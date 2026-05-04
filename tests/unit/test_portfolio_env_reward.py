"""Unit tests：``compute_reward_components``（T023、FR-006/9、SC-007）。"""

from __future__ import annotations

import numpy as np
import pytest

from portfolio_env.reward import compute_reward_components

_W = np.array([0.2, 0.2, 0.1, 0.1, 0.2, 0.1, 0.1], dtype=np.float32)
_W2 = np.array([0.1, 0.1, 0.2, 0.2, 0.1, 0.2, 0.1], dtype=np.float32)


def test_initial_step_log_return_zero():
    """首步強制 log_return == 0（FR-016 / spec Edge Case）。"""
    rc = compute_reward_components(
        prev_nav=1.0,
        nav=1.05,
        peak_nav=1.0,
        prev_weights=_W,
        weights=_W,
        lambda_mdd=1.0,
        lambda_turnover=0.0015,
        is_initial_step=True,
    )
    assert rc.log_return == 0.0


def test_zero_lambdas_reduce_to_log_return():
    """SC-007 ablation：``λ_mdd = λ_turnover = 0`` → ``reward == log_return``，容差 1e-12。"""
    rc = compute_reward_components(
        prev_nav=1.0,
        nav=1.05,
        peak_nav=1.05,
        prev_weights=_W,
        weights=_W2,
        lambda_mdd=0.0,
        lambda_turnover=0.0,
        is_initial_step=False,
    )
    assert abs(rc.reward - rc.log_return) < 1e-12


def test_drawdown_zero_when_nav_at_or_above_peak():
    """nav >= peak → drawdown = 0。"""
    rc = compute_reward_components(
        prev_nav=1.0,
        nav=1.10,
        peak_nav=1.05,
        prev_weights=_W,
        weights=_W,
        lambda_mdd=1.0,
        lambda_turnover=0.0,
        is_initial_step=False,
    )
    assert rc.drawdown_penalty == 0.0


def test_drawdown_positive_when_nav_below_peak():
    rc = compute_reward_components(
        prev_nav=1.20,
        nav=1.00,
        peak_nav=1.20,
        prev_weights=_W,
        weights=_W,
        lambda_mdd=1.0,
        lambda_turnover=0.0,
        is_initial_step=False,
    )
    expected_dd = (1.20 - 1.00) / 1.20
    assert rc.drawdown_penalty == pytest.approx(expected_dd, abs=1e-12)


def test_turnover_in_unit_range():
    rc = compute_reward_components(
        prev_nav=1.0,
        nav=1.0,
        peak_nav=1.0,
        prev_weights=_W,
        weights=_W2,
        lambda_mdd=0.0,
        lambda_turnover=1.0,
        is_initial_step=False,
    )
    assert 0.0 <= rc.turnover_penalty <= 1.0


def test_three_components_sum_to_reward_within_tol():
    """``log_return - drawdown_penalty - turnover_penalty == reward``，容差 1e-9（FR-009）。"""
    rc = compute_reward_components(
        prev_nav=1.0,
        nav=1.05,
        peak_nav=1.10,  # 5% nav < peak → drawdown 5/110
        prev_weights=_W,
        weights=_W2,
        lambda_mdd=1.0,
        lambda_turnover=0.0015,
        is_initial_step=False,
    )
    recomputed = rc.log_return - rc.drawdown_penalty - rc.turnover_penalty
    assert abs(recomputed - rc.reward) < 1e-9


def test_zero_turnover_when_weights_unchanged():
    rc = compute_reward_components(
        prev_nav=1.0,
        nav=1.0,
        peak_nav=1.0,
        prev_weights=_W,
        weights=_W,
        lambda_mdd=0.0,
        lambda_turnover=1.0,
        is_initial_step=False,
    )
    assert rc.turnover_penalty == 0.0
