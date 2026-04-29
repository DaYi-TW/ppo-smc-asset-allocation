"""FRED adapter — 抓取單一 series（預設 DTB3）的日頻觀測值。

研究決策見 research.md R2（fredapi、FRED_API_KEY env）與 R3（同 yfinance 重試政策）。

API key 永遠由環境變數提供，禁止寫入 commit、metadata、log。本模組在 fetch
入口立刻檢查 env 缺失並 fail-fast（FR-021）。
"""

from __future__ import annotations

import os
from typing import Any

import pandas as pd
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

try:
    from fredapi import Fred
except ImportError:  # pragma: no cover
    Fred = None


_FRED_API_KEY_ENV = "FRED_API_KEY"


class FredFetchError(RuntimeError):
    """Raised after exhausting retries or on FRED config errors."""


class FredApiKeyMissingError(FredFetchError):
    """Specifically raised when FRED_API_KEY env var is unset (FR-021)."""

    def __init__(self) -> None:
        super().__init__(
            "FRED_API_KEY environment variable is not set. "
            "Register for a free key at "
            "https://fred.stlouisfed.org/docs/api/api_key.html "
            f"and export {_FRED_API_KEY_ENV} before running fetch."
        )


def _retry_decorator(max_attempts: int, base_seconds: float, multiplier: float):
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=base_seconds, exp_base=multiplier),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        reraise=True,
    )


def fetch_fred(
    series_id: str,
    start: str,
    end: str,
    *,
    api_key: str | None = None,
    max_attempts: int = 5,
    base_seconds: float = 1.0,
    multiplier: float = 2.0,
) -> tuple[pd.Series, dict[str, Any]]:
    """Fetch a FRED series as a pandas.Series with DatetimeIndex (UTC-naive).

    Returns ``(series, call_params)``. ``call_params`` records the verbatim
    invocation for metadata FR-012. The API key is **never** included in
    call_params — only the env var name is implicit context.
    """
    key = api_key or os.environ.get(_FRED_API_KEY_ENV)
    if not key:
        raise FredApiKeyMissingError()

    if Fred is None:
        raise FredFetchError(
            "fredapi is not installed in the current environment. "
            "Run `pip install fredapi~=0.5.2` (or rebuild the dev container)."
        )

    client = Fred(api_key=key)

    @_retry_decorator(max_attempts, base_seconds, multiplier)
    def _do_fetch() -> pd.Series:
        s = client.get_series(
            series_id,
            observation_start=start,
            observation_end=end,
        )
        if s is None or len(s) == 0:
            raise FredFetchError(
                f"FRED returned empty series for {series_id!r} "
                f"({start} → {end}); check the series_id is valid."
            )
        return s

    try:
        raw = _do_fetch()
    except FredFetchError:
        raise
    except RetryError as exc:
        raise FredFetchError(
            f"FRED fetch for {series_id!r} failed after {max_attempts} retries: "
            f"{exc.last_attempt.exception()!r}"
        ) from exc
    except Exception as exc:
        raise FredFetchError(
            f"FRED fatal error for {series_id!r}: {exc!r}"
        ) from exc

    series = raw.copy()
    series.name = "rate_pct"
    series.index.name = "date"
    if isinstance(series.index, pd.DatetimeIndex) and series.index.tz is not None:
        series.index = series.index.tz_localize(None)
    series = series.astype("float64")

    call_params = {
        "series_id": series_id,
        "observation_start": start,
        "observation_end": end,
    }
    return series, call_params
