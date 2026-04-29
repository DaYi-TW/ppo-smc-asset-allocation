"""SC-007 byte-determinism：相同 DataFrame 兩次 write_parquet 必須 byte-identical。

研究決策（research.md R4）trade-off：
- pandas-injected schema metadata（含 ``pandas_version`` / ``pyarrow.creator.version``
  字串）會嵌入檔案 → 嚴格意義的「跨 pyarrow 版本 byte-identical」不可達。
- 但保留這段 metadata 才能在 read_parquet 後正確還原 ``string`` extension dtype
  （loader 對 ``quality_flag`` 的 dtype 契約所需）。
- 最終 SC-007 「同 commit + 同 lock file → byte-identical」由 ``poetry.lock`` /
  ``uv.lock`` 釘住 pyarrow 與 pandas 的 patch 版本來保證；兩次相同版本下寫出的
  metadata 是字面一致的，因此 ``test_two_writes_produce_byte_identical_files``
  仍會通過。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from data_ingestion.writer import write_parquet


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    idx = pd.date_range("2024-01-02", periods=20, freq="B", name="date")
    rs = np.random.default_rng(seed=7)
    close = 100.0 + np.cumsum(rs.normal(0, 1.0, size=len(idx)))
    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.5,
            "close": close,
            "volume": rs.integers(1_000_000, 10_000_000, size=len(idx)).astype("int64"),
            "quality_flag": pd.array(["ok"] * len(idx), dtype="string"),
        },
        index=idx,
    )


def test_two_writes_produce_byte_identical_files(sample_ohlcv: pd.DataFrame, tmp_path: Path):
    a = tmp_path / "a.parquet"
    b = tmp_path / "b.parquet"
    write_parquet(sample_ohlcv, a)
    write_parquet(sample_ohlcv, b)
    assert _sha(a) == _sha(b)
    assert a.stat().st_size == b.stat().st_size


def test_same_version_writes_have_identical_schema_metadata(
    sample_ohlcv: pd.DataFrame, tmp_path: Path
):
    """同一 pandas/pyarrow 版本下，schema metadata 必須字面一致。

    這是 SC-007 同-lock-file byte-identical 的必要條件：
    若 schema metadata 在兩次 write 之間有差異（例如插入時間戳或亂數 ID），
    上一個 byte-identical 測試也會失敗。此測試聚焦 metadata layer，
    若上層 sha256 比對失敗，這裡能立即點出 root cause。
    """
    a = tmp_path / "a.parquet"
    b = tmp_path / "b.parquet"
    write_parquet(sample_ohlcv, a)
    write_parquet(sample_ohlcv, b)
    schema_a = pq.read_schema(a)
    schema_b = pq.read_schema(b)
    assert schema_a.metadata == schema_b.metadata
    # pandas key 必定存在（這是 string dtype roundtrip 的依賴）
    assert schema_a.metadata is not None
    assert b"pandas" in schema_a.metadata


def test_writer_roundtrip_preserves_dtypes(sample_ohlcv: pd.DataFrame, tmp_path: Path):
    p = tmp_path / "roundtrip.parquet"
    write_parquet(sample_ohlcv, p)
    back = pd.read_parquet(p)
    for col in ("open", "high", "low", "close"):
        assert str(back[col].dtype) == "float64"
    assert str(back["volume"].dtype) == "int64"
    assert str(back["quality_flag"].dtype) == "string"
    assert back.index.name == "date"
    assert isinstance(back.index, pd.DatetimeIndex)
    assert back.index.tz is None
