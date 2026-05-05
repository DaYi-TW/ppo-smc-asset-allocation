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


# ---------------------------------------------------------------------------
# v2 ATR filter（spec 008 FR-011 / scenario US3-1 / US3-2 / US3-3）
# ---------------------------------------------------------------------------


def _gap_series_height_one():
    """構造一個 height = 1.0 的 bullish FVG：bar[0].high=100、bar[2].low=101，
    mid_close=closes[1]=100.5（pct=1/100.5 ≈ 0.00995，遠超 fvg_min_pct=0.001）。
    """
    highs = [100.0, 100.5, 102.0]
    lows = [99.0, 99.5, 101.0]
    closes = [99.5, 100.5, 101.5]
    return _series(highs, lows, closes)


def test_atr_filter_below_ratio_excluded():
    """T031 — ATR=5、FVG height=1.0（ratio 0.2 < 0.25）→ 不保留。

    對應 spec FR-011、scenario US3-1。
    """
    h, l_, c, ts, v = _gap_series_height_one()
    atr = np.full(3, 5.0, dtype=np.float64)
    fvgs, _ = detect_and_track_fvgs(
        h, l_, c, ts, v, fvg_min_pct=0.0,
        atr=atr, fvg_min_atr_ratio=0.25,
    )
    assert len(fvgs) == 0, f"ratio 0.2 < 0.25 應過濾，實際留下 {len(fvgs)}"


def test_atr_filter_at_boundary_kept():
    """T032 — ATR=4、FVG height=1.0（ratio 等於 0.25）→ 保留（>= 邊界）。

    對應 spec scenario US3-2、Edge Case「ATR ratio 邊界」。
    """
    h, l_, c, ts, v = _gap_series_height_one()
    atr = np.full(3, 4.0, dtype=np.float64)
    fvgs, _ = detect_and_track_fvgs(
        h, l_, c, ts, v, fvg_min_pct=0.0,
        atr=atr, fvg_min_atr_ratio=0.25,
    )
    assert len(fvgs) == 1


def test_atr_filter_above_ratio_kept():
    """T033 — ATR=2、FVG height=1.0（ratio 0.5）→ 保留。

    對應 spec FR-011。
    """
    h, l_, c, ts, v = _gap_series_height_one()
    atr = np.full(3, 2.0, dtype=np.float64)
    fvgs, _ = detect_and_track_fvgs(
        h, l_, c, ts, v, fvg_min_pct=0.0,
        atr=atr, fvg_min_atr_ratio=0.25,
    )
    assert len(fvgs) == 1


def test_atr_nan_falls_back_to_pct():
    """T034 — warmup 期 ATR=NaN，FVG 過濾退化為 fvg_min_pct。

    對應 spec FR-011、Edge Case「ATR 未就緒退化」。
    """
    h, l_, c, ts, v = _gap_series_height_one()
    atr = np.full(3, np.nan, dtype=np.float64)
    # height/mid_close ≈ 0.00995 — 大於預設 fvg_min_pct=0.001 → 保留
    fvgs, _ = detect_and_track_fvgs(
        h, l_, c, ts, v, fvg_min_pct=0.001,
        atr=atr, fvg_min_atr_ratio=0.25,
    )
    assert len(fvgs) == 1, "ATR=NaN 時應退化到 fvg_min_pct 檢查"

    # 反例：用很高的 fvg_min_pct → 即便 ATR=NaN 也不應保留
    fvgs2, _ = detect_and_track_fvgs(
        h, l_, c, ts, v, fvg_min_pct=0.5,
        atr=atr, fvg_min_atr_ratio=0.25,
    )
    assert len(fvgs2) == 0


def test_ratio_zero_disables_filter():
    """T035 — fvg_min_atr_ratio=0.0 與 v1 行為等價（僅檢 fvg_min_pct）。

    對應 spec scenario US3-3。
    """
    h, l_, c, ts, v = _gap_series_height_one()
    atr = np.full(3, 1000.0, dtype=np.float64)  # 任何 ratio 都會 < 0.25
    fvgs, _ = detect_and_track_fvgs(
        h, l_, c, ts, v, fvg_min_pct=0.0,
        atr=atr, fvg_min_atr_ratio=0.0,
    )
    assert len(fvgs) == 1, "ratio=0.0 應禁用 ATR 過濾"
