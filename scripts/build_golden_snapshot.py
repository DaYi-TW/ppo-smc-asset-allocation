"""Build a tiny deterministic golden snapshot for cross-platform tests (T049).

Outputs `tests/fixtures/golden_snapshots/golden_daily_20240102_20240131.parquet`
+ matching `.meta.json`. Re-running this script must produce byte-identical
output (no system time, no random state). The metadata's
``fetch_timestamp_utc`` is hard-coded for that reason.

Run inside the dev container:

    docker compose run --rm dev python scripts/build_golden_snapshot.py

Should be re-run only when the snapshot schema changes intentionally.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from data_ingestion import (
    ColumnSchema,
    IndexSchema,
    QualitySummary,
    SnapshotMetadata,
    TimeRange,
)
from data_ingestion.hashing import sha256_of_file
from data_ingestion.metadata import (
    metadata_to_dict,
    write_metadata_json,
)
from data_ingestion.quality import apply_asset_quality_flags
from data_ingestion.writer import write_parquet

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = REPO_ROOT / "tests" / "fixtures" / "golden_snapshots"

# Small deterministic OHLCV — 22 business days in Jan 2024
_START = "2024-01-02"
_END = "2024-01-31"
_FETCH_TS = "2024-02-01T00:00:00Z"  # frozen for byte-identical output


def _build_frame() -> pd.DataFrame:
    idx = pd.date_range(_START, _END, freq="B", name="date")
    n = len(idx)
    rs = np.random.default_rng(seed=42)
    close = 100.0 + np.cumsum(rs.normal(0, 0.5, size=n))
    return pd.DataFrame(
        {
            "open": close - 0.3,
            "high": close + 0.7,
            "low": close - 0.8,
            "close": close,
            "volume": rs.integers(1_000_000, 5_000_000, size=n).astype("int64"),
        },
        index=idx,
    )


def main() -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    parquet_path = GOLDEN_DIR / "golden_daily_20240102_20240131.parquet"

    raw = _build_frame()
    clean, dup_ts = apply_asset_quality_flags(raw)
    write_parquet(clean, parquet_path)

    summary = {
        "ok": int((clean["quality_flag"] == "ok").sum()),
        "missing_close": int((clean["quality_flag"] == "missing_close").sum()),
        "zero_volume": int((clean["quality_flag"] == "zero_volume").sum()),
        "missing_rate": 0,
        "duplicate_dropped": len(dup_ts),
    }

    # Bypass build_metadata to keep fetch_timestamp + upstream versions
    # frozen — the fixture must remain byte-identical even when the dev
    # container's installed pandas/pyarrow patch versions roll forward.
    import pyarrow.parquet as pq
    from datetime import datetime

    table_meta = pq.read_metadata(parquet_path)
    column_schema = (
        ColumnSchema(name="open", dtype="float64"),
        ColumnSchema(name="high", dtype="float64"),
        ColumnSchema(name="low", dtype="float64"),
        ColumnSchema(name="close", dtype="float64"),
        ColumnSchema(name="volume", dtype="int64"),
        ColumnSchema(name="quality_flag", dtype="string"),
    )
    meta = SnapshotMetadata(
        schema_version="1.0",
        fetch_timestamp_utc=datetime.strptime(_FETCH_TS, "%Y-%m-%dT%H:%M:%SZ"),
        data_source="yfinance",
        data_source_call_params={
            "ticker": "GOLDEN",
            "start": _START,
            "end": _END,
            "auto_adjust": True,
            "interval": "1d",
        },
        upstream_package_versions={
            "pandas": "2.2.3",
            "pyarrow": "15.0.2",
            "yfinance": "0.2.40",
            "fredapi": "0.5.2",
        },
        sha256=sha256_of_file(parquet_path),
        row_count=int(table_meta.num_rows),
        column_schema=column_schema,
        index_schema=IndexSchema(name="date", dtype="datetime64[ns]", tz=None),
        time_range=TimeRange(start=_START, end=_END),
        quality_summary=QualitySummary(**summary),
        duplicate_dropped_timestamps=tuple(dup_ts),
    )
    write_metadata_json(meta, parquet_path)

    sha_short = meta.sha256[:16]
    print(
        f"wrote {parquet_path.name} ({meta.row_count} rows, sha256={sha_short}…)\n"
        f"meta: {metadata_to_dict(meta)['column_schema']}"
    )


if __name__ == "__main__":
    main()
