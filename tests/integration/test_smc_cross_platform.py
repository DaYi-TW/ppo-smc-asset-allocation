"""T056 — SMC features 跨平台 byte-identical（spec SC-002）。

`tests/fixtures/expected_smc_features.parquet` 是在 Linux dev container（pandas
2.2.x / pyarrow 15.x、固定 SMCFeatureParams 預設）對 ``nvda_2024H1.parquet``
跑 ``batch_compute(include_aux=True)`` 產出並 commit 的。本測試在當前平台：

  1. 載入同一份輸入 fixture；
  2. 跑 ``batch_compute`` 取得「當前平台輸出」；
  3. 與 commit 進 repo 的 expected fixture 用 ``np.allclose(atol=1e-9)``
     比對 float 欄位、用 ``==`` 比對 int8/bool/timestamp 欄位。

通過代表 lock file 鎖定的 numerical stack 確實能在三個平台產出位元組相同
的 SMC features（spec SC-002 跨平台 ≤ 1e-9 誤差）。

若刻意升級 numerical stack（e.g. pandas 2.3）：

  python scripts/build_smc_expected_features.py

重新產生 expected fixture 並 commit。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from smc_features import SMCFeatureParams, batch_compute

_INPUT_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "nvda_2024H1.parquet"
_EXPECTED_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "expected_smc_features.parquet"
)

_FLOAT_COLS = (
    "fvg_distance_pct",
    "ob_distance_ratio",
    "fvg_top_active",
    "fvg_bottom_active",
    "ob_top_active",
    "ob_bottom_active",
)
_INT_COLS = ("bos_signal", "choch_signal")
_BOOL_COLS = ("ob_touched", "swing_high_marker", "swing_low_marker")


@pytest.fixture
def input_df() -> pd.DataFrame:
    if not _INPUT_FIXTURE.exists():
        pytest.skip(f"input fixture missing: {_INPUT_FIXTURE}")
    return pd.read_parquet(_INPUT_FIXTURE)


def test_expected_fixture_exists() -> None:
    if not _EXPECTED_FIXTURE.exists():
        pytest.skip(
            f"expected fixture missing: {_EXPECTED_FIXTURE}. "
            "Run scripts/build_smc_expected_features.py to regenerate."
        )


def test_smc_features_byte_identical_across_platforms(input_df: pd.DataFrame) -> None:
    """SC-002：``batch_compute`` 在 lock file 鎖定的 numerical stack 下，
    對相同 fixture 應產出與 expected_features.parquet 相同的特徵欄位
    （float 欄 atol=1e-9，int/bool/timestamp 嚴格相等）。
    """
    if not _EXPECTED_FIXTURE.exists():
        pytest.skip(f"expected fixture missing: {_EXPECTED_FIXTURE}")

    expected = pd.read_parquet(_EXPECTED_FIXTURE)
    out = batch_compute(input_df, SMCFeatureParams(), include_aux=True).output

    # index 完全一致
    pd.testing.assert_index_equal(out.index, expected.index)

    # int 欄位嚴格相等（NaN 對應）
    for col in _INT_COLS:
        if col not in expected.columns:
            continue
        a = out[col]
        b = expected[col]
        # Int8 nullable — 比對 mask 與整數值
        a_mask = a.isna()
        b_mask = b.isna()
        assert (a_mask == b_mask).all(), f"{col}: NaN 位置不一致"
        valid = ~a_mask
        assert (a[valid].astype("int64") == b[valid].astype("int64")).all(), (
            f"{col} integer values diverge across platforms"
        )

    # bool 欄位嚴格相等（NaN 對應）
    for col in _BOOL_COLS:
        if col not in expected.columns:
            continue
        a = out[col]
        b = expected[col]
        a_mask = a.isna()
        b_mask = b.isna()
        assert (a_mask == b_mask).all(), f"{col}: NaN 位置不一致"
        valid = ~a_mask
        assert (a[valid].astype("bool") == b[valid].astype("bool")).all(), (
            f"{col} bool values diverge across platforms"
        )

    # float 欄位 atol=1e-9（NaN 對應）
    for col in _FLOAT_COLS:
        if col not in expected.columns:
            continue
        a = out[col].to_numpy(dtype=np.float64)
        b = expected[col].to_numpy(dtype=np.float64)
        a_nan = np.isnan(a)
        b_nan = np.isnan(b)
        assert np.array_equal(a_nan, b_nan), f"{col}: NaN 位置不一致"
        valid = ~a_nan
        assert np.allclose(a[valid], b[valid], atol=1e-9, rtol=0), (
            f"{col} float values diverge beyond atol=1e-9 across platforms; "
            f"max diff = {np.max(np.abs(a[valid] - b[valid])) if valid.any() else 0}"
        )
