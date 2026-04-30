"""T017 — Order Block 偵測 / 失效（research R3）。

最小覆蓋：bullish OB（swing low 前最後紅 K 棒）、時間失效、結構失效。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from smc_features.ob import detect_and_track_obs


def _arrays(opens, highs, lows, closes):
    n = len(opens)
    return (
        np.asarray(opens, dtype=np.float64),
        np.asarray(highs, dtype=np.float64),
        np.asarray(lows, dtype=np.float64),
        np.asarray(closes, dtype=np.float64),
        pd.date_range("2024-01-02", periods=n, freq="B").to_numpy(),
        np.ones(n, dtype=np.bool_),
    )


def test_bullish_ob_detected_before_swing_low():
    # 構造：
    # i=0: 紅 K 棒（close < open）→ 候選 bullish OB
    # i=1..4: 任意
    # i=2: swing_low_marker = True
    opens = [102, 100, 95, 100, 105]
    closes = [100, 101, 96, 102, 106]  # i=0 紅 (100 < 102), 其他綠
    highs = [103, 102, 97, 103, 107]
    lows = [99, 99, 94, 99, 104]
    o, h, l_, c, ts, v = _arrays(opens, highs, lows, closes)
    swing_high_marker = np.zeros(5, dtype=np.bool_)
    swing_low_marker = np.array([False, False, True, False, False])
    atr = np.full(5, 1.0, dtype=np.float64)

    obs, _touched, _dist = detect_and_track_obs(
        o, h, l_, c, ts, v, swing_high_marker, swing_low_marker, atr, ob_lookback_bars=10
    )
    assert len(obs) == 1
    assert obs[0].direction == "bullish"
    assert obs[0].formation_bar_index == 0  # 最後一根紅 K 棒
    assert obs[0].top == 103.0
    assert obs[0].bottom == 99.0


def test_ob_time_expiry():
    # OB 形成於 i=0，lookback=2，故 i=3 應失效
    opens = [102, 100, 95, 100, 105, 110]
    closes = [100, 101, 96, 102, 106, 111]
    highs = [103, 102, 97, 103, 107, 112]
    lows = [99, 99, 94, 99, 104, 109]
    o, h, l_, c, ts, v = _arrays(opens, highs, lows, closes)
    swing_high_marker = np.zeros(6, dtype=np.bool_)
    swing_low_marker = np.array([False, False, True, False, False, False])
    atr = np.full(6, 1.0, dtype=np.float64)

    obs, touched, _dist = detect_and_track_obs(
        o, h, l_, c, ts, v, swing_high_marker, swing_low_marker, atr, ob_lookback_bars=2
    )
    # OB invalidated 應在 i=3（formation 0 + lookback 2 = expiry 2；i=3 > 2 失效）
    assert obs[0].invalidated
    # i >= 3 後 ob_touched 應為 False（已失效）
    assert not touched[5]


def test_ob_structural_invalidation():
    # bullish OB bottom=99；後續 close < 99 應結構失效
    opens = [102, 100, 95, 100, 95, 90]
    closes = [100, 101, 96, 102, 96, 89]  # i=5 close=89 < bottom 99
    highs = [103, 102, 97, 103, 97, 92]
    lows = [99, 99, 94, 99, 95, 88]
    o, h, l_, c, ts, v = _arrays(opens, highs, lows, closes)
    swing_high_marker = np.zeros(6, dtype=np.bool_)
    swing_low_marker = np.array([False, False, True, False, False, False])
    atr = np.full(6, 1.0, dtype=np.float64)

    obs, _, _ = detect_and_track_obs(
        o, h, l_, c, ts, v, swing_high_marker, swing_low_marker, atr, ob_lookback_bars=10
    )
    assert obs[0].invalidated
    assert obs[0].invalidation_timestamp is not None


def test_ob_distance_nan_without_atr():
    opens = [102, 100, 95, 100, 105]
    closes = [100, 101, 96, 102, 106]
    highs = [103, 102, 97, 103, 107]
    lows = [99, 99, 94, 99, 104]
    o, h, l_, c, ts, v = _arrays(opens, highs, lows, closes)
    swing_low_marker = np.array([False, False, True, False, False])
    swing_high_marker = np.zeros(5, dtype=np.bool_)
    atr = np.full(5, np.nan, dtype=np.float64)

    _, _, dist = detect_and_track_obs(
        o, h, l_, c, ts, v, swing_high_marker, swing_low_marker, atr, ob_lookback_bars=10
    )
    assert np.isnan(dist).all()
