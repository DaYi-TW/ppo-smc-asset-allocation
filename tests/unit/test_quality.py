"""quality_flag 判定 + DataFrame 級處理。

對齊 data-model.md §4 優先序：missing_close > zero_volume > ok。
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from data_ingestion import quality

# ---------------------------------------------------------------------------
# Row-level classifiers
# ---------------------------------------------------------------------------


def test_classify_asset_row_ok():
    assert (
        quality.classify_asset_row(open_=1.0, high=1.5, low=0.5, close=1.2, volume=1000)
        == "ok"
    )


def test_classify_asset_row_missing_close_takes_priority_over_zero_volume():
    assert (
        quality.classify_asset_row(
            open_=1.0, high=1.5, low=0.5, close=math.nan, volume=0
        )
        == "missing_close"
    )


def test_classify_asset_row_zero_volume():
    assert (
        quality.classify_asset_row(open_=1.0, high=1.5, low=0.5, close=1.2, volume=0)
        == "zero_volume"
    )


def test_classify_asset_row_any_nan_field_flags_missing_close():
    for col in ("open_", "high", "low", "close"):
        kwargs = dict(open_=1.0, high=1.5, low=0.5, close=1.2, volume=1000)
        kwargs[col] = math.nan
        assert quality.classify_asset_row(**kwargs) == "missing_close"


def test_classify_rate_row_ok_and_missing():
    assert quality.classify_rate_row(rate_pct=5.25) == "ok"
    assert quality.classify_rate_row(rate_pct=math.nan) == "missing_rate"


# ---------------------------------------------------------------------------
# DataFrame-level pipeline
# ---------------------------------------------------------------------------


def test_apply_asset_quality_flags_no_duplicates():
    idx = pd.date_range("2024-01-02", periods=3, freq="B", name="date")
    df = pd.DataFrame(
        {
            "open": [10.0, 11.0, 12.0],
            "high": [10.5, 11.5, 12.5],
            "low": [9.5, 10.5, 11.5],
            "close": [10.2, 11.2, 12.2],
            "volume": [1000, 0, 2000],
        },
        index=idx,
    )
    clean, dup = quality.apply_asset_quality_flags(df)
    assert dup == []
    assert list(clean["quality_flag"]) == ["ok", "zero_volume", "ok"]
    assert clean.index.name == "date"
    assert list(clean.columns) == [
        "open", "high", "low", "close", "volume", "quality_flag"
    ]


def test_apply_asset_quality_flags_drops_duplicates_keeping_first():
    idx = pd.DatetimeIndex(
        ["2024-01-02", "2024-01-03", "2024-01-03", "2024-01-04"], name="date"
    )
    df = pd.DataFrame(
        {
            "open": [1.0, 2.0, 99.0, 4.0],
            "high": [1.0, 2.0, 99.0, 4.0],
            "low": [1.0, 2.0, 99.0, 4.0],
            "close": [1.0, 2.0, 99.0, 4.0],
            "volume": [10, 20, 30, 40],
        },
        index=idx,
    )
    clean, dup = quality.apply_asset_quality_flags(df)
    assert dup == ["2024-01-03"]
    assert list(clean["close"]) == [1.0, 2.0, 4.0]


def test_apply_asset_quality_flags_missing_columns_raises():
    df = pd.DataFrame({"open": [1.0]}, index=pd.DatetimeIndex(["2024-01-02"], name="date"))
    with pytest.raises(ValueError, match="missing columns"):
        quality.apply_asset_quality_flags(df)


def test_apply_rate_quality_flags_basic():
    idx = pd.date_range("2024-01-02", periods=3, freq="B", name="date")
    s = pd.Series([5.25, np.nan, 5.30], index=idx, name="rate_pct")
    clean, dup = quality.apply_rate_quality_flags(s)
    assert dup == []
    assert list(clean["quality_flag"]) == ["ok", "missing_rate", "ok"]
    assert list(clean.columns) == ["rate_pct", "quality_flag"]


def test_summarize_quality_flags_zero_fills_all_keys():
    flags = pd.Series(["ok", "ok", "zero_volume"], dtype="string")
    summary = quality.summarize_quality_flags(flags, duplicate_dropped=2)
    assert summary == {
        "ok": 2,
        "missing_close": 0,
        "zero_volume": 1,
        "missing_rate": 0,
        "duplicate_dropped": 2,
    }
