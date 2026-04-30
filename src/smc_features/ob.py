"""Order Block (OB) 偵測與距離計算（research R3）。

定義
----

* **Bullish OB**：在 swing low 形成前，**最後一根紅 K 棒**（``close < open``），
  範圍 ``[low, high]``，midpoint = (low + high) / 2。
* **Bearish OB**：在 swing high 形成前，**最後一根綠 K 棒**（``close > open``），
  對稱定義。

失效（兩擇一）：

1. **時間失效**：``current_bar_index > formation_bar_index + ob_lookback_bars``。
2. **結構失效**：
   * Bullish OB：當前 K 棒 ``close < OB.bottom`` → invalidated
   * Bearish OB：當前 K 棒 ``close > OB.top`` → invalidated

特徵輸出
--------

* ``ob_touched[t]``：``[low[t], high[t]]`` 與 **最近有效 OB**
  （``formation_bar_index`` 最大者）的範圍 ``[bottom, top]`` 有交集。
* ``ob_distance_ratio[t]``：``(close[t] - OB.midpoint) / atr[t]``。
  若無有效 OB 或 ATR 未就緒（NaN），輸出 NaN。
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from smc_features.types import OrderBlock


def _find_last_opposite_candle(
    opens: NDArray[np.float64],
    closes: NDArray[np.float64],
    valid_mask: NDArray[np.bool_],
    end_index: int,
    direction: str,
) -> int | None:
    """在 ``[0, end_index]`` 內由 end_index 向前找最後一根反向 K 棒。

    direction == "bullish" → 找紅 K（close < open）。
    direction == "bearish" → 找綠 K（close > open）。
    回傳該根 K 棒位置；找不到則 None。
    """
    want_red = direction == "bullish"
    for j in range(end_index, -1, -1):
        if not valid_mask[j]:
            continue
        c, o = closes[j], opens[j]
        is_red = c < o
        is_green = c > o
        if want_red and is_red:
            return j
        if (not want_red) and is_green:
            return j
    return None


def detect_and_track_obs(
    opens: NDArray[np.float64],
    highs: NDArray[np.float64],
    lows: NDArray[np.float64],
    closes: NDArray[np.float64],
    timestamps: NDArray,
    valid_mask: NDArray[np.bool_],
    swing_high_marker: NDArray[np.bool_],
    swing_low_marker: NDArray[np.bool_],
    atr: NDArray[np.float64],
    ob_lookback_bars: int,
) -> tuple[list[OrderBlock], NDArray[np.bool_], NDArray[np.float64]]:
    """掃描全段資料，產生 OB 列表與每根 K 棒的觸碰旗標 / 距離比。

    Returns:
        ``(obs, ob_touched, ob_distance_ratio)`` —

        * ``obs``: 已偵測的 OB 列表（含已失效）。
        * ``ob_touched``: bool 陣列。
        * ``ob_distance_ratio``: float64 陣列；NaN 表「無有效 OB 或 ATR 未就緒」。
    """
    n = opens.shape[0]
    obs: list[OrderBlock] = []
    # active_indices：obs 中尚未失效者的索引（按 formation_bar_index 升序）。
    active_indices: list[int] = []
    touched = np.zeros(n, dtype=np.bool_)
    distance_ratio = np.full(n, np.nan, dtype=np.float64)

    def _invalidate(idx: int, ts) -> None:
        ob = obs[idx]
        obs[idx] = OrderBlock(
            formation_timestamp=ob.formation_timestamp,
            formation_bar_index=ob.formation_bar_index,
            direction=ob.direction,
            top=ob.top,
            bottom=ob.bottom,
            midpoint=ob.midpoint,
            expiry_bar_index=ob.expiry_bar_index,
            invalidated=True,
            invalidation_timestamp=ts,
        )

    for i in range(n):
        # (a) 在 swing 標記出現時，回望尋找新 OB。Swing 確認位置即為 OB 形成判定點。
        if valid_mask[i]:
            if swing_low_marker[i]:
                pos = _find_last_opposite_candle(opens, closes, valid_mask, i, "bullish")
                if pos is not None:
                    obs.append(
                        OrderBlock(
                            formation_timestamp=timestamps[pos],
                            formation_bar_index=pos,
                            direction="bullish",
                            top=float(highs[pos]),
                            bottom=float(lows[pos]),
                            midpoint=(float(highs[pos]) + float(lows[pos])) / 2.0,
                            expiry_bar_index=pos + ob_lookback_bars,
                            invalidated=False,
                            invalidation_timestamp=None,
                        )
                    )
                    active_indices.append(len(obs) - 1)
            if swing_high_marker[i]:
                pos = _find_last_opposite_candle(opens, closes, valid_mask, i, "bearish")
                if pos is not None:
                    obs.append(
                        OrderBlock(
                            formation_timestamp=timestamps[pos],
                            formation_bar_index=pos,
                            direction="bearish",
                            top=float(highs[pos]),
                            bottom=float(lows[pos]),
                            midpoint=(float(highs[pos]) + float(lows[pos])) / 2.0,
                            expiry_bar_index=pos + ob_lookback_bars,
                            invalidated=False,
                            invalidation_timestamp=None,
                        )
                    )
                    active_indices.append(len(obs) - 1)

        # (b) 用「今日 K 棒」更新失效狀態（時間 + 結構）。
        if active_indices:
            still_active: list[int] = []
            for idx in active_indices:
                ob = obs[idx]
                if ob.invalidated:
                    continue
                # 時間失效
                if i > ob.expiry_bar_index:
                    _invalidate(idx, timestamps[i])
                    continue
                # 結構失效（用今日收盤）
                if valid_mask[i]:
                    c = closes[i]
                    if ob.direction == "bullish" and c < ob.bottom:
                        _invalidate(idx, timestamps[i])
                        continue
                    if ob.direction == "bearish" and c > ob.top:
                        _invalidate(idx, timestamps[i])
                        continue
                still_active.append(idx)
            active_indices = still_active

        # (c) 計算當前 K 棒的觸碰與距離比。
        if valid_mask[i] and active_indices:
            latest = active_indices[-1]
            ob = obs[latest]
            # 觸碰：[low_i, high_i] ∩ [bottom, top] 非空
            if not (highs[i] < ob.bottom or lows[i] > ob.top):
                touched[i] = True
            atr_i = atr[i]
            if not np.isnan(atr_i) and atr_i > 0:
                distance_ratio[i] = (closes[i] - ob.midpoint) / atr_i

    return obs, touched, distance_ratio


__all__ = ["detect_and_track_obs"]
