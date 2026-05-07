"""載入 PPO ``final_policy.zip`` 並在完整 episode 上評估業務級指標。

對應 spec 004 之 FR-021（policy 以 sb3 標準 zip 格式持久化）。

輸出指標：

* ``final_nav`` — 期末 NAV（``initial_nav=1.0`` 起算）。
* ``cumulative_return_pct`` — ``(final_nav - 1) × 100``。
* ``annualized_return_pct`` — ``(final_nav^(252/T) - 1) × 100``，T 為 step 數。
* ``max_drawdown_pct`` — ``max((peak - nav) / peak) × 100``。
* ``sharpe_ratio`` — ``mean(daily_log_return) / std(daily_log_return) × sqrt(252)``。
* ``sortino_ratio`` — 僅以下行波動為分母（負 daily return）。

執行：``python -m ppo_training.evaluate --policy <path> --data-root data/raw``

預設使用 ``deterministic=True``（FR-021 推理模式）；同一 policy + 同一資料 →
完全可重現的 NAV 軌跡（憲法 Principle I）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from portfolio_env import PortfolioEnv, PortfolioEnvConfig


def _make_softmax_wrapper() -> type:
    """重建訓練側的 ``_SoftmaxActionWrapper``（與 ``train.py`` 一致）。

    PPO MlpPolicy 之 Gaussian 輸出 ∈ ℝ^7；env 要求 simplex action。訓練時
    透過 softmax wrapper 接合，評估時必須沿用同一 wrapper 才能讓 policy
    輸出語意正確（否則 negative logits 會被 clip 為 0，行為偏移）。
    """
    import gymnasium

    class _SoftmaxActionWrapper(gymnasium.ActionWrapper):  # type: ignore[misc]
        def __init__(self, env: Any) -> None:
            super().__init__(env)
            self.action_space = gymnasium.spaces.Box(
                low=-10.0,
                high=10.0,
                shape=env.action_space.shape,
                dtype=np.float32,
            )

        def action(self, action: np.ndarray) -> np.ndarray:
            a = np.asarray(action, dtype=np.float64)
            a = a - a.max()
            ex = np.exp(a)
            simplex = ex / ex.sum()
            return simplex.astype(np.float32)

    return _SoftmaxActionWrapper


def _max_drawdown(nav_series: np.ndarray) -> float:
    """``max((peak - nav) / peak)`` over the entire trajectory."""
    peaks = np.maximum.accumulate(nav_series)
    drawdowns = (peaks - nav_series) / peaks
    return float(drawdowns.max())


def _sharpe(daily_log_returns: np.ndarray, periods_per_year: int = 252) -> float:
    if daily_log_returns.size < 2:
        return float("nan")
    std = float(daily_log_returns.std(ddof=1))
    if std == 0.0:
        return float("nan")
    mean = float(daily_log_returns.mean())
    return mean / std * np.sqrt(periods_per_year)


def _sortino(daily_log_returns: np.ndarray, periods_per_year: int = 252) -> float:
    if daily_log_returns.size < 2:
        return float("nan")
    downside = daily_log_returns[daily_log_returns < 0]
    if downside.size < 2:
        return float("nan")
    dstd = float(downside.std(ddof=1))
    if dstd == 0.0:
        return float("nan")
    mean = float(daily_log_returns.mean())
    return mean / dstd * np.sqrt(periods_per_year)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m ppo_training.evaluate",
        description="在 PortfolioEnv 上跑完整 episode 並計算 NAV / Sharpe / MDD。",
    )
    p.add_argument(
        "--policy",
        type=Path,
        required=True,
        help="``final_policy.zip`` 路徑（sb3 PPO.save 產出）。",
    )
    p.add_argument(
        "--data-root",
        type=Path,
        default=Path("data/raw"),
        help="002 Parquet 快照目錄（預設 data/raw/）。",
    )
    p.add_argument(
        "--no-smc",
        action="store_true",
        help="若訓練時用了 ``--no-smc``，評估也須加上（obs 維度 33 vs 63）。",
    )
    p.add_argument(
        "--start-date",
        type=date.fromisoformat,
        default=None,
        help="評估資料起始日（含），ISO 8601。未指定 = 用全部資料（in-sample）。",
    )
    p.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=None,
        help="評估資料結束日（含），ISO 8601。未指定 = 用全部資料（in-sample）。",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=42,
        help="env reset seed（影響 deterministic 的環境內亂數源；預設 42）。",
    )
    p.add_argument(
        "--stochastic",
        action="store_true",
        help="使用 stochastic policy（``deterministic=False``）；預設 deterministic。",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="輸出 JSON 報告路徑。預設寫到 policy 同目錄的 evaluation_report.json。",
    )
    p.add_argument(
        "--save-trajectory",
        action="store_true",
        help="同時寫出 trajectory.csv（每日 nav / weights / log_return）。",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    if not args.policy.exists():
        print(f"[evaluate] ERROR: policy 檔不存在：{args.policy}", file=sys.stderr)
        return 2

    # 建環境（與訓練側 cfg 對齊；deterministic 評估不需 Monitor / DataHashesWrapper）。
    cfg = PortfolioEnvConfig(
        data_root=args.data_root,
        include_smc=not args.no_smc,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    base_env = PortfolioEnv(cfg)
    SoftmaxWrapper = _make_softmax_wrapper()
    env = SoftmaxWrapper(base_env)

    # 載入 policy（sb3 standard format）。
    from stable_baselines3 import PPO

    print(f"[evaluate] 載入 policy：{args.policy}")
    model = PPO.load(str(args.policy), env=env, device="auto")

    obs, info = env.reset(seed=args.seed)

    nav_traj: list[float] = [float(info["nav"])]
    weights_traj: list[list[float]] = [list(info["weights"])]
    dates: list[str] = [info["date"]]
    log_returns: list[float] = []

    step_count = 0
    deterministic = not args.stochastic
    while True:
        action, _ = model.predict(obs, deterministic=deterministic)
        obs, _reward, terminated, truncated, info = env.step(action)
        step_count += 1

        nav_traj.append(float(info["nav"]))
        weights_traj.append(list(info["weights"]))
        dates.append(info["date"])
        log_returns.append(float(info["reward_components"]["log_return"]))

        if terminated or truncated:
            break

    nav_arr = np.asarray(nav_traj, dtype=np.float64)
    log_ret_arr = np.asarray(log_returns, dtype=np.float64)

    final_nav = float(nav_arr[-1])
    initial_nav = float(nav_arr[0])
    cumulative_return = (final_nav / initial_nav) - 1.0
    n_steps = log_ret_arr.size
    annualized_return = (final_nav / initial_nav) ** (252.0 / n_steps) - 1.0 if n_steps > 0 else float("nan")
    mdd = _max_drawdown(nav_arr)
    sharpe = _sharpe(log_ret_arr)
    sortino = _sortino(log_ret_arr)

    report = {
        "policy_path": str(args.policy),
        "data_root": str(args.data_root),
        "include_smc": not args.no_smc,
        "deterministic": deterministic,
        "seed": args.seed,
        "n_steps": n_steps,
        "start_date": dates[0],
        "end_date": dates[-1],
        "initial_nav": initial_nav,
        "final_nav": final_nav,
        "cumulative_return_pct": cumulative_return * 100.0,
        "annualized_return_pct": annualized_return * 100.0,
        "max_drawdown_pct": mdd * 100.0,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "mean_daily_log_return": float(log_ret_arr.mean()) if n_steps > 0 else float("nan"),
        "std_daily_log_return": float(log_ret_arr.std(ddof=1)) if n_steps > 1 else float("nan"),
    }

    output_path = args.output if args.output is not None else args.policy.parent / "evaluation_report.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print("=" * 60)
    print(f"  Evaluation report: {args.policy.name}")
    print("=" * 60)
    print(f"  期間              : {dates[0]} → {dates[-1]} ({n_steps} 個交易日)")
    print(f"  Final NAV         : {final_nav:.6f}  (初始 {initial_nav:.4f})")
    print(f"  累積報酬          : {cumulative_return * 100:+.2f}%")
    print(f"  年化報酬          : {annualized_return * 100:+.2f}%")
    print(f"  最大回撤 (MDD)    : {mdd * 100:.2f}%")
    print(f"  Sharpe ratio      : {sharpe:.3f}")
    print(f"  Sortino ratio     : {sortino:.3f}")
    print("=" * 60)
    print(f"  報告已寫入：{output_path}")

    if args.save_trajectory:
        import csv

        # 從 env 直接取 closes（避免下游 sanity check 還要 import pyarrow / pandas）
        env_data = base_env._env_data
        closes_arr = env_data.closes  # shape (T, 6) float64
        env_dates = [str(d)[:10] for d in env_data.trading_days.astype("datetime64[D]")]
        env_date_to_close = {d: closes_arr[i] for i, d in enumerate(env_dates)}

        traj_path = output_path.parent / "trajectory.csv"
        with traj_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            asset_names = list(cfg.assets) + ["CASH"]
            close_cols = [f"close_{a}" for a in cfg.assets]
            writer.writerow(
                ["date", "nav", "log_return", *[f"w_{a}" for a in asset_names], *close_cols]
            )
            for i, d in enumerate(dates):
                lr = log_ret_arr[i - 1] if i > 0 else 0.0
                # d 是 'YYYY-MM-DD'；env_dates 也是。
                cl = env_date_to_close.get(d[:10])
                close_vals = list(cl) if cl is not None else [float("nan")] * len(cfg.assets)
                writer.writerow([d, nav_traj[i], lr, *weights_traj[i], *close_vals])
        print(f"  軌跡已寫入：{traj_path}")

    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
