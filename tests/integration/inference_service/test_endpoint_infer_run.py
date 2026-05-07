"""T018 — POST /infer/run endpoint integration test (RED → GREEN at T023).

對應 spec FR-001 / User Story 2 (on-demand 手動觸發)。
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_post_infer_run_returns_payload(
    fake_state: Any,
    fake_payload_dict: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /infer/run → 200 + PredictionPayload with triggered_by='manual'."""
    from inference_service.app import create_app
    from inference_service.schemas import PredictionPayload

    app = create_app(state=fake_state, redis_client=None)

    # Stub the handler so we don't run real PPO.
    import inference_service.handler as handler_mod

    async def fake_runner(_state: Any, triggered_by: str) -> PredictionPayload:
        d = dict(fake_payload_dict)
        d["triggered_by"] = triggered_by
        return PredictionPayload.model_validate(d)

    monkeypatch.setattr(handler_mod, "_run_inference_unlocked", AsyncMock(side_effect=fake_runner))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/infer/run")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["triggered_by"] == "manual"
    assert sum(body["target_weights"].values()) == pytest.approx(1.0, abs=1e-6)


@pytest.mark.asyncio
async def test_post_infer_run_concurrent_serialized_or_busy(
    fake_state: Any,
    fake_payload_dict: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """並發 2 個 POST /infer/run：第二個應回 200（排隊）或 409 INFERENCE_BUSY。

    FR-003：mutex 互斥；spec 允許 server 選擇阻塞排隊或立即拒絕，
    本實作（asyncio.Lock）會阻塞排隊 → 兩個都應 200。
    """
    from inference_service.app import create_app
    from inference_service.schemas import PredictionPayload

    app = create_app(state=fake_state, redis_client=None)

    import uuid as uuid_mod

    import inference_service.handler as handler_mod

    async def slow_runner(_state: Any, triggered_by: str) -> PredictionPayload:
        await asyncio.sleep(0.3)
        d = dict(fake_payload_dict)
        d["triggered_by"] = triggered_by
        d["inference_id"] = str(uuid_mod.uuid4())
        return PredictionPayload.model_validate(d)

    monkeypatch.setattr(handler_mod, "_run_inference_unlocked", AsyncMock(side_effect=slow_runner))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        results = await asyncio.gather(ac.post("/infer/run"), ac.post("/infer/run"))

    statuses = [r.status_code for r in results]
    # 兩種都接受：(200, 200) 排隊，或 (200, 409) 立刻拒絕
    assert all(s in (200, 409) for s in statuses), statuses
    assert 200 in statuses, "至少第一個應該成功"


@pytest.mark.asyncio
async def test_post_infer_run_internal_error_returns_500(
    fake_state: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """handler raise → 500 + ErrorResponse 含 INFERENCE_FAILED + error_id。"""
    from inference_service.app import create_app

    app = create_app(state=fake_state, redis_client=None)

    import inference_service.handler as handler_mod

    monkeypatch.setattr(
        handler_mod, "_run_inference_unlocked", AsyncMock(side_effect=RuntimeError("boom"))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/infer/run")

    assert resp.status_code == 500, resp.text
    body = resp.json()
    assert body["code"] == "INFERENCE_FAILED"
    assert "error_id" in body
    # 不洩漏 stack trace
    assert "Traceback" not in body.get("message", "")
    assert "boom" not in body.get("message", "")
