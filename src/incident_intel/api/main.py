"""FastAPI application: the front door of the platform.

Run it locally with:
    uv run uvicorn incident_intel.api.main:app --reload
Then open http://127.0.0.1:8000/docs for interactive API docs.
"""

from fastapi import FastAPI
from pydantic import BaseModel

from incident_intel import __version__
from incident_intel.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Ingests IT incidents, tickets, logs and metrics; triages them, predicts SLA "
        "breaches, detects anomalies and proposes evidence-linked root causes."
    ),
)


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
