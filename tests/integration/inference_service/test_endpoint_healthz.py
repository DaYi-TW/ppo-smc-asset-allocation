"""T020 — GET /healthz endpoint integration test (RED → GREEN at T025).

對應 spec FR-009 / User Story 4 (健康檢查)。
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient


class _FakeRedis:
    def __init__(self, reachable: bool = True) -> None:
        self._reachable = reachable

    async def ping(self) -> bool:
        if not self._reachable:
            raise ConnectionError("redis down")
        return True

    async def get(self, key: str) -> str | None:
        return None


@pytest.mark.asyncio
async def test_healthz_ok_when_ready(fake_state: Any) -> None:
    """policy + redis 都 OK → 200 + status='ok'."""
    from inference_service.app import create_app

    app = create_app(state=fake_state, redis_client=_FakeRedis(reachable=True))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/healthz")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["policy_loaded"] is True
    assert body["redis_reachable"] is True
    assert body["uptime_seconds"] >= 0


@pytest.mark.asyncio
async def test_healthz_degraded_when_policy_missing(fake_state: Any) -> None:
    """policy=None → 503 + status='degraded' + policy_loaded=False."""
    from inference_service.app import create_app

    fake_state.policy = None
    app = create_app(state=fake_state, redis_client=_FakeRedis(reachable=True))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/healthz")

    assert resp.status_code == 503, resp.text
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["policy_loaded"] is False


@pytest.mark.asyncio
async def test_healthz_degraded_when_redis_down(fake_state: Any) -> None:
    """redis ping 失敗 → 503 + redis_reachable=False."""
    from inference_service.app import create_app

    app = create_app(state=fake_state, redis_client=_FakeRedis(reachable=False))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/healthz")

    assert resp.status_code == 503, resp.text
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["redis_reachable"] is False
