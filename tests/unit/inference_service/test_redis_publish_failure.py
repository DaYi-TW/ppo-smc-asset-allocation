"""T036 — Redis publish 失敗解耦 (FR-011).

publish 失敗不應 raise；inference 仍視為成功。set 與 publish 兩條路徑各自獨立。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_publish_swallows_redis_error(fake_payload_dict: dict[str, Any]) -> None:
    """publish() raise → publish_prediction 不 raise；set 仍嘗試呼叫."""
    from redis.exceptions import RedisError

    from inference_service.redis_io import RedisIO
    from inference_service.schemas import PredictionPayload

    fake_client = AsyncMock()
    fake_client.set = AsyncMock(return_value=True)
    fake_client.publish = AsyncMock(side_effect=RedisError("connection lost"))

    redis_io = RedisIO(
        client=fake_client, channel="predictions:latest", key="predictions:latest", ttl_seconds=604800
    )

    payload = PredictionPayload.model_validate(fake_payload_dict)

    # MUST NOT raise
    await redis_io.publish_prediction(payload)

    fake_client.set.assert_awaited_once()
    fake_client.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_failure_does_not_skip_publish(fake_payload_dict: dict[str, Any]) -> None:
    """set() raise 後 publish() 仍應嘗試（兩條路徑解耦）."""
    from redis.exceptions import RedisError

    from inference_service.redis_io import RedisIO
    from inference_service.schemas import PredictionPayload

    fake_client = AsyncMock()
    fake_client.set = AsyncMock(side_effect=RedisError("set failed"))
    fake_client.publish = AsyncMock(return_value=1)

    redis_io = RedisIO(
        client=fake_client, channel="predictions:latest", key="predictions:latest", ttl_seconds=604800
    )

    payload = PredictionPayload.model_validate(fake_payload_dict)
    await redis_io.publish_prediction(payload)

    fake_client.set.assert_awaited_once()
    fake_client.publish.assert_awaited_once()
