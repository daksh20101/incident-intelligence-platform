"""Tests for the database layer and the data loader."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session

from incident_intel.storage import repository
from incident_intel.storage.loader import load_dataset
from incident_intel.storage.tables import IncidentRow
from incident_intel.synthetic import GeneratorConfig, World, generate_world


@pytest.fixture(scope="module")
def world() -> World:
    return generate_world(GeneratorConfig(seed=3, days=2, num_incidents=2))


@pytest.fixture
def loaded(engine: Engine, world: World, tmp_path: Path) -> dict[str, int]:
    world.save(tmp_path)
    return load_dataset(engine, tmp_path)


def test_loader_loads_every_record(loaded: dict[str, int], world: World) -> None:
    assert loaded["services"] == len(world.topology.services)
    assert loaded["incidents"] == len(world.incidents)
    assert loaded["tickets"] == len(world.tickets)
    assert loaded["logs"] == len(world.logs)
    assert loaded["metrics"] == len(world.timestamps) * len(world.metrics)


def test_records_come_back_exactly_as_they_went_in(
    loaded: dict[str, int], world: World, session: Session
) -> None:
    for incident in world.incidents:
        assert repository.get_incident(session, incident.id) == incident
    for ticket in world.tickets:
        assert repository.get_ticket(session, ticket.id) == ticket


def test_loader_refuses_an_incomplete_folder(engine: Engine, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="services.json"):
        load_dataset(engine, tmp_path)


def test_deployments_filter_by_service_and_time(
    loaded: dict[str, int], world: World, session: Session
) -> None:
    target = world.deployments[len(world.deployments) // 2]

    found = repository.list_deployments(
        session, service=target.service, since=target.deployed_at, until=target.deployed_at
    )
    assert found == []  # "until" is exclusive
    found = repository.list_deployments(session, service=target.service, since=target.deployed_at)
    assert target in found
    assert all(d.service == target.service and d.deployed_at >= target.deployed_at for d in found)


def test_timestamps_without_timezone_are_refused(session: Session) -> None:
    naive = datetime(2026, 9, 10, 14, 0)
    row = IncidentRow(
        id="INC-1",
        opened_at=naive,
        service="x",
        title="t",
        description="d",
        priority="P3",
        status="open",
    )
    session.add(row)

    with pytest.raises(StatementError, match="without a timezone"):
        session.commit()


def test_services_and_deployments_endpoints(loaded: dict[str, int], client: TestClient) -> None:
    services = client.get("/services").json()
    assert len(services) == loaded["services"]
    assert "order-db" in next(s for s in services if s["name"] == "order-service")["depends_on"]

    since = datetime(2026, 9, 7, 12, tzinfo=UTC).isoformat()
    deployments = client.get("/deployments", params={"since": since}).json()
    assert all(d["deployed_at"] >= "2026-09-07T12:00:00Z" for d in deployments)


def test_time_filters_must_include_a_timezone(client: TestClient) -> None:
    response = client.get("/deployments", params={"since": "2026-09-07T12:00:00"})

    assert response.status_code == 422


def test_ready_probe_checks_the_database(client: TestClient) -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
