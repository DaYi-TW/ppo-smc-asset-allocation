"""Tests for ``inference_service.episodes`` and the two episode endpoints.

對應 spec FR-006 / FR-008 / FR-009 / FR-013，tasks T031-T038。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from inference_service.app import create_app
from inference_service.episode_schemas import EpisodeDetailEnvelope
from inference_service.episodes import EpisodeStore


def _minimal_envelope_dict() -> dict:
    """Build a tiny but schema-valid EpisodeDetailEnvelope payload."""
    weights = {"NVDA": 0.1, "AMD": 0.1, "TSM": 0.1, "MU": 0.1, "GLD": 0.2, "TLT": 0.2, "CASH": 0.2}
    ohlc = {
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 1_000_000.0,
    }
    ohlc_per_asset = {a: ohlc for a in ("NVDA", "AMD", "TSM", "MU", "GLD", "TLT")}
    smc_signals = {
        "bos": 0,
        "choch": 0,
        "fvgDistancePct": None,
        "obTouching": False,
        "obDistanceRatio": None,
    }
    weight_alloc = {
        "riskOn": 0.4,
        "riskOff": 0.4,
        "cash": 0.2,
        "perAsset": weights,
    }
    reward = {
        "total": 0.001,
        "returnComponent": 0.001,
        "drawdownPenalty": 0.0,
        "costPenalty": 0.0,
    }
    action = {
        "raw": [0.0] * 7,
        "normalized": [1 / 7] * 7,
        "logProb": -1.5,
        "entropy": 1.9,
    }
    frames = []
    for i in range(3):
        frames.append(
            {
                "timestamp": f"2025-01-0{i + 2}",
                "step": i,
                "weights": weight_alloc,
                "nav": 1.0 + 0.001 * i,
                "drawdownPct": 0.0,
                "reward": reward,
                "smcSignals": smc_signals,
                "ohlcv": ohlc,
                "ohlcvByAsset": ohlc_per_asset,
                "action": action,
            }
        )

    cumulative = []
    running = 0.0
    for i in range(3):
        running += reward["total"]
        cumulative.append(
            {
                "step": max(1, i),
                "cumulativeTotal": running,
                "cumulativeReturn": running,
                "cumulativeDrawdownPenalty": 0.0,
                "cumulativeCostPenalty": 0.0,
            }
        )

    overlay = {"swings": [], "zigzag": [], "fvgs": [], "obs": [], "breaks": []}
    return {
        "data": {
            "summary": {
                "id": "test-episode-1",
                "policyId": "test-episode-1",
                "startDate": "2025-01-02",
                "endDate": "2025-01-04",
                "nSteps": 2,
                "initialNav": 1.0,
                "finalNav": 1.002,
                "cumulativeReturnPct": 0.2,
                "annualizedReturnPct": 5.0,
                "maxDrawdownPct": 0.0,
                "sharpeRatio": 1.5,
                "sortinoRatio": 1.8,
                "includeSmc": True,
            },
            "trajectoryInline": frames,
            "rewardBreakdown": {
                "byStep": [reward, reward, reward],
                "cumulative": cumulative,
            },
            "smcOverlayByAsset": {
                a: overlay
                for a in ("NVDA", "AMD", "TSM", "MU", "GLD", "TLT")
            },
        },
        "meta": {
            "generatedAt": "2026-05-07T00:00:00Z",
            "evaluatorVersion": "1.0.0",
            "policyChecksum": None,
            "dataChecksum": None,
        },
    }


@pytest.fixture
def artefact_file(tmp_path: Path) -> Path:
    payload = _minimal_envelope_dict()
    out = tmp_path / "episode_detail.json"
    out.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return out


class TestEpisodeStoreLoading:
    def test_from_file_loads_and_validates(self, artefact_file: Path) -> None:
        store = EpisodeStore.from_file(artefact_file)
        assert store.episode_id == "test-episode-1"
        assert store.summary.nSteps == 2
        assert len(store.detail.trajectoryInline) == 3

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="episode artefact not found"):
            EpisodeStore.from_file(tmp_path / "missing.json")

    def test_invalid_payload_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"data": {}, "meta": {}}), encoding="utf-8")
        with pytest.raises(Exception):  # pydantic ValidationError
            EpisodeStore.from_file(bad)

    def test_extra_fields_rejected(self, tmp_path: Path) -> None:
        payload = _minimal_envelope_dict()
        payload["data"]["summary"]["extraField"] = "leak"
        bad = tmp_path / "extra.json"
        bad.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(Exception):
            EpisodeStore.from_file(bad)


class TestEpisodeEndpoints:
    @pytest.fixture
    def client_with_store(self, artefact_file: Path):
        store = EpisodeStore.from_file(artefact_file)

        # 用 minimal stub state — 不需要 init_state 的 policy
        class _StubState:
            policy = None
            from datetime import UTC, datetime
            started_at_utc = datetime.now(UTC)
            last_inference_at_utc = None

        app = create_app(
            state=_StubState(),  # type: ignore[arg-type]
            redis_client=None,
            episode_store=store,
        )
        return TestClient(app)

    def test_list_returns_one_episode(self, client_with_store) -> None:
        resp = client_with_store.get("/api/v1/episodes")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body and "meta" in body
        assert len(body["items"]) == 1
        assert body["items"][0]["id"] == "test-episode-1"
        assert body["meta"]["count"] == 1

    def test_detail_returns_full_envelope(self, client_with_store) -> None:
        resp = client_with_store.get("/api/v1/episodes/test-episode-1")
        assert resp.status_code == 200
        body = resp.json()
        # Strict schema validation
        EpisodeDetailEnvelope.model_validate(body)
        assert body["data"]["summary"]["id"] == "test-episode-1"
        assert len(body["data"]["trajectoryInline"]) == 3
        assert set(body["data"]["smcOverlayByAsset"].keys()) == {
            "NVDA", "AMD", "TSM", "MU", "GLD", "TLT",
        }

    def test_detail_404_for_unknown_id(self, client_with_store) -> None:
        resp = client_with_store.get("/api/v1/episodes/does-not-exist")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "EPISODE_NOT_FOUND"

    def test_503_when_store_missing(self) -> None:
        from datetime import UTC, datetime

        class _StubState:
            policy = None
            started_at_utc = datetime.now(UTC)
            last_inference_at_utc = None

        app = create_app(
            state=_StubState(),  # type: ignore[arg-type]
            redis_client=None,
            episode_store=None,
        )
        client = TestClient(app)
        for path in ("/api/v1/episodes", "/api/v1/episodes/anything"):
            resp = client.get(path)
            assert resp.status_code == 503
            assert resp.json()["code"] == "EPISODE_STORE_UNAVAILABLE"
