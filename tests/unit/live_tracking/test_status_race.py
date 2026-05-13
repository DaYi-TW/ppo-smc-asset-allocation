"""Race tests for LiveTrackingStatus atomic write + load retry.

Regression for the 2026-05-13 incident：
    POST /api/v1/episodes/live/refresh accepted (pipeline starts) →
    same-process GET /api/v1/episodes/live/status reads status file
    while pipeline is mid-write → pydantic ValidationError
    (truncated JSON) → 500 → Gateway translates to 503.

Fix：atomic write (`.tmp` + os.replace + fsync) + load() retry on
ValidationError / JSONDecodeError / FileNotFoundError.
"""

from __future__ import annotations

import threading
from datetime import UTC, date, datetime
from pathlib import Path

from live_tracking.status import LiveTrackingStatus


def test_concurrent_read_during_write_does_not_raise(tmp_path: Path) -> None:
    """write() 是 atomic — reader 不應抓到截斷 JSON 或 ValidationError."""
    path = tmp_path / "status.json"
    LiveTrackingStatus(
        is_running=False, last_frame_date=date(2026, 5, 11)
    ).write(path)

    errors: list[Exception] = []
    stop = threading.Event()

    def writer() -> None:
        for i in range(200):
            if stop.is_set():
                return
            try:
                LiveTrackingStatus(
                    is_running=(i % 2 == 0),
                    last_frame_date=date(2026, 5, 11),
                    last_updated=datetime.now(UTC),
                    running_pid=12345 if i % 2 == 0 else None,
                ).write(path)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    def reader() -> None:
        for _ in range(500):
            if stop.is_set():
                return
            try:
                LiveTrackingStatus.load(path)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    threads = [
        threading.Thread(target=writer),
        threading.Thread(target=reader),
        threading.Thread(target=reader),
    ]
    for t in threads:
        t.start()
    threads[0].join(timeout=10)
    stop.set()
    for t in threads[1:]:
        t.join(timeout=2)

    assert not errors, f"concurrent IO raised: {errors[:3]}"


def test_atomic_write_leaves_no_temp_file(tmp_path: Path) -> None:
    """成功 write() 不應留 .tmp 殘檔（os.replace 必須執行）."""
    path = tmp_path / "status.json"
    LiveTrackingStatus(is_running=True).write(path)
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == [], f"tmp leftover: {leftovers}"
