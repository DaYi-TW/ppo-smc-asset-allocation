"""SC-006 / FR-021 — 錯誤訊息可直接判讀，含足夠上下文供修復。

驗證三種典型錯誤的 stderr 訊息：
  1. yfinance symbol 退市 / 空回應 — 訊息含 ticker + 修復提示
  2. FRED_API_KEY 未設定 — 訊息含環境變數名 + 註冊網址
  3. FRED 序列不存在 / 空回應 — 訊息含 series_id

不依賴網路：透過 monkeypatch 替換 fetcher 模組層的下游 fetch 函式，模擬各
種錯誤條件。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from data_ingestion import cli, fetcher
from data_ingestion.sources.fred_source import (
    FredApiKeyMissingError,
    FredFetchError,
)
from data_ingestion.sources.yfinance_source import YfinanceFetchError
from tests.integration.test_atomic_fetch import (  # type: ignore[import-not-found]
    fake_asset_fetcher,
    fake_rate_fetcher,
)

# ---------------------------------------------------------------------------
# 1. yfinance: ticker 退市 / 空回應
# ---------------------------------------------------------------------------


def _delisted_asset_fetcher(ticker, start, end, **_):
    if ticker == "TSM":
        raise YfinanceFetchError(
            f"yfinance returned empty DataFrame for {ticker!r} "
            f"(start={start}, end={end}); ticker may be delisted "
            "or temporarily unavailable."
        )
    return fake_asset_fetcher(ticker, start, end)


def test_yfinance_delisted_message_has_ticker_and_repair_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    """SC-006：退市訊息必須含 ticker 名與「可能退市」修復提示。"""
    original = fetcher.fetch_all

    def _patched(
        config,
        *,
        asset_fetcher=_delisted_asset_fetcher,
        rate_fetcher=fake_rate_fetcher,
        progress=lambda _: None,
    ):
        return original(
            config,
            asset_fetcher=asset_fetcher,
            rate_fetcher=rate_fetcher,
            progress=progress,
        )

    monkeypatch.setattr(fetcher, "fetch_all", _patched)
    monkeypatch.setattr(cli, "fetch_all", _patched)

    rc = cli.main(
        [
            "--output-dir",
            str(tmp_path),
            "fetch",
            "--start",
            "2024-01-02",
            "--end",
            "2024-01-12",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 1
    # 必須含 ticker 名（caller 才能定位）
    assert "TSM" in captured.err or "'TSM'" in captured.err
    # 必須含修復提示（不可只是 stack trace）
    assert "delisted" in captured.err.lower() or "unavailable" in captured.err.lower()
    # 必須含「舊資料未受影響」的承諾（FR-018）
    assert "data/raw/" in captured.err or "unchanged" in captured.err.lower()


# ---------------------------------------------------------------------------
# 2. FRED_API_KEY 未設定
# ---------------------------------------------------------------------------


def _missing_key_rate_fetcher(series_id, start, end, **_):
    raise FredApiKeyMissingError()


def test_fred_api_key_missing_message_has_env_var_and_registration_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    """FR-021：缺 FRED_API_KEY 時訊息必須指引註冊流程。"""
    original = fetcher.fetch_all

    def _patched(
        config,
        *,
        asset_fetcher=fake_asset_fetcher,
        rate_fetcher=_missing_key_rate_fetcher,
        progress=lambda _: None,
    ):
        return original(
            config,
            asset_fetcher=asset_fetcher,
            rate_fetcher=rate_fetcher,
            progress=progress,
        )

    monkeypatch.setattr(fetcher, "fetch_all", _patched)
    monkeypatch.setattr(cli, "fetch_all", _patched)

    rc = cli.main(
        [
            "--output-dir",
            str(tmp_path),
            "fetch",
            "--start",
            "2024-01-02",
            "--end",
            "2024-01-12",
        ]
    )
    captured = capsys.readouterr()

    # 缺 key 屬 config 錯誤 → exit 2
    assert rc == 2
    # 必須含環境變數名
    assert "FRED_API_KEY" in captured.err
    # 必須含 FRED 註冊網址（讓使用者知道要去哪取得 key）
    assert "fred.stlouisfed.org" in captured.err


# ---------------------------------------------------------------------------
# 3. FRED 序列不存在 / 空回應
# ---------------------------------------------------------------------------


def _bad_series_rate_fetcher(series_id, start, end, **_):
    raise FredFetchError(
        f"FRED returned empty series for {series_id!r} "
        f"({start} → {end}); check the series_id is valid."
    )


def test_fred_invalid_series_message_has_series_id_and_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    """SC-006：FRED series_id 錯誤訊息必須含 series_id + 修復提示。"""
    original = fetcher.fetch_all

    def _patched(
        config,
        *,
        asset_fetcher=fake_asset_fetcher,
        rate_fetcher=_bad_series_rate_fetcher,
        progress=lambda _: None,
    ):
        return original(
            config,
            asset_fetcher=asset_fetcher,
            rate_fetcher=rate_fetcher,
            progress=progress,
        )

    monkeypatch.setattr(fetcher, "fetch_all", _patched)
    monkeypatch.setattr(cli, "fetch_all", _patched)

    rc = cli.main(
        [
            "--output-dir",
            str(tmp_path),
            "fetch",
            "--start",
            "2024-01-02",
            "--end",
            "2024-01-12",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 1
    assert "DTB3" in captured.err
    assert "series_id" in captured.err.lower() or "valid" in captured.err.lower()
    assert "data/raw/" in captured.err or "unchanged" in captured.err.lower()


# ---------------------------------------------------------------------------
# 4. 任一失敗訊息「不僅是 stack trace」
# ---------------------------------------------------------------------------


def test_error_messages_are_not_raw_stack_traces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    """FR-021：錯誤訊息不應僅呈現 stack trace（無 'Traceback' 字樣）。"""
    original = fetcher.fetch_all

    def _patched(
        config,
        *,
        asset_fetcher=_delisted_asset_fetcher,
        rate_fetcher=fake_rate_fetcher,
        progress=lambda _: None,
    ):
        return original(
            config,
            asset_fetcher=asset_fetcher,
            rate_fetcher=rate_fetcher,
            progress=progress,
        )

    monkeypatch.setattr(fetcher, "fetch_all", _patched)
    monkeypatch.setattr(cli, "fetch_all", _patched)

    rc = cli.main(
        [
            "--output-dir",
            str(tmp_path),
            "fetch",
            "--start",
            "2024-01-02",
            "--end",
            "2024-01-12",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 1
    # CLI 不應 leak Python traceback 結構
    assert "Traceback (most recent call last)" not in captured.err
    assert 'File "' not in captured.err
