"""Load the synthetic dataset into the database.

Usage (from the project folder, after `scripts/generate_data.py`):
    uv run python scripts/load_data.py

Reads data/synthetic/ and REPLACES everything in the database configured by
DATABASE_URL (default: the SQLite file data/incident_intel.db).
"""

import argparse
import sys
import time
from pathlib import Path

from incident_intel.config import get_settings
from incident_intel.storage.db import make_engine
from incident_intel.storage.loader import load_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=Path("data/synthetic"), help="input folder")
    args = parser.parse_args()

    database_url = get_settings().database_url
    started = time.perf_counter()
    try:
        counts = load_dataset(make_engine(database_url), args.data)
    except FileNotFoundError as exc:
        print(f"[FAIL] {exc}")
        print("Run this first:  uv run python scripts/generate_data.py")
        return 1

    print(f"Loaded {args.data}/ into {database_url} in {time.perf_counter() - started:.1f}s\n")
    for table, count in counts.items():
        print(f"  {table:<12} {count:>8,}")
    print("\nStart the API with:  uv run uvicorn incident_intel.api.main:app --reload")
    return 0


if __name__ == "__main__":
    sys.exit(main())
