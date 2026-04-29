"""SC-004 / FR-018：整體成功才搬入 data/raw；任一失敗時 staging 清除、舊版完整保留。

策略：用 monkeypatch 在 fetcher 模組層替換 asset_fetcher / rate_fetcher，避免
網路依賴。第三檔抓取拋例外的場景驗證原子性。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from data_ingestion import IngestionConfig
from data_ingestion.fetcher import fetch_all
from data_ingestion.sources.yfinance_source import YfinanceFetchError


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _fake_asset_df(ticker: str, n: int = 6) -> pd.DataFrame:
    idx = pd.date_range("2024-01-02", periods=n, freq="B", name="date")
    rs = np.random.default_rng(seed=hash(ticker) & 0xFFFF)
    close = 100.0 + np.cumsum(rs.normal(0, 1.0, size=n))
    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.5,
            "close": close,
            "volume": rs.integers(1_000_000, 10_000_000, size=n).astype("int64"),
        },
        index=idx,
    )


def _fake_rate_series(n: int = 6) -> pd.Series:
    idx = pd.date_range("2024-01-02", periods=n, freq="B", name="date")
    return pd.Series(np.linspace(5.20, 5.30, n), index=idx, name="rate_pct")


def fake_asset_fetcher(ticker, start, end, **_):
    df = _fake_asset_df(ticker)
    return df, {
        "ticker": ticker,
        "start": start,
        "end": end,
        "auto_adjust": True,
        "interval": "1d",
    }


def fake_rate_fetcher(series_id, start, end, **_):
    s = _fake_rate_series()
    return s, {
        "series_id": series_id,
        "observation_start": start,
        "observation_end": end,
    }


def make_failing_asset_fetcher(fail_on_ticker: str):
    def _fn(ticker, start, end, **_):
        if ticker == fail_on_ticker:
            raise YfinanceFetchError(f"simulated failure on {ticker}")
        return fake_asset_fetcher(ticker, start, end)
    return _fn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path) -> IngestionConfig:
    return IngestionConfig(
        tickers_risk_on=("NVDA", "AMD", "TSM", "MU"),
        tickers_risk_off=("GLD", "TLT"),
        fred_series_id="DTB3",
        start_date="2024-01-02",
        end_date="2024-01-12",
        output_dir=tmp_path,
    )


def test_happy_path_publishes_all_14_files(tmp_path: Path):
    cfg = _make_config(tmp_path)
    snapshots = fetch_all(
        cfg, asset_fetcher=fake_asset_fetcher, rate_fetcher=fake_rate_fetcher
    )
    assert len(snapshots) == 7

    parquet_files = sorted(tmp_path.glob("*.parquet"))
    meta_files = sorted(tmp_path.glob("*.parquet.meta.json"))
    assert len(parquet_files) == 7
    assert len(meta_files) == 7

    # No staging dir leftover
    leftovers = list(tmp_path.glob(".staging-*"))
    assert leftovers == []


def test_failure_mid_fetch_keeps_data_dir_clean(tmp_path: Path):
    cfg = _make_config(tmp_path)
    failing = make_failing_asset_fetcher("TSM")  # 第三檔
    with pytest.raises(YfinanceFetchError, match="TSM"):
        fetch_all(cfg, asset_fetcher=failing, rate_fetcher=fake_rate_fetcher)

    # data/raw/ 應為空（沒有部分檔案）
    assert list(tmp_path.glob("*.parquet")) == []
    assert list(tmp_path.glob("*.parquet.meta.json")) == []
    assert list(tmp_path.glob(".staging-*")) == []


def test_failure_preserves_existing_snapshots(tmp_path: Path):
    """若 data/raw 已有舊版本，失敗的重抓必須完全保留舊版。"""
    cfg = _make_config(tmp_path)

    # 第一次成功抓取，落地 7 檔
    fetch_all(cfg, asset_fetcher=fake_asset_fetcher, rate_fetcher=fake_rate_fetcher)
    before = {p.name: p.read_bytes() for p in tmp_path.glob("*.parquet")}
    assert len(before) == 7

    # 第二次第三檔失敗
    failing = make_failing_asset_fetcher("TSM")
    with pytest.raises(YfinanceFetchError):
        fetch_all(cfg, asset_fetcher=failing, rate_fetcher=fake_rate_fetcher)

    # 檔案內容必須與第一次完全一致（byte-identical）
    after = {p.name: p.read_bytes() for p in tmp_path.glob("*.parquet")}
    assert after == before
    assert list(tmp_path.glob(".staging-*")) == []
