"""資料載入 — 整合 002 loader + 001 batch_compute + hash 驗證。

關鍵流程（research R5、R6、R7）：

1. 對 6 檔股票 + DTB3 各自 ``load_asset_snapshot`` / ``load_rate_snapshot``。
2. 立即重新計算 SHA-256 並比對 sidecar metadata，不符即 raise（FR-021、R6）。
3. 過濾 ``quality_flag != "ok"`` 的股票交易日；六檔交集為 ``_trading_days``。
4. FRED ``quality_flag == "missing_rate"`` 對 ``rate_pct`` 做 forward fill；
   不影響交易日序列（R5）。
5. 預計算 simple return ``_returns``、日化無風險利率 ``_rf_daily``。
6. ``include_smc=True`` 時於 __init__ 階段一次性呼叫 ``smc_features.batch_compute``
   為每檔股票算 SMC 5 欄；結果切為 ``dict[ticker, ndarray[float32]]`` 供
   ``observation.build_observation`` 查表使用（R7）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from data_ingestion.loader import load_asset_snapshot, load_rate_snapshot
from portfolio_env.config import PortfolioEnvConfig
from smc_features import batch_compute

_TRADING_DAYS_PER_YEAR = 252


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_expected_sha(parquet_path: Path) -> str:
    meta_path = parquet_path.with_suffix(parquet_path.suffix + ".meta.json")
    if not meta_path.is_file():
        raise RuntimeError(
            f"Snapshot metadata sidecar missing for {parquet_path.name}: {meta_path}"
        )
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    return str(payload["sha256"])


def _verify_hash(parquet_path: Path, asset: str) -> str:
    expected = _read_expected_sha(parquet_path)
    actual = _sha256_file(parquet_path)
    if expected != actual:
        raise RuntimeError(f"Snapshot hash mismatch: {asset} expected {expected}, got {actual}")
    return actual


def _find_parquet(prefix: str, data_dir: Path) -> Path:
    pattern = f"{prefix}_daily_*.parquet"
    matches = sorted(p for p in data_dir.glob(pattern) if not p.name.endswith(".meta.json"))
    if not matches:
        raise FileNotFoundError(
            f"no snapshot matching {pattern!r} in {data_dir}; "
            "run `ppo-smc-data fetch` first or check the prefix"
        )
    if len(matches) > 1:
        raise ValueError(
            f"multiple snapshots match {pattern!r} in {data_dir}: "
            + ", ".join(p.name for p in matches)
        )
    return matches[0]


def _stock_valid_days(df: pd.DataFrame) -> pd.DatetimeIndex:
    """回傳該股票 quality_flag == 'ok' 的日期 index。"""
    qf = df["quality_flag"].astype("string")
    mask = (qf == "ok").to_numpy()
    return df.index[mask]


def _forward_fill_rate(rate_df: pd.DataFrame) -> pd.DataFrame:
    """對 quality_flag == 'missing_rate' 的列做 forward fill（research R5）。"""
    qf = rate_df["quality_flag"].astype("string")
    mask = (qf == "missing_rate").to_numpy()
    if not mask.any():
        return rate_df
    rate = rate_df["rate_pct"].copy()
    # 將 missing_rate 列暫時設為 NaN 再 ffill
    rate_arr = rate.to_numpy(dtype=np.float64).copy()
    rate_arr[mask] = np.nan
    filled = pd.Series(rate_arr, index=rate_df.index).ffill()
    # 第一列若仍 NaN（無前值可填）則退回原值
    if filled.isna().any():
        first_nan = filled.isna().to_numpy()
        filled.values[first_nan] = rate.to_numpy(dtype=np.float64)[first_nan]
    out = rate_df.copy()
    out["rate_pct"] = filled.to_numpy(dtype=np.float64)
    return out


@dataclass(frozen=True)
class EnvData:
    """``PortfolioEnv.__init__`` 階段預計算之全 episode 資料快照。

    所有屬性皆為 ``__init__`` 後不可變；step 內僅以 ``current_index`` 索引讀取。
    """

    trading_days: np.ndarray  # shape (T,) dtype object (datetime.date)
    closes: np.ndarray  # shape (T, 6) float64
    returns: np.ndarray  # shape (T, 6) float64, simple return; t=0 row all-zeros
    rf_daily: np.ndarray  # shape (T,) float64, daily risk-free simple return
    smc_features: dict[str, np.ndarray] | None  # {ticker: (T, 5) float32}
    data_hashes: dict[str, str]  # {TICKER: sha256_hex} + {DTB3: ...}
    skipped_dates_init: list[str]  # research R5 init-time 累積


def load_environment_data(config: PortfolioEnvConfig) -> EnvData:
    """執行 R5/R6/R7 全流程；__init__ 一次性呼叫。

    Raises:
        RuntimeError: 任一檔 hash 與 metadata 不符（FR-021）。
        FileNotFoundError: 找不到 Parquet 或 sidecar。
    """
    data_dir = Path(config.data_root)

    # ---- 1. 載入 6 檔股票 + DTB3，立即 hash 比對 ----
    raw_dfs: dict[str, pd.DataFrame] = {}
    data_hashes: dict[str, str] = {}
    for ticker in config.assets:
        parquet_path = _find_parquet(ticker.lower(), data_dir)
        sha = _verify_hash(parquet_path, ticker)
        data_hashes[ticker] = sha
        raw_dfs[ticker] = load_asset_snapshot(ticker, data_dir=data_dir)

    rate_path = _find_parquet("dtb3", data_dir)
    data_hashes["DTB3"] = _verify_hash(rate_path, "DTB3")
    rate_df = load_rate_snapshot("DTB3", data_dir=data_dir)
    rate_df = _forward_fill_rate(rate_df)

    # ---- 2. 過濾 quality_flag、計算 trading days 交集 ----
    valid_per_ticker = [_stock_valid_days(raw_dfs[t]) for t in config.assets]
    trading_index = valid_per_ticker[0]
    for vd in valid_per_ticker[1:]:
        trading_index = trading_index.intersection(vd)
    # 與 rate 的日期交集（rate 不會被踢，但 trading_days 必須是 rate 也有的日期）
    trading_index = trading_index.intersection(rate_df.index)

    # 套用 start_date / end_date 過濾
    if config.start_date is not None:
        trading_index = trading_index[trading_index >= pd.Timestamp(config.start_date)]
    if config.end_date is not None:
        trading_index = trading_index[trading_index <= pd.Timestamp(config.end_date)]
    trading_index = trading_index.sort_values()

    if len(trading_index) < 2:
        raise RuntimeError(
            f"Trading day intersection has only {len(trading_index)} days; "
            "need at least 2 to form a valid episode"
        )

    # 累積跳日：union of all valid_days minus trading_index（限 stock 缺值產生的）
    union_days = valid_per_ticker[0]
    for vd in valid_per_ticker[1:]:
        union_days = union_days.union(vd)
    skipped = union_days.difference(trading_index).sort_values()
    skipped_dates_init = [d.strftime("%Y-%m-%d") for d in skipped]

    # ---- 3. closes / returns / rf_daily ----
    n_assets = len(config.assets)
    T = len(trading_index)  # noqa: N806 — 慣例：T 為 episode 長度
    closes = np.zeros((T, n_assets), dtype=np.float64)
    for i, ticker in enumerate(config.assets):
        aligned = raw_dfs[ticker]["close"].reindex(trading_index)
        closes[:, i] = aligned.to_numpy(dtype=np.float64)

    returns = np.zeros_like(closes)
    if T > 1:
        returns[1:, :] = closes[1:, :] / closes[:-1, :] - 1.0

    rate_aligned = rate_df["rate_pct"].reindex(trading_index).to_numpy(dtype=np.float64)
    rf_daily = (1.0 + rate_aligned / 100.0) ** (1.0 / _TRADING_DAYS_PER_YEAR) - 1.0

    # ---- 4. SMC 預計算（research R7）+ look-ahead 修正 ----
    #
    # **重要修正（look-ahead bias 補丁）**：
    #
    # ``smc_features.batch_compute`` 內部 ``detect_swings`` 採用 ±L 鄰居比較定義
    # swing point — 第 ``i`` 根 K 棒最早於第 ``i+L`` 根才能確認（見 swing.py
    # docstring: "delayed signal"）。然而 BOS/CHoCh/OB 在 swing 確認的當下即用
    # ``last_swing_high/last_swing_low`` 推進狀態 → 等價於把「未來 L 根才能知道」
    # 的訊息塞進 batch 結果的位置 ``i``。
    #
    # 在 batch 模式對歷史資料一次算完是合法的（離線分析），但**不能直接餵給 RL
    # observation** — 否則 agent 在 t 時刻就「知道」位置 ``t`` 是不是 swing，
    # 而這需要 ``t+L`` 的 highs/lows。實證：500k SMC policy 跑出 2350x NAV、
    # corr(weights[t], realized_return[t]) ≈ 2x corr(weights[t], next_return[t→t+1]),
    # 確認 look-ahead 偏差。
    #
    # 修法：將整個 SMC 特徵陣列**沿時間軸延遲 L 拍**——位置 ``t`` 的 obs 只能看到
    # 位置 ``t-L`` 的 SMC 訊號（彼時 swing 已可確認）。前 L 拍補 0（neutral）。
    # FVG 雖無 look-ahead 也一併延遲，保持 5 欄時間對齊一致。
    #
    # 長期解（spec 001 後續修法）：``batch_compute`` 應提供 "as_of_index" 介面，
    # 在每個 t 嚴格使用 ``[0, t]`` 之資料。本補丁為 spec 003 env 端最小可行修正，
    # 不破壞 spec 001 contract。
    smc_features: dict[str, np.ndarray] | None
    if config.include_smc:
        smc_features = {}
        smc_lookahead_lag = int(config.smc_params.swing_length)
        for ticker in config.assets:
            df_full = raw_dfs[ticker]
            result = batch_compute(df_full, params=config.smc_params)
            # 切片到 trading_index 後，將五欄編碼為 float32（FR-010a）
            sub = result.output.reindex(trading_index)
            arr_raw = np.zeros((T, 5), dtype=np.float32)
            arr_raw[:, 0] = sub["bos_signal"].to_numpy(dtype=np.float32)
            arr_raw[:, 1] = sub["choch_signal"].to_numpy(dtype=np.float32)
            arr_raw[:, 2] = sub["fvg_distance_pct"].to_numpy(dtype=np.float32)
            arr_raw[:, 3] = sub["ob_touched"].astype("boolean").to_numpy(
                dtype=np.float32, na_value=0.0
            )
            arr_raw[:, 4] = sub["ob_distance_ratio"].to_numpy(dtype=np.float32)
            # 延遲 swing_length 拍：obs[t] 只能看到 SMC[t - L]，前 L 拍補 0。
            arr = np.zeros_like(arr_raw)
            if T > smc_lookahead_lag:
                arr[smc_lookahead_lag:] = arr_raw[: T - smc_lookahead_lag]
            smc_features[ticker] = arr
    else:
        smc_features = None

    return EnvData(
        trading_days=np.array(trading_index.values, dtype="datetime64[ns]"),
        closes=closes,
        returns=returns,
        rf_daily=rf_daily,
        smc_features=smc_features,
        data_hashes=data_hashes,
        skipped_dates_init=skipped_dates_init,
    )


__all__ = ["EnvData", "load_environment_data"]
