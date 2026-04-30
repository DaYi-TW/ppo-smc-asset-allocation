"""Reward 三項分量（憲法 Principle III、FR-006、FR-009、research R2、R3）。

公式：

* ``log_return = log(nav_t / nav_{t-1})``；首步強制為 ``0.0``（FR-006）。
* ``drawdown_t = max(0.0, (peak_t - nav_t) / peak_t)``；先更新 peak、再算 drawdown。
* ``turnover_t = 0.5 * sum(abs(w_t - w_{t-1}))``。
* ``reward = log_return - lambda_mdd * drawdown - lambda_turnover * turnover``。

組裝順序遵守 research R2：以 Python ``-`` 運算子按字面順序執行，**不**用
``numpy.subtract.reduce``，避免跨平台 BLAS reduction 順序差異。
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np


class RewardComponents(NamedTuple):
    log_return: float
    drawdown_penalty: float
    turnover_penalty: float
    reward: float


def compute_reward_components(
    prev_nav: float,
    nav: float,
    peak_nav: float,
    prev_weights: np.ndarray,
    weights: np.ndarray,
    lambda_mdd: float,
    lambda_turnover: float,
    is_initial_step: bool = False,
) -> RewardComponents:
    """計算 reward 三項分量並組合 reward。

    Args:
        prev_nav: 上一步 NAV。
        nav: 當前 NAV（已由 step 推進完成）。
        peak_nav: 當前 peak NAV（已含 ``max(peak_{t-1}, nav_{t-1})`` 更新）。
        prev_weights: 上一步權重 (7,)。
        weights: 當前權重 (7,)。
        lambda_mdd: drawdown 懲罰係數。
        lambda_turnover: turnover 懲罰係數。
        is_initial_step: True 時 ``log_return`` 強制為 0.0（FR-006 Edge Case）。

    Returns:
        ``RewardComponents(log_return, drawdown_penalty, turnover_penalty, reward)``。
    """
    log_return = 0.0 if is_initial_step else float(np.log(nav / prev_nav))

    drawdown = max(0.0, (peak_nav - nav) / peak_nav) if peak_nav > 0.0 else 0.0
    drawdown_penalty = float(lambda_mdd) * float(drawdown)

    diff = np.asarray(weights, dtype=np.float64) - np.asarray(prev_weights, dtype=np.float64)
    turnover = 0.5 * float(np.abs(diff).sum())
    turnover_penalty = float(lambda_turnover) * turnover

    # 字面順序組裝（research R2）
    reward = log_return - drawdown_penalty - turnover_penalty

    return RewardComponents(
        log_return=log_return,
        drawdown_penalty=drawdown_penalty,
        turnover_penalty=turnover_penalty,
        reward=reward,
    )


__all__ = ["RewardComponents", "compute_reward_components"]
