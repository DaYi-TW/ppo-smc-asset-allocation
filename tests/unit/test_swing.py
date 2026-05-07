"""T013 — swing high / swing low 偵測（research R1）。"""

from __future__ import annotations

import numpy as np

from smc_features.swing import detect_swings


def _v(*xs: float) -> np.ndarray:
    return np.asarray(xs, dtype=np.float64)


def test_swing_high_positive():
    # 中央位置 (i=2) high 嚴格大於左右各 2 根
    highs = _v(1, 2, 5, 2, 1)
    lows = _v(0, 0, 0, 0, 0)
    valid = np.ones(5, dtype=np.bool_)
    sh, sl = detect_swings(highs, lows, swing_length=2, valid_mask=valid)
    assert sh[2]
    assert not sh[0] and not sh[1] and not sh[3] and not sh[4]
    assert not sl.any()


def test_swing_low_positive():
    highs = _v(0, 0, 0, 0, 0)
    lows = _v(2, 1, -1, 1, 2)
    valid = np.ones(5, dtype=np.bool_)
    sh, sl = detect_swings(highs, lows, swing_length=2, valid_mask=valid)
    assert sl[2]
    assert not sh.any()


def test_swing_strict_inequality_rejects_tie():
    # i=2 與 i=4 同高 → 不嚴格大於 → 不採計
    highs = _v(1, 2, 5, 2, 5)
    lows = _v(0, 0, 0, 0, 0)
    valid = np.ones(5, dtype=np.bool_)
    sh, _ = detect_swings(highs, lows, swing_length=2, valid_mask=valid)
    assert not sh.any()


def test_swing_skips_invalid_positions():
    # 第 1 根 valid=False；應視為「不存在」，不阻止其他位置成為 swing。
    highs = _v(1, 99, 5, 2, 1)  # i=1 是瑕疵列（valid=False），其 high=99 不應該影響 i=2
    lows = _v(0, 0, 0, 0, 0)
    valid = np.array([True, False, True, True, True])
    sh, _ = detect_swings(highs, lows, swing_length=2, valid_mask=valid)
    assert sh[2]


def test_swing_edge_no_room():
    # 前 L 根與後 L 根永不為 swing
    highs = _v(10, 1, 1, 1, 10)
    lows = _v(0, 0, 0, 0, 0)
    valid = np.ones(5, dtype=np.bool_)
    sh, _ = detect_swings(highs, lows, swing_length=2, valid_mask=valid)
    assert not sh.any()
