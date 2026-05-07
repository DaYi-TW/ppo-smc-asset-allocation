"""配置 dataclass — frozen，符合憲法 Principle I 可重現性。

* :class:`RewardConfig` — reward function 兩個權重（data-model §2.1、research R3）。
* :class:`PortfolioEnvConfig` — 環境靜態配置（data-model §2.2）。

所有不變式於 ``__post_init__`` 強制檢查，違反即 ``ValueError``，避免無效配置
靜默產生錯誤訓練曲線（spec FR-007、FR-022、FR-023、FR-027）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from smc_features import SMCFeatureParams


@dataclass(frozen=True)
class RewardConfig:
    """Reward function 權重（research R3 採風控優先型）。

    將兩個 lambda 同時設為 ``0`` 即退化為純 log return（SC-007 ablation）。
    """

    lambda_mdd: float = 1.0
    lambda_turnover: float = 0.0015

    def __post_init__(self) -> None:
        if self.lambda_mdd < 0:
            raise ValueError(f"lambda_mdd must be >= 0, got {self.lambda_mdd}")
        if self.lambda_turnover < 0:
            raise ValueError(f"lambda_turnover must be >= 0, got {self.lambda_turnover}")


@dataclass(frozen=True)
class PortfolioEnvConfig:
    """``PortfolioEnv`` 靜態配置。詳見 ``data-model.md §2.2``。

    ``render_mode`` 採 Gymnasium 0.29+ 慣例：於 ``__init__`` 傳入並儲存於
    instance、不作為 ``render()`` 之參數（spec FR-027）。
    """

    data_root: Path
    assets: tuple[str, ...] = ("NVDA", "AMD", "TSM", "MU", "GLD", "TLT")
    include_smc: bool = True
    reward_config: RewardConfig = field(default_factory=RewardConfig)
    position_cap: float = 0.4
    base_slippage_bps: float = 5.0
    initial_nav: float = 1.0
    start_date: date | None = None
    end_date: date | None = None
    smc_params: SMCFeatureParams = field(default_factory=SMCFeatureParams)
    render_mode: str | None = None

    def __post_init__(self) -> None:
        if self.render_mode not in (None, "ansi"):
            raise ValueError(f"render_mode must be None or 'ansi', got {self.render_mode!r}")
        if not (0 < self.position_cap <= 1):
            raise ValueError(f"position_cap must be in (0, 1], got {self.position_cap}")
        if self.position_cap * len(self.assets) < 1.0:
            raise ValueError(
                "position_cap * num_assets must be >= 1 to ensure simplex feasibility "
                f"(got {self.position_cap} × {len(self.assets)} = "
                f"{self.position_cap * len(self.assets)})"
            )
        if self.initial_nav <= 0:
            raise ValueError(f"initial_nav must be > 0, got {self.initial_nav}")
        if self.base_slippage_bps < 0:
            raise ValueError(f"base_slippage_bps must be >= 0, got {self.base_slippage_bps}")


__all__ = ["PortfolioEnvConfig", "RewardConfig"]
