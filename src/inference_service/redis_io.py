"""async Redis publisher + LatestCache。

對應 spec FR-004 / FR-005 / FR-011。Phase 5 T037 實作。

設計：
    * ``RedisIO`` wrap async ``redis.asyncio.Redis`` 提供 publish_prediction / get_latest / ping
    * ``publish_prediction`` 先 ``set(key, json, ex=ttl)`` 再 ``publish(channel, json)``，兩個動作各自 try/except，**publish 失敗不 raise**（FR-011）
    * ``get_latest`` ``GET key`` → Pydantic validate，cache 過期或 key 不存在回 ``None``
"""

from __future__ import annotations

import json
import logging
import traceback
from dataclasses import dataclass
from typing import Any

from .schemas import PredictionPayload

logger = logging.getLogger(__name__)


@dataclass
class RedisIO:
    """async Redis client wrapper（dataclass，不是 BaseModel — caller 注入 client）."""

    client: Any  # redis.asyncio.Redis or fakeredis.aioredis.FakeRedis
    channel: str
    key: str
    ttl_seconds: int

    async def publish_prediction(self, payload: PredictionPayload) -> None:
        """Set + publish。任何一條失敗 swallow + log warning，不 raise."""
        body = payload.model_dump_json()

        try:
            await self.client.set(self.key, body, ex=self.ttl_seconds)
        except Exception:
            traceback.print_exc()
            logger.warning("redis_set_failed key=%s", self.key)

        try:
            await self.client.publish(self.channel, body)
        except Exception:
            traceback.print_exc()
            logger.warning("redis_publish_failed channel=%s", self.channel)

    async def get_latest(self) -> PredictionPayload | None:
        """GET key → PredictionPayload；過期或不存在回 None；解析失敗回 None."""
        try:
            raw = await self.client.get(self.key)
        except Exception:
            traceback.print_exc()
            logger.warning("redis_get_failed key=%s", self.key)
            return None
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return PredictionPayload.model_validate(json.loads(raw))
        except Exception:
            traceback.print_exc()
            logger.warning("redis_payload_malformed key=%s", self.key)
            return None

    async def ping(self) -> bool:
        """供 /healthz 用；連不上回 False（不 raise）."""
        try:
            await self.client.ping()
            return True
        except Exception:
            return False
