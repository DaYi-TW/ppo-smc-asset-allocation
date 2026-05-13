"""T012 — DailyTrackerPipeline orchestration unit tests.

對應 spec 010 FR-007 / FR-008 / FR-009 / FR-010 / FR-011 / SC-002 / SC-005
和 data-model §3。

Strategy: stub the ``FrameBuilder`` callback so we exercise pipeline state
transitions / error classification / append-only invariant without touching
real OHLCV / policy / SMC compute.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from inference_service.episode_schemas import EpisodeDetail
from live_tracking.pipeline import (
    DailyTrackerPipeline,
    DataFetchError,
    InferenceError,
    PipelineResult,
    RefreshInProgressError,
)
from live_tracking.status import LiveTrackingStatus
from live_tracking.store import LiveTrackingStore


def _envelope_with_n_frames(n: int) -> EpisodeDetail:
    """Build EpisodeDetail with n frames starting at 2026-04-29."""
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


def _make_pipeline(
    store_paths: tuple[Path, Path],
    builder,
) -> DailyTrackerPipeline:
    artefact_path, status_path = store_paths
    return DailyTrackerPipeline(
        store=LiveTrackingStore(artefact_path),
        status_path=status_path,
        build_frames=builder,
        initial_nav=1.7291986,
        start_anchor=date(2026, 4, 29),
        policy_run_id="test_policy",
    )


class TestNoOpEarlyReturn:
    """FR-008：last_frame_date == today → frames_appended == 0。"""

    def test_noop_returns_zero_frames(self, store_paths) -> None:
        _, status_path = store_paths
        # Seed status: last_frame_date already today
        s = LiveTrackingStatus(
            last_frame_date=date(2026, 5, 8), is_running=False
        )
        s.write(status_path)

        def _builder_should_not_be_called(**_kwargs):
            raise AssertionError("builder must not be invoked when no missing days")

        pipeline = _make_pipeline(store_paths, _builder_should_not_be_called)
        result = pipeline.run_once(date(2026, 5, 8), pipeline_id="pid1")

        assert isinstance(result, PipelineResult)
        assert result.frames_appended == 0
        assert result.final_status == "noop"
        # Status reflects success without changing last_frame_date
        loaded = LiveTrackingStatus.load(status_path)
        assert loaded.is_running is False
        assert loaded.last_frame_date == date(2026, 5, 8)
        assert loaded.last_error is None


class TestSingleDayBackfill:
    def test_one_missing_day_appends_one_frame(self, store_paths) -> None:
        artefact_path, status_path = store_paths
        # Seed status: last_frame_date = 2026-04-28 (so 2026-04-29 is missing)
        s = LiveTrackingStatus(
            last_frame_date=date(2026, 4, 28), is_running=False
        )
        s.write(status_path)

        new_env = _envelope_with_n_frames(1)

        def builder(**kwargs):
            assert kwargs["missing_days"] == [date(2026, 4, 29)]
            assert kwargs["current_envelope"] is None  # store empty
            return new_env

        pipeline = _make_pipeline(store_paths, builder)
        result = pipeline.run_once(date(2026, 4, 29), pipeline_id="pid2")
        assert result.frames_appended == 1
        assert result.final_status == "succeeded"
        assert result.last_frame_date == date(2026, 4, 29)
        assert artefact_path.exists()


class TestMultiDayBackfill:
    """SC-002：日期嚴格遞增、無跳號。"""

    def test_five_missing_days_appends_five_frames(self, store_paths) -> None:
        artefact_path, status_path = store_paths
        s = LiveTrackingStatus(
            last_frame_date=date(2026, 4, 28), is_running=False
        )
        s.write(status_path)

        target = _envelope_with_n_frames(5)

        def builder(**kwargs):
            return target

        pipeline = _make_pipeline(store_paths, builder)
        result = pipeline.run_once(date(2026, 5, 5), pipeline_id="pid3")
        assert result.frames_appended == 5

        loaded = LiveTrackingStore(artefact_path).load()
        assert loaded is not None
        assert len(loaded.trajectoryInline) == 5
        # Strictly increasing dates, no gaps in our fixture
        dates = [f.timestamp[:10] for f in loaded.trajectoryInline]
        assert dates == sorted(dates)
        assert len(set(dates)) == len(dates)


class TestFailureClassification:
    """SC-005 + research §R10：DATA_FETCH / INFERENCE / WRITE 三類錯誤前綴。"""

    def test_data_fetch_error_marks_status_with_prefix(self, store_paths) -> None:
        _, status_path = store_paths
        LiveTrackingStatus(
            last_frame_date=date(2026, 4, 28), is_running=False
        ).write(status_path)

        def builder(**_kwargs):
            raise DataFetchError("yfinance returned empty for NVDA")

        pipeline = _make_pipeline(store_paths, builder)
        with pytest.raises(DataFetchError):
            pipeline.run_once(date(2026, 4, 29), pipeline_id="pid4")

        loaded = LiveTrackingStatus.load(status_path)
        assert loaded.is_running is False
        assert loaded.last_error is not None
        assert loaded.last_error.startswith("DATA_FETCH:")
        # last_frame_date unchanged on failure
        assert loaded.last_frame_date == date(2026, 4, 28)

    def test_unclassified_exception_becomes_inference(self, store_paths) -> None:
        _, status_path = store_paths
        LiveTrackingStatus(
            last_frame_date=date(2026, 4, 28), is_running=False
        ).write(status_path)

        def builder(**_kwargs):
            raise ValueError("env step produced NaN")

        pipeline = _make_pipeline(store_paths, builder)
        with pytest.raises(InferenceError):
            pipeline.run_once(date(2026, 4, 29), pipeline_id="pid5")

        loaded = LiveTrackingStatus.load(status_path)
        assert loaded.last_error is not None
        assert loaded.last_error.startswith("INFERENCE:")


class TestAtomicityOnFailure:
    """FR-009：失敗 → 既有 artefact byte-identical。"""

    def test_existing_artefact_unchanged_when_builder_fails(self, store_paths) -> None:
        artefact_path, status_path = store_paths
        # Seed an artefact at version v1
        v1 = _envelope_with_n_frames(2)
        LiveTrackingStore(artefact_path).atomic_write(v1)
        original_sha = hashlib.sha256(artefact_path.read_bytes()).hexdigest()

        # Status mirrors that state
        LiveTrackingStatus(
            last_frame_date=date(2026, 4, 30), is_running=False
        ).write(status_path)

        def failing_builder(**_kwargs):
            raise RuntimeError("simulated NaN explosion in env")

        pipeline = _make_pipeline(store_paths, failing_builder)
        with pytest.raises(InferenceError):
            pipeline.run_once(date(2026, 5, 1), pipeline_id="pid6")

        # Artefact byte-equal
        assert (
            hashlib.sha256(artefact_path.read_bytes()).hexdigest() == original_sha
        )


class TestSingleFlightGuard:
    def test_run_once_raises_when_already_running(self, store_paths) -> None:
        _, status_path = store_paths
        LiveTrackingStatus(
            is_running=True,
            running_pid=12345,
            running_started_at=datetime(2026, 5, 8, 14, 0, tzinfo=UTC),
        ).write(status_path)

        def builder(**_kwargs):  # pragma: no cover - guard fires first
            raise AssertionError("must not enter")

        pipeline = _make_pipeline(store_paths, builder)
        with pytest.raises(RefreshInProgressError):
            pipeline.run_once(date(2026, 5, 8), pipeline_id="pid7")


class TestAppendOnlyInvariant:
    """INV-3：第二次寫入的前 k frames 必須 byte-equal 第一次。"""

    def test_builder_rewrites_history_is_rejected(self, store_paths) -> None:
        """Mutating frame 0 OHLCV (yfinance drift simulation) MUST fire INV-3."""
        artefact_path, status_path = store_paths
        v1 = _envelope_with_n_frames(2)
        LiveTrackingStore(artefact_path).atomic_write(v1)
        LiveTrackingStatus(
            last_frame_date=date(2026, 4, 30), is_running=False
        ).write(status_path)

        # Build a "v2" that DELIBERATELY rewrites frame 0 — pipeline must
        # catch this and refuse the write. We mutate ``ohlcv.close`` because
        # that's exactly the field yfinance silently changes when it adjusts
        # historical prices for late splits/divs (the real-world failure
        # mode that motivates INV-3).
        v2 = _envelope_with_n_frames(3)
        v2_payload = v2.model_dump()
        v2_payload["trajectoryInline"][0]["ohlcv"]["close"] += 0.5
        v2_bad = EpisodeDetail.model_validate(v2_payload)

        def builder(**_kwargs):
            return v2_bad

        pipeline = _make_pipeline(store_paths, builder)
        with pytest.raises(InferenceError, match="append-only"):
            pipeline.run_once(date(2026, 5, 1), pipeline_id="pid8")

        # Regression：append-only violation 必須走 _fail 路徑、寫入 last_error，
        # 否則前端 status badge 看不到原因，artefact 卡住但 last_error=null。
        loaded = LiveTrackingStatus.load(status_path)
        assert loaded.is_running is False
        assert loaded.last_error is not None
        assert loaded.last_error.startswith("APPEND_ONLY:")
        assert "frame 0" in loaded.last_error

    def test_policy_output_drift_does_not_trigger_violation(
        self, store_paths
    ) -> None:
        """NAV / reward / action 的 float-noise drift 不應觸發 INV-3。

        2026-05-13 incident：cuDNN nondeterminism 讓 model.predict 的 logits
        每次 rollout 飄 ~1e-7，連帶 action / weights / reward / nav 都飄。
        舊版 _verify_append_only 用 dict equality 嚴格比所有欄位 → 任何 refresh
        都會 false-positive，pipeline 卡住、前端拿 stale data。修正後僅比對
        market data + structural keys，policy output drift 應被視為正常。
        """
        artefact_path, status_path = store_paths
        v1 = _envelope_with_n_frames(2)
        LiveTrackingStore(artefact_path).atomic_write(v1)
        LiveTrackingStatus(
            last_frame_date=date(2026, 4, 30), is_running=False
        ).write(status_path)

        # v2: 與 v1 在 frame 0 的 OHLCV / SMC 完全相同，但 policy 輸出與 NAV 飄一點。
        v2 = _envelope_with_n_frames(3)
        v2_payload = v2.model_dump()
        v2_payload["trajectoryInline"][0]["nav"] += 1e-6
        v2_payload["trajectoryInline"][0]["drawdownPct"] += 1e-8
        v2_payload["trajectoryInline"][0]["reward"]["total"] += 1e-7
        v2_payload["trajectoryInline"][0]["reward"]["returnComponent"] += 1e-8
        v2_payload["trajectoryInline"][0]["action"]["raw"] = [
            x + 1e-7 for x in v2_payload["trajectoryInline"][0]["action"]["raw"]
        ]
        v2_drifted = EpisodeDetail.model_validate(v2_payload)

        def builder(**_kwargs):
            return v2_drifted

        pipeline = _make_pipeline(store_paths, builder)
        # No exception → pipeline accepts the write. last_frame_date advances.
        result = pipeline.run_once(date(2026, 5, 1), pipeline_id="pid8b")
        assert result.final_status == "succeeded"
        loaded = LiveTrackingStatus.load(status_path)
        assert loaded.last_error is None


class TestWriteFailureClassified:
    def test_write_failure_marks_status_write_prefix(
        self, store_paths, monkeypatch
    ) -> None:
        _artefact_path, status_path = store_paths
        LiveTrackingStatus(
            last_frame_date=date(2026, 4, 28), is_running=False
        ).write(status_path)

        new_env = _envelope_with_n_frames(1)

        def builder(**_kwargs):
            return new_env

        pipeline = _make_pipeline(store_paths, builder)
        # Force ``store.atomic_write`` to fail. Patching `os.replace`
        # globally would also break ``LiveTrackingStatus.write`` (which now
        # uses tmp + os.replace for crash-safety), so patch the store method
        # directly — keeps the test isolated to the WRITE-stage failure path.
        def boom(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(pipeline.store, "atomic_write", boom)

        from live_tracking.pipeline import WriteError as _WriteError

        with pytest.raises(_WriteError):
            pipeline.run_once(date(2026, 4, 29), pipeline_id="pid9")

        loaded = LiveTrackingStatus.load(status_path)
        assert loaded.last_error is not None
        assert loaded.last_error.startswith("WRITE:")
        assert loaded.is_running is False
