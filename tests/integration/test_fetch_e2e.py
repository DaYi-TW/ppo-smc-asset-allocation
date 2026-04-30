"""E2E：以 monkeypatch 注入假 fetcher 後執行 cli.main(['fetch', ...])，
驗證 14 個檔案落地、退出代碼 0、列數合理、metadata 通過 JSON Schema 驗證。

不錄真實 yfinance/FRED VCR cassette — 留待 Polish phase 真要 commit data/raw 時。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from data_ingestion import cli, fetcher
from tests.integration.test_atomic_fetch import (  # type: ignore[import-not-found]
    fake_asset_fetcher,
    fake_rate_fetcher,
)


@pytest.fixture
def patched_fetchers(monkeypatch: pytest.MonkeyPatch):
    """讓 fetcher.fetch_all 預設使用假 fetcher（CLI 會以預設值呼叫 fetch_all）。"""
    monkeypatch.setattr(fetcher, "fetch_yfinance", fake_asset_fetcher)
    monkeypatch.setattr(fetcher, "fetch_fred", fake_rate_fetcher)
    # 重新繫結 fetch_all 的預設參數（fetch_all 在 import 時凍結了預設）
    original_fetch_all = fetcher.fetch_all

    def _patched(config, *, asset_fetcher=fake_asset_fetcher,
                 rate_fetcher=fake_rate_fetcher, progress=lambda _: None):
        return original_fetch_all(
            config,
            asset_fetcher=asset_fetcher,
            rate_fetcher=rate_fetcher,
            progress=progress,
        )

    monkeypatch.setattr(fetcher, "fetch_all", _patched)
    monkeypatch.setattr(cli, "fetch_all", _patched)
    yield


def test_cli_fetch_full_run(tmp_path: Path, patched_fetchers, capsys):
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
    assert rc == 0, f"stdout:\n{captured.out}\nstderr:\n{captured.err}"

    parquet_files = sorted(tmp_path.glob("*.parquet"))
    meta_files = sorted(tmp_path.glob("*.parquet.meta.json"))
    assert len(parquet_files) == 7, [p.name for p in parquet_files]
    assert len(meta_files) == 7

    # 檔名規約：<lower>_daily_<startYYYYMMDD>_<endYYYYMMDD>.parquet
    expected_prefixes = {"nvda", "amd", "tsm", "mu", "gld", "tlt", "dtb3"}
    actual_prefixes = {p.name.split("_")[0] for p in parquet_files}
    assert actual_prefixes == expected_prefixes


def test_cli_dry_run_makes_no_files(tmp_path: Path, patched_fetchers, capsys):
    rc = cli.main(
        [
            "--output-dir",
            str(tmp_path),
            "fetch",
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "dry-run OK" in captured.out
    assert list(tmp_path.glob("*.parquet")) == []


def test_cli_fetch_metadata_passes_schema(tmp_path: Path, patched_fetchers):
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
    assert rc == 0
    meta_files = list(tmp_path.glob("*.parquet.meta.json"))
    for mf in meta_files:
        payload = json.loads(mf.read_text(encoding="utf-8"))
        assert payload["schema_version"] == "1.0"
        assert payload["row_count"] > 0
        assert len(payload["sha256"]) == 64


def test_cli_invalid_start_date_returns_config_error(
    tmp_path: Path, patched_fetchers, capsys
):
    rc = cli.main(
        [
            "--output-dir",
            str(tmp_path),
            "fetch",
            "--start",
            "not-a-date",
            "--end",
            "2024-01-12",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 2
    assert "invalid configuration" in captured.err.lower()


def test_cli_no_subcommand_prints_help_exit_zero(capsys):
    rc = cli.main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "fetch" in captured.out
