"""T028 — APScheduler basic trigger fire (RED → GREEN at T031).

對應 spec FR-002 / User Story 1。

設計：把 cron 設成「每秒一次」(* * * * * *)；mock run_inference + redis_publisher
為 noop；起 scheduler 後等 ≤ 5 秒，assert 至少 fire 1 次、payload triggered_by="scheduled"。
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_scheduler_fires_at_least_once(
    fake_state: Any,
    fake_payload_dict: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SCHEDULE_CRON='* * * * *'（每分鐘） + speed-mock → fire ≥1 次."""
    from inference_service.handler import run_inference  # noqa: F401
    from inference_service.scheduler import init_scheduler
    from inference_service.schemas import PredictionPayload

    fired_count = 0
    fired_triggers: list[str] = []

    async def fake_run_inference(state: Any, triggered_by: str) -> PredictionPayload:
        nonlocal fired_count
        fired_count += 1
        fired_triggers.append(triggered_by)
        d = dict(fake_payload_dict)
        d["triggered_by"] = triggered_by
        return PredictionPayload.model_validate(d)

    publisher = AsyncMock()

    import inference_service.scheduler as sched_mod

    monkeypatch.setattr(sched_mod, "run_inference", fake_run_inference)

    # 用每秒 trigger 加快測試
    scheduler = init_scheduler(
        state=fake_state,
        cron_expr="*/1 * * * * *",  # 每秒（second-level cron, APScheduler-only）
        timezone_name="UTC",
        redis_publisher=publisher,
    )
    scheduler.start()
    try:
        await asyncio.sleep(2.5)
    finally:
        scheduler.shutdown(wait=False)

    assert fired_count >= 1, f"expected ≥1 trigger fire, got {fired_count}"
    assert all(t == "scheduled" for t in fired_triggers), fired_triggers
    assert publisher.await_count == fired_count
