"""T035 — Redis key TTL + get_latest cache 行為.

對應 spec FR-005 / data-model §8。

- ``publish_prediction`` 後 GET key TTL ∈ (604790, 604800] 秒（7 天，扣掉 round-trip）
- ``get_latest`` after expire(0) → None
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.mark.asyncio
async def test_publish_sets_ttl_around_seven_days(
    fake_payload_dict: dict[str, Any],
) -> None:
    import fakeredis.aioredis as fakeredis_aio

    from inference_service.redis_io import RedisIO
    from inference_service.schemas import PredictionPayload

    client = fakeredis_aio.FakeRedis(decode_responses=False)
    redis_io = RedisIO(
        client=client, channel="predictions:latest", key="predictions:latest", ttl_seconds=604800
    )

    payload = PredictionPayload.model_validate(fake_payload_dict)
    await redis_io.publish_prediction(payload)

    ttl = await client.ttl("predictions:latest")
    assert 604790 <= ttl <= 604800, f"unexpected ttl: {ttl}"

    await client.aclose()


@pytest.mark.asyncio
async def test_get_latest_returns_none_after_expiry(
    fake_payload_dict: dict[str, Any],
) -> None:
    import fakeredis.aioredis as fakeredis_aio

    from inference_service.redis_io import RedisIO
    from inference_service.schemas import PredictionPayload

    client = fakeredis_aio.FakeRedis(decode_responses=False)
    redis_io = RedisIO(
        client=client, channel="predictions:latest", key="predictions:latest", ttl_seconds=604800
    )

    payload = PredictionPayload.model_validate(fake_payload_dict)
    await redis_io.publish_prediction(payload)

    cached = await redis_io.get_latest()
    assert cached is not None
    assert cached.model_dump() == payload.model_dump()

    # Force expire — fakeredis expire(0) leaves the key in place; use delete instead.
    await client.delete("predictions:latest")
    expired = await redis_io.get_latest()
    assert expired is None

    await client.aclose()
