"""Integration test：以 Dirichlet 隨機策略跑滿 episode（T030、US1 acceptance）。"""

from __future__ import annotations

import numpy as np

from portfolio_env import PortfolioEnv


def test_random_episode_reaches_termination(portfolio_default_config):
    env = PortfolioEnv(portfolio_default_config)
    _obs, info = env.reset(seed=42)
    assert info["is_initial_step"] is True
    assert info["nav"] == 1.0
    rng = np.random.default_rng(42)

    n_trading_days = env._env_data.trading_days.size
    steps = 0
    while True:
        action = rng.dirichlet(np.ones(7)).astype(np.float32)
        _obs, reward, terminated, truncated, info = env.step(action)
        steps += 1
        # 不變式：NAV / reward 永不為 NaN/inf
        assert not np.isnan(info["nav"])
        assert not np.isinf(info["nav"])
        assert info["nav"] > 0.0
        assert not np.isnan(reward)
        assert not np.isinf(reward)
        # weights simplex
        assert abs(sum(info["weights"]) - 1.0) < 1e-6
        assert min(info["weights"]) >= 0.0
        assert max(info["weights"][:6]) <= 0.4 + 1e-6
        if terminated:
            break
        assert truncated is False

    assert steps == n_trading_days - 1


def test_two_resets_yield_identical_trajectory(portfolio_default_config):
    """同 seed → 同 trajectory（SC-005）。"""

    def run_episode(env, seed):
        env.reset(seed=seed)
        rng = np.random.default_rng(seed)
        navs = []
        rewards = []
        while True:
            a = rng.dirichlet(np.ones(7)).astype(np.float32)
            _, r, term, _, info = env.step(a)
            navs.append(info["nav"])
            rewards.append(r)
            if term:
                break
        return navs, rewards

    env_a = PortfolioEnv(portfolio_default_config)
    env_b = PortfolioEnv(portfolio_default_config)
    navs_a, rewards_a = run_episode(env_a, 42)
    navs_b, rewards_b = run_episode(env_b, 42)
    assert navs_a == navs_b
    assert rewards_a == rewards_b
