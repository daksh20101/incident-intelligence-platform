"""Tests for the synthetic data generator.

If the ground truth is wrong, every evaluation built on it later is wrong too,
so these tests check that the planted incidents are consistent and visible.
"""

import csv
import json
import statistics
from pathlib import Path

import pytest

from incident_intel.domain import (
    Deployment,
    Incident,
    LogEvent,
    MetricName,
    RootCauseType,
    SeededIncident,
    Ticket,
)
from incident_intel.synthetic import GeneratorConfig, World, generate_world
from incident_intel.synthetic.scenarios import SCENARIOS
from incident_intel.synthetic.topology import SHOPFAST_SERVICES, Topology

# Small and fast, but enough room for one incident of every kind.
SMALL = GeneratorConfig(seed=7, days=4, num_incidents=len(SCENARIOS))


@pytest.fixture(scope="module")
def world() -> World:
    return generate_world(SMALL)


# ------------------------------------------------------------------ topology


def test_blast_radius_follows_the_call_chain() -> None:
    topology = Topology(SHOPFAST_SERVICES)

    assert topology.callers_of("order-db") == {
        "order-service": 1,
        "api-gateway": 2,
        "web-frontend": 3,
    }


def test_unknown_dependency_is_rejected() -> None:
    broken = [SHOPFAST_SERVICES[0].model_copy(update={"depends_on": ["no-such-service"]})]

    with pytest.raises(ValueError, match="unknown service"):
        Topology(broken)


# ----------------------------------------------------------- reproducibility


def test_same_seed_gives_identical_files(tmp_path: Path) -> None:
    generate_world(SMALL).save(tmp_path / "a")
    generate_world(SMALL).save(tmp_path / "b")

    for file in sorted((tmp_path / "a").iterdir()):
        assert file.read_bytes() == (tmp_path / "b" / file.name).read_bytes(), file.name


def test_different_seed_gives_different_data() -> None:
    other = generate_world(GeneratorConfig(seed=8, days=4, num_incidents=len(SCENARIOS)))

    assert other.tickets != generate_world(SMALL).tickets


# -------------------------------------------------------------- ground truth


def test_every_scenario_type_is_planted(world: World) -> None:
    planted = {truth.root_cause for truth in world.seeded_incidents}

    assert planted == {scenario.root_cause for scenario in SCENARIOS}


def test_ground_truth_points_to_real_records(world: World) -> None:
    incidents = {i.id: i for i in world.incidents}
    tickets = {t.id: t for t in world.tickets}
    deployments = {d.id: d for d in world.deployments}

    for truth in world.seeded_incidents:
        assert truth.root_cause_service in world.topology.services
        assert truth.started_at < truth.ended_at
        assert truth.incident_ids and truth.ticket_ids, truth.id
        for incident_id in truth.incident_ids:
            assert truth.started_at <= incidents[incident_id].opened_at <= truth.ended_at
        for ticket_id in truth.ticket_ids:
            assert truth.started_at <= tickets[ticket_id].created_at <= truth.ended_at
        for decoy_id in truth.decoy_deployment_ids:
            decoy = deployments[decoy_id]
            assert decoy.deployed_at < truth.started_at
            assert decoy.service != truth.root_cause_service


def test_bad_deployments_are_linked_to_their_trigger(world: World) -> None:
    deployments = {d.id: d for d in world.deployments}
    bad = [t for t in world.seeded_incidents if t.root_cause == RootCauseType.BAD_DEPLOYMENT]

    for truth in bad:
        trigger = deployments[truth.trigger_deployment_id]
        assert trigger.service == truth.root_cause_service
        assert trigger.deployed_at == truth.started_at
        assert trigger.rolled_back_at == truth.ended_at


def test_false_alarms_are_not_part_of_any_incident(world: World) -> None:
    seeded_alerts = {i for truth in world.seeded_incidents for i in truth.incident_ids}

    assert not seeded_alerts & set(world.false_alarm_incident_ids)


# -------------------------------------------------------------- signals


def test_alerts_saw_values_above_their_threshold(world: World) -> None:
    for incident in world.incidents:
        assert incident.observed_value >= incident.threshold, incident.id


def test_root_cause_leaves_a_fingerprint_in_its_own_metrics(world: World) -> None:
    """The broken service's metrics move during the incident: the RCA clue."""
    for truth in world.seeded_incidents:
        window = [
            i for i, ts in enumerate(world.timestamps) if truth.started_at <= ts < truth.ended_at
        ]
        biggest_change = 0.0
        for metric in (MetricName.ERROR_RATE, MetricName.LATENCY_P95_MS, MetricName.MEMORY_PCT):
            values = world.metrics.get((truth.root_cause_service, metric))
            if values is None:
                continue
            during = statistics.mean(values[i] for i in window)
            biggest_change = max(biggest_change, during / statistics.median(values))
        assert biggest_change >= 1.5, (truth.id, truth.root_cause_service)


def test_ids_are_assigned_in_time_order(world: World) -> None:
    opened = [i.opened_at for i in world.incidents]
    created = [t.created_at for t in world.tickets]

    assert opened == sorted(opened)
    assert created == sorted(created)
    assert world.incidents[0].id == "INC-0001"


def test_too_many_incidents_for_the_time_span_is_rejected() -> None:
    with pytest.raises(ValueError, match="Too many incidents"):
        generate_world(GeneratorConfig(days=1, num_incidents=10))


# -------------------------------------------------------------- saved files


def test_saved_files_load_back_into_models(world: World, tmp_path: Path) -> None:
    counts = world.save(tmp_path)

    for name, model in [
        ("deployments.jsonl", Deployment),
        ("incidents.jsonl", Incident),
        ("tickets.jsonl", Ticket),
        ("logs.jsonl", LogEvent),
    ]:
        lines = (tmp_path / name).read_text().splitlines()
        assert [model.model_validate_json(line) for line in lines], name

    with (tmp_path / "metrics.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == counts["metric points"]

    truth = json.loads((tmp_path / "ground_truth.json").read_text())
    assert [SeededIncident.model_validate(s) for s in truth["seeded_incidents"]]
