"""SMC Feature Engine 的不可變資料型別。

本模組提供 frozen dataclass 定義，對齊 ``specs/001-smc-feature-engine/data-model.md``
§3–§6 與 ``specs/001-smc-feature-engine/contracts/api.pyi``。

設計原則：
* 所有結構皆 ``frozen=True``，保證可重現性（憲法 Principle I）— 任何就地修改皆觸發
  ``dataclasses.FrozenInstanceError``。
* ``SMCFeatureParams`` 在 ``__post_init__`` 強制檢驗參數區間，違反即拋
  ``ValueError``，避免無效參數靜默產生錯誤特徵。
* ``SMCEngineState.initial(params)`` 提供統一初始狀態工廠，確保 batch 與 incremental
  路徑在 ``bar_count == 0`` 時完全一致。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Public type aliases
# ---------------------------------------------------------------------------

SwingKind = Literal["high", "low"]
Direction = Literal["bullish", "bearish"]
TrendState = Literal["bullish", "bearish", "neutral"]
BreakKind = Literal["BOS_BULL", "BOS_BEAR", "CHOCH_BULL", "CHOCH_BEAR"]
VizFormat = Literal["png", "html"]


# ---------------------------------------------------------------------------
# Parameters (data-model.md §3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SMCFeatureParams:
    """SMC 特徵判定參數。

    Attributes:
        swing_length: Swing high/low 偵測左右各 L 根（research R1）。
        fvg_min_pct: FVG 最小幅度（相對中間 K 棒收盤；research R2）。
        ob_lookback_bars: Order Block 時間失效視窗（research R3）。
        atr_window: ATR 平滑視窗（Wilder smoothing；research R3）。

    Raises:
        ValueError: 任一參數違反區間。
    """

    swing_length: int = 5
    fvg_min_pct: float = 0.001
    ob_lookback_bars: int = 50
    atr_window: int = 14
    fvg_min_atr_ratio: float = 0.25

    def __post_init__(self) -> None:
        if self.swing_length < 1:
            raise ValueError(f"swing_length 必須 >= 1，收到 {self.swing_length}")
        if self.fvg_min_pct < 0:
            raise ValueError(f"fvg_min_pct 必須 >= 0，收到 {self.fvg_min_pct}")
        if self.ob_lookback_bars < 1:
            raise ValueError(f"ob_lookback_bars 必須 >= 1，收到 {self.ob_lookback_bars}")
        if self.atr_window < 1:
            raise ValueError(f"atr_window 必須 >= 1，收到 {self.atr_window}")
        if self.fvg_min_atr_ratio < 0:
            raise ValueError(
                f"fvg_min_atr_ratio 必須 >= 0，收到 {self.fvg_min_atr_ratio}"
            )


# ---------------------------------------------------------------------------
# Internal entities (data-model.md §4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SwingPoint:
    """確認的 swing high 或 swing low。"""

    timestamp: pd.Timestamp
    price: float
    kind: SwingKind
    bar_index: int


@dataclass(frozen=True)
class FVG:
    """Fair Value Gap（三 K 棒缺口）。

    狀態轉移：``is_filled`` 由 ``False`` → ``True`` 單向；一旦填補不可復原。
    """

    formation_timestamp: pd.Timestamp
    formation_bar_index: int
    direction: Direction
    top: float
    bottom: float
    is_filled: bool
    fill_timestamp: pd.Timestamp | None


@dataclass(frozen=True)
class OrderBlock:
    """Order Block（v2：由 BOS / CHoCh break event 觸發，往回找最後一根反向 K）。

    有效判定：``active = (not invalidated) and (current_bar_index <= expiry_bar_index)``

    v2 新增 ``source_break_index`` / ``source_break_kind`` 兩欄位用以追溯觸發 OB 的
    structure break 事件；`-1` / 空字串為 sentinel，僅供 v1 swing-driven 路徑暫時
    沿用，待 batch.py 切換完成後 v2 路徑保證為正確值。
    """

    formation_timestamp: pd.Timestamp
    formation_bar_index: int
    direction: Direction
    top: float
    bottom: float
    midpoint: float
    expiry_bar_index: int
    invalidated: bool
    invalidation_timestamp: pd.Timestamp | None
    source_break_index: int = -1
    source_break_kind: BreakKind | Literal[""] = ""


@dataclass(frozen=True)
class StructureBreak:
    """BOS / CHoCh 結構突破事件（spec 008 FR-006）。

    每個 instance 對應 batch ``bos_signal`` / ``choch_signal`` 中恰一個非零位。

    Attributes:
        kind: 事件類型——BOS_BULL / BOS_BEAR / CHOCH_BULL / CHOCH_BEAR。
        time: 突破當下 K 棒時間戳。
        bar_index: 突破當下 K 棒在序列中的位置。
        break_price: 突破當下 close。
        anchor_swing_time: 被突破的 swing point 時間戳。
        anchor_swing_bar_index: 被突破的 swing point 位置。
        anchor_swing_price: 被突破的 swing point 價位。
        trend_after: 事件處理完之後的 trend 狀態。
    """

    kind: BreakKind
    time: np.datetime64
    bar_index: int
    break_price: float
    anchor_swing_time: np.datetime64
    anchor_swing_bar_index: int
    anchor_swing_price: float
    trend_after: TrendState


# ---------------------------------------------------------------------------
# Engine state & row outputs (data-model.md §5–§6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SMCEngineState:
    """增量計算狀態快照。

    每次 ``incremental_compute`` 回傳新 instance；呼叫前後 ``prior_state`` 不變
    （見 contracts/api.pyi `Equivalence`）。

    ``window_bars`` 為內部尾段 OHLCV 視窗（每元素為
    ``(timestamp_ns, open, high, low, close, volume, valid)``），用於
    ``incremental_compute`` 的尾段重算（research R6）。對外 contracts/api.pyi
    不顯式列出此欄位，但仍受 ``frozen`` 保護。
    """

    last_swing_high: SwingPoint | None
    last_swing_low: SwingPoint | None
    prev_swing_high: SwingPoint | None
    prev_swing_low: SwingPoint | None
    trend_state: TrendState
    open_fvgs: tuple[FVG, ...]
    active_obs: tuple[OrderBlock, ...]
    atr_buffer: tuple[float, ...]
    last_atr: float | None
    bar_count: int
    params: SMCFeatureParams
    window_bars: tuple[
        tuple[int, float, float, float, float, float, bool], ...
    ] = ()

    @classmethod
    def initial(cls, params: SMCFeatureParams) -> SMCEngineState:
        """建立 ``bar_count == 0`` 的初始狀態。"""
        return cls(
            last_swing_high=None,
            last_swing_low=None,
            prev_swing_high=None,
            prev_swing_low=None,
            trend_state="neutral",
            open_fvgs=(),
            active_obs=(),
            atr_buffer=(),
            last_atr=None,
            bar_count=0,
            params=params,
            window_bars=(),
        )


@dataclass(frozen=True)
class FeatureRow:
    """單根 K 棒的 SMC 特徵輸出（增量模式回傳的列結構）。"""

    timestamp: pd.Timestamp
    bos_signal: int
    choch_signal: int
    fvg_distance_pct: float
    ob_touched: bool
    ob_distance_ratio: float
    swing_high_marker: bool | None = None
    swing_low_marker: bool | None = None
    fvg_top_active: float | None = None
    fvg_bottom_active: float | None = None
    ob_top_active: float | None = None
    ob_bottom_active: float | None = None


@dataclass(frozen=True)
class BatchResult:
    """``batch_compute`` 的回傳容器。

    ``output`` 保留輸入 DataFrame 的 index 與列數（spec FR-001）。
    ``state`` 是處理完最後一根 K 棒後的引擎狀態，可直接餵給
    ``incremental_compute`` 切換到串流模式（spec FR-008）。
    ``breaks`` 是 v2 新增（feature 008 FR-007）的結構突破事件列表，
    與 ``output`` 中 ``bos_signal``/``choch_signal`` 一一對應：每個
    非零 signal 位置對應 ``breaks`` 中恰一個 ``StructureBreak``。
    """

    output: pd.DataFrame
    state: SMCEngineState
    breaks: tuple[StructureBreak, ...] = field(default_factory=tuple)


__all__ = [
    "FVG",
    "BatchResult",
    "BreakKind",
    "Direction",
    "FeatureRow",
    "OrderBlock",
    "SMCEngineState",
    "SMCFeatureParams",
    "StructureBreak",
    "SwingKind",
    "SwingPoint",
    "TrendState",
    "VizFormat",
]
