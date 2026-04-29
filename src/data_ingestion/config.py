"""IngestionConfig — frozen dataclass for fetch / verify / rebuild parameters.

Mirrors `contracts/api.pyi` exactly. Validation runs in __post_init__ so a
malformed config raises ValueError at construction time, never silently at
fetch time. See data-model.md §5 for the validation rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal


_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]*$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class IngestionConfig:
    tickers_risk_on: tuple[str, ...] = ("NVDA", "AMD", "TSM", "MU")
    tickers_risk_off: tuple[str, ...] = ("GLD", "TLT")
    fred_series_id: str = "DTB3"
    start_date: str = "2018-01-01"
    end_date: str = "2026-04-29"
    output_dir: Path = Path("data/raw")
    interval: Literal["1d"] = "1d"
    auto_adjust: bool = True
    snappy_compression: bool = True
    max_retry_attempts: int = 5
    retry_base_seconds: float = 1.0
    retry_multiplier: float = 2.0

    def __post_init__(self) -> None:
        for label, value in (("start_date", self.start_date), ("end_date", self.end_date)):
            if not _ISO_DATE_RE.match(value):
                raise ValueError(f"{label} must be ISO 8601 YYYY-MM-DD, got {value!r}")
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"{label} is not a valid calendar date: {value!r}") from exc

        if date.fromisoformat(self.start_date) > date.fromisoformat(self.end_date):
            raise ValueError(
                f"start_date ({self.start_date}) must be <= end_date ({self.end_date})"
            )

        all_tickers = tuple(self.tickers_risk_on) + tuple(self.tickers_risk_off)
        if not all_tickers:
            raise ValueError("at least one ticker must be configured")
        for t in all_tickers:
            if not _TICKER_RE.match(t):
                raise ValueError(
                    f"ticker {t!r} must be uppercase alphanumeric (with optional . or -)"
                )
        if len(set(all_tickers)) != len(all_tickers):
            raise ValueError(f"duplicate tickers detected: {all_tickers}")

        if not self.fred_series_id or not self.fred_series_id.strip():
            raise ValueError("fred_series_id must be a non-empty string")

        if self.max_retry_attempts < 1:
            raise ValueError(
                f"max_retry_attempts must be >= 1, got {self.max_retry_attempts}"
            )
        if self.retry_base_seconds <= 0:
            raise ValueError(
                f"retry_base_seconds must be > 0, got {self.retry_base_seconds}"
            )
        if self.retry_multiplier < 1.0:
            raise ValueError(
                f"retry_multiplier must be >= 1.0, got {self.retry_multiplier}"
            )

    def all_tickers(self) -> tuple[str, ...]:
        return tuple(self.tickers_risk_on) + tuple(self.tickers_risk_off)
