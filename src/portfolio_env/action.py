"""Action 處理管線（data-model §4、FR-014、research R9）。

三道處理：

1. NaN 檢查 — ``numpy.isnan(action).any()`` 觸發 ``ValueError``。
2. L1 normalize — 容差 1e-6（research R8）；和 < 1e-6 觸發 ``ValueError``；
   ``|sum-1| > 1e-6`` 時 ``action /= sum`` 並標記 ``action_renormalized=True``。
3. Water-filling position cap — CASH（index 6）不受 cap 限制。前 6 維中超出
   ``position_cap`` 的鎖定為 cap，溢出量按未鎖定維度（含 CASH）的當前比例
   一次性重分配（research R9 已證明單趟收斂；保險最多 2 趟）。

不變式（``cap × len(stocks) >= 1``）由 ``PortfolioEnvConfig.__post_init__``
強制；此處假設輸入已合法、簡化迴圈邏輯。
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np

_L1_TOLERANCE = 1e-6
_NUM_STOCKS = 6  # 前 6 維為股票（受 cap 限制）；index 6 為 CASH


class ProcessedAction(NamedTuple):
    weights: np.ndarray  # shape (7,) float32
    action_renormalized: bool
    position_capped: bool


def process_action(
    action: np.ndarray,
    position_cap: float,
) -> ProcessedAction:
    """執行 NaN 檢查、L1 normalize、water-filling cap 三道處理。

    Args:
        action: shape (7,) numpy array，型別任意（實作會 cast 為 float64 計算
            後最終 cast 為 float32）。
        position_cap: 單檔股票權重上限（CASH 不受限）。

    Returns:
        ``ProcessedAction(weights, action_renormalized, position_capped)``。

    Raises:
        ValueError: 含 NaN 或 sum 過小（< 1e-6）。
    """
    a = np.asarray(action, dtype=np.float64).copy()
    if a.shape != (7,):
        raise ValueError(f"Action shape must be (7,), got {a.shape}")
    if np.isnan(a).any():
        raise ValueError("Action contains NaN")

    # ---- L1 normalize ----
    s = float(a.sum())
    if s < _L1_TOLERANCE:
        raise ValueError(f"Action sum near zero ({s} < {_L1_TOLERANCE})")
    if abs(s - 1.0) > _L1_TOLERANCE:
        a = a / s
        action_renormalized = True
    else:
        action_renormalized = False

    # 確保非負（裁掉浮點負值雜訊）
    a = np.clip(a, 0.0, None)
    # 重歸一以保 sum=1（裁掉負值後可能略 < 1）
    s2 = float(a.sum())
    if s2 < _L1_TOLERANCE:
        raise ValueError(f"Action sum near zero after clip ({s2})")
    a = a / s2

    # ---- Water-filling position cap ----
    cap = float(position_cap)
    stocks = a[:_NUM_STOCKS]
    position_capped = False
    if stocks.max() > cap:
        position_capped = True
        # 最多 2 趟保險；R9 證明 1 趟足夠
        for _ in range(2):
            over_mask = a[:_NUM_STOCKS] > cap
            if not over_mask.any():
                break
            excess = float((a[:_NUM_STOCKS][over_mask] - cap).sum())
            # 鎖定超出維度為 cap
            a[:_NUM_STOCKS][over_mask] = cap
            # 未鎖定維度集合：未超 cap 的股票 + CASH
            unlocked = np.zeros(7, dtype=bool)
            unlocked[:_NUM_STOCKS] = ~over_mask
            unlocked[_NUM_STOCKS] = True  # CASH 永遠 unlocked
            unlocked_total = float(a[unlocked].sum())
            if unlocked_total <= 0.0:
                # 退化：未鎖定維度全 0（含 CASH）；excess 全部丟進 CASH（CASH 無上限）。
                a[_NUM_STOCKS] += excess
            else:
                # 按當前未鎖定權重比例分配 excess
                ratios = np.where(unlocked, a / unlocked_total, 0.0)
                a = a + ratios * excess

    weights = a.astype(np.float32)
    return ProcessedAction(
        weights=weights,
        action_renormalized=action_renormalized,
        position_capped=position_capped,
    )


__all__ = ["ProcessedAction", "process_action"]
