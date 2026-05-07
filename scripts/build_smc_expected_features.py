"""Generate ``tests/fixtures/expected_smc_features.parquet`` (T056).

Run inside the dev container so the lock file's pandas / pyarrow patch versions
are honored — the resulting Parquet is what every other platform compares
against in ``tests/integration/test_smc_cross_platform.py`` (spec SC-002).

Usage::

    docker compose run --rm dev python scripts/build_smc_expected_features.py

Then ``git add tests/fixtures/expected_smc_features.parquet`` and commit.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from smc_features import SMCFeatureParams, batch_compute

REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "nvda_2024H1.parquet"
EXPECTED_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "expected_smc_features.parquet"


def main() -> None:
    if not INPUT_FIXTURE.exists():
        raise SystemExit(
            f"input fixture missing: {INPUT_FIXTURE}\n"
            "Run scripts/build_smc_fixtures.py first."
        )
    df = pd.read_parquet(INPUT_FIXTURE)
    out = batch_compute(df, SMCFeatureParams(), include_aux=True).output
    out.to_parquet(EXPECTED_FIXTURE, compression="snappy", index=True)
    print(f"Wrote {EXPECTED_FIXTURE} ({EXPECTED_FIXTURE.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
