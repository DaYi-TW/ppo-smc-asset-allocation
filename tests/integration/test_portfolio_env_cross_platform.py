"""Integration test：跨次 reset 同 seed trajectory byte-identical（T031、SC-002、SC-005）。

跨平台 fixture 比對暫以「同機器同進程內兩次 reset」為代理；CI 三平台矩陣
（research R2）會跑同樣腳本並透過 fixture 序列檔比對，需要 ``data/raw/`` 真實
快照後再 wire。
"""

from __future__ import annotations

import numpy as np

from portfolio_env import PortfolioEnv


def test_two_resets_produce_byte_identical_navs(portfolio_default_config, set_blas_single_thread):
    """同進程 reset(seed=42) 兩次 + 同 action 序列 → NAV 完全相等（容差 0.0）。"""

    def run(env, seed):
        env.reset(seed=seed)
        rng = np.random.default_rng(seed)
        navs, rewards = [], []
        while True:
            a = rng.dirichlet(np.ones(7)).astype(np.float32)
            _, r, term, _, info = env.step(a)
            navs.append(info["nav"])
            rewards.append(r)
            if term:
                break
        return np.array(navs), np.array(rewards)

    env = PortfolioEnv(portfolio_default_config)
    navs_a, rewards_a = run(env, 42)
    navs_b, rewards_b = run(env, 42)
    np.testing.assert_array_equal(navs_a, navs_b)
    np.testing.assert_array_equal(rewards_a, rewards_b)


def test_two_independent_envs_same_seed(portfolio_default_config, set_blas_single_thread):
    """兩個獨立 env instance + 同 seed → byte-identical（容差 1e-9，SC-002）。"""

    def run(seed):
        env = PortfolioEnv(portfolio_default_config)
        env.reset(seed=seed)
        rng = np.random.default_rng(seed)
        navs = []
        while True:
            a = rng.dirichlet(np.ones(7)).astype(np.float32)
            _, _, term, _, info = env.step(a)
            navs.append(info["nav"])
            if term:
                break
        return np.array(navs)

    a = run(42)
    b = run(42)
    np.testing.assert_allclose(a, b, atol=1e-9, rtol=0.0)
