"""Data ingestion package — feature 002.

Public surface mirrors `specs/002-data-ingestion/contracts/api.pyi`. Functions
with full implementations live in dedicated modules; ones still pending in
later phases of tasks.md raise NotImplementedError so the import surface is
stable for downstream features (001, 003) and contract tests can run today.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Mapping, Optional

import pandas as pd

from .config import IngestionConfig

__version__ = "0.1.0"


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
    start: str
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
    message: str

    @property
    def ok(self) -> bool:
        return self.sha256_match and self.row_count_match and self.schema_match


# ---------------------------------------------------------------------------
# Public functions — implementations land in Phase 3 / Phase 6 of tasks.md
# ---------------------------------------------------------------------------


def load_asset_snapshot(
    ticker: str,
    data_dir: Path = Path("data/raw"),
) -> pd.DataFrame:
    raise NotImplementedError("load_asset_snapshot lands in Phase 6 (T041-T046)")


def load_rate_snapshot(
    series_id: str = "DTB3",
    data_dir: Path = Path("data/raw"),
) -> pd.DataFrame:
    raise NotImplementedError("load_rate_snapshot lands in Phase 6 (T041-T046)")


def load_metadata(parquet_path: Path) -> SnapshotMetadata:
    raise NotImplementedError("load_metadata lands in Phase 4 (T030-T036)")


def verify_snapshot(parquet_path: Path) -> VerifyResult:
    raise NotImplementedError("verify_snapshot lands in Phase 4 (T030-T036)")


def verify_all(data_dir: Path = Path("data/raw")) -> tuple[VerifyResult, ...]:
    raise NotImplementedError("verify_all lands in Phase 4 (T030-T036)")


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
