"""T025 — Integration tests for /api/v1/episodes/live/* (TestClient e2e).

對應 spec 010 FR-006 / FR-012 / FR-013 / FR-014 / FR-016 / SC-004 / SC-006。

與 ``tests/contract/inference_service/test_live_endpoints_contract.py`` 互補：
contract 測 schema shape；本檔測流程與 dispatch 行為。

5 個 flow：
  (a) GET /live/status 首次   → 全 None / data_lag_days null
  (b) POST /live/refresh 首次 → 202 + 預估秒數 ≥ 1
  (c) 第二次並發 POST /refresh → 409 + RefreshConflictResponse + running_pid
  (d) GET /episodes 含 OOS + Live source 排序（OOS 在前 Live 在後）
  (e) GET /episodes/{live_id} → 讀 live_tracking.json（不快取，mtime 改變即見新內容）
  (f) GET /episodes/{oos_id} → 讀 OOS（不變動，FR-014）
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from inference_service.app import create_app
from inference_service.episode_schemas import (
    EpisodeDetail,
    EpisodeDetailEnvelope,
)
from inference_service.episodes import EpisodeStore, MultiSourceEpisodeStore
from live_tracking.store import LiveTrackingStore


def _stub_state():
    class _StubState:
        policy = None
        started_at_utc = datetime.now(UTC)
        last_inference_at_utc = None

    return _StubState()


def _envelope_with_n_frames(n: int, episode_id: str) -> EpisodeDetail:
    """Build minimal valid EpisodeDetail with n frames."""
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
                "id": episode_id,
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


def _seed_oos_artefact(path: Path, episode_id: str = "oos_run") -> str:
    """Persist a valid EpisodeDetailEnvelope and return episode_id."""
    detail = _envelope_with_n_frames(3, episode_id)
    envelope = EpisodeDetailEnvelope.model_validate(
        {
            "data": detail.model_dump(),
            "meta": {"generatedAt": "2026-05-08T00:00:00Z"},
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(envelope.model_dump(mode="json")), encoding="utf-8")
    return episode_id


@pytest.fixture
def paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "oos_artefact": tmp_path / "oos" / "episode_detail.json",
        "live_artefact": tmp_path / "live" / "live_tracking.json",
        "live_status": tmp_path / "live" / "live_tracking_status.json",
    }


@pytest.fixture
def client(paths: dict[str, Path]) -> TestClient:
    """App with OOS + Live multi-source store."""
    oos_id = _seed_oos_artefact(paths["oos_artefact"])
    oos_store = EpisodeStore.from_file(paths["oos_artefact"])
    assert oos_store.episode_id == oos_id

    live_store = LiveTrackingStore(paths["live_artefact"])
    multi = MultiSourceEpisodeStore(oos=oos_store, live=live_store)

    app = create_app(
        state=_stub_state(),  # type: ignore[arg-type]
        redis_client=None,
        episode_store=multi,
        live_status_path=paths["live_status"],
        live_start_anchor=date(2026, 4, 29),
        live_initial_nav=1.7291986,
        live_policy_run_id="test_policy",
    )
    return TestClient(app)


class TestStatusFlow:
    def test_a_status_blank_state(self, client: TestClient) -> None:
        """(a) 從未跑過 pipeline → 全 None。"""
        resp = client.get("/api/v1/episodes/live/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data_lag_days"] is None
        assert body["is_running"] is False


class TestRefreshHappyPath:
    def test_b_refresh_first_call_returns_202(self, client: TestClient) -> None:
        """(b) 首次 POST → 202 + 預估秒數 ≥ 1。"""
        resp = client.post("/api/v1/episodes/live/refresh")
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["accepted"] is True
        assert body["estimated_duration_seconds"] >= 1
        assert body["poll_status_url"] == "/api/v1/episodes/live/status"


class TestRefreshConcurrent409:
    """(c) Lock 已被 hold → 409 + running_pid（FR-006 / SC-004）。"""

    def test_c_second_refresh_returns_409(self, client: TestClient) -> None:
        # 直接搶下 app.state 的 live_refresh_lock 模擬「正在跑」
        lock: asyncio.Lock = client.app.state.live_refresh_lock  # type: ignore[attr-defined]
        # 搶 lock 必須在 event loop 內
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(lock.acquire())
            resp = client.post("/api/v1/episodes/live/refresh")
            assert resp.status_code == 409, resp.text
            body = resp.json()
            assert body["detail"] == "pipeline already running"
            assert "running_pid" in body
            assert "running_started_at" in body
            assert body["poll_status_url"] == "/api/v1/episodes/live/status"
        finally:
            if lock.locked():
                lock.release()
            loop.close()


class TestEpisodesListDualSource:
    """(d) /episodes 含 OOS + Live source。Live artefact 不存在 → 僅 OOS。"""

    def test_d_list_oos_only_when_live_absent(self, client: TestClient) -> None:
        resp = client.get("/api/v1/episodes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["count"] == 1
        # OOS first
        assert body["items"][0]["id"] == "oos_run"

    def test_d_list_oos_then_live_when_both_present(
        self, client: TestClient, paths: dict[str, Path]
    ) -> None:
        # 寫入 Live artefact（id 後綴 _live）— 走 LiveTrackingStore 的 atomic_write
        live_detail = _envelope_with_n_frames(2, "test_policy_live")
        LiveTrackingStore(paths["live_artefact"]).atomic_write(live_detail)

        resp = client.get("/api/v1/episodes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["count"] == 2
        # OOS 在前 Live 在後（FR-012 ordering）
        assert body["items"][0]["id"] == "oos_run"
        assert body["items"][1]["id"] == "test_policy_live"


class TestEpisodeDetailDispatch:
    """(e)(f) /episodes/{id} dispatch — Live id 走 LiveTrackingStore，OOS id 走 EpisodeStore。"""

    def test_e_live_id_reads_from_live_store_no_cache(
        self, client: TestClient, paths: dict[str, Path]
    ) -> None:
        # 初始 Live artefact 未存在 → 404
        resp1 = client.get("/api/v1/episodes/test_policy_live")
        assert resp1.status_code == 404

        # 建立 v1（透過 LiveTrackingStore.atomic_write 確保 schema 通過）
        store = LiveTrackingStore(paths["live_artefact"])
        v1_detail = _envelope_with_n_frames(1, "test_policy_live")
        store.atomic_write(v1_detail)
        resp2 = client.get("/api/v1/episodes/test_policy_live")
        assert resp2.status_code == 200
        assert len(resp2.json()["data"]["trajectoryInline"]) == 1

        # 寫入 v2（3 frames）→ 同一 client 不快取，立刻看到 3 frames
        v2_detail = _envelope_with_n_frames(3, "test_policy_live")
        store.atomic_write(v2_detail)
        resp3 = client.get("/api/v1/episodes/test_policy_live")
        assert resp3.status_code == 200
        assert len(resp3.json()["data"]["trajectoryInline"]) == 3

    def test_f_oos_id_reads_oos_store(self, client: TestClient) -> None:
        resp = client.get("/api/v1/episodes/oos_run")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["summary"]["id"] == "oos_run"
        assert len(body["data"]["trajectoryInline"]) == 3
