"""Unit tests：``PortfolioEnvConfig`` / ``RewardConfig`` (T007、spec FR-007/22/23/27)。"""

from __future__ import annotations

import dataclasses
from datetime import date
from pathlib import Path

import pytest

from portfolio_env import PortfolioEnvConfig, RewardConfig

# ---- RewardConfig ----


def test_reward_config_defaults_match_research_r3():
    rc = RewardConfig()
    assert rc.lambda_mdd == 1.0
    assert rc.lambda_turnover == 0.0015


def test_reward_config_negative_mdd_raises():
    with pytest.raises(ValueError, match="lambda_mdd"):
        RewardConfig(lambda_mdd=-0.1)


def test_reward_config_negative_turnover_raises():
    with pytest.raises(ValueError, match="lambda_turnover"):
        RewardConfig(lambda_turnover=-0.001)


def test_reward_config_frozen():
    rc = RewardConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        rc.lambda_mdd = 0.5  # type: ignore[misc]


def test_reward_config_zero_lambdas_legal():
    """SC-007 ablation 場景：兩個 lambda 同時為 0 不應 raise。"""
    rc = RewardConfig(lambda_mdd=0.0, lambda_turnover=0.0)
    assert rc.lambda_mdd == 0.0
    assert rc.lambda_turnover == 0.0


# ---- PortfolioEnvConfig ----


def test_portfolio_env_config_defaults():
    cfg = PortfolioEnvConfig(data_root=Path("data/raw"))
    assert cfg.assets == ("NVDA", "AMD", "TSM", "MU", "GLD", "TLT")
    assert cfg.include_smc is True
    assert cfg.position_cap == 0.4
    assert cfg.base_slippage_bps == 5.0
    assert cfg.initial_nav == 1.0
    assert cfg.render_mode is None


def test_portfolio_env_config_invalid_render_mode_raises():
    with pytest.raises(ValueError, match="render_mode"):
        PortfolioEnvConfig(data_root=Path("/tmp"), render_mode="rgb_array")


def test_portfolio_env_config_position_cap_too_low_raises():
    """position_cap × len(assets) < 1.0 違反 simplex 可解性（FR-022）。"""
    with pytest.raises(ValueError, match="position_cap"):
        PortfolioEnvConfig(data_root=Path("/tmp"), position_cap=0.1)  # 0.1*6=0.6 < 1


def test_portfolio_env_config_position_cap_zero_raises():
    with pytest.raises(ValueError, match="position_cap"):
        PortfolioEnvConfig(data_root=Path("/tmp"), position_cap=0.0)


def test_portfolio_env_config_position_cap_above_one_raises():
    with pytest.raises(ValueError, match="position_cap"):
        PortfolioEnvConfig(data_root=Path("/tmp"), position_cap=1.5)


def test_portfolio_env_config_negative_initial_nav_raises():
    with pytest.raises(ValueError, match="initial_nav"):
        PortfolioEnvConfig(data_root=Path("/tmp"), initial_nav=-1.0)


def test_portfolio_env_config_zero_initial_nav_raises():
    with pytest.raises(ValueError, match="initial_nav"):
        PortfolioEnvConfig(data_root=Path("/tmp"), initial_nav=0.0)


def test_portfolio_env_config_negative_slippage_raises():
    with pytest.raises(ValueError, match="base_slippage_bps"):
        PortfolioEnvConfig(data_root=Path("/tmp"), base_slippage_bps=-0.5)


def test_portfolio_env_config_frozen():
    cfg = PortfolioEnvConfig(data_root=Path("/tmp"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.position_cap = 0.5  # type: ignore[misc]


def test_portfolio_env_config_render_mode_ansi_legal():
    cfg = PortfolioEnvConfig(data_root=Path("/tmp"), render_mode="ansi")
    assert cfg.render_mode == "ansi"


def test_portfolio_env_config_dates_optional():
    cfg = PortfolioEnvConfig(
        data_root=Path("/tmp"),
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )
    assert cfg.start_date == date(2024, 1, 1)
    assert cfg.end_date == date(2024, 12, 31)
