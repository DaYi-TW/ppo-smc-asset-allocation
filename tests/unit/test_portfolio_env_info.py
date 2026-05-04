"""Unit tests：``info_to_json_safe`` round-trip（T025、FR-026、SC-008）。"""

from __future__ import annotations

import json

import numpy as np

from portfolio_env import info_to_json_safe


def test_numpy_arrays_converted_to_list():
    info = {"weights": np.array([0.1, 0.2, 0.7], dtype=np.float32)}
    safe = info_to_json_safe(info)
    assert safe["weights"] == [
        float(np.float32(0.1)),
        float(np.float32(0.2)),
        float(np.float32(0.7)),
    ]
    json.dumps(safe)  # 不 raise


def test_numpy_scalar_converted():
    info = {
        "nav": np.float64(1.234567890123),
        "step": np.int64(42),
        "flag": np.bool_(True),
    }
    safe = info_to_json_safe(info)
    assert isinstance(safe["nav"], float)
    assert isinstance(safe["step"], int)
    assert isinstance(safe["flag"], bool)
    assert safe["flag"] is True


def test_nested_dict_recursed():
    info = {
        "reward_components": {
            "log_return": np.float64(0.01),
            "drawdown_penalty": np.float64(0.001),
            "turnover_penalty": np.float64(0.0005),
        }
    }
    safe = info_to_json_safe(info)
    assert isinstance(safe["reward_components"]["log_return"], float)
    json.dumps(safe)


def test_float64_round_trip_lossless():
    """SC-008：float64 經 ``json.dumps`` round-trip 必須無精度損失。"""
    val = 1.234567890123456789
    info = {"nav": np.float64(val)}
    safe = info_to_json_safe(info)
    restored = json.loads(json.dumps(safe))
    assert restored["nav"] == val


def test_list_of_arrays_recursed():
    info = {"trace": [np.array([1.0, 2.0]), np.array([3.0, 4.0])]}
    safe = info_to_json_safe(info)
    assert safe["trace"] == [[1.0, 2.0], [3.0, 4.0]]
    json.dumps(safe)


def test_strings_passthrough():
    info = {"date": "2024-01-02", "label": "x"}
    safe = info_to_json_safe(info)
    assert safe["date"] == "2024-01-02"
    assert safe["label"] == "x"
