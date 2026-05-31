"""
Abstract base class for TradingCalendar.

A TradingCalendar determines whether market activity is expected at a given
UTC timestamp.  It does NOT model live prices, provider behavior, or execution
mechanics.

Design constraints:
- All datetime arguments must be UTC-aware; naive datetimes raise ValueError.
- Calendars have no I/O; no database or network access.
- Holiday databases and intraday session windows are deferred (see MARKET_CALENDAR.md).
"""
from abc import ABC, abstractmethod
from datetime import datetime


class TradingCalendar(ABC):
    """
    Minimal calendar abstraction for forward-testing market session policy.

    Responsibilities:
    - Determine whether a market session is expected at a given UTC time.
    - Determine whether a bar should exist for a given timestamp/timeframe.
    - Distinguish market-closed periods from possible provider failure.

    Subclasses must enforce UTC-awareness on all datetime arguments and
    must raise ValueError for naive (timezone-unaware) inputs.
    """

    @abstractmethod
    def is_session_open(self, dt: datetime) -> bool:
        """
        Return True if a trading session is expected to be active at *dt*.

        Args:
            dt: UTC-aware datetime to check.

        Returns:
            True if the market is expected to be open at this point in time.

        Raises:
            ValueError: if *dt* is timezone-naive.
        """

    @abstractmethod
    def is_bar_expected(self, bar_timestamp: datetime, timeframe: str) -> bool:
        """
        Return True if a bar with open-time *bar_timestamp* is expected to exist.

        A bar is "expected" when the calendar indicates that a trading session
        covers the period beginning at *bar_timestamp*.  Absence of an expected
        bar signals a potential provider failure or data gap.  Absence of an
        unexpected bar is normal market closure and must not be treated as a gap.

        Args:
            bar_timestamp: Candle open-time.  Must be UTC-aware.
            timeframe:     Canonical QuantLab timeframe string (e.g. "1d", "1h").
                           Accepted for future extensibility; some calendars may
                           vary expected-bar logic by timeframe.

        Returns:
            True if the bar is expected given this calendar.

        Raises:
            ValueError: if *bar_timestamp* is timezone-naive.
        """
