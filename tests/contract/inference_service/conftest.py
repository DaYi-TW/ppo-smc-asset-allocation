"""Shared fixtures for 005-inference-service contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_POLICY_RUN = "20260506_004455_659b8eb_seed42"


@pytest.fixture
def policy_path() -> Path:
    p = _REPO_ROOT / "runs" / _DEFAULT_POLICY_RUN / "final_policy.zip"
    if not p.exists():
        pytest.skip(f"policy fixture not available: {p}")
    return p


@pytest.fixture
def data_root() -> Path:
    p = _REPO_ROOT / "data" / "raw"
    if not p.exists() or not list(p.glob("*.parquet")):
        pytest.skip(f"data_root fixture not available: {p}")
    return p
