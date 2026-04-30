"""Unit test：SMC 預計算僅在 ``__init__`` 階段執行（T017、research R7、SC-001）。"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np

from portfolio_env import PortfolioEnv


def test_batch_compute_called_once_per_asset_at_init(portfolio_default_config):
    """``__init__`` 後 ``batch_compute`` 呼叫次數 = ``len(assets)``；step 不再調用。"""
    with patch(
        "portfolio_env.data_loader.batch_compute",
        side_effect=__import__("smc_features").batch_compute,
    ) as spy:
        env = PortfolioEnv(portfolio_default_config)
    init_calls = spy.call_count
    assert init_calls == len(portfolio_default_config.assets)

    # step 階段不應再觸發 batch_compute（精確：spy 不會被再次呼叫）
    with patch("portfolio_env.data_loader.batch_compute") as step_spy:
        env.reset(seed=0)
        rng = np.random.default_rng(0)
        for _ in range(5):
            a = rng.dirichlet(np.ones(7)).astype(np.float32)
            env.step(a)
        assert step_spy.call_count == 0
    env.close()


def test_smc_buffer_dtype_and_shape(portfolio_default_config):
    """precomputed SMC buffer 為 float32 且 shape = (T, 5)。"""
    env = PortfolioEnv(portfolio_default_config)
    assert env._env_data.smc_features is not None
    n_steps = env._env_data.trading_days.size
    for ticker, arr in env._env_data.smc_features.items():
        assert arr.dtype == np.float32, f"{ticker} dtype != float32"
        assert arr.shape == (n_steps, 5), f"{ticker} shape != (T,5)"
    env.close()
