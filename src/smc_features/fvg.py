"""Fair Value Gap (FVG) 偵測與距離計算（research R2）。

定義
----

對連續三根 K 棒 ``bar[i-2], bar[i-1], bar[i]``：

* **Bullish FVG**：``low[i] > high[i-2]``。區間 ``[high[i-2], low[i]]``，
  形成位置記錄為中間 K 棒 ``i-1``。
* **Bearish FVG**：``high[i] < low[i-2]``。區間 ``[high[i], low[i-2]]``。

FVG 高度 ``(top - bottom) / close[i-1]`` 必須 ≥ ``fvg_min_pct``（預設 0.001）；
否則視為雜訊忽略（spec FR-017）。

填補規則
--------

FVG 形成後，後續任一 K 棒 ``j > i``：

* Bullish FVG 完全填補：``low[j] <= bottom``
* Bearish FVG 完全填補：``high[j] >= top``

填補為單向：一旦填補不可復原（data-model.md §4.2 狀態轉移）。

距離特徵
--------

``fvg_distance_pct[t]`` 取 **目前所有未填補 FVG 中時間距離最近的一個**，計算
``(close[t] - midpoint) / close[t]``（帶符號百分比；正值表示收盤在 FVG 上方）。
若無未填補 FVG，輸出 NaN。

瑕疵列（``valid_mask[t] = False``）：對應 ``t`` 既不參與 FVG 形成判定，亦不更新
任何 FVG 的填補狀態，輸出該位置距離為 NaN。
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from smc_features.types import FVG


def detect_and_track_fvgs(
    highs: NDArray[np.float64],
    lows: NDArray[np.float64],
    closes: NDArray[np.float64],
    timestamps: NDArray,
    valid_mask: NDArray[np.bool_],
    fvg_min_pct: float,
    atr: NDArray[np.float64] | None = None,
    fvg_min_atr_ratio: float = 0.0,
) -> tuple[list[FVG], NDArray[np.float64]]:
    """掃描全段資料，回傳 FVG 列表與每根 K 棒的 fvg_distance_pct。

    過濾邏輯（spec 008 FR-011）：
      1. 若 ``atr`` 提供且 ``atr[i]`` 非 NaN：要求 ``(top - bottom) / atr[i] >=
         fvg_min_atr_ratio``。
      2. 否則（``atr`` 未提供 / ``atr[i] = NaN``）：退化為 ``(top - bottom) /
         mid_close >= fvg_min_pct`` 絕對下限檢查。
      3. ``fvg_min_atr_ratio = 0.0`` 等價於停用 ATR 過濾（與 v1 行為相同）。

    Args:
        highs / lows / closes: float64 序列。
        timestamps: pandas DatetimeIndex 等價的 ndarray（``df.index.values``）。
        valid_mask: bool 序列；False 列從計算中跳過。
        fvg_min_pct: 最小幅度門檻（含），相對於中間 K 棒收盤。
        atr: optional float64 ATR 陣列；提供時用 ATR-relative 過濾。
        fvg_min_atr_ratio: ATR-relative 最小 ratio（含；spec 預設 0.25）。

    Returns:
        ``(fvgs, distance_pct_array)`` —

        * ``fvgs``: 形成順序排列的 ``FVG`` 物件列表（含已填補與未填補）。
        * ``distance_pct_array``: 與輸入同長的 float64 陣列。
    """
    n = highs.shape[0]
    distances = np.full(n, np.nan, dtype=np.float64)
    fvgs: list[FVG] = []
    # 為提升填補追蹤效率，分別維護 bullish / bearish 未填補列表（升序，按 formation_bar_index）。
    open_bull: list[int] = []  # 在 fvgs 中的索引
    open_bear: list[int] = []

    for i in range(n):
        # (a) 先以「今日 K 棒」更新尚未填補的 FVG 之填補狀態
        if valid_mask[i]:
            h_i, low_i = highs[i], lows[i]
            still_open_bull: list[int] = []
            for idx in open_bull:
                fvg = fvgs[idx]
                if low_i <= fvg.bottom:
                    fvgs[idx] = FVG(
                        formation_timestamp=fvg.formation_timestamp,
                        formation_bar_index=fvg.formation_bar_index,
                        direction=fvg.direction,
                        top=fvg.top,
                        bottom=fvg.bottom,
                        is_filled=True,
                        fill_timestamp=timestamps[i],
                    )
                else:
                    still_open_bull.append(idx)
            open_bull = still_open_bull

            still_open_bear: list[int] = []
            for idx in open_bear:
                fvg = fvgs[idx]
                if h_i >= fvg.top:
                    fvgs[idx] = FVG(
                        formation_timestamp=fvg.formation_timestamp,
                        formation_bar_index=fvg.formation_bar_index,
                        direction=fvg.direction,
                        top=fvg.top,
                        bottom=fvg.bottom,
                        is_filled=True,
                        fill_timestamp=timestamps[i],
                    )
                else:
                    still_open_bear.append(idx)
            open_bear = still_open_bear

        # (b) 偵測新 FVG（需 i >= 2 且 i-2, i-1, i 三根皆 valid）
        if i >= 2 and valid_mask[i] and valid_mask[i - 1] and valid_mask[i - 2]:
            h2 = highs[i - 2]
            low2 = lows[i - 2]
            mid_close = closes[i - 1]
            if mid_close > 0:
                atr_i = atr[i] if atr is not None else np.nan
                use_atr_filter = (
                    atr is not None
                    and fvg_min_atr_ratio > 0.0
                    and not np.isnan(atr_i)
                    and atr_i > 0
                )

                # bullish: low[i] > high[i-2]
                if lows[i] > h2:
                    top = float(lows[i])
                    bottom = float(h2)
                    height = top - bottom
                    if use_atr_filter:
                        keep = height / atr_i >= fvg_min_atr_ratio
                    else:
                        keep = height / mid_close >= fvg_min_pct
                    if keep:
                        fvgs.append(
                            FVG(
                                formation_timestamp=timestamps[i - 1],
                                formation_bar_index=i - 1,
                                direction="bullish",
                                top=top,
                                bottom=bottom,
                                is_filled=False,
                                fill_timestamp=None,
                            )
                        )
                        open_bull.append(len(fvgs) - 1)
                # bearish: high[i] < low[i-2]
                elif highs[i] < low2:
                    top = float(low2)
                    bottom = float(highs[i])
                    height = top - bottom
                    if use_atr_filter:
                        keep = height / atr_i >= fvg_min_atr_ratio
                    else:
                        keep = height / mid_close >= fvg_min_pct
                    if keep:
                        fvgs.append(
                            FVG(
                                formation_timestamp=timestamps[i - 1],
                                formation_bar_index=i - 1,
                                direction="bearish",
                                top=top,
                                bottom=bottom,
                                is_filled=False,
                                fill_timestamp=None,
                            )
                        )
                        open_bear.append(len(fvgs) - 1)

        # (c) 計算距離 — 取所有未填補 FVG 中 formation_bar_index 最大者（最近形成）
        if valid_mask[i] and (open_bull or open_bear):
            latest_idx = -1
            if open_bull and open_bear:
                latest_idx = max(open_bull[-1], open_bear[-1])
            elif open_bull:
                latest_idx = open_bull[-1]
            else:
                latest_idx = open_bear[-1]
            fvg = fvgs[latest_idx]
            mid = (fvg.top + fvg.bottom) / 2.0
            c = closes[i]
            if c != 0:
                distances[i] = (c - mid) / c
    return fvgs, distances


__all__ = ["detect_and_track_fvgs"]
