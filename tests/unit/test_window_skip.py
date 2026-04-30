"""T049 — swing.detect_swings 與 atr.compute_atr 在 valid_mask 含 False 時的行為。"""

from __future__ import annotations

import numpy as np

from smc_features.atr import compute_atr
from smc_features.swing import detect_swings


def test_swing_skips_invalid_rows() -> None:
    """中央 K 棒被標 invalid 時，不應被認定為 swing high/low。"""
    n = 11
    highs = np.array([10.0, 10.5, 11.0, 11.5, 12.0, 13.0, 12.0, 11.5, 11.0, 10.5, 10.0])
    lows = highs - 1.0
    valid_mask = np.ones(n, dtype=np.bool_)
    valid_mask[5] = False  # 中央高點被標為瑕疵列

    swing_highs, _ = detect_swings(highs, lows, swing_length=2, valid_mask=valid_mask)
    assert not swing_highs[5], "瑕疵列不應被偵測為 swing high"


def test_atr_skips_invalid_rows_outputs_nan() -> None:
    """瑕疵列位置的 ATR 應為 NaN，下游視窗不應把瑕疵列 TR 納入。"""
    n = 30
    rng = np.random.default_rng(42)
    closes = 100.0 + np.cumsum(rng.normal(0, 1, n))
    highs = closes + 1.0
    lows = closes - 1.0
    valid_mask = np.ones(n, dtype=np.bool_)
    valid_mask[10] = False
    valid_mask[20] = False

    atr = compute_atr(highs, lows, closes, window=14, valid_mask=valid_mask)
    # 瑕疵位置應為 NaN
    assert np.isnan(atr[10])
    assert np.isnan(atr[20])
    # 跳過後的有效位置仍能形成 ATR（不應因瑕疵列而全 NaN）
    assert not np.isnan(atr[-1])


def test_swing_with_all_invalid_returns_no_markers() -> None:
    n = 10
    highs = np.linspace(10.0, 20.0, n)
    lows = highs - 1.0
    valid_mask = np.zeros(n, dtype=np.bool_)
    swing_highs, swing_lows = detect_swings(
        highs, lows, swing_length=2, valid_mask=valid_mask
    )
    assert not swing_highs.any()
    assert not swing_lows.any()


def test_atr_with_all_invalid_returns_all_nan() -> None:
    n = 30
    closes = np.full(n, 100.0)
    highs = closes + 1.0
    lows = closes - 1.0
    valid_mask = np.zeros(n, dtype=np.bool_)
    atr = compute_atr(highs, lows, closes, window=14, valid_mask=valid_mask)
    assert np.isnan(atr).all()
