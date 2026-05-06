"""SMC engine v2 batch_compute 合約驗證（spec 008 FR-007 / FR-013 / FR-014）。

對應 contracts/008-smc-engine-v2/contracts/batch_compute.contract.md Invariant
B-1 ~ B-7、tasks.md T039 ~ T044。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from smc_features import batch_compute
from smc_features.types import OrderBlock, SMCFeatureParams, StructureBreak

# ---------------------------------------------------------------------------
# T039 Invariant B-1 / B-2 — signal array ↔ breaks 對應
# ---------------------------------------------------------------------------


def test_breaks_signal_array_consistency(small_ohlcv, default_params):
    """contract Invariant B-1：sorted([nonzero bos] + [nonzero choch]) ==
    sorted(b.bar_index for b in breaks)；
    Invariant B-2：每個 break 對應 array 上恰一個非零位、kind 與 sign 對齊。
    """
    br = batch_compute(small_ohlcv, default_params)
    bos = br.output["bos_signal"]
    choch = br.output["choch_signal"]
    breaks = br.breaks

    bos_arr = np.array(
        [int(v) if not pd.isna(v) else 0 for v in bos], dtype=np.int8
    )
    choch_arr = np.array(
        [int(v) if not pd.isna(v) else 0 for v in choch], dtype=np.int8
    )

    nonzero_bos = sorted(np.flatnonzero(bos_arr).tolist())
    nonzero_choch = sorted(np.flatnonzero(choch_arr).tolist())
    break_indices = sorted(b.bar_index for b in breaks)
    assert sorted(nonzero_bos + nonzero_choch) == break_indices, (
        f"signal nonzero count {len(nonzero_bos) + len(nonzero_choch)} "
        f"!= breaks {len(breaks)}"
    )

    for b in breaks:
        if b.kind.startswith("BOS"):
            expected = 1 if "BULL" in b.kind else -1
            assert bos_arr[b.bar_index] == expected
            assert choch_arr[b.bar_index] == 0
        else:
            expected = 1 if "BULL" in b.kind else -1
            assert choch_arr[b.bar_index] == expected
            assert bos_arr[b.bar_index] == 0


# ---------------------------------------------------------------------------
# T040 Invariant B-3 — OB ↔ break 對齊
# ---------------------------------------------------------------------------


def test_obs_aligned_with_breaks(small_ohlcv, default_params):
    """每個 OB 的 source_break_index 合法、source_break_kind 一致、direction
    對齊。對應 contract Invariant B-3。
    """
    br = batch_compute(small_ohlcv, default_params, include_aux=True)
    breaks = br.breaks
    # obs 透過 BatchResult 輸出沒有直接 list；用 source_break_kind 驗證 column 存在
    # 這裡轉而從 batch.py 內部 obs（透過 ob_top_active/ob_bottom_active 反推 active 範圍）
    # 由於合約規定 BatchResult 不必直接暴露 obs 列表，本測試直接呼叫 build_obs_from_breaks
    # 重建 obs 列表，驗證每個 OB 的欄位一致性。
    from smc_features.ob import build_obs_from_breaks

    df = small_ohlcv
    valid_mask = (
        df["quality_flag"].to_numpy() == "ok"
        if "quality_flag" in df.columns
        else np.ones(len(df), dtype=np.bool_)
    )
    opens = df["open"].to_numpy(dtype=np.float64)
    highs = df["high"].to_numpy(dtype=np.float64)
    lows = df["low"].to_numpy(dtype=np.float64)
    closes = df["close"].to_numpy(dtype=np.float64)
    timestamps = df.index.to_numpy().astype("datetime64[ns]")

    obs = build_obs_from_breaks(
        breaks=breaks,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        timestamps=timestamps,
        valid_mask=valid_mask,
        ob_lookback_bars=default_params.ob_lookback_bars,
    )

    assert len(obs) <= len(breaks), f"OB 數 {len(obs)} > breaks 數 {len(breaks)}"
    for ob in obs:
        assert isinstance(ob, OrderBlock)
        assert 0 <= ob.source_break_index < len(breaks)
        src = breaks[ob.source_break_index]
        assert ob.source_break_kind == src.kind
        assert ob.formation_bar_index < src.bar_index
        if ob.direction == "bullish":
            assert src.kind in ("BOS_BULL", "CHOCH_BULL")
        else:
            assert src.kind in ("BOS_BEAR", "CHOCH_BEAR")


# ---------------------------------------------------------------------------
# T041 Invariant B-4 — anchor swing dedup
# ---------------------------------------------------------------------------


def test_dedup_anchor_swing_unique(small_ohlcv, default_params):
    """每個 (anchor_swing_bar_index, direction) 組合在 breaks 中至多一次。
    對應 contract Invariant B-4。
    """
    br = batch_compute(small_ohlcv, default_params)
    anchors = [
        (b.anchor_swing_bar_index, b.kind.endswith("_BULL")) for b in br.breaks
    ]
    assert len(anchors) == len(set(anchors)), (
        f"重複的 anchor: {[a for a in anchors if anchors.count(a) > 1]}"
    )


# ---------------------------------------------------------------------------
# T042 Invariant B-5 — FVG ATR 過濾正確
# ---------------------------------------------------------------------------


def test_fvg_atr_filter_in_batch_result(small_ohlcv):
    """直接呼叫 fvg + atr 子模組重建驗證每個 FVG 滿足過濾條件。

    對應 contract Invariant B-5。BatchResult 沒有直接 expose fvgs 列表，
    所以本測試重建 pipeline 的 FVG list 進行驗證。
    """
    from smc_features.atr import compute_atr
    from smc_features.fvg import detect_and_track_fvgs

    params = SMCFeatureParams(fvg_min_atr_ratio=0.25)
    df = small_ohlcv
    valid_mask = (
        df["quality_flag"].to_numpy() == "ok"
        if "quality_flag" in df.columns
        else np.ones(len(df), dtype=np.bool_)
    )
    highs = df["high"].to_numpy(dtype=np.float64)
    lows = df["low"].to_numpy(dtype=np.float64)
    closes = df["close"].to_numpy(dtype=np.float64)
    timestamps = df.index.to_numpy()

    atr = compute_atr(highs, lows, closes, params.atr_window, valid_mask)
    fvgs, _ = detect_and_track_fvgs(
        highs, lows, closes, timestamps, valid_mask,
        fvg_min_pct=params.fvg_min_pct,
        atr=atr,
        fvg_min_atr_ratio=params.fvg_min_atr_ratio,
    )

    n = len(df)
    for f in fvgs:
        height = f.top - f.bottom
        # ATR 取 formation 後一根（gap 完成的 bar），但 formation_bar_index 是
        # 中間 K（i-1），ATR 真值來自 i = formation+1 — 邊界處理：取 formation_bar_index
        # 對應的 ATR；若 NaN 退化為 mid_close 檢查
        idx = f.formation_bar_index + 1
        atr_at = atr[idx] if idx < n else np.nan
        if not np.isnan(atr_at) and atr_at > 0:
            assert height / atr_at >= params.fvg_min_atr_ratio, (
                f"FVG @ {f.formation_bar_index} ratio={height / atr_at} < "
                f"{params.fvg_min_atr_ratio}"
            )
        else:
            mid = (f.top + f.bottom) / 2.0
            assert height / mid >= params.fvg_min_pct


# ---------------------------------------------------------------------------
# T043 Invariant B-6 — observation 介面相容（PPO 5-channel）
# ---------------------------------------------------------------------------


def test_observation_5_channel_shape_unchanged(small_ohlcv, default_params):
    """從 BatchResult 組 5-channel float32 array → shape (n, 5)、dtype float32。

    對應 spec FR-013、Constitution Gate III-2、contract Invariant B-6。
    """
    br = batch_compute(small_ohlcv, default_params)
    out = br.output
    n = len(out)

    def _to_f32(col):
        # NA → 0.0 處理（與 PPO env 對齊）
        return col.fillna(0.0).to_numpy(dtype=np.float32)

    obs_5ch = np.stack(
        [
            _to_f32(out["bos_signal"]),
            _to_f32(out["choch_signal"]),
            _to_f32(out["fvg_distance_pct"]),
            _to_f32(out["ob_touched"].astype("float32")),
            _to_f32(out["ob_distance_ratio"]),
        ],
        axis=1,
    )
    assert obs_5ch.shape == (n, 5)
    assert obs_5ch.dtype == np.float32


# ---------------------------------------------------------------------------
# T044 Invariant B-7 — determinism
# ---------------------------------------------------------------------------


def test_batch_compute_deterministic(small_ohlcv, default_params):
    """同輸入跑兩次：output DataFrame、breaks 列表 byte-identical。

    對應 contract Invariant B-7、SC-006。
    """
    br1 = batch_compute(small_ohlcv, default_params, include_aux=True)
    br2 = batch_compute(small_ohlcv, default_params, include_aux=True)

    pd.testing.assert_frame_equal(br1.output, br2.output)
    assert len(br1.breaks) == len(br2.breaks)
    for a, b in zip(br1.breaks, br2.breaks, strict=True):
        assert isinstance(a, StructureBreak) and isinstance(b, StructureBreak)
        assert a == b
