"""SMC Feature Engine — Smart Money Concepts 量化特徵函式庫。

為 PPO 訓練的觀測空間提供可重現、可解釋、可視覺化覆核的 BOS/CHoCh/FVG/OB
特徵。Phase 2 已就緒：公開所有不可變資料型別；Phase 3 後將補齊
``batch_compute`` / ``incremental_compute`` / ``visualize`` 三個進入點。
"""

from __future__ import annotations

from smc_features.batch import batch_compute
from smc_features.types import (
    FVG,
    BatchResult,
    FeatureRow,
    OrderBlock,
    SMCEngineState,
    SMCFeatureParams,
    SwingPoint,
)
from smc_features.viz import visualize

__version__ = "0.1.0"

__all__ = [
    "FVG",
    "BatchResult",
    "FeatureRow",
    "OrderBlock",
    "SMCEngineState",
    "SMCFeatureParams",
    "SwingPoint",
    "batch_compute",
    "visualize",
]
