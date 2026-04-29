"""Quality flag enum constants and judgment logic.

See data-model.md §4. Priority order when multiple conditions match a row:
    missing_close (or missing_rate) > zero_volume > ok

`duplicate_dropped` is **not** a row-level flag — duplicates are removed before
writing, and only counted in metadata.quality_summary.
"""

from __future__ import annotations

from typing import Final

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
