"""T011 — single_step_inference unit tests.

對應 spec 010 FR-020。Mock sb3 policy（duck-typed）→ 確認 ActionResult 形狀
與 contract 一致。
"""

from __future__ import annotations

import numpy as np
import pytest

from live_tracking.inference import ActionResult, single_step_inference


class _MockPolicy:
    """Minimal sb3 policy stub — 只實作 predict, 沒有 evaluate_actions."""

    def __init__(self, raw_action: np.ndarray) -> None:
        self._raw = raw_action
        self.calls: list[tuple[np.ndarray, bool]] = []

    def predict(self, obs: np.ndarray, deterministic: bool = True):
        self.calls.append((obs, deterministic))
        return self._raw, None


@pytest.fixture
def obs() -> np.ndarray:
    # 33-dim no-SMC observation; module is shape-agnostic（直接傳 reshape(-1)）
    return np.linspace(-1.0, 1.0, 33, dtype=np.float32)


class TestActionResultShape:
    def test_returns_7_vectors_with_log_prob_and_entropy(self, obs: np.ndarray) -> None:
        raw = np.array([0.1, 0.2, 0.3, 0.0, -0.1, 0.5, 0.4], dtype=np.float32)
        policy = _MockPolicy(raw)
        result = single_step_inference(policy, obs)

        assert isinstance(result, ActionResult)
        assert len(result.raw) == 7
        assert len(result.normalized) == 7
        # softmax simplex
        assert pytest.approx(sum(result.normalized), abs=1e-6) == 1.0
        assert all(0.0 <= v <= 1.0 for v in result.normalized)
        # log_prob / entropy 在 mock policy 沒有 evaluate_actions 時 fallback 0
        assert result.log_prob == 0.0
        assert result.entropy == 0.0

    def test_passes_deterministic_flag(self, obs: np.ndarray) -> None:
        raw = np.zeros(7, dtype=np.float32)
        policy = _MockPolicy(raw)
        single_step_inference(policy, obs, deterministic=False)
        assert policy.calls[-1][1] is False

    def test_deterministic_default_is_true(self, obs: np.ndarray) -> None:
        raw = np.zeros(7, dtype=np.float32)
        policy = _MockPolicy(raw)
        single_step_inference(policy, obs)
        assert policy.calls[-1][1] is True


class TestSoftmaxCorrectness:
    def test_uniform_logits_produce_uniform_simplex(self, obs: np.ndarray) -> None:
        raw = np.zeros(7, dtype=np.float32)
        policy = _MockPolicy(raw)
        result = single_step_inference(policy, obs)
        for v in result.normalized:
            assert pytest.approx(v, abs=1e-6) == 1.0 / 7

    def test_extreme_logit_dominates(self, obs: np.ndarray) -> None:
        raw = np.array([10.0, -10, -10, -10, -10, -10, -10], dtype=np.float32)
        policy = _MockPolicy(raw)
        result = single_step_inference(policy, obs)
        # softmax of [10, -10, ..., -10] → essentially [~1, ~0, ..., ~0]
        assert result.normalized[0] > 0.99
        for i in range(1, 7):
            assert result.normalized[i] < 0.01


class TestNoEpisodeLoop:
    """FR-020：single_step 不能跑整段 episode（only one .predict call）。"""

    def test_single_predict_invocation(self, obs: np.ndarray) -> None:
        raw = np.zeros(7, dtype=np.float32)
        policy = _MockPolicy(raw)
        single_step_inference(policy, obs)
        assert len(policy.calls) == 1
