"""
Built-in TradingCalendar implementations.

Provided:
- TwentyFourSevenCalendar  — crypto / always-open markets (no closures)
- WeekdayMarketCalendar    — Monday–Friday equity markets (no holiday DB)
- DefaultCalendar          — conservative fallback; behaves as WeekdayMarketCalendar

Limitations (see docs/MARKET_CALENDAR.md):
- No exchange-specific holiday database (NYSE, Bursa, etc.)
- No intraday session-window enforcement (e.g. 09:30–16:00 NYSE)
- No half-day / early-close modeling
- Weekday determination is purely date-based; no timezone offset for market-open

These calendars are intentionally minimal.  They correctly distinguish
weekday/weekend boundaries and 24/7 vs. Monday–Friday markets without
requiring external dependencies.
"""
from datetime import datetime

from backend.market_calendar.base import TradingCalendar


class TwentyFourSevenCalendar(TradingCalendar):
    """
    Calendar for 24/7 markets (crypto, digital assets).

    Every timestamp on every day of the week is an expected trading period.
    Weekends, holidays, and closures do not apply.

    Instruments: BTC-USD, ETH-USD, and any asset that trades continuously.
    """

    def is_session_open(self, dt: datetime) -> bool:
        if dt.tzinfo is None:
            raise ValueError("dt must be UTC-aware; got naive datetime")
        return True

    def is_bar_expected(self, bar_timestamp: datetime, timeframe: str) -> bool:
        if bar_timestamp.tzinfo is None:
            raise ValueError("bar_timestamp must be UTC-aware; got naive datetime")
        return True


class WeekdayMarketCalendar(TradingCalendar):
    """
    Calendar for Monday–Friday equity/ETF/fund markets.

    Saturdays and Sundays are not expected trading days.
    Holiday database is deferred (see docs/MARKET_CALENDAR.md).
    Intraday session windows (e.g. 09:30–16:00) are deferred.

    Weekday determination uses Python's datetime.weekday():
        0 = Monday, 1 = Tuesday, ..., 4 = Friday, 5 = Saturday, 6 = Sunday

    Instruments: AAPL, MSFT, SPY, and any standard equity/ETF trading Mon–Fri.
    """

    def is_session_open(self, dt: datetime) -> bool:
        if dt.tzinfo is None:
            raise ValueError("dt must be UTC-aware; got naive datetime")
        return dt.weekday() < 5

    def is_bar_expected(self, bar_timestamp: datetime, timeframe: str) -> bool:
        if bar_timestamp.tzinfo is None:
            raise ValueError("bar_timestamp must be UTC-aware; got naive datetime")
        return bar_timestamp.weekday() < 5


class DefaultCalendar(WeekdayMarketCalendar):
    """
    Conservative fallback calendar for unknown or unclassified asset classes.

    Behaves identically to WeekdayMarketCalendar: Monday–Friday sessions,
    weekends excluded.  ForwardTestService uses this when no explicit
    asset_class → calendar mapping exists, erring on the side of caution
    (not expecting weekend bars) rather than assuming 24/7 availability.

    This conservative default prevents false gap alerts on weekends for
    instruments whose trading schedule is unknown.
    """
