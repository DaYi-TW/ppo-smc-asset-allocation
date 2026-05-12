"""T049 — Phase 4 (US2) integration test for dual-source episodes (FR-012).

Scenario A: OOS artefact present, Live artefact missing → list returns 1 item (OOS only).
Scenario B: OOS artefact present, Live artefact created → list returns 2 items, OOS first (research §R5 ordering invariant).

Tests the production wiring path through ``MultiSourceEpisodeStore`` + FastAPI
``/api/v1/episodes`` endpoint — proves dispatch logic is correct end-to-end.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from inference_service.app import create_app
from inference_service.episode_schemas import EpisodeDetail
from inference_service.episodes import EpisodeStore, MultiSourceEpisodeStore
from live_tracking.store import LiveTrackingStore

_REPO_ROOT = Path(__file__).resolve().parents[3]
_OOS_ARTEFACT = (
    _REPO_ROOT
    / "runs"
    / "20260506_004455_659b8eb_seed42"
    / "eval_oos"
    / "episode_detail.json"
)


def _stub_state():
    class _StubState:
        policy = None
        started_at_utc = datetime.now(UTC)
        last_inference_at_utc = None

    return _StubState()


def _live_envelope(episode_id: str) -> EpisodeDetail:
    return EpisodeDetail.model_validate(
        {
            "summary": {
                "id": episode_id,
                "policyId": episode_id.removesuffix("_live"),
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


@pytest.fixture(scope="module")
def oos_artefact_path() -> Path:
    if not _OOS_ARTEFACT.exists():
        pytest.skip(f"OOS artefact not committed: {_OOS_ARTEFACT}")
    return _OOS_ARTEFACT


def _client(store: MultiSourceEpisodeStore) -> TestClient:
    app = create_app(
        state=_stub_state(),  # type: ignore[arg-type]
        redis_client=None,
        episode_store=store,
    )
    return TestClient(app)


class TestDualSourceList:
    def test_only_oos_when_live_missing(
        self, oos_artefact_path: Path, tmp_path: Path
    ) -> None:
        oos = EpisodeStore.from_file(oos_artefact_path)
        live = LiveTrackingStore(tmp_path / "live_tracking.json")
        store = MultiSourceEpisodeStore(oos=oos, live=live)

        resp = _client(store).get("/api/v1/episodes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["count"] == 1
        ids = [item["id"] for item in body["items"]]
        assert ids == [oos.episode_id]

    def test_both_when_live_created(
        self, oos_artefact_path: Path, tmp_path: Path
    ) -> None:
        oos = EpisodeStore.from_file(oos_artefact_path)
        live = LiveTrackingStore(tmp_path / "live_tracking.json")
        live_id = f"{oos.episode_id}_live"
        live.atomic_write(_live_envelope(live_id))

        store = MultiSourceEpisodeStore(oos=oos, live=live)
        resp = _client(store).get("/api/v1/episodes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["count"] == 2
        ids = [item["id"] for item in body["items"]]
        # research §R5 ordering invariant: OOS 在前
        assert ids == [oos.episode_id, live_id]


class TestDualSourceDetail:
    def test_live_detail_reads_through(
        self, oos_artefact_path: Path, tmp_path: Path
    ) -> None:
        """T051 invariant: live id 不走快取。寫入 → list 顯示之 finalNav 與 detail 一致。"""
        oos = EpisodeStore.from_file(oos_artefact_path)
        live = LiveTrackingStore(tmp_path / "live_tracking.json")
        live_id = f"{oos.episode_id}_live"

        # v1: nav 1.0
        v1 = _live_envelope(live_id)
        live.atomic_write(v1)
        store = MultiSourceEpisodeStore(oos=oos, live=live)
        client = _client(store)

        r1 = client.get(f"/api/v1/episodes/{live_id}")
        assert r1.status_code == 200
        assert r1.json()["data"]["summary"]["finalNav"] == pytest.approx(1.7291986)

        # v2: 改寫 finalNav，模擬 pipeline 重寫 — 同一 process 第二次 GET 必須看到新值
        v2 = v1.model_dump()
        v2["summary"]["finalNav"] = 1.85
        live.atomic_write(EpisodeDetail.model_validate(v2))

        r2 = client.get(f"/api/v1/episodes/{live_id}")
        assert r2.status_code == 200
        assert r2.json()["data"]["summary"]["finalNav"] == pytest.approx(1.85)

    def test_oos_id_does_not_dispatch_to_live(
        self, oos_artefact_path: Path, tmp_path: Path
    ) -> None:
        oos = EpisodeStore.from_file(oos_artefact_path)
        live = LiveTrackingStore(tmp_path / "live_tracking.json")
        store = MultiSourceEpisodeStore(oos=oos, live=live)

        resp = _client(store).get(f"/api/v1/episodes/{oos.episode_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["summary"]["id"] == oos.episode_id

    def test_unknown_id_returns_404(
        self, oos_artefact_path: Path, tmp_path: Path
    ) -> None:
        oos = EpisodeStore.from_file(oos_artefact_path)
        live = LiveTrackingStore(tmp_path / "live_tracking.json")
        store = MultiSourceEpisodeStore(oos=oos, live=live)

        resp = _client(store).get("/api/v1/episodes/does_not_exist_live")
        assert resp.status_code == 404
