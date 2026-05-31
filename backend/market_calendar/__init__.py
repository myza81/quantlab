"""
QuantLab market calendar package — Phase 4C.3A.

Provides exchange calendar abstractions and bar-finalization policy helpers
for forward testing and future execution modes.

Public API
----------
Calendar types:
    TradingCalendar          — abstract base; extend for new calendar types
    TwentyFourSevenCalendar  — crypto / always-open markets
    WeekdayMarketCalendar    — Monday–Friday equity markets (no holiday DB)
    DefaultCalendar          — conservative fallback (behaves as WeekdayMarketCalendar)

Registry:
    get_calendar(asset_class, ...)  — resolve a TradingCalendar from market context

Policy helpers:
    is_bar_expected(bar_timestamp, timeframe, calendar)
        Returns True if a bar should exist given the calendar.
        Primary use: gap detection in ForwardTestService.

    is_bar_finalized(bar_timestamp, timeframe, now_utc, calendar, safety_buffer)
        Returns True if the bar is both time-finalized AND expected by the calendar.
        Primary use: bar processing gate in ForwardTestService.

Known limitations (see docs/MARKET_CALENDAR.md)
------------------------------------------------
- No exchange-specific holiday database (NYSE, LSE, Bursa, etc.)
- No intraday session window enforcement (e.g. 09:30–16:00 NYSE)
- No half-day / early-close modeling
- ``provider_name``, ``exchange``, ``symbol`` reserved in get_calendar() but not yet used
- Future expansion: full exchange calendars, intraday schedules, holiday feeds
"""
from backend.market_calendar.base import TradingCalendar
from backend.market_calendar.calendars import (
    DefaultCalendar,
    TwentyFourSevenCalendar,
    WeekdayMarketCalendar,
)
from backend.market_calendar.policy import is_bar_expected, is_bar_finalized
from backend.market_calendar.registry import get_calendar

__all__ = [
    "TradingCalendar",
    "TwentyFourSevenCalendar",
    "WeekdayMarketCalendar",
    "DefaultCalendar",
    "get_calendar",
    "is_bar_expected",
    "is_bar_finalized",
]
