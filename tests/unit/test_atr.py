"""T018 — ATR Wilder smoothing（research R3）。"""

from __future__ import annotations

import numpy as np

from smc_features.atr import compute_atr


def test_atr_initial_window_nan():
    n = 20
    rng = np.arange(1, n + 1, dtype=np.float64)
    highs = rng + 1.0
    lows = rng - 1.0
    closes = rng
    valid = np.ones(n, dtype=np.bool_)
    atr = compute_atr(highs, lows, closes, window=14, valid_mask=valid)
    # 前 13 個位置為 NaN（seed 在第 14 個 valid TR 完成）
    assert np.isnan(atr[:13]).all()
    # 第 14 起為非 NaN
    assert not np.isnan(atr[13])
    assert not np.isnan(atr[-1])


def test_atr_constant_tr_yields_constant_atr():
    n = 30
    closes = np.full(n, 100.0)
    highs = closes + 1.0
    lows = closes - 1.0
    valid = np.ones(n, dtype=np.bool_)
    atr = compute_atr(highs, lows, closes, window=14, valid_mask=valid)
    # TR 全部 = 2（第 0 根 = high - low；之後 = max(2, |1|, |1|) = 2）
    # SMA seed = 2；之後 EMA(2 + (2-2)/14) = 2 始終
    assert np.isclose(atr[13], 2.0, atol=1e-12)
    assert np.isclose(atr[-1], 2.0, atol=1e-12)


def test_atr_invalid_window_raises():
    import pytest

    valid = np.array([True])
    with pytest.raises(ValueError):
        compute_atr(
            np.array([1.0]),
            np.array([0.0]),
            np.array([1.0]),
            window=0,
            valid_mask=valid,
        )


def test_atr_skips_invalid_rows():
    n = 30
    closes = np.full(n, 100.0)
    highs = closes + 1.0
    lows = closes - 1.0
    valid = np.ones(n, dtype=np.bool_)
    valid[5] = False  # 瑕疵列；TR 跳過
    atr = compute_atr(highs, lows, closes, window=14, valid_mask=valid)
    assert np.isnan(atr[5])
    # seed 仍能於後續累積完成
    assert not np.isnan(atr[-1])


def test_atr_empty_input():
    atr = compute_atr(
        np.array([], dtype=np.float64),
        np.array([], dtype=np.float64),
        np.array([], dtype=np.float64),
        window=14,
        valid_mask=np.array([], dtype=np.bool_),
    )
    assert atr.shape == (0,)
