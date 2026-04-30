"""US1 端到端：``batch_compute`` 在 NVDA fixture 上的合約驗證（T019）。

涵蓋 spec FR-001 / FR-002~FR-005 與 data-model.md §9 invariant 1, 2。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from smc_features import BatchResult, SMCEngineState, batch_compute


def test_batch_compute_returns_batch_result(small_ohlcv, default_params):
    br = batch_compute(small_ohlcv, default_params)
    assert isinstance(br, BatchResult)
    assert isinstance(br.output, pd.DataFrame)
    assert isinstance(br.state, SMCEngineState)


def test_row_count_preserved(small_ohlcv, default_params):
    br = batch_compute(small_ohlcv, default_params)
    assert len(br.output) == len(small_ohlcv)


def test_index_preserved(small_ohlcv, default_params):
    br = batch_compute(small_ohlcv, default_params)
    pd.testing.assert_index_equal(br.output.index, small_ohlcv.index)


def test_feature_columns_present(small_ohlcv, default_params):
    br = batch_compute(small_ohlcv, default_params)
    expected = {
        "bos_signal",
        "choch_signal",
        "fvg_distance_pct",
        "ob_touched",
        "ob_distance_ratio",
    }
    assert expected.issubset(set(br.output.columns))


def test_signal_value_domain(small_ohlcv, default_params):
    br = batch_compute(small_ohlcv, default_params)
    bos = br.output["bos_signal"].dropna().unique()
    choch = br.output["choch_signal"].dropna().unique()
    assert set(int(v) for v in bos).issubset({-1, 0, 1})
    assert set(int(v) for v in choch).issubset({-1, 0, 1})


def test_ob_touched_dtype_is_boolean(small_ohlcv, default_params):
    br = batch_compute(small_ohlcv, default_params)
    # nullable boolean dtype，dropna 後型別為 BooleanArray
    assert str(br.output["ob_touched"].dtype) == "boolean"


def test_distance_pct_is_float64(small_ohlcv, default_params):
    br = batch_compute(small_ohlcv, default_params)
    assert br.output["fvg_distance_pct"].dtype == np.float64
    assert br.output["ob_distance_ratio"].dtype == np.float64


def test_state_terminal_bar_count_matches(small_ohlcv, default_params):
    br = batch_compute(small_ohlcv, default_params)
    assert br.state.bar_count == len(small_ohlcv)


def test_include_aux_adds_six_columns(small_ohlcv, default_params):
    br_min = batch_compute(small_ohlcv, default_params, include_aux=False)
    br_aux = batch_compute(small_ohlcv, default_params, include_aux=True)
    aux_cols = {
        "swing_high_marker",
        "swing_low_marker",
        "fvg_top_active",
        "fvg_bottom_active",
        "ob_top_active",
        "ob_bottom_active",
    }
    assert aux_cols.issubset(set(br_aux.output.columns))
    assert not aux_cols.intersection(set(br_min.output.columns))


def test_invalid_index_non_monotonic_raises(small_ohlcv, default_params):
    bad = small_ohlcv.iloc[::-1].copy()
    with pytest.raises(ValueError, match="單調"):
        batch_compute(bad, default_params)


def test_missing_column_raises(small_ohlcv, default_params):
    bad = small_ohlcv.drop(columns=["volume"])
    with pytest.raises(KeyError, match="volume"):
        batch_compute(bad, default_params)


def test_default_params_used_when_omitted(small_ohlcv):
    br = batch_compute(small_ohlcv)
    assert br.state.params.swing_length == 5
    assert br.state.params.fvg_min_pct == 0.001
