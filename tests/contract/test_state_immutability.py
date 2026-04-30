"""T043 — SMCEngineState frozen 行為與 incremental 不就地修改 prior_state。"""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from smc_features import (
    SMCEngineState,
    SMCFeatureParams,
    batch_compute,
    incremental_compute,
)


def _toy_df(n: int = 30) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    base = [100.0 + i * 0.5 for i in range(n)]
    return pd.DataFrame(
        {
            "open": base,
            "high": [b + 1.0 for b in base],
            "low": [b - 1.0 for b in base],
            "close": [b + 0.2 for b in base],
            "volume": [1_000_000] * n,
            "quality_flag": ["ok"] * n,
        },
        index=idx,
    )


def test_state_is_frozen_dataclass() -> None:
    p = SMCFeatureParams()
    state = SMCEngineState.initial(p)
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.bar_count = 99  # type: ignore[misc]


def test_incremental_does_not_mutate_prior_state() -> None:
    df = _toy_df()
    p = SMCFeatureParams()
    prior = batch_compute(df, p).state
    snapshot_window = prior.window_bars
    snapshot_atr_buf = prior.atr_buffer
    snapshot_open_fvgs = prior.open_fvgs
    snapshot_active_obs = prior.active_obs
    snapshot_bar_count = prior.bar_count

    new_bar = pd.Series(
        {
            "open": 200.0,
            "high": 201.0,
            "low": 199.0,
            "close": 200.5,
            "volume": 999_000,
            "quality_flag": "ok",
        },
        name=df.index[-1] + pd.Timedelta(days=1),
    )
    _, new_state = incremental_compute(prior, new_bar)

    # prior 各欄位應與 snapshot 完全一致（tuple 是 hashable，可直接 ==）
    assert prior.window_bars == snapshot_window
    assert prior.atr_buffer == snapshot_atr_buf
    assert prior.open_fvgs == snapshot_open_fvgs
    assert prior.active_obs == snapshot_active_obs
    assert prior.bar_count == snapshot_bar_count
    # new_state 應為新 instance
    assert new_state is not prior
    assert new_state.bar_count == prior.bar_count + 1
