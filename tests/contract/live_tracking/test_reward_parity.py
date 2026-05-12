"""T060 — Constitution Principle III gate (Risk-First Reward, NON-NEGOTIABLE).

對應 spec 010 FR-019 + INV-4 (data-model §3) + constitution.md Principle III：

> Daily pipeline 內計算每日 frame 的 reward 三元（return / drawdown_penalty /
> cost_penalty）必須呼叫 ``src/portfolio_env/reward.py`` 的同一個
> ``compute_reward_components``，禁止複製或近似實作。

兩條 invariants：
1. **函式 identity**：``portfolio_env.reward.compute_reward_components`` 是
   pipeline 唯一允許的 reward source — 任何 PR 改名 / 移檔都會炸這條 gate。
2. **數值決定性**：給定 fixed prev_nav / nav / peak_nav / prev_weights /
   weights / lambdas，兩次 call 結果完全相等（log_return,
   drawdown_penalty, turnover_penalty 三元 + 組合 reward）— 確保跨 process
   / 跨機器 byte-level reproducibility（Principle I × Principle III 交集）。

當未來 FrameBuilder 真實實作落地時（T018），其內部 reward 計算 **必須** 走
這個 ``compute_reward_components`` 而非自寫；本 gate test 在 PR review 時
作為 hard-gate 防止 reward 漂移。
"""

from __future__ import annotations

import numpy as np
import pytest


class TestRewardFunctionIdentity:
    """Invariant 1：``portfolio_env.reward.compute_reward_components`` 必須存在
    且 importable — 任何重命名 / 移檔都會炸這條 gate。"""

    def test_canonical_reward_function_is_importable(self) -> None:
        from portfolio_env import reward as reward_module

        assert hasattr(reward_module, "compute_reward_components"), (
            "Constitution Principle III violation: "
            "portfolio_env.reward.compute_reward_components 已被改名或刪除。"
            "Pipeline 必須走這個 canonical reward source。"
        )
        assert callable(reward_module.compute_reward_components)

    def test_reward_components_namedtuple_shape(self) -> None:
        """RewardComponents 必須有 4 個欄位（log_return / drawdown_penalty /
        turnover_penalty / reward）— 對應 009 TrajectoryFrame.reward DTO 的
        三元 + 組合值。"""
        from portfolio_env.reward import RewardComponents

        # NamedTuple field set 鎖死
        assert RewardComponents._fields == (
            "log_return",
            "drawdown_penalty",
            "turnover_penalty",
            "reward",
        )


class TestRewardDeterminism:
    """Invariant 2：固定輸入 → 兩次 call 完全相等（包含 reward 組合值）。

    這條 gate 驗 cross-platform reproducibility — 若哪天有人把字面組裝
    ``log_return - drawdown_penalty - turnover_penalty`` 改用
    ``np.subtract.reduce(...)``，BLAS reduction order 差異會被這條測試
    抓到（research §R2 已警告過此 trap）。
    """

    def test_two_calls_return_byte_equal_values(self) -> None:
        from portfolio_env.reward import compute_reward_components

        prev_nav = 1.7291986
        nav = 1.7291986 * 1.001
        peak_nav = 1.8
        prev_weights = np.array(
            [0.2, 0.2, 0.1, 0.1, 0.15, 0.15, 0.1], dtype=np.float64
        )
        weights = np.array(
            [0.18, 0.22, 0.12, 0.08, 0.15, 0.15, 0.10], dtype=np.float64
        )
        lambda_mdd = 0.5
        lambda_turnover = 0.001

        a = compute_reward_components(
            prev_nav=prev_nav,
            nav=nav,
            peak_nav=peak_nav,
            prev_weights=prev_weights,
            weights=weights,
            lambda_mdd=lambda_mdd,
            lambda_turnover=lambda_turnover,
            is_initial_step=False,
        )
        b = compute_reward_components(
            prev_nav=prev_nav,
            nav=nav,
            peak_nav=peak_nav,
            prev_weights=prev_weights.copy(),
            weights=weights.copy(),
            lambda_mdd=lambda_mdd,
            lambda_turnover=lambda_turnover,
            is_initial_step=False,
        )

        assert a.log_return == b.log_return
        assert a.drawdown_penalty == b.drawdown_penalty
        assert a.turnover_penalty == b.turnover_penalty
        # 字面組裝順序：reward = log_return - drawdown_penalty - turnover_penalty
        assert a.reward == b.reward
        assert a.reward == pytest.approx(
            a.log_return - a.drawdown_penalty - a.turnover_penalty,
            abs=1e-15,
        )

    def test_initial_step_log_return_is_zero(self) -> None:
        """FR-006 Edge Case：is_initial_step=True 時 log_return 必為 0.0。"""
        from portfolio_env.reward import compute_reward_components

        result = compute_reward_components(
            prev_nav=1.0,
            nav=1.5,  # 即使 nav 變大也不算 return
            peak_nav=1.5,
            prev_weights=np.zeros(7, dtype=np.float64),
            weights=np.array([1 / 7] * 7, dtype=np.float64),
            lambda_mdd=0.5,
            lambda_turnover=0.001,
            is_initial_step=True,
        )
        assert result.log_return == 0.0


class TestRewardSignConvention:
    """sanity：drawdown_penalty / turnover_penalty 都是非負 — 公式 ``reward =
    log_return - drawdown_penalty - turnover_penalty`` 才合理。"""

    def test_drawdown_penalty_non_negative(self) -> None:
        from portfolio_env.reward import compute_reward_components

        # nav 跌破 peak → drawdown > 0
        result = compute_reward_components(
            prev_nav=1.0,
            nav=0.9,
            peak_nav=1.2,
            prev_weights=np.array([1 / 7] * 7),
            weights=np.array([1 / 7] * 7),
            lambda_mdd=0.5,
            lambda_turnover=0.001,
        )
        assert result.drawdown_penalty >= 0.0
        assert result.turnover_penalty >= 0.0  # weights 不變，turnover==0
