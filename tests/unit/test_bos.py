"""T014 — BOS 判定（research R1）。"""

from __future__ import annotations

import numpy as np

from smc_features.structure import compute_bos_choch


def test_no_bos_in_neutral_state():
    # 無 swing 出現 → trend 永 neutral → bos 全 0
    n = 5
    closes = np.array([100, 101, 102, 103, 104], dtype=np.float64)
    highs = closes + 0.5
    lows = closes - 0.5
    sh = np.zeros(n, dtype=np.bool_)
    sl = np.zeros(n, dtype=np.bool_)
    valid = np.ones(n, dtype=np.bool_)
    bos, choch = compute_bos_choch(closes, highs, lows, sh, sl, valid)
    assert (bos == 0).all()
    assert (choch == 0).all()


def test_bos_up_in_bullish():
    # 構造：先讓 trend 升 bullish（HH+HL），然後一根 close 突破 last_swing_high。
    # 詳細序列見 test_invariants 的 CHoCh 構造模板。此處僅檢查 bos != 0 確實出現。
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
    # 突破 last_swing_high = 115：
    closes[35] = 120.0
    highs[35] = 121.0
    lows[35] = 119.0
    sh = np.zeros(n, dtype=np.bool_)
    sl = np.zeros(n, dtype=np.bool_)
    sh[12] = True
    sh[25] = True
    sl[5] = True
    sl[18] = True
    valid = np.ones(n, dtype=np.bool_)
    bos, choch = compute_bos_choch(closes, highs, lows, sh, sl, valid)
    # 至少在 i=35 觸發 bos=+1（trend 已是 bullish 且 close > last_high=115）
    assert bos[35] == 1
    # 同根不應觸發 CHoCh
    assert choch[35] == 0
