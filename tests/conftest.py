"""共用測試 fixture：在 tmp_path 中組出最小但合規的 parquet + metadata 對。

Phase 6（loader）測試在尚未有真實 data/raw/ 快照前先用這些 fixture 跑通；Phase 3
fetch 落地後同一組 fixture 仍可直接搭配 Phase 4 verify 使用，不必重寫。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

# 鎖定 pyarrow writer 參數 — 與 research R5 / SC-007 一致；fixture 必須與 Phase 3
# 真正寫入時參數一致，否則 verify 會誤判 byte 不一致。
# coerce_timestamps 只接受 'ms' / 'us'；ns 留作 pandas 端 dtype，寫入 parquet 時
# 統一降為 us 以保 SC-007 跨平台一致性（pandas 讀回後仍會升回 ns）。
_PARQUET_WRITER_KWARGS = dict(
    compression="snappy",
    version="2.6",
    data_page_version="2.0",
    write_statistics=False,
    use_dictionary=False,
    coerce_timestamps="us",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_parquet_with_meta(
    df: pd.DataFrame,
    parquet_path: Path,
    *,
    data_source: str,
    call_params: dict,
    column_schema: list[dict],
    quality_summary: dict,
    duplicate_dropped_timestamps: list[str],
) -> None:
    """寫一份 fixture parquet 與其 metadata sidecar。"""
    table = pa.Table.from_pandas(df, preserve_index=True)
    pq.write_table(table, parquet_path, **_PARQUET_WRITER_KWARGS)

    sha = _sha256(parquet_path)
    metadata = {
        "schema_version": "1.0",
        "fetch_timestamp_utc": datetime(2026, 4, 29, 3, 14, 15, tzinfo=UTC)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_source": data_source,
        "data_source_call_params": call_params,
        "upstream_package_versions": {
            "yfinance": "0.2.43",
            "fredapi": "0.5.2",
            "pyarrow": pa.__version__,
            "pandas": pd.__version__,
        },
        "sha256": sha,
        "row_count": len(df),
        "column_schema": column_schema,
        "index_schema": {"name": "date", "dtype": "datetime64[ns]", "tz": None},
        "time_range": {
            "start": df.index.min().strftime("%Y-%m-%d"),
            "end": df.index.max().strftime("%Y-%m-%d"),
        },
        "quality_summary": quality_summary,
        "duplicate_dropped_timestamps": duplicate_dropped_timestamps,
    }
    meta_path = parquet_path.with_suffix(parquet_path.suffix + ".meta.json")
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def _make_nvda_df() -> pd.DataFrame:
    rng = pd.date_range("2024-01-02", periods=10, freq="B", name="date")
    rs = np.random.default_rng(seed=42)
    close = 100.0 + np.cumsum(rs.normal(0, 1.0, size=len(rng)))
    df = pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.5,
            "close": close,
            "volume": (rs.integers(1_000_000, 10_000_000, size=len(rng))).astype("int64"),
            "quality_flag": pd.array(["ok"] * len(rng), dtype="string"),
        },
        index=rng,
    )
    return df


def _make_dtb3_df() -> pd.DataFrame:
    rng = pd.date_range("2024-01-02", periods=10, freq="B", name="date")
    df = pd.DataFrame(
        {
            "rate_pct": np.linspace(5.20, 5.30, len(rng)),
            "quality_flag": pd.array(["ok"] * len(rng), dtype="string"),
        },
        index=rng,
    )
    return df


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Iterator[Path]:
    """提供含合規 NVDA OHLCV 與 DTB3 rate 快照的 data_dir。"""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()

    # NVDA OHLCV
    nvda = _make_nvda_df()
    _write_parquet_with_meta(
        nvda,
        data_dir / "nvda_daily_20240102_20240115.parquet",
        data_source="yfinance",
        call_params={
            "ticker": "NVDA",
            "start": "2024-01-02",
            "end": "2024-01-16",
            "auto_adjust": True,
            "interval": "1d",
        },
        column_schema=[
            {"name": "open", "dtype": "float64"},
            {"name": "high", "dtype": "float64"},
            {"name": "low", "dtype": "float64"},
            {"name": "close", "dtype": "float64"},
            {"name": "volume", "dtype": "int64"},
            {"name": "quality_flag", "dtype": "string"},
        ],
        quality_summary={
            "ok": len(nvda),
            "missing_close": 0,
            "zero_volume": 0,
            "missing_rate": 0,
            "duplicate_dropped": 0,
        },
        duplicate_dropped_timestamps=[],
    )

    # DTB3 rate
    dtb3 = _make_dtb3_df()
    _write_parquet_with_meta(
        dtb3,
        data_dir / "dtb3_daily_20240102_20240115.parquet",
        data_source="fred",
        call_params={
            "series_id": "DTB3",
            "observation_start": "2024-01-02",
            "observation_end": "2024-01-15",
        },
        column_schema=[
            {"name": "rate_pct", "dtype": "float64"},
            {"name": "quality_flag", "dtype": "string"},
        ],
        quality_summary={
            "ok": len(dtb3),
            "missing_close": 0,
            "zero_volume": 0,
            "missing_rate": 0,
            "duplicate_dropped": 0,
        },
        duplicate_dropped_timestamps=[],
    )

    yield data_dir


# ---------------------------------------------------------------------------
# Feature 001 (smc-feature-engine) shared fixtures
# ---------------------------------------------------------------------------
#
# 跨 user story 的小型 fixture：
# * ``default_params`` — 預設 ``SMCFeatureParams``。
# * ``small_ohlcv`` — ~125 列日線（單元 / 輕量 integration 用）。
# * ``sample_ohlcv`` — ~500 列兩年日線（性能基準與 SC-001 / SC-003 用）。
# * ``deterministic_atol`` — 1e-9，對應 spec SC-002 跨平台容差。
#
# parquet fixture 來源於 002 NVDA 快照子集（見 tests/fixtures/README.md）。檔案缺
# 失時 fixture 直接 ``pytest.skip``，避免在 CI / 新環境下產生噪音失敗，並提示重建
# 流程：``docker compose run --rm dev python scripts/build_smc_fixtures.py``。

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def default_params():
    """Phase 2 之後每個 001 測試的預設 ``SMCFeatureParams``。"""
    from smc_features.types import SMCFeatureParams

    return SMCFeatureParams()


def _load_smc_ohlcv(filename: str, expected_min_rows: int) -> pd.DataFrame:
    path = _FIXTURES_DIR / filename
    if not path.exists():
        pytest.skip(
            f"SMC OHLCV fixture 缺失：{path.name}。"
            "重建：`docker compose run --rm dev python scripts/build_smc_fixtures.py`"
        )
    df = pd.read_parquet(path)
    if len(df) < expected_min_rows:
        pytest.skip(
            f"SMC OHLCV fixture 列數 ({len(df)}) 小於預期最小值 {expected_min_rows}；"
            "請重新由 002 快照抽出。"
        )
    return df


@pytest.fixture
def small_ohlcv() -> pd.DataFrame:
    """~125 列 NVDA 2024H1 日線（單元測試用）。"""
    return _load_smc_ohlcv("nvda_2024H1.parquet", expected_min_rows=100)


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """~500 列 NVDA 兩年日線（SC-001 性能基準量級 / integration 用）。"""
    return _load_smc_ohlcv("nvda_2023_2024.parquet", expected_min_rows=400)


@pytest.fixture
def deterministic_atol() -> float:
    """跨平台浮點容差（spec SC-002）。"""
    return 1e-9
