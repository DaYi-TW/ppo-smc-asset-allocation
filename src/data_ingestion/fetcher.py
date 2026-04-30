"""Fetch orchestration — 串接 sources → quality → writer → metadata → atomic publish。

CLI 層僅負責參數解析、stdout 格式、退出代碼；本模組封裝所有資料邏輯。
測試（test_atomic_fetch / test_fetch_e2e）藉由 monkeypatch 替換 sources 子模組
中的兩個 fetch 函式，因此本檔案以模組級函式參考為「可注入點」。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from . import IngestionConfig
from .atomic import atomic_publish, staging_scope
from .metadata import build_metadata, utc_now_iso_z, write_metadata_json
from .quality import (
    apply_asset_quality_flags,
    apply_rate_quality_flags,
    summarize_quality_flags,
)
from .sources.fred_source import fetch_fred
from .sources.yfinance_source import fetch_yfinance
from .writer import write_parquet

AssetFetcher = Callable[..., tuple[pd.DataFrame, dict[str, object]]]
RateFetcher = Callable[..., tuple[pd.Series, dict[str, object]]]


@dataclass(frozen=True)
class FetchedSnapshot:
    parquet_path: Path
    metadata_path: Path
    sha256: str
    row_count: int
    quality_summary: dict[str, int]


def _date_compact(d: str) -> str:
    return date.fromisoformat(d).strftime("%Y%m%d")


def _asset_filename(ticker: str, start: str, end: str) -> str:
    return f"{ticker.lower()}_daily_{_date_compact(start)}_{_date_compact(end)}.parquet"


def _rate_filename(series_id: str, start: str, end: str) -> str:
    return f"{series_id.lower()}_daily_{_date_compact(start)}_{_date_compact(end)}.parquet"


def _process_asset(
    ticker: str,
    config: IngestionConfig,
    staging_dir: Path,
    *,
    fetch_fn: AssetFetcher,
    fetch_timestamp_utc: str,
) -> FetchedSnapshot:
    raw, call_params = fetch_fn(
        ticker,
        config.start_date,
        config.end_date,
        auto_adjust=config.auto_adjust,
        interval=config.interval,
        max_attempts=config.max_retry_attempts,
        base_seconds=config.retry_base_seconds,
        multiplier=config.retry_multiplier,
    )
    clean, dup_ts = apply_asset_quality_flags(raw)

    parquet_path = staging_dir / _asset_filename(ticker, config.start_date, config.end_date)
    write_parquet(clean, parquet_path)

    summary = summarize_quality_flags(
        clean["quality_flag"], duplicate_dropped=len(dup_ts)
    )
    actual_start = clean.index.min().strftime("%Y-%m-%d") if len(clean) else config.start_date
    actual_end = clean.index.max().strftime("%Y-%m-%d") if len(clean) else config.end_date
    meta = build_metadata(
        parquet_path=parquet_path,
        data_source="yfinance",
        call_params=call_params,
        time_range=(actual_start, actual_end),
        quality_summary=summary,
        duplicate_dropped_timestamps=dup_ts,
        fetch_timestamp_utc=fetch_timestamp_utc,
    )
    meta_path = write_metadata_json(meta, parquet_path)

    return FetchedSnapshot(
        parquet_path=parquet_path,
        metadata_path=meta_path,
        sha256=meta.sha256,
        row_count=meta.row_count,
        quality_summary=summary,
    )


def _process_rate(
    config: IngestionConfig,
    staging_dir: Path,
    *,
    fetch_fn: RateFetcher,
    fetch_timestamp_utc: str,
) -> FetchedSnapshot:
    series, call_params = fetch_fn(
        config.fred_series_id,
        config.start_date,
        config.end_date,
        max_attempts=config.max_retry_attempts,
        base_seconds=config.retry_base_seconds,
        multiplier=config.retry_multiplier,
    )
    clean, dup_ts = apply_rate_quality_flags(series)

    parquet_path = staging_dir / _rate_filename(
        config.fred_series_id, config.start_date, config.end_date
    )
    write_parquet(clean, parquet_path)

    summary = summarize_quality_flags(
        clean["quality_flag"], duplicate_dropped=len(dup_ts)
    )
    actual_start = clean.index.min().strftime("%Y-%m-%d") if len(clean) else config.start_date
    actual_end = clean.index.max().strftime("%Y-%m-%d") if len(clean) else config.end_date
    meta = build_metadata(
        parquet_path=parquet_path,
        data_source="fred",
        call_params=call_params,
        time_range=(actual_start, actual_end),
        quality_summary=summary,
        duplicate_dropped_timestamps=dup_ts,
        fetch_timestamp_utc=fetch_timestamp_utc,
    )
    meta_path = write_metadata_json(meta, parquet_path)

    return FetchedSnapshot(
        parquet_path=parquet_path,
        metadata_path=meta_path,
        sha256=meta.sha256,
        row_count=meta.row_count,
        quality_summary=summary,
    )


def fetch_all(
    config: IngestionConfig,
    *,
    asset_fetcher: AssetFetcher = fetch_yfinance,
    rate_fetcher: RateFetcher = fetch_fred,
    progress: Callable[[str], None] = lambda _: None,
) -> tuple[FetchedSnapshot, ...]:
    """Run the full 7-snapshot fetch + atomic publish.

    On any single asset/rate failure the staging dir is removed (via
    ``staging_scope``) and the exception propagates — ``data/raw/`` remains
    untouched (FR-018, SC-004).

    The two ``*_fetcher`` parameters exist so tests can inject deterministic
    fakes that produce small DataFrames without network access.
    """
    output_dir = Path(config.output_dir)
    fetch_ts = utc_now_iso_z()
    snapshots: list[FetchedSnapshot] = []
    started = time.perf_counter()

    with staging_scope(output_dir) as staging:
        for ticker in config.all_tickers():
            progress(f"yfinance: {ticker}")
            snap = _process_asset(
                ticker,
                config,
                staging,
                fetch_fn=asset_fetcher,
                fetch_timestamp_utc=fetch_ts,
            )
            snapshots.append(snap)

        progress(f"fred: {config.fred_series_id}")
        snapshots.append(
            _process_rate(
                config, staging, fetch_fn=rate_fetcher, fetch_timestamp_utc=fetch_ts
            )
        )

        # 全部成功 — atomic publish 至 output_dir
        atomic_publish(staging, output_dir)

    # 重新指向 output_dir 中的最終位置（atomic_publish 已搬好）
    finalised: list[FetchedSnapshot] = []
    for snap in snapshots:
        finalised.append(
            FetchedSnapshot(
                parquet_path=output_dir / snap.parquet_path.name,
                metadata_path=output_dir / snap.metadata_path.name,
                sha256=snap.sha256,
                row_count=snap.row_count,
                quality_summary=snap.quality_summary,
            )
        )
    progress(f"All {len(finalised)} snapshots written in {time.perf_counter()-started:.1f}s")
    return tuple(finalised)
