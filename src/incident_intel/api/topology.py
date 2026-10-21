"""Read-only context: which services exist, and what was deployed when."""

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from incident_intel.api.deps import SessionDep
from incident_intel.domain import Deployment, Service
from incident_intel.storage import repository

router = APIRouter(tags=["topology"])

# AwareDatetime rejects times without a timezone with a clear 422 error.
ServiceFilter = Annotated[str | None, Query(description="Only this service")]
Since = Annotated[AwareDatetime | None, Query(description="At or after, e.g. 2026-09-10T00:00Z")]
Until = Annotated[AwareDatetime | None, Query(description="Before, e.g. 2026-09-11T00:00Z")]


@router.get("/services", response_model=list[Service])
def list_services(session: SessionDep) -> list[Service]:
    """Every service and the services it depends on."""
    return repository.list_services(session)


@router.get("/deployments", response_model=list[Deployment])
def list_deployments(
    session: SessionDep,
    service: ServiceFilter = None,
    since: Since = None,
    until: Until = None,
) -> list[Deployment]:
    """Deployments in time order. "What changed before this incident?" starts here."""
    return repository.list_deployments(session, service=service, since=since, until=until)
