"""SC-007 — 跨平台 byte-identical 驗證。

`tests/fixtures/golden_snapshots/` 下的 reference Parquet + metadata 是在 Linux
dev container（pandas 2.2.x / pyarrow 15.x）產生並 commit 進 repo 的。本測試
在當前平台（CI 矩陣涵蓋 Linux / macOS / Windows）：

  1. 重算 Parquet 的 SHA-256 並比對 metadata 中的 ``sha256``；
  2. 走完整的 ``verify_snapshot`` 流程確認 row_count / schema 全部 match。

通過代表 lock file 鎖定的 pandas / pyarrow patch 版本確實能在三個平台產出
位元組相同的 Parquet（憲法 Principle I + spec SC-007）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from data_ingestion import verify_snapshot
from data_ingestion.hashing import sha256_of_file

# 由 scripts/build_golden_snapshot.py 在 dev container 產出後 commit 進 repo。
# 若刻意更新 fixture（schema 變更或 lock 升級），要同步調整下面的 expected hash。
_GOLDEN_PARQUET = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "golden_snapshots"
    / "golden_daily_20240102_20240131.parquet"
)
_EXPECTED_SHA256 = "ce80d87558e5ed6bc40f7885687233f193d33584c633b10e2e6290a85dcd6634"
_EXPECTED_ROWS = 22


def test_golden_fixture_exists():
    assert _GOLDEN_PARQUET.is_file(), (
        f"Missing golden fixture: {_GOLDEN_PARQUET}. "
        "Run `python scripts/build_golden_snapshot.py` to regenerate."
    )
    meta_path = _GOLDEN_PARQUET.with_suffix(_GOLDEN_PARQUET.suffix + ".meta.json")
    assert meta_path.is_file()


def test_golden_fixture_byte_identical_across_platforms():
    """SC-007: 重算 SHA-256 必須等於 fixture commit 時的值。"""
    actual = sha256_of_file(_GOLDEN_PARQUET)
    assert actual == _EXPECTED_SHA256, (
        f"Cross-platform SHA-256 mismatch on {_GOLDEN_PARQUET.name}.\n"
        f"  Expected: {_EXPECTED_SHA256}\n"
        f"  Actual:   {actual}\n"
        "This indicates pandas / pyarrow produced different bytes on this "
        "platform. Check requirements-lock.txt patch versions match the "
        "container that generated the fixture."
    )


def test_golden_fixture_passes_verify_snapshot():
    """走完整的 verify 流程：sha256 + row_count + schema 全部 match。"""
    result = verify_snapshot(_GOLDEN_PARQUET)
    assert result.ok, f"verify_snapshot failed: {result.message}"
    assert result.row_count_match
    assert result.schema_match
    assert result.sha256_match
    assert result.expected_sha256 == _EXPECTED_SHA256


def test_golden_fixture_row_count():
    result = verify_snapshot(_GOLDEN_PARQUET)
    # row_count_match 已隱含此斷言；單獨列出讓 regression 訊息更清楚
    import pyarrow.parquet as pq

    actual = pq.read_metadata(_GOLDEN_PARQUET).num_rows
    assert actual == _EXPECTED_ROWS, (
        f"Golden fixture row count drift: expected {_EXPECTED_ROWS}, got {actual}"
    )
    assert result.ok


def test_golden_fixture_under_size_cap():
    """fixture 必須遠小於 1 MB（tasks.md T049 限制）。"""
    parquet_size = _GOLDEN_PARQUET.stat().st_size
    meta_size = _GOLDEN_PARQUET.with_suffix(
        _GOLDEN_PARQUET.suffix + ".meta.json"
    ).stat().st_size
    total = parquet_size + meta_size
    assert total < 1024 * 1024, (
        f"Golden fixture grew to {total:,} bytes; T049 specifies ≪ 1 MB"
    )


@pytest.mark.parametrize(
    "expected_col,expected_dtype",
    [
        ("open", "float64"),
        ("high", "float64"),
        ("low", "float64"),
        ("close", "float64"),
        ("volume", "int64"),
        ("quality_flag", "string"),
    ],
)
def test_golden_fixture_schema_columns(expected_col: str, expected_dtype: str):
    """逐欄驗證 metadata.column_schema — 防止 schema drift。"""
    from data_ingestion import load_metadata

    meta = load_metadata(_GOLDEN_PARQUET)
    by_name = {c.name: c.dtype for c in meta.column_schema}
    assert expected_col in by_name, f"missing column {expected_col!r}"
    assert by_name[expected_col] == expected_dtype
