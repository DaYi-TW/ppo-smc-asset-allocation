"""Public Python API for feature 002-data-ingestion.

This stub defines the contract surface consumed by downstream features
(in particular 001-smc-feature-engine and the future PPO training feature).
All names exported here MUST be re-exported from `data_ingestion/__init__.py`.

Implementations MUST NOT add or remove names from this surface without
bumping the feature MAJOR version (see contracts/cli.md for the same rule).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Mapping, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Metadata structures (parsed from *.parquet.meta.json)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ColumnSchema:
    name: str
    dtype: Literal["float64", "int64", "string", "bool"]


@dataclass(frozen=True)
class IndexSchema:
    name: Literal["date"]
    dtype: Literal["datetime64[ns]"]
    tz: Optional[str]


@dataclass(frozen=True)
class TimeRange:
    start: str   # ISO 8601 date
    end: str


@dataclass(frozen=True)
class QualitySummary:
    ok: int
    missing_close: int = 0
    zero_volume: int = 0
    missing_rate: int = 0
    duplicate_dropped: int = 0


@dataclass(frozen=True)
class SnapshotMetadata:
    schema_version: Literal["1.0"]
    fetch_timestamp_utc: datetime
    data_source: Literal["yfinance", "fred"]
    data_source_call_params: Mapping[str, object]
    upstream_package_versions: Mapping[str, str]
    sha256: str
    row_count: int
    column_schema: tuple[ColumnSchema, ...]
    index_schema: IndexSchema
    time_range: TimeRange
    quality_summary: QualitySummary
    duplicate_dropped_timestamps: tuple[str, ...]


# ---------------------------------------------------------------------------
# Verification result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerifyResult:
    parquet_path: Path
    metadata_path: Path
    sha256_match: bool
    row_count_match: bool
    schema_match: bool
    expected_sha256: str
    actual_sha256: str
    message: str        # Human-readable summary; "OK" if all matches, else first failure reason

    @property
    def ok(self) -> bool: ...


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def load_asset_snapshot(
    ticker: str,
    data_dir: Path = Path("data/raw"),
) -> pd.DataFrame:
    """Load an OHLCV Parquet snapshot for the given ticker.

    Parameters
    ----------
    ticker : str
        Upper-case ticker symbol (e.g. ``"NVDA"``). Case-insensitive on input.
    data_dir : Path, default ``data/raw``
        Directory containing snapshot Parquet files.

    Returns
    -------
    pandas.DataFrame
        DataFrame with columns ``open``, ``high``, ``low``, ``close``,
        ``volume``, ``quality_flag`` and a ``DatetimeIndex`` named ``date``.
        Schema matches feature 001's input contract directly; no transformation
        is required by the caller.

    Raises
    ------
    FileNotFoundError
        If no Parquet matching the ticker is found in ``data_dir``.
    ValueError
        If multiple Parquets matching the ticker are found (ambiguous).

    Performance
    -----------
    SC-003: returns within 100 ms on standard SSD hardware for a single asset.
    """
    ...


def load_rate_snapshot(
    series_id: str = "DTB3",
    data_dir: Path = Path("data/raw"),
) -> pd.DataFrame:
    """Load a FRED rate Parquet snapshot.

    Returns
    -------
    pandas.DataFrame
        DataFrame with columns ``rate_pct``, ``quality_flag`` and a
        ``DatetimeIndex`` named ``date``. Annualised percentage points
        (e.g. ``5.25`` means 5.25%).
    """
    ...


def load_metadata(parquet_path: Path) -> SnapshotMetadata:
    """Load and validate the metadata sidecar for a Parquet file.

    Looks for ``<parquet_path>.meta.json``. Validates against the JSON Schema
    in ``contracts/snapshot-metadata.schema.json`` before parsing.

    Raises
    ------
    FileNotFoundError
        If the sidecar metadata file does not exist.
    ValueError
        If the metadata fails JSON Schema validation.
    """
    ...


def verify_snapshot(parquet_path: Path) -> VerifyResult:
    """Verify a single Parquet against its metadata sidecar.

    Recomputes SHA-256 over the Parquet bytes, validates the metadata JSON
    Schema, and cross-checks ``row_count`` / ``column_schema`` against the
    actual Parquet content.

    Returns
    -------
    VerifyResult
        Result object whose ``.ok`` is True iff all checks passed.
    """
    ...


def verify_all(data_dir: Path = Path("data/raw")) -> tuple[VerifyResult, ...]:
    """Verify every snapshot in ``data_dir``.

    Returns one ``VerifyResult`` per Parquet found. Order is sorted by filename
    for deterministic CI output.
    """
    ...


# ---------------------------------------------------------------------------
# Public symbol surface
# ---------------------------------------------------------------------------


__all__ = [
    "IngestionConfig",
    "ColumnSchema",
    "IndexSchema",
    "TimeRange",
    "QualitySummary",
    "SnapshotMetadata",
    "VerifyResult",
    "load_asset_snapshot",
    "load_rate_snapshot",
    "load_metadata",
    "verify_snapshot",
    "verify_all",
]
