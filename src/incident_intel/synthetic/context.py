"""The toolbox scenarios use to plant an incident: `ScenarioContext`.

Each helper adds one kind of evidence to the world (a metric change, log lines,
an alert, user tickets, a deployment) and remembers it for the ground truth.
Scenario recipes in `scenarios.py` are written almost entirely with these.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from incident_intel.domain import (
    Deployment,
    DeploymentStatus,
    Incident,
    IncidentStatus,
    LogEvent,
    LogLevel,
    MetricName,
    Priority,
    RootCauseType,
    SeededIncident,
    ServiceTier,
    Ticket,
    TicketCategory,
)
from incident_intel.synthetic.signals import RESOURCES, MetricEffect, alert_threshold
from incident_intel.synthetic.text import (
    HARMLESS_CHANGES,
    humanize,
    random_channel,
    random_employee,
    random_reporter,
)
from incident_intel.synthetic.topology import Topology
from incident_intel.synthetic.world import World

ERROR_RATE = MetricName.ERROR_RATE
LATENCY = MetricName.LATENCY_P95_MS

TicketTemplates = list[tuple[str, str]]  # (subject, body) pairs


@dataclass
class ScenarioContext:
    """Everything a scenario needs to plant one incident, plus friendly helpers."""

    world: World
    rng: random.Random
    root_service: str
    start: datetime
    end: datetime
    priority: Priority
    summary: str = ""
    remediation: str = ""
    affected: set[str] = field(default_factory=set)
    incident_ids: list[str] = field(default_factory=list)
    ticket_ids: list[str] = field(default_factory=list)
    trigger_deployment_id: str | None = None
    decoy_deployment_ids: list[str] = field(default_factory=list)

    @property
    def topology(self) -> Topology:
        return self.world.topology

    def at(self, minutes: float) -> datetime:
        """The time `minutes` after the incident started."""
        return self.start + timedelta(minutes=minutes)

    def direct_callers(self, service: str | None = None) -> list[str]:
        """Services that call `service` (default: the root cause) directly."""
        callers = self.topology.callers_of(service or self.root_service)
        return [name for name, hops in callers.items() if hops == 1]

    # ----------------------------------------------------------------- metrics

    def change_metric(
        self,
        service: str,
        metric: MetricName,
        *,
        target: float | None = None,
        factor: float | None = None,
        ramp_minutes: int = 0,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> None:
        """Make `metric` of `service` misbehave during the incident."""
        self.world.effects.append(
            MetricEffect(
                service=service,
                metric=metric,
                start=start or self.start,
                end=end or self.end,
                target=target,
                factor=factor,
                ramp_minutes=ramp_minutes,
            )
        )
        self.affected.add(service)

    def spread_to_callers(
        self, *, error_rate: float, latency_factor: float, decay: float = 0.5
    ) -> None:
        """Everything upstream of the root cause feels a weaker version of the pain.

        A caller 1 hop away gets `decay` x the effect, 2 hops away `decay`^2, and
        so on. This is why the loudest alert is often NOT on the broken service.
        """
        for caller, hops in self.topology.callers_of(self.root_service).items():
            strength = decay**hops
            self.change_metric(caller, ERROR_RATE, target=error_rate * strength)
            self.change_metric(caller, LATENCY, factor=1 + (latency_factor - 1) * strength)

    # -------------------------------------------------------------------- logs

    def log(
        self,
        service: str,
        messages: list[str],
        *,
        level: LogLevel = LogLevel.ERROR,
        every_minutes: float = 3.0,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> None:
        """Emit lines from `messages` at random moments, about every `every_minutes`."""
        t = start or self.start
        stop = end or self.end
        while True:
            t += timedelta(minutes=self.rng.expovariate(1 / every_minutes))
            if t >= stop:
                break
            message = self.rng.choice(messages).format(**self._fields())
            self.world.logs.append(
                LogEvent(
                    timestamp=t,
                    service=service,
                    level=level,
                    message=message,
                    trace_id=f"{self.rng.getrandbits(64):016x}",
                )
            )
        self.affected.add(service)

    # ------------------------------------------------------------- deployments

    def deploy(
        self, service: str, *, at: datetime, summary: str, trigger: bool = False
    ) -> Deployment:
        """Record a deployment. `trigger=True` marks it as the cause of this incident."""
        deployment = Deployment(
            id=self.world.temp_id("DEP"),
            service=service,
            version=self.world.next_version(service),
            deployed_at=at,
            author=random_employee(self.rng),
            change_summary=summary.format(resource=RESOURCES.get(service, "items")),
        )
        self.world.deployments.append(deployment)
        if trigger:
            self.trigger_deployment_id = deployment.id
        return deployment

    def rollback(self, deployment: Deployment, *, at: datetime) -> None:
        deployment.status = DeploymentStatus.ROLLED_BACK
        deployment.rolled_back_at = at

    def decoy_deployment(self, probability: float = 0.5) -> None:
        """Maybe add an innocent deployment just before the incident.

        Real outages often follow an unrelated deploy. A good RCA system must not
        blame every recent change, so we plant traps and check it avoids them.
        """
        if self.rng.random() >= probability:
            return
        app_tiers = (ServiceTier.FRONTEND, ServiceTier.GATEWAY, ServiceTier.BACKEND)
        candidates = [s for s in self.topology.names_in_tiers(*app_tiers) if s != self.root_service]
        deployment = self.deploy(
            self.rng.choice(candidates),
            at=self.start - timedelta(minutes=self.rng.randint(10, 45)),
            summary=self.rng.choice(HARMLESS_CHANGES),
        )
        self.decoy_deployment_ids.append(deployment.id)

    # ------------------------------------------------------------------ alerts

    def alert(self, service: str, metric: MetricName, *, after_minutes: int, title: str) -> None:
        """Open a monitoring incident on `service` when `metric` crosses its threshold.

        Monitoring checks metrics every few minutes (one "bucket"), so the alert
        fires shortly after the first check at or after `after_minutes`.
        """
        step = self.world.timestamps[1] - self.world.timestamps[0]
        desired = self.at(after_minutes)
        check_time = next(ts for ts in self.world.timestamps if ts >= desired)
        opened_at = check_time + timedelta(seconds=self.rng.randint(20, int(step.seconds * 0.8)))
        threshold = alert_threshold(service, metric)
        incident = Incident(
            id=self.world.temp_id("INC"),
            opened_at=opened_at,
            service=service,
            title=title,
            description=f"Alert: {metric.value} on {service} crossed its threshold of {threshold}.",
            priority=self.priority,
            status=IncidentStatus.RESOLVED,
            resolved_at=self.end + timedelta(minutes=self.rng.randint(2, 10)),
            alert_metric=metric,
            threshold=threshold,
        )
        self.world.incidents.append(incident)
        self.incident_ids.append(incident.id)

    # ----------------------------------------------------------------- tickets

    def tickets(
        self,
        templates: TicketTemplates,
        *,
        category: TicketCategory,
        count: tuple[int, int] = (2, 4),
    ) -> None:
        """Users notice the problem and file tickets, each worded differently."""
        duration = (self.end - self.start).total_seconds() / 60
        for _ in range(self.rng.randint(*count)):
            subject, body = self.rng.choice(templates)
            fields = self._fields()
            created_at = self.at(self.rng.uniform(3, max(4, duration * 0.8)))
            ticket = Ticket(
                id=self.world.temp_id("TCK"),
                created_at=created_at,
                reporter=random_reporter(self.rng),
                channel=random_channel(self.rng),
                subject=humanize(subject.format(**fields), self.rng),
                body=humanize(body.format(**fields), self.rng),
                category=category,
                priority=self.rng.choice([self.priority, _one_lower(self.priority)]),
                resolved_at=self.end + timedelta(minutes=self.rng.randint(10, 120)),
            )
            self.world.tickets.append(ticket)
            self.ticket_ids.append(ticket.id)

    # ------------------------------------------------------------------ finish

    def _fields(self) -> dict[str, int]:
        """Random values that templates can use, e.g. "order {order}"."""
        return {
            "order": self.rng.randint(100000, 999999),
            "id": self.rng.randint(1000, 99999),
            "n": self.rng.randint(2, 12),
            "ms": self.rng.randint(5000, 30000),
        }

    def finish(self, root_cause: RootCauseType, expected_runbook: str) -> SeededIncident:
        """Package everything the scenario did into the ground-truth record."""
        if not self.summary or not self.remediation:
            raise ValueError(f"The {root_cause} scenario must set ctx.summary and ctx.remediation")
        return SeededIncident(
            id=self.world.temp_id("SI"),
            root_cause=root_cause,
            root_cause_service=self.root_service,
            started_at=self.start,
            ended_at=self.end,
            priority=self.priority,
            affected_services=sorted(self.affected),
            trigger_deployment_id=self.trigger_deployment_id,
            decoy_deployment_ids=self.decoy_deployment_ids,
            incident_ids=self.incident_ids,
            ticket_ids=self.ticket_ids,
            expected_runbook=expected_runbook,
            remediation=self.remediation,
            summary=self.summary,
        )


def _one_lower(priority: Priority) -> Priority:
    order = list(Priority)
    return order[min(order.index(priority) + 1, len(order) - 1)]
