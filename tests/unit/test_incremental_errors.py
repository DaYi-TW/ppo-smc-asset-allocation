"""T042 — incremental_compute 錯誤路徑（缺欄位、timestamp 倒退、空 state、非法型別）。"""

from __future__ import annotations

import pandas as pd
import pytest

from smc_features import (
    SMCEngineState,
    SMCFeatureParams,
    batch_compute,
    incremental_compute,
)


def _toy_df(n: int = 5) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "open": [10.0 + i for i in range(n)],
            "high": [11.0 + i for i in range(n)],
            "low": [9.0 + i for i in range(n)],
            "close": [10.5 + i for i in range(n)],
            "volume": [1_000_000 + i for i in range(n)],
            "quality_flag": ["ok"] * n,
        },
        index=idx,
    )


def test_missing_required_field_raises_keyerror() -> None:
    df = _toy_df()
    p = SMCFeatureParams()
    state = batch_compute(df, p).state
    bad = pd.Series(
        {"open": 1.0, "high": 1.5, "low": 0.5},  # 缺 close, volume
        name=df.index[-1] + pd.Timedelta(days=1),
    )
    with pytest.raises(KeyError, match="缺必要欄位"):
        incremental_compute(state, bad)


def test_timestamp_not_strictly_after_last_raises() -> None:
    df = _toy_df()
    p = SMCFeatureParams()
    state = batch_compute(df, p).state
    bar = pd.Series(
        {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100},
        name=df.index[-1],  # 與最後一根同 timestamp → 應拒絕
    )
    with pytest.raises(ValueError, match="必須嚴格晚於"):
        incremental_compute(state, bar)


def test_timestamp_earlier_than_last_raises() -> None:
    df = _toy_df()
    p = SMCFeatureParams()
    state = batch_compute(df, p).state
    bar = pd.Series(
        {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100},
        name=df.index[0],  # 早於 last
    )
    with pytest.raises(ValueError, match="必須嚴格晚於"):
        incremental_compute(state, bar)


def test_non_timestamp_name_raises() -> None:
    df = _toy_df()
    p = SMCFeatureParams()
    state = batch_compute(df, p).state
    bar = pd.Series(
        {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100},
        name="not-a-timestamp",
    )
    with pytest.raises(ValueError, match=r"pd\.Timestamp"):
        incremental_compute(state, bar)


def test_initial_state_without_window_raises() -> None:
    p = SMCFeatureParams()
    initial = SMCEngineState.initial(p)
    bar = pd.Series(
        {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100},
        name=pd.Timestamp("2024-01-01"),
    )
    with pytest.raises(ValueError, match="window_bars"):
        incremental_compute(initial, bar)
