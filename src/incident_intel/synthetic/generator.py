"""Put it all together: build a synthetic ShopFast world with seeded incidents."""

import random
from datetime import timedelta

from incident_intel.synthetic.background import (
    add_false_alarms,
    add_routine_deployments,
    add_routine_tickets,
)
from incident_intel.synthetic.scenarios import SCENARIOS, ScenarioContext
from incident_intel.synthetic.signals import apply_effects, baseline_metrics, normal_logs
from incident_intel.synthetic.topology import SHOPFAST_SERVICES, Topology
from incident_intel.synthetic.world import GeneratorConfig, World


def generate_world(config: GeneratorConfig | None = None) -> World:
    """Generate everything. Same config (including seed) -> identical output.

    One `random.Random(seed)` object drives every random choice. Never use the
    global `random` functions here: any other code touching them would change
    the results, and reproducibility is what makes evaluation trustworthy.
    """
    config = config or GeneratorConfig()
    rng = random.Random(config.seed)
    step = timedelta(minutes=config.bucket_minutes)
    buckets = int(timedelta(days=config.days) / step)
    world = World(
        config=config,
        topology=Topology(SHOPFAST_SERVICES),
        timestamps=[config.start + i * step for i in range(buckets)],
    )

    # 1. Everyday background activity.
    add_routine_deployments(world, rng)
    add_routine_tickets(world, rng)
    add_false_alarms(world, rng)

    # 2. Plant the incidents we know the answers to.
    _plant_incidents(world, rng)

    # 3. Turn everything into metrics and logs.
    world.metrics = baseline_metrics(world.topology, world.timestamps, rng)
    apply_effects(world.metrics, world.timestamps, world.effects, rng)
    world.logs.extend(normal_logs(world.topology, world.timestamps, rng))

    world.finalize()
    return world


def _plant_incidents(world: World, rng: random.Random) -> None:
    """Spread incidents over the timeline so they never overlap.

    The timeline is cut into equal slots, one incident per slot, starting at a
    random time inside it. Scenario types rotate so each appears roughly equally.
    """
    config = world.config
    if config.num_incidents < 1:
        return
    kinds = [SCENARIOS[i % len(SCENARIOS)] for i in range(config.num_incidents)]
    rng.shuffle(kinds)

    slot = (config.end - config.start) / config.num_incidents
    if slot < timedelta(hours=7):
        raise ValueError("Too many incidents for the time span: allow at least 7 hours each")

    for i, scenario_class in enumerate(kinds):
        scenario = scenario_class()
        slot_start = config.start + i * slot
        earliest = slot_start + timedelta(hours=2)
        latest = slot_start + slot - timedelta(hours=4)
        offset_minutes = int((latest - earliest).total_seconds() // 60 * rng.random())
        start = earliest + timedelta(minutes=offset_minutes)
        root = rng.choice(scenario.candidate_services)
        ctx = ScenarioContext(
            world=world,
            rng=rng,
            root_service=root,
            start=start,
            end=start + timedelta(minutes=rng.randint(*scenario.duration_minutes)),
            priority=scenario.priority_for(root),
        )
        scenario.inject(ctx)
        world.seeded_incidents.append(ctx.finish(scenario.root_cause, scenario.expected_runbook))
