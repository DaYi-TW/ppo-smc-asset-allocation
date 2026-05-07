"""T030 — Scheduler 失敗不停（FR-010 / SC-006）.

第一次 callback 噴 RuntimeError，scheduler 仍持續 fire 第二次。
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_scheduler_survives_callback_exception(
    fake_state: Any,
    fake_payload_dict: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第一次 run_inference raise → second trigger 仍要 fire."""
    from inference_service.scheduler import init_scheduler
    from inference_service.schemas import PredictionPayload

    call_count = 0

    async def flaky_run(state: Any, triggered_by: str) -> PredictionPayload:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("first call boom")
        d = dict(fake_payload_dict)
        d["triggered_by"] = triggered_by
        return PredictionPayload.model_validate(d)

    publisher = AsyncMock()

    import inference_service.scheduler as sched_mod

    monkeypatch.setattr(sched_mod, "run_inference", flaky_run)

    scheduler = init_scheduler(
        state=fake_state,
        cron_expr="*/1 * * * * *",
        timezone_name="UTC",
        redis_publisher=publisher,
    )
    scheduler.start()
    try:
        await asyncio.sleep(3.5)
    finally:
        scheduler.shutdown(wait=False)

    # 至少要看到 ≥2 次嘗試（第一次 raise、第二次 OK）
    assert call_count >= 2, f"expected ≥2 fires (incl. recovery), got {call_count}"
