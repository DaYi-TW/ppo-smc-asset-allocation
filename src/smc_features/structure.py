"""BOS / CHoCh 市場結構判定（research R1）。

規則
----

維護下列狀態：

* ``last_swing_high`` / ``last_swing_low``：最近一個 **已確認** 的 swing 點。
* ``prev_swing_high`` / ``prev_swing_low``：前一個確認的 swing 點。
* ``trend_state ∈ {"bullish", "bearish", "neutral"}``：基於 swing 序列遞增/遞減判斷。

判定邏輯（基於收盤價，避免影線假突破）：

1. **CHoCh（性格轉變，趨勢反轉）**：
   * trend == bullish 且 ``close[t] < last_swing_low.price`` → ``choch = -1``，
     翻轉為 bearish。
   * trend == bearish 且 ``close[t] > last_swing_high.price`` → ``choch = +1``，
     翻轉為 bullish。
2. **BOS（結構斷裂，趨勢延續）**：
   * trend == bullish 且 ``close[t] > last_swing_high.price`` → ``bos = +1``。
   * trend == bearish 且 ``close[t] < last_swing_low.price`` → ``bos = -1``。
3. **衝突優先**（spec FR-019）：CHoCh 優先於 BOS。同根 K 棒同時符合 BOS 與 CHoCh
   條件時 ``bos = 0`` 且 ``choch ≠ 0``。

當第 ``i`` 根 K 棒被偵測為 swing point（``swing_high_marker[i]=True``）時，更新
``last_swing_high`` 並依 swing 序列檢查 ``trend_state`` 是否需要更新（HH/HL → bullish；
LH/LL → bearish）。

瑕疵列（``valid_mask[t]=False``）：``bos[t] = choch[t] = 0`` 且不參與狀態更新（spec FR-015）。
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def compute_bos_choch(
    closes: NDArray[np.float64],
    highs: NDArray[np.float64],
    lows: NDArray[np.float64],
    swing_high_marker: NDArray[np.bool_],
    swing_low_marker: NDArray[np.bool_],
    valid_mask: NDArray[np.bool_],
) -> tuple[NDArray[np.int8], NDArray[np.int8]]:
    """計算每根 K 棒的 ``bos_signal`` 與 ``choch_signal``。

    Returns:
        ``(bos_signal, choch_signal)``，皆為 int8 陣列，值域 {-1, 0, 1}。
    """
    n = closes.shape[0]
    bos = np.zeros(n, dtype=np.int8)
    choch = np.zeros(n, dtype=np.int8)
    if n == 0:
        return bos, choch

    # 維護最近 / 上一個 swing 的價位（None 表尚未出現）。
    last_high: float | None = None
    prev_high: float | None = None
    last_low: float | None = None
    prev_low: float | None = None
    trend = "neutral"  # bullish / bearish / neutral

    for i in range(n):
        if not valid_mask[i]:
            continue
        c = closes[i]

        # (a) 先依當前 trend 與 last swing 計算 BOS / CHoCh。
        ch_signal = 0
        bs_signal = 0
        if trend == "bullish":
            if last_low is not None and c < last_low:
                ch_signal = -1  # CHoCh 反向
            elif last_high is not None and c > last_high:
                bs_signal = 1
        elif trend == "bearish":
            if last_high is not None and c > last_high:
                ch_signal = 1
            elif last_low is not None and c < last_low:
                bs_signal = -1
        else:
            # neutral：CHoCh 不適用；以 swing 突破啟動 trend，但暫不發 BOS（無前一波段參考）
            pass

        # CHoCh 優先（規則 3）— 上面 if/elif 已自然滿足互斥；雙保險：
        if ch_signal != 0:
            bs_signal = 0

        bos[i] = bs_signal
        choch[i] = ch_signal

        # (b) 依 CHoCh 翻轉 trend
        if ch_signal == -1:
            trend = "bearish"
        elif ch_signal == 1:
            trend = "bullish"

        # (c) 若當前 K 棒 *本身* 確認為 swing point，更新 last/prev。
        if swing_high_marker[i]:
            prev_high = last_high
            last_high = float(highs[i])
        if swing_low_marker[i]:
            prev_low = last_low
            last_low = float(lows[i])

        # (d) 任一 swing 更新後，重新評估 trend（neutral 時可升 bullish/bearish）。
        if (
            (swing_high_marker[i] or swing_low_marker[i])
            and trend == "neutral"
            and prev_high is not None
            and last_high is not None
            and prev_low is not None
            and last_low is not None
        ):
            if last_high > prev_high and last_low > prev_low:
                trend = "bullish"
            elif last_high < prev_high and last_low < prev_low:
                trend = "bearish"

    # highs / lows 在當前實作中不直接使用（保留簽章對齊 contract / 未來需要影線輔助時擴充）。
    _ = (highs, lows)
    return bos, choch


__all__ = ["compute_bos_choch"]
