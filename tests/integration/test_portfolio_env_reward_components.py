"""US2 integration tests：reward 三項拆解 + λ 消融（T039-T041、SC-007、FR-018）。

* 兩 env 同 seed → reward 完全相同（baseline）。
* λ_mdd=0、λ_turnover=0 → reward == log_return（容差 1e-12，對應 SC-007 ablation）。
* reward 拆解總和（log_return - drawdown_penalty - turnover_penalty） == reward
  （容差 1e-9）。
"""

from __future__ import annotations

import numpy as np

from portfolio_env import PortfolioEnv, PortfolioEnvConfig, RewardConfig


def _run(env: PortfolioEnv, seed: int):
    env.reset(seed=seed)
    rng = np.random.default_rng(seed)
    rewards, log_rs, dd_pen, turn_pen = [], [], [], []
    while True:
        a = rng.dirichlet(np.ones(7)).astype(np.float32)
        _, r, term, _, info = env.step(a)
        rewards.append(r)
        comp = info["reward_components"]
        log_rs.append(comp["log_return"])
        dd_pen.append(comp["drawdown_penalty"])
        turn_pen.append(comp["turnover_penalty"])
        if term:
            break
    return (
        np.array(rewards),
        np.array(log_rs),
        np.array(dd_pen),
        np.array(turn_pen),
    )


def test_reward_components_sum_to_reward(portfolio_default_config):
    """``reward == log_return - drawdown_penalty - turnover_penalty``（FR-018）。"""
    env = PortfolioEnv(portfolio_default_config)
    rewards, log_rs, dd_pen, turn_pen = _run(env, 42)
    composed = log_rs - dd_pen - turn_pen
    np.testing.assert_allclose(rewards, composed, atol=1e-9, rtol=0.0)


def test_lambda_zero_ablation_reduces_to_log_return(tmp_portfolio_data_dir):
    """λ_mdd=0 + λ_turnover=0 → reward 完全等於 log_return（SC-007，atol=1e-12）。"""
    cfg = PortfolioEnvConfig(
        data_root=tmp_portfolio_data_dir,
        reward_config=RewardConfig(lambda_mdd=0.0, lambda_turnover=0.0),
    )
    env = PortfolioEnv(cfg)
    rewards, log_rs, dd_pen, turn_pen = _run(env, 42)
    # 即使 λ=0，penalty 計算仍會跑（但乘以 0 → 0.0）
    np.testing.assert_array_equal(dd_pen, np.zeros_like(dd_pen))
    np.testing.assert_array_equal(turn_pen, np.zeros_like(turn_pen))
    np.testing.assert_allclose(rewards, log_rs, atol=1e-12, rtol=0.0)


def test_two_envs_same_seed_yield_identical_components(portfolio_default_config):
    """兩個獨立 env + 同 seed → 每步三項分量逐元素 byte-identical。"""
    env_a = PortfolioEnv(portfolio_default_config)
    env_b = PortfolioEnv(portfolio_default_config)
    a_r, a_log, a_dd, a_turn = _run(env_a, 7)
    b_r, b_log, b_dd, b_turn = _run(env_b, 7)
    np.testing.assert_array_equal(a_r, b_r)
    np.testing.assert_array_equal(a_log, b_log)
    np.testing.assert_array_equal(a_dd, b_dd)
    np.testing.assert_array_equal(a_turn, b_turn)


def test_drawdown_penalty_nonnegative(portfolio_default_config):
    """drawdown_penalty ≥ 0（peak 永不低於 NAV，公式定義所致）。"""
    env = PortfolioEnv(portfolio_default_config)
    _, _, dd_pen, _ = _run(env, 99)
    assert (dd_pen >= 0.0).all()


def test_turnover_penalty_nonnegative(portfolio_default_config):
    env = PortfolioEnv(portfolio_default_config)
    _, _, _, turn_pen = _run(env, 99)
    assert (turn_pen >= 0.0).all()
