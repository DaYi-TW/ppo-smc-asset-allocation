"""PPO 訓練環境（PPO Training Environment）— spec 003-ppo-training-env。

對外公開符號（與 ``contracts/api.pyi`` 一一對應）：

* :class:`PortfolioEnv` — Gymnasium 0.29+ 環境主類別。
* :class:`PortfolioEnvConfig` / :class:`RewardConfig` — frozen dataclass 配置。
* :data:`SMCParams` — re-export 自 ``smc_features.SMCFeatureParams``，便於下游
  ``from portfolio_env import SMCParams`` 一站式取用（spec FR-007、data-model §2.3）。
* :func:`info_to_json_safe` — 將 ``step()`` 回傳的 info dict 轉為 JSON-safe
  原生型別（FR-026、SC-008）。
* :func:`make_default_env` — quickstart §2 的便利建構子。
"""

from __future__ import annotations

from pathlib import Path

from portfolio_env.config import PortfolioEnvConfig, RewardConfig
from portfolio_env.env import PortfolioEnv
from portfolio_env.info import info_to_json_safe

# 與 contracts/api.pyi 對齊：對外暴露 SMCParams 名稱（內部實際為 SMCFeatureParams）。
from smc_features import SMCFeatureParams as SMCParams

__version__ = "0.1.0"


def make_default_env(data_root: Path | str, *, include_smc: bool = True) -> PortfolioEnv:
    """快速建立預設配置環境（quickstart §2）。

    等價於 ``PortfolioEnv(PortfolioEnvConfig(data_root=Path(data_root),
    include_smc=include_smc))``。
    """
    return PortfolioEnv(PortfolioEnvConfig(data_root=Path(data_root), include_smc=include_smc))


__all__ = [
    "PortfolioEnv",
    "PortfolioEnvConfig",
    "RewardConfig",
    "SMCParams",
    "info_to_json_safe",
    "make_default_env",
]
