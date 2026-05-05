"""SMC engine v2 結構突破事件偵測 — BOS dedup + CHoCh + neutral 初始 BOS。

對應 spec 008 FR-002 ~ FR-007、tasks.md T012 ~ T017。

v2 介面：``compute_bos_choch(closes, highs, lows, sh, sl, valid, timestamps)``
回傳 ``(bos_signal, choch_signal, breaks)``，其中 breaks 為
``tuple[StructureBreak, ...]``。每個 non-zero signal 位置對應 breaks 中
恰一個 event；同一 swing 在被突破後不再發第二次 break。
"""

from __future__ import annotations

import numpy as np

from smc_features.structure import compute_bos_choch
from smc_features.types import StructureBreak


def _ts(n: int) -> np.ndarray:
    """產出長度 n 的 datetime64[ns] timestamp 陣列。"""
    return (np.datetime64("2024-01-01", "D") + np.arange(n, dtype="timedelta64[D]")).astype(
        "datetime64[ns]"
    )


# ---------------------------------------------------------------------------
# T012 BOS dedup — 同 swing 被突破後不應再發 BOS
# ---------------------------------------------------------------------------


def test_bos_dedup_same_swing_only_once():
    """連續 N 根 K 棒 close > last_swing_high → 只在第一根發 BOS_BULL，後續=0。

    對應 spec FR-003、scenario US1-1。
    """
    n = 25
    closes = np.full(n, 100.0)
    highs = np.full(n, 100.5)
    lows = np.full(n, 99.5)
    sh = np.zeros(n, dtype=np.bool_)
    sl = np.zeros(n, dtype=np.bool_)
    valid = np.ones(n, dtype=np.bool_)
    timestamps = _ts(n)

    # bar 5：swing_low @ 95.0（價格谷）
    lows[5] = 95.0
    sl[5] = True
    # bar 10：swing_high @ 110.0（價格峰）— 此 swing 將被突破
    highs[10] = 110.0
    sh[10] = True
    # bar 13：swing_low @ 100.0（HL，使 trend 升 bullish）
    lows[13] = 100.0
    sl[13] = True
    # bar 15 起連續 close > 110：應只在第一根（bar 15）發 BOS_BULL
    for i in range(15, 25):
        closes[i] = 112.0 + (i - 15) * 0.5
        highs[i] = closes[i] + 0.5

    bos, choch, breaks = compute_bos_choch(closes, highs, lows, sh, sl, valid, timestamps)

    bos_nonzero = np.flatnonzero(bos != 0)
    assert len(bos_nonzero) == 1, (
        f"同 swing 應只發一次 BOS，實際 {len(bos_nonzero)} 次 @ idx={bos_nonzero.tolist()}"
    )
    assert bos[bos_nonzero[0]] == 1
    assert (choch == 0).all()
    assert len(breaks) == 1
    assert breaks[0].kind == "BOS_BULL"
    assert breaks[0].bar_index == int(bos_nonzero[0])
    assert breaks[0].anchor_swing_bar_index == 10
    assert breaks[0].anchor_swing_price == 110.0


# ---------------------------------------------------------------------------
# T013 CHoCh 優先 — 同根 K 同時符合 BOS / CHoCh 條件時發 CHoCh
# ---------------------------------------------------------------------------


def test_choch_priority_over_bos():
    """trend 為 bullish 時，若 close 同時 > last_swing_high 又 < last_swing_low
    在數學上互斥（bullish 下 last_swing_low < last_swing_high）。
    這個 test 驗證 CHoCh 翻轉後的 trend：bullish → close 跌破 last_swing_low
    應發 CHoCh_BEAR、不發 BOS。

    對應 spec FR-004、scenario US1-2。
    """
    n = 25
    closes = np.full(n, 100.0)
    highs = np.full(n, 100.5)
    lows = np.full(n, 99.5)
    sh = np.zeros(n, dtype=np.bool_)
    sl = np.zeros(n, dtype=np.bool_)
    valid = np.ones(n, dtype=np.bool_)
    timestamps = _ts(n)

    # 構造 bullish trend：sl@5(95) → sh@10(110) → sl@13(100, HL)
    lows[5] = 95.0
    sl[5] = True
    highs[10] = 110.0
    sh[10] = True
    lows[13] = 100.0
    sl[13] = True
    # bar 15：先突破 sh@10 → BOS_BULL（trend 確立 bullish 並 dedup sh@10）
    closes[15] = 112.0
    highs[15] = 112.5
    # bar 17：close 跌破 last_swing_low（sl@13=100）→ CHoCh_BEAR
    closes[17] = 99.0
    lows[17] = 98.5

    bos, choch, breaks = compute_bos_choch(closes, highs, lows, sh, sl, valid, timestamps)

    # 應有兩個 break：BOS_BULL @ 15、CHOCH_BEAR @ 17
    assert len(breaks) == 2
    assert breaks[0].kind == "BOS_BULL"
    assert breaks[1].kind == "CHOCH_BEAR"
    # CHoCh 那根 bos 必為 0（FR-004 互斥）
    assert bos[17] == 0
    assert choch[17] == -1


# ---------------------------------------------------------------------------
# T014 neutral 期初始 BOS — neutral → 第一次突破應發 BOS（不發 CHoCh）
# ---------------------------------------------------------------------------


def test_initial_bos_from_neutral_sets_trend():
    """trend=neutral 時，第一次 close > last_swing_high 應發 BOS_BULL
    並設 trend=bullish；不發 CHoCh（CHoCh 需有方向才能反轉）。

    對應 spec FR-005、Edge Case「初始 BOS」。
    """
    n = 15
    closes = np.full(n, 100.0)
    highs = np.full(n, 100.5)
    lows = np.full(n, 99.5)
    sh = np.zeros(n, dtype=np.bool_)
    sl = np.zeros(n, dtype=np.bool_)
    valid = np.ones(n, dtype=np.bool_)
    timestamps = _ts(n)

    # 唯一的 swing_high @ bar 3：105.0
    highs[3] = 105.0
    sh[3] = True
    # bar 8：close 突破 105 → 應發 BOS_BULL（不是 CHoCh，因為 prev trend=neutral）
    closes[8] = 106.0
    highs[8] = 106.5

    bos, choch, breaks = compute_bos_choch(closes, highs, lows, sh, sl, valid, timestamps)

    assert len(breaks) == 1
    assert breaks[0].kind == "BOS_BULL"
    assert breaks[0].trend_after == "bullish"
    assert bos[8] == 1
    assert choch[8] == 0


# ---------------------------------------------------------------------------
# T015 同根 K 同時 swing + break — 先處理 break、再更新 last_swing_*
# ---------------------------------------------------------------------------


def test_swing_and_break_same_bar_order():
    """若同根 K 同時被確認為 swing point + 觸發 break，必須先用 *本根 K 之前*
    的 last_swing_* 判定 break，再更新 last_swing_*。否則新形成的 swing 可能
    被自己突破。

    對應 spec FR-014 Edge Case「同根 K swing + break」。
    """
    n = 20
    closes = np.full(n, 100.0)
    highs = np.full(n, 100.5)
    lows = np.full(n, 99.5)
    sh = np.zeros(n, dtype=np.bool_)
    sl = np.zeros(n, dtype=np.bool_)
    valid = np.ones(n, dtype=np.bool_)
    timestamps = _ts(n)

    # 唯一 swing_high @ bar 3：105.0
    highs[3] = 105.0
    sh[3] = True
    # bar 10：同時 close 突破 105 + 確認為新 swing_high（價=108）
    # break 應以 sh@3=105 為 anchor、不以本根 K 的 108 為 anchor
    closes[10] = 106.0
    highs[10] = 108.0
    sh[10] = True

    bos, choch, breaks = compute_bos_choch(closes, highs, lows, sh, sl, valid, timestamps)

    assert len(breaks) == 1, f"預期 1 個 break，實際 {len(breaks)}"
    assert breaks[0].anchor_swing_bar_index == 3, (
        f"anchor 應為 bar 3 (105)，實際 bar {breaks[0].anchor_swing_bar_index}"
    )
    assert breaks[0].anchor_swing_price == 105.0


# ---------------------------------------------------------------------------
# T016 StructureBreak 欄位完整性 + anchor 對應真實 swing
# ---------------------------------------------------------------------------


def test_breaks_list_full_fields():
    """每個 StructureBreak 的 anchor_swing_* 必須對應序列中真實存在的 swing 點。

    對應 spec FR-006、SC-005。
    """
    n = 25
    closes = np.full(n, 100.0)
    highs = np.full(n, 100.5)
    lows = np.full(n, 99.5)
    sh = np.zeros(n, dtype=np.bool_)
    sl = np.zeros(n, dtype=np.bool_)
    valid = np.ones(n, dtype=np.bool_)
    timestamps = _ts(n)

    lows[5] = 95.0
    sl[5] = True
    highs[10] = 110.0
    sh[10] = True
    lows[13] = 100.0
    sl[13] = True
    closes[15] = 112.0
    highs[15] = 112.5

    bos, choch, breaks = compute_bos_choch(closes, highs, lows, sh, sl, valid, timestamps)

    assert len(breaks) >= 1
    for b in breaks:
        assert isinstance(b, StructureBreak)
        # anchor swing 必須存在於 sh 或 sl marker
        if "BULL" in b.kind:
            assert sh[b.anchor_swing_bar_index], (
                f"anchor @ {b.anchor_swing_bar_index} 不是 swing high"
            )
            assert b.anchor_swing_price == highs[b.anchor_swing_bar_index]
        else:
            assert sl[b.anchor_swing_bar_index], (
                f"anchor @ {b.anchor_swing_bar_index} 不是 swing low"
            )
            assert b.anchor_swing_price == lows[b.anchor_swing_bar_index]
        # break_price 必為突破當下 close
        assert b.break_price == closes[b.bar_index]
        # bar_index > anchor_swing_bar_index
        assert b.bar_index > b.anchor_swing_bar_index
        # time 與 anchor_swing_time 與 timestamps 對齊
        assert b.time == timestamps[b.bar_index]
        assert b.anchor_swing_time == timestamps[b.anchor_swing_bar_index]


# ---------------------------------------------------------------------------
# T017 signal array <-> breaks 列表計數一致性
# ---------------------------------------------------------------------------


def test_breaks_signal_array_count_consistency():
    """sum(|bos|) + sum(|choch|) == len(breaks)。每個 break 對應 array
    上恰一個非零位、kind 與 sign 對齊。

    對應 contracts/batch_compute.contract.md Invariant B-1、B-2、B-4。
    """
    rng = np.random.default_rng(seed=42)
    n = 200
    closes = 100.0 + np.cumsum(rng.standard_normal(n))
    highs = closes + np.abs(rng.standard_normal(n)) * 0.5
    lows = closes - np.abs(rng.standard_normal(n)) * 0.5
    valid = np.ones(n, dtype=np.bool_)
    timestamps = _ts(n)

    # 用 swing detector 產生真實 marker
    from smc_features.swing import detect_swings

    sh, sl = detect_swings(highs, lows, swing_length=5, valid_mask=valid)

    bos, choch, breaks = compute_bos_choch(closes, highs, lows, sh, sl, valid, timestamps)

    total_signals = int(np.sum(np.abs(bos)) + np.sum(np.abs(choch)))
    assert total_signals == len(breaks), (
        f"signal 總數 {total_signals} 不等於 breaks 列表長度 {len(breaks)}"
    )

    # 每個 break 對應 array 上恰一個非零位 + sign 對齊
    for b in breaks:
        if b.kind == "BOS_BULL":
            assert bos[b.bar_index] == 1
            assert choch[b.bar_index] == 0
        elif b.kind == "BOS_BEAR":
            assert bos[b.bar_index] == -1
            assert choch[b.bar_index] == 0
        elif b.kind == "CHOCH_BULL":
            assert choch[b.bar_index] == 1
            assert bos[b.bar_index] == 0
        elif b.kind == "CHOCH_BEAR":
            assert choch[b.bar_index] == -1
            assert bos[b.bar_index] == 0
