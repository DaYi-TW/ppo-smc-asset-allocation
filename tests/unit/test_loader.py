"""loader.py 細節行為：大小寫、custom data_dir、錯誤路徑。"""

from __future__ import annotations

import pandas as pd
import pytest

import data_ingestion

# ---------------------------------------------------------------------------
# Case-insensitive ticker
# ---------------------------------------------------------------------------


def test_lowercase_and_uppercase_ticker_return_equal_dataframes(tmp_data_dir):
    upper = data_ingestion.load_asset_snapshot("NVDA", data_dir=tmp_data_dir)
    lower = data_ingestion.load_asset_snapshot("nvda", data_dir=tmp_data_dir)
    pd.testing.assert_frame_equal(upper, lower)


def test_mixed_case_ticker(tmp_data_dir):
    df = data_ingestion.load_asset_snapshot("NvDa", data_dir=tmp_data_dir)
    assert len(df) == 10


def test_whitespace_in_ticker_is_stripped(tmp_data_dir):
    df = data_ingestion.load_asset_snapshot("  NVDA  ", data_dir=tmp_data_dir)
    assert len(df) == 10


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_empty_ticker_rejected(tmp_data_dir):
    with pytest.raises(ValueError, match="non-empty"):
        data_ingestion.load_asset_snapshot("", data_dir=tmp_data_dir)


def test_missing_snapshot_raises_filenotfounderror(tmp_data_dir):
    with pytest.raises(FileNotFoundError, match="no snapshot"):
        data_ingestion.load_asset_snapshot("AAPL", data_dir=tmp_data_dir)


def test_missing_data_dir_raises_filenotfounderror(tmp_path):
    with pytest.raises(FileNotFoundError, match="data_dir does not exist"):
        data_ingestion.load_asset_snapshot("NVDA", data_dir=tmp_path / "nonexistent")


def test_duplicate_snapshot_raises_valueerror(tmp_data_dir):
    src = next(tmp_data_dir.glob("nvda_daily_*.parquet"))
    duplicate = tmp_data_dir / "nvda_daily_20240102_20240115_v2.parquet"
    duplicate.write_bytes(src.read_bytes())
    with pytest.raises(ValueError, match="multiple snapshots"):
        data_ingestion.load_asset_snapshot("NVDA", data_dir=tmp_data_dir)


def test_load_metadata_missing_sidecar(tmp_data_dir):
    parquet = next(tmp_data_dir.glob("nvda_daily_*.parquet"))
    sidecar = parquet.with_suffix(parquet.suffix + ".meta.json")
    sidecar.unlink()
    with pytest.raises(FileNotFoundError, match="metadata sidecar"):
        data_ingestion.load_metadata(parquet)


def test_load_metadata_invalid_payload(tmp_data_dir):
    parquet = next(tmp_data_dir.glob("nvda_daily_*.parquet"))
    sidecar = parquet.with_suffix(parquet.suffix + ".meta.json")
    sidecar.write_text('{"schema_version": "9.9"}', encoding="utf-8")
    with pytest.raises(ValueError):
        data_ingestion.load_metadata(parquet)


# ---------------------------------------------------------------------------
# Rate loader
# ---------------------------------------------------------------------------


def test_rate_loader_default_series_id(tmp_data_dir):
    df = data_ingestion.load_rate_snapshot(data_dir=tmp_data_dir)
    assert "rate_pct" in df.columns
    assert len(df) == 10


def test_rate_loader_empty_series_id(tmp_data_dir):
    with pytest.raises(ValueError, match="non-empty"):
        data_ingestion.load_rate_snapshot("", data_dir=tmp_data_dir)
