"""ATR（Average True Range）計算 — Wilder 平滑法（research R3）。

公式（Wilder, 1978）::

    TR_i  = max( high_i - low_i,
                 |high_i - close_{i-1}|,
                 |low_i - close_{i-1}| )

    ATR_i = ATR_{i-1} + (TR_i - ATR_{i-1}) / window      (i >= window)
          = SMA(TR_1..TR_window)                         (i == window-1; seed)
          = NaN                                          (i < window-1)

* 第 0 根 K 棒沒有前一根 close → TR_0 = high_0 - low_0。
* ``valid_mask`` 為 ``False`` 的列：TR 視為 NaN，不納入 seed average，亦不
  推進 Wilder 遞迴；輸出該列為 NaN（spec FR-014/FR-015 — 瑕疵列不污染下游）。
* 跨平台 byte-identical：純 IEEE 754 float64 + 順序明確的 Python 迴圈，避免
  SIMD reduce 順序差異（research R5）。
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def compute_atr(
    highs: NDArray[np.float64],
    lows: NDArray[np.float64],
    closes: NDArray[np.float64],
    window: int,
    valid_mask: NDArray[np.bool_],
) -> NDArray[np.float64]:
    """以 Wilder smoothing 計算 ATR 序列。

    Args:
        highs: 高價序列（float64，可含 NaN）。
        lows: 低價序列。
        closes: 收盤序列。
        window: 平滑視窗（research R3 預設 14）。
        valid_mask: 與 highs 同長 bool 陣列；False 列不納入 TR 計算。

    Returns:
        與輸入同長的 float64 陣列；前 ``window-1`` 個有效 TR 之前的位置為 NaN。

    Raises:
        ValueError: ``window < 1`` 或輸入長度不一致。
    """
    if window < 1:
        raise ValueError(f"window 必須 >= 1，收到 {window}")
    n = highs.shape[0]
    if not (lows.shape[0] == n == closes.shape[0] == valid_mask.shape[0]):
        raise ValueError("highs / lows / closes / valid_mask 長度必須一致")

    atr = np.full(n, np.nan, dtype=np.float64)
    if n == 0:
        return atr

    # True Range（含 valid_mask 篩選）
    tr = np.full(n, np.nan, dtype=np.float64)
    for i in range(n):
        if not valid_mask[i]:
            continue
        h, low_i = highs[i], lows[i]
        if i == 0 or not valid_mask[i - 1]:
            tr_i = h - low_i
        else:
            prev_close = closes[i - 1]
            tr_i = max(h - low_i, abs(h - prev_close), abs(low_i - prev_close))
        tr[i] = tr_i

    # Wilder seed = SMA(前 `window` 個有效 TR)，之後 EMA 遞迴
    valid_tr_count = 0
    seed_sum = 0.0
    seed_complete = False
    last_atr = np.nan
    for i in range(n):
        if np.isnan(tr[i]):
            continue
        if not seed_complete:
            seed_sum += tr[i]
            valid_tr_count += 1
            if valid_tr_count == window:
                last_atr = seed_sum / window
                atr[i] = last_atr
                seed_complete = True
        else:
            last_atr = last_atr + (tr[i] - last_atr) / window
            atr[i] = last_atr
    return atr


__all__ = ["compute_atr"]
