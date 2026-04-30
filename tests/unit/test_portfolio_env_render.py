"""Unit tests：``render()`` 行為（T027、FR-027）。"""

from __future__ import annotations

import numpy as np

from portfolio_env import PortfolioEnv, PortfolioEnvConfig


def test_render_mode_none_returns_none(portfolio_default_config):
    env = PortfolioEnv(portfolio_default_config)
    env.reset(seed=42)
    assert env.render() is None


def test_render_mode_ansi_returns_str(tmp_portfolio_data_dir):
    cfg = PortfolioEnvConfig(data_root=tmp_portfolio_data_dir, render_mode="ansi")
    env = PortfolioEnv(cfg)
    env.reset(seed=42)
    out = env.render()
    assert isinstance(out, str)
    assert "nav=" in out
    assert "weights=" in out


def test_render_after_step_includes_nav(tmp_portfolio_data_dir):
    cfg = PortfolioEnvConfig(data_root=tmp_portfolio_data_dir, render_mode="ansi")
    env = PortfolioEnv(cfg)
    env.reset(seed=42)
    rng = np.random.default_rng(42)
    a = rng.dirichlet(np.ones(7)).astype(np.float32)
    env.step(a)
    out = env.render()
    assert "nav=" in out
    assert "peak=" in out


def test_render_no_mode_param(portfolio_default_config):
    """Gymnasium 0.29+：``render`` 不接受 mode 參數。"""
    import inspect

    env = PortfolioEnv(portfolio_default_config)
    sig = inspect.signature(env.render)
    assert "mode" not in sig.parameters
