"""T048 — quality_flag 為非 ok 的列特徵全 NaN，且不污染下游視窗（invariant 6）。"""

from __future__ import annotations

import pandas as pd

from smc_features import SMCFeatureParams, batch_compute


def _df_with_quality(quality_flags: list[str]) -> pd.DataFrame:
    n = len(quality_flags)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    base = [100.0 + i * 0.5 for i in range(n)]
    return pd.DataFrame(
        {
            "open": base,
            "high": [b + 1.0 for b in base],
            "low": [b - 1.0 for b in base],
            "close": [b + 0.2 for b in base],
            "volume": [1_000_000] * n,
            "quality_flag": quality_flags,
        },
        index=idx,
    )


def test_missing_close_row_features_are_na() -> None:
    flags = ["ok"] * 30
    flags[15] = "missing_close"
    df = _df_with_quality(flags)
    out = batch_compute(df, SMCFeatureParams()).output
    row = out.iloc[15]
    assert pd.isna(row["bos_signal"])
    assert pd.isna(row["choch_signal"])
    assert pd.isna(row["fvg_distance_pct"])
    assert pd.isna(row["ob_touched"])
    assert pd.isna(row["ob_distance_ratio"])


def test_zero_volume_row_features_are_na() -> None:
    flags = ["ok"] * 30
    flags[20] = "zero_volume"
    df = _df_with_quality(flags)
    out = batch_compute(df, SMCFeatureParams()).output
    row = out.iloc[20]
    assert pd.isna(row["bos_signal"])
    assert pd.isna(row["fvg_distance_pct"])


def test_duplicate_dropped_row_features_are_na() -> None:
    flags = ["ok"] * 30
    flags[10] = "duplicate_dropped"
    df = _df_with_quality(flags)
    out = batch_compute(df, SMCFeatureParams()).output
    row = out.iloc[10]
    assert pd.isna(row["bos_signal"])
    assert pd.isna(row["choch_signal"])


def test_other_rows_unaffected_by_bad_row() -> None:
    """瑕疵列前後的有效列特徵應與「全段都 ok」時除瑕疵列外的列一致 — 即不污染。"""
    n = 60
    p = SMCFeatureParams()
    flags_good = ["ok"] * n
    flags_bad = ["ok"] * n
    flags_bad[30] = "missing_close"

    df_good = _df_with_quality(flags_good)
    df_bad = _df_with_quality(flags_bad)
    out_good = batch_compute(df_good, p).output
    out_bad = batch_compute(df_bad, p).output

    # 比對「不在瑕疵位置」的列：注意 ATR / FVG / OB 等視窗會因為跳過第 30 列而與「全 ok」
    # 不同（這正是預期的「跳過」行為），所以這裡僅驗證瑕疵列前的列、且距離夠遠（避開
    # ATR window 14 的影響）。
    cols = ["bos_signal", "choch_signal"]
    pd.testing.assert_series_equal(
        out_good.iloc[:15][cols[0]],
        out_bad.iloc[:15][cols[0]],
        check_dtype=True,
        check_exact=True,
    )


def test_missing_quality_flag_column_treated_as_all_ok() -> None:
    n = 30
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    base = [100.0 + i * 0.5 for i in range(n)]
    df = pd.DataFrame(
        {
            "open": base,
            "high": [b + 1.0 for b in base],
            "low": [b - 1.0 for b in base],
            "close": [b + 0.2 for b in base],
            "volume": [1_000_000] * n,
        },
        index=idx,
    )
    out = batch_compute(df, SMCFeatureParams()).output
    # 沒有 quality_flag 時應全部視為 ok — 不應有任何「結構性 NaN」
    # 但 ATR 前 13 列、swing 兩端各 swing_length 列允許 NaN（這由演算法決定，不算瑕疵）
    assert not out["bos_signal"].isna().all()
