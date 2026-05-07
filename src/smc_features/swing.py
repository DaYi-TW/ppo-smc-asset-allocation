"""Swing high / swing low 偵測（research R1）。

定義
----

對長度 ``L = swing_length`` 與位置 ``i``：

* ``i`` 為 swing high  ⇔  對所有 ``j ∈ [i-L, i+L] \\ {i}``：``high[i] > high[j]``
* ``i`` 為 swing low   ⇔  對所有 ``j ∈ [i-L, i+L] \\ {i}``：``low[i]  < low[j]``

* 嚴格不等（平手不採計）— 避免雙頂/雙底邊界爭議。
* swing point 為 **delayed signal**：第 ``i`` 根 K 棒最早於第 ``i+L`` 根時才
  能確認；故批次計算的最後 ``L`` 根可能尚未確認 swing。
* ``valid_mask`` 為 ``False`` 的位置（瑕疵列；spec FR-015）：該位置永不為 swing，
  且其 high/low 不參與其他位置的鄰居比較（從窗口計算中跳過）。
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def detect_swings(
    highs: NDArray[np.float64],
    lows: NDArray[np.float64],
    swing_length: int,
    valid_mask: NDArray[np.bool_],
) -> tuple[NDArray[np.bool_], NDArray[np.bool_]]:
    """偵測 swing high / low 標記陣列。

    Args:
        highs: 高價序列。
        lows: 低價序列。
        swing_length: 左右視窗大小 ``L >= 1``。
        valid_mask: 同長 bool 陣列；瑕疵列從計算中跳過。

    Returns:
        ``(swing_high_marker, swing_low_marker)`` 兩個與輸入同長的 bool 陣列。

    Raises:
        ValueError: ``swing_length < 1`` 或輸入長度不一致。
    """
    if swing_length < 1:
        raise ValueError(f"swing_length 必須 >= 1，收到 {swing_length}")
    n = highs.shape[0]
    if not (lows.shape[0] == n == valid_mask.shape[0]):
        raise ValueError("highs / lows / valid_mask 長度必須一致")

    sh = np.zeros(n, dtype=np.bool_)
    sl = np.zeros(n, dtype=np.bool_)
    if n == 0:
        return sh, sl

    width = swing_length
    for i in range(width, n - width):
        if not valid_mask[i]:
            continue
        center_high = highs[i]
        center_low = lows[i]
        is_high = True
        is_low = True
        for j in range(i - width, i + width + 1):
            if j == i or not valid_mask[j]:
                continue
            if not (center_high > highs[j]):
                is_high = False
            if not (center_low < lows[j]):
                is_low = False
            if not is_high and not is_low:
                break
        if is_high:
            sh[i] = True
        if is_low:
            sl[i] = True
    return sh, sl


__all__ = ["detect_swings"]
