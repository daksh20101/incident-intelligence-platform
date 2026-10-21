"""Load the synthetic dataset files into the database.

Every record is validated with its domain model on the way in ("validate at
the edges"), so a corrupt file fails loudly here instead of confusing the AI
later. `ground_truth.json` is deliberately NOT loaded: the platform must never
see the answers it is being evaluated on.
"""

import csv
import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from incident_intel.domain import (
    Deployment,
    Incident,
    LogEvent,
    MetricName,
    MetricPoint,
    Service,
    Ticket,
)
from incident_intel.storage.db import reset_tables
from incident_intel.storage.repository import TABLE_FOR, bulk_insert

JSONL_FILES: list[tuple[str, type[BaseModel]]] = [
    ("deployments.jsonl", Deployment),
    ("incidents.jsonl", Incident),
    ("tickets.jsonl", Ticket),
    ("logs.jsonl", LogEvent),
]


def load_dataset(engine: Engine, data_dir: Path) -> dict[str, int]:
    """Replace everything in the database with the files in `data_dir`.

    Runs as one transaction: if any file is bad, nothing is saved.
    """
    missing = [
        name
        for name in ["services.json", "metrics.csv", *(f for f, _ in JSONL_FILES)]
        if not (data_dir / name).exists()
    ]
    if missing:
        raise FileNotFoundError(f"Missing in {data_dir}: {', '.join(missing)}")

    reset_tables(engine)
    counts: dict[str, int] = {}
    with Session(engine) as session:
        services = [Service.model_validate(s) for s in _read_json(data_dir / "services.json")]
        counts["services"] = bulk_insert(session, TABLE_FOR[Service], services)
        for file_name, model in JSONL_FILES:
            records = _read_jsonl(data_dir / file_name, model)
            counts[file_name.removesuffix(".jsonl")] = bulk_insert(
                session, TABLE_FOR[model], records
            )
        counts["metrics"] = bulk_insert(
            session, TABLE_FOR[MetricPoint], _read_metrics(data_dir / "metrics.csv")
        )
        session.commit()
    return counts


def _read_json(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl[M: BaseModel](path: Path, model: type[M]) -> Iterator[M]:
    """Read a JSON Lines file one line at a time (no need to load it all at once)."""
    with path.open(encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            if line.strip():
                try:
                    yield model.model_validate_json(line)
                except ValueError as exc:
                    raise ValueError(f"{path.name} line {line_number}: {exc}") from exc


def _read_metrics(path: Path) -> Iterator[MetricPoint]:
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            yield MetricPoint(
                timestamp=datetime.fromisoformat(row["timestamp"]),
                service=row["service"],
                metric=MetricName(row["metric"]),
                value=float(row["value"]),
            )
