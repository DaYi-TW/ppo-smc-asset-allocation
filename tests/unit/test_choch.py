"""T015 — CHoCh 判定 + CHoCh 優先於 BOS（research R1 / spec FR-019）。"""

from __future__ import annotations

import numpy as np

from smc_features.structure import compute_bos_choch


def _setup_bullish_then_drop(drop_close: float, breakout_close: float):
    n = 40
    closes = np.full(n, 100.0)
    highs = np.full(n, 100.5)
    lows = np.full(n, 99.5)
    lows[5] = 95.0
    for i in range(6, 20):
        closes[i] = 100.0 + (i - 5) * 0.5
        highs[i] = closes[i] + 0.5
        lows[i] = closes[i] - 0.5
    highs[12] = 110.0
    closes[12] = 109.5
    lows[18] = 96.5
    for i in range(20, 30):
        closes[i] = 108.0
        highs[i] = 108.5
        lows[i] = 107.5
    highs[25] = 115.0
    closes[25] = 114.5
    closes[35] = drop_close
    highs[35] = max(highs[34], breakout_close)
    lows[35] = drop_close - 1.0
    sh = np.zeros(n, dtype=np.bool_)
    sl = np.zeros(n, dtype=np.bool_)
    sh[12] = True
    sh[25] = True
    sl[5] = True
    sl[18] = True
    valid = np.ones(n, dtype=np.bool_)
    return closes, highs, lows, sh, sl, valid


def test_choch_down_in_bullish():
    closes, highs, lows, sh, sl, valid = _setup_bullish_then_drop(
        drop_close=90.0, breakout_close=92.0
    )
    bos, choch = compute_bos_choch(closes, highs, lows, sh, sl, valid)
    assert choch[35] == -1
    assert bos[35] == 0


def test_choch_priority_over_bos():
    """同 K 棒同時滿足 BOS（close > last_swing_high）與 CHoCh 條件不會發生在
    bullish 趨勢，因兩者方向互斥；但驗證實作上 ``choch != 0`` 時 ``bos == 0``
    的硬性互斥（spec FR-019 / invariant 7）。
    """
    closes, highs, lows, sh, sl, valid = _setup_bullish_then_drop(
        drop_close=90.0, breakout_close=92.0
    )
    bos, choch = compute_bos_choch(closes, highs, lows, sh, sl, valid)
    conflict = (choch != 0)
    if conflict.any():
        assert (bos[conflict] == 0).all()


def test_no_choch_in_neutral():
    n = 5
    closes = np.array([100.0, 101.0, 102.0, 103.0, 104.0])
    highs = closes + 0.5
    lows = closes - 0.5
    sh = np.zeros(n, dtype=np.bool_)
    sl = np.zeros(n, dtype=np.bool_)
    valid = np.ones(n, dtype=np.bool_)
    _, choch = compute_bos_choch(closes, highs, lows, sh, sl, valid)
    assert (choch == 0).all()
