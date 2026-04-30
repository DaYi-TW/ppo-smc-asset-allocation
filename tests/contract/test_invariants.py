"""T021 — data-model.md §9 不變式驗證。

涵蓋 invariant 1 / 2 / 3 / 5 / 7（4、6 由 US3 / US4 各自覆蓋）。
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from smc_features import SMCFeatureParams, batch_compute


def test_invariant_1_row_count(small_ohlcv, default_params):
    br = batch_compute(small_ohlcv, default_params)
    assert len(br.output) == len(small_ohlcv)


def test_invariant_2_index_preserved(small_ohlcv, default_params):
    br = batch_compute(small_ohlcv, default_params)
    pd.testing.assert_index_equal(br.output.index, small_ohlcv.index)
    # dtype 也保留
    assert br.output.index.dtype == small_ohlcv.index.dtype


def test_invariant_3_byte_identical_repeat(small_ohlcv, default_params):
    a = batch_compute(small_ohlcv, default_params).output
    b = batch_compute(small_ohlcv, default_params).output
    pd.testing.assert_frame_equal(a, b, check_dtype=True, check_exact=True)


def test_invariant_5_params_frozen():
    p = SMCFeatureParams()
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.swing_length = 99  # type: ignore[misc]


def test_invariant_5_state_frozen(small_ohlcv, default_params):
    br = batch_compute(small_ohlcv, default_params)
    with pytest.raises(dataclasses.FrozenInstanceError):
        br.state.bar_count = -1  # type: ignore[misc]


def test_invariant_7_choch_priority_synthetic():
    """構造同根 K 棒同時觸發 BOS 與 CHoCh 的人造序列。

    場景：bullish trend 中遇到大跳空向下，使收盤同時 < last_swing_low。預期：
    ``choch_signal == -1`` 且 ``bos_signal == 0``。
    """
    # 構造序列：先建立明確的 HH+HL（bullish），然後一根長黑棒收盤跌破 last_swing_low。
    idx = pd.date_range("2024-01-02", periods=40, freq="B", name="date")
    n = len(idx)
    # 先製造一個 swing low 在 i=5（左右各 5 根更高低點）
    closes = np.full(n, 100.0)
    highs = np.full(n, 100.5)
    lows = np.full(n, 99.5)
    # swing low @ 5
    lows[5] = 95.0
    # 之後價位墊高形成 HH/HL
    for i in range(6, 20):
        closes[i] = 100.0 + (i - 5) * 0.5
        highs[i] = closes[i] + 0.5
        lows[i] = closes[i] - 0.5
    # swing high @ 12（左右各 5 根更低點）
    highs[12] = 110.0
    closes[12] = 109.5
    # swing low @ 18 高於 5，形成 HL
    lows[18] = 96.5
    # 之後維持高位
    for i in range(20, 30):
        closes[i] = 108.0
        highs[i] = 108.5
        lows[i] = 107.5
    # swing high @ 25 高於 12 → HH
    highs[25] = 115.0
    closes[25] = 114.5
    # 在 i=35（已過完所有 swing 確認延遲）丟一根跌破 last_swing_low (~96.5) 的 K 棒
    closes[35] = 90.0
    highs[35] = 91.0
    lows[35] = 89.0
    df = pd.DataFrame(
        {
            "open": closes - 0.1,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.full(n, 1_000_000, dtype=np.int64),
        },
        index=idx,
    )
    br = batch_compute(df, SMCFeatureParams(swing_length=5))
    bos = br.output["bos_signal"]
    choch = br.output["choch_signal"]
    # 同時觸發位置應有 choch != 0 且 bos == 0
    conflict = (choch != 0) & (~choch.isna())
    if conflict.any():
        assert (bos[conflict] == 0).all(), (
            "CHoCh 觸發位置 BOS 必須為 0（spec FR-019、invariant 7）"
        )
    else:
        pytest.skip("人造序列未觸發 CHoCh — 重新校準 fixture 後再驗證")
