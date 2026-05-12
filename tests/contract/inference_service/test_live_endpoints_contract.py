"""T024 / T025 — Contract tests for /api/v1/episodes/live/* endpoints.

對齊 spec 010 FR-015 / FR-016 / SC-004 與
``specs/010-live-tracking-dashboard/contracts/openapi-live-tracking.yaml``。

Constitution Principle V (Spec-First, NON-NEGOTIABLE) gate：endpoint shape
完全鎖死 spec — 欄位數量、status code、值域 enum 必須與 OpenAPI 定義一致。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from inference_service.app import create_app
from inference_service.episodes import MultiSourceEpisodeStore
from live_tracking.status import LiveTrackingStatus
from live_tracking.store import LiveTrackingStore


def _stub_state():
    class _StubState:
        policy = None
        started_at_utc = datetime.now(UTC)
        last_inference_at_utc = None

    return _StubState()


@pytest.fixture
def live_paths(tmp_path: Path) -> tuple[Path, Path]:
    artefact = tmp_path / "live_tracking.json"
    status = tmp_path / "live_tracking_status.json"
    return artefact, status


@pytest.fixture
def client(live_paths: tuple[Path, Path]) -> TestClient:
    artefact_path, status_path = live_paths
    live_store = LiveTrackingStore(artefact_path)
    multi = MultiSourceEpisodeStore(oos=None, live=live_store)
    app = create_app(
        state=_stub_state(),  # type: ignore[arg-type]
        redis_client=None,
        episode_store=multi,
        live_status_path=status_path,
        live_start_anchor=date(2026, 4, 29),
        live_initial_nav=1.7291986,
        live_policy_run_id="test_policy",
    )
    return TestClient(app)


class TestStatusEndpointBlankState:
    """``GET /live/status`` 在從未跑過 pipeline 時的 baseline 形狀。"""

    def test_status_200_with_all_nullable_fields(self, client: TestClient) -> None:
        resp = client.get("/api/v1/episodes/live/status")
        assert resp.status_code == 200
        body = resp.json()
        # 嚴格欄位集合（spec FR-015）
        assert set(body.keys()) == {
            "last_updated",
            "last_frame_date",
            "data_lag_days",
            "is_running",
            "last_error",
        }
        assert body["last_updated"] is None
        assert body["last_frame_date"] is None
        assert body["data_lag_days"] is None
        assert body["is_running"] is False
        assert body["last_error"] is None


class TestStatusEndpointWithPersistedState:
    def test_status_serializes_persisted_fields(
        self, client: TestClient, live_paths: tuple[Path, Path]
    ) -> None:
        _, status_path = live_paths
        s = LiveTrackingStatus(
            last_updated=datetime(2026, 5, 8, 14, 0, 0, tzinfo=UTC),
            last_frame_date=date(2026, 5, 7),
            is_running=False,
            last_error=None,
        )
        s.write(status_path)

        resp = client.get("/api/v1/episodes/live/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["last_frame_date"] == "2026-05-07"
        assert body["is_running"] is False
        assert body["data_lag_days"] is not None
        assert body["data_lag_days"] >= 0


class TestRefreshEndpoint202Shape:
    """SC-004 + FR-016：202 body 嚴格欄位集合 + value enums."""

    def test_refresh_returns_202_envelope(self, client: TestClient) -> None:
        # 第一次呼叫：lock 無人持有 → 202
        resp = client.post("/api/v1/episodes/live/refresh")
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert set(body.keys()) == {
            "accepted",
            "pipeline_id",
            "estimated_duration_seconds",
            "poll_status_url",
        }
        assert body["accepted"] is True
        assert isinstance(body["pipeline_id"], str)
        assert len(body["pipeline_id"]) >= 8  # uuid string
        assert body["estimated_duration_seconds"] >= 1
        assert body["poll_status_url"] == "/api/v1/episodes/live/status"


class TestEpisodesListWithLiveOnly:
    """FR-012：list 包含 Live entry（即使尚無 frame）— 但目前 live artefact
    為空 → 沒有 Live summary 可列。此測試確認不 500。"""

    def test_list_empty_when_no_artefacts(self, client: TestClient) -> None:
        resp = client.get("/api/v1/episodes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["meta"]["count"] == 0
