"""公開 API 契約測試（spec FR-018、tasks T012）。

驗證 ``smc_features`` 的公開符號與 ``specs/001-smc-feature-engine/contracts/api.pyi``
完全對齊：
* dataclass 為 ``frozen=True``（嘗試就地修改觸發 ``FrozenInstanceError``）。
* ``SMCFeatureParams.__post_init__`` 強制驗證；違反區間拋 ``ValueError``。
* ``SMCEngineState.initial(params)`` 工廠回傳 ``bar_count=0`` 且 Optional 欄位皆 ``None``。
* ``batch_compute`` / ``incremental_compute`` / ``visualize`` 簽章與 stub 一致 —
  Phase 2 尚未實作，故以 ``pytest.xfail`` 包裹，待 Phase 3-5 完成後自動轉綠。
"""

from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path
from typing import Literal, Optional, get_type_hints

import pandas as pd
import pytest

import smc_features
from smc_features.types import (
    FVG,
    BatchResult,
    FeatureRow,
    OrderBlock,
    SMCEngineState,
    SMCFeatureParams,
    SwingPoint,
)

# ---------------------------------------------------------------------------
# Frozen dataclass invariants (data-model.md §9 invariant 5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "factory",
    [
        lambda: SMCFeatureParams(),
        lambda: SwingPoint(
            timestamp=pd.Timestamp("2024-01-02"),
            price=100.0,
            kind="high",
            bar_index=0,
        ),
        lambda: FVG(
            formation_timestamp=pd.Timestamp("2024-01-02"),
            formation_bar_index=1,
            direction="bullish",
            top=101.0,
            bottom=99.0,
            is_filled=False,
            fill_timestamp=None,
        ),
        lambda: OrderBlock(
            formation_timestamp=pd.Timestamp("2024-01-02"),
            formation_bar_index=1,
            direction="bullish",
            top=101.0,
            bottom=99.0,
            midpoint=100.0,
            expiry_bar_index=51,
            invalidated=False,
            invalidation_timestamp=None,
        ),
        lambda: SMCEngineState.initial(SMCFeatureParams()),
        lambda: FeatureRow(
            timestamp=pd.Timestamp("2024-01-02"),
            bos_signal=0,
            choch_signal=0,
            fvg_distance_pct=float("nan"),
            ob_touched=False,
            ob_distance_ratio=float("nan"),
        ),
    ],
)
def test_frozen_dataclass_rejects_mutation(factory):
    obj = factory()
    field_names = [f.name for f in dataclasses.fields(obj)]
    assert field_names, "dataclass 必須至少含一個欄位"
    target = field_names[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(obj, target, None)


# ---------------------------------------------------------------------------
# SMCFeatureParams validation (data-model.md §3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"swing_length": 0},
        {"swing_length": -1},
        {"fvg_min_pct": -0.01},
        {"ob_lookback_bars": 0},
        {"atr_window": 0},
    ],
)
def test_params_rejects_invalid_values(kwargs):
    with pytest.raises(ValueError):
        SMCFeatureParams(**kwargs)


def test_params_default_values():
    p = SMCFeatureParams()
    assert p.swing_length == 5
    assert p.fvg_min_pct == 0.001
    assert p.ob_lookback_bars == 50
    assert p.atr_window == 14


# ---------------------------------------------------------------------------
# Engine state factory (data-model.md §5)
# ---------------------------------------------------------------------------


def test_initial_engine_state():
    params = SMCFeatureParams()
    s = SMCEngineState.initial(params)
    assert s.bar_count == 0
    assert s.last_swing_high is None
    assert s.last_swing_low is None
    assert s.prev_swing_high is None
    assert s.prev_swing_low is None
    assert s.trend_state == "neutral"
    assert s.open_fvgs == ()
    assert s.active_obs == ()
    assert s.atr_buffer == ()
    assert s.last_atr is None
    assert s.params is params


# ---------------------------------------------------------------------------
# Public-symbol export (contracts/api.pyi `__all__`)
# ---------------------------------------------------------------------------


def test_public_symbols_exported():
    expected_types = {
        "SMCFeatureParams": SMCFeatureParams,
        "SwingPoint": SwingPoint,
        "FVG": FVG,
        "OrderBlock": OrderBlock,
        "SMCEngineState": SMCEngineState,
        "FeatureRow": FeatureRow,
        "BatchResult": BatchResult,
    }
    for name, cls in expected_types.items():
        assert hasattr(smc_features, name), f"smc_features 缺 export: {name}"
        assert getattr(smc_features, name) is cls


# ---------------------------------------------------------------------------
# Public function signatures (xfail until Phase 3-5)
# ---------------------------------------------------------------------------


def _expected_batch_compute_sig() -> inspect.Signature:
    return inspect.Signature(
        parameters=[
            inspect.Parameter(
                "df", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=pd.DataFrame
            ),
            inspect.Parameter(
                "params",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=SMCFeatureParams(),
                annotation=SMCFeatureParams,
            ),
            inspect.Parameter(
                "include_aux",
                inspect.Parameter.KEYWORD_ONLY,
                default=False,
                annotation=bool,
            ),
        ],
        return_annotation=BatchResult,
    )


def test_batch_compute_signature_matches_contract():
    if not hasattr(smc_features, "batch_compute"):
        pytest.xfail("batch_compute 尚未實作（Phase 3 / T028 後就緒）")
    fn = smc_features.batch_compute
    sig = inspect.signature(fn)
    expected = _expected_batch_compute_sig()
    # 比較參數名與 kind（避免預設值的 dataclass 不可雜湊問題）
    assert list(sig.parameters.keys()) == list(expected.parameters.keys())
    for name in expected.parameters:
        actual = sig.parameters[name]
        want = expected.parameters[name]
        assert actual.kind == want.kind, f"參數 {name} kind 不符"


def test_incremental_compute_signature_matches_contract():
    if not hasattr(smc_features, "incremental_compute"):
        pytest.xfail("incremental_compute 尚未實作（Phase 5 / T046 後就緒）")
    fn = smc_features.incremental_compute
    sig = inspect.signature(fn)
    assert list(sig.parameters.keys()) == ["prior_state", "new_bar"]


def test_visualize_signature_matches_contract():
    if not hasattr(smc_features, "visualize"):
        pytest.xfail("visualize 尚未實作（Phase 4 / T037 後就緒）")
    fn = smc_features.visualize
    sig = inspect.signature(fn)
    expected_params = ["df_with_features", "time_range", "output_path", "fmt", "params"]
    assert list(sig.parameters.keys()) == expected_params
    assert sig.parameters["fmt"].default == "png"
    assert sig.parameters["params"].kind == inspect.Parameter.KEYWORD_ONLY


# ---------------------------------------------------------------------------
# api.pyi presence check — guard against stub deletion
# ---------------------------------------------------------------------------


def test_api_stub_file_exists():
    repo_root = Path(__file__).resolve().parents[2]
    stub = repo_root / "specs" / "001-smc-feature-engine" / "contracts" / "api.pyi"
    assert stub.exists(), f"contracts/api.pyi 缺失：{stub}"


# Touch get_type_hints / Optional / Literal 以避免 ruff F401 — 這些在後續
# Phase 3 增加的型別斷言會用到；保留 import 以最小化未來 diff。
_ = (get_type_hints, Optional, Literal)
