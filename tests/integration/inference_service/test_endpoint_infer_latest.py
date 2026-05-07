"""T019 — GET /infer/latest endpoint integration test (RED → GREEN at T024).

對應 spec FR-008 / User Story 3 (取最新 prediction from cache)。
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient


class _FakeRedis:
    """In-memory replacement for redis.asyncio.Redis (just .get / .ping)."""

    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self._store: dict[str, str] = {}
        if payload is not None:
            self._store["predictions:latest"] = json.dumps(payload)

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def ping(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_get_infer_latest_returns_404_when_empty(fake_state: Any) -> None:
    """剛啟動 cache 為空 → 404 NO_PREDICTION_YET."""
    from inference_service.app import create_app

    app = create_app(state=fake_state, redis_client=_FakeRedis(payload=None))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/infer/latest")

    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == "NO_PREDICTION_YET"


@pytest.mark.asyncio
async def test_get_infer_latest_returns_payload(
    fake_state: Any, fake_payload_dict: dict[str, Any]
) -> None:
    """Cache 有東西 → 200 + PredictionPayload."""
    from inference_service.app import create_app

    app = create_app(
        state=fake_state, redis_client=_FakeRedis(payload=fake_payload_dict)
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/infer/latest")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["as_of_date"] == "2026-04-28"
    assert body["triggered_by"] == "manual"
