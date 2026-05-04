"""Performance tests：``__init__`` ≤ 10s、reset+episode ≤ 20s（T032/T033、SC-001）。

由於 mini fixture 規模 ~80 trading day（vs. 真實 2090 day 的 3% 規模），這些
benchmark 在 CI 上會穩穩通過；切到真實 ``data/raw/`` 才能驗證真實預算。
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from portfolio_env import PortfolioEnv


@pytest.mark.benchmark
def test_init_under_budget(portfolio_default_config):
    """``PortfolioEnv(config)`` 建構耗時 ≤ 10 秒（SC-001 子預算）。"""
    t0 = time.perf_counter()
    env = PortfolioEnv(portfolio_default_config)
    elapsed = time.perf_counter() - t0
    assert elapsed <= 10.0, f"__init__ took {elapsed:.2f}s, budget 10s"
    env.close()


@pytest.mark.benchmark
def test_episode_under_budget(portfolio_default_config):
    """``reset() + step loop`` 耗時 ≤ 20 秒（SC-001 子預算）。"""
    env = PortfolioEnv(portfolio_default_config)
    t0 = time.perf_counter()
    env.reset(seed=42)
    rng = np.random.default_rng(42)
    while True:
        a = rng.dirichlet(np.ones(7)).astype(np.float32)
        _, _, term, _, _ = env.step(a)
        if term:
            break
    elapsed = time.perf_counter() - t0
    assert elapsed <= 20.0, f"episode took {elapsed:.2f}s, budget 20s"
    env.close()
