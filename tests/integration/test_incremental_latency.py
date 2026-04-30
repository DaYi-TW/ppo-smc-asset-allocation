"""T041 — incremental_compute 單根 K 棒延遲（spec SC-003：< 10 ms p50）。

策略：以 fixture 全段為 prior_window，從相同 state 起點重複呼叫 incremental_compute
若干次（每次配同一 new_bar），收集 wall-clock 時間，回報 p50 / p95 與是否達標。
"""

from __future__ import annotations

import time
from pathlib import Path
from statistics import median

import pandas as pd
import pytest

from smc_features import (
    SMCFeatureParams,
    batch_compute,
    incremental_compute,
)


@pytest.fixture
def fixture_df() -> pd.DataFrame:
    path = Path("tests/fixtures/nvda_2024H1.parquet")
    if not path.exists():
        pytest.skip(f"fixture {path} 不存在；先跑 scripts/build_smc_fixtures.py")
    return pd.read_parquet(path)


def test_incremental_p50_under_10ms(fixture_df: pd.DataFrame) -> None:
    """spec SC-003：p50 < 10 ms（日線 N ≤ 5000；本 fixture N ≈ 124 已遠低於上限）。"""
    p = SMCFeatureParams()
    prefix = fixture_df.iloc[:-1]
    new_bar = fixture_df.iloc[-1]
    state = batch_compute(prefix, p, include_aux=False).state

    # warm-up：避免首次匯入 / JIT 影響
    for _ in range(3):
        incremental_compute(state, new_bar)

    samples_ms: list[float] = []
    for _ in range(20):
        t0 = time.perf_counter()
        incremental_compute(state, new_bar)
        samples_ms.append((time.perf_counter() - t0) * 1000.0)

    p50 = median(samples_ms)
    p95 = sorted(samples_ms)[int(len(samples_ms) * 0.95) - 1]
    assert p50 < 10.0, f"p50 latency {p50:.2f} ms 超過 SC-003 上限 10 ms（p95={p95:.2f} ms）"
