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

from dataclasses import dataclass
from typing import Literal

import pandas as pd

# ---------------------------------------------------------------------------
# Public type aliases
# ---------------------------------------------------------------------------

SwingKind = Literal["high", "low"]
Direction = Literal["bullish", "bearish"]
TrendState = Literal["bullish", "bearish", "neutral"]
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

    def __post_init__(self) -> None:
        if self.swing_length < 1:
            raise ValueError(f"swing_length 必須 >= 1，收到 {self.swing_length}")
        if self.fvg_min_pct < 0:
            raise ValueError(f"fvg_min_pct 必須 >= 0，收到 {self.fvg_min_pct}")
        if self.ob_lookback_bars < 1:
            raise ValueError(f"ob_lookback_bars 必須 >= 1，收到 {self.ob_lookback_bars}")
        if self.atr_window < 1:
            raise ValueError(f"atr_window 必須 >= 1，收到 {self.atr_window}")


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
    """Order Block（趨勢反轉前的最後一根反向 K 棒）。

    有效判定：``active = (not invalidated) and (current_bar_index <= expiry_bar_index)``
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
    """

    output: pd.DataFrame
    state: SMCEngineState


__all__ = [
    "FVG",
    "BatchResult",
    "Direction",
    "FeatureRow",
    "OrderBlock",
    "SMCEngineState",
    "SMCFeatureParams",
    "SwingKind",
    "SwingPoint",
    "TrendState",
    "VizFormat",
]
