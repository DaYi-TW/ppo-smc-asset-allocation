"""T034 — Redis pub/sub round-trip via fakeredis.

對應 spec FR-004 / SC-004.

Note：tasks.md 原本指定 testcontainers[redis] 起真容器，但本機 docker 環境
未保證可用 + CI 起真 redis 太慢；改用 fakeredis（async API）作為 in-memory 替代，
驗證 publish_prediction → SUBSCRIBE 收到 byte-identical JSON。真容器 round-trip
留給 Phase 7 contract test (T046) 或 docker-compose smoke (T043)。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest


@pytest.mark.asyncio
async def test_publish_prediction_round_trip_via_fakeredis(
    fake_payload_dict: dict[str, Any],
) -> None:
    """publish → subscribe round-trip：subscriber 收到 byte-identical JSON."""
    import fakeredis.aioredis as fakeredis_aio

    from inference_service.redis_io import RedisIO
    from inference_service.schemas import PredictionPayload

    # Two clients sharing the same in-memory server
    server = fakeredis_aio.FakeServer()
    pub_client = fakeredis_aio.FakeRedis(server=server, decode_responses=False)
    sub_client = fakeredis_aio.FakeRedis(server=server, decode_responses=False)

    redis_io = RedisIO(
        client=pub_client, channel="predictions:latest", key="predictions:latest", ttl_seconds=604800
    )

    payload = PredictionPayload.model_validate(fake_payload_dict)

    # Set up subscriber
    pubsub = sub_client.pubsub()
    await pubsub.subscribe("predictions:latest")

    # Drain the initial subscribe-ack message
    received_messages: list[dict[str, Any]] = []

    async def _consume() -> None:
        async for msg in pubsub.listen():
            if msg.get("type") == "message":
                received_messages.append(msg)
                break

    consumer_task = asyncio.create_task(_consume())
    await asyncio.sleep(0.05)  # let subscriber settle

    await redis_io.publish_prediction(payload)

    await asyncio.wait_for(consumer_task, timeout=2.0)
    await pubsub.aclose()
    await pub_client.aclose()
    await sub_client.aclose()

    assert len(received_messages) == 1
    raw = received_messages[0]["data"]
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    received_payload = PredictionPayload.model_validate(json.loads(raw))
    # Byte-identical contract：所有 11 個欄位都對齊
    assert received_payload.model_dump() == payload.model_dump()
