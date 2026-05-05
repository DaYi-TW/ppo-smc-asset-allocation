"""Order Block (OB) 偵測與生命週期追蹤（v2 — feature 008）。

定義
----

* **Bullish OB**：在 BOS_BULL / CHOCH_BULL break 之前，**最後一根紅 K 棒**
  （``close < open``），範圍 ``[low, high]``，midpoint = (low + high) / 2。
* **Bearish OB**：在 BOS_BEAR / CHOCH_BEAR break 之前，**最後一根綠 K 棒**
  （``close > open``），對稱定義。

失效（兩擇一）：

1. **時間失效**：``current_bar_index > formation_bar_index + ob_lookback_bars``。
2. **結構失效**：
   * Bullish OB：當前 K 棒 ``close < OB.bottom`` → invalidated
   * Bearish OB：當前 K 棒 ``close > OB.top`` → invalidated

特徵輸出（``track_ob_lifecycle``）
--------------------------------

* ``ob_touched[t]``：``[low[t], high[t]]`` 與 **最近有效 OB**
  （``formation_bar_index`` 最大者）的範圍 ``[bottom, top]`` 有交集。
* ``ob_distance_ratio[t]``：``(close[t] - OB.midpoint) / atr[t]``。
  若無有效 OB 或 ATR 未就緒（NaN），輸出 NaN。

v2 入口
-------

* :func:`build_obs_from_breaks` — 由 ``StructureBreak`` 列表反推 OB（每筆 break
  最多產一個 OB；找不到反向 K 則跳過）。產出的 OB 帶 ``source_break_index`` /
  ``source_break_kind``，可追溯（spec FR-008/FR-009、contract Invariant B-3）。
* :func:`track_ob_lifecycle` — 對 OB 列表跑時間 + 結構失效迴圈，回傳
  ``ob_touched`` / ``ob_distance_ratio``（spec FR-010）。

v1 入口（deprecated，由 batch.py Phase 6 切換完成後可移除）
---------------------------------------------------------

* :func:`detect_and_track_obs` — swing-driven，舊行為保留以利分階段 commit。
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from smc_features.types import OrderBlock, StructureBreak


def _find_last_opposite_candle(
    opens: NDArray[np.float64],
    closes: NDArray[np.float64],
    valid_mask: NDArray[np.bool_],
    end_index: int,
    direction: str,
    earliest_index: int = 0,
) -> int | None:
    """在 ``[earliest_index, end_index]`` 內由 end_index 向前找最後一根反向 K 棒。

    direction == "bullish" → 找紅 K（close < open）。
    direction == "bearish" → 找綠 K（close > open）。
    回傳該根 K 棒位置；找不到則 None。
    """
    want_red = direction == "bullish"
    for j in range(end_index, earliest_index - 1, -1):
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


# ---------------------------------------------------------------------------
# v2 break-driven OB
# ---------------------------------------------------------------------------


def build_obs_from_breaks(
    breaks: tuple[StructureBreak, ...],
    opens: NDArray[np.float64],
    highs: NDArray[np.float64],
    lows: NDArray[np.float64],
    closes: NDArray[np.float64],
    timestamps: NDArray,
    valid_mask: NDArray[np.bool_],
    ob_lookback_bars: int,
) -> list[OrderBlock]:
    """每筆 ``StructureBreak`` 反推一個 OB（往回找最後一根反向 K 棒）。

    ``BOS_BULL`` / ``CHOCH_BULL`` → bullish OB；對稱 bearish。
    若 lookback 範圍 ``[break_idx - ob_lookback_bars, break_idx - 1]``
    內找不到反向 K，跳過此 break（spec Edge Case）。

    Args:
        breaks: ``StructureBreak`` 元組（``compute_bos_choch`` 第 3 個回傳值）。
        opens / highs / lows / closes: float64 OHLC 陣列。
        timestamps: 對應 K 棒時間戳；可為 ``np.datetime64[*]`` 或 ``pd.Timestamp``。
        valid_mask: bool 陣列；False 處跳過。
        ob_lookback_bars: 同時作為「往回找反向 K」的視窗大小 + 「OB 失效視窗」。

    Returns:
        ``OrderBlock`` 列表；每個 OB 的 ``source_break_index`` 對應 ``breaks``
        中的位置、``source_break_kind`` 對齊該 break 的 ``kind``。
    """
    obs: list[OrderBlock] = []
    for src_idx, br in enumerate(breaks):
        bull = br.kind.endswith("_BULL")
        direction = "bullish" if bull else "bearish"
        end_index = br.bar_index - 1
        if end_index < 0:
            continue
        earliest = max(0, br.bar_index - ob_lookback_bars)
        pos = _find_last_opposite_candle(
            opens, closes, valid_mask, end_index, direction, earliest_index=earliest
        )
        if pos is None:
            continue
        obs.append(
            OrderBlock(
                formation_timestamp=timestamps[pos],
                formation_bar_index=pos,
                direction=direction,  # type: ignore[arg-type]
                top=float(highs[pos]),
                bottom=float(lows[pos]),
                midpoint=(float(highs[pos]) + float(lows[pos])) / 2.0,
                expiry_bar_index=pos + ob_lookback_bars,
                invalidated=False,
                invalidation_timestamp=None,
                source_break_index=src_idx,
                source_break_kind=br.kind,
            )
        )
    return obs


def track_ob_lifecycle(
    obs: list[OrderBlock],
    opens: NDArray[np.float64],
    highs: NDArray[np.float64],
    lows: NDArray[np.float64],
    closes: NDArray[np.float64],
    timestamps: NDArray,
    valid_mask: NDArray[np.bool_],
    atr: NDArray[np.float64],
) -> tuple[list[OrderBlock], NDArray[np.bool_], NDArray[np.float64]]:
    """掃 OHLC 跑 OB 失效迴圈，輸出 ``ob_touched`` 與 ``ob_distance_ratio``。

    輸入 ``obs`` 的順序 *不需* 排序；函式內部按 ``formation_bar_index`` 排序
    後跑時間 + 結構失效。回傳 ``obs_after`` 與輸入 obs 一一對應（同樣長度、
    同樣順序，但失效狀態被更新）。

    Args:
        obs: ``build_obs_from_breaks`` 產出的列表（或 v1 swing-driven）。
        atr: float64 ATR 陣列；NaN 處 ``ob_distance_ratio`` 輸出 NaN。

    Returns:
        ``(obs_after, ob_touched, ob_distance_ratio)``。
    """
    n = closes.shape[0]
    touched = np.zeros(n, dtype=np.bool_)
    distance = np.full(n, np.nan, dtype=np.float64)
    if not obs:
        return obs, touched, distance

    # 依 formation_bar_index 排序（穩定排序保留同 index 的原序）。
    order = sorted(range(len(obs)), key=lambda i: obs[i].formation_bar_index)
    obs_mut: list[OrderBlock] = list(obs)

    # active_orig_idx：obs_mut 中尚未失效者的 *原列表 index*。
    active_orig_idx: list[int] = []
    next_to_admit = 0  # order 中下一個尚未進入 active 的位置

    for i in range(n):
        # (a) 把所有 formation_bar_index <= i 的 OB 加入 active。
        while (
            next_to_admit < len(order)
            and obs_mut[order[next_to_admit]].formation_bar_index <= i
        ):
            active_orig_idx.append(order[next_to_admit])
            next_to_admit += 1

        # (b) 用今日 K 棒更新失效狀態。
        if active_orig_idx:
            still: list[int] = []
            for idx in active_orig_idx:
                ob = obs_mut[idx]
                if ob.invalidated:
                    continue
                # 時間失效
                if i > ob.expiry_bar_index:
                    obs_mut[idx] = OrderBlock(
                        formation_timestamp=ob.formation_timestamp,
                        formation_bar_index=ob.formation_bar_index,
                        direction=ob.direction,
                        top=ob.top,
                        bottom=ob.bottom,
                        midpoint=ob.midpoint,
                        expiry_bar_index=ob.expiry_bar_index,
                        invalidated=True,
                        invalidation_timestamp=timestamps[i],
                        source_break_index=ob.source_break_index,
                        source_break_kind=ob.source_break_kind,
                    )
                    continue
                # 結構失效（用今日收盤）
                if valid_mask[i]:
                    c = closes[i]
                    if (ob.direction == "bullish" and c < ob.bottom) or (
                        ob.direction == "bearish" and c > ob.top
                    ):
                        obs_mut[idx] = OrderBlock(
                            formation_timestamp=ob.formation_timestamp,
                            formation_bar_index=ob.formation_bar_index,
                            direction=ob.direction,
                            top=ob.top,
                            bottom=ob.bottom,
                            midpoint=ob.midpoint,
                            expiry_bar_index=ob.expiry_bar_index,
                            invalidated=True,
                            invalidation_timestamp=timestamps[i],
                            source_break_index=ob.source_break_index,
                            source_break_kind=ob.source_break_kind,
                        )
                        continue
                still.append(idx)
            active_orig_idx = still

        # (c) 觸碰旗標 + 距離比（用最近的 active OB，formation_bar_index 最大者）。
        if valid_mask[i] and active_orig_idx:
            latest = max(active_orig_idx, key=lambda k: obs_mut[k].formation_bar_index)
            ob = obs_mut[latest]
            if not (highs[i] < ob.bottom or lows[i] > ob.top):
                touched[i] = True
            atr_i = atr[i]
            if not np.isnan(atr_i) and atr_i > 0:
                distance[i] = (closes[i] - ob.midpoint) / atr_i

    return obs_mut, touched, distance


# ---------------------------------------------------------------------------
# v1 swing-driven OB（deprecated wrapper — 由 batch.py Phase 6 切換完成後移除）
# ---------------------------------------------------------------------------


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
    """v1 swing-driven 入口 — 在 swing 標記出現時回望最後一根反向 K 形成 OB。

    保留為向後相容；v2 callers 應改用 ``build_obs_from_breaks`` +
    ``track_ob_lifecycle``。
    """
    n = opens.shape[0]
    obs: list[OrderBlock] = []
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
            source_break_index=ob.source_break_index,
            source_break_kind=ob.source_break_kind,
        )

    for i in range(n):
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

        if active_indices:
            still_active: list[int] = []
            for idx in active_indices:
                ob = obs[idx]
                if ob.invalidated:
                    continue
                if i > ob.expiry_bar_index:
                    _invalidate(idx, timestamps[i])
                    continue
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

        if valid_mask[i] and active_indices:
            latest = active_indices[-1]
            ob = obs[latest]
            if not (highs[i] < ob.bottom or lows[i] > ob.top):
                touched[i] = True
            atr_i = atr[i]
            if not np.isnan(atr_i) and atr_i > 0:
                distance_ratio[i] = (closes[i] - ob.midpoint) / atr_i

    return obs, touched, distance_ratio


__all__ = ["build_obs_from_breaks", "track_ob_lifecycle", "detect_and_track_obs"]
