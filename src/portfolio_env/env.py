"""``PortfolioEnv`` — Gymnasium 0.29+ 多資產組合配置環境。

對應 spec 003-ppo-training-env 之 FR-001~027、SC-001~008、四大 user story。

核心方法：

* :meth:`__init__` — 載入資料、SMC 預計算、hash 比對、初始化 spaces。
* :meth:`reset` — 四層 PRNG 同步、清空 episode 狀態、回傳初始 observation + info。
* :meth:`step` — NAV 推進、reward 三項分量、observation 重組、終止判定。
* :meth:`render` — 依 ``self.render_mode`` 分流（None / "ansi"）。
* :meth:`close` — no-op（無外部資源）。

不變式（data-model §7）：

1. Reward 三項加總 == reward（容差 1e-9 / SC-007 純 ablation 1e-12）。
2. NAV 連續性：``nav_t = nav_{t-1} × (1 + dot(w, returns) + w[6] × rf_daily)``。
3. Weights simplex：sum=1（1e-9）、min≥0、stocks max ≤ position_cap。
4. Observation shape：63（include_smc）/33（no SMC），dtype float32。
5. Episode 長度 == ``len(_trading_days) - 1``。
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, ClassVar

import gymnasium
import numpy as np
import pandas as pd
from gymnasium.spaces import Box

from portfolio_env.action import process_action
from portfolio_env.config import PortfolioEnvConfig
from portfolio_env.data_loader import EnvData, load_environment_data
from portfolio_env.info import build_info
from portfolio_env.observation import build_observation
from portfolio_env.render import render_ansi
from portfolio_env.reward import compute_reward_components
from portfolio_env.seeding import synchronize_seeds

_NUM_ASSETS = 6  # 六檔股票（不含 CASH）
_ACTION_DIM = 7  # 含 CASH


class PortfolioEnv(gymnasium.Env):
    """多資產組合配置 RL 環境。

    Observation: ``Box(shape=(63,) or (33,), dtype=float32)`` — 詳見
    ``data-model.md §3``。
    Action: ``Box(shape=(7,), low=0, high=1, dtype=float32)`` — 詳見 §4。
    Reward: ``log(NAV_t/NAV_{t-1}) - λ_mdd × drawdown - λ_turnover × turnover``。
    """

    metadata: ClassVar[dict[str, Any]] = {"render_modes": ["ansi"], "render_fps": 0}

    def __init__(self, config: PortfolioEnvConfig) -> None:
        super().__init__()
        self.config = config
        self.render_mode = config.render_mode

        # 載入 + hash 驗證 + SMC 預計算（research R5/R6/R7）
        self._env_data: EnvData = load_environment_data(config)

        # data_hashes 包成不可變 view，每步 step 共用同一 dict（避免 mutate）。
        # 僅暴露 config.assets 對應的股票 hash；DTB3 hash 已於 __init__ 階段驗證
        # （fail-fast），不屬 info-schema.data_hashes 範疇（pattern '^[A-Z]+$' 拒
        # 含數字 key）。
        _stock_hashes = {t: self._env_data.data_hashes[t] for t in config.assets}
        self._cached_data_hashes = MappingProxyType(_stock_hashes)

        # Spaces
        if config.include_smc:
            obs_dim = 4 * _NUM_ASSETS + 5 * _NUM_ASSETS + 2 + _ACTION_DIM  # 63
        else:
            obs_dim = 4 * _NUM_ASSETS + 2 + _ACTION_DIM  # 33
        self.observation_space = Box(
            low=-np.inf,
            high=np.inf,
            shape=(obs_dim,),
            dtype=np.float32,
        )
        self.action_space = Box(
            low=0.0,
            high=1.0,
            shape=(_ACTION_DIM,),
            dtype=np.float32,
        )

        # Episode 狀態（reset 時填）
        self.current_index: int = 0
        self.current_weights: np.ndarray = np.full(_ACTION_DIM, 1.0 / _ACTION_DIM, dtype=np.float32)
        self.nav_history: list[float] = [config.initial_nav]
        self.peak_nav: float = config.initial_nav
        self._skipped_dates: list[str] = []
        self._cumulative_nan_replaced: int = 0

        # PRNG（reset 時填；屬性先預宣告以利 type checker）
        self._py_random: Any = None
        self._numpy_rng: Any = None

    # ------------------------------------------------------------------
    # Gymnasium API
    # ------------------------------------------------------------------

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        """重設 episode、同步 seed，回傳 (obs, info)。"""
        super().reset(seed=seed)
        synchronize_seeds(self, seed)

        self.current_index = 0
        self.current_weights = np.full(_ACTION_DIM, 1.0 / _ACTION_DIM, dtype=np.float32)
        self.nav_history = [self.config.initial_nav]
        self.peak_nav = self.config.initial_nav
        self._skipped_dates = list(self._env_data.skipped_dates_init)
        self._cumulative_nan_replaced = 0

        obs_result = build_observation(
            env_data=self._env_data,
            current_index=self.current_index,
            current_weights=self.current_weights,
            include_smc=self.config.include_smc,
        )
        self._cumulative_nan_replaced += obs_result.nan_replaced

        nav = self.nav_history[-1]
        asset_values = nav * self.current_weights[:_NUM_ASSETS]
        cash = nav * self.current_weights[_NUM_ASSETS]
        date_str = self._date_str(self.current_index)
        action_raw = np.zeros(_ACTION_DIM, dtype=np.float32)

        info = build_info(
            date_str=date_str,
            weights=self.current_weights,
            nav=nav,
            peak_nav=self.peak_nav,
            asset_values=asset_values,
            cash=cash,
            turnover=0.0,
            slippage_bps=0.0,
            log_return=0.0,
            drawdown_penalty=0.0,
            turnover_penalty=0.0,
            action_raw=action_raw,
            action_processed=self.current_weights,
            action_renormalized=False,
            position_capped=False,
            nan_replaced=self._cumulative_nan_replaced,
            is_initial_step=True,
            data_hashes=self._cached_data_hashes,
            skipped_dates=self._skipped_dates,
        )
        return obs_result.obs, info

    def step(
        self,
        action: np.ndarray,
    ) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        """前進一步：處理 action、推進 NAV、計 reward、組 observation+info。"""
        prev_weights = self.current_weights.copy()
        prev_nav = self.nav_history[-1]
        action_raw = np.asarray(action, dtype=np.float32).copy()

        processed = process_action(action, position_cap=self.config.position_cap)

        # 推進到下一 trading day（research R2 固定運算順序）
        next_index = self.current_index + 1
        returns_next = self._env_data.returns[next_index]  # shape (6,)
        rf_next = float(self._env_data.rf_daily[next_index])

        # nav_t = nav_{t-1} × (1 + Σ w[i]×ret[i] + w[6]×rf_daily)
        # 字面順序：先算 stocks 部分、再加 cash 部分、再 +1.0、再乘 prev_nav。
        stocks_w = processed.weights[:_NUM_ASSETS].astype(np.float64)
        cash_w = float(processed.weights[_NUM_ASSETS])
        portfolio_return = float(np.dot(stocks_w, returns_next.astype(np.float64))) + (
            cash_w * rf_next
        )
        nav = prev_nav * (1.0 + portfolio_return)

        # 先更新 peak（基於 prev_nav）— data-model §7 不變式 2：peak_t = max(peak_{t-1}, nav_{t-1})
        peak_for_drawdown = max(self.peak_nav, prev_nav)
        # 計算 reward
        rc = self.config.reward_config
        components = compute_reward_components(
            prev_nav=prev_nav,
            nav=nav,
            peak_nav=peak_for_drawdown,
            prev_weights=prev_weights,
            weights=processed.weights,
            lambda_mdd=rc.lambda_mdd,
            lambda_turnover=rc.lambda_turnover,
            is_initial_step=False,
        )

        # 推進狀態
        self.peak_nav = max(peak_for_drawdown, nav)
        self.nav_history.append(nav)
        self.current_index = next_index
        self.current_weights = processed.weights

        # Observation
        obs_result = build_observation(
            env_data=self._env_data,
            current_index=self.current_index,
            current_weights=self.current_weights,
            include_smc=self.config.include_smc,
        )
        self._cumulative_nan_replaced += obs_result.nan_replaced

        # Info
        asset_values = nav * processed.weights[:_NUM_ASSETS]
        cash = nav * processed.weights[_NUM_ASSETS]
        turnover = 0.5 * float(np.abs(processed.weights - prev_weights).sum())
        slippage_bps = float(self.config.base_slippage_bps) * turnover
        date_str = self._date_str(self.current_index)

        info = build_info(
            date_str=date_str,
            weights=processed.weights,
            nav=nav,
            peak_nav=self.peak_nav,
            asset_values=asset_values,
            cash=cash,
            turnover=turnover,
            slippage_bps=slippage_bps,
            log_return=components.log_return,
            drawdown_penalty=components.drawdown_penalty,
            turnover_penalty=components.turnover_penalty,
            action_raw=action_raw,
            action_processed=processed.weights,
            action_renormalized=processed.action_renormalized,
            position_capped=processed.position_capped,
            nan_replaced=self._cumulative_nan_replaced,
            is_initial_step=False,
            data_hashes=self._cached_data_hashes,
            skipped_dates=self._skipped_dates,
        )

        terminated = self.current_index >= self._env_data.trading_days.size - 1
        truncated = False
        return obs_result.obs, float(components.reward), terminated, truncated, info

    def render(self) -> str | None:
        """依 ``self.render_mode`` 分流。"""
        if self.render_mode is None:
            return None
        if self.render_mode == "ansi":
            # 用最近一步的狀態組裝；若 reset 後尚未 step，回傳簡單摘要。
            nav = self.nav_history[-1]
            weights_str = "[" + ",".join(f"{w:.3f}" for w in self.current_weights) + "]"
            return (
                f"date={self._date_str(self.current_index)} "
                f"nav={nav:.4f} peak={self.peak_nav:.4f} "
                f"weights={weights_str}"
            )
        return None

    def close(self) -> None:
        """no-op — 無外部資源需釋放。"""
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _date_str(self, index: int) -> str:
        ts = pd.Timestamp(self._env_data.trading_days[index])
        return ts.strftime("%Y-%m-%d")


__all__ = ["PortfolioEnv", "render_ansi"]
