"""``batch_compute`` — 對整段 OHLCV 一次計算所有 SMC 特徵。

實作步驟：

1. 驗證輸入 schema（spec FR-012/FR-013）。
2. 建立 ``valid_mask = (quality_flag == "ok")``（缺欄則全 True）。
3. 依序呼叫 swing → ATR → BOS/CHoCh → FVG → OB 子模組。
4. 組裝輸出 DataFrame（int8 / float64 / bool dtype 嚴格指定）。
5. ``include_aux=True`` 時加入 6 個視覺化輔助欄位。
6. 回傳 ``BatchResult(output, terminal_state)``。

Determinism：所有計算路徑為純 numpy / pandas float64；不依賴系統時間或亂數
（spec FR-007）。``BatchResult.state`` 由最終的 swing/ATR/FVG/OB 結構快照組成，
可餵給 ``incremental_compute`` 切換到串流模式（spec FR-008）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from smc_features.atr import compute_atr
from smc_features.fvg import detect_and_track_fvgs
from smc_features.ob import detect_and_track_obs
from smc_features.structure import compute_bos_choch
from smc_features.swing import detect_swings
from smc_features.types import (
    BatchResult,
    SMCEngineState,
    SMCFeatureParams,
    SwingPoint,
)

_REQUIRED_COLS = ("open", "high", "low", "close", "volume")


def _validate_input(df: pd.DataFrame) -> None:
    missing = [c for c in _REQUIRED_COLS if c not in df.columns]
    if missing:
        raise KeyError(f"缺少必要欄位：{missing}（需要 {list(_REQUIRED_COLS)}）")
    if not df.index.is_monotonic_increasing:
        raise ValueError("DataFrame index 必須單調遞增（spec FR-013）")
    if not df.index.is_unique:
        raise ValueError("DataFrame index 必須唯一（spec FR-013）")


def _build_valid_mask(df: pd.DataFrame) -> np.ndarray:
    if "quality_flag" not in df.columns:
        return np.ones(len(df), dtype=np.bool_)
    qf = df["quality_flag"].astype("string")
    return (qf == "ok").to_numpy(dtype=np.bool_, na_value=False)


def _last_two_swings(
    marker: np.ndarray,
    timestamps: np.ndarray,
    prices: np.ndarray,
    kind: str,
) -> tuple[SwingPoint | None, SwingPoint | None]:
    """回傳 ``(last, prev)`` 兩個 SwingPoint（最近與上一個）；不足則 None。"""
    indices = np.flatnonzero(marker)
    if len(indices) == 0:
        return None, None
    last_i = int(indices[-1])
    last = SwingPoint(
        timestamp=pd.Timestamp(timestamps[last_i]),
        price=float(prices[last_i]),
        kind=kind,  # type: ignore[arg-type]
        bar_index=last_i,
    )
    if len(indices) == 1:
        return last, None
    prev_i = int(indices[-2])
    prev = SwingPoint(
        timestamp=pd.Timestamp(timestamps[prev_i]),
        price=float(prices[prev_i]),
        kind=kind,  # type: ignore[arg-type]
        bar_index=prev_i,
    )
    return last, prev


def batch_compute(
    df: pd.DataFrame,
    params: SMCFeatureParams | None = None,
    *,
    include_aux: bool = False,
) -> BatchResult:
    """對 OHLCV DataFrame 一次計算 SMC 特徵。

    Args:
        df: OHLCV DataFrame；index 為 ``DatetimeIndex``，欄位含
            ``open/high/low/close/volume``，可選 ``quality_flag``。
        params: 特徵判定參數；省略時使用 ``SMCFeatureParams()`` 預設。
        include_aux: ``True`` 時加入 6 個視覺化輔助欄位（data-model.md §2）。

    Returns:
        ``BatchResult(output=DataFrame, state=SMCEngineState)``。

    Raises:
        KeyError: 缺必要欄位。
        ValueError: index 非單調遞增 / 非唯一，或 ``params`` 違反區間。
    """
    if params is None:
        params = SMCFeatureParams()
    _validate_input(df)

    n = len(df)
    valid_mask = _build_valid_mask(df)
    opens = df["open"].to_numpy(dtype=np.float64, copy=False)
    highs = df["high"].to_numpy(dtype=np.float64, copy=False)
    lows = df["low"].to_numpy(dtype=np.float64, copy=False)
    closes = df["close"].to_numpy(dtype=np.float64, copy=False)
    timestamps = df.index.to_numpy()

    # 1. swing
    swing_high_marker, swing_low_marker = detect_swings(
        highs, lows, params.swing_length, valid_mask
    )

    # 2. ATR
    atr = compute_atr(highs, lows, closes, params.atr_window, valid_mask)

    # 3. BOS / CHoCh
    bos, choch = compute_bos_choch(
        closes, highs, lows, swing_high_marker, swing_low_marker, valid_mask
    )

    # 4. FVG
    fvgs, fvg_distance_pct = detect_and_track_fvgs(
        highs, lows, closes, timestamps, valid_mask, params.fvg_min_pct
    )

    # 5. OB
    obs, ob_touched, ob_distance_ratio = detect_and_track_obs(
        opens,
        highs,
        lows,
        closes,
        timestamps,
        valid_mask,
        swing_high_marker,
        swing_low_marker,
        atr,
        params.ob_lookback_bars,
    )

    # 6. 將瑕疵列的全部特徵設為 NA。
    bos_int8 = pd.array(bos, dtype="Int8")
    choch_int8 = pd.array(choch, dtype="Int8")
    ob_touched_bool = pd.array(ob_touched, dtype="boolean")
    fvg_dist = fvg_distance_pct.copy()
    ob_dist = ob_distance_ratio.copy()
    invalid = ~valid_mask
    if invalid.any():
        bos_int8[invalid] = pd.NA
        choch_int8[invalid] = pd.NA
        ob_touched_bool[invalid] = pd.NA
        fvg_dist[invalid] = np.nan
        ob_dist[invalid] = np.nan

    output = df.copy()
    output["bos_signal"] = bos_int8
    output["choch_signal"] = choch_int8
    output["fvg_distance_pct"] = fvg_dist
    output["ob_touched"] = ob_touched_bool
    output["ob_distance_ratio"] = ob_dist

    if include_aux:
        # FVG / OB top/bottom 來自最近未填補 / 有效者；用線掃 + 索引位置記錄。
        fvg_top_active = np.full(n, np.nan, dtype=np.float64)
        fvg_bottom_active = np.full(n, np.nan, dtype=np.float64)
        ob_top_active = np.full(n, np.nan, dtype=np.float64)
        ob_bottom_active = np.full(n, np.nan, dtype=np.float64)

        # 重建 FVG aux：依 formation_bar_index 與 fill_timestamp 推每根 K 棒「最近未填補」者。
        fvg_intervals = [
            (
                f.formation_bar_index,
                # 找填補位置的 bar_index — fvg.fill_timestamp 對應 timestamps 中的位置。
                int(np.searchsorted(timestamps, np.datetime64(f.fill_timestamp)))
                if f.fill_timestamp is not None
                else n,
                f.top,
                f.bottom,
            )
            for f in fvgs
        ]
        for i in range(n):
            if not valid_mask[i]:
                continue
            best_form = -1
            top_v = np.nan
            bottom_v = np.nan
            for form_i, fill_i, top, bottom in fvg_intervals:
                if form_i <= i < fill_i and form_i > best_form:
                    best_form = form_i
                    top_v = top
                    bottom_v = bottom
            if best_form >= 0:
                fvg_top_active[i] = top_v
                fvg_bottom_active[i] = bottom_v

        ob_intervals = [
            (
                ob.formation_bar_index,
                int(np.searchsorted(timestamps, np.datetime64(ob.invalidation_timestamp)))
                if ob.invalidation_timestamp is not None
                else min(ob.expiry_bar_index + 1, n),
                ob.top,
                ob.bottom,
            )
            for ob in obs
        ]
        for i in range(n):
            if not valid_mask[i]:
                continue
            best_form = -1
            top_v = np.nan
            bottom_v = np.nan
            for form_i, end_i, top, bottom in ob_intervals:
                if form_i <= i < end_i and form_i > best_form:
                    best_form = form_i
                    top_v = top
                    bottom_v = bottom
            if best_form >= 0:
                ob_top_active[i] = top_v
                ob_bottom_active[i] = bottom_v

        output["swing_high_marker"] = pd.array(swing_high_marker, dtype="boolean")
        output["swing_low_marker"] = pd.array(swing_low_marker, dtype="boolean")
        output["fvg_top_active"] = fvg_top_active
        output["fvg_bottom_active"] = fvg_bottom_active
        output["ob_top_active"] = ob_top_active
        output["ob_bottom_active"] = ob_bottom_active

    # 7. 構造 terminal SMCEngineState（供 incremental 切換）。
    last_swing_high, prev_swing_high = _last_two_swings(
        swing_high_marker, timestamps, highs, "high"
    )
    last_swing_low, prev_swing_low = _last_two_swings(swing_low_marker, timestamps, lows, "low")
    # 為 incremental 準備 ATR buffer：取最近 atr_window 個有效 TR。
    # 這裡為 MVP 簡化：incremental Phase 5 才嚴格使用，目前快照儲存最後 atr_window 個 TR。
    tr_buffer: list[float] = []
    last_atr_value: float | None = None
    if not np.isnan(atr).all():
        # 找最後一個非 NaN ATR 作為 last_atr。
        last_valid = np.where(~np.isnan(atr))[0]
        if last_valid.size > 0:
            last_atr_value = float(atr[last_valid[-1]])
    # 收最近 atr_window 個有效 TR — 可由 high/low/close 重新計算最後段以避免額外傳遞。
    for i in range(max(0, n - params.atr_window), n):
        if not valid_mask[i]:
            continue
        if i == 0 or not valid_mask[i - 1]:
            tr_i = float(highs[i] - lows[i])
        else:
            tr_i = float(
                max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]),
                )
            )
        tr_buffer.append(tr_i)

    # 趨勢狀態：以最後兩個 swing high / low 比較推回最終 trend_state。
    trend_state: str = "neutral"
    if (
        last_swing_high is not None
        and prev_swing_high is not None
        and last_swing_low is not None
        and prev_swing_low is not None
    ):
        hh_hl = (last_swing_high.price > prev_swing_high.price) and (
            last_swing_low.price > prev_swing_low.price
        )
        lh_ll = (last_swing_high.price < prev_swing_high.price) and (
            last_swing_low.price < prev_swing_low.price
        )
        if hh_hl:
            trend_state = "bullish"
        elif lh_ll:
            trend_state = "bearish"

    state = SMCEngineState(
        last_swing_high=last_swing_high,
        last_swing_low=last_swing_low,
        prev_swing_high=prev_swing_high,
        prev_swing_low=prev_swing_low,
        trend_state=trend_state,  # type: ignore[arg-type]
        open_fvgs=tuple(f for f in fvgs if not f.is_filled),
        active_obs=tuple(
            ob for ob in obs if (not ob.invalidated) and ((n - 1) <= ob.expiry_bar_index)
        ),
        atr_buffer=tuple(tr_buffer),
        last_atr=last_atr_value,
        bar_count=n,
        params=params,
    )

    return BatchResult(output=output, state=state)


__all__ = ["batch_compute"]
