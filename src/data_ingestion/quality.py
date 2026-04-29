"""Quality flag enum constants and judgment logic.

See data-model.md §4. Priority order when multiple conditions match a row:
    missing_close (or missing_rate) > zero_volume > ok

`duplicate_dropped` is **not** a row-level flag — duplicates are removed before
writing, and only counted in metadata.quality_summary.
"""

from __future__ import annotations

from typing import Final

import pandas as pd

OK: Final[str] = "ok"
MISSING_CLOSE: Final[str] = "missing_close"
ZERO_VOLUME: Final[str] = "zero_volume"
MISSING_RATE: Final[str] = "missing_rate"
DUPLICATE_DROPPED: Final[str] = "duplicate_dropped"

ASSET_FLAGS: Final[frozenset[str]] = frozenset({OK, MISSING_CLOSE, ZERO_VOLUME})
RATE_FLAGS: Final[frozenset[str]] = frozenset({OK, MISSING_RATE})
ALL_FLAGS: Final[frozenset[str]] = frozenset(
    {OK, MISSING_CLOSE, ZERO_VOLUME, MISSING_RATE, DUPLICATE_DROPPED}
)


def classify_asset_row(
    *, open_: float, high: float, low: float, close: float, volume: int
) -> str:
    """Return the quality_flag for a single OHLCV row.

    NaN in any of open/high/low/close → "missing_close" (the priority bucket
    for OHLCV gaps). volume == 0 with all prices present → "zero_volume".
    Otherwise "ok".
    """
    import math

    for v in (open_, high, low, close):
        if isinstance(v, float) and math.isnan(v):
            return MISSING_CLOSE
    if volume == 0:
        return ZERO_VOLUME
    return OK


def classify_rate_row(*, rate_pct: float) -> str:
    """Return the quality_flag for a FRED rate row."""
    import math

    if isinstance(rate_pct, float) and math.isnan(rate_pct):
        return MISSING_RATE
    return OK


# ---------------------------------------------------------------------------
# DataFrame-level helpers used by Phase 3 fetch pipeline
# ---------------------------------------------------------------------------


def apply_asset_quality_flags(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    """Process an OHLCV DataFrame: drop duplicate index, add quality_flag.

    Parameters
    ----------
    df : pandas.DataFrame
        Must contain columns ``open``, ``high``, ``low``, ``close``, ``volume``
        and a DatetimeIndex named ``date``. The DataFrame may contain duplicate
        index entries (yfinance occasional behaviour, FR-011) which will be
        kept-first then dropped.

    Returns
    -------
    (clean_df, duplicate_dropped_timestamps)
        ``clean_df`` has a unique monotonic-increasing index, a ``string``
        ``quality_flag`` column appended last, and unchanged numeric values.
        ``duplicate_dropped_timestamps`` is the list of ISO date strings that
        were removed (kept first occurrence). Order matches removal order.
    """
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"asset DataFrame missing columns: {sorted(missing)}")

    duplicated_mask = df.index.duplicated(keep="first")
    duplicate_dropped_timestamps = [
        ts.strftime("%Y-%m-%d") for ts in df.index[duplicated_mask]
    ]
    clean = df.loc[~duplicated_mask].copy()
    clean = clean.sort_index()

    flags: list[str] = []
    for row in clean.itertuples(index=False):
        flags.append(
            classify_asset_row(
                open_=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=int(row.volume) if pd.notna(row.volume) else 0,
            )
        )
    clean["quality_flag"] = pd.array(flags, dtype="string")

    column_order = ["open", "high", "low", "close", "volume", "quality_flag"]
    clean = clean[column_order]
    clean.index.name = "date"
    return clean, duplicate_dropped_timestamps


def apply_rate_quality_flags(
    series: pd.Series,
) -> tuple[pd.DataFrame, list[str]]:
    """Process a FRED rate Series: drop duplicate index, add quality_flag.

    Returns the same shape contract as :func:`apply_asset_quality_flags` but
    with columns ``rate_pct`` and ``quality_flag``.
    """
    if not isinstance(series, pd.Series):
        raise TypeError(f"rate input must be pandas.Series, got {type(series).__name__}")

    duplicated_mask = series.index.duplicated(keep="first")
    duplicate_dropped_timestamps = [
        ts.strftime("%Y-%m-%d") for ts in series.index[duplicated_mask]
    ]
    clean = series.loc[~duplicated_mask].sort_index()

    df = pd.DataFrame({"rate_pct": clean.astype("float64")})
    flags = [classify_rate_row(rate_pct=float(v)) if pd.notna(v) else MISSING_RATE
             for v in df["rate_pct"]]
    df["quality_flag"] = pd.array(flags, dtype="string")
    df.index.name = "date"
    return df, duplicate_dropped_timestamps


def summarize_quality_flags(
    flags: pd.Series,
    *,
    duplicate_dropped: int = 0,
) -> dict[str, int]:
    """Build a quality_summary dict for metadata writing.

    Always returns the full set of keys (FR-012, JSON Schema requires all five),
    zero-filled when the corresponding flag never appears.
    """
    counts = flags.value_counts().to_dict()
    return {
        "ok": int(counts.get(OK, 0)),
        "missing_close": int(counts.get(MISSING_CLOSE, 0)),
        "zero_volume": int(counts.get(ZERO_VOLUME, 0)),
        "missing_rate": int(counts.get(MISSING_RATE, 0)),
        "duplicate_dropped": int(duplicate_dropped),
    }
