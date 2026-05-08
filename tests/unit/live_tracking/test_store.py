"""T007 — LiveTrackingStore: load / atomic_write / append-only invariant.

對應 spec 010 FR-001 / FR-003 / FR-009、data-model §1、INV-2 / INV-3。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from inference_service.episode_schemas import (
    EpisodeDetail,
)
from live_tracking.store import LiveTrackingStore


def _read_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def tracking_dir(tmp_path: Path) -> Path:
    d = tmp_path / "live_tracking"
    d.mkdir()
    return d


@pytest.fixture
def empty_envelope() -> EpisodeDetail:
    """A minimal valid EpisodeDetail with zero frames (for invariant tests)."""
    return EpisodeDetail.model_validate(
        {
            "summary": {
                "id": "test_live",
                "policyId": "test_policy",
                "startDate": "2026-04-29",
                "endDate": "2026-04-29",
                "nSteps": 1,
                "initialNav": 1.7291986,
                "finalNav": 1.7291986,
                "cumulativeReturnPct": 0.0,
                "annualizedReturnPct": 0.0,
                "maxDrawdownPct": 0.0,
                "sharpeRatio": 0.0,
                "sortinoRatio": 0.0,
                "includeSmc": True,
            },
            "trajectoryInline": [],
            "rewardBreakdown": {"byStep": [], "cumulative": []},
            "smcOverlayByAsset": {},
        }
    )


def _make_envelope_with_n_frames(n: int) -> EpisodeDetail:
    frames = [
        {
            "timestamp": f"2026-04-{29 + i:02d}T00:00:00Z",
            "step": i,
            "weights": {"riskOn": 0.4, "riskOff": 0.4, "cash": 0.2, "perAsset": {}},
            "nav": 1.7291986 * (1 + i * 0.001),
            "drawdownPct": 0.0,
            "reward": {
                "total": 0.001,
                "returnComponent": 0.001,
                "drawdownPenalty": 0.0,
                "costPenalty": 0.0,
            },
            "smcSignals": {
                "bos": 0,
                "choch": 0,
                "fvgDistancePct": None,
                "obTouching": False,
                "obDistanceRatio": None,
            },
            "ohlcv": {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1.0},
            "ohlcvByAsset": {},
            "action": {
                "raw": [0.1] * 7,
                "normalized": [0.14] * 7,
                "logProb": -1.0,
                "entropy": 0.5,
            },
        }
        for i in range(n)
    ]
    cumulative = [
        {
            "step": i + 1,
            "cumulativeTotal": 0.001 * (i + 1),
            "cumulativeReturn": 0.001 * (i + 1),
            "cumulativeDrawdownPenalty": 0.0,
            "cumulativeCostPenalty": 0.0,
        }
        for i in range(n)
    ]
    return EpisodeDetail.model_validate(
        {
            "summary": {
                "id": "test_live",
                "policyId": "test_policy",
                "startDate": "2026-04-29",
                "endDate": f"2026-04-{29 + max(n - 1, 0):02d}",
                "nSteps": max(n, 1),
                "initialNav": 1.7291986,
                "finalNav": 1.7291986 * (1 + (n - 1) * 0.001) if n > 0 else 1.7291986,
                "cumulativeReturnPct": 0.0,
                "annualizedReturnPct": 0.0,
                "maxDrawdownPct": 0.0,
                "sharpeRatio": 0.0,
                "sortinoRatio": 0.0,
                "includeSmc": True,
            },
            "trajectoryInline": frames,
            "rewardBreakdown": {
                "byStep": [f["reward"] for f in frames],
                "cumulative": cumulative,
            },
            "smcOverlayByAsset": {},
        }
    )


class TestLoadAbsent:
    def test_load_returns_none_when_file_absent(self, tracking_dir: Path) -> None:
        store = LiveTrackingStore(tracking_dir / "live_tracking.json")
        assert store.load() is None


class TestAtomicWriteRoundTrip:
    def test_write_then_load_byte_equal(
        self, tracking_dir: Path, empty_envelope: EpisodeDetail
    ) -> None:
        path = tracking_dir / "live_tracking.json"
        store = LiveTrackingStore(path)
        store.atomic_write(empty_envelope)
        assert path.exists()
        loaded = store.load()
        assert loaded is not None
        assert loaded == empty_envelope


class TestAtomicWriteRollback:
    def test_existing_file_unchanged_when_replace_fails(
        self, tracking_dir: Path, empty_envelope: EpisodeDetail
    ) -> None:
        path = tracking_dir / "live_tracking.json"
        store = LiveTrackingStore(path)
        # Write 1: 落第一版
        store.atomic_write(empty_envelope)
        original_sha = _read_sha256(path)

        # Write 2: 注入錯誤 → 既有檔案不變 (INV-2 / FR-009 / SC-005)
        new_envelope = _make_envelope_with_n_frames(3)
        with (
            patch("os.replace", side_effect=OSError("simulated disk failure")),
            pytest.raises(OSError, match="simulated"),
        ):
            store.atomic_write(new_envelope)

        assert _read_sha256(path) == original_sha
        # Confirm content is still the empty envelope
        loaded = store.load()
        assert loaded == empty_envelope


class TestAppendOnlyInvariant:
    """INV-3: 連續兩次 atomic_write，第二次的 trajectoryInline[:k] 必須與第一次相同."""

    def test_first_n_frames_byte_equal_across_writes(self, tracking_dir: Path) -> None:
        path = tracking_dir / "live_tracking.json"
        store = LiveTrackingStore(path)

        first = _make_envelope_with_n_frames(2)
        store.atomic_write(first)
        loaded_first = store.load()
        assert loaded_first is not None

        second = _make_envelope_with_n_frames(5)
        # Important: 前 2 frames 必須與 first 完全相同（pipeline 不可改寫歷史）
        for i in range(2):
            assert (
                second.trajectoryInline[i].model_dump()
                == first.trajectoryInline[i].model_dump()
            )
        store.atomic_write(second)

        loaded_second = store.load()
        assert loaded_second is not None
        # Re-affirm: load 後前 2 frame 仍相等
        for i in range(2):
            assert (
                loaded_second.trajectoryInline[i].model_dump()
                == loaded_first.trajectoryInline[i].model_dump()
            )


class TestSerializationStability:
    def test_write_produces_pretty_json(
        self, tracking_dir: Path, empty_envelope: EpisodeDetail
    ) -> None:
        path = tracking_dir / "live_tracking.json"
        store = LiveTrackingStore(path)
        store.atomic_write(empty_envelope)
        text = path.read_text(encoding="utf-8")
        # Sanity: JSON parses
        parsed = json.loads(text)
        assert "summary" in parsed
        # newline at EOF
        assert text.endswith("\n")
