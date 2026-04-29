"""yfinance adapter — 抓取單一 ticker 的日線 OHLCV。

研究決策見 research.md R1（auto_adjust=True）與 R3（tenacity 指數退避、無 jitter、
4xx 立即 fail-fast、5 次重試上限）。

呼叫端負責 quality flag 處理與 parquet 寫入；本模組僅做 client 互動 + 重試。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# yfinance 在 import 失敗時讓呼叫端處理（CI 不一定裝；單元測試可 monkeypatch
# fetch_yfinance 而完全不需要 yfinance）。
try:
    import yfinance as yf  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    yf = None  # type: ignore[assignment]


class YfinanceFetchError(RuntimeError):
    """Raised after exhausting retries or on non-retryable yfinance errors."""


def _retry_decorator(max_attempts: int, base_seconds: float, multiplier: float):
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=base_seconds, exp_base=multiplier),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        reraise=True,
    )


def fetch_yfinance(
    ticker: str,
    start: str,
    end: str,
    *,
    auto_adjust: bool = True,
    interval: str = "1d",
    max_attempts: int = 5,
    base_seconds: float = 1.0,
    multiplier: float = 2.0,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Download OHLCV daily bars for ``ticker``.

    Parameters
    ----------
    ticker : str
        Upper-case ticker (e.g. "NVDA").
    start, end : str
        Inclusive ISO 8601 dates (research R9). yfinance's ``end`` is
        exclusive so we add one day internally.

    Returns
    -------
    (df, call_params)
        ``df`` is the raw yfinance DataFrame with columns Open/High/Low/Close/
        Volume (capitalised — caller normalises). ``call_params`` is the
        verbatim record of the client-level invocation for metadata FR-012.
    """
    if yf is None:
        raise YfinanceFetchError(
            "yfinance is not installed in the current environment. "
            "Run `pip install yfinance~=0.2.40` (or rebuild the dev container)."
        )

    end_exclusive = (date.fromisoformat(end) + timedelta(days=1)).isoformat()

    @_retry_decorator(max_attempts, base_seconds, multiplier)
    def _do_fetch() -> pd.DataFrame:
        df = yf.download(
            tickers=ticker,
            start=start,
            end=end_exclusive,
            interval=interval,
            auto_adjust=auto_adjust,
            progress=False,
            threads=False,
            group_by="column",
        )
        if df is None or df.empty:
            raise YfinanceFetchError(
                f"yfinance returned empty DataFrame for {ticker!r} "
                f"(start={start}, end={end}); ticker may be delisted "
                "or temporarily unavailable."
            )
        return df

    try:
        raw = _do_fetch()
    except YfinanceFetchError:
        raise
    except RetryError as exc:
        raise YfinanceFetchError(
            f"yfinance failed for {ticker!r} after {max_attempts} retries: "
            f"{exc.last_attempt.exception()!r}"
        ) from exc
    except Exception as exc:
        raise YfinanceFetchError(
            f"yfinance fatal error for {ticker!r}: {exc!r}"
        ) from exc

    df = _normalise_yfinance_frame(raw, ticker)

    call_params = {
        "ticker": ticker,
        "start": start,
        "end": end_exclusive,
        "auto_adjust": bool(auto_adjust),
        "interval": interval,
    }
    return df, call_params


def _normalise_yfinance_frame(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Lower-case columns, drop multi-index, ensure expected dtype shape.

    yfinance occasionally returns a MultiIndex on columns when ``tickers`` is
    treated as a list — flatten to single level. The DataFrame is left
    otherwise untouched (no NaN handling, no quality_flag — that lives in
    quality.py per data-model.md §4 priority order).
    """
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    rename = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    df = df.rename(columns=rename)
    keep = ["open", "high", "low", "close", "volume"]
    missing = [c for c in keep if c not in df.columns]
    if missing:
        raise YfinanceFetchError(
            f"yfinance response for {ticker!r} missing columns {missing}; "
            f"got {list(df.columns)!r}"
        )
    df = df[keep]
    df.index.name = "date"
    if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df["volume"] = df["volume"].fillna(0).astype("int64")
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].astype("float64")
    return df
