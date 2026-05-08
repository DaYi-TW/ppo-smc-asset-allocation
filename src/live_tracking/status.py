"""LiveTrackingStatus state machine — spec 010 FR-010 / FR-011 / FR-015.

持久化於 ``runs/<policy_run_id>/live_tracking/live_tracking_status.json``。
State transitions（research §R6）::

    [absent] ─load→ [is_running=False, all None]
    [is_running=False] ─mark_running→ [is_running=True, pid+started_at set]
    [is_running=True] ─mark_succeeded(d)→ [is_running=False, last_frame_date=d, last_error=None]
    [is_running=True] ─mark_failed(msg)→ [is_running=False, last_error=msg, last_frame_date unchanged]

Orphan recovery: startup 時若 status.is_running=True，比對 running_pid 是否存在
+ process create_time 是否與 running_started_at 一致；任一不符 → 視為 orphan
（前次 process 被 SIGKILL）+ reset is_running=False，寫入 last_error。
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict


class LiveTrackingStatus(BaseModel):
    """Persistent status for live tracking pipeline.

    See ``specs/010-live-tracking-dashboard/data-model.md §2``.
    """

    model_config = ConfigDict(extra="forbid")

    last_updated: datetime | None = None
    last_frame_date: date | None = None
    is_running: bool = False
    last_error: str | None = None
    running_pid: int | None = None
    running_started_at: datetime | None = None

    # ---------- IO ----------

    @classmethod
    def load(cls, path: Path) -> Self:
        if not path.exists():
            return cls()
        text = path.read_text(encoding="utf-8")
        return cls.model_validate_json(text)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # mode='json' 把 datetime / date 序列化為 ISO 字串
        data = self.model_dump(mode="json")
        text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
        path.write_text(text + "\n", encoding="utf-8")

    # ---------- State transitions ----------

    def mark_running(self, *, pid: int, started_at: datetime) -> None:
        self.is_running = True
        self.running_pid = pid
        self.running_started_at = started_at

    def mark_succeeded(self, *, last_frame_date: date | None) -> None:
        self.is_running = False
        self.running_pid = None
        self.running_started_at = None
        self.last_error = None
        if last_frame_date is not None:
            self.last_frame_date = last_frame_date
        self.last_updated = datetime.now(UTC)

    def mark_failed(self, error_message: str) -> None:
        self.is_running = False
        self.running_pid = None
        self.running_started_at = None
        self.last_error = error_message
        # last_updated **not** updated on failure — 維持 last_updated = 上次成功時間。
        # last_frame_date unchanged.

    # ---------- Recovery ----------

    def recover_orphan(self, *, current_pid: int) -> bool:
        """Reset is_running if recorded pid is dead or pid mismatch.

        Returns True iff an orphan was detected and reset.
        """
        if not self.is_running:
            return False
        if self.running_pid is None or self.running_started_at is None:
            # is_running=True 但 metadata 不完整 → 視為 orphan
            self._reset_orphan("orphan lock recovered at startup (missing metadata)")
            return True

        try:
            import psutil
        except ImportError:  # pragma: no cover
            self._reset_orphan("orphan lock recovered (psutil unavailable)")
            return True

        if not psutil.pid_exists(self.running_pid):
            self._reset_orphan(
                f"orphan lock recovered: pid {self.running_pid} no longer exists"
            )
            return True

        try:
            proc = psutil.Process(self.running_pid)
            create_time = datetime.fromtimestamp(proc.create_time(), tz=UTC)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self._reset_orphan(
                f"orphan lock recovered: pid {self.running_pid} not accessible"
            )
            return True

        # 容差 2 秒，避開 fs timestamp resolution + clock skew
        if abs((create_time - self.running_started_at).total_seconds()) > 2.0:
            self._reset_orphan(
                f"orphan lock recovered: pid {self.running_pid} create_time mismatch"
            )
            return True

        # 真的還在跑 → 不重置
        return False

    def _reset_orphan(self, reason: str) -> None:
        self.is_running = False
        self.running_pid = None
        self.running_started_at = None
        self.last_error = reason


__all__ = ["LiveTrackingStatus"]
