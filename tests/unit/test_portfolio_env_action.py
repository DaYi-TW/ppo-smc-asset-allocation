"""Unit tests：``process_action`` 三道處理（T021、spec FR-014、research R9）。"""

from __future__ import annotations

import numpy as np
import pytest

from portfolio_env.action import process_action

_CAP = 0.4


def test_nan_action_raises():
    a = np.array([float("nan"), 0.1, 0.1, 0.1, 0.2, 0.2, 0.3], dtype=np.float32)
    with pytest.raises(ValueError, match="NaN"):
        process_action(a, position_cap=_CAP)


def test_zero_sum_action_raises():
    a = np.zeros(7, dtype=np.float32)
    with pytest.raises(ValueError, match="near zero"):
        process_action(a, position_cap=_CAP)


def test_unit_simplex_action_no_renormalize():
    """sum 已 == 1 且不超 cap → 不觸發 normalize 也不觸發 cap。"""
    a = np.array([0.3, 0.1, 0.1, 0.1, 0.2, 0.1, 0.1], dtype=np.float32)
    pa = process_action(a, position_cap=_CAP)
    assert pa.action_renormalized is False
    assert pa.position_capped is False
    np.testing.assert_allclose(pa.weights.sum(), 1.0, atol=1e-6)


def test_renormalize_triggers_when_sum_not_one():
    """e.g. ``[1, 1, 0, ...]`` (sum=2) → 觸發 normalize → ``[0.5, 0.5, 0, ...]``。"""
    a = np.array([1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    pa = process_action(a, position_cap=_CAP)
    assert pa.action_renormalized is True
    # 0.5 > 0.4 → cap 也應觸發
    assert pa.position_capped is True
    assert pa.weights[:6].max() <= _CAP + 1e-6


def test_position_cap_redistributes_excess():
    """``[0.6, 0.1, 0.1, 0.05, 0.05, 0.05, 0.05]`` → cap 觸發、最大值 ≤ 0.4。"""
    a = np.array([0.6, 0.1, 0.1, 0.05, 0.05, 0.05, 0.05], dtype=np.float32)
    pa = process_action(a, position_cap=_CAP)
    assert pa.position_capped is True
    assert pa.weights[:6].max() <= _CAP + 1e-6
    np.testing.assert_allclose(pa.weights.sum(), 1.0, atol=1e-6)


def test_cash_not_capped():
    """CASH（index 6）允許 100% 配置。"""
    a = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0], dtype=np.float32)
    pa = process_action(a, position_cap=_CAP)
    assert pa.position_capped is False
    assert pa.weights[6] == pytest.approx(1.0, abs=1e-6)


def test_water_filling_multi_over_cap():
    """多檔同時 > cap 的 case：``[0.5, 0.5, 0, 0, 0, 0, 0]`` → 兩檔皆鎖到 0.4 後 0.2 分到 CASH。"""
    a = np.array([0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    pa = process_action(a, position_cap=_CAP)
    assert pa.position_capped is True
    assert pa.weights[:6].max() <= _CAP + 1e-6
    np.testing.assert_allclose(pa.weights.sum(), 1.0, atol=1e-6)


def test_action_non_negative_after_processing():
    """裁掉浮點負值雜訊後所有權重應 ≥ 0。"""
    a = np.array([-1e-10, 0.2, 0.2, 0.2, 0.2, 0.1, 0.1], dtype=np.float32)
    pa = process_action(a, position_cap=_CAP)
    assert pa.weights.min() >= 0.0


def test_invalid_shape_raises():
    a = np.array([0.5, 0.5], dtype=np.float32)
    with pytest.raises(ValueError, match="shape"):
        process_action(a, position_cap=_CAP)
