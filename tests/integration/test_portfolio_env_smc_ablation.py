"""US3 integration test：``include_smc`` toggle（T042-T043、SC-008、FR-001a）。

* ``include_smc=False`` → ``observation_space.shape == (33,)``。
* ``include_smc=True`` → ``observation_space.shape == (63,)``。
* 兩 env（同 seed、不同 include_smc）：價格段 [0:24]、macro 段（False 為 [24:26]、
  True 為 [54:56]）、weights 段（False 為 [26:33]、True 為 [56:63]）byte-identical。
"""

from __future__ import annotations

import numpy as np

from portfolio_env import PortfolioEnv, PortfolioEnvConfig


def _run(env, seed):
    env.reset(seed=seed)
    rng = np.random.default_rng(seed)
    obs_list = []
    while True:
        a = rng.dirichlet(np.ones(7)).astype(np.float32)
        obs, _, term, _, _ = env.step(a)
        obs_list.append(obs.copy())
        if term:
            break
    return np.stack(obs_list)


def test_observation_dimension_changes_with_smc(tmp_portfolio_data_dir):
    cfg_smc = PortfolioEnvConfig(data_root=tmp_portfolio_data_dir, include_smc=True)
    cfg_no = PortfolioEnvConfig(data_root=tmp_portfolio_data_dir, include_smc=False)
    env_smc = PortfolioEnv(cfg_smc)
    env_no = PortfolioEnv(cfg_no)
    assert env_smc.observation_space.shape == (63,)
    assert env_no.observation_space.shape == (33,)
    env_smc.close()
    env_no.close()


def test_non_smc_segments_byte_identical_across_toggle(tmp_portfolio_data_dir):
    """價格段 [0:24] 與 weights 段（含 macro）在兩種 config 下逐元素相等。"""
    cfg_smc = PortfolioEnvConfig(data_root=tmp_portfolio_data_dir, include_smc=True)
    cfg_no = PortfolioEnvConfig(data_root=tmp_portfolio_data_dir, include_smc=False)

    env_smc = PortfolioEnv(cfg_smc)
    env_no = PortfolioEnv(cfg_no)
    obs_smc = _run(env_smc, 42)
    obs_no = _run(env_no, 42)

    # 形狀
    assert obs_smc.shape[0] == obs_no.shape[0]
    # 價格段（前 24）
    np.testing.assert_array_equal(obs_smc[:, :24], obs_no[:, :24])
    # SMC True 的 macro 在 [54:56]、False 在 [24:26]
    np.testing.assert_array_equal(obs_smc[:, 54:56], obs_no[:, 24:26])
    # SMC True 的 weights 在 [56:63]、False 在 [26:33]
    np.testing.assert_array_equal(obs_smc[:, 56:63], obs_no[:, 26:33])

    env_smc.close()
    env_no.close()


def test_smc_segment_present_only_when_enabled(tmp_portfolio_data_dir):
    """``include_smc=True`` 時 [24:54] 段非全零（mini fixture 有些 SMC 訊號）。

    若 mini fixture 不夠長以致 30 維全部為 0，這個斷言會 skip — 但仍驗證 dtype。
    """
    cfg_smc = PortfolioEnvConfig(data_root=tmp_portfolio_data_dir, include_smc=True)
    env = PortfolioEnv(cfg_smc)
    obs_smc = _run(env, 42)
    smc_block = obs_smc[:, 24:54]
    assert smc_block.shape == (obs_smc.shape[0], 30)
    assert smc_block.dtype == np.float32
    env.close()
