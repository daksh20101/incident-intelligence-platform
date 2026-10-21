"""Tests for the /tickets endpoints."""

from typing import Any

from fastapi.testclient import TestClient


def make_ticket(**changes: Any) -> dict[str, Any]:
    ticket = {
        "id": "TCK-2001",
        "created_at": "2026-09-10T14:12:00Z",
        "reporter": "customer-12345",
        "channel": "portal",
        "subject": "Checkout fails",
        "body": "Error when placing my order, tried several times.",
        "category": "availability",
        "priority": "P2",
    }
    ticket.update(changes)
    return ticket


def test_created_ticket_can_be_read_back(client: TestClient) -> None:
    assert client.post("/tickets", json=make_ticket()).status_code == 201

    assert client.get("/tickets/TCK-2001").json()["subject"] == "Checkout fails"


def test_ticket_retries_are_idempotent_and_conflicts_rejected(client: TestClient) -> None:
    assert client.post("/tickets", json=make_ticket()).status_code == 201
    assert client.post("/tickets", json=make_ticket()).status_code == 200
    assert client.post("/tickets", json=make_ticket(body="changed")).status_code == 409


def test_unknown_ticket_returns_404(client: TestClient) -> None:
    assert client.get("/tickets/TCK-0000").status_code == 404


def test_tickets_are_listed_newest_first(client: TestClient) -> None:
    client.post("/tickets", json=make_ticket(id="TCK-1", created_at="2026-09-01T09:00:00Z"))
    client.post("/tickets", json=make_ticket(id="TCK-2", created_at="2026-09-02T09:00:00Z"))

    page = client.get("/tickets").json()

    assert [t["id"] for t in page["items"]] == ["TCK-2", "TCK-1"]
