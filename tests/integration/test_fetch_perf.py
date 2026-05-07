"""SC-001 — fetch 流程純本地時間 < 30 秒（5 分鐘預算扣除網路後寬鬆）。

策略：用 fake fetcher 完全去掉網路 I/O，量測純磁碟 I/O + parquet 寫入 +
metadata 計算 + atomic publish 的牆鐘時間。預算 30 秒對 7 個小快照（每檔
~6 列）非常寬鬆，CI 上若超出代表有性能 regression（例如不必要的 schema
重複讀取、O(n^2) 演算法等）。
"""

from __future__ import annotations

import time
from pathlib import Path

from data_ingestion.fetcher import fetch_all
from tests.integration.test_atomic_fetch import (  # type: ignore[import-not-found]
    _make_config,
    fake_asset_fetcher,
    fake_rate_fetcher,
)

# SC-001 扣除網路後的本地預算（秒）
_BUDGET_SECONDS = 30.0


def test_fetch_all_local_runtime_under_budget(tmp_path: Path):
    cfg = _make_config(tmp_path)
    started = time.perf_counter()
    snapshots = fetch_all(cfg, asset_fetcher=fake_asset_fetcher, rate_fetcher=fake_rate_fetcher)
    elapsed = time.perf_counter() - started

    assert len(snapshots) == 7, "fetch_all 必須產出 7 個快照"
    assert elapsed < _BUDGET_SECONDS, (
        f"fetch_all 純本地耗時 {elapsed:.2f}s 超過 SC-001 預算 "
        f"{_BUDGET_SECONDS:.0f}s — 檢查是否引入 O(n^2) / 多餘 I/O"
    )
