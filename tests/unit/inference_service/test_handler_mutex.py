"""T011 — handler asyncio.Lock 互斥 (RED → GREEN at T016).

驗證 spec FR-003：scheduled / manual 兩條路徑共用同一 lock，第二個並發請求排隊。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_concurrent_runs_are_serialized() -> None:
    """兩個 await run_inference 並發 → 第二個 latency ≥ 第一個 duration."""
    from inference_service.handler import InferenceState, run_inference
    from inference_service.schemas import PredictionPayload

    # Build a fake state: lock + mocked _run_inference_unlocked that sleeps 0.5s.
    state = InferenceState(
        lock=asyncio.Lock(),
        policy=MagicMock(),
        env_factory=MagicMock(),
        last_inference_at_utc=None,
        last_inference_id=None,
        inference_count=0,
        inference_failure_count=0,
    )

    fake_payload_dict = {
        "as_of_date": "2026-04-28",
        "next_trading_day_target": "first session after 2026-04-28 (apply at next open)",
        "policy_path": "fake.zip",
        "deterministic": True,
        "target_weights": {
            "NVDA": 0.1, "AMD": 0.1, "TSM": 0.1, "MU": 0.1,
            "GLD": 0.1, "TLT": 0.1, "CASH": 0.4,
        },
        "weights_capped": False,
        "renormalized": False,
        "context": {
            "data_root": "data/raw",
            "include_smc": True,
            "n_warmup_steps": 100,
            "current_nav_at_as_of": 1.0,
        },
        "triggered_by": "manual",
        "inference_id": "00000000-0000-0000-0000-000000000000",
        "inferred_at_utc": "2026-05-06T00:00:00+00:00",
    }

    import uuid as uuid_mod

    async def slow_runner(_state: InferenceState, triggered_by: str) -> PredictionPayload:
        await asyncio.sleep(0.5)
        d = dict(fake_payload_dict)
        d["triggered_by"] = triggered_by
        d["inference_id"] = str(uuid_mod.uuid4())
        return PredictionPayload.model_validate(d)

    # Patch the inner unlocked path
    import inference_service.handler as handler_mod

    handler_mod._run_inference_unlocked = AsyncMock(side_effect=slow_runner)  # type: ignore[attr-defined]

    start = asyncio.get_event_loop().time()
    results = await asyncio.gather(
        run_inference(state, "manual"),
        run_inference(state, "manual"),
    )
    elapsed = asyncio.get_event_loop().time() - start

    # Two serialized 0.5s runs ≥ 1.0s wall clock (allow scheduler jitter).
    assert elapsed >= 0.95, f"expected ≥0.95s serialized, got {elapsed:.3f}s"
    assert len(results) == 2
    assert results[0].inference_id != results[1].inference_id


@pytest.mark.asyncio
async def test_lock_releases_on_exception() -> None:
    """run_inference 內部 raise → lock MUST 釋放（finally 邏輯）."""
    from inference_service.handler import InferenceState, run_inference

    state = InferenceState(
        lock=asyncio.Lock(),
        policy=MagicMock(),
        env_factory=MagicMock(),
        last_inference_at_utc=None,
        last_inference_id=None,
        inference_count=0,
        inference_failure_count=0,
    )

    import inference_service.handler as handler_mod

    handler_mod._run_inference_unlocked = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError):
        await run_inference(state, "manual")

    # If lock was leaked, the next acquire would deadlock; assert it succeeds quickly.
    await asyncio.wait_for(state.lock.acquire(), timeout=1.0)
    state.lock.release()
    assert state.inference_failure_count == 1
