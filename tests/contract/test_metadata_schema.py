"""Contract: snapshot-metadata.schema.json validates good payloads and rejects bad ones.

Tests the JSON Schema directly via jsonschema. The actual write path (Phase 3)
will produce conformant payloads; the read/verify path (Phase 4) consumes them.
This contract test pins the schema's behaviour so neither path drifts.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "specs" / "002-data-ingestion" / "contracts" / "snapshot-metadata.schema.json"
)


@pytest.fixture(scope="module")
def schema() -> dict:
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def valid_yfinance_metadata() -> dict:
    return {
        "schema_version": "1.0",
        "fetch_timestamp_utc": "2026-04-29T03:14:15Z",
        "data_source": "yfinance",
        "data_source_call_params": {
            "ticker": "NVDA",
            "start": "2018-01-01",
            "end": "2026-04-30",
            "auto_adjust": True,
            "interval": "1d",
        },
        "upstream_package_versions": {
            "yfinance": "0.2.43",
            "pyarrow": "15.0.2",
            "pandas": "2.2.1",
        },
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "row_count": 2087,
        "column_schema": [
            {"name": "open", "dtype": "float64"},
            {"name": "high", "dtype": "float64"},
            {"name": "low", "dtype": "float64"},
            {"name": "close", "dtype": "float64"},
            {"name": "volume", "dtype": "int64"},
            {"name": "quality_flag", "dtype": "string"},
        ],
        "index_schema": {"name": "date", "dtype": "datetime64[ns]", "tz": None},
        "time_range": {"start": "2018-01-02", "end": "2026-04-29"},
        "quality_summary": {
            "ok": 2080,
            "missing_close": 0,
            "zero_volume": 5,
            "missing_rate": 0,
            "duplicate_dropped": 2,
        },
        "duplicate_dropped_timestamps": ["2020-03-23", "2022-06-14"],
    }


@pytest.fixture
def valid_fred_metadata(valid_yfinance_metadata: dict) -> dict:
    md = copy.deepcopy(valid_yfinance_metadata)
    md["data_source"] = "fred"
    md["data_source_call_params"] = {
        "series_id": "DTB3",
        "observation_start": "2018-01-01",
        "observation_end": "2026-04-29",
    }
    md["column_schema"] = [
        {"name": "rate_pct", "dtype": "float64"},
        {"name": "quality_flag", "dtype": "string"},
    ]
    md["quality_summary"] = {
        "ok": 2160,
        "missing_close": 0,
        "zero_volume": 0,
        "missing_rate": 10,
        "duplicate_dropped": 0,
    }
    md["row_count"] = 2170
    md["duplicate_dropped_timestamps"] = []
    return md


def test_valid_yfinance_metadata_passes(schema: dict, valid_yfinance_metadata: dict) -> None:
    jsonschema.validate(valid_yfinance_metadata, schema)


def test_valid_fred_metadata_passes(schema: dict, valid_fred_metadata: dict) -> None:
    jsonschema.validate(valid_fred_metadata, schema)


def test_wrong_schema_version_rejected(schema: dict, valid_yfinance_metadata: dict) -> None:
    valid_yfinance_metadata["schema_version"] = "2.0"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(valid_yfinance_metadata, schema)


def test_missing_z_suffix_rejected(schema: dict, valid_yfinance_metadata: dict) -> None:
    valid_yfinance_metadata["fetch_timestamp_utc"] = "2026-04-29T03:14:15"  # no Z
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(valid_yfinance_metadata, schema)


def test_uppercase_sha256_rejected(schema: dict, valid_yfinance_metadata: dict) -> None:
    valid_yfinance_metadata["sha256"] = (
        "E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855"
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(valid_yfinance_metadata, schema)


def test_unknown_data_source_rejected(schema: dict, valid_yfinance_metadata: dict) -> None:
    valid_yfinance_metadata["data_source"] = "alpha_vantage"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(valid_yfinance_metadata, schema)


def test_extra_top_level_property_rejected(schema: dict, valid_yfinance_metadata: dict) -> None:
    valid_yfinance_metadata["unexpected_field"] = "x"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(valid_yfinance_metadata, schema)


def test_missing_required_field_rejected(schema: dict, valid_yfinance_metadata: dict) -> None:
    del valid_yfinance_metadata["sha256"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(valid_yfinance_metadata, schema)


def test_quality_summary_extra_key_rejected(schema: dict, valid_yfinance_metadata: dict) -> None:
    valid_yfinance_metadata["quality_summary"]["bogus_flag"] = 1
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(valid_yfinance_metadata, schema)
