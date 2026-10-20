"""Seeded incident scenarios: recipes for planting realistic outages.

Each scenario knows how one kind of failure looks from the outside: which
metrics move, what the logs say, which alerts fire and what users complain
about. The `ScenarioContext` helpers (see `context.py`) do the planting and
record the true answer, so we can later check whether the platform figured it out.

To add a new kind of incident:
  1. add a value to `RootCauseType` in `domain/models.py`
  2. subclass `Scenario` below and implement `inject()`
  3. add the class to `SCENARIOS` at the bottom of this file
"""

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import ClassVar

from incident_intel.domain import LogLevel, MetricName, Priority, RootCauseType, TicketCategory
from incident_intel.synthetic.context import ScenarioContext, TicketTemplates
from incident_intel.synthetic.signals import RESOURCES
from incident_intel.synthetic.text import RISKY_CHANGES

ERROR_RATE = MetricName.ERROR_RATE
LATENCY = MetricName.LATENCY_P95_MS
CPU = MetricName.CPU_PCT
MEMORY = MetricName.MEMORY_PCT


class Scenario(ABC):
    """A recipe for one kind of incident."""

    root_cause: ClassVar[RootCauseType]
    candidate_services: ClassVar[tuple[str, ...]]  # where this failure can happen
    duration_minutes: ClassVar[tuple[int, int]] = (30, 90)
    expected_runbook: ClassVar[str]

    def priority_for(self, service: str) -> Priority:
        return Priority.P2

    @abstractmethod
    def inject(self, ctx: ScenarioContext) -> None:
        """Plant the incident's signals and set `ctx.summary` and `ctx.remediation`."""


# --------------------------------------------------------------- user tickets

FEATURE_TICKETS: dict[str, tuple[TicketCategory, TicketTemplates]] = {
    "auth-service": (
        TicketCategory.ACCESS,
        [
            ("Can't log in", "The login page says 'something went wrong' every time I sign in."),
            ("Login broken", "Getting an error after entering my password. Tried 3 browsers."),
            ("Unable to sign in to my account", "Sign in fails with error 500, please fix."),
        ],
    ),
    "catalog-service": (
        TicketCategory.AVAILABILITY,
        [
            ("Product pages not loading", "Clicking any product shows an error page."),
            ("Error 500 on product details", "I can see the list but product details fail."),
            ("Shop is broken?", "Half the items show 'Oops, something went wrong'."),
        ],
    ),
    "search-service": (
        TicketCategory.AVAILABILITY,
        [
            ("Search not working", "Every search returns an error page."),
            ("Can't search for products", "The search bar just shows an error for any query."),
        ],
    ),
    "cart-service": (
        TicketCategory.AVAILABILITY,
        [
            ("Can't add items to cart", "Add to cart spins and then shows an error."),
            ("Cart error", "My cart page shows error 500 and I can't check out."),
        ],
    ),
    "order-service": (
        TicketCategory.AVAILABILITY,
        [
            ("Checkout fails", "Error when placing order {order}, tried several times."),
            ("Cannot place order", "Checkout says 'order could not be created'. Lost a sale!"),
            ("Orders failing", "Our customers report checkout errors since a few minutes."),
        ],
    ),
}


# ------------------------------------------------------------------ scenarios


class BadDeployment(Scenario):
    """A release ships a bug: errors start at the deploy and stop at the rollback."""

    root_cause = RootCauseType.BAD_DEPLOYMENT
    candidate_services = (
        "auth-service",
        "catalog-service",
        "search-service",
        "cart-service",
        "order-service",
    )
    duration_minutes = (25, 75)
    expected_runbook = "rollback-bad-deployment"

    def priority_for(self, service: str) -> Priority:
        return Priority.P1 if service in ("auth-service", "order-service") else Priority.P2

    def inject(self, ctx: ScenarioContext) -> None:
        root = ctx.root_service
        release = ctx.deploy(
            root, at=ctx.start, summary=ctx.rng.choice(RISKY_CHANGES), trigger=True
        )

        ctx.change_metric(root, ERROR_RATE, target=ctx.rng.uniform(0.2, 0.4))
        ctx.change_metric(root, LATENCY, factor=3.5)
        ctx.change_metric(root, CPU, factor=1.4)
        ctx.spread_to_callers(error_rate=0.3, latency_factor=2.5)

        ctx.log(
            root,
            [
                "Unhandled exception in RequestHandler: KeyError: 'sku'",
                "TypeError: cannot read property 'id' of undefined (request {id})",
                "500 Internal Server Error on POST /v1/" + RESOURCES[root],
                "Serialization failed: unexpected null in field 'price'",
            ],
            every_minutes=1.5,
        )
        ctx.log(
            "api-gateway",
            [
                f"upstream {root} returned 500 Internal Server Error",
                f"upstream {root} error, request {{id}}",
            ],
            every_minutes=2.5,
        )

        ctx.alert(
            "api-gateway",
            ERROR_RATE,
            after_minutes=ctx.rng.randint(3, 7),
            title="High 5xx error rate on api-gateway",
        )
        ctx.alert(
            root,
            ERROR_RATE,
            after_minutes=ctx.rng.randint(5, 10),
            title=f"Error rate above 5% on {root}",
        )

        category, templates = FEATURE_TICKETS[root]
        ctx.tickets(templates, category=category)

        ctx.rollback(release, at=ctx.end)
        ctx.summary = (
            f"Release {release.version} of {root} ('{release.change_summary}') introduced a bug "
            f"that returned 5xx errors until the release was rolled back."
        )
        ctx.remediation = (
            f"Roll back {root} to the previous version, confirm error rates recover, "
            f"then add a regression test before redeploying."
        )


class DbConnectionPoolExhaustion(Scenario):
    """A database runs out of connections; every service using it starts timing out."""

    root_cause = RootCauseType.DB_CONNECTION_POOL_EXHAUSTION
    candidate_services = ("order-db", "user-db", "catalog-db")
    duration_minutes = (30, 80)
    expected_runbook = "database-connection-pool-exhaustion"

    TICKETS: ClassVar[dict[str, tuple[TicketCategory, TicketTemplates]]] = {
        "order-db": (
            TicketCategory.PERFORMANCE,
            [
                ("Checkout extremely slow", "Checkout spins for a minute and then times out."),
                ("Order page timing out", "Placing order {order} takes forever and then fails."),
                ("Site very slow at checkout", "Payment step hangs, customers are complaining."),
            ],
        ),
        "user-db": (
            TicketCategory.ACCESS,
            [
                (
                    "Login takes forever",
                    "After entering my password it loads for ages, then fails.",
                ),
                ("Sign in timing out", "Login times out every time, can't get into my account."),
            ],
        ),
        "catalog-db": (
            TicketCategory.PERFORMANCE,
            [
                ("Product pages very slow", "Product pages take 20+ seconds to load."),
                ("Shop is crawling", "Browsing the catalog is extremely slow right now."),
            ],
        ),
    }

    def priority_for(self, service: str) -> Priority:
        return Priority.P1 if service in ("order-db", "user-db") else Priority.P2

    def inject(self, ctx: ScenarioContext) -> None:
        db = ctx.root_service
        clients = ctx.direct_callers()
        cause = ctx.rng.choice(
            [
                "a long-running report query held connections open",
                "a retry storm opened far more connections than usual",
                "a batch job leaked connections without closing them",
            ]
        )
        ctx.decoy_deployment(probability=0.6)

        ctx.change_metric(db, CPU, factor=1.8)
        ctx.change_metric(db, LATENCY, factor=6)
        ctx.spread_to_callers(error_rate=0.4, latency_factor=10)

        ctx.log(
            db,
            [
                "FATAL: sorry, too many clients already",
                "FATAL: remaining connection slots are reserved for superuser connections",
                "LOG: connection rejected: max_connections=100 reached",
            ],
            level=LogLevel.FATAL,
            every_minutes=2,
        )
        for client in clients:
            ctx.log(
                client,
                [
                    "QueuePool limit of size 20 overflow 10 reached, connection timed out",
                    f"Timed out after {{ms}}ms waiting for a connection to {db}",
                    f"Health check degraded: {db} connection unavailable",
                ],
                every_minutes=1.5,
            )

        main_client = clients[0]
        ctx.alert(
            main_client,
            LATENCY,
            after_minutes=ctx.rng.randint(4, 8),
            title=f"p95 latency above threshold on {main_client}",
        )
        ctx.alert(
            "api-gateway",
            ERROR_RATE,
            after_minutes=ctx.rng.randint(6, 12),
            title="High 5xx error rate on api-gateway",
        )

        category, templates = self.TICKETS[db]
        ctx.tickets(templates, category=category)

        ctx.summary = (
            f"{db} ran out of connections because {cause}, so {', '.join(clients)} "
            f"timed out waiting for the connection pool."
        )
        ctx.remediation = (
            f"Terminate long-running and idle-in-transaction sessions on {db}, restart the "
            f"connection pools of {', '.join(clients)}, then cap pool sizes and add a "
            f"statement timeout."
        )


class ThirdPartyOutage(Scenario):
    """The external payment provider goes down; checkouts fail. Nothing to roll back."""

    root_cause = RootCauseType.THIRD_PARTY_OUTAGE
    candidate_services = ("payment-provider",)
    duration_minutes = (20, 60)
    expected_runbook = "third-party-payment-outage"

    def priority_for(self, service: str) -> Priority:
        return Priority.P1

    def inject(self, ctx: ScenarioContext) -> None:
        provider = ctx.root_service
        ctx.decoy_deployment(probability=0.5)

        ctx.change_metric(provider, ERROR_RATE, target=ctx.rng.uniform(0.5, 0.8))
        ctx.change_metric(provider, LATENCY, factor=6)
        ctx.spread_to_callers(error_rate=0.7, latency_factor=5, decay=0.6)

        ctx.log(
            "payment-service",
            [
                "PaymentProviderError: POST https://api.paypro.example/v1/charges returned 503",
                "Timeout calling payment provider after 10000ms (attempt 3/3)",
                "Circuit breaker OPEN for payment-provider after 20 consecutive failures",
            ],
            every_minutes=1,
        )
        ctx.log(
            "order-service",
            [
                "Checkout failed for order {order}: payment service unavailable",
                "Order {order} moved to PAYMENT_FAILED",
            ],
            every_minutes=2,
        )

        ctx.alert(
            "payment-service",
            ERROR_RATE,
            after_minutes=ctx.rng.randint(2, 5),
            title="Error rate above 5% on payment-service",
        )
        ctx.alert(
            "order-service",
            ERROR_RATE,
            after_minutes=ctx.rng.randint(4, 9),
            title="Checkout failures above 5% on order-service",
        )

        ctx.tickets(
            [
                ("Payment failed", "My card payment keeps failing at checkout for order {order}."),
                ("Card declined but money taken?", "Payment error but I think I was charged."),
                ("Can't pay", "Checkout says 'payment could not be processed', tried 2 cards."),
                ("Customers can't pay", "Lots of customers report failed payments right now."),
            ],
            category=TicketCategory.PAYMENTS,
            count=(3, 5),
        )

        ctx.summary = (
            "The external payment provider (PayPro) had an outage, returning HTTP 503s and "
            "timeouts, so payments and checkouts failed until the provider recovered."
        )
        ctx.remediation = (
            "Fail over to the backup payment provider, show a 'payments delayed' banner and "
            "open a support case with PayPro. No internal rollback is needed."
        )


class CacheMemoryPressure(Scenario):
    """Redis fills up to its memory limit and rejects writes: logouts and lost carts.

    Memory climbs for a while BEFORE users notice: an early warning that a good
    anomaly detector should catch.
    """

    root_cause = RootCauseType.CACHE_MEMORY_PRESSURE
    candidate_services = ("redis-cache",)
    duration_minutes = (25, 70)
    expected_runbook = "redis-memory-pressure"

    def inject(self, ctx: ScenarioContext) -> None:
        cache = ctx.root_service
        warning_minutes = ctx.rng.randint(30, 60)
        warning_start = ctx.start - timedelta(minutes=warning_minutes)

        ctx.change_metric(
            cache, MEMORY, target=99, ramp_minutes=warning_minutes, start=warning_start
        )
        ctx.change_metric(cache, LATENCY, factor=4)
        ctx.spread_to_callers(error_rate=0.3, latency_factor=2.5)

        ctx.log(
            cache,
            [
                "used_memory rising quickly, approaching maxmemory",
                "keyspace grew by {n}% in the last 10 minutes",
            ],
            level=LogLevel.WARN,
            every_minutes=8,
            start=warning_start,
            end=ctx.start,
        )
        ctx.log(
            cache,
            [
                "OOM command not allowed when used memory > 'maxmemory'",
                "maxmemory reached with policy noeviction, rejecting writes",
            ],
            every_minutes=2,
        )
        ctx.log(
            "auth-service",
            [
                "ResponseError: OOM command not allowed when used memory > 'maxmemory'",
                "Session store write failed, forcing user to sign in again",
            ],
            every_minutes=2,
        )
        ctx.log(
            "cart-service",
            ["Failed to save cart {id}: OOM command not allowed when used memory > 'maxmemory'"],
            every_minutes=2.5,
        )

        ctx.alert(
            cache,
            MEMORY,
            after_minutes=ctx.rng.randint(1, 3),
            title=f"Memory above 90% on {cache}",
        )
        ctx.alert(
            "auth-service",
            ERROR_RATE,
            after_minutes=ctx.rng.randint(3, 8),
            title="Error rate above 5% on auth-service",
        )

        ctx.tickets(
            [
                ("Keeps logging me out", "I get logged out every few minutes and lose my session."),
                ("Session expired constantly", "Have to log in again on every page."),
            ],
            category=TicketCategory.ACCESS,
            count=(1, 3),
        )
        ctx.tickets(
            [
                ("My cart got emptied", "Items I added to my cart disappeared."),
                ("Cart lost items", "Added {n} items, refreshed, the cart is empty again."),
            ],
            category=TicketCategory.DATA,
            count=(1, 2),
        )

        ctx.summary = (
            f"{cache} filled up to its memory limit with the 'noeviction' policy, so writes "
            f"failed: sessions could not be saved (users logged out) and carts were lost."
        )
        ctx.remediation = (
            f"Free memory on {cache} (expire or delete oversized keys), switch the eviction "
            f"policy to allkeys-lru or raise maxmemory, then find what caused the key growth."
        )


# Every scenario the generator can plant. Add new scenario classes here.
SCENARIOS: list[type[Scenario]] = [
    BadDeployment,
    DbConnectionPoolExhaustion,
    ThirdPartyOutage,
    CacheMemoryPressure,
]
