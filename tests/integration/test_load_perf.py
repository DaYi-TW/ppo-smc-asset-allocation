"""SC-003 效能：load_asset_snapshot 在 SSD 上連續 10 次 p95 < 500 ms（CI 寬鬆值）。

本機 SSD 通常 < 100 ms；CI runner（共享 IO、容器冷啟動）放寬至 500 ms 以
避免偽陽性。Phase 7 polish 階段會用真實 data/raw/ 加上更嚴格的 < 100 ms 測試。
"""

from __future__ import annotations

import time

import data_ingestion

PERF_BUDGET_SECONDS = 0.5


def test_load_asset_snapshot_p95_within_budget(tmp_data_dir):
    samples: list[float] = []
    for _ in range(10):
        t0 = time.perf_counter()
        data_ingestion.load_asset_snapshot("NVDA", data_dir=tmp_data_dir)
        samples.append(time.perf_counter() - t0)

    samples.sort()
    p95 = samples[int(0.95 * len(samples)) - 1]
    assert p95 < PERF_BUDGET_SECONDS, (
        f"load_asset_snapshot p95 = {p95 * 1000:.1f} ms exceeds "
        f"{PERF_BUDGET_SECONDS * 1000:.0f} ms budget; samples (ms): "
        f"{[round(s * 1000, 1) for s in samples]}"
    )


def test_load_rate_snapshot_p95_within_budget(tmp_data_dir):
    samples: list[float] = []
    for _ in range(10):
        t0 = time.perf_counter()
        data_ingestion.load_rate_snapshot("DTB3", data_dir=tmp_data_dir)
        samples.append(time.perf_counter() - t0)

    samples.sort()
    p95 = samples[int(0.95 * len(samples)) - 1]
    assert p95 < PERF_BUDGET_SECONDS
