"""Public API contract for ``smc_features``.

Phase 1 contract for feature 001-smc-feature-engine. Implementation lives in
``src/smc_features/`` and MUST conform to these signatures (parameter names,
types, defaults, and return shapes). Behavioural semantics are specified in
``spec.md`` (functional requirements) and ``data-model.md`` (entities).

This stub is the single source of truth for the public surface; CI MUST run
``mypy --strict`` against this file plus the implementation, and contract
tests in ``tests/contract/`` MUST exercise every public symbol declared here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Parameters & state (mirrors data-model.md §3, §5, §6)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SMCFeatureParams:
    swing_length: int = 5
    fvg_min_pct: float = 0.001
    ob_lookback_bars: int = 50
    atr_window: int = 14

    def __post_init__(self) -> None: ...


@dataclass(frozen=True)
class SwingPoint:
    timestamp: pd.Timestamp
    price: float
    kind: Literal["high", "low"]
    bar_index: int


@dataclass(frozen=True)
class FVG:
    formation_timestamp: pd.Timestamp
    formation_bar_index: int
    direction: Literal["bullish", "bearish"]
    top: float
    bottom: float
    is_filled: bool
    fill_timestamp: Optional[pd.Timestamp]


@dataclass(frozen=True)
class OrderBlock:
    formation_timestamp: pd.Timestamp
    formation_bar_index: int
    direction: Literal["bullish", "bearish"]
    top: float
    bottom: float
    midpoint: float
    expiry_bar_index: int
    invalidated: bool
    invalidation_timestamp: Optional[pd.Timestamp]


@dataclass(frozen=True)
class SMCEngineState:
    last_swing_high: Optional[SwingPoint]
    last_swing_low: Optional[SwingPoint]
    prev_swing_high: Optional[SwingPoint]
    prev_swing_low: Optional[SwingPoint]
    trend_state: Literal["bullish", "bearish", "neutral"]
    open_fvgs: tuple[FVG, ...]
    active_obs: tuple[OrderBlock, ...]
    atr_buffer: tuple[float, ...]
    last_atr: Optional[float]
    bar_count: int
    params: SMCFeatureParams


@dataclass(frozen=True)
class FeatureRow:
    timestamp: pd.Timestamp
    bos_signal: int
    choch_signal: int
    fvg_distance_pct: float
    ob_touched: bool
    ob_distance_ratio: float
    swing_high_marker: Optional[bool] = None
    swing_low_marker: Optional[bool] = None
    fvg_top_active: Optional[float] = None
    fvg_bottom_active: Optional[float] = None
    ob_top_active: Optional[float] = None
    ob_bottom_active: Optional[float] = None


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BatchResult:
    """Return value of ``batch_compute``.

    ``output`` preserves the input ``DataFrame``'s index and row count
    (spec FR-001) with appended feature columns (data-model.md §2).
    ``state`` is the engine state after processing the final bar — pass it
    to ``incremental_compute`` to switch to streaming mode (spec FR-008).
    """

    output: pd.DataFrame
    state: SMCEngineState


def batch_compute(
    df: pd.DataFrame,
    params: SMCFeatureParams = ...,
    *,
    include_aux: bool = False,
) -> BatchResult:
    """Compute SMC features over an entire OHLCV history.

    Args:
        df: OHLCV DataFrame matching ``data-model.md §1`` (DatetimeIndex,
            columns ``open``/``high``/``low``/``close``/``volume`` plus
            optional ``quality_flag``).
        params: Feature judgement parameters (spec FR-017). Defaults match
            the recommendations in ``research.md`` (R1–R3).
        include_aux: When ``True``, append the auxiliary visualisation
            columns described in ``data-model.md §2`` (``swing_high_marker``
            etc.). Default ``False`` keeps the output minimal.

    Returns:
        ``BatchResult`` with the augmented DataFrame and the terminal
        ``SMCEngineState``.

    Raises:
        ValueError: If the index is not monotonic increasing or unique
            (spec FR-013).
        KeyError: If any required OHLCV column is missing (spec FR-012).
        ValueError: If ``params`` violates its validation rules
            (data-model.md §3).
    """
    ...


def incremental_compute(
    prior_state: SMCEngineState,
    new_bar: pd.Series,
) -> tuple[FeatureRow, SMCEngineState]:
    """Advance the engine by one bar and return the new feature row.

    Args:
        prior_state: ``SMCEngineState`` returned from a previous
            ``batch_compute`` or ``incremental_compute`` call. The
            ``params`` embedded in ``prior_state`` are reused — the caller
            cannot change parameters mid-stream (spec FR-017).
        new_bar: A pandas ``Series`` whose ``name`` is the bar's
            ``pd.Timestamp`` and whose entries cover the same OHLCV(+
            optional ``quality_flag``) schema as ``batch_compute``'s
            ``df``. The timestamp MUST be strictly greater than the last
            processed bar.

    Returns:
        A pair ``(row, state)`` where ``row`` is the ``FeatureRow`` for
        ``new_bar`` and ``state`` is the updated engine state.

    Raises:
        ValueError: If ``new_bar.name`` is not strictly later than the
            previously processed bar.
        KeyError: If required OHLCV fields are missing.

    Equivalence:
        For any input DataFrame ``df`` and params ``p``:
            ``br = batch_compute(df, p)``
            ``br_prefix = batch_compute(df.iloc[:-1], p)``
            ``row, _ = incremental_compute(br_prefix.state, df.iloc[-1])``
        then ``row`` MUST equal ``br.output.iloc[-1]`` value-wise
        (spec FR-008, data-model.md invariant 4).
    """
    ...


def visualize(
    df_with_features: pd.DataFrame,
    time_range: tuple[pd.Timestamp, pd.Timestamp],
    output_path: Path | str,
    fmt: Literal["png", "html"] = "png",
    *,
    params: Optional[SMCFeatureParams] = None,
) -> None:
    """Render an annotated K-line chart with SMC overlays.

    The plot MUST overlay swing high/low markers, unfilled FVG bands,
    active OB bands, and BOS/CHoCh event labels (spec FR-009, FR-010).

    Args:
        df_with_features: Output of ``batch_compute`` with
            ``include_aux=True``. The auxiliary columns are required for
            FVG/OB band drawing.
        time_range: Inclusive ``(start, end)`` timestamps. The slice MUST
            lie within ``df_with_features.index``.
        output_path: Destination file path. Parent directory MUST exist.
        fmt: ``"png"`` uses ``mplfinance`` (static raster); ``"html"`` uses
            ``plotly`` (interactive). See ``research.md`` R4.
        params: Optional ``SMCFeatureParams`` for the figure's parameter
            footnote (spec FR-011). When omitted, no footnote is drawn.

    Raises:
        ValueError: If ``time_range`` falls outside the DataFrame index
            or if required auxiliary columns are absent.
        KeyError: If feature columns are missing from
            ``df_with_features``.
    """
    ...


__all__ = [
    "SMCFeatureParams",
    "SwingPoint",
    "FVG",
    "OrderBlock",
    "SMCEngineState",
    "FeatureRow",
    "BatchResult",
    "batch_compute",
    "incremental_compute",
    "visualize",
]
