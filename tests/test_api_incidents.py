"""Tests for the /incidents endpoints."""

from typing import Any

from fastapi.testclient import TestClient


def make_incident(**changes: Any) -> dict[str, Any]:
    """A valid incident as JSON; pass keyword arguments to change any field."""
    incident = {
        "id": "INC-1001",
        "opened_at": "2026-09-10T14:05:00Z",
        "service": "order-service",
        "title": "Error rate above 5% on order-service",
        "description": "Alert: error_rate on order-service crossed its threshold of 0.05.",
        "priority": "P1",
        "alert_metric": "error_rate",
        "observed_value": 0.23,
        "threshold": 0.05,
    }
    incident.update(changes)
    return incident


def test_created_incident_can_be_read_back(client: TestClient) -> None:
    created = client.post("/incidents", json=make_incident())

    assert created.status_code == 201
    fetched = client.get("/incidents/INC-1001")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Error rate above 5% on order-service"


def test_new_incidents_are_open_by_default(client: TestClient) -> None:
    response = client.post("/incidents", json=make_incident())

    assert response.json()["status"] == "open"


def test_sending_the_same_incident_twice_is_safe(client: TestClient) -> None:
    first = client.post("/incidents", json=make_incident())
    retry = client.post("/incidents", json=make_incident())

    assert first.status_code == 201
    assert retry.status_code == 200
    assert client.get("/incidents").json()["total"] == 1


def test_same_id_with_different_data_is_a_conflict(client: TestClient) -> None:
    client.post("/incidents", json=make_incident())
    response = client.post("/incidents", json=make_incident(title="Something else"))

    assert response.status_code == 409


def test_unknown_incident_returns_404(client: TestClient) -> None:
    assert client.get("/incidents/INC-9999").status_code == 404


def test_invalid_incident_is_rejected_with_422(client: TestClient) -> None:
    response = client.post("/incidents", json=make_incident(priority="P9"))

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "priority"]


def test_times_in_other_timezones_are_stored_as_utc(client: TestClient) -> None:
    client.post("/incidents", json=make_incident(opened_at="2026-09-10T16:05:00+02:00"))

    opened_at = client.get("/incidents/INC-1001").json()["opened_at"]
    assert opened_at == "2026-09-10T14:05:00Z"


def test_list_is_newest_first_and_paginated(client: TestClient) -> None:
    for day in range(1, 6):
        incident = make_incident(id=f"INC-{day}", opened_at=f"2026-09-0{day}T10:00:00Z")
        client.post("/incidents", json=incident)

    page = client.get("/incidents", params={"limit": 2, "offset": 1}).json()

    assert page["total"] == 5
    assert [i["id"] for i in page["items"]] == ["INC-4", "INC-3"]


def test_page_size_is_limited(client: TestClient) -> None:
    assert client.get("/incidents", params={"limit": 501}).status_code == 422


def test_incidents_can_be_filtered_by_service_and_priority(client: TestClient) -> None:
    client.post("/incidents", json=make_incident(id="INC-1", priority="P1"))
    client.post("/incidents", json=make_incident(id="INC-2", priority="P3"))
    client.post("/incidents", json=make_incident(id="INC-3", service="api-gateway"))

    by_service = client.get("/incidents", params={"service": "order-service"}).json()
    by_both = client.get("/incidents", params={"service": "order-service", "priority": "P1"})

    assert {i["id"] for i in by_service["items"]} == {"INC-1", "INC-2"}
    assert by_service["total"] == 2
    assert [i["id"] for i in by_both.json()["items"]] == ["INC-1"]


def test_incidents_can_be_filtered_by_status(client: TestClient) -> None:
    client.post("/incidents", json=make_incident(id="INC-1"))
    client.post("/incidents", json=make_incident(id="INC-2", status="resolved"))

    page = client.get("/incidents", params={"status": "open"}).json()

    assert [i["id"] for i in page["items"]] == ["INC-1"]


def test_unknown_priority_filter_is_rejected(client: TestClient) -> None:
    response = client.get("/incidents", params={"priority": "P9"})

    assert response.status_code == 422
