"""T012 — Reproducibility (G-I-3 / SC-007).

相同 config 跑兩次 run_inference → target_weights byte-identical（容差 0.0）.

注意：這個 test 跑真 PPO load + episode，slow（~30s/round）；用 marker 讓 CI 可選跑。
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.asyncio
@pytest.mark.slow
async def test_two_runs_produce_byte_identical_weights(policy_path: Path, data_root: Path) -> None:
    """同 policy + 同 data + deterministic=True → 兩次 target_weights `==` 比對."""
    from inference_service.config import ServiceConfig
    from inference_service.handler import init_state, run_inference

    cfg = ServiceConfig(
        policy_path=policy_path,
        data_root=data_root,
        redis_url="redis://localhost:6379/0",
    )
    state = init_state(cfg)

    p1 = await run_inference(state, "manual")
    p2 = await run_inference(state, "manual")

    # SC-007: 容差 0.0 — 用 dict equality 而非 isclose
    assert p1.target_weights.model_dump() == p2.target_weights.model_dump()
    assert p1.as_of_date == p2.as_of_date
    assert p1.context.current_nav_at_as_of == p2.context.current_nav_at_as_of
    # inference_id MUST 不同（每次 uuid4）
    assert p1.inference_id != p2.inference_id
