"""T014 — Single-step PPO inference helper.

對應 spec 010 FR-020。包裝 sb3 ``policy.predict`` + ``evaluate_actions``，輸出
``ActionResult`` 含 raw / normalized / log_prob / entropy 四元組，與 009
TrajectoryFrame.action 結構一致。

設計考量：
* 不重新建立 env — 接受 ``obs: np.ndarray`` 與已就緒 ``policy``。
* deterministic=True（FR-021 推理模式），與 evaluator 一致。
* log_prob / entropy 失敗時 fallback 為 0.0（與 evaluator
  ``policy_action_log_prob_entropy`` 同樣 contract）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ActionResult:
    """Single-step inference output。對齊 009 ``ActionVector`` schema。

    * ``raw`` — policy 輸出（softmax 前的 logits 或 raw action）。
    * ``normalized`` — 套 softmax 後的 simplex weights，length 7。
    * ``log_prob`` — Gaussian 分佈下該 action 的 log-likelihood。
    * ``entropy`` — 該 action 之 distribution entropy。
    """

    raw: list[float]
    normalized: list[float]
    log_prob: float
    entropy: float


def _softmax(x: np.ndarray) -> np.ndarray:
    a = np.asarray(x, dtype=np.float64)
    a = a - a.max()
    ex = np.exp(a)
    return (ex / ex.sum()).astype(np.float32)


def single_step_inference(
    policy: Any, obs: np.ndarray, *, deterministic: bool = True
) -> ActionResult:
    """跑一次 ``policy.predict`` 並嘗試取 log_prob / entropy。

    Args:
        policy: sb3 ``PPO`` model（或 duck-typed mock with ``predict`` +
            optional ``policy.evaluate_actions``）。
        obs: shape (obs_dim,) ndarray — 通常來自 ``env.reset()`` /
            ``env.step()`` 的回傳。
        deterministic: True = greedy（推理預設）；False = 採樣。

    Returns:
        ``ActionResult`` — raw 7-vec + normalized simplex 7-vec + log_prob +
        entropy。

    Raises:
        TypeError / ValueError: ``policy.predict`` 拋例外時直接 propagate。
    """
    raw_action, _ = policy.predict(obs, deterministic=deterministic)
    raw_arr = np.asarray(raw_action, dtype=np.float32).reshape(-1)
    normalized = _softmax(raw_arr)

    log_prob = 0.0
    entropy = 0.0
    try:
        # sb3 PPO.policy.evaluate_actions expects (obs_tensor, action_tensor)
        import torch

        inner = getattr(policy, "policy", None)
        if inner is not None and hasattr(inner, "evaluate_actions"):
            obs_t = torch.as_tensor(np.asarray(obs).reshape(1, -1), dtype=torch.float32)
            act_t = torch.as_tensor(raw_arr.reshape(1, -1), dtype=torch.float32)
            _values, lp_t, ent_t = inner.evaluate_actions(obs_t, act_t)
            log_prob = float(lp_t.detach().cpu().numpy().reshape(-1)[0])
            entropy = float(ent_t.detach().cpu().numpy().reshape(-1)[0])
    except Exception:
        # 與 evaluator 一致：失敗 fallback 0，不阻塞 pipeline
        log_prob = 0.0
        entropy = 0.0

    return ActionResult(
        raw=[float(v) for v in raw_arr.tolist()],
        normalized=[float(v) for v in normalized.tolist()],
        log_prob=log_prob,
        entropy=entropy,
    )


__all__ = ["ActionResult", "single_step_inference"]
