"""Single-day forward prediction — 用訓練好的 PPO policy 推下一個交易日的目標配置。

對照 ``ppo_training.evaluate``（整段回測）：``predict`` 只關心「**最後一根 K 棒收盤
後**的 policy 動作」，輸出明日開盤生效的目標權重。

語意（重要）：
    PPO policy 不預測股價漲跌，預測「給定當前市場狀態，現在該怎麼配置」。
    輸出 7 維 weights ∈ simplex（NVDA / AMD / TSM / MU / GLD / TLT / CASH，sum=1）。

執行：
    python -m ppo_training.predict \\
        --policy runs/<run_id>/final_policy.zip \\
        --data-root data/raw \\
        --as-of 2026-04-29

輸出 JSON 結構：
    {
      "as_of_date": "2026-04-29",
      "next_trading_day_target": "first session after 2026-04-29 (apply at next open)",
      "policy_path": "...",
      "deterministic": true,
      "target_weights": {
        "NVDA": 0.2143, "AMD": 0.0921, "TSM": 0.1842, "MU": 0.0512,
        "GLD": 0.1230, "TLT": 0.2812, "CASH": 0.0540
      },
      "weights_capped": false,
      "renormalized": false,
      "context": {
        "data_root": "data/raw",
        "include_smc": true,
        "n_warmup_steps": 1758,
        "current_nav_at_as_of": 215.97
      }
    }

設計：
    1. 載入 PortfolioEnv，``end_date = as_of``，include_smc 跟訓練時一致。
    2. ``reset(seed=42)``、走完整段 episode 到 as_of（這是必要的：env 內部維持
       NAV / peak / current_weights 狀態，policy 需要看到「進入 as_of 收盤時的
       observation」）。
    3. 在 as_of 那根 obs 上呼叫 ``model.predict(obs, deterministic=True)``
       取得 raw action。
    4. 用同一個 SoftmaxActionWrapper 把 raw action 轉成 simplex（與訓練側一致）。
    5. 印 + 寫 JSON。

注意：
    * deterministic=True（同 ``evaluate.py`` 預設），實盤不應每次抽不同 sample。
    * SMC look-ahead lag (swing_length 拍) 在 ``data_loader.py`` 已自動補正，
      predict 沿用 batch 結果切片，**不需要再做時間延遲**。
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

_ASSET_NAMES = ("NVDA", "AMD", "TSM", "MU", "GLD", "TLT", "CASH")


def _make_softmax_wrapper() -> type:
    """重建訓練側的 ``_SoftmaxActionWrapper``（與 ``train.py`` / ``evaluate.py`` 一致）。"""
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


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m ppo_training.predict",
        description="用訓練好的 PPO policy 推下一個交易日的目標配置（live inference）。",
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
        help="若訓練時用了 ``--no-smc``，預測也須加上。",
    )
    p.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        help=(
            "預測基準日（含），ISO 8601。policy 看到該日收盤後的 obs，"
            "輸出明日開盤生效的目標配置。未指定 = 用資料中最後一個交易日（最新狀態）。"
        ),
    )
    p.add_argument(
        "--seed",
        type=int,
        default=42,
        help="env reset seed（預設 42，與 evaluate 一致）。",
    )
    p.add_argument(
        "--stochastic",
        action="store_true",
        help="使用 stochastic policy；預設 deterministic（實盤推薦）。",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="輸出 JSON 路徑。預設寫到 policy 同目錄的 ``prediction_<as_of>.json``。",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    if not args.policy.exists():
        print(f"[predict] ERROR: policy 檔不存在：{args.policy}", file=sys.stderr)
        return 2

    cfg = PortfolioEnvConfig(
        data_root=args.data_root,
        include_smc=not args.no_smc,
        start_date=None,
        end_date=args.as_of,
    )
    base_env = PortfolioEnv(cfg)
    SoftmaxWrapper = _make_softmax_wrapper()
    env = SoftmaxWrapper(base_env)

    from stable_baselines3 import PPO

    print(f"[predict] 載入 policy：{args.policy}")
    model = PPO.load(str(args.policy), env=env, device="auto")

    obs, info = env.reset(seed=args.seed)

    deterministic = not args.stochastic
    n_warmup = 0
    action: np.ndarray = np.zeros(len(_ASSET_NAMES), dtype=np.float32)
    while True:
        action, _ = model.predict(obs, deterministic=deterministic)
        obs, _reward, terminated, truncated, info = env.step(action)
        n_warmup += 1
        if terminated or truncated:
            break

    final_weights = np.asarray(info["weights"], dtype=np.float64)

    as_of_str = info["date"]
    weights_dict = {name: float(final_weights[i]) for i, name in enumerate(_ASSET_NAMES)}

    report = {
        "as_of_date": as_of_str,
        "next_trading_day_target": f"first session after {as_of_str} (apply at next open)",
        "policy_path": str(args.policy),
        "deterministic": bool(deterministic),
        "target_weights": weights_dict,
        "weights_capped": bool(info.get("position_capped", False)),
        "renormalized": bool(info.get("action_renormalized", False)),
        "context": {
            "data_root": str(args.data_root),
            "include_smc": not args.no_smc,
            "n_warmup_steps": int(n_warmup),
            "current_nav_at_as_of": float(info["nav"]),
        },
    }

    output_path = args.output
    if output_path is None:
        output_path = args.policy.parent / f"prediction_{as_of_str}.json"
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("=" * 60)
    print(f"  Forward prediction — as of {as_of_str}")
    print(f"  policy             : {args.policy}")
    print(f"  warmup steps       : {n_warmup}")
    print(f"  current NAV        : {float(info['nav']):.4f}")
    print("  下一個交易日開盤目標配置：")
    sorted_w = sorted(weights_dict.items(), key=lambda kv: -kv[1])
    for name, w in sorted_w:
        bar = "█" * int(round(w * 40))
        print(f"    {name:<5} : {w * 100:>6.2f}%  {bar}")
    print(f"  weights_capped     : {report['weights_capped']}")
    print(f"  renormalized       : {report['renormalized']}")
    print(f"  完整 JSON 寫入：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
