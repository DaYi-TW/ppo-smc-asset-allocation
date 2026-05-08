"""T048 / T059 — Constitution Principle I gate (Live scope, NON-NEGOTIABLE).

對應 spec 010 FR-003 + INV-3 (data-model §3) + constitution.md Principle I：

> Live ``live_tracking.json`` 是 mutable artefact（**不**要求 byte-identical
> sha256），但 **append-only** invariant 必須鐵打：第 N+1 次寫入的
> ``trajectoryInline[:k]`` 必須與第 N 次寫入完全一致（k = 第 N 次的 frame
> 數）。任何重寫歷史的 builder 都必須被 ``DailyTrackerPipeline`` 的
> ``_verify_append_only`` 攔下並 raise InferenceError。

兩條 invariants：
1. **Pipeline-level**：給一個鏡像式 builder（前 k frame 與既有 store 完全
   一致 + 新增 frame）→ pipeline 接受並寫入。
2. **Pipeline-level（reject path）**：給一個改寫第 0 frame 的 builder
   → pipeline 必 raise + 既有 artefact byte-equal。

這條 gate 與 ``tests/unit/live_tracking/test_pipeline.py::TestAppendOnlyInvariant``
的 reject 路徑重疊，但獨立分檔以利 CI ``-m "contract and live_tracking"``
selective run（plan Phase 6）。
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pytest

from inference_service.episode_schemas import EpisodeDetail
from live_tracking.pipeline import DailyTrackerPipeline, InferenceError
from live_tracking.status import LiveTrackingStatus
from live_tracking.store import LiveTrackingStore


def _envelope_with_n_frames(n: int) -> EpisodeDetail:
    """Minimal valid EpisodeDetail with n strictly-increasing frames。"""
    frames = [
        {
            "timestamp": f"2026-04-{29 + i:02d}T00:00:00Z",
            "step": i,
            "weights": {
                "riskOn": 0.4,
                "riskOff": 0.4,
                "cash": 0.2,
                "perAsset": {},
            },
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
            "ohlcv": {
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1.0,
            },
            "ohlcvByAsset": {},
            "action": {
                "raw": [0.1] * 7,
                "normalized": [1 / 7] * 7,
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
                "id": "test_policy_live",
                "policyId": "test_policy",
                "startDate": "2026-04-29",
                "endDate": f"2026-04-{29 + max(n - 1, 0):02d}",
                "nSteps": max(n, 1),
                "initialNav": 1.7291986,
                "finalNav": (
                    1.7291986 * (1 + (n - 1) * 0.001) if n > 0 else 1.7291986
                ),
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


@pytest.fixture
def store_paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "live_tracking.json", tmp_path / "live_tracking_status.json"


def _make_pipeline(store_paths, builder) -> DailyTrackerPipeline:
    artefact_path, status_path = store_paths
    return DailyTrackerPipeline(
        store=LiveTrackingStore(artefact_path),
        status_path=status_path,
        build_frames=builder,
        initial_nav=1.7291986,
        start_anchor=date(2026, 4, 29),
        policy_run_id="test_policy",
    )


class TestAppendOnlyInvariantAccepts:
    """INV-3 happy path：mirror-prefix builder 被接受。"""

    def test_pipeline_accepts_strict_append(self, store_paths) -> None:
        artefact_path, status_path = store_paths
        v1 = _envelope_with_n_frames(2)
        LiveTrackingStore(artefact_path).atomic_write(v1)
        LiveTrackingStatus(
            last_frame_date=date(2026, 4, 30), is_running=False
        ).write(status_path)

        # Builder 必須 mirror 前 2 frames + append 1 frame
        v2 = _envelope_with_n_frames(3)

        def builder(**_kwargs):
            return v2

        pipeline = _make_pipeline(store_paths, builder)
        result = pipeline.run_once(date(2026, 5, 1), pipeline_id="append_ok")
        assert result.frames_appended == 1
        assert result.final_status == "succeeded"


class TestAppendOnlyInvariantRejects:
    """INV-3 reject path：改寫前 k frame 的 builder 必 raise + artefact 不變。"""

    def test_pipeline_rejects_history_rewrite(self, store_paths) -> None:
        artefact_path, status_path = store_paths
        v1 = _envelope_with_n_frames(2)
        LiveTrackingStore(artefact_path).atomic_write(v1)
        original_sha = hashlib.sha256(artefact_path.read_bytes()).hexdigest()
        LiveTrackingStatus(
            last_frame_date=date(2026, 4, 30), is_running=False
        ).write(status_path)

        # Builder 改寫 frame 0 的 NAV — pipeline 必須拒絕
        v2 = _envelope_with_n_frames(3)
        v2_payload = v2.model_dump()
        v2_payload["trajectoryInline"][0]["nav"] = 99.99
        v2_bad = EpisodeDetail.model_validate(v2_payload)

        def builder(**_kwargs):
            return v2_bad

        pipeline = _make_pipeline(store_paths, builder)
        with pytest.raises(InferenceError, match="append-only"):
            pipeline.run_once(date(2026, 5, 1), pipeline_id="append_reject")

        # Artefact 必須與寫入前 byte-equal（FR-009 atomicity）
        assert (
            hashlib.sha256(artefact_path.read_bytes()).hexdigest() == original_sha
        ), "rejected write must not corrupt existing artefact"
