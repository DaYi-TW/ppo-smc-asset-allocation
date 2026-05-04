"""Unit tests：``build_observation`` 布局與 NaN 替換（T019、FR-010/10a/12）。"""

from __future__ import annotations

import numpy as np

from portfolio_env import PortfolioEnv, PortfolioEnvConfig


def test_observation_shape_with_smc(portfolio_default_config):
    env = PortfolioEnv(portfolio_default_config)
    obs, _ = env.reset(seed=42)
    assert obs.shape == (63,)
    assert obs.dtype == np.float32


def test_observation_shape_without_smc(tmp_portfolio_data_dir):
    cfg = PortfolioEnvConfig(data_root=tmp_portfolio_data_dir, include_smc=False)
    env = PortfolioEnv(cfg)
    obs, _ = env.reset(seed=42)
    assert obs.shape == (33,)
    assert obs.dtype == np.float32


def test_observation_no_nan_inf(portfolio_default_config):
    env = PortfolioEnv(portfolio_default_config)
    obs, _ = env.reset(seed=42)
    assert not np.isnan(obs).any()
    assert not np.isinf(obs).any()


def test_observation_smc_segment_encoding(portfolio_default_config):
    """``bos_signal`` / ``choch_signal`` ∈ {-1.0, 0.0, 1.0}；``ob_touched`` ∈ {0.0, 1.0}（FR-010a）。"""
    env = PortfolioEnv(portfolio_default_config)
    env.reset(seed=42)
    rng = np.random.default_rng(0)
    for _ in range(10):
        a = rng.dirichlet(np.ones(7)).astype(np.float32)
        obs, _, _, _, _ = env.step(a)
        # SMC 區段 [24:54] — 對 6 檔每檔 5 維：bos, choch, fvg_dist, ob_touched, ob_dist_ratio
        for i in range(6):
            base = 24 + 5 * i
            bos = obs[base + 0]
            choch = obs[base + 1]
            ob_t = obs[base + 3]
            assert bos in (-1.0, 0.0, 1.0), f"bos_signal[{i}] = {bos}"
            assert choch in (-1.0, 0.0, 1.0), f"choch_signal[{i}] = {choch}"
            assert ob_t in (0.0, 1.0), f"ob_touched[{i}] = {ob_t}"


def test_observation_weights_segment_matches_current(portfolio_default_config):
    env = PortfolioEnv(portfolio_default_config)
    obs, _ = env.reset(seed=42)
    # weights 區段在 include_smc=True 時為 [56:63]
    np.testing.assert_allclose(obs[56:63], env.current_weights, atol=1e-6)


def test_no_smc_segment_alignment(tmp_portfolio_data_dir):
    """``include_smc=False`` 時 [0:24] 價格區段、[24:26] macro、[26:33] weights 對齊。"""
    cfg_full = PortfolioEnvConfig(data_root=tmp_portfolio_data_dir, include_smc=True)
    cfg_price = PortfolioEnvConfig(data_root=tmp_portfolio_data_dir, include_smc=False)
    env_full = PortfolioEnv(cfg_full)
    env_price = PortfolioEnv(cfg_price)
    obs_f, _ = env_full.reset(seed=42)
    obs_p, _ = env_price.reset(seed=42)
    # 價格區段
    np.testing.assert_array_equal(obs_f[:24], obs_p[:24])
    # macro
    np.testing.assert_array_equal(obs_f[54:56], obs_p[24:26])
    # weights
    np.testing.assert_array_equal(obs_f[56:63], obs_p[26:33])
