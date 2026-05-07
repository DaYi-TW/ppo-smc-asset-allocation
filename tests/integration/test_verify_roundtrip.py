"""SC-002：fetch → verify roundtrip。

正常路徑全綠；對任一 Parquet 末尾追加 1 byte 後，verify 應指出該檔名 +
expected/actual sha256；缺檔情境亦覆蓋（FR-016）。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from data_ingestion import verify_all, verify_snapshot


def test_clean_dir_all_ok(tmp_data_dir: Path):
    results = verify_all(tmp_data_dir)
    assert len(results) == 2  # NVDA + DTB3
    assert all(r.ok for r in results), [r.message for r in results]
    assert all(r.message == "OK" for r in results)


def test_byte_tampering_detected(tmp_data_dir: Path):
    """末尾追加 1 byte 後，sha256 必須不符且訊息含 expected/actual。"""
    nvda = tmp_data_dir / "nvda_daily_20240102_20240115.parquet"
    original = nvda.read_bytes()
    nvda.write_bytes(original + b"\x00")

    result = verify_snapshot(nvda)
    assert not result.ok
    assert not result.sha256_match
    assert result.expected_sha256 != result.actual_sha256
    assert "sha256 mismatch" in result.message


def test_missing_parquet_detected(tmp_data_dir: Path):
    nvda = tmp_data_dir / "nvda_daily_20240102_20240115.parquet"
    nvda.unlink()

    result = verify_snapshot(nvda)
    assert not result.ok
    assert "MISSING" in result.message
    assert "nvda" in result.message


def test_missing_metadata_sidecar_detected(tmp_data_dir: Path):
    meta = tmp_data_dir / "nvda_daily_20240102_20240115.parquet.meta.json"
    meta.unlink()

    nvda = tmp_data_dir / "nvda_daily_20240102_20240115.parquet"
    result = verify_snapshot(nvda)
    assert not result.ok
    assert "MISSING" in result.message
    assert "meta.json" in result.message


def test_verify_all_data_dir_missing_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        verify_all(tmp_path / "does-not-exist")


def test_verify_all_returns_sorted_results(tmp_data_dir: Path):
    results = verify_all(tmp_data_dir)
    names = [r.parquet_path.name for r in results]
    assert names == sorted(names)


# ---------------------------------------------------------------------------
# CLI-level exit code matrix（透過 subprocess 跑真正的 argparse 流程）
# ---------------------------------------------------------------------------


def _run_cli(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "data_ingestion.cli", *argv],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_verify_clean_dir_exits_zero(tmp_data_dir: Path):
    result = _run_cli("--output-dir", str(tmp_data_dir), "verify")
    assert result.returncode == 0, result.stderr
    assert "All 2 snapshots verified successfully" in result.stdout


def test_cli_verify_tampered_exits_one(tmp_data_dir: Path):
    nvda = tmp_data_dir / "nvda_daily_20240102_20240115.parquet"
    nvda.write_bytes(nvda.read_bytes() + b"\x00")

    result = _run_cli("--output-dir", str(tmp_data_dir), "verify")
    assert result.returncode == 1, result.stdout
    assert "nvda_daily_20240102_20240115.parquet" in result.stdout
    assert "FAIL" in result.stdout


def test_cli_verify_strict_unexpected_exits_three(tmp_data_dir: Path):
    """合規快照 + 額外非預期 prefix（SPY） → strict 模式 exit 3。"""
    # 複製一份合規 nvda 快照作為「合規但 prefix 不在預期清單」的檔案
    src_pq = tmp_data_dir / "nvda_daily_20240102_20240115.parquet"
    src_meta = src_pq.with_suffix(src_pq.suffix + ".meta.json")
    rogue_pq = tmp_data_dir / "spy_daily_20240102_20240115.parquet"
    rogue_meta = rogue_pq.with_suffix(rogue_pq.suffix + ".meta.json")
    shutil.copy2(src_pq, rogue_pq)
    shutil.copy2(src_meta, rogue_meta)

    # 非 strict 應仍 exit 0（spy 合規 + 預期清單外不影響）
    result_lax = _run_cli("--output-dir", str(tmp_data_dir), "verify")
    assert result_lax.returncode == 0, result_lax.stdout

    # strict 應 exit 3 並列出 spy
    result_strict = _run_cli("--output-dir", str(tmp_data_dir), "verify", "--strict")
    assert result_strict.returncode == 3, result_strict.stdout
    assert "spy_daily_20240102_20240115.parquet" in result_strict.stdout
    assert "UNEXPECTED" in result_strict.stdout
