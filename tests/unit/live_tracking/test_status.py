"""T006 — LiveTrackingStatus state machine + persistence + orphan recovery.

對應 spec 010 FR-010 / FR-011 / FR-015、data-model §2、research R6。
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from live_tracking.status import LiveTrackingStatus


@pytest.fixture
def status_path(tmp_path: Path) -> Path:
    return tmp_path / "live_tracking_status.json"


class TestLoadAbsent:
    def test_load_absent_returns_blank(self, status_path: Path) -> None:
        s = LiveTrackingStatus.load(status_path)
        assert s.last_updated is None
        assert s.last_frame_date is None
        assert s.is_running is False
        assert s.last_error is None
        assert s.running_pid is None
        assert s.running_started_at is None


class TestRoundTrip:
    def test_write_then_load_byte_equal(self, status_path: Path) -> None:
        s = LiveTrackingStatus(
            last_updated=datetime(2026, 5, 8, 14, 0, 0, tzinfo=UTC),
            last_frame_date=date(2026, 5, 7),
            is_running=False,
            last_error=None,
            running_pid=None,
            running_started_at=None,
        )
        s.write(status_path)
        loaded = LiveTrackingStatus.load(status_path)
        assert loaded == s


class TestStateTransitions:
    def test_mark_running_sets_pid_and_timestamps(self, status_path: Path) -> None:
        s = LiveTrackingStatus.load(status_path)
        s.mark_running(pid=12345, started_at=datetime(2026, 5, 8, 14, 0, 0, tzinfo=UTC))
        assert s.is_running is True
        assert s.running_pid == 12345
        assert s.running_started_at == datetime(2026, 5, 8, 14, 0, 0, tzinfo=UTC)

    def test_mark_succeeded_clears_error_and_pid(self, status_path: Path) -> None:
        s = LiveTrackingStatus.load(status_path)
        s.mark_running(pid=12345, started_at=datetime(2026, 5, 8, 14, 0, 0, tzinfo=UTC))
        s.last_error = "DATA_FETCH: previous run failure"
        s.mark_succeeded(last_frame_date=date(2026, 5, 7))
        assert s.is_running is False
        assert s.running_pid is None
        assert s.running_started_at is None
        assert s.last_error is None
        assert s.last_frame_date == date(2026, 5, 7)
        assert s.last_updated is not None

    def test_mark_succeeded_no_op_keeps_last_frame_date(self, status_path: Path) -> None:
        s = LiveTrackingStatus.load(status_path)
        s.last_frame_date = date(2026, 5, 5)
        s.mark_running(pid=42, started_at=datetime(2026, 5, 8, 14, 0, tzinfo=UTC))
        s.mark_succeeded(last_frame_date=None)  # no new frame
        assert s.last_frame_date == date(2026, 5, 5)  # unchanged
        assert s.is_running is False

    def test_mark_failed_keeps_last_frame_date_writes_error(self, status_path: Path) -> None:
        s = LiveTrackingStatus.load(status_path)
        s.last_frame_date = date(2026, 5, 5)
        s.mark_running(pid=42, started_at=datetime(2026, 5, 8, 14, 0, tzinfo=UTC))
        s.mark_failed("DATA_FETCH: yfinance returned empty for NVDA on 2026-05-08")
        assert s.is_running is False
        assert s.running_pid is None
        assert s.running_started_at is None
        assert s.last_frame_date == date(2026, 5, 5)  # unchanged
        assert s.last_error is not None
        assert s.last_error.startswith("DATA_FETCH:")


class TestOrphanRecovery:
    """research R6: PID + create_time double-check."""

    def test_recover_clean_when_not_running(self, status_path: Path) -> None:
        s = LiveTrackingStatus.load(status_path)
        recovered = s.recover_orphan(current_pid=os.getpid())
        assert recovered is False
        assert s.is_running is False

    def test_recover_orphan_when_pid_dead(self, status_path: Path) -> None:
        s = LiveTrackingStatus.load(status_path)
        # Use a PID that almost certainly doesn't exist
        s.is_running = True
        s.running_pid = 999999
        s.running_started_at = datetime(2026, 5, 8, 14, 0, tzinfo=UTC)
        recovered = s.recover_orphan(current_pid=os.getpid())
        assert recovered is True
        assert s.is_running is False
        assert s.running_pid is None
        assert s.running_started_at is None
        assert s.last_error is not None
        assert "orphan" in s.last_error.lower()

    def test_recover_keeps_running_when_pid_alive_and_matches(self, status_path: Path) -> None:
        # 模擬「我自己是 running pid」：用當前 process 的真實 pid + create_time
        import psutil

        my_pid = os.getpid()
        my_create_time = datetime.fromtimestamp(psutil.Process(my_pid).create_time(), tz=UTC)
        s = LiveTrackingStatus.load(status_path)
        s.is_running = True
        s.running_pid = my_pid
        s.running_started_at = my_create_time
        # 假裝 startup hook 是另一 process 跑
        recovered = s.recover_orphan(current_pid=my_pid + 1)
        # 因為 pid 還活著且 started_at 與 process create_time 一致 → 不算 orphan
        assert recovered is False
        assert s.is_running is True


class TestStrictSchema:
    def test_extra_field_forbidden(self, status_path: Path) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LiveTrackingStatus.model_validate({"last_updated": None, "extra": "x"})
