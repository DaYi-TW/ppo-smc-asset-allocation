"""APScheduler cron + pytz ET timezone + DST 安全 + 失敗不停 scheduler。

對應 spec FR-002 / FR-010 / SC-002。Phase 4 T031 實作。
"""

from __future__ import annotations
