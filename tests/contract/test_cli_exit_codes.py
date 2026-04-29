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
