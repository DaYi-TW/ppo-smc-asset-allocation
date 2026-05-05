"""SMC engine OB 偵測 — v1 swing-driven 與 v2 break-driven。

v1 部分（``detect_and_track_obs``）：bullish OB（swing low 前最後紅 K 棒）、
時間失效、結構失效。
v2 部分（``build_obs_from_breaks`` + ``track_ob_lifecycle``）：對應 spec 008
FR-008、FR-009、FR-010 與 contracts/batch_compute.contract.md Invariant B-3。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from smc_features.ob import detect_and_track_obs
from smc_features.types import StructureBreak


def _arrays(opens, highs, lows, closes):
    n = len(opens)
    return (
        np.asarray(opens, dtype=np.float64),
        np.asarray(highs, dtype=np.float64),
        np.asarray(lows, dtype=np.float64),
        np.asarray(closes, dtype=np.float64),
        pd.date_range("2024-01-02", periods=n, freq="B").to_numpy(),
        np.ones(n, dtype=np.bool_),
    )


# ---------------------------------------------------------------------------
# v1 swing-driven OB（保留為 deprecated wrapper，T029）
# ---------------------------------------------------------------------------


def test_bullish_ob_detected_before_swing_low():
    opens = [102, 100, 95, 100, 105]
    closes = [100, 101, 96, 102, 106]
    highs = [103, 102, 97, 103, 107]
    lows = [99, 99, 94, 99, 104]
    o, h, l_, c, ts, v = _arrays(opens, highs, lows, closes)
    swing_high_marker = np.zeros(5, dtype=np.bool_)
    swing_low_marker = np.array([False, False, True, False, False])
    atr = np.full(5, 1.0, dtype=np.float64)

    obs, _touched, _dist = detect_and_track_obs(
        o, h, l_, c, ts, v, swing_high_marker, swing_low_marker, atr, ob_lookback_bars=10
    )
    assert len(obs) == 1
    assert obs[0].direction == "bullish"
    assert obs[0].formation_bar_index == 0
    assert obs[0].top == 103.0
    assert obs[0].bottom == 99.0


def test_ob_time_expiry():
    opens = [102, 100, 95, 100, 105, 110]
    closes = [100, 101, 96, 102, 106, 111]
    highs = [103, 102, 97, 103, 107, 112]
    lows = [99, 99, 94, 99, 104, 109]
    o, h, l_, c, ts, v = _arrays(opens, highs, lows, closes)
    swing_high_marker = np.zeros(6, dtype=np.bool_)
    swing_low_marker = np.array([False, False, True, False, False, False])
    atr = np.full(6, 1.0, dtype=np.float64)

    obs, touched, _dist = detect_and_track_obs(
        o, h, l_, c, ts, v, swing_high_marker, swing_low_marker, atr, ob_lookback_bars=2
    )
    assert obs[0].invalidated
    assert not touched[5]


def test_ob_structural_invalidation():
    opens = [102, 100, 95, 100, 95, 90]
    closes = [100, 101, 96, 102, 96, 89]
    highs = [103, 102, 97, 103, 97, 92]
    lows = [99, 99, 94, 99, 95, 88]
    o, h, l_, c, ts, v = _arrays(opens, highs, lows, closes)
    swing_high_marker = np.zeros(6, dtype=np.bool_)
    swing_low_marker = np.array([False, False, True, False, False, False])
    atr = np.full(6, 1.0, dtype=np.float64)

    obs, _, _ = detect_and_track_obs(
        o, h, l_, c, ts, v, swing_high_marker, swing_low_marker, atr, ob_lookback_bars=10
    )
    assert obs[0].invalidated
    assert obs[0].invalidation_timestamp is not None


def test_ob_distance_nan_without_atr():
    opens = [102, 100, 95, 100, 105]
    closes = [100, 101, 96, 102, 106]
    highs = [103, 102, 97, 103, 107]
    lows = [99, 99, 94, 99, 104]
    o, h, l_, c, ts, v = _arrays(opens, highs, lows, closes)
    swing_low_marker = np.array([False, False, True, False, False])
    swing_high_marker = np.zeros(5, dtype=np.bool_)
    atr = np.full(5, np.nan, dtype=np.float64)

    _, _, dist = detect_and_track_obs(
        o, h, l_, c, ts, v, swing_high_marker, swing_low_marker, atr, ob_lookback_bars=10
    )
    assert np.isnan(dist).all()


# ---------------------------------------------------------------------------
# v2 break-driven OB（spec 008 FR-008 / FR-009 / contract Invariant B-3）
# ---------------------------------------------------------------------------


def _ts_ns(n: int) -> np.ndarray:
    return (np.datetime64("2024-01-02", "D") + np.arange(n, dtype="timedelta64[D]")).astype(
        "datetime64[ns]"
    )


def _make_break(idx: int, kind: str, bar_index: int, time, anchor_idx: int) -> StructureBreak:
    return StructureBreak(
        kind=kind,  # type: ignore[arg-type]
        time=time,
        bar_index=bar_index,
        break_price=100.0,
        anchor_swing_time=time,
        anchor_swing_bar_index=anchor_idx,
        anchor_swing_price=99.0,
        trend_after="bullish" if kind.endswith("_BULL") else "bearish",  # type: ignore[arg-type]
    )


def test_build_obs_from_breaks_one_per_break_or_fewer():
    """T022 — 給定 5 筆 break event，OB 數 ≤ 5、每個 OB 帶正確 source_break_*。

    對應 spec FR-008/FR-009、scenario US2-1、contract Invariant B-3。
    """
    from smc_features.ob import build_obs_from_breaks

    n = 50
    rng = np.random.default_rng(42)
    closes = 100.0 + np.cumsum(rng.standard_normal(n) * 0.5)
    opens = closes + rng.standard_normal(n) * 0.3
    highs = np.maximum(opens, closes) + np.abs(rng.standard_normal(n)) * 0.2
    lows = np.minimum(opens, closes) - np.abs(rng.standard_normal(n)) * 0.2
    valid = np.ones(n, dtype=np.bool_)
    ts = _ts_ns(n)

    # 5 個假 break：bar_index 10/15/20/25/30，方向交錯
    break_specs = [
        (10, "BOS_BULL", 5),
        (15, "BOS_BEAR", 12),
        (20, "BOS_BULL", 17),
        (25, "CHOCH_BEAR", 22),
        (30, "BOS_BULL", 27),
    ]
    breaks = tuple(
        _make_break(i, kind, br_idx, ts[br_idx], anchor)
        for i, (br_idx, kind, anchor) in enumerate(break_specs)
    )

    obs = build_obs_from_breaks(
        breaks=breaks,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        timestamps=ts,
        valid_mask=valid,
        ob_lookback_bars=50,
    )

    assert len(obs) <= len(breaks), f"len(obs)={len(obs)} > len(breaks)={len(breaks)}"
    for ob in obs:
        # source_break_index 指向 breaks 中合法位置
        assert 0 <= ob.source_break_index < len(breaks)
        src = breaks[ob.source_break_index]
        assert ob.source_break_kind == src.kind
        assert ob.formation_bar_index < src.bar_index
        if ob.direction == "bullish":
            assert src.kind in ("BOS_BULL", "CHOCH_BULL")
        else:
            assert src.kind in ("BOS_BEAR", "CHOCH_BEAR")


def test_no_ob_for_unbroken_swing():
    """T023 — 只有 swing 點但無 break event → obs 列表為空。

    對應 spec scenario US2-3。
    """
    from smc_features.ob import build_obs_from_breaks

    n = 30
    closes = np.linspace(100, 110, n)
    opens = closes - 0.5
    highs = closes + 0.3
    lows = closes - 0.3
    valid = np.ones(n, dtype=np.bool_)
    ts = _ts_ns(n)

    breaks: tuple[StructureBreak, ...] = ()
    obs = build_obs_from_breaks(
        breaks=breaks,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        timestamps=ts,
        valid_mask=valid,
        ob_lookback_bars=50,
    )
    assert obs == []


def test_ob_finds_last_opposite_candle_before_break():
    """T024 — break_index=10、之前 [0,9] 內第 7 根為紅 K（最後一根反向 K）→
    bullish break 對應 OB.formation_bar_index = 7、top/bottom = 該 K 的 high/low。

    對應 spec FR-008、scenario US2-2。
    """
    from smc_features.ob import build_obs_from_breaks

    n = 20
    # 前 10 根：i=7 是紅 K（close < open），其餘綠 K 或平
    opens = np.full(n, 100.0)
    closes = np.full(n, 101.0)  # 全綠
    opens[7] = 102.0
    closes[7] = 99.0  # i=7 紅 K (close < open)
    highs = np.maximum(opens, closes) + 0.5
    lows = np.minimum(opens, closes) - 0.5
    valid = np.ones(n, dtype=np.bool_)
    ts = _ts_ns(n)

    breaks = (
        _make_break(0, "BOS_BULL", bar_index=10, time=ts[10], anchor_idx=3),
    )
    obs = build_obs_from_breaks(
        breaks=breaks,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        timestamps=ts,
        valid_mask=valid,
        ob_lookback_bars=50,
    )
    assert len(obs) == 1
    ob = obs[0]
    assert ob.direction == "bullish"
    assert ob.formation_bar_index == 7
    assert ob.top == float(highs[7])
    assert ob.bottom == float(lows[7])
    assert ob.source_break_index == 0
    assert ob.source_break_kind == "BOS_BULL"


def test_ob_invalidation_rules_preserved():
    """T025 — 時間失效 + 結構失效兩條沿用 v1。

    對應 spec FR-010。
    """
    from smc_features.ob import build_obs_from_breaks, track_ob_lifecycle

    n = 30
    opens = np.full(n, 100.0)
    closes = np.full(n, 101.0)
    opens[3] = 102.0
    closes[3] = 99.0  # 紅 K @ i=3
    highs = np.maximum(opens, closes) + 0.5
    lows = np.minimum(opens, closes) - 0.5
    # bar 25：close 跌破 OB.bottom → 結構失效
    closes[25] = 95.0
    lows[25] = 94.0
    valid = np.ones(n, dtype=np.bool_)
    ts = _ts_ns(n)
    atr = np.full(n, 1.0, dtype=np.float64)

    # break @ bar 5（ob_lookback=10 → expiry=3+10=13；bar 25 已超期）
    breaks = (_make_break(0, "BOS_BULL", bar_index=5, time=ts[5], anchor_idx=1),)
    obs = build_obs_from_breaks(
        breaks=breaks,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        timestamps=ts,
        valid_mask=valid,
        ob_lookback_bars=10,
    )
    assert len(obs) == 1

    obs_after, touched, dist = track_ob_lifecycle(
        obs=obs,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        timestamps=ts,
        valid_mask=valid,
        atr=atr,
    )
    assert obs_after[0].invalidated
    # 失效後應有 invalidation_timestamp
    assert obs_after[0].invalidation_timestamp is not None


def test_no_ob_when_no_opposite_candle_in_lookback():
    """T026 — lookback 範圍內全是同向 K → break event 仍記錄但 obs 不增加。

    對應 spec Edge Case「OB 無反向 K」。
    """
    from smc_features.ob import build_obs_from_breaks

    n = 20
    # 全綠 K（close > open）— bullish break 找不到紅 K
    opens = np.full(n, 100.0)
    closes = np.full(n, 101.0)
    highs = closes + 0.5
    lows = opens - 0.5
    valid = np.ones(n, dtype=np.bool_)
    ts = _ts_ns(n)

    breaks = (_make_break(0, "BOS_BULL", bar_index=10, time=ts[10], anchor_idx=3),)
    obs = build_obs_from_breaks(
        breaks=breaks,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        timestamps=ts,
        valid_mask=valid,
        ob_lookback_bars=50,
    )
    assert obs == []
