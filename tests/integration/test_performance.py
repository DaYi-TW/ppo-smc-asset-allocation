"""T030 — 性能 smoke：sample fixture 兩年日線批次計算 < 30 秒（spec SC-001）。

實際 NVDA 兩年日線 ~500 列遠少於 30 秒上限；本 test 提供回歸護欄，避免未來
重構引入的退化（例如非向量化迴圈展開到大 fixture）。
"""

from __future__ import annotations

import time

import pytest

from smc_features import batch_compute


@pytest.mark.benchmark
def test_batch_compute_under_30s(sample_ohlcv, default_params):
    t0 = time.perf_counter()
    br = batch_compute(sample_ohlcv, default_params)
    elapsed = time.perf_counter() - t0
    assert len(br.output) == len(sample_ohlcv)
    assert elapsed < 30.0, f"batch_compute on ~{len(sample_ohlcv)} bars took {elapsed:.2f}s"
