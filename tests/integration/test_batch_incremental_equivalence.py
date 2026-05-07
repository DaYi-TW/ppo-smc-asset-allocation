"""T040 — batch / incremental byte-identical 等價性（spec FR-008、invariant 4）。"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
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


def _row_equal(batch_row: pd.Series, feature_row, atol: float = 1e-9) -> None:
    # int 欄位 ==
    for col in ("bos_signal", "choch_signal"):
        bv = batch_row[col]
        fv = getattr(feature_row, col)
        if pd.isna(bv):
            assert fv == 0
        else:
            assert int(bv) == int(fv), f"{col}: batch={bv} vs incremental={fv}"
    # bool 欄位
    bv = batch_row["ob_touched"]
    fv = feature_row.ob_touched
    if pd.isna(bv):
        assert fv is False
    else:
        assert bool(bv) == bool(fv)
    # float 欄位（NaN 對應）
    for col in ("fvg_distance_pct", "ob_distance_ratio"):
        bv = batch_row[col]
        fv = getattr(feature_row, col)
        if pd.isna(bv):
            assert math.isnan(fv), f"{col}: batch=NaN, incremental={fv}"
        else:
            assert math.isclose(float(bv), float(fv), abs_tol=atol), (
                f"{col}: batch={bv} vs incremental={fv}"
            )


def test_last_50_bars_equivalent_to_batch(fixture_df: pd.DataFrame):
    """逐根用 incremental 推進，每步與「對應前綴的 batch 末列」比對。

    Note: 不能直接和 ``batch(full_df).iloc[i]`` 比對 — swing 偵測需要
    ``swing_length`` 根右側 lookahead，故 ``batch(df[:i+1]).iloc[i]`` 與
    ``batch(df).iloc[i]`` 在 swing 未確認的尾段位置必然不同。invariant 4
    明文只要求 ``batch(df).iloc[-1] == incremental(batch(df[:-1]).state, df.iloc[-1])``，
    本測試對每個 step 驗證該等式。
    """
    p = SMCFeatureParams()
    n = len(fixture_df)
    start_replay = max(2, n - 50)
    prefix = fixture_df.iloc[:start_replay]
    state = batch_compute(prefix, p, include_aux=False).state

    for i in range(start_replay, n):
        new_bar = fixture_df.iloc[i]
        feature_row, state = incremental_compute(state, new_bar)
        # 對應 batch 末列：batch(df[:i+1]).iloc[-1]
        prefix_up_to_i = fixture_df.iloc[: i + 1]
        batch_last = batch_compute(prefix_up_to_i, p, include_aux=False).output.iloc[-1]
        _row_equal(batch_last, feature_row)


def test_single_step_after_full_batch(fixture_df: pd.DataFrame):
    """spec FR-008 文字版：batch(df).iloc[-1] == incremental(batch(df[:-1]).state, df.iloc[-1])。"""
    p = SMCFeatureParams()
    full_br = batch_compute(fixture_df, p, include_aux=False)
    prefix_br = batch_compute(fixture_df.iloc[:-1], p, include_aux=False)
    last_bar = fixture_df.iloc[-1]
    feature_row, _ = incremental_compute(prefix_br.state, last_bar)
    _row_equal(full_br.output.iloc[-1], feature_row)


# ---------------------------------------------------------------------------
# T045 — parametrized seed equivalence (spec 008 contracts/incremental I-1~I-3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [0, 1, 2, 42, 1337])
def test_batch_incremental_equivalence_random_seeds(seed: int, make_random_ohlcv):
    """parametrize seed=[0,1,2,42,1337]、n=1000 隨機 OHLCV → 用
    ``make_random_ohlcv`` fixture 產 random-walk，驗證
    「先 batch n-1 + incremental 1 根」與「一次 batch n 根」最後 FeatureRow
    完全相等。

    對應 contracts/incremental.contract.md Invariant I-1 ~ I-3、tasks T045。
    """
    n = 1000
    bars = make_random_ohlcv(seed=seed, n=n)
    df = pd.DataFrame(
        {
            "open": bars["opens"],
            "high": bars["highs"],
            "low": bars["lows"],
            "close": bars["closes"],
            "volume": np.zeros(n, dtype=np.float64),
        },
        index=pd.DatetimeIndex(bars["timestamps"], name="date"),
    )

    p = SMCFeatureParams()
    full_br = batch_compute(df, p, include_aux=False)
    prefix_br = batch_compute(df.iloc[:-1], p, include_aux=False)
    last_bar = df.iloc[-1]
    feature_row, _ = incremental_compute(prefix_br.state, last_bar)
    _row_equal(full_br.output.iloc[-1], feature_row)
