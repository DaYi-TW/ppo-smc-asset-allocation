"""Unit tests：``data_loader.load_environment_data`` 內部行為（T015、research R5）。

* simple return 公式（``c_t/c_{t-1} - 1``，第 0 列為零）。
* FRED ``missing_rate`` forward fill。
* 股票 ``quality_flag != 'ok'`` 的日期不進入 ``trading_days``。
* ``rf_daily`` = ``(1 + rate_pct/100)^(1/252) - 1``。
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from portfolio_env.data_loader import _forward_fill_rate, load_environment_data


def test_returns_first_row_zero_and_simple_formula(portfolio_default_config):
    env_data = load_environment_data(portfolio_default_config)
    # 第 0 列 returns 必為零（episode 起始無前一日）
    np.testing.assert_array_equal(env_data.returns[0, :], np.zeros(6))
    # 第 1 列 = closes[1]/closes[0] - 1
    expected = env_data.closes[1, :] / env_data.closes[0, :] - 1.0
    np.testing.assert_allclose(env_data.returns[1, :], expected, atol=1e-12, rtol=0.0)


def test_rf_daily_formula(portfolio_default_config):
    env_data = load_environment_data(portfolio_default_config)
    # rf_daily 必為非負且不可能為 NaN
    assert np.all(np.isfinite(env_data.rf_daily))
    # rate_pct=2 → rf ≈ (1.02)^(1/252) - 1 ≈ 7.86e-5；至少要在合理範圍
    assert np.all(env_data.rf_daily < 0.01)
    assert np.all(env_data.rf_daily > -0.01)


def test_forward_fill_replaces_missing_rate():
    """``_forward_fill_rate`` 內部函式：missing_rate flag 行用前值取代。"""
    idx = pd.date_range("2024-01-02", periods=5, freq="B")
    df = pd.DataFrame(
        {
            "rate_pct": [5.0, 5.1, 99.99, 99.99, 5.4],
            "quality_flag": ["ok", "ok", "missing_rate", "missing_rate", "ok"],
        },
        index=idx,
    )
    out = _forward_fill_rate(df)
    np.testing.assert_array_equal(out["rate_pct"].to_numpy(), np.array([5.0, 5.1, 5.1, 5.1, 5.4]))


def test_data_hashes_includes_all_assets_plus_dtb3(portfolio_default_config):
    env_data = load_environment_data(portfolio_default_config)
    expected_keys = {"NVDA", "AMD", "TSM", "MU", "GLD", "TLT", "DTB3"}
    assert set(env_data.data_hashes) == expected_keys
    for v in env_data.data_hashes.values():
        assert len(v) == 64  # SHA-256 hex
        int(v, 16)  # 必須是合法 hex


def test_quality_flag_skip_excludes_day_from_trading_days(
    portfolio_default_config, tmp_portfolio_data_dir
):
    """把 NVDA 第 5 列 quality_flag 改成 ``missing_close`` → trading_days 應少一日。"""
    env_before = load_environment_data(portfolio_default_config)
    n_before = env_before.trading_days.size

    nvda_parquet = sorted(tmp_portfolio_data_dir.glob("nvda_daily_*.parquet"))[0]
    df = pq.read_table(nvda_parquet).to_pandas()
    target_idx = 5
    df.iloc[target_idx, df.columns.get_loc("quality_flag")] = "missing_close"
    skipped_date = pd.Timestamp(df.index[target_idx]).strftime("%Y-%m-%d")

    pq.write_table(
        pa.Table.from_pandas(df, preserve_index=True),
        nvda_parquet,
        compression="snappy",
    )

    # 重新計算 metadata SHA-256
    import hashlib

    meta_path = nvda_parquet.with_suffix(nvda_parquet.suffix + ".meta.json")
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    payload["sha256"] = hashlib.sha256(nvda_parquet.read_bytes()).hexdigest()
    meta_path.write_text(json.dumps(payload), encoding="utf-8")

    env_after = load_environment_data(portfolio_default_config)
    assert env_after.trading_days.size == n_before - 1
    assert skipped_date in env_after.skipped_dates_init


def test_smc_features_shape_when_enabled(portfolio_default_config):
    env_data = load_environment_data(portfolio_default_config)
    assert env_data.smc_features is not None
    n_steps = env_data.trading_days.size
    for ticker in ("NVDA", "AMD", "TSM", "MU", "GLD", "TLT"):
        arr = env_data.smc_features[ticker]
        assert arr.shape == (n_steps, 5)
        assert arr.dtype == np.float32


def test_smc_features_none_when_disabled(tmp_portfolio_data_dir):
    from portfolio_env import PortfolioEnvConfig

    cfg = PortfolioEnvConfig(data_root=tmp_portfolio_data_dir, include_smc=False)
    env_data = load_environment_data(cfg)
    assert env_data.smc_features is None
