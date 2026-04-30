"""rebuild 原子性 — 中途失敗保留舊版（spec User Story 3 Acceptance Scenario 2）。

策略：先用 fetch_all + 假 fetcher 落地一次「舊版」；接著呼叫 cli.main(['rebuild',
'--yes', ...]) 並 monkeypatch fetcher 模組讓第三檔失敗，斷言 data/raw/ 仍是
舊版（檔名 / sha256 byte-identical）、無殘留 staging。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from data_ingestion import cli, fetcher
from data_ingestion.fetcher import fetch_all
from tests.integration.test_atomic_fetch import (  # type: ignore[import-not-found]
    _make_config,
    fake_asset_fetcher,
    fake_rate_fetcher,
    make_failing_asset_fetcher,
)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture
def seeded_data_dir(tmp_path: Path) -> Path:
    """在 tmp_path 中先以假 fetcher 落地一次完整的 7 個快照作為「舊版」。"""
    cfg = _make_config(tmp_path)
    fetch_all(cfg, asset_fetcher=fake_asset_fetcher, rate_fetcher=fake_rate_fetcher)
    return tmp_path


def test_rebuild_failure_preserves_old_snapshots(
    seeded_data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    """rebuild 中途第三檔失敗時，舊版必須 byte-identical 保留。"""
    before = {p.name: _sha(p) for p in seeded_data_dir.glob("*.parquet")}
    assert len(before) == 7

    failing = make_failing_asset_fetcher("TSM")
    # cli._cmd_rebuild 內部呼叫 fetcher.fetch_all；patch 預設 fetcher
    original_fetch_all = fetcher.fetch_all

    def _patched(config, *, asset_fetcher=failing,
                 rate_fetcher=fake_rate_fetcher, progress=lambda _: None):
        return original_fetch_all(
            config,
            asset_fetcher=asset_fetcher,
            rate_fetcher=rate_fetcher,
            progress=progress,
        )

    monkeypatch.setattr(fetcher, "fetch_all", _patched)
    monkeypatch.setattr(cli, "fetch_all", _patched)

    rc = cli.main([
        "--output-dir", str(seeded_data_dir),
        "rebuild", "--yes",
        "--start", "2024-01-02",
        "--end", "2024-01-12",
    ])
    captured = capsys.readouterr()
    assert rc == 1, f"stdout:\n{captured.out}\nstderr:\n{captured.err}"
    assert "Existing snapshots have been preserved" in captured.err

    after = {p.name: _sha(p) for p in seeded_data_dir.glob("*.parquet")}
    assert after == before
    # 無 staging 殘留
    assert list(seeded_data_dir.glob(".staging-*")) == []


def test_rebuild_success_overwrites_with_new_range(
    seeded_data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    """rebuild --start / --end 變更後，新版 metadata 須含新範圍。"""
    import json

    # 確認舊版 metadata 中的 start
    old_meta_path = next(seeded_data_dir.glob("nvda_*.parquet.meta.json"))
    old_meta = json.loads(old_meta_path.read_text(encoding="utf-8"))
    old_start = old_meta["data_source_call_params"]["start"]
    assert old_start == "2024-01-02"

    # patch fetcher.fetch_all 走假 fetcher
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

    rc = cli.main([
        "--output-dir", str(seeded_data_dir),
        "rebuild", "--yes",
        "--start", "2024-01-03",
        "--end", "2024-01-12",
    ])
    captured = capsys.readouterr()
    assert rc == 0, f"stdout:\n{captured.out}\nstderr:\n{captured.err}"

    # 舊檔名（20240102 起）必須消失，新檔名（20240103 起）必須存在
    old_pq = seeded_data_dir / "nvda_daily_20240102_20240112.parquet"
    new_pq = seeded_data_dir / "nvda_daily_20240103_20240112.parquet"
    assert not old_pq.exists(), "rebuild should remove obsolete snapshot"
    assert new_pq.exists()

    # 新版 metadata 的 start 應為 2024-01-03
    new_meta_path = new_pq.with_suffix(new_pq.suffix + ".meta.json")
    new_meta = json.loads(new_meta_path.read_text(encoding="utf-8"))
    assert new_meta["data_source_call_params"]["start"] == "2024-01-03"

    # 仍是 7 個快照（不能多也不能少）
    assert len(list(seeded_data_dir.glob("*.parquet"))) == 7
    assert len(list(seeded_data_dir.glob("*.parquet.meta.json"))) == 7


def test_rebuild_no_yes_with_n_aborts(
    seeded_data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    """無 --yes 時，stdin 餵 'n' → exit 0 不執行 fetch。"""
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("n\n"))

    # 確保 fetcher 沒被呼叫：如果被呼叫會走真 yfinance 並失敗
    rc = cli.main([
        "--output-dir", str(seeded_data_dir),
        "rebuild",
        "--start", "2024-01-02",
        "--end", "2024-01-12",
    ])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "Aborted by user" in captured.out
