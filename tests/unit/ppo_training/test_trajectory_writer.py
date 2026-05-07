"""Tests for ``ppo_training.trajectory_writer``（feature 009 / T010-T011）。

對應 spec FR-001~005、tasks.md T010 / T011。
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from ppo_training.trajectory_writer import (
    ASSET_NAMES_DEFAULT,
    TrajectoryRecord,
    write_trajectory_csv,
    write_trajectory_parquet,
)


def _make_record(
    *,
    step: int,
    nav: float = 1.0,
    log_return: float = 0.0,
    reward_total: float = 0.0,
    reward_return: float = 0.0,
    reward_drawdown_penalty: float = 0.0,
    reward_cost_penalty: float = 0.0,
) -> TrajectoryRecord:
    return TrajectoryRecord(
        date=f"2025-01-{(step % 28) + 1:02d}",
        step=step,
        nav=nav,
        log_return=log_return,
        weights=[0.1, 0.1, 0.1, 0.1, 0.2, 0.2, 0.2],
        reward_total=reward_total,
        reward_return=reward_return,
        reward_drawdown_penalty=reward_drawdown_penalty,
        reward_cost_penalty=reward_cost_penalty,
        action_raw=[0.05, -0.02, 0.1, -0.1, 0.2, -0.05, 0.0],
        action_normalized=[0.1, 0.1, 0.1, 0.1, 0.2, 0.2, 0.2],
        action_log_prob=-1.234,
        action_entropy=1.946,
        smc_bos=0,
        smc_choch=1,
        smc_fvg_distance_pct=0.012,
        smc_ob_touching=False,
        smc_ob_distance_ratio=2.5,
        closes=[150.0, 100.0, 90.0, 80.0, 200.0, 110.0],
    )


class TestParquetWriter:
    def test_writes_parquet_with_full_schema(self, tmp_path: Path) -> None:
        records = [
            _make_record(step=i, nav=1.0 + 0.001 * i, log_return=0.001 * i if i > 0 else 0.0)
            for i in range(5)
        ]
        out = write_trajectory_parquet(records, tmp_path / "trajectory.parquet")
        assert out.exists()

        df = pd.read_parquet(out)
        # 長度 == 5 frames
        assert len(df) == 5

        expected_cols = {
            "date",
            "step",
            "nav",
            "log_return",
            "reward_total",
            "reward_return",
            "reward_drawdown_penalty",
            "reward_cost_penalty",
            "action_log_prob",
            "action_entropy",
            "smc_bos",
            "smc_choch",
            "smc_fvg_distance_pct",
            "smc_ob_touching",
            "smc_ob_distance_ratio",
        }
        # 7 weight cols + 7 raw + 7 normalized + 6 close
        for name in (*ASSET_NAMES_DEFAULT, "CASH"):
            expected_cols.add(f"weight_{name}")
        for i in range(7):
            expected_cols.add(f"action_raw_{i}")
            expected_cols.add(f"action_normalized_{i}")
        for name in ASSET_NAMES_DEFAULT:
            expected_cols.add(f"close_{name}")

        assert expected_cols.issubset(set(df.columns)), f"missing: {expected_cols - set(df.columns)}"

    def test_reward_invariant_holds(self, tmp_path: Path) -> None:
        # total ≈ return - drawdown - cost (1e-9)
        records = [
            _make_record(
                step=i,
                reward_return=0.005,
                reward_drawdown_penalty=0.001,
                reward_cost_penalty=0.0005,
                reward_total=0.005 - 0.001 - 0.0005,
            )
            for i in range(3)
        ]
        out = write_trajectory_parquet(records, tmp_path / "t.parquet")
        df = pd.read_parquet(out)
        residual = (
            df["reward_total"]
            - df["reward_return"]
            + df["reward_drawdown_penalty"]
            + df["reward_cost_penalty"]
        )
        assert residual.abs().max() < 1e-9

    def test_empty_records_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="empty"):
            write_trajectory_parquet([], tmp_path / "t.parquet")


class TestCsvWriter:
    def test_legacy_csv_has_16_cols(self, tmp_path: Path) -> None:
        records = [_make_record(step=i) for i in range(3)]
        out = write_trajectory_csv(records, tmp_path / "trajectory.csv")
        assert out.exists()

        with out.open("r", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            header = next(reader)

        expected = [
            "date",
            "nav",
            "log_return",
            "w_NVDA",
            "w_AMD",
            "w_TSM",
            "w_MU",
            "w_GLD",
            "w_TLT",
            "w_CASH",
            "close_NVDA",
            "close_AMD",
            "close_TSM",
            "close_MU",
            "close_GLD",
            "close_TLT",
        ]
        assert header == expected
        # FR-005 16 columns exact

    def test_csv_no_reward_or_action_cols(self, tmp_path: Path) -> None:
        # legacy CSV 不能洩漏新欄位（向後相容）
        records = [_make_record(step=i) for i in range(2)]
        out = write_trajectory_csv(records, tmp_path / "t.csv")
        text = out.read_text(encoding="utf-8")
        assert "reward_total" not in text
        assert "action_raw" not in text
        assert "smc_bos" not in text

    def test_csv_round_trip_via_pandas(self, tmp_path: Path) -> None:
        records = [_make_record(step=i, nav=1.0 + 0.01 * i) for i in range(3)]
        out = write_trajectory_csv(records, tmp_path / "t.csv")
        df = pd.read_csv(out)
        assert df.shape == (3, 16)
        assert df["nav"].iloc[0] == pytest.approx(1.0)
        assert df["nav"].iloc[2] == pytest.approx(1.02)
