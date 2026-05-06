"""Shared fixtures for 005-inference-service unit tests.

T009 在 Phase 2 把 ``policy_path`` / ``data_root`` 改成實值；目前 skeleton。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_POLICY_RUN = "20260506_004455_659b8eb_seed42"


@pytest.fixture
def policy_path() -> Path:
    """指向 repo 內 default policy。Phase 2 T009 接到 tiny_policy_run。"""
    p = _REPO_ROOT / "runs" / _DEFAULT_POLICY_RUN / "final_policy.zip"
    if not p.exists():
        pytest.skip(f"policy fixture not available: {p}")
    return p


@pytest.fixture
def data_root() -> Path:
    """指向 repo 內 data/raw。"""
    p = _REPO_ROOT / "data" / "raw"
    if not p.exists() or not list(p.glob("*.parquet")):
        pytest.skip(f"data_root fixture not available: {p}")
    return p


@pytest.fixture
def fake_payload_dict() -> dict[str, Any]:
    """A canonical PredictionPayload dict（與 integration conftest 對齊）."""
    return {
        "as_of_date": "2026-04-28",
        "next_trading_day_target": "first session after 2026-04-28 (apply at next open)",
        "policy_path": "fake.zip",
        "deterministic": True,
        "target_weights": {
            "NVDA": 0.1,
            "AMD": 0.1,
            "TSM": 0.1,
            "MU": 0.1,
            "GLD": 0.1,
            "TLT": 0.1,
            "CASH": 0.4,
        },
        "weights_capped": False,
        "renormalized": False,
        "context": {
            "data_root": "data/raw",
            "include_smc": True,
            "n_warmup_steps": 100,
            "current_nav_at_as_of": 1.0,
        },
        "triggered_by": "manual",
        "inference_id": "00000000-0000-0000-0000-000000000000",
        "inferred_at_utc": "2026-05-06T00:00:00+00:00",
    }
