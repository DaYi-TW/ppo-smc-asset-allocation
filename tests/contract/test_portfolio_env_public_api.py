"""Contract test：``portfolio_env`` 公開 API 與 ``contracts/api.pyi`` 對齊（T010）。

對應 spec FR-002 / Constitution Principle V — 任何符號變動皆屬契約變更。
"""

from __future__ import annotations

import inspect

import portfolio_env


def test_all_export_set():
    """``__all__`` 內容與 contracts/api.pyi 之 ``__all__`` 一致。"""
    expected = {
        "PortfolioEnv",
        "PortfolioEnvConfig",
        "RewardConfig",
        "SMCParams",
        "info_to_json_safe",
        "make_default_env",
    }
    assert set(portfolio_env.__all__) == expected


def test_all_symbols_importable():
    for sym in portfolio_env.__all__:
        assert hasattr(portfolio_env, sym), f"missing symbol: {sym}"


def test_make_default_env_signature():
    sig = inspect.signature(portfolio_env.make_default_env)
    params = list(sig.parameters)
    assert params[0] == "data_root"
    # include_smc 為 keyword-only with default True
    assert sig.parameters["include_smc"].default is True
    assert sig.parameters["include_smc"].kind is inspect.Parameter.KEYWORD_ONLY


def test_portfolio_env_config_fields():
    """contracts/api.pyi 列出的欄位皆存在；frozen=True。"""
    cfg_cls = portfolio_env.PortfolioEnvConfig
    fields = {f.name for f in cfg_cls.__dataclass_fields__.values()}
    expected_fields = {
        "data_root",
        "assets",
        "include_smc",
        "reward_config",
        "position_cap",
        "base_slippage_bps",
        "initial_nav",
        "start_date",
        "end_date",
        "smc_params",
        "render_mode",
    }
    assert fields == expected_fields
    assert cfg_cls.__dataclass_params__.frozen is True


def test_reward_config_fields():
    rc_cls = portfolio_env.RewardConfig
    fields = {f.name for f in rc_cls.__dataclass_fields__.values()}
    assert fields == {"lambda_mdd", "lambda_turnover"}
    assert rc_cls.__dataclass_params__.frozen is True


def test_smc_params_re_exported():
    """``portfolio_env.SMCParams`` 應為 ``smc_features.SMCFeatureParams`` 別名。"""
    from smc_features import SMCFeatureParams

    assert portfolio_env.SMCParams is SMCFeatureParams


def test_portfolio_env_inherits_gymnasium_env():
    import gymnasium

    assert issubclass(portfolio_env.PortfolioEnv, gymnasium.Env)
