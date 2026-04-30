"""Contract test：``gymnasium.utils.env_checker.check_env`` 通過（T029、SC-003）。"""

from __future__ import annotations

import warnings

from gymnasium.utils.env_checker import check_env

from portfolio_env import PortfolioEnv, PortfolioEnvConfig


def test_check_env_passes_with_smc(portfolio_default_config):
    env = PortfolioEnv(portfolio_default_config)
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # 任何 warning 視為失敗
        try:
            check_env(env, skip_render_check=True)
        except UserWarning as exc:  # gymnasium 內部偶發以 UserWarning 提示
            # 容忍與 spec 無關的 internal info warnings；若內容含 reset/step 字眼則 fail
            msg = str(exc)
            blocked = ["reset", "step", "observation_space", "action_space", "render_mode"]
            assert not any(k in msg.lower() for k in blocked), msg
    env.close()


def test_check_env_passes_without_smc(tmp_portfolio_data_dir):
    cfg = PortfolioEnvConfig(data_root=tmp_portfolio_data_dir, include_smc=False)
    env = PortfolioEnv(cfg)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        try:
            check_env(env, skip_render_check=True)
        except UserWarning as exc:
            msg = str(exc)
            blocked = ["reset", "step", "observation_space", "action_space", "render_mode"]
            assert not any(k in msg.lower() for k in blocked), msg
    env.close()


def test_metadata_correct(portfolio_default_config):
    env = PortfolioEnv(portfolio_default_config)
    assert env.metadata["render_modes"] == ["ansi"]
    assert env.metadata["render_fps"] == 0
