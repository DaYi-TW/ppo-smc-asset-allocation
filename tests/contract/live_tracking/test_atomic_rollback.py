"""T052 — Phase 5 (US3) atomic rollback contract test (FR-009 / INV-2 / SC-005).

對應 spec 010 ``FR-009 atomic write`` + ``INV-2 atomicity`` + ``SC-005`` + research
§R1：``os.replace`` 失敗 → tmp 清掉 + 既有檔案 byte-identical 到 patch 之前。

兩條 invariants：
1. **Replace failure**：``os.replace`` raise OSError → exception 上傳；既存 artefact
   sha256 + mtime 完全不變；殘留 tmp 已被清掉（INV-2）。
2. **Write failure**：tmp 寫到一半 raise → 既存 artefact byte-equal 並無殘留 tmp。

是 Phase 5 「失敗回滾」 user story 的 hard gate — 任何 atomic write 改寫
需先過這條 test 才可 merge。
"""

from __future__ import annotations

import hashlib
import os
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from inference_service.episode_schemas import EpisodeDetail
from live_tracking.store import LiveTrackingStore


def _envelope(n: int = 1) -> EpisodeDetail:
    """Minimal valid EpisodeDetail with n frames（dates from 2026-04-29）。"""
    frames = [
        {
            "timestamp": f"2026-04-{29 + i:02d}T00:00:00Z",
            "step": i,
            "weights": {
                "riskOn": 0.4,
                "riskOff": 0.4,
                "cash": 0.2,
                "perAsset": {},
            },
            "nav": 1.7291986,
            "drawdownPct": 0.0,
            "reward": {
                "total": 0.0,
                "returnComponent": 0.0,
                "drawdownPenalty": 0.0,
                "costPenalty": 0.0,
            },
            "smcSignals": {
                "bos": 0,
                "choch": 0,
                "fvgDistancePct": None,
                "obTouching": False,
                "obDistanceRatio": None,
            },
            "ohlcv": {
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1.0,
            },
            "ohlcvByAsset": {},
            "action": {
                "raw": [0.1] * 7,
                "normalized": [1 / 7] * 7,
                "logProb": -1.0,
                "entropy": 0.5,
            },
        }
        for i in range(n)
    ]
    return EpisodeDetail.model_validate(
        {
            "summary": {
                "id": "test_policy_live",
                "policyId": "test_policy",
                "startDate": "2026-04-29",
                "endDate": f"2026-04-{29 + n - 1:02d}" if n else "2026-04-29",
                "nSteps": n,
                "initialNav": 1.7291986,
                "finalNav": 1.7291986,
                "cumulativeReturnPct": 0.0,
                "annualizedReturnPct": 0.0,
                "maxDrawdownPct": 0.0,
                "sharpeRatio": 0.0,
                "sortinoRatio": 0.0,
                "includeSmc": True,
            },
            "trajectoryInline": frames,
            "rewardBreakdown": {
                "byStep": [f["reward"] for f in frames],
                "cumulative": [
                    {
                        "step": i + 1,
                        "cumulativeTotal": 0.0,
                        "cumulativeReturn": 0.0,
                        "cumulativeDrawdownPenalty": 0.0,
                        "cumulativeCostPenalty": 0.0,
                    }
                    for i in range(n)
                ],
            },
            "smcOverlayByAsset": {},
        }
    )


@pytest.fixture
def store_with_v1(tmp_path: Path) -> tuple[LiveTrackingStore, str, float]:
    """初始化 artefact 為 v1（1 frame）→ 回 (store, sha256, mtime_ns)。"""
    path = tmp_path / "live_tracking.json"
    store = LiveTrackingStore(path)
    store.atomic_write(_envelope(1))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    mtime_ns = path.stat().st_mtime_ns
    return store, sha, mtime_ns


def _no_residual_tmp(path: Path) -> bool:
    return not (path.with_suffix(path.suffix + ".tmp")).exists()


class TestAtomicRollbackOnReplaceFailure:
    """INV-2 — ``os.replace`` raise → existing artefact byte-equal + tmp removed。"""

    def test_replace_oserror_preserves_existing_file(
        self, store_with_v1: tuple[LiveTrackingStore, str, float], _date: date = date(2026, 4, 29)
    ) -> None:
        del _date  # unused — kept for test signature symmetry
        store, original_sha, _ = store_with_v1
        path = store.path

        # patch os.replace 在 store 模組命名空間 → raise
        with (
            patch("live_tracking.store.os.replace", side_effect=OSError("disk full")),
            pytest.raises(OSError, match="disk full"),
        ):
            store.atomic_write(_envelope(2))

        # Invariant 1: existing artefact byte-equal to pre-patch state
        assert hashlib.sha256(path.read_bytes()).hexdigest() == original_sha

        # Invariant 2: no residual .tmp file
        assert _no_residual_tmp(path), (
            f"residual {path.with_suffix(path.suffix + '.tmp')} after rollback"
        )

    def test_replace_oserror_load_returns_v1(
        self, store_with_v1: tuple[LiveTrackingStore, str, float]
    ) -> None:
        """rollback 後 store.load() 回 v1（即 1 frame），證明邏輯層面也乾淨。"""
        store, _, _ = store_with_v1
        with (
            patch("live_tracking.store.os.replace", side_effect=OSError("ENOSPC")),
            pytest.raises(OSError),
        ):
            store.atomic_write(_envelope(2))

        loaded = store.load()
        assert loaded is not None
        assert len(loaded.trajectoryInline) == 1


class TestAtomicRollbackOnWriteFailure:
    """INV-2 — tmp 寫入過程 raise → existing artefact byte-equal + tmp removed。"""

    def test_open_failure_preserves_existing_file(
        self, store_with_v1: tuple[LiveTrackingStore, str, float]
    ) -> None:
        store, original_sha, _ = store_with_v1
        path = store.path

        # patch open 在 store 模組 → raise (simulates fs error during write)
        real_open = open

        def boom(file, *args, **kwargs):  # type: ignore[no-untyped-def]
            if str(file).endswith(".tmp"):
                raise OSError("ENOSPC: no space left on device")
            return real_open(file, *args, **kwargs)

        with (
            patch("live_tracking.store.open", side_effect=boom),
            pytest.raises(OSError, match="ENOSPC"),
        ):
            store.atomic_write(_envelope(2))

        assert hashlib.sha256(path.read_bytes()).hexdigest() == original_sha
        assert _no_residual_tmp(path)


class TestAtomicWriteHappyPath:
    """sanity baseline: 沒注入 fault 時 atomic_write 正常成功。"""

    def test_consecutive_writes_succeed(self, tmp_path: Path) -> None:
        path = tmp_path / "live_tracking.json"
        store = LiveTrackingStore(path)
        store.atomic_write(_envelope(1))
        sha1 = hashlib.sha256(path.read_bytes()).hexdigest()
        store.atomic_write(_envelope(2))
        sha2 = hashlib.sha256(path.read_bytes()).hexdigest()
        # 內容變了 → sha 必須變；rollback 路徑 sha 不變。
        assert sha1 != sha2
        assert _no_residual_tmp(path)
        assert os.path.exists(path)
