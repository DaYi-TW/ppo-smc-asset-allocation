"""inference handler — scheduled / manual 兩條入口共用 ``run_inference()``.

對應 spec FR-001 / FR-003 / G-I-1 / G-III-3.

設計（data-model §5）：
    * ``InferenceState``：lock + eager-loaded policy + env_factory + counters
    * ``run_inference(state, triggered_by)``：``async with state.lock``，
      呼叫 ``_run_inference_unlocked()``（內部跑 env episode + 收 final action）
    * lock 釋放 by ``async with``，例外時計數 inference_failure_count
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from .schemas import PredictionContext, PredictionPayload, TargetWeights

_ASSET_NAMES = ("NVDA", "AMD", "TSM", "MU", "GLD", "TLT", "CASH")


@dataclass
class InferenceState:
    """handler 內部狀態（process-level，FastAPI lifespan 建立）."""

    lock: asyncio.Lock
    policy: Any
    env_factory: Callable[[], Any]
    last_inference_at_utc: datetime | None = None
    last_inference_id: str | None = None
    inference_count: int = 0
    inference_failure_count: int = 0

    # 啟動時記錄、給 healthz 用
    started_at_utc: datetime = field(default_factory=lambda: datetime.now(UTC))
    policy_path: str = ""
    data_root: str = ""
    include_smc: bool = True
    seed: int = 42


def _make_softmax_wrapper() -> type:
    """重建訓練側的 ``_SoftmaxActionWrapper``（與 ``predict.py`` / ``train.py`` 一致）.

    G-II-1 + G-III-3：handler 必須走 env.process_action pipeline，不能繞過 softmax
    後直接吐 raw action。
    """
    import gymnasium

    class _SoftmaxActionWrapper(gymnasium.ActionWrapper):
        def __init__(self, env: Any) -> None:
            super().__init__(env)
            self.action_space = gymnasium.spaces.Box(
                low=-10.0,
                high=10.0,
                shape=env.action_space.shape,
                dtype=np.float32,
            )

        def action(self, action: np.ndarray) -> np.ndarray:
            a = np.asarray(action, dtype=np.float64)
            a = a - a.max()
            ex = np.exp(a)
            simplex = ex / ex.sum()
            return simplex.astype(np.float32)

    return _SoftmaxActionWrapper


def init_state(config: Any) -> InferenceState:
    """eager-load PPO policy + 配置 env_factory（lifespan startup）.

    對應 data-model §5 InferenceState lifecycle.
    """
    from stable_baselines3 import PPO

    from portfolio_env import PortfolioEnv, PortfolioEnvConfig

    softmax_cls = _make_softmax_wrapper()

    def _build_env() -> Any:
        cfg = PortfolioEnvConfig(
            data_root=Path(config.data_root),
            include_smc=config.include_smc,
            start_date=None,
            end_date=None,  # 走到資料尾
        )
        return softmax_cls(PortfolioEnv(cfg))

    # 載一個臨時 env 給 PPO.load 對齊 obs_space
    bootstrap_env = _build_env()
    policy = PPO.load(str(config.policy_path), env=bootstrap_env, device="auto")

    return InferenceState(
        lock=asyncio.Lock(),
        policy=policy,
        env_factory=_build_env,
        policy_path=str(config.policy_path),
        data_root=str(config.data_root),
        include_smc=config.include_smc,
        seed=config.seed,
    )


async def _run_inference_unlocked(state: InferenceState, triggered_by: str) -> PredictionPayload:
    """實際跑一次 inference（caller MUST hold state.lock）.

    把 PPO predict + env.step 的 blocking 部分丟到 thread pool，避免阻塞 event loop.
    """
    loop = asyncio.get_running_loop()

    def _blocking_run() -> tuple[dict[str, Any], int, np.ndarray, str]:
        env = state.env_factory()
        obs, info = env.reset(seed=state.seed)
        n_warmup = 0
        while True:
            action, _ = state.policy.predict(obs, deterministic=True)
            obs, _r, terminated, truncated, info = env.step(action)
            n_warmup += 1
            if terminated or truncated:
                break
        final_weights = np.asarray(info["weights"], dtype=np.float64)
        return info, n_warmup, final_weights, info["date"]

    info, n_warmup, final_weights, as_of_str = await loop.run_in_executor(None, _blocking_run)

    weights_dict = {name: float(final_weights[i]) for i, name in enumerate(_ASSET_NAMES)}

    return PredictionPayload(
        as_of_date=as_of_str,
        next_trading_day_target=f"first session after {as_of_str} (apply at next open)",
        policy_path=state.policy_path,
        deterministic=True,
        target_weights=TargetWeights(**weights_dict),
        weights_capped=bool(info.get("position_capped", False)),
        renormalized=bool(info.get("action_renormalized", False)),
        context=PredictionContext(
            data_root=state.data_root,
            include_smc=state.include_smc,
            n_warmup_steps=int(n_warmup),
            current_nav_at_as_of=float(info["nav"]),
        ),
        triggered_by=triggered_by,  # type: ignore[arg-type]
        inference_id=str(uuid.uuid4()),
        inferred_at_utc=datetime.now(UTC).isoformat(),
    )


async def run_inference(state: InferenceState, triggered_by: str) -> PredictionPayload:
    """共用 inference handler — 兩條入口都走這裡（FR-003 mutex via asyncio.Lock）.

    Args:
        state: 啟動時建立的 ``InferenceState``.
        triggered_by: ``"scheduled"`` 或 ``"manual"``.

    Raises:
        Exception: 任何 inference 內部錯誤（counters 已更新、lock 已釋放）.
    """
    async with state.lock:
        try:
            payload = await _run_inference_unlocked(state, triggered_by)
        except Exception:
            state.inference_failure_count += 1
            raise
        state.inference_count += 1
        state.last_inference_at_utc = datetime.now(UTC)
        state.last_inference_id = payload.inference_id
        return payload
