"""Incident endpoints: monitoring systems send alerts here, people read them back."""

from fastapi import APIRouter, HTTPException, Response, status

from incident_intel.api.deps import Limit, Offset, Page, SessionDep
from incident_intel.domain import Incident
from incident_intel.storage import repository

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.post(
    "",
    response_model=Incident,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Already received with identical data (safe retry)"},
        409: {"description": "An incident with this id exists with different data"},
    },
)
def create_incident(incident: Incident, response: Response, session: SessionDep) -> Incident:
    """Store an incident sent by a monitoring system.

    The endpoint is **idempotent**: monitoring tools retry when the network
    hiccups, so receiving the same incident twice must not create a duplicate.
    """
    existing = repository.get_incident(session, incident.id)
    if existing is None:
        repository.add_incident(session, incident)
        return incident
    if existing == incident:
        response.status_code = status.HTTP_200_OK
        return existing
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Incident {incident.id} already exists with different data",
    )


@router.get("", response_model=Page[Incident])
def list_incidents(session: SessionDep, limit: Limit = 50, offset: Offset = 0) -> Page[Incident]:
    """Incidents, newest first, one page at a time."""
    items, total = repository.list_incidents(session, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/{incident_id}", response_model=Incident, responses={404: {"description": "Not found"}}
)
def get_incident(incident_id: str, session: SessionDep) -> Incident:
    incident = repository.get_incident(session, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return incident
