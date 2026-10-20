"""Tests for the system endpoints.

TestClient calls the app in-process, so no server needs to be running.
"""

from fastapi.testclient import TestClient

from incident_intel import __version__
from incident_intel.api.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "environment" in body


def test_openapi_docs_are_published() -> None:
    # FastAPI generates an OpenAPI spec automatically; /docs renders it.
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/health" in response.json()["paths"]


def test_version_returns_package_version() -> None:
    response = client.get("/version")

    assert response.status_code == 200
    assert response.json()["version"] == __version__
