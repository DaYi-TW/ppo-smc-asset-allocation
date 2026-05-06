"""T047 — ErrorResponse contract（contracts/error-codes.md）.

對每個 error code 構造對應條件，assert HTTP status + body schema.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class _FakeRedis:
    def __init__(self, payload: Any | None = None, reachable: bool = True) -> None:
        self._payload = payload
        self._reachable = reachable

    async def get(self, key: str) -> Any | None:
        if not self._reachable:
            raise ConnectionError("redis unreachable")
        return self._payload

    async def ping(self) -> bool:
        if not self._reachable:
            raise ConnectionError("redis unreachable")
        return True


def _validate_error_body(body: dict[str, Any], expected_code: str) -> None:
    assert set(body.keys()) >= {"code", "message", "error_id", "timestamp_utc"}
    assert body["code"] == expected_code
    assert isinstance(body["message"], str) and body["message"]
    assert _UUID_RE.match(body["error_id"]), body["error_id"]
    uuid.UUID(body["error_id"])
    assert body["timestamp_utc"].count("-") >= 2


@pytest.fixture
def fake_state_obj() -> Any:
    """Local copy of fake_state for this test module（contract dir 沒共享 conftest）."""
    from unittest.mock import MagicMock

    from inference_service.handler import InferenceState

    return InferenceState(
        lock=asyncio.Lock(),
        policy=MagicMock(),
        env_factory=MagicMock(),
        policy_path="fake.zip",
        data_root="data/raw",
        include_smc=True,
        seed=42,
    )


@pytest.fixture
def fake_payload() -> dict[str, Any]:
    return {
        "as_of_date": "2026-04-28",
        "next_trading_day_target": "first session after 2026-04-28 (apply at next open)",
        "policy_path": "fake.zip",
        "deterministic": True,
        "target_weights": {
            "NVDA": 0.1, "AMD": 0.1, "TSM": 0.1, "MU": 0.1,
            "GLD": 0.1, "TLT": 0.1, "CASH": 0.4,
        },
        "weights_capped": False,
        "renormalized": False,
        "context": {
            "data_root": "data/raw", "include_smc": True,
            "n_warmup_steps": 100, "current_nav_at_as_of": 1.0,
        },
        "triggered_by": "manual",
        "inference_id": "00000000-0000-0000-0000-000000000000",
        "inferred_at_utc": "2026-05-06T00:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_no_prediction_yet(fake_state_obj: Any) -> None:
    """GET /infer/latest, empty cache → 404 NO_PREDICTION_YET."""
    from inference_service.app import create_app

    app = create_app(state=fake_state_obj, redis_client=_FakeRedis(payload=None))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/infer/latest")
    assert resp.status_code == 404
    _validate_error_body(resp.json(), "NO_PREDICTION_YET")


@pytest.mark.asyncio
async def test_redis_unreachable_on_latest(fake_state_obj: Any) -> None:
    """GET /infer/latest, redis raise → 503 REDIS_UNREACHABLE."""
    from inference_service.app import create_app

    app = create_app(state=fake_state_obj, redis_client=_FakeRedis(reachable=False))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/infer/latest")
    assert resp.status_code == 503
    _validate_error_body(resp.json(), "REDIS_UNREACHABLE")


@pytest.mark.asyncio
async def test_inference_failed(
    fake_state_obj: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /infer/run handler raise → 500 INFERENCE_FAILED."""
    import inference_service.handler as handler_mod
    from inference_service.app import create_app

    monkeypatch.setattr(
        handler_mod, "_run_inference_unlocked", AsyncMock(side_effect=RuntimeError("kaboom"))
    )

    app = create_app(state=fake_state_obj, redis_client=None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/infer/run")
    assert resp.status_code == 500
    body = resp.json()
    _validate_error_body(body, "INFERENCE_FAILED")
    assert "kaboom" not in body["message"]


@pytest.mark.asyncio
async def test_policy_not_loaded_via_healthz(fake_state_obj: Any) -> None:
    """policy=None → /healthz 503 (POLICY_NOT_LOADED 等價於 status=degraded)."""
    from inference_service.app import create_app

    fake_state_obj.policy = None
    app = create_app(state=fake_state_obj, redis_client=_FakeRedis(reachable=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/healthz")
    # /healthz 用 HealthResponse schema，不是 ErrorResponse；驗證 503 + degraded
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["policy_loaded"] is False
