"""Domain model: the shared vocabulary of the whole platform.

Every component (ingestion API, ML models, the RCA agent, dashboards) talks in
these types, so they live in one place. Pydantic validates data whenever it is
created or parsed, which catches bad input at the edges of the system.

Two kinds of data live here:

* Operational data the platform *sees*: services, deployments, metrics, logs,
  incidents (from monitoring alerts) and tickets (from people).
* Ground truth (`SeededIncident`): the real answer for each incident we plant in
  the synthetic data. Models never see it; the evaluation harness uses it to
  score them.
"""

from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base class for all domain models.

    `extra="forbid"` rejects unknown fields, so a typo like `servcie=` fails loudly
    instead of being silently ignored.
    """

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- enums
# StrEnum members behave like strings ("P1" == Priority.P1) but only allow the
# listed values. That keeps data consistent and gives autocomplete in the editor.


class ServiceTier(StrEnum):
    FRONTEND = "frontend"
    GATEWAY = "gateway"
    BACKEND = "backend"
    DATASTORE = "datastore"
    EXTERNAL = "external"  # third-party APIs we depend on but cannot see inside


class Criticality(StrEnum):
    HIGH = "high"  # revenue or login stops if this breaks
    MEDIUM = "medium"
    LOW = "low"


class Priority(StrEnum):
    P1 = "P1"  # critical: core business function down for many users
    P2 = "P2"  # high: major degradation or a key feature broken
    P3 = "P3"  # medium: limited impact, workaround exists
    P4 = "P4"  # low: minor issue or request


class MetricName(StrEnum):
    REQUEST_RATE = "request_rate"  # requests per second
    ERROR_RATE = "error_rate"  # fraction of requests failing, between 0 and 1
    LATENCY_P95_MS = "latency_p95_ms"  # 95% of requests are faster than this
    CPU_PCT = "cpu_pct"
    MEMORY_PCT = "memory_pct"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"


class IncidentStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class DeploymentStatus(StrEnum):
    SUCCEEDED = "succeeded"
    ROLLED_BACK = "rolled_back"


class TicketChannel(StrEnum):
    PORTAL = "portal"
    EMAIL = "email"
    CHAT = "chat"
    PHONE = "phone"


class TicketCategory(StrEnum):
    AVAILABILITY = "availability"  # something is down or erroring
    PERFORMANCE = "performance"  # slow, timing out
    ACCESS = "access"  # login, passwords, permissions
    PAYMENTS = "payments"
    DATA = "data"  # wrong or missing data
    SERVICE_REQUEST = "service_request"  # "please do X for me", not a fault


class RootCauseType(StrEnum):
    BAD_DEPLOYMENT = "bad_deployment"
    DB_CONNECTION_POOL_EXHAUSTION = "db_connection_pool_exhaustion"
    THIRD_PARTY_OUTAGE = "third_party_outage"
    CACHE_MEMORY_PRESSURE = "cache_memory_pressure"


# -------------------------------------------------------------- operational data


class Service(StrictModel):
    """A component of the system and what it calls."""

    name: str
    tier: ServiceTier
    team: str
    criticality: Criticality
    depends_on: list[str] = Field(default_factory=list, description="Services this one calls")


class Deployment(StrictModel):
    """A release of a new version of one service."""

    id: str
    service: str
    version: str
    deployed_at: AwareDatetime
    author: str
    change_summary: str
    status: DeploymentStatus = DeploymentStatus.SUCCEEDED
    rolled_back_at: AwareDatetime | None = None


class MetricPoint(StrictModel):
    """One measurement of one metric for one service at one moment."""

    timestamp: AwareDatetime
    service: str
    metric: MetricName
    value: float = Field(ge=0)


class LogEvent(StrictModel):
    """One application log line."""

    timestamp: AwareDatetime
    service: str
    level: LogLevel
    message: str
    trace_id: str | None = None


class Incident(StrictModel):
    """An incident opened by a monitoring alert."""

    id: str
    opened_at: AwareDatetime
    service: str = Field(description="Service the alert fired on (a symptom, not always the cause)")
    title: str
    description: str
    priority: Priority
    status: IncidentStatus = IncidentStatus.RESOLVED
    resolved_at: AwareDatetime | None = None
    alert_metric: MetricName | None = None
    observed_value: float | None = None
    threshold: float | None = None


class Ticket(StrictModel):
    """A report written by a person: an employee or a customer."""

    id: str
    created_at: AwareDatetime
    reporter: str
    channel: TicketChannel
    subject: str
    body: str
    category: TicketCategory = Field(description="Category assigned by the service desk")
    priority: Priority
    resolved_at: AwareDatetime | None = None


# ------------------------------------------------------------------ ground truth


class SeededIncident(StrictModel):
    """The true story behind an incident planted in the synthetic data.

    Used only for evaluation: "did the platform find this root cause, group these
    alerts and tickets together, and suggest this runbook?"
    """

    id: str
    root_cause: RootCauseType
    root_cause_service: str
    started_at: AwareDatetime
    ended_at: AwareDatetime
    priority: Priority
    affected_services: list[str] = Field(description="Services that showed symptoms")
    trigger_deployment_id: str | None = Field(
        default=None, description="The deployment that caused it, if any"
    )
    decoy_deployment_ids: list[str] = Field(
        default_factory=list, description="Innocent deployments that happened just before it"
    )
    incident_ids: list[str] = Field(description="Monitoring incidents caused by this event")
    ticket_ids: list[str] = Field(description="User tickets caused by this event")
    expected_runbook: str
    remediation: str
    summary: str
