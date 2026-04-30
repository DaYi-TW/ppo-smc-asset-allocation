"""四層 PRNG 同步（research R1）。

確保 ``PortfolioEnv.reset(seed=N)`` 兩次得到 byte-identical trajectory（SC-005）：

1. ``super().reset(seed=seed)`` — Gymnasium 內建 PRNG 初始化（``env.np_random``）。
2. ``env._py_random = random.Random(seed)`` — 環境內如有 Python ``random``
   用途，使用此本地實例。
3. ``env._numpy_rng = numpy.random.default_rng(seed)`` — 任何 numpy 隨機抽樣
   一律走此 Generator，**不**走 ``numpy.random.*`` 全域介面。
4. 環境內部所有資料切片邏輯 MUST 以 ``self._numpy_rng`` 為唯一隨機源；不從系統
   時間、不從 ``os.urandom``。
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from portfolio_env.env import PortfolioEnv


def synchronize_seeds(env: PortfolioEnv, seed: int | None) -> None:
    """同步環境內所有本地 PRNG。

    呼叫前提：``env`` 已透過 ``super().reset(seed=seed)`` 初始化 ``env.np_random``。
    本函式僅補上 Python ``random`` 與 numpy ``Generator`` 兩條本地實例，**不**
    觸碰 ``numpy.random`` / ``random`` 全域 PRNG。

    Args:
        env: ``PortfolioEnv`` instance。
        seed: ``None`` 時依 Gymnasium 慣例為 non-reproducible 模式。
    """
    env._py_random = random.Random(seed)
    env._numpy_rng = np.random.default_rng(seed)


__all__ = ["synchronize_seeds"]
