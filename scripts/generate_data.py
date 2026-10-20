"""Generate the synthetic ShopFast dataset.

Usage (from the project folder):
    uv run python scripts/generate_data.py
    uv run python scripts/generate_data.py --days 14 --incidents 12 --seed 42

Files are written to data/synthetic/ (git-ignored; anyone can regenerate them
from the same seed).
"""

import argparse
import sys
import time
from pathlib import Path

from incident_intel.synthetic import GeneratorConfig, generate_world


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=42, help="random seed (default 42)")
    parser.add_argument("--days", type=int, default=14, help="days of history (default 14)")
    parser.add_argument("--incidents", type=int, default=12, help="incidents to plant (default 12)")
    parser.add_argument("--out", type=Path, default=Path("data/synthetic"), help="output folder")
    args = parser.parse_args()

    started = time.perf_counter()
    config = GeneratorConfig(seed=args.seed, days=args.days, num_incidents=args.incidents)
    try:
        world = generate_world(config)
    except ValueError as exc:
        print(f"[FAIL] {exc}")
        return 1
    counts = world.save(args.out)
    elapsed = time.perf_counter() - started

    print(f"Generated ShopFast data in {elapsed:.1f}s -> {args.out}/\n")
    for name, count in counts.items():
        print(f"  {name:<17} {count:>8,}")

    print("\nSeeded incidents (the answers, stored in ground_truth.json):")
    for truth in world.seeded_incidents:
        started_at = truth.started_at.strftime("%a %d %b %H:%M")
        print(
            f"  {truth.id}  {started_at}  {truth.priority}  "
            f"{truth.root_cause.value:<30} {truth.root_cause_service}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
