"""T053 — Phase 5 (US3) error classification unit test (R7 / FR-010).

對應 spec 010 FR-010 (status.last_error 三段式 prefix) + research §R10：

    Pipeline 失敗時 ``status.last_error`` 必須以下列前綴開頭：
    * ``DATA_FETCH:`` — yfinance / FRED 拿不到資料
    * ``INFERENCE:`` — env / policy / SMC 計算錯誤
    * ``WRITE:``     — atomic write / fsync / disk full

對三類注入錯誤分別 fault-inject 到 builder / atomic_write，斷言 ``status.last_error``
落在對應 prefix。前端 ``FailureToast`` (T054 + T056) 依此 prefix 出對應使用者文案。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from inference_service.episode_schemas import EpisodeDetail
from live_tracking.pipeline import (
    DailyTrackerPipeline,
    DataFetchError,
    InferenceError,
    WriteError,
)
from live_tracking.status import LiveTrackingStatus
from live_tracking.store import LiveTrackingStore


def _empty_envelope() -> EpisodeDetail:
    return EpisodeDetail.model_validate(
        {
            "summary": {
                "id": "test_policy_live",
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
            "trajectoryInline": [
                {
                    "timestamp": "2026-04-29T00:00:00Z",
                    "step": 0,
                    "weights": {
                        "riskOn": 0.4,
                        "riskOff": 0.4,
                        "cash": 0.2,
                        "perAsset": {},
                    },
                    "nav": 1.7291986,
                    "drawdownPct": 0.0,
                    "reward": {
                        "total": 0.0,
                        "returnComponent": 0.0,
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
            ],
            "rewardBreakdown": {
                "byStep": [
                    {
                        "total": 0.0,
                        "returnComponent": 0.0,
                        "drawdownPenalty": 0.0,
                        "costPenalty": 0.0,
                    }
                ],
                "cumulative": [
                    {
                        "step": 1,
                        "cumulativeTotal": 0.0,
                        "cumulativeReturn": 0.0,
                        "cumulativeDrawdownPenalty": 0.0,
                        "cumulativeCostPenalty": 0.0,
                    }
                ],
            },
            "smcOverlayByAsset": {},
        }
    )


@pytest.fixture
def paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "live_tracking.json", tmp_path / "live_tracking_status.json"


def _make_pipeline(paths_pair, builder) -> DailyTrackerPipeline:
    artefact_path, status_path = paths_pair
    # 把 status 預先初始化為 idle（沒有 is_running flag）
    LiveTrackingStatus(
        last_frame_date=None, is_running=False
    ).write(status_path)
    return DailyTrackerPipeline(
        store=LiveTrackingStore(artefact_path),
        status_path=status_path,
        build_frames=builder,
        initial_nav=1.7291986,
        start_anchor=date(2026, 4, 29),
        policy_run_id="test_policy",
    )


class TestErrorClassification:
    """三類錯誤 → status.last_error 三段式 prefix。"""

    def test_data_fetch_error_prefix(self, paths: tuple[Path, Path]) -> None:
        _, status_path = paths

        def builder(**_kwargs):
            raise DataFetchError("yfinance request timed out")

        pipeline = _make_pipeline(paths, builder)
        with pytest.raises(DataFetchError):
            pipeline.run_once(date(2026, 4, 30), pipeline_id="data_fetch_fail")

        status = LiveTrackingStatus.load(status_path)
        assert status.last_error is not None
        assert status.last_error.startswith("DATA_FETCH:"), (
            f"Expected DATA_FETCH: prefix, got: {status.last_error}"
        )
        assert status.is_running is False  # mark_failed must reset is_running

    def test_inference_error_prefix(self, paths: tuple[Path, Path]) -> None:
        _, status_path = paths

        def builder(**_kwargs):
            # 任意非 DataFetch / Write 異常 → INFERENCE 分類
            raise ValueError("policy.predict NaN output")

        pipeline = _make_pipeline(paths, builder)
        with pytest.raises(InferenceError):
            pipeline.run_once(date(2026, 4, 30), pipeline_id="inference_fail")

        status = LiveTrackingStatus.load(status_path)
        assert status.last_error is not None
        assert status.last_error.startswith("INFERENCE:"), (
            f"Expected INFERENCE: prefix, got: {status.last_error}"
        )
        assert status.is_running is False

    def test_write_error_prefix(self, paths: tuple[Path, Path]) -> None:
        artefact_path, status_path = paths

        def builder(**_kwargs):
            return _empty_envelope()

        pipeline = _make_pipeline(paths, builder)

        # patch atomic_write 直接 raise OSError
        from unittest.mock import patch

        with (
            patch.object(
                LiveTrackingStore, "atomic_write", side_effect=OSError("disk full")
            ),
            pytest.raises(WriteError),
        ):
            pipeline.run_once(date(2026, 4, 30), pipeline_id="write_fail")

        status = LiveTrackingStatus.load(status_path)
        assert status.last_error is not None
        assert status.last_error.startswith("WRITE:"), (
            f"Expected WRITE: prefix, got: {status.last_error}"
        )
        assert status.is_running is False
        # artefact 不存在（建立過程一路失敗）— 不破壞既有狀態
        assert not artefact_path.exists()

    def test_succeeded_run_clears_last_error(self, paths: tuple[Path, Path]) -> None:
        """sanity：成功 run 後 last_error 必須被清掉，下次 status badge 不顯示舊錯。"""
        _, status_path = paths

        # 先注入 DATA_FETCH error
        def fetch_fail(**_kwargs):
            raise DataFetchError("first run fail")

        pipeline = _make_pipeline(paths, fetch_fail)
        with pytest.raises(DataFetchError):
            pipeline.run_once(date(2026, 4, 30), pipeline_id="run1")

        # 第二次成功
        def ok_builder(**_kwargs):
            return _empty_envelope()

        pipeline.build_frames = ok_builder
        pipeline.run_once(date(2026, 4, 30), pipeline_id="run2")

        status = LiveTrackingStatus.load(status_path)
        assert status.last_error is None, (
            f"Successful run must clear last_error, but got: {status.last_error}"
        )
