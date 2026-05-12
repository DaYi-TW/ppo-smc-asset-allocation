"""Trajectory writer — feature 009 (PPO Episode Detail Store).

把 evaluator 蒐集到的 per-step 紀錄寫成 ``trajectory.parquet``（主檔，給 009
artefact builder 消費）與向後相容的 ``trajectory.csv``（精簡欄位，給既有
Colab notebook 消費）。

設計原則：

* 純函數：不直接讀 env / model；接受 dict 化的 record list 即可。
* parquet 用 pandas + pyarrow（現有相依），zstd 壓縮。
* CSV 仍維持 16 欄精簡 schema（FR-005 向後相容）。
* float 不做 round（parquet 是中間產物；byte-identical 由 builder 端的
  JSON 序列化負責）。

對應 spec FR-001~005、tasks T010~T015。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ASSET_NAMES_DEFAULT: tuple[str, ...] = ("NVDA", "AMD", "TSM", "MU", "GLD", "TLT")


@dataclass
class TrajectoryRecord:
    """單一交易日（含 step=0 起始 frame）的完整紀錄。

    All numeric fields use native Python float / int 以避免 numpy scalar 序列化
    開銷。step=0 frame 的 reward / action(log_prob/entropy) 為 0（FR-002 邊界）。
    """

    date: str
    step: int
    nav: float
    log_return: float  # step=0 時為 0.0
    weights: list[float]  # length 7 (NVDA..MU + GLD + TLT + CASH)
    reward_total: float
    reward_return: float
    reward_drawdown_penalty: float
    reward_cost_penalty: float
    action_raw: list[float]
    action_normalized: list[float]
    action_log_prob: float
    action_entropy: float
    smc_bos: int
    smc_choch: int
    smc_fvg_distance_pct: float | None
    smc_ob_touching: bool
    smc_ob_distance_ratio: float | None
    closes: list[float] = field(default_factory=list)  # 6 個資產 close


def _flatten_record(record: TrajectoryRecord, asset_names: tuple[str, ...]) -> dict[str, Any]:
    asset_with_cash = (*asset_names, "CASH")
    flat: dict[str, Any] = {
        "date": record.date,
        "step": record.step,
        "nav": record.nav,
        "log_return": record.log_return,
        "reward_total": record.reward_total,
        "reward_return": record.reward_return,
        "reward_drawdown_penalty": record.reward_drawdown_penalty,
        "reward_cost_penalty": record.reward_cost_penalty,
        "action_log_prob": record.action_log_prob,
        "action_entropy": record.action_entropy,
        "smc_bos": record.smc_bos,
        "smc_choch": record.smc_choch,
        "smc_fvg_distance_pct": record.smc_fvg_distance_pct,
        "smc_ob_touching": record.smc_ob_touching,
        "smc_ob_distance_ratio": record.smc_ob_distance_ratio,
    }
    for i, name in enumerate(asset_with_cash):
        flat[f"weight_{name}"] = record.weights[i]
    for i in range(len(asset_with_cash)):
        flat[f"action_raw_{i}"] = record.action_raw[i]
        flat[f"action_normalized_{i}"] = record.action_normalized[i]
    for i, name in enumerate(asset_names):
        flat[f"close_{name}"] = record.closes[i] if i < len(record.closes) else float("nan")
    return flat


def write_trajectory_parquet(
    records: list[TrajectoryRecord],
    output_path: Path,
    *,
    asset_names: tuple[str, ...] = ASSET_NAMES_DEFAULT,
) -> Path:
    """寫 trajectory.parquet（zstd compression）。

    每列 1 個 frame；schema 約 50 columns（取決於 asset_names 長度）。
    """
    if not records:
        raise ValueError("records is empty")
    rows = [_flatten_record(r, asset_names) for r in records]
    df = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, compression="zstd", index=False)
    return output_path


def write_trajectory_csv(
    records: list[TrajectoryRecord],
    output_path: Path,
    *,
    asset_names: tuple[str, ...] = ASSET_NAMES_DEFAULT,
) -> Path:
    """寫向後相容的 legacy CSV（FR-005）。

    欄位（共 16）：
      date, nav, log_return, w_NVDA, w_AMD, w_TSM, w_MU, w_GLD, w_TLT, w_CASH,
      close_NVDA, close_AMD, close_TSM, close_MU, close_GLD, close_TLT
    """
    if not records:
        raise ValueError("records is empty")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    asset_with_cash = (*asset_names, "CASH")
    weight_cols = [f"w_{a}" for a in asset_with_cash]
    close_cols = [f"close_{a}" for a in asset_names]
    header = ["date", "nav", "log_return", *weight_cols, *close_cols]
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for r in records:
            close_vals = [r.closes[i] if i < len(r.closes) else float("nan") for i in range(len(asset_names))]
            writer.writerow([r.date, r.nav, r.log_return, *r.weights, *close_vals])
    return output_path


def policy_action_log_prob_entropy(
    model: Any,
    obs: np.ndarray,
    action: np.ndarray,
) -> tuple[float, float]:
    """從 sb3 PPO model 取得單一 (obs, action) 的 log_prob / entropy。

    使用 ``model.policy.evaluate_actions(obs_tensor, action_tensor)`` API。
    若 wrapper 干擾 action shape，呼叫端負責提供 unwrapped raw action。

    回傳 (log_prob, entropy)；皆為 Python float。
    """
    import torch

    obs_t = torch.as_tensor(np.asarray(obs, dtype=np.float32)).unsqueeze(0)
    action_t = torch.as_tensor(np.asarray(action, dtype=np.float32)).unsqueeze(0)
    with torch.no_grad():
        _values, log_prob, entropy = model.policy.evaluate_actions(obs_t, action_t)
    return float(log_prob.item()), float(entropy.item())


__all__ = [
    "ASSET_NAMES_DEFAULT",
    "TrajectoryRecord",
    "policy_action_log_prob_entropy",
    "write_trajectory_csv",
    "write_trajectory_parquet",
]
