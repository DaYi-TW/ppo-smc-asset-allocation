"""觀測向量組裝（data-model §3、FR-010 / FR-010a / FR-011 / FR-012）。

布局：

* ``include_smc=True`` → ``D=63``：``[0:24]`` 價格 (6×4) + ``[24:54]`` SMC (6×5)
  + ``[54:56]`` macro (2) + ``[56:63]`` weights (7)。
* ``include_smc=False`` → ``D=33``：``[0:24]`` 價格 + ``[24:26]`` macro
  + ``[26:33]`` weights。

實作策略（research R2）：先 ``numpy.zeros(D, dtype=float32)``、再分區 in-place
寫入，避免 ``numpy.concatenate`` 的記憶體配置順序差異產生跨平台不一致。
NaN 一律替換為 0.0 並回傳替換次數供 info 累計（FR-012）。
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np

from portfolio_env.data_loader import EnvData


class _ObsResult(NamedTuple):
    obs: np.ndarray  # shape (D,) float32
    nan_replaced: int  # 本次組裝中替換的 NaN 數量


def _safe_log_return(closes_col: np.ndarray, t: int, lookback: int) -> float:
    """``log(close_t / close_{t-lookback})``；t < lookback 時 backfill 用 t=0 值。"""
    if t < lookback:
        return 0.0
    prev = closes_col[t - lookback]
    cur = closes_col[t]
    if prev <= 0.0 or cur <= 0.0:
        return 0.0
    return float(np.log(cur / prev))


def _rolling_std_log_return(closes_col: np.ndarray, t: int, window: int) -> float:
    """20d log return std；t < window 時 backfill 用 t=0 值（即 0.0）。"""
    if t < window:
        return 0.0
    sub = closes_col[t - window : t + 1]
    if (sub <= 0.0).any():
        return 0.0
    log_returns = np.diff(np.log(sub))
    return float(log_returns.std(ddof=0))


def _replace_nan(value: float, counter: list[int]) -> float:
    if np.isnan(value) or np.isinf(value):
        counter[0] += 1
        return 0.0
    return value


def build_observation(
    env_data: EnvData,
    current_index: int,
    current_weights: np.ndarray,
    include_smc: bool,
    rf_daily_lookback: int = 20,
) -> _ObsResult:
    """組裝單步 observation。

    Args:
        env_data: 由 ``load_environment_data`` 產出的全 episode 資料快照。
        current_index: 當前 trading day index ∈ [0, T-1]。
        current_weights: shape (7,) 當前權重，將寫入 weights 區段。
        include_smc: 是否包含 SMC 區段（控制 D=63 vs D=33）。
        rf_daily_lookback: macro 區段「20d 利率變化」的 lookback 天數。

    Returns:
        ``(obs: ndarray (D,) float32, nan_replaced: int)``。
    """
    n_assets = env_data.closes.shape[1]
    if not include_smc:
        d = 4 * n_assets + 2 + (n_assets + 1)
    else:
        d = 4 * n_assets + 5 * n_assets + 2 + (n_assets + 1)

    obs = np.zeros(d, dtype=np.float32)
    nan_counter = [0]
    t = current_index

    # ---- §3.1.1 [0:24] 價格特徵（每檔 4 維）----
    for i in range(n_assets):
        col = env_data.closes[:, i]
        base = 4 * i
        obs[base + 0] = _replace_nan(_safe_log_return(col, t, 1), nan_counter)
        obs[base + 1] = _replace_nan(_safe_log_return(col, t, 5), nan_counter)
        obs[base + 2] = _replace_nan(_safe_log_return(col, t, 20), nan_counter)
        obs[base + 3] = _replace_nan(_rolling_std_log_return(col, t, 20), nan_counter)

    price_end = 4 * n_assets

    # ---- §3.1.2 [24:54] SMC 特徵 ----
    if include_smc:
        assert env_data.smc_features is not None, "include_smc=True 需 smc_features"
        smc_keys = list(env_data.smc_features.keys())
        for i, ticker in enumerate(smc_keys):
            arr = env_data.smc_features[ticker]
            base = price_end + 5 * i
            for k in range(5):
                v = float(arr[t, k])
                obs[base + k] = _replace_nan(v, nan_counter)
        macro_start = price_end + 5 * n_assets
    else:
        macro_start = price_end

    # ---- §3.1.3 macro [macro_start : macro_start+2] ----
    rf = env_data.rf_daily[t]
    obs[macro_start + 0] = _replace_nan(float(rf), nan_counter)
    if t < rf_daily_lookback:
        rf_change = 0.0
    else:
        rf_change = float(rf - env_data.rf_daily[t - rf_daily_lookback])
    obs[macro_start + 1] = _replace_nan(rf_change, nan_counter)

    # ---- §3.1.4 weights [macro_start+2 : ] ----
    weights_start = macro_start + 2
    for k in range(n_assets + 1):
        obs[weights_start + k] = _replace_nan(float(current_weights[k]), nan_counter)

    return _ObsResult(obs=obs, nan_replaced=nan_counter[0])


__all__ = ["build_observation"]
