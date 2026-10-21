"""Reading and writing domain objects: the only code that knows about tables.

The API and, later, the AI components call these functions with and get back
Pydantic domain models (`Incident`, `Ticket`, ...), never table rows. This is
the *repository pattern*: swap SQLite for Postgres, or add caching, by changing
this file only.
"""

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from incident_intel.domain import (
    Deployment,
    Incident,
    IncidentStatus,
    LogEvent,
    MetricPoint,
    Priority,
    Service,
    Ticket,
)
from incident_intel.storage.tables import (
    Base,
    DeploymentRow,
    IncidentRow,
    LogRow,
    MetricRow,
    ServiceRow,
    TicketRow,
)

# --------------------------------------------------------------- conversion


def _row_values(model: BaseModel) -> dict[str, Any]:
    """Domain model -> plain values a table row accepts (enums become strings)."""
    values = model.model_dump()
    return {key: getattr(value, "value", value) for key, value in values.items()}


# ---------------------------------------------------------------- incidents


def get_incident(session: Session, incident_id: str) -> Incident | None:
    row = session.get(IncidentRow, incident_id)
    return None if row is None else Incident.model_validate(row, from_attributes=True)


def add_incident(session: Session, incident: Incident) -> None:
    session.add(IncidentRow(**_row_values(incident)))
    session.commit()


def list_incidents(
    session: Session,
    *,
    service: str | None = None,
    priority: Priority | None = None,
    status: IncidentStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Incident], int]:
    """A page of incidents, newest first, plus how many there are in total."""
    query = select(IncidentRow)
    if service is not None:
        query = query.where(IncidentRow.service == service)
    if priority is not None:
        query = query.where(IncidentRow.priority == priority)
    if status is not None:
        query = query.where(IncidentRow.status == status)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(IncidentRow.opened_at.desc(), IncidentRow.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [Incident.model_validate(row, from_attributes=True) for row in rows], total


# ------------------------------------------------------------------ tickets


def get_ticket(session: Session, ticket_id: str) -> Ticket | None:
    row = session.get(TicketRow, ticket_id)
    return None if row is None else Ticket.model_validate(row, from_attributes=True)


def add_ticket(session: Session, ticket: Ticket) -> None:
    session.add(TicketRow(**_row_values(ticket)))
    session.commit()


def list_tickets(session: Session, *, limit: int = 50, offset: int = 0) -> tuple[list[Ticket], int]:
    """A page of tickets, newest first, plus how many there are in total."""
    query = select(TicketRow)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(TicketRow.created_at.desc(), TicketRow.id.desc()).limit(limit).offset(offset)
    )
    return [Ticket.model_validate(row, from_attributes=True) for row in rows], total


# --------------------------------------------------- services & deployments


def list_services(session: Session) -> list[Service]:
    rows = session.scalars(select(ServiceRow).order_by(ServiceRow.name))
    return [Service.model_validate(row, from_attributes=True) for row in rows]


def list_deployments(
    session: Session,
    *,
    service: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[Deployment]:
    """Deployments in time order, optionally for one service and/or a time window."""
    query = select(DeploymentRow)
    if service is not None:
        query = query.where(DeploymentRow.service == service)
    if since is not None:
        query = query.where(DeploymentRow.deployed_at >= since)
    if until is not None:
        query = query.where(DeploymentRow.deployed_at < until)
    rows = session.scalars(query.order_by(DeploymentRow.deployed_at, DeploymentRow.id))
    return [Deployment.model_validate(row, from_attributes=True) for row in rows]


# ------------------------------------------------------------- bulk loading


def bulk_insert(
    session: Session, row_class: type[Base], models: Iterable[BaseModel], batch_size: int = 5000
) -> int:
    """Insert many records fast: one INSERT statement per batch instead of per row.

    Used by the loader for hundreds of thousands of metric points. Returns the
    number of rows inserted. The caller commits.
    """
    count = 0
    batch: list[dict[str, Any]] = []
    for model in models:
        batch.append(_row_values(model))
        if len(batch) >= batch_size:
            session.execute(insert(row_class), batch)
            count += len(batch)
            batch = []
    if batch:
        session.execute(insert(row_class), batch)
        count += len(batch)
    return count


TABLE_FOR = {
    Service: ServiceRow,
    Deployment: DeploymentRow,
    Incident: IncidentRow,
    Ticket: TicketRow,
    LogEvent: LogRow,
    MetricPoint: MetricRow,
}
