"""T029 — DST 切換正確性 (RED → GREEN at T031).

對應 plan §Risks DST：APScheduler + pytz 必須在 DST spring-forward / fall-back
正確計算下次 trigger time（仍指向 16:30 ET，跨 DST 後 UTC offset 從 -5 變 -4）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
import pytz


def test_dst_spring_forward_next_run_at_1630_et(fake_state: Any) -> None:
    """2026-03-08 ET 是 DST spring-forward 日（02:00 → 03:00）。

    在 03-07 半夜建立 scheduler，next_run_time 應指向 03-09 (Mon) 16:30 ET（即 20:30 UTC，因 DST 後 EDT=UTC-4）。
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    et = pytz.timezone("America/New_York")
    # 2026-03-07 23:00 ET (DST 切換前一天晚上)
    fake_now = et.localize(datetime(2026, 3, 7, 23, 0, 0))

    scheduler = AsyncIOScheduler(timezone=et)
    trigger = CronTrigger.from_crontab("30 16 * * MON-FRI", timezone=et)

    # APScheduler CronTrigger.get_next_fire_time(prev, now)
    next_fire = trigger.get_next_fire_time(None, fake_now)
    scheduler.shutdown(wait=False) if scheduler.running else None

    assert next_fire is not None
    next_fire_et = next_fire.astimezone(et)
    assert next_fire_et.hour == 16 and next_fire_et.minute == 30, next_fire_et
    # 03-09 是 Monday；如果切換前那一天剛好計算過 03-08 那也接受；只要落在 weekday 16:30 即可
    assert next_fire_et.weekday() < 5  # Mon-Fri
    # 確認 utcoffset 反映 EDT (-4) 或 EST (-5)，跨 DST 後應為 EDT
    assert next_fire_et.utcoffset().total_seconds() == -4 * 3600  # EDT


def test_dst_fall_back_next_run_at_1630_et(fake_state: Any) -> None:
    """2026-11-01 ET 是 DST fall-back 日（02:00 → 01:00）。

    在 10-31 半夜建立 scheduler，next_run_time 應指向 11-02 (Mon) 16:30 ET，
    UTC offset 從 -4 (EDT) 變成 -5 (EST)。
    """
    from apscheduler.triggers.cron import CronTrigger

    et = pytz.timezone("America/New_York")
    fake_now = et.localize(datetime(2026, 10, 31, 23, 0, 0))

    trigger = CronTrigger.from_crontab("30 16 * * MON-FRI", timezone=et)
    next_fire = trigger.get_next_fire_time(None, fake_now)

    assert next_fire is not None
    next_fire_et = next_fire.astimezone(et)
    assert next_fire_et.hour == 16 and next_fire_et.minute == 30, next_fire_et
    assert next_fire_et.weekday() < 5
    # DST fall-back 後 EST (-5)
    assert next_fire_et.utcoffset().total_seconds() == -5 * 3600  # EST
