"""BOS / CHoCh 結構突破事件偵測（v2 — feature 008）。

v2 規則
-------

維護下列狀態：

* ``last_swing_high`` / ``last_swing_low``：最近一個 *已確認* 的 swing 點（價位 + bar_index）。
* ``prev_swing_high`` / ``prev_swing_low``：前一個確認的 swing 點。
* ``trend ∈ {"bullish", "bearish", "neutral"}``：由事件流推進。
* ``used_swing_high_bar_indices`` / ``used_swing_low_bar_indices``：被突破過的 swing
  位置集合，用於 **dedup**（FR-003）。

判定邏輯（基於收盤價，避免影線假突破）：

1. **CHoCh（性格轉變，趨勢反轉）**——FR-002 / FR-004：
   * trend == bullish 且 ``close[t] < last_swing_low.price`` 且該 swing_low 未在 used 集合
     → ``choch_signal[t] = -1``、emit ``CHOCH_BEAR``、trend 翻轉為 bearish、加入 used。
   * trend == bearish 且 ``close[t] > last_swing_high.price`` 且該 swing_high 未在 used 集合
     → ``choch_signal[t] = +1``、emit ``CHOCH_BULL``、trend 翻轉為 bullish、加入 used。
2. **BOS（結構斷裂，趨勢延續）**——FR-002 / FR-003：
   * trend == bullish 且 ``close[t] > last_swing_high.price`` 且該 swing_high 未在 used 集合
     → ``bos_signal[t] = +1``、emit ``BOS_BULL``、trend 不變、加入 used。
   * trend == bearish 且 ``close[t] < last_swing_low.price`` 且該 swing_low 未在 used 集合
     → ``bos_signal[t] = -1``、emit ``BOS_BEAR``、trend 不變、加入 used。
3. **初始 BOS（neutral → bullish/bearish）**——FR-005：
   * trend == neutral 且 ``close[t] > last_swing_high.price`` 且未在 used → emit
     ``BOS_BULL``、trend = bullish。
   * trend == neutral 且 ``close[t] < last_swing_low.price`` 且未在 used → emit
     ``BOS_BEAR``、trend = bearish。
   * 若同時符合（bullish 與 bearish 突破），以 close 與 last_swing_high 距離較近者優先；
     此情境僅在價格極大跳空且 last_swing_high < last_swing_low 才可能（罕見）。
4. **CHoCh 優先於 BOS**（FR-004）：上述判定本身互斥（trend 已決定方向），但實作以
   if/elif 確保「同根 K 棒至多一個 break event」。
5. **同根 K 同時 swing + break**（FR-014 Edge Case）：先以本根 K *之前* 的
   ``last_swing_*`` 判定 break，再更新 ``last_swing_*``——這樣新形成的 swing 不會被
   自己突破。

瑕疵列（``valid_mask[t] == False``）：``bos_signal[t] = choch_signal[t] = 0`` 且不參與
狀態更新（spec FR-015）。

v2 對 v1 的差異
---------------

* 簽章新增 ``timestamps`` keyword-only 參數，回傳 3-tuple ``(bos_signal, choch_signal, breaks)``。
* 加入 dedup 集合：同一 swing 被突破後不再發第二次 break。
* neutral trend 第一次突破 → 初始 BOS（v1 不發；FR-005 改）。
* 結構突破事件以 ``StructureBreak`` dataclass 同步輸出，供前端視覺化與 RL ablation 追溯。
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from smc_features.types import StructureBreak


def compute_bos_choch(
    closes: NDArray[np.float64],
    highs: NDArray[np.float64],
    lows: NDArray[np.float64],
    swing_high_marker: NDArray[np.bool_],
    swing_low_marker: NDArray[np.bool_],
    valid_mask: NDArray[np.bool_],
    timestamps: NDArray[np.datetime64] | None = None,
) -> tuple[NDArray[np.int8], NDArray[np.int8], tuple[StructureBreak, ...]]:
    """計算每根 K 棒的 ``bos_signal`` / ``choch_signal``，以及對應的 ``StructureBreak``
    事件列表（v2 — feature 008）。

    Args:
        closes: 收盤價 float64 陣列。
        highs: 最高價（用於 swing_high anchor 價）。
        lows: 最低價（用於 swing_low anchor 價）。
        swing_high_marker: bool 陣列，True 處為已確認的 swing high。
        swing_low_marker: bool 陣列，True 處為已確認的 swing low。
        valid_mask: bool 陣列，False 處跳過（不發 signal、不更新 state）。
        timestamps: optional datetime64 陣列；省略時 ``StructureBreak.time``
            與 ``anchor_swing_time`` 將設為 ``np.datetime64("NaT")``，dedup 與
            signal 行為不變。

    Returns:
        ``(bos_signal, choch_signal, breaks)``：
        * ``bos_signal``: int8，值域 {-1, 0, 1}。
        * ``choch_signal``: int8，值域 {-1, 0, 1}。
        * ``breaks``: ``tuple[StructureBreak, ...]``，與 signal 一一對應。

    Example:
        >>> import numpy as np
        >>> from smc_features.structure import compute_bos_choch
        >>> closes = np.array([100.0, 100.0, 100.0, 105.0, 100.0, 100.0, 110.0])
        >>> highs = np.array([101.0, 101.0, 105.5, 105.0, 100.5, 100.5, 111.0])
        >>> lows = np.array([99.0, 99.0, 99.0, 99.0, 99.0, 99.0, 109.0])
        >>> sh = np.array([False, False, True, False, False, False, False])
        >>> sl = np.zeros(7, dtype=np.bool_)
        >>> valid = np.ones(7, dtype=np.bool_)
        >>> bos, choch, breaks = compute_bos_choch(closes, highs, lows, sh, sl, valid)
        >>> len(breaks)  # 第一次 close > 105.5 → 初始 BOS_BULL
        1
        >>> breaks[0].kind
        'BOS_BULL'
    """
    n = closes.shape[0]
    bos = np.zeros(n, dtype=np.int8)
    choch = np.zeros(n, dtype=np.int8)
    breaks: list[StructureBreak] = []
    if n == 0:
        return bos, choch, ()

    nat = np.datetime64("NaT")
    ts = timestamps if timestamps is not None else np.full(n, nat, dtype="datetime64[ns]")

    last_high_price: float | None = None
    last_high_idx: int | None = None
    prev_high_price: float | None = None
    last_low_price: float | None = None
    last_low_idx: int | None = None
    prev_low_price: float | None = None
    trend: str = "neutral"
    used_high_idx: set[int] = set()
    used_low_idx: set[int] = set()

    for i in range(n):
        if not valid_mask[i]:
            continue
        c = float(closes[i])

        # (a) 用「本根 K 之前」的 last_swing_* 判定 break event（FR-014 同根 K
        # swing+break 邊界：先 break 後 update swing）。
        kind: str | None = None
        anchor_idx: int | None = None
        anchor_price: float | None = None

        if trend == "bullish":
            # 1. CHoCh 優先：跌破 last_swing_low → CHOCH_BEAR
            if (
                last_low_price is not None
                and last_low_idx is not None
                and last_low_idx not in used_low_idx
                and c < last_low_price
            ):
                kind = "CHOCH_BEAR"
                anchor_idx = last_low_idx
                anchor_price = last_low_price
                used_low_idx.add(last_low_idx)
                trend = "bearish"
            # 2. BOS_BULL（trend 延續）
            elif (
                last_high_price is not None
                and last_high_idx is not None
                and last_high_idx not in used_high_idx
                and c > last_high_price
            ):
                kind = "BOS_BULL"
                anchor_idx = last_high_idx
                anchor_price = last_high_price
                used_high_idx.add(last_high_idx)

        elif trend == "bearish":
            if (
                last_high_price is not None
                and last_high_idx is not None
                and last_high_idx not in used_high_idx
                and c > last_high_price
            ):
                kind = "CHOCH_BULL"
                anchor_idx = last_high_idx
                anchor_price = last_high_price
                used_high_idx.add(last_high_idx)
                trend = "bullish"
            elif (
                last_low_price is not None
                and last_low_idx is not None
                and last_low_idx not in used_low_idx
                and c < last_low_price
            ):
                kind = "BOS_BEAR"
                anchor_idx = last_low_idx
                anchor_price = last_low_price
                used_low_idx.add(last_low_idx)

        else:  # neutral
            # FR-005 初始 BOS：第一次任一方向突破 → 設 trend、發 BOS_*。
            up_break = (
                last_high_price is not None
                and last_high_idx is not None
                and last_high_idx not in used_high_idx
                and c > last_high_price
            )
            down_break = (
                last_low_price is not None
                and last_low_idx is not None
                and last_low_idx not in used_low_idx
                and c < last_low_price
            )
            if up_break and not down_break:
                kind = "BOS_BULL"
                assert last_high_idx is not None and last_high_price is not None
                anchor_idx = last_high_idx
                anchor_price = last_high_price
                used_high_idx.add(last_high_idx)
                trend = "bullish"
            elif down_break and not up_break:
                kind = "BOS_BEAR"
                assert last_low_idx is not None and last_low_price is not None
                anchor_idx = last_low_idx
                anchor_price = last_low_price
                used_low_idx.add(last_low_idx)
                trend = "bearish"
            elif up_break and down_break:
                # 罕見：兩方向同時突破（last_swing_high < last_swing_low）。
                # 取突破幅度比較大者。
                assert last_high_price is not None and last_low_price is not None
                up_dist = c - last_high_price
                down_dist = last_low_price - c
                if up_dist >= down_dist:
                    kind = "BOS_BULL"
                    assert last_high_idx is not None
                    anchor_idx = last_high_idx
                    anchor_price = last_high_price
                    used_high_idx.add(last_high_idx)
                    trend = "bullish"
                else:
                    kind = "BOS_BEAR"
                    assert last_low_idx is not None
                    anchor_idx = last_low_idx
                    anchor_price = last_low_price
                    used_low_idx.add(last_low_idx)
                    trend = "bearish"

        # (b) 將 event 寫入 signal array + breaks 列表
        if kind is not None:
            assert anchor_idx is not None and anchor_price is not None
            sign = 1 if kind.endswith("_BULL") else -1
            if kind.startswith("BOS"):
                bos[i] = sign
            else:
                choch[i] = sign
            breaks.append(
                StructureBreak(
                    kind=kind,  # type: ignore[arg-type]
                    time=ts[i],
                    bar_index=i,
                    break_price=c,
                    anchor_swing_time=ts[anchor_idx],
                    anchor_swing_bar_index=anchor_idx,
                    anchor_swing_price=anchor_price,
                    trend_after=trend,  # type: ignore[arg-type]
                )
            )

        # (c) 本根 K 若被確認為 swing point，更新 last/prev（FR-014：先 break 後 update）。
        if swing_high_marker[i]:
            prev_high_price = last_high_price
            last_high_price = float(highs[i])
            last_high_idx = i
        if swing_low_marker[i]:
            prev_low_price = last_low_price
            last_low_price = float(lows[i])
            last_low_idx = i

        # (d) 任一 swing 更新後，若 trend 仍 neutral 且 HH/HL（或 LH/LL）已成立，
        # 透過 swing 結構升 trend。此邏輯仍保留（v1 行為）以涵蓋「初始 BOS 尚未觸發」
        # 但 swing 結構已明確顯示方向的場景。
        if (
            (swing_high_marker[i] or swing_low_marker[i])
            and trend == "neutral"
            and prev_high_price is not None
            and last_high_price is not None
            and prev_low_price is not None
            and last_low_price is not None
        ):
            if last_high_price > prev_high_price and last_low_price > prev_low_price:
                trend = "bullish"
            elif last_high_price < prev_high_price and last_low_price < prev_low_price:
                trend = "bearish"

    return bos, choch, tuple(breaks)


__all__ = ["compute_bos_choch"]
