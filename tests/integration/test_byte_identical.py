"""T020 — 重現性：相同 (df, params) 兩次呼叫 byte-identical。

對應 spec FR-006 與 data-model.md §9 invariant 3。
"""

from __future__ import annotations

import pandas as pd

from smc_features import batch_compute


def test_byte_identical_two_runs(small_ohlcv, default_params):
    br_a = batch_compute(small_ohlcv, default_params)
    br_b = batch_compute(small_ohlcv, default_params)
    pd.testing.assert_frame_equal(
        br_a.output,
        br_b.output,
        check_dtype=True,
        check_exact=True,
    )


def test_byte_identical_with_aux(small_ohlcv, default_params):
    br_a = batch_compute(small_ohlcv, default_params, include_aux=True)
    br_b = batch_compute(small_ohlcv, default_params, include_aux=True)
    pd.testing.assert_frame_equal(
        br_a.output,
        br_b.output,
        check_dtype=True,
        check_exact=True,
    )


def test_byte_identical_on_sample(sample_ohlcv, default_params):
    br_a = batch_compute(sample_ohlcv, default_params)
    br_b = batch_compute(sample_ohlcv, default_params)
    pd.testing.assert_frame_equal(
        br_a.output,
        br_b.output,
        check_dtype=True,
        check_exact=True,
    )
