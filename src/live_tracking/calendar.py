"""NYSE trading calendar — 010 FR-007.

純函數 ``missing_trading_days(last_frame_date, today, *, start_anchor)``。
回傳 ``last_frame_date`` 之後（不含）到 ``today``（含）之間的 NYSE 交易日。

研究決策 R2：採 ``pandas_market_calendars`` 而非自建表，避免漏 Federal holiday
與半日市行為漂移。半日市（如 Black Friday）視為正常交易日。

Edge case: 若 ``last_frame_date is None``（首次啟動），從 ``start_anchor``
（預設 spec FR-002 = 2026-04-29）算起；若 ``today < start_anchor`` 回 ``[]``
（防止負區間建立）。
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pandas_market_calendars as mcal


def _to_date(ts: pd.Timestamp) -> date:
    return date(ts.year, ts.month, ts.day)


def missing_trading_days(
    last_frame_date: date | None,
    today: date,
    *,
    start_anchor: date = date(2026, 4, 29),
) -> list[date]:
    """Return list of NYSE trading days in (last_frame_date, today] window.

    Args:
        last_frame_date: artefact 最後一個 frame 的交易日；None ⇒ 從 anchor 開始。
        today: 上界（含）；通常是呼叫方 `date.today()` 或測試 freezegun 鎖定值。
        start_anchor: 首次啟動的下界（含）；預設 spec FR-002 = 2026-04-29。

    Returns:
        嚴格遞增的交易日 list。若無缺漏（last_frame_date >= today，或
        today < start_anchor），回 ``[]``。
    """
    if last_frame_date is not None and last_frame_date >= today:
        return []

    lower = (
        start_anchor
        if last_frame_date is None
        else date.fromordinal(last_frame_date.toordinal() + 1)
    )

    if today < lower:
        return []

    nyse = mcal.get_calendar("NYSE")
    schedule = nyse.schedule(start_date=lower, end_date=today)
    if schedule.empty:
        return []
    return [_to_date(ts) for ts in schedule.index]


__all__ = ["missing_trading_days"]
