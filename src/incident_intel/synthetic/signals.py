"""Metric and log signals: what "normal" looks like, and how incidents bend it.

Normal behaviour has a daily rhythm (busy evenings, quiet mornings), busier
weekends, and random noise. Incidents are added on top as `MetricEffect`s, e.g.
"error rate of order-service rises to 30% between 14:05 and 14:50".
"""

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from incident_intel.domain import LogEvent, LogLevel, MetricName, ServiceTier
from incident_intel.synthetic.topology import Topology

Series = dict[tuple[str, MetricName], list[float]]


@dataclass(frozen=True)
class Profile:
    """Typical values for one service at average load."""

    rps: float  # requests per second
    latency_ms: float  # p95 latency
    error_rate: float  # fraction of requests that fail
    cpu_pct: float
    memory_pct: float


PROFILES: dict[str, Profile] = {
    "web-frontend": Profile(rps=220, latency_ms=180, error_rate=0.002, cpu_pct=35, memory_pct=55),
    "api-gateway": Profile(rps=400, latency_ms=120, error_rate=0.002, cpu_pct=40, memory_pct=50),
    "auth-service": Profile(rps=90, latency_ms=60, error_rate=0.001, cpu_pct=25, memory_pct=45),
    "catalog-service": Profile(rps=180, latency_ms=80, error_rate=0.001, cpu_pct=30, memory_pct=60),
    "search-service": Profile(rps=60, latency_ms=150, error_rate=0.002, cpu_pct=45, memory_pct=65),
    "cart-service": Profile(rps=70, latency_ms=50, error_rate=0.001, cpu_pct=20, memory_pct=40),
    "order-service": Profile(rps=25, latency_ms=220, error_rate=0.002, cpu_pct=30, memory_pct=55),
    "payment-service": Profile(rps=12, latency_ms=350, error_rate=0.003, cpu_pct=15, memory_pct=40),
    "inventory-service": Profile(
        rps=30, latency_ms=70, error_rate=0.001, cpu_pct=20, memory_pct=45
    ),
    "notification-service": Profile(
        rps=15, latency_ms=90, error_rate=0.004, cpu_pct=10, memory_pct=35
    ),
    "user-db": Profile(rps=150, latency_ms=8, error_rate=0.0002, cpu_pct=30, memory_pct=70),
    "order-db": Profile(rps=80, latency_ms=12, error_rate=0.0002, cpu_pct=35, memory_pct=72),
    "catalog-db": Profile(rps=260, latency_ms=6, error_rate=0.0002, cpu_pct=40, memory_pct=68),
    "redis-cache": Profile(rps=900, latency_ms=2, error_rate=0.0001, cpu_pct=20, memory_pct=55),
    # External: we only see it from the outside (a synthetic probe), so no CPU/memory.
    "payment-provider": Profile(rps=12, latency_ms=300, error_rate=0.002, cpu_pct=0, memory_pct=0),
}

ALL_METRICS = list(MetricName)
EXTERNAL_METRICS = [MetricName.REQUEST_RATE, MetricName.ERROR_RATE, MetricName.LATENCY_P95_MS]


def metrics_for(topology: Topology, service: str) -> list[MetricName]:
    if topology.get(service).tier == ServiceTier.EXTERNAL:
        return EXTERNAL_METRICS
    return ALL_METRICS


def load_factor(ts: datetime) -> float:
    """How busy the shop is at `ts`, relative to average (1.0).

    A sine wave gives a daily cycle peaking around 19:00 UTC and bottoming out
    around 07:00 UTC; weekends are 20% busier.
    """
    hour = ts.hour + ts.minute / 60
    daily = 1 + 0.45 * math.sin(2 * math.pi * (hour - 13) / 24)
    weekend = 1.2 if ts.weekday() >= 5 else 1.0
    return daily * weekend


def alert_threshold(service: str, metric: MetricName) -> float:
    """The level at which monitoring raises an alert for this service and metric."""
    profile = PROFILES[service]
    thresholds = {
        MetricName.ERROR_RATE: 0.05,
        MetricName.LATENCY_P95_MS: round(profile.latency_ms * 3),
        MetricName.CPU_PCT: 85.0,
        MetricName.MEMORY_PCT: 90.0,
        MetricName.REQUEST_RATE: round(profile.rps * 3),
    }
    return thresholds[metric]


def baseline_metrics(topology: Topology, timestamps: list[datetime], rng: random.Random) -> Series:
    """Generate normal-looking metrics for every service at every timestamp."""
    series: Series = {}
    for name in topology.names:
        profile = PROFILES[name]
        metrics = metrics_for(topology, name)
        for metric in metrics:
            series[(name, metric)] = []
        for ts in timestamps:
            load = load_factor(ts)
            values = {
                MetricName.REQUEST_RATE: profile.rps * load * rng.gauss(1, 0.05),
                MetricName.LATENCY_P95_MS: profile.latency_ms
                * (1 + 0.25 * (load - 1))
                * rng.gauss(1, 0.06),
                MetricName.ERROR_RATE: profile.error_rate * rng.lognormvariate(0, 0.4),
                MetricName.CPU_PCT: profile.cpu_pct * load * rng.gauss(1, 0.07),
                MetricName.MEMORY_PCT: profile.memory_pct + rng.gauss(0, 1.5),
            }
            for metric in metrics:
                series[(name, metric)].append(_clamp(metric, values[metric]))
    return series


@dataclass
class MetricEffect:
    """A change applied on top of normal metric values during an incident.

    Use `target` to push a value towards a level (error_rate -> 0.3) or `factor`
    to multiply it (latency x4). `ramp_minutes` makes the change gradual, like a
    memory leak, instead of instant, like a crash.
    """

    service: str
    metric: MetricName
    start: datetime
    end: datetime
    target: float | None = None
    factor: float | None = None
    ramp_minutes: int = 0

    def __post_init__(self) -> None:
        if (self.target is None) == (self.factor is None):
            raise ValueError("MetricEffect needs exactly one of `target` or `factor`")


def apply_effects(
    series: Series, timestamps: list[datetime], effects: list[MetricEffect], rng: random.Random
) -> None:
    """Modify `series` in place so incidents show up in the metrics."""
    t0 = timestamps[0]
    step = timestamps[1] - timestamps[0]
    for effect in effects:
        values = series.get((effect.service, effect.metric))
        if values is None:  # e.g. CPU of an external service: not observable
            continue
        first = max(0, math.ceil((effect.start - t0) / step))
        last = min(len(timestamps), math.ceil((effect.end - t0) / step))
        for i in range(first, last):
            elapsed = (timestamps[i] - effect.start).total_seconds() / 60
            strength = 1.0 if effect.ramp_minutes <= 0 else min(1.0, elapsed / effect.ramp_minutes)
            current = values[i]
            if effect.target is not None:
                # A level ("memory pinned at 99%") wobbles only a little.
                goal = max(current, effect.target * rng.gauss(1, 0.03))
                new = current + (goal - current) * strength
            else:
                assert effect.factor is not None
                new = current * (1 + (effect.factor * rng.gauss(1, 0.08) - 1) * strength)
            values[i] = _clamp(effect.metric, new)


def _clamp(metric: MetricName, value: float) -> float:
    upper = {
        MetricName.ERROR_RATE: 1.0,
        MetricName.CPU_PCT: 100.0,
        MetricName.MEMORY_PCT: 100.0,
    }.get(metric, math.inf)
    return min(max(value, 0.0), upper)


# ------------------------------------------------------------------------- logs

RESOURCES = {
    "web-frontend": "pages",
    "api-gateway": "products",
    "auth-service": "sessions",
    "catalog-service": "products",
    "search-service": "queries",
    "cart-service": "carts",
    "order-service": "orders",
    "payment-service": "payments",
    "inventory-service": "stock",
    "notification-service": "emails",
    "user-db": "users",
    "order-db": "orders",
    "catalog-db": "products",
    "redis-cache": "keys",
}

NORMAL_LINES = {
    ServiceTier.FRONTEND: [
        "GET / 200 {ms}ms",
        "GET /products/{id} 200 {ms}ms",
        "GET /cart 200 {ms}ms",
        "rendered /checkout in {ms}ms",
    ],
    ServiceTier.GATEWAY: [
        "route=/api/{resource} status=200 duration={ms}ms",
        "GET /api/products/{id} -> catalog-service 200 {ms}ms",
        "rate limiter: {n} tokens available",
    ],
    ServiceTier.BACKEND: [
        "GET /v1/{resource}/{id} 200 {ms}ms",
        "POST /v1/{resource} 201 {ms}ms",
        "processed batch of {n} {resource}",
        "health check ok",
    ],
    ServiceTier.DATASTORE: [
        "accepted client connection id={id}",
        "checkpoint complete: wrote {n} buffers",
        "background save of {resource} completed in {ms}ms",
    ],
}

WARN_LINES = [
    "slow request: {ms}ms exceeds the 300ms budget",
    "retrying request (attempt 2/3)",
    "deprecated API version v1 used by a client",
    "cache miss rate above 20% for 1 minute",
]


def normal_logs(
    topology: Topology, timestamps: list[datetime], rng: random.Random
) -> list[LogEvent]:
    """Background log lines: mostly INFO, a few harmless WARNs (real logs are noisy)."""
    step_seconds = int((timestamps[1] - timestamps[0]).total_seconds())
    logs: list[LogEvent] = []
    for ts in timestamps:
        load = load_factor(ts)
        for name in topology.names:
            tier = topology.get(name).tier
            if tier == ServiceTier.EXTERNAL:  # we can't see inside third-party systems
                continue
            if rng.random() > 0.35 * load:  # busier hours produce more lines
                continue
            fields = {
                "resource": RESOURCES.get(name, "items"),
                "ms": rng.randint(5, 400),
                "id": rng.randint(1000, 99999),
                "n": rng.randint(1, 500),
            }
            if rng.random() < 0.05:
                level, template = LogLevel.WARN, rng.choice(WARN_LINES)
            else:
                level, template = LogLevel.INFO, rng.choice(NORMAL_LINES[tier])
            logs.append(
                LogEvent(
                    timestamp=ts + timedelta(seconds=rng.randint(0, step_seconds - 1)),
                    service=name,
                    level=level,
                    message=template.format(**fields),
                )
            )
    return logs
