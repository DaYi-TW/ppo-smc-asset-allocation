"""T021 — ErrorResponse schema 對齊 contracts/error-codes.md（FR-012）。

驗證 5xx / 4xx response body 的 schema、不洩漏 stack trace。
"""

from __future__ import annotations

import re
import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient


_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_ISO_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T")


class _FakeRedisEmpty:
    async def get(self, key: str) -> str | None:
        return None

    async def ping(self) -> bool:
        return True


def _assert_error_schema(body: dict[str, Any], expected_code: str) -> None:
    """ErrorResponse contract assertion."""
    assert set(body.keys()) >= {"code", "message", "error_id", "timestamp_utc"}
    assert body["code"] == expected_code
    assert isinstance(body["message"], str) and len(body["message"]) > 0
    assert _UUID_PATTERN.match(body["error_id"]), body["error_id"]
    # 確認 error_id 是 valid uuid
    uuid.UUID(body["error_id"])
    assert _ISO_PATTERN.match(body["timestamp_utc"]), body["timestamp_utc"]


@pytest.mark.asyncio
async def test_no_prediction_yet_error_schema(fake_state: Any) -> None:
    """GET /infer/latest 空 cache → 404 NO_PREDICTION_YET 完整 schema."""
    from inference_service.app import create_app

    app = create_app(state=fake_state, redis_client=_FakeRedisEmpty())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/infer/latest")

    assert resp.status_code == 404
    _assert_error_schema(resp.json(), "NO_PREDICTION_YET")


@pytest.mark.asyncio
async def test_inference_failed_error_schema(
    fake_state: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """handler raise → 500 INFERENCE_FAILED + 完整 schema + 不洩 stack trace."""
    from inference_service.app import create_app

    app = create_app(state=fake_state, redis_client=None)

    import inference_service.handler as handler_mod

    secret_msg = "internal-implementation-detail-leak"
    monkeypatch.setattr(
        handler_mod,
        "_run_inference_unlocked",
        AsyncMock(side_effect=RuntimeError(secret_msg)),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/infer/run")

    assert resp.status_code == 500
    body = resp.json()
    _assert_error_schema(body, "INFERENCE_FAILED")
    # FR-012：response 不能含 stack trace 或 raw exception message
    assert "Traceback" not in body["message"]
    assert secret_msg not in body["message"]
    # message 應該是 generic 安全字串
    assert "INFERENCE_FAILED" in body["message"] or "Inference" in body["message"]
