"""ShopFast: the fictional e-commerce company whose systems we monitor.

Customers use the web frontend, which goes through an API gateway to backend
services. Those services use databases, a Redis cache and an external payment
provider. When something deep in this chain breaks, everything that calls it
(directly or indirectly) starts showing symptoms.
"""

from collections import deque

from incident_intel.domain import Criticality, Service, ServiceTier

H, M, L = Criticality.HIGH, Criticality.MEDIUM, Criticality.LOW

SHOPFAST_SERVICES: list[Service] = [
    Service(
        name="web-frontend",
        tier=ServiceTier.FRONTEND,
        team="web",
        criticality=H,
        depends_on=["api-gateway"],
    ),
    Service(
        name="api-gateway",
        tier=ServiceTier.GATEWAY,
        team="platform",
        criticality=H,
        depends_on=[
            "auth-service",
            "catalog-service",
            "search-service",
            "cart-service",
            "order-service",
        ],
    ),
    Service(
        name="auth-service",
        tier=ServiceTier.BACKEND,
        team="identity",
        criticality=H,
        depends_on=["user-db", "redis-cache"],
    ),
    Service(
        name="catalog-service",
        tier=ServiceTier.BACKEND,
        team="catalog",
        criticality=M,
        depends_on=["catalog-db", "redis-cache"],
    ),
    Service(
        name="search-service",
        tier=ServiceTier.BACKEND,
        team="catalog",
        criticality=M,
        depends_on=["catalog-service"],
    ),
    Service(
        name="cart-service",
        tier=ServiceTier.BACKEND,
        team="checkout",
        criticality=H,
        depends_on=["redis-cache", "catalog-service"],
    ),
    Service(
        name="order-service",
        tier=ServiceTier.BACKEND,
        team="checkout",
        criticality=H,
        depends_on=["order-db", "payment-service", "inventory-service", "notification-service"],
    ),
    Service(
        name="payment-service",
        tier=ServiceTier.BACKEND,
        team="payments",
        criticality=H,
        depends_on=["payment-provider"],
    ),
    Service(
        name="inventory-service",
        tier=ServiceTier.BACKEND,
        team="catalog",
        criticality=M,
        depends_on=["catalog-db"],
    ),
    Service(
        name="notification-service",
        tier=ServiceTier.BACKEND,
        team="platform",
        criticality=L,
    ),
    Service(name="user-db", tier=ServiceTier.DATASTORE, team="identity", criticality=H),
    Service(name="order-db", tier=ServiceTier.DATASTORE, team="checkout", criticality=H),
    Service(name="catalog-db", tier=ServiceTier.DATASTORE, team="catalog", criticality=M),
    Service(name="redis-cache", tier=ServiceTier.DATASTORE, team="platform", criticality=H),
    Service(name="payment-provider", tier=ServiceTier.EXTERNAL, team="payments", criticality=H),
]


class Topology:
    """The services and who-calls-whom, with a few graph questions answered."""

    def __init__(self, services: list[Service]) -> None:
        self.services: dict[str, Service] = {s.name: s for s in services}
        for service in services:
            for dependency in service.depends_on:
                if dependency not in self.services:
                    raise ValueError(f"{service.name} depends on unknown service {dependency!r}")

    @property
    def names(self) -> list[str]:
        return list(self.services)

    def get(self, name: str) -> Service:
        return self.services[name]

    def names_in_tiers(self, *tiers: ServiceTier) -> list[str]:
        return [s.name for s in self.services.values() if s.tier in tiers]

    def callers_of(self, name: str) -> dict[str, int]:
        """Every service that directly or indirectly calls `name`, with its distance.

        For `order-db` this gives {"order-service": 1, "api-gateway": 2,
        "web-frontend": 3}. These are the services that feel the pain when
        `name` breaks: the "blast radius". It is a breadth-first search over the
        dependency arrows, walked backwards.
        """
        callers: dict[str, int] = {}
        queue = deque([(name, 0)])
        while queue:
            current, distance = queue.popleft()
            for service in self.services.values():
                if current in service.depends_on and service.name not in callers:
                    if service.name == name:
                        continue
                    callers[service.name] = distance + 1
                    queue.append((service.name, distance + 1))
        return callers
