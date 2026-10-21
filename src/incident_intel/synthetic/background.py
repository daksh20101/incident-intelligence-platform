"""Background activity: the everyday noise around real incidents.

Without noise, every deployment would be guilty and every ticket would be about
an outage. Real operations data is mostly routine: harmless releases, password
resets, how-to questions and alerts that fire and clear on their own.
"""

import random
from datetime import timedelta

from incident_intel.domain import (
    Deployment,
    Incident,
    IncidentStatus,
    MetricName,
    Priority,
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
from incident_intel.synthetic.world import World

APP_TIERS = (ServiceTier.FRONTEND, ServiceTier.GATEWAY, ServiceTier.BACKEND)

EMPLOYEE, CUSTOMER, ANYONE = "employee", "customer", "anyone"

# (category, priority, who files it, subject, body)
ROUTINE_TICKETS: list[tuple[TicketCategory, Priority, str, str, str]] = [
    (TicketCategory.ACCESS, Priority.P3, ANYONE, "Password reset not working",
     "I requested a password reset but never got the email."),
    (TicketCategory.ACCESS, Priority.P4, EMPLOYEE, "Need access to the reporting dashboard",
     "Please give me read access to the sales reports."),
    (TicketCategory.ACCESS, Priority.P3, ANYONE, "Account locked",
     "My account got locked after too many attempts, please unlock."),
    (TicketCategory.SERVICE_REQUEST, Priority.P4, EMPLOYEE, "How do I export last month's orders?",
     "Need a CSV of all orders from last month for accounting."),
    (TicketCategory.SERVICE_REQUEST, Priority.P4, EMPLOYEE, "New user for warehouse team",
     "Please create an account for our new warehouse colleague."),
    (TicketCategory.SERVICE_REQUEST, Priority.P4, CUSTOMER, "Change my email address",
     "I want to change the email on my account."),
    (TicketCategory.PERFORMANCE, Priority.P3, EMPLOYEE, "Admin panel a bit slow",
     "The admin panel felt slow this morning, seems ok now."),
    (TicketCategory.PAYMENTS, Priority.P3, CUSTOMER, "Refund status",
     "Where is my refund for order {order}? It's been 5 days."),
    (TicketCategory.PAYMENTS, Priority.P3, CUSTOMER, "Charged twice?",
     "I see two charges on my card for order {order}."),
    (TicketCategory.DATA, Priority.P3, ANYONE, "Wrong price on product",
     "Product {order} shows a different price in the cart than on the page."),
    (TicketCategory.DATA, Priority.P4, CUSTOMER, "Duplicate customer record",
     "There are two accounts with my email address."),
    (TicketCategory.AVAILABILITY, Priority.P3, EMPLOYEE, "Warehouse printer offline",
     "The label printer in the warehouse is offline again."),
    (TicketCategory.AVAILABILITY, Priority.P3, EMPLOYEE, "VPN keeps disconnecting",
     "My VPN drops every 10 minutes when working from home."),
]  # fmt: skip


def _reporter(who: str, rng: random.Random) -> str:
    if who == EMPLOYEE:
        return random_employee(rng)
    if who == CUSTOMER:
        return f"customer-{rng.randint(10000, 99999)}"
    return random_reporter(rng)


def add_routine_deployments(world: World, rng: random.Random) -> None:
    """2-5 harmless releases per day during working hours."""
    app_services = world.topology.names_in_tiers(*APP_TIERS)
    for day in range(world.config.days):
        day_start = world.config.start + timedelta(days=day)
        for _ in range(rng.randint(2, 5)):
            service = rng.choice(app_services)
            world.deployments.append(
                Deployment(
                    id=world.temp_id("DEP"),
                    service=service,
                    version=world.next_version(service),
                    deployed_at=day_start + timedelta(minutes=rng.randint(9 * 60, 18 * 60)),
                    author=random_employee(rng),
                    change_summary=rng.choice(HARMLESS_CHANGES).format(
                        resource=RESOURCES.get(service, "items")
                    ),
                )
            )


def add_routine_tickets(world: World, rng: random.Random) -> None:
    """3-7 everyday tickets per day that have nothing to do with outages."""
    for day in range(world.config.days):
        day_start = world.config.start + timedelta(days=day)
        for _ in range(rng.randint(3, 7)):
            category, priority, who, subject, body = rng.choice(ROUTINE_TICKETS)
            created_at = day_start + timedelta(minutes=rng.randint(7 * 60, 22 * 60))
            world.tickets.append(
                Ticket(
                    id=world.temp_id("TCK"),
                    created_at=created_at,
                    reporter=_reporter(who, rng),
                    channel=random_channel(rng),
                    subject=humanize(subject, rng),
                    body=humanize(body.format(order=rng.randint(100000, 999999)), rng),
                    category=category,
                    priority=priority,
                    resolved_at=created_at + timedelta(minutes=rng.randint(20, 3 * 24 * 60)),
                )
            )


def add_false_alarms(world: World, rng: random.Random) -> None:
    """Short CPU spikes that trigger an alert and clear by themselves (no real incident).

    Alert fatigue is a real problem in operations; the platform should learn to
    tell these apart from real incidents.
    """
    app_services = world.topology.names_in_tiers(*APP_TIERS)
    step = world.timestamps[1] - world.timestamps[0]
    for day in range(world.config.days):
        if rng.random() > 0.7:
            continue
        day_start = world.config.start + timedelta(days=day)
        service = rng.choice(app_services)
        start = day_start + timedelta(minutes=rng.randint(30, 23 * 60))
        end = start + timedelta(minutes=rng.randint(10, 20))
        world.effects.append(
            MetricEffect(
                service=service, metric=MetricName.CPU_PCT, start=start, end=end, target=96
            )
        )
        check_time = next(ts for ts in world.timestamps if ts >= start)
        incident = Incident(
            id=world.temp_id("INC"),
            opened_at=check_time + timedelta(seconds=rng.randint(20, int(step.seconds * 0.8))),
            service=service,
            title=f"CPU above 85% on {service}",
            description=f"Alert: cpu_pct on {service} crossed its threshold of 85.0.",
            priority=Priority.P4,
            status=IncidentStatus.RESOLVED,
            resolved_at=end + timedelta(minutes=rng.randint(1, 3)),
            alert_metric=MetricName.CPU_PCT,
            threshold=alert_threshold(service, MetricName.CPU_PCT),
        )
        world.incidents.append(incident)
        world.false_alarm_incident_ids.append(incident.id)
