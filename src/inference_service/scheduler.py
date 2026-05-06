"""APScheduler cron + pytz ET timezone + DST 安全 + 失敗不停 scheduler。

對應 spec FR-002 / FR-010 / SC-002。Phase 4 T031 實作。
"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .handler import InferenceState, run_inference
from .schemas import PredictionPayload

logger = logging.getLogger(__name__)


def _build_cron_trigger(cron_expr: str, timezone_name: str) -> CronTrigger:
    """Build CronTrigger，支援 5-field 與 6-field（second-level，給測試用快 trigger）。"""
    tz = pytz.timezone(timezone_name)
    parts = cron_expr.split()
    if len(parts) == 6:
        second, minute, hour, day, month, day_of_week = parts
        return CronTrigger(
            second=second,
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone=tz,
        )
    return CronTrigger.from_crontab(cron_expr, timezone=tz)


def init_scheduler(
    *,
    state: InferenceState,
    cron_expr: str,
    timezone_name: str,
    redis_publisher: Callable[[PredictionPayload], Awaitable[Any]] | None,
) -> AsyncIOScheduler:
    """建立 AsyncIOScheduler 並註冊 daily inference job.

    Callback：
        1. ``await run_inference(state, "scheduled")`` — 跑推理（失敗不停 scheduler）
        2. ``await redis_publisher(payload)`` — 廣播（publish 失敗不影響後續 trigger）

    Args:
        state: 共用 InferenceState（與 HTTP layer 同 process / 同 lock）
        cron_expr: 5-field cron 或 6-field（second-level，僅供測試）
        timezone_name: e.g. ``"America/New_York"``（pytz 名稱，DST-safe）
        redis_publisher: optional async callable；None = skip publish

    Returns:
        Started-able ``AsyncIOScheduler``（caller 自行 ``.start()`` / ``.shutdown()``）
    """
    tz = pytz.timezone(timezone_name)
    scheduler = AsyncIOScheduler(timezone=tz)
    trigger = _build_cron_trigger(cron_expr, timezone_name)

    async def _job() -> None:
        try:
            payload = await run_inference(state, "scheduled")
        except Exception:
            traceback.print_exc()
            logger.error("scheduled_inference_failed")
            return
        logger.info("scheduled_trigger_fired inference_id=%s", payload.inference_id)

        if redis_publisher is not None:
            try:
                await redis_publisher(payload)
            except Exception:
                traceback.print_exc()
                logger.warning("redis_publish_failed inference_id=%s", payload.inference_id)

    scheduler.add_job(
        _job,
        trigger=trigger,
        id="daily_inference",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    return scheduler
