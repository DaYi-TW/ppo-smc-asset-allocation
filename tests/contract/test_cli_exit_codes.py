"""Contract: ppo-smc-data CLI exit-code surface.

Until Phase 3 wires real argparse, the stub must still:
  - exit 0 on `--help`, `-h`, no-args, and `--version`
  - exit non-zero (≠0) on any unimplemented subcommand so CI catches premature use

The signatures here are pinned by spec contracts/cli.md and must not change
without a feature MAJOR bump.
"""

from __future__ import annotations

import subprocess
import sys


def _run(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "data_ingestion.cli", *argv],
        capture_output=True,
        text=True,
        check=False,
    )


def test_no_args_exits_zero() -> None:
    result = _run()
    assert result.returncode == 0, result.stderr


def test_help_long_exits_zero() -> None:
    result = _run("--help")
    assert result.returncode == 0, result.stderr
    assert "ppo-smc-data" in result.stdout


def test_help_short_exits_zero() -> None:
    result = _run("-h")
    assert result.returncode == 0, result.stderr


def test_version_exits_zero_and_prints_semver() -> None:
    result = _run("--version")
    assert result.returncode == 0, result.stderr
    assert "ppo-smc-data" in result.stdout
    parts = result.stdout.strip().split()
    assert len(parts) >= 2
    version = parts[-1]
    segments = version.split(".")
    assert len(segments) == 3, f"version must be MAJOR.MINOR.PATCH, got {version!r}"
    for seg in segments:
        assert seg.isdigit(), f"version segment {seg!r} must be numeric"


def test_unknown_subcommand_exits_nonzero() -> None:
    result = _run("nonsense-subcommand")
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# verify subcommand exit codes (Phase 4 / US2 / contracts/cli.md §verify)
# ---------------------------------------------------------------------------


def test_verify_data_dir_missing_exits_two(tmp_path):
    """data_dir 不存在 → exit 2（EXIT_CONFIG_ERROR）。"""
    missing = tmp_path / "does-not-exist"
    result = _run("--output-dir", str(missing), "verify")
    assert result.returncode == 2, result.stderr


def test_verify_clean_data_dir_exits_zero(tmp_path):
    """空 data_dir：0 個 snapshot，仍 exit 0（vacuously true）。"""
    empty_dir = tmp_path / "raw"
    empty_dir.mkdir()
    result = _run("--output-dir", str(empty_dir), "verify")
    assert result.returncode == 0, result.stderr


def test_verify_strict_flag_is_accepted(tmp_path):
    """`--strict` 旗標必須被 argparse 接受（不拋 unknown argument）。

    精確的 exit-3 語意（合規 snapshot + 額外非預期 parquet）由
    tests/integration/test_verify_roundtrip.py 覆蓋，因為那裡有真正的
    合規 fixture。
    """
    empty_dir = tmp_path / "raw"
    empty_dir.mkdir()
    result = _run("--output-dir", str(empty_dir), "verify", "--strict")
    # 空目錄 + strict 應 exit 0（無快照、無非預期）
    assert result.returncode == 0, result.stderr
