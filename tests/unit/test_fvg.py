"""T016 — FVG 偵測 / 填補追蹤 / 距離計算（research R2）。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from smc_features.fvg import detect_and_track_fvgs


def _series(highs, lows, closes):
    n = len(highs)
    timestamps = pd.date_range("2024-01-02", periods=n, freq="B").to_numpy()
    valid = np.ones(n, dtype=np.bool_)
    return (
        np.asarray(highs, dtype=np.float64),
        np.asarray(lows, dtype=np.float64),
        np.asarray(closes, dtype=np.float64),
        timestamps,
        valid,
    )


def test_bullish_fvg_detected():
    # bar[2].low = 105 > bar[0].high = 102 → bullish FVG，bottom=102, top=105
    highs = [102, 103, 110]
    lows = [98, 100, 105]
    closes = [100, 101, 107]
    h, l_, c, ts, v = _series(highs, lows, closes)
    fvgs, _dist = detect_and_track_fvgs(h, l_, c, ts, v, fvg_min_pct=0.0)
    assert len(fvgs) == 1
    assert fvgs[0].direction == "bullish"
    assert fvgs[0].bottom == 102.0
    assert fvgs[0].top == 105.0
    assert not fvgs[0].is_filled


def test_min_pct_filters_small_gap():
    # 缺口大小 / mid_close < threshold → 過濾
    highs = [100, 100.05, 100.5]
    lows = [99.9, 99.95, 100.1]
    closes = [99.95, 100.0, 100.3]
    h, l_, c, ts, v = _series(highs, lows, closes)
    fvgs, _dist = detect_and_track_fvgs(h, l_, c, ts, v, fvg_min_pct=0.01)
    assert len(fvgs) == 0


def test_bearish_fvg_filled_by_subsequent_high():
    # bar[2].high = 90 < bar[0].low = 95 → bearish FVG (top=95, bottom=90)
    # bar[5].high = 100 ≥ 95 → 填補
    highs = [100, 96, 90, 92, 96, 100]
    lows = [95, 92, 88, 90, 93, 97]
    closes = [98, 94, 89, 91, 94, 98]
    h, l_, c, ts, v = _series(highs, lows, closes)
    fvgs, _dist = detect_and_track_fvgs(h, l_, c, ts, v, fvg_min_pct=0.0)
    bear = [f for f in fvgs if f.direction == "bearish"]
    assert len(bear) == 1
    assert bear[0].is_filled
    assert bear[0].fill_timestamp is not None


def test_distance_pct_signed():
    highs = [102, 103, 110, 110, 109]
    lows = [98, 100, 105, 106, 105]
    closes = [100, 101, 107, 108, 107]
    h, l_, c, ts, v = _series(highs, lows, closes)
    _, dist = detect_and_track_fvgs(h, l_, c, ts, v, fvg_min_pct=0.0)
    # i=2 之後存在 bullish FVG（mid=103.5）；close=107 → (107-103.5)/107 ≈ +0.0327
    assert dist[2] > 0
    assert np.isnan(dist[0]) and np.isnan(dist[1])


def test_distance_nan_when_no_fvg():
    highs = [102, 102.1, 102.05]
    lows = [101, 101.5, 101.8]
    closes = [101.5, 101.8, 101.9]
    h, l_, c, ts, v = _series(highs, lows, closes)
    fvgs, dist = detect_and_track_fvgs(h, l_, c, ts, v, fvg_min_pct=0.001)
    assert len(fvgs) == 0
    assert np.isnan(dist).all()
