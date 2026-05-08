"""T005 — calendar.missing_trading_days unit tests (spec 010 FR-007).

Cover:
- empty range when last_date >= today
- skip weekend
- skip Federal holiday (Memorial Day 2026-05-25)
- 半日市仍視為交易日（Black Friday 2026-11-27）
- start anchor 邊界（today < 2026-04-29 → []）
"""

from __future__ import annotations

from datetime import date

import pytest

from live_tracking.calendar import missing_trading_days


class TestMissingTradingDays:
    def test_returns_empty_when_last_frame_equals_today(self) -> None:
        assert missing_trading_days(date(2026, 5, 7), date(2026, 5, 7)) == []

    def test_returns_empty_when_last_frame_after_today(self) -> None:
        assert missing_trading_days(date(2026, 5, 8), date(2026, 5, 7)) == []

    def test_skips_weekend(self) -> None:
        # 2026-05-08 is Friday; 2026-05-11 is Monday. Weekend skipped.
        result = missing_trading_days(date(2026, 5, 8), date(2026, 5, 11))
        assert result == [date(2026, 5, 11)]

    def test_skips_memorial_day_2026(self) -> None:
        # Memorial Day = 2026-05-25 (Mon). Range 2026-05-22 (Fri) → 2026-05-26 (Tue).
        result = missing_trading_days(date(2026, 5, 22), date(2026, 5, 26))
        assert result == [date(2026, 5, 26)]
        assert date(2026, 5, 25) not in result

    def test_includes_half_day_black_friday_2026(self) -> None:
        # Black Friday 2026 = 2026-11-27, half-day market but is still a trading day.
        result = missing_trading_days(date(2026, 11, 26), date(2026, 11, 27))
        # 2026-11-26 is Thanksgiving (closed), 2026-11-27 half-day open.
        assert result == [date(2026, 11, 27)]

    def test_thanksgiving_skipped(self) -> None:
        result = missing_trading_days(date(2026, 11, 25), date(2026, 11, 26))
        assert result == []  # Thanksgiving closed, no other trading day in range

    def test_start_anchor_when_last_frame_none(self) -> None:
        # today < anchor → []
        result = missing_trading_days(None, date(2026, 4, 28), start_anchor=date(2026, 4, 29))
        assert result == []

    def test_start_anchor_when_today_equals_anchor(self) -> None:
        # 2026-04-29 is a Wednesday → trading day.
        result = missing_trading_days(None, date(2026, 4, 29), start_anchor=date(2026, 4, 29))
        assert result == [date(2026, 4, 29)]

    def test_start_anchor_when_today_after_anchor(self) -> None:
        result = missing_trading_days(None, date(2026, 5, 1), start_anchor=date(2026, 4, 29))
        # 2026-04-29 (Wed), 2026-04-30 (Thu), 2026-05-01 (Fri) all trading days
        assert result == [date(2026, 4, 29), date(2026, 4, 30), date(2026, 5, 1)]

    def test_consecutive_trading_days_strict_ascending(self) -> None:
        result = missing_trading_days(date(2026, 5, 1), date(2026, 5, 8))
        assert result == [
            date(2026, 5, 4),
            date(2026, 5, 5),
            date(2026, 5, 6),
            date(2026, 5, 7),
            date(2026, 5, 8),
        ]
        # Strict ascending
        assert result == sorted(set(result))


class TestStartAnchorEdgeCase:
    """Spec 010 edge case: 首次啟動且 today < 2026-04-29 → 不應建立負區間."""

    def test_today_before_anchor_returns_empty(self) -> None:
        result = missing_trading_days(None, date(2026, 4, 1), start_anchor=date(2026, 4, 29))
        assert result == []

    @pytest.mark.parametrize("delta_days", [1, 7, 30])
    def test_today_after_anchor_includes_anchor(self, delta_days: int) -> None:
        from datetime import timedelta

        today = date(2026, 4, 29) + timedelta(days=delta_days)
        result = missing_trading_days(None, today, start_anchor=date(2026, 4, 29))
        # Anchor should be the first element (it's a Wednesday → trading day)
        assert len(result) >= 1
        assert result[0] == date(2026, 4, 29)
