"""The `World`: a container for everything the generator produces, plus saving.

Scenarios and background generators append to the lists here. At the end,
`finalize()` tidies the data up and `save()` writes it to disk.
"""

import csv
import json
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from incident_intel.domain import (
    Deployment,
    Incident,
    LogEvent,
    MetricName,
    SeededIncident,
    Ticket,
)
from incident_intel.synthetic.signals import MetricEffect, Series
from incident_intel.synthetic.topology import Topology


@dataclass(frozen=True)
class GeneratorConfig:
    """Knobs for the generator. The same config + seed always gives the same data."""

    seed: int = 42
    start: datetime = datetime(2026, 9, 7, tzinfo=UTC)  # a Monday
    days: int = 14
    num_incidents: int = 12
    bucket_minutes: int = 5  # one metric value per service every 5 minutes

    @property
    def end(self) -> datetime:
        return self.start + timedelta(days=self.days)


@dataclass
class World:
    config: GeneratorConfig
    topology: Topology
    timestamps: list[datetime]
    deployments: list[Deployment] = field(default_factory=list)
    incidents: list[Incident] = field(default_factory=list)
    tickets: list[Ticket] = field(default_factory=list)
    logs: list[LogEvent] = field(default_factory=list)
    effects: list[MetricEffect] = field(default_factory=list)
    metrics: Series = field(default_factory=dict)
    seeded_incidents: list[SeededIncident] = field(default_factory=list)
    false_alarm_incident_ids: list[str] = field(default_factory=list)
    _counters: dict[str, int] = field(default_factory=dict)

    # ------------------------------------------------------------- ids & versions

    def temp_id(self, prefix: str) -> str:
        """A placeholder id. `finalize()` renumbers everything in time order."""
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"tmp-{prefix}-{self._counters[prefix]}"

    def next_version(self, service: str) -> str:
        """Version numbers that go up with every deployment of a service."""
        key = f"version:{service}"
        self._counters[key] = self._counters.get(key, 0) + 1
        return f"v1.{20 + self._counters[key]}.0"

    # ---------------------------------------------------------------- finalizing

    def finalize(self) -> None:
        self._fill_observed_values()
        self._renumber()
        self.logs.sort(key=lambda log: (log.timestamp, log.service))

    def _fill_observed_values(self) -> None:
        """Record the metric value each alert actually saw at the moment it fired."""
        t0, step = self.timestamps[0], self.timestamps[1] - self.timestamps[0]
        for incident in self.incidents:
            if incident.alert_metric is None or incident.observed_value is not None:
                continue
            index = math.floor((incident.opened_at - t0) / step)
            value = self.metrics[(incident.service, incident.alert_metric)][index]
            digits = 4 if incident.alert_metric == MetricName.ERROR_RATE else 1
            incident.observed_value = round(value, digits)

    def _renumber(self) -> None:
        """Give ids in time order (INC-0001 is the oldest), like a real ticketing system.

        This also prevents "data leakage": if incident tickets were created last,
        they would all have the highest ids, and a model could learn that shortcut
        instead of reading the text.
        """
        dep = _renumber(self.deployments, "DEP", lambda d: d.deployed_at)
        inc = _renumber(self.incidents, "INC", lambda i: i.opened_at)
        tck = _renumber(self.tickets, "TCK", lambda t: t.created_at)
        self.false_alarm_incident_ids = sorted(inc[i] for i in self.false_alarm_incident_ids)
        for truth in self.seeded_incidents:
            truth.incident_ids = sorted(inc[i] for i in truth.incident_ids)
            truth.ticket_ids = sorted(tck[t] for t in truth.ticket_ids)
            truth.decoy_deployment_ids = sorted(dep[d] for d in truth.decoy_deployment_ids)
            if truth.trigger_deployment_id:
                truth.trigger_deployment_id = dep[truth.trigger_deployment_id]
        _renumber(self.seeded_incidents, "SI", lambda s: s.started_at)

    # -------------------------------------------------------------------- saving

    def save(self, out_dir: Path) -> dict[str, int]:
        """Write every dataset to `out_dir` and return how many records each has."""
        out_dir.mkdir(parents=True, exist_ok=True)
        services = [s.model_dump(mode="json") for s in self.topology.services.values()]
        _write_json(out_dir / "services.json", services)
        _write_jsonl(out_dir / "deployments.jsonl", self.deployments)
        _write_jsonl(out_dir / "incidents.jsonl", self.incidents)
        _write_jsonl(out_dir / "tickets.jsonl", self.tickets)
        _write_jsonl(out_dir / "logs.jsonl", self.logs)
        metric_rows = self._write_metrics(out_dir / "metrics.csv")
        _write_json(
            out_dir / "ground_truth.json",
            {
                "generator": {
                    "seed": self.config.seed,
                    "start": self.config.start.isoformat(),
                    "days": self.config.days,
                    "bucket_minutes": self.config.bucket_minutes,
                },
                "seeded_incidents": [s.model_dump(mode="json") for s in self.seeded_incidents],
                "false_alarm_incident_ids": self.false_alarm_incident_ids,
            },
        )
        return {
            "services": len(services),
            "deployments": len(self.deployments),
            "incidents": len(self.incidents),
            "tickets": len(self.tickets),
            "log lines": len(self.logs),
            "metric points": metric_rows,
            "seeded incidents": len(self.seeded_incidents),
            "false alarms": len(self.false_alarm_incident_ids),
        }

    def _write_metrics(self, path: Path) -> int:
        """CSV in time order: timestamp, service, metric, value."""
        rows = 0
        keys = list(self.metrics)
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "service", "metric", "value"])
            for i, ts in enumerate(self.timestamps):
                stamp = ts.isoformat()
                for service, metric in keys:
                    value = self.metrics[(service, metric)][i]
                    digits = 5 if metric == MetricName.ERROR_RATE else 2
                    writer.writerow([stamp, service, metric.value, round(value, digits)])
                    rows += 1
        return rows


def _renumber(items: list[Any], prefix: str, time_of: Any) -> dict[str, str]:
    items.sort(key=lambda item: (time_of(item), item.id))
    mapping: dict[str, str] = {}
    for number, item in enumerate(items, start=1):
        new_id = f"{prefix}-{number:04d}"
        mapping[item.id] = new_id
        item.id = new_id
    return mapping


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, items: list[BaseModel]) -> None:
    """JSON Lines: one JSON object per line. Easy to stream and append to."""
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(item.model_dump_json() + "\n")
