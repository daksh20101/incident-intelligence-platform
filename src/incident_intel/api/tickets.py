"""Ticket endpoints: the service desk sends user reports here."""

from fastapi import APIRouter, HTTPException, Response, status

from incident_intel.api.deps import Limit, Offset, Page, SessionDep
from incident_intel.domain import Ticket
from incident_intel.storage import repository

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post(
    "",
    response_model=Ticket,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Already received with identical data (safe retry)"},
        409: {"description": "A ticket with this id exists with different data"},
    },
)
def create_ticket(ticket: Ticket, response: Response, session: SessionDep) -> Ticket:
    """Store a ticket. Idempotent, like `POST /incidents`."""
    existing = repository.get_ticket(session, ticket.id)
    if existing is None:
        repository.add_ticket(session, ticket)
        return ticket
    if existing == ticket:
        response.status_code = status.HTTP_200_OK
        return existing
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Ticket {ticket.id} already exists with different data",
    )


@router.get("", response_model=Page[Ticket])
def list_tickets(session: SessionDep, limit: Limit = 50, offset: Offset = 0) -> Page[Ticket]:
    """Tickets, newest first, one page at a time."""
    items, total = repository.list_tickets(session, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{ticket_id}", response_model=Ticket, responses={404: {"description": "Not found"}})
def get_ticket(ticket_id: str, session: SessionDep) -> Ticket:
    ticket = repository.get_ticket(session, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return ticket
