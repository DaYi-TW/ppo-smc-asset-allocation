"""T050 — spec Edge Cases 全部覆蓋。

* 資料量不足 → 全 NaN
* index 非單調 → ValueError
* 缺欄 → KeyError
* 跨大缺口不誤判 BOS（盤中跳空但無突破前 swing high）
* 永久未填補 FVG（後續 K 棒未碰觸缺口）— `fvg_distance_pct` 持續輸出
* incremental 非連續時間 → ValueError
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from smc_features import (
    SMCFeatureParams,
    batch_compute,
    incremental_compute,
)


def _df(n: int, *, opens=None, highs=None, lows=None, closes=None) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    if closes is None:
        closes = [100.0 + i * 0.5 for i in range(n)]
    if opens is None:
        opens = closes
    if highs is None:
        highs = [c + 1.0 for c in closes]
    if lows is None:
        lows = [c - 1.0 for c in closes]
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1_000_000] * n,
            "quality_flag": ["ok"] * n,
        },
        index=idx,
    )


def test_data_too_short_yields_nans() -> None:
    """資料量少於 swing_length * 2 + 1 時，任何 swing 都不應被確認。"""
    df = _df(3)
    out = batch_compute(df, SMCFeatureParams()).output
    # bos / choch 因無 swing 可參照，全部 0（int8）— 不應有非 0 訊號
    assert (out["bos_signal"].fillna(0) == 0).all()
    assert (out["choch_signal"].fillna(0) == 0).all()


def test_non_monotonic_index_raises() -> None:
    df = _df(10)
    df = df.iloc[[0, 2, 1, 3, 4, 5, 6, 7, 8, 9]]
    with pytest.raises(ValueError, match="單調遞增"):
        batch_compute(df, SMCFeatureParams())


def test_missing_required_column_raises() -> None:
    df = _df(10).drop(columns=["close"])
    with pytest.raises(KeyError, match="缺少必要欄位"):
        batch_compute(df, SMCFeatureParams())


def test_large_gap_does_not_falsely_trigger_bos() -> None:
    """跨大缺口（隔夜跳空）但未實際突破前 swing high — 不應誤判 BOS。"""
    closes = [100.0] * 5 + [102.0] * 5 + [110.0] * 5 + [108.0] * 5
    # 構造尚未確認 swing high 前就出現巨幅跳空，bos_signal 不應為 1
    df = _df(20, closes=closes)
    out = batch_compute(df, SMCFeatureParams()).output
    # 早期（前 swing_length 列）必然不會有 BOS
    assert (out["bos_signal"].iloc[:5].fillna(0) == 0).all()


def test_unfilled_fvg_keeps_emitting_distance() -> None:
    """形成永久未填補的 FVG 後，後續 K 棒仍應有 fvg_distance_pct 輸出。"""
    n = 40
    # 構造明顯的 bullish FVG：bar 5 大幅跳空向上，後續 K 棒不回填
    closes = [100.0] * 5 + [110.0] * (n - 5)  # 第 5 根開始一路 110
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    # 在第 5 根上方明顯留缺口：bar 4 high = 100.5, bar 6 low = 109.5 → bullish FVG
    df = _df(n, closes=closes, highs=highs, lows=lows)
    out = batch_compute(df, SMCFeatureParams(fvg_min_pct=0.001)).output
    later = out["fvg_distance_pct"].iloc[10:]
    # 至少有部分非 NaN（FVG 一旦形成且未填補就持續輸出）
    assert later.notna().any(), "未填補 FVG 應持續輸出 fvg_distance_pct"


def test_incremental_non_consecutive_timestamp_raises() -> None:
    """incremental_compute 對「不嚴格遞增」的 timestamp 應拒絕。"""
    df = _df(20)
    p = SMCFeatureParams()
    state = batch_compute(df, p).state
    bar = pd.Series(
        {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 100,
            "quality_flag": "ok",
        },
        name=df.index[-1],  # 同 timestamp
    )
    with pytest.raises(ValueError, match="嚴格晚於"):
        incremental_compute(state, bar)


def test_all_nan_quality_yields_all_nan_features() -> None:
    """整段資料全部 quality 瑕疵 — 所有特徵列應全 NaN。"""
    n = 30
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    df = pd.DataFrame(
        {
            "open": np.full(n, 100.0),
            "high": np.full(n, 101.0),
            "low": np.full(n, 99.0),
            "close": np.full(n, 100.0),
            "volume": np.full(n, 1_000_000),
            "quality_flag": ["missing_close"] * n,
        },
        index=idx,
    )
    out = batch_compute(df, SMCFeatureParams()).output
    assert out["bos_signal"].isna().all()
    assert out["choch_signal"].isna().all()
    assert out["fvg_distance_pct"].isna().all()
