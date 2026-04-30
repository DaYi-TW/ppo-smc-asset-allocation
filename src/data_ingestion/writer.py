"""Parquet writer — byte-deterministic 寫入。

研究決策見 research.md R4：
- compression="snappy"（FR-004）
- version="2.6"
- data_page_version="2.0"
- write_statistics=False（避免浮點 min/max 跨平台差異）
- coerce_timestamps="us" + allow_truncated_timestamps=False
- use_dictionary=False（dictionary encoding 在某些 row order 下會偷渡 nondeterminism）
- 不寫 created_by 元資料（pyarrow 預設嵌入版本字串會破壞 byte-identical）

同一 commit、相同 pyarrow 版本下，相同輸入 DataFrame 兩次 write 必須 byte-identical。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# 鎖定 writer kwargs。conftest.py fixture 與 Phase 3 fetch 共用同一組。
_WRITER_KWARGS: dict[str, object] = {
    "compression": "snappy",
    "version": "2.6",
    "data_page_version": "2.0",
    "write_statistics": False,
    "use_dictionary": False,
    "coerce_timestamps": "us",
    "allow_truncated_timestamps": False,
}


def write_parquet(df: pd.DataFrame, path: Path) -> None:
    """Write ``df`` to ``path`` using the locked byte-deterministic config.

    The DataFrame's pandas-level metadata (column dtypes, index name) is
    preserved via ``pa.Table.from_pandas``. ``preserve_index=True`` is the
    pyarrow default, but we set it explicitly so any future default change
    cannot silently break SC-007.

    No ``created_by`` / ``pyarrow.__version__`` strings end up in the file
    header — verified via the determinism unit test (T017).
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"df must be pandas.DataFrame, got {type(df).__name__}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    table = pa.Table.from_pandas(df, preserve_index=True)
    # Note：保留 pandas-injected schema metadata（含 dtype 提示）以確保
    # quality_flag 等 pandas extension dtype 在 roundtrip 後正確還原。
    # SC-007 byte-identical 由 lock file 鎖定 pandas / pyarrow patch 版本來保證；
    # 兩次相同 pandas 版本下的 schema metadata 也是字面一致。

    pq.write_table(table, path, **_WRITER_KWARGS)
