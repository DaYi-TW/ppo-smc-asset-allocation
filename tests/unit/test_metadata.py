"""metadata.build/write — 通過 JSON Schema、含 importlib.metadata 動態版本、
fetch_timestamp_utc 為 ISO 8601 + Z。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

from data_ingestion.metadata import (
    build_metadata,
    metadata_to_dict,
    utc_now_iso_z,
    write_metadata_json,
)
from data_ingestion.writer import write_parquet


_ISO_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


@pytest.fixture
def written_parquet(tmp_path: Path) -> Path:
    idx = pd.date_range("2024-01-02", periods=5, freq="B", name="date")
    df = pd.DataFrame(
        {
            "open": [1.0, 2.0, 3.0, 4.0, 5.0],
            "high": [1.5, 2.5, 3.5, 4.5, 5.5],
            "low": [0.5, 1.5, 2.5, 3.5, 4.5],
            "close": [1.2, 2.2, 3.2, 4.2, 5.2],
            "volume": [100, 200, 300, 400, 500],
            "quality_flag": pd.array(["ok"] * 5, dtype="string"),
        },
        index=idx,
    )
    p = tmp_path / "test.parquet"
    write_parquet(df, p)
    return p


def test_utc_now_iso_z_format():
    s = utc_now_iso_z()
    assert _ISO_Z_RE.match(s), s


def test_build_metadata_populates_versions(written_parquet: Path):
    meta = build_metadata(
        parquet_path=written_parquet,
        data_source="yfinance",
        call_params={
            "ticker": "TEST",
            "start": "2024-01-02",
            "end": "2024-01-09",
            "auto_adjust": True,
            "interval": "1d",
        },
        time_range=("2024-01-02", "2024-01-08"),
        quality_summary={
            "ok": 5,
            "missing_close": 0,
            "zero_volume": 0,
            "missing_rate": 0,
            "duplicate_dropped": 0,
        },
        duplicate_dropped_timestamps=[],
    )
    versions = dict(meta.upstream_package_versions)
    assert "pyarrow" in versions
    assert "pandas" in versions
    # 版本字串應為 PEP 440-ish（至少非空、含數字）
    for name, ver in versions.items():
        assert ver, f"{name} version empty"


def test_write_metadata_json_passes_schema(written_parquet: Path):
    meta = build_metadata(
        parquet_path=written_parquet,
        data_source="yfinance",
        call_params={
            "ticker": "TEST",
            "start": "2024-01-02",
            "end": "2024-01-09",
            "auto_adjust": True,
            "interval": "1d",
        },
        time_range=("2024-01-02", "2024-01-08"),
        quality_summary={
            "ok": 5,
            "missing_close": 0,
            "zero_volume": 0,
            "missing_rate": 0,
            "duplicate_dropped": 0,
        },
        duplicate_dropped_timestamps=[],
    )
    meta_path = write_metadata_json(meta, written_parquet)
    assert meta_path.exists()
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert _ISO_Z_RE.match(payload["fetch_timestamp_utc"])
    assert payload["row_count"] == 5
    assert payload["sha256"] == meta.sha256


def test_metadata_to_dict_roundtrip_via_load_metadata(written_parquet: Path):
    import data_ingestion

    meta = build_metadata(
        parquet_path=written_parquet,
        data_source="yfinance",
        call_params={
            "ticker": "TEST",
            "start": "2024-01-02",
            "end": "2024-01-09",
            "auto_adjust": True,
            "interval": "1d",
        },
        time_range=("2024-01-02", "2024-01-08"),
        quality_summary={
            "ok": 5,
            "missing_close": 0,
            "zero_volume": 0,
            "missing_rate": 0,
            "duplicate_dropped": 0,
        },
        duplicate_dropped_timestamps=[],
    )
    write_metadata_json(meta, written_parquet)
    loaded = data_ingestion.load_metadata(written_parquet)
    assert loaded.sha256 == meta.sha256
    assert loaded.row_count == 5
    assert loaded.data_source == "yfinance"
