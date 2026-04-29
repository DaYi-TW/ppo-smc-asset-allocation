"""Schema 相容性：載入後 DataFrame 直接符合 001 spec 的 batch_compute 輸入。

001 spec data-model.md §1 規定 OHLCV 輸入欄位 dtype；本測試確保 002 載入器輸出
的 DataFrame 不需任何轉換即可餵入 001。Rate 同理對應 003 PPO env 的 risk-free
rate 輸入。
"""

from __future__ import annotations

import pandas as pd

import data_ingestion


ASSET_DTYPE_CONTRACT = {
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "int64",
    "quality_flag": "string",
}

RATE_DTYPE_CONTRACT = {
    "rate_pct": "float64",
    "quality_flag": "string",
}


def test_asset_dataframe_dtypes_match_contract(tmp_data_dir):
    df = data_ingestion.load_asset_snapshot("NVDA", data_dir=tmp_data_dir)
    for col, expected in ASSET_DTYPE_CONTRACT.items():
        assert col in df.columns, f"missing column {col!r}"
        assert str(df[col].dtype) == expected, (
            f"column {col!r} dtype {df[col].dtype} != contract {expected}"
        )


def test_asset_index_is_utc_naive_datetimeindex(tmp_data_dir):
    df = data_ingestion.load_asset_snapshot("NVDA", data_dir=tmp_data_dir)
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.name == "date"
    assert df.index.tz is None
    assert df.index.is_monotonic_increasing
    assert df.index.is_unique


def test_rate_dataframe_dtypes_match_contract(tmp_data_dir):
    df = data_ingestion.load_rate_snapshot("DTB3", data_dir=tmp_data_dir)
    for col, expected in RATE_DTYPE_CONTRACT.items():
        assert col in df.columns
        assert str(df[col].dtype) == expected


def test_rate_index_is_utc_naive_datetimeindex(tmp_data_dir):
    df = data_ingestion.load_rate_snapshot("DTB3", data_dir=tmp_data_dir)
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.name == "date"
    assert df.index.tz is None


def test_load_metadata_roundtrip(tmp_data_dir):
    parquet = next(tmp_data_dir.glob("nvda_daily_*.parquet"))
    md = data_ingestion.load_metadata(parquet)
    assert md.schema_version == "1.0"
    assert md.data_source == "yfinance"
    assert md.row_count == 10
    assert md.quality_summary.ok == 10
    assert all(c.dtype in {"float64", "int64", "string", "bool"} for c in md.column_schema)
