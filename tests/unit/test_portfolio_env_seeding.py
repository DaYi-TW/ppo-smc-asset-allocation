"""Unit tests：四層 seed 同步（T012、research R1、spec FR-019）。"""

from __future__ import annotations

import random

import numpy as np

from portfolio_env import PortfolioEnv


def test_synchronize_seeds_two_calls_yield_identical_numpy_sequence(
    portfolio_default_config,
):
    """同 seed 兩次 reset 後從 ``env._numpy_rng`` 抽出之數列必須相同。"""
    env_a = PortfolioEnv(portfolio_default_config)
    env_b = PortfolioEnv(portfolio_default_config)
    env_a.reset(seed=42)
    env_b.reset(seed=42)
    a = env_a._numpy_rng.random(100)
    b = env_b._numpy_rng.random(100)
    assert np.array_equal(a, b)


def test_synchronize_seeds_does_not_pollute_global_numpy_random(
    portfolio_default_config,
):
    """``synchronize_seeds`` 後 ``numpy.random.random()`` 全域狀態未被覆蓋。"""
    np.random.seed(123)
    pre = np.random.random()
    env = PortfolioEnv(portfolio_default_config)
    env.reset(seed=42)
    np.random.seed(123)
    post = np.random.random()
    assert pre == post  # 全域 PRNG 未被 reset(seed=42) 污染


def test_synchronize_seeds_does_not_pollute_global_python_random(
    portfolio_default_config,
):
    """同上，對 Python ``random`` 全域狀態。"""
    random.seed(456)
    pre = random.random()
    env = PortfolioEnv(portfolio_default_config)
    env.reset(seed=42)
    random.seed(456)
    post = random.random()
    assert pre == post


def test_seed_none_does_not_raise(portfolio_default_config):
    """``seed=None`` 為 Gymnasium 慣例的 non-reproducible 模式，不應 raise。"""
    env = PortfolioEnv(portfolio_default_config)
    obs, _info = env.reset(seed=None)
    assert obs.shape == env.observation_space.shape


def test_py_random_attached_after_reset(portfolio_default_config):
    env = PortfolioEnv(portfolio_default_config)
    env.reset(seed=42)
    assert isinstance(env._py_random, random.Random)


def test_numpy_rng_attached_after_reset(portfolio_default_config):
    env = PortfolioEnv(portfolio_default_config)
    env.reset(seed=42)
    assert isinstance(env._numpy_rng, np.random.Generator)
