"""Oracle upper bound：每天用「明天的 returns」決策，求理論最佳 NAV。

這是 long-only + position_cap 限制下的物理上限。任何 RL policy 跑出超過
這條線的 NAV，必然含 look-ahead bias。

執行：``python scripts/oracle_upper_bound.py``
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data" / "raw"
ASSETS = ["NVDA", "AMD", "TSM", "MU", "GLD", "TLT"]
POSITION_CAP = 0.4
TRADING_DAYS_PER_YEAR = 252


def main() -> None:
    closes: dict[str, np.ndarray] = {}
    dates = None
    for a in ASSETS:
        fn = DATA_ROOT / f"{a.lower()}_daily_20180101_20260429.parquet"
        t = pq.read_table(fn)
        df = t.to_pylist()
        closes[a] = np.array([r["close"] for r in df], dtype=np.float64)
        if dates is None:
            dates = [str(r["date"])[:10] for r in df]

    n_assets = len(ASSETS)
    n = len(dates)
    closes_mat = np.stack([closes[a] for a in ASSETS], axis=1)  # (T, 6)
    returns = closes_mat[1:] / closes_mat[:-1] - 1.0  # (T-1, 6)

    print(f"資料區間：{dates[0]} → {dates[-1]} ({n} 天 / {n - 1} return)")
    print(f"資產數：{n_assets}，position_cap = {POSITION_CAP}")
    print()

    # === Buy-and-hold benchmarks ===
    print("=" * 70)
    print("Buy-and-hold benchmarks")
    print("=" * 70)
    for i, a in enumerate(ASSETS):
        final = closes_mat[-1, i] / closes_mat[0, i]
        cagr = final ** (TRADING_DAYS_PER_YEAR / (n - 1)) - 1
        print(f"  {a:5s}  {final:8.2f}x   CAGR {cagr * 100:+6.2f}%")

    ew_nav = 1.0
    for t in range(n - 1):
        ew_nav *= 1 + returns[t].mean()
    cagr_ew = ew_nav ** (TRADING_DAYS_PER_YEAR / (n - 1)) - 1
    print(f"  EW    {ew_nav:8.2f}x   CAGR {cagr_ew * 100:+6.2f}%  (等權每日 rebalance)")

    # === Oracle ：知道明天 return，每天最佳化 weight ===
    print()
    print("=" * 70)
    print("Oracle upper bound（每天看明天 return 出 weight，long-only + cap）")
    print("=" * 70)

    # 加 cash bucket（return = 0），共 7 維。
    returns_with_cash = np.concatenate([returns, np.zeros((n - 1, 1))], axis=1)  # (T-1, 7)

    # 每日：max_w  w · r   s.t.  sum(w)=1, 0 <= w[i] <= cap (i<6), 0 <= w[6] <= 1
    # 線性規劃；最佳解：把資金集中在「報酬最高的資產，每個最多 cap」。
    # 演算法：依 returns 由大到小排序，逐一灌滿 cap，最後剩餘給 cash（若 cash 報酬最高則優先）。
    nav_oracle = 1.0
    cap_vec = np.array([POSITION_CAP] * n_assets + [1.0])
    nav_traj = [1.0]
    for t in range(n - 1):
        r = returns_with_cash[t]  # 7-dim
        order = np.argsort(-r)  # 由大到小
        w = np.zeros(7)
        remaining = 1.0
        for idx in order:
            if r[idx] <= 0 and idx != 6:
                # 報酬非正且非現金：寧可放現金（return 0）。
                continue
            take = min(cap_vec[idx], remaining)
            w[idx] = take
            remaining -= take
            if remaining <= 1e-12:
                break
        if remaining > 1e-12:
            w[6] += remaining  # 剩下放現金
        port_ret = float(w @ r)
        nav_oracle *= 1 + port_ret
        nav_traj.append(nav_oracle)

    cagr_oracle = nav_oracle ** (TRADING_DAYS_PER_YEAR / (n - 1)) - 1
    print(f"  Oracle  {nav_oracle:.2e}x   CAGR {cagr_oracle * 100:+6.1f}%")
    print(f"  （理論上限 — 任何 policy 不應超過此值）")

    # === 比較 ===
    print()
    print("=" * 70)
    print("比對你的 PPO policies")
    print("=" * 70)
    print(f"  500k SMC（修補前）：       2350.97x   CAGR  155.0%")
    print(f"  500k SMC（修補後 v2）：     116.79x   CAGR   77.5%")
    print(f"  Oracle 物理上限：         {nav_oracle:8.2e}x   CAGR {cagr_oracle * 100:+6.1f}%")
    print(f"  最佳單檔 (NVDA)：             42.46x   CAGR   57.1%")
    print()
    print("解讀：")
    print(f"  - 修補後 116x ≈ NVDA 的 2.7 倍。")
    print(f"  - Oracle 上限 {nav_oracle:.1e}x — long-only 加 cap=0.4 仍能放大很多倍，")
    print(f"    因為 8 年 ≈ 2080 天，每天 0.4×max_return 累積。")
    print(f"  - 116x 在 oracle 上限內，但若 policy 真的有 0.1+ 的 next-day corr，")
    print(f"    對等權每日 rebalance（{ew_nav:.1f}x）的 8 倍倍數合理嗎？")
    print(f"  - 116/{ew_nav:.1f} = {116 / ew_nav:.1f}x 等權倍數。")


if __name__ == "__main__":
    main()
