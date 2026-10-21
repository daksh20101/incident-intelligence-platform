"""FastAPI application: the front door of the platform.

Run it locally with:
    uv run uvicorn incident_intel.api.main:app --reload
Then open http://127.0.0.1:8000/docs for interactive API docs.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from incident_intel import __version__
from incident_intel.api import incidents, tickets, topology
from incident_intel.api.deps import SessionDep
from incident_intel.config import get_settings
from incident_intel.storage.db import create_tables, get_engine

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Code that runs once when the server starts (before `yield`) and stops (after)."""
    create_tables(get_engine())
    yield


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Ingests IT incidents, tickets, logs and metrics; triages them, predicts SLA "
        "breaches, detects anomalies and proposes evidence-linked root causes."
    ),
    lifespan=lifespan,
)
app.include_router(incidents.router)
app.include_router(tickets.router)
app.include_router(topology.router)


class HealthResponse(BaseModel):
    """Shape of the /health reply. FastAPI uses it to validate and document the API."""

    status: str
    environment: str


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Liveness probe: answers 'ok' if the service is up.

    Load balancers, Docker and Kubernetes call endpoints like this to decide
    whether to send traffic to (or restart) a service.
    """
    return HealthResponse(status="ok", environment=settings.environment)


@app.get(
    "/ready",
    response_model=HealthResponse,
    tags=["system"],
    responses={503: {"description": "The database is unreachable"}},
)
def ready(session: SessionDep) -> HealthResponse:
    """Readiness probe: answers 'ready' only if the database answers too.

    Liveness asks "is the process alive?"; readiness asks "can it do real work
    right now?". An orchestrator stops sending traffic while this returns 503.
    """
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return HealthResponse(status="ready", environment=settings.environment)


class VersionResponse(BaseModel):
    """Shape of the /version reply."""

    name: str
    version: str


@app.get("/version", response_model=VersionResponse, tags=["system"])
def version() -> VersionResponse:
    """Return the app name and version."""
    return VersionResponse(name=settings.app_name, version=__version__)
