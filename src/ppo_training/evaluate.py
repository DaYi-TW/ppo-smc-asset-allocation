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
from ppo_training.trajectory_writer import (
    ASSET_NAMES_DEFAULT,
    TrajectoryRecord,
    policy_action_log_prob_entropy,
    write_trajectory_csv,
    write_trajectory_parquet,
)


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

    # 預備：env_data 提供 SMC features (T,5) per ticker，與 closes (T,6)
    env_data = base_env._env_data  # noqa: SLF001 — 公開 attribute 走法
    env_dates = [str(d)[:10] for d in env_data.trading_days.astype("datetime64[D]")]
    env_date_to_index = {d: i for i, d in enumerate(env_dates)}
    smc_feat_nvda = (
        env_data.smc_features.get("NVDA")
        if (env_data.smc_features is not None)
        else None
    )

    def _smc_signals_for_date(d: str) -> tuple[int, int, float | None, bool, float | None]:
        # 用 NVDA 作代表（與 obs 設計一致）；若 include_smc=False 則回 0/null
        if smc_feat_nvda is None:
            return 0, 0, None, False, None
        idx = env_date_to_index.get(d[:10])
        if idx is None:
            return 0, 0, None, False, None
        row = smc_feat_nvda[idx]  # shape (5,) float32
        bos = int(row[0])
        choch = int(row[1])
        fvg = float(row[2])
        ob_touch = bool(row[3] >= 0.5)
        ob_dist = float(row[4])
        # NaN 視為 null（JSON 不能塞 NaN）
        fvg_v: float | None = None if (np.isnan(fvg) or fvg == 0.0) else fvg
        ob_dist_v: float | None = None if (np.isnan(ob_dist) or ob_dist == 0.0) else ob_dist
        return bos, choch, fvg_v, ob_touch, ob_dist_v

    def _closes_for_date(d: str) -> list[float]:
        idx = env_date_to_index.get(d[:10])
        if idx is None:
            return [float("nan")] * env_data.closes.shape[1]
        return [float(v) for v in env_data.closes[idx]]

    # 起始 frame（step=0）— reward / log_prob / entropy 為 0
    initial_date = info["date"]
    initial_weights = [float(w) for w in info["weights"]]
    initial_smc = _smc_signals_for_date(initial_date)
    records: list[TrajectoryRecord] = [
        TrajectoryRecord(
            date=initial_date,
            step=0,
            nav=float(info["nav"]),
            log_return=0.0,
            weights=initial_weights,
            reward_total=0.0,
            reward_return=0.0,
            reward_drawdown_penalty=0.0,
            reward_cost_penalty=0.0,
            action_raw=initial_weights,
            action_normalized=initial_weights,
            action_log_prob=0.0,
            action_entropy=0.0,
            smc_bos=initial_smc[0],
            smc_choch=initial_smc[1],
            smc_fvg_distance_pct=initial_smc[2],
            smc_ob_touching=initial_smc[3],
            smc_ob_distance_ratio=initial_smc[4],
            closes=_closes_for_date(initial_date),
        )
    ]

    nav_traj: list[float] = [float(info["nav"])]
    weights_traj: list[list[float]] = [list(info["weights"])]
    dates: list[str] = [info["date"]]
    log_returns: list[float] = []

    step_count = 0
    deterministic = not args.stochastic
    while True:
        action, _ = model.predict(obs, deterministic=deterministic)
        # 取 log_prob / entropy（FR-003）— 失敗時 fallback 為 0（不阻塞 evaluator）
        try:
            log_prob, entropy = policy_action_log_prob_entropy(model, obs, action)
        except Exception:  # noqa: BLE001
            log_prob, entropy = 0.0, 0.0

        prev_obs_action_raw = np.asarray(action, dtype=np.float32).tolist()

        obs, reward_scalar, terminated, truncated, info = env.step(action)
        step_count += 1

        nav_traj.append(float(info["nav"]))
        weights_traj.append(list(info["weights"]))
        dates.append(info["date"])
        rc = info["reward_components"]
        log_returns.append(float(rc["log_return"]))

        smc = _smc_signals_for_date(info["date"])
        records.append(
            TrajectoryRecord(
                date=info["date"],
                step=step_count,
                nav=float(info["nav"]),
                log_return=float(rc["log_return"]),
                weights=[float(w) for w in info["weights"]],
                reward_total=float(reward_scalar),
                reward_return=float(rc["log_return"]),
                reward_drawdown_penalty=float(rc["drawdown_penalty"]),
                reward_cost_penalty=float(rc["turnover_penalty"]),
                action_raw=prev_obs_action_raw,
                action_normalized=[float(w) for w in info["action_processed"]],
                action_log_prob=log_prob,
                action_entropy=entropy,
                smc_bos=smc[0],
                smc_choch=smc[1],
                smc_fvg_distance_pct=smc[2],
                smc_ob_touching=smc[3],
                smc_ob_distance_ratio=smc[4],
                closes=_closes_for_date(info["date"]),
            )
        )

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
        # feature 009：parquet 主檔（reward / action / smc 全欄位）+ legacy CSV
        asset_names = tuple(cfg.assets) if isinstance(cfg.assets, list | tuple) else ASSET_NAMES_DEFAULT
        traj_parquet = output_path.parent / "trajectory.parquet"
        traj_csv = output_path.parent / "trajectory.csv"
        write_trajectory_parquet(records, traj_parquet, asset_names=asset_names)
        write_trajectory_csv(records, traj_csv, asset_names=asset_names)
        print(f"  軌跡 parquet 已寫入：{traj_parquet}")
        print(f"  軌跡 CSV 已寫入   ：{traj_csv}")

    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
