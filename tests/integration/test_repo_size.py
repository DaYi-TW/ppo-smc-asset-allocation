"""Repo size budget — SC-005（< 10 MB）。

每次 commit 後 CI 透過 pytest 執行此檔，斷言 ``data/raw/`` 下所有 ``*.parquet``
與 ``*.parquet.meta.json`` 總位元組 < 10 MB。若 ``data/raw/`` 不存在或無快照
（feature 尚未跑 fetch），測試 skip — 不阻塞 CI；待 T055 提交真實資料後本檔會
變成「會擋下不慎變大的快照」的守衛。
"""

from __future__ import annotations

from pathlib import Path

import pytest

# 專案根目錄：從 tests/integration/ 上溯兩層
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_RAW = _REPO_ROOT / "data" / "raw"

# SC-005：< 10 MB（10 * 1024 * 1024 = 10_485_760 bytes）
_BUDGET_BYTES = 10 * 1024 * 1024


def _collect_snapshot_files() -> list[Path]:
    if not _DATA_RAW.is_dir():
        return []
    return sorted(
        p
        for p in _DATA_RAW.iterdir()
        if p.is_file() and (p.suffix == ".parquet" or p.name.endswith(".parquet.meta.json"))
    )


def test_data_raw_total_size_under_10mb() -> None:
    files = _collect_snapshot_files()
    if not files:
        pytest.skip("data/raw/ has no snapshots yet (T055 pending)")

    breakdown = [(p.name, p.stat().st_size) for p in files]
    total = sum(size for _, size in breakdown)

    if total >= _BUDGET_BYTES:
        # 列出最大檔案讓研究者快速定位過胖快照
        offenders = sorted(breakdown, key=lambda kv: -kv[1])[:5]
        offender_lines = "\n".join(f"  {name}: {size:,} bytes" for name, size in offenders)
        pytest.fail(
            f"data/raw/ total size {total:,} bytes exceeds SC-005 budget "
            f"{_BUDGET_BYTES:,} bytes ({_BUDGET_BYTES / 1024 / 1024:.1f} MB).\n"
            f"Largest files:\n{offender_lines}"
        )
