"""Tests for ``scripts.build_episode_artifact``（feature 009 / T020-T024）。

對齊 spec FR-006~011、tasks T020~T024、data-model.md §13。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from scripts.build_episode_artifact import build_episode_artifact

from inference_service.episode_schemas import EpisodeDetail
from ppo_training.trajectory_writer import (
    ASSET_NAMES_DEFAULT,
    TrajectoryRecord,
    write_trajectory_parquet,
)

# 與 002 conftest._PARQUET_WRITER_KWARGS 對齊（research R5）。
_OHLC_WRITER_KWARGS = dict(
    compression="snappy",
    version="2.6",
    data_page_version="2.0",
    write_statistics=False,
    use_dictionary=False,
    coerce_timestamps="us",
)


def _make_ohlc_df(seed: int, dates: pd.DatetimeIndex, base: float = 100.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = len(dates)
    closes = base + np.cumsum(rng.standard_normal(n)) * 0.5
    opens = closes + rng.standard_normal(n) * 0.05
    highs = np.maximum(opens, closes) + np.abs(rng.standard_normal(n)) * 0.2
    lows = np.minimum(opens, closes) - np.abs(rng.standard_normal(n)) * 0.2
    volumes = (1_000_000 + rng.integers(0, 100_000, size=n)).astype("int64")
    df = pd.DataFrame(
        {
            "open": opens.astype(np.float64),
            "high": highs.astype(np.float64),
            "low": lows.astype(np.float64),
            "close": closes.astype(np.float64),
            "volume": volumes,
            "quality_flag": pd.array(["ok"] * n, dtype="string"),
        },
        index=pd.DatetimeIndex(dates, name="timestamp"),
    )
    return df


def _write_ohlc_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=True)
    pq.write_table(table, path, **_OHLC_WRITER_KWARGS)


def _make_record(date: str, step: int, nav: float) -> TrajectoryRecord:
    return TrajectoryRecord(
        date=date,
        step=step,
        nav=nav,
        log_return=0.001 if step > 0 else 0.0,
        weights=[0.1, 0.1, 0.1, 0.1, 0.2, 0.2, 0.2],
        reward_total=0.0008 if step > 0 else 0.0,
        reward_return=0.001 if step > 0 else 0.0,
        reward_drawdown_penalty=0.0001 if step > 0 else 0.0,
        reward_cost_penalty=0.0001 if step > 0 else 0.0,
        action_raw=[0.0] * 7,
        action_normalized=[1.0 / 7] * 7,
        action_log_prob=-1.5 if step > 0 else 0.0,
        action_entropy=1.9 if step > 0 else 0.0,
        smc_bos=0,
        smc_choch=0,
        smc_fvg_distance_pct=0.012,
        smc_ob_touching=False,
        smc_ob_distance_ratio=2.5,
        closes=[150.0, 100.0, 90.0, 80.0, 200.0, 110.0],
    )


@pytest.fixture
def mini_run(tmp_path: Path) -> dict:
    """建立 10 frames × 6 assets 的 mini run 目錄結構。"""
    n_steps = 10
    dates = pd.date_range("2025-01-02", periods=n_steps, freq="B")  # business days
    date_strs = [d.strftime("%Y-%m-%d") for d in dates]

    # 1. trajectory.parquet
    records = [
        _make_record(date_strs[i], step=i, nav=1.0 + 0.001 * i) for i in range(n_steps)
    ]
    run_dir = tmp_path / "runs" / "test_run" / "eval_oos"
    run_dir.mkdir(parents=True, exist_ok=True)
    write_trajectory_parquet(records, run_dir / "trajectory.parquet")

    # 2. eval_summary.json
    summary = {
        "policy_path": "runs/test_run/final_policy.zip",
        "data_root": "data/raw",
        "include_smc": True,
        "deterministic": True,
        "seed": 42,
        "n_steps": n_steps - 1,  # transitions = frames - 1
        "start_date": date_strs[0],
        "end_date": date_strs[-1],
        "initial_nav": 1.0,
        "final_nav": records[-1].nav,
        "cumulative_return_pct": (records[-1].nav - 1.0) * 100,
        "annualized_return_pct": 5.0,
        "max_drawdown_pct": 0.5,
        "sharpe_ratio": 1.2,
        "sortino_ratio": 1.5,
    }
    (run_dir / "eval_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    # 3. data/raw/<asset>_daily_*.parquet（6 assets）
    data_root = tmp_path / "data" / "raw"
    extended = pd.date_range(
        dates[0] - pd.Timedelta(days=120), dates[-1] + pd.Timedelta(days=10), freq="B"
    )
    for i, asset in enumerate(ASSET_NAMES_DEFAULT):
        df = _make_ohlc_df(seed=100 + i, dates=extended, base=100.0 + 10 * i)
        _write_ohlc_parquet(df, data_root / f"{asset.lower()}_daily_test.parquet")

    return {
        "run_dir": run_dir,
        "data_root": data_root,
        "summary": summary,
        "n_frames": n_steps,
    }


class TestBuildEpisodeArtifactBasic:
    def test_writes_episode_detail_json(self, mini_run: dict, tmp_path: Path) -> None:
        out = build_episode_artifact(
            run_dir=mini_run["run_dir"],
            data_root=mini_run["data_root"],
            output_path=mini_run["run_dir"] / "episode_detail.json",
        )
        assert out.exists()
        payload = json.loads(out.read_text(encoding="utf-8"))
        # data + meta envelope
        assert set(payload.keys()) == {"data", "meta"}
        assert "summary" in payload["data"]
        assert "trajectoryInline" in payload["data"]
        assert "rewardBreakdown" in payload["data"]
        assert "smcOverlayByAsset" in payload["data"]

    def test_payload_validates_via_pydantic(self, mini_run: dict) -> None:
        out = build_episode_artifact(
            run_dir=mini_run["run_dir"],
            data_root=mini_run["data_root"],
            output_path=mini_run["run_dir"] / "episode_detail.json",
        )
        payload = json.loads(out.read_text(encoding="utf-8"))
        # data 區段必須 strict 過 EpisodeDetail
        EpisodeDetail.model_validate(payload["data"])

    def test_trajectory_inline_length_matches_frames(self, mini_run: dict) -> None:
        out = build_episode_artifact(
            run_dir=mini_run["run_dir"],
            data_root=mini_run["data_root"],
            output_path=mini_run["run_dir"] / "episode_detail.json",
        )
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert len(payload["data"]["trajectoryInline"]) == mini_run["n_frames"]
        assert len(payload["data"]["rewardBreakdown"]["byStep"]) == mini_run["n_frames"]
        assert (
            len(payload["data"]["rewardBreakdown"]["cumulative"])
            == mini_run["n_frames"]
        )

    def test_per_asset_ohlcv_in_each_frame(self, mini_run: dict) -> None:
        out = build_episode_artifact(
            run_dir=mini_run["run_dir"],
            data_root=mini_run["data_root"],
            output_path=mini_run["run_dir"] / "episode_detail.json",
        )
        payload = json.loads(out.read_text(encoding="utf-8"))
        for frame in payload["data"]["trajectoryInline"]:
            assert set(frame["ohlcvByAsset"].keys()) == set(ASSET_NAMES_DEFAULT)
            for _asset, ohlcv in frame["ohlcvByAsset"].items():
                assert {"open", "high", "low", "close", "volume"} <= set(ohlcv.keys())
                assert ohlcv["high"] >= ohlcv["low"]

    def test_weight_sum_close_to_one(self, mini_run: dict) -> None:
        out = build_episode_artifact(
            run_dir=mini_run["run_dir"],
            data_root=mini_run["data_root"],
            output_path=mini_run["run_dir"] / "episode_detail.json",
        )
        payload = json.loads(out.read_text(encoding="utf-8"))
        for frame in payload["data"]["trajectoryInline"]:
            w = frame["weights"]
            total = (
                w["riskOn"]
                + w["riskOff"]
                + w["cash"]
            )
            assert abs(total - 1.0) < 1e-6

    def test_reward_cumulative_invariant(self, mini_run: dict) -> None:
        out = build_episode_artifact(
            run_dir=mini_run["run_dir"],
            data_root=mini_run["data_root"],
            output_path=mini_run["run_dir"] / "episode_detail.json",
        )
        payload = json.loads(out.read_text(encoding="utf-8"))
        by_step = payload["data"]["rewardBreakdown"]["byStep"]
        cumulative = payload["data"]["rewardBreakdown"]["cumulative"]
        # cumulativeTotal 應是 byStep.total 的累積（含 step=0 frame，total=0 起算）
        running = 0.0
        for i, cum in enumerate(cumulative):
            running += by_step[i]["total"]
            assert abs(cum["cumulativeTotal"] - running) < 1e-9
