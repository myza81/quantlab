"""
Calendar-aware bar finalization and expected-bar policy helpers.

These are the primary primitives for ForwardTestService to decide:
1. Whether an existing bar is both finalized and expected.
2. Whether an absent bar represents a gap vs. normal market closure.

Both functions are UTC-pure: naive datetimes are rejected with ValueError.

Phase 4C.3 integration
----------------------
``is_bar_finalized()`` in this module wraps the time-check primitive from
``backend.services.ohlcv_service`` and adds calendar awareness.

The two functions serve different layers:

    ohlcv_service.is_bar_finalized
        Time-only check — no calendar context.
        Used by OHLCVService.get_recent_bars() and get_bars_since() for
        historical and research-grade data retrieval.

    market_calendar.policy.is_bar_finalized
        Time + calendar check — for forward testing only.
        A bar is finalized in the forward-testing sense only when BOTH the
        candle period has elapsed AND the calendar expected the bar to exist.

This design ensures that the Phase 4C.3 primitives remain general-purpose
(no calendar coupling) while the forward-testing layer enforces the stricter
"finalized AND expected" contract.

Architectural rule
------------------
Forward testing must evaluate only bars that are both finalized and expected.
Normal market closure must not be treated as a provider failure.
"""
from datetime import datetime

from backend.market_calendar.base import TradingCalendar
from backend.services.ohlcv_service import is_bar_finalized as _time_is_bar_finalized


def is_bar_expected(
    bar_timestamp: datetime,
    timeframe: str,
    calendar: TradingCalendar,
) -> bool:
    """
    Return True if a bar at *bar_timestamp* is expected to exist given *calendar*.

    Used by ForwardTestService for gap detection: distinguishes between
    - A missing bar caused by market closure → expected absence, not a gap.
    - A missing bar caused by provider failure → unexpected absence, a gap.

    Args:
        bar_timestamp: Candle open-time.  Must be UTC-aware.
        timeframe:     Canonical timeframe string (e.g. "1d", "1h").  Accepted
                       for future extension; some calendars may vary expected-bar
                       logic by timeframe (e.g. intraday session windows).
        calendar:      TradingCalendar governing this session's instrument.

    Returns:
        True if the calendar expects a bar to exist at this timestamp.

    Raises:
        ValueError: if *bar_timestamp* is timezone-naive.
    """
    if bar_timestamp.tzinfo is None:
        raise ValueError("bar_timestamp must be UTC-aware; got naive datetime")
    return calendar.is_bar_expected(bar_timestamp, timeframe)


def is_bar_finalized(
    bar_timestamp: datetime,
    timeframe: str,
    now_utc: datetime,
    calendar: TradingCalendar,
    safety_buffer: int = 60,
) -> bool:
    """
    Return True when a bar is both time-finalized and expected by the calendar.

    A bar is considered finalized in the forward-testing sense only when ALL
    of the following conditions are satisfied:

    1. **Calendar check**: the bar was expected to exist (market was open).
       A Saturday daily equity bar fails this check regardless of time.

    2. **Time check**: the candle period + safety_buffer has fully elapsed.
       ``current_time >= bar_open + timeframe_duration + safety_buffer``

    This combined check prevents two failure classes:
    - Forming candles being evaluated (time guard, Phase 4C.3 invariant).
    - Normal market closure being treated as a provider failure (calendar guard).

    Wraps ``ohlcv_service.is_bar_finalized`` for the time check; adds the
    calendar layer on top.  The two functions are not redundant — the
    ohlcv_service primitive is the correct general-purpose helper for
    historical research workflows that have no calendar context.

    Args:
        bar_timestamp: Candle open-time.  Must be UTC-aware.
        timeframe:     Canonical timeframe string (e.g. "1d", "1h").
        now_utc:       Reference "now".  Must be UTC-aware.
        calendar:      TradingCalendar governing this session's instrument.
        safety_buffer: Seconds added after candle close before the bar is
                       considered finalized.  Default 60.
                       Pass ``settings.forward_test_bar_finalization_buffer_seconds``
                       in production code.

    Returns:
        True if the bar is both expected by the calendar and time-finalized.
        False if the bar is not expected (market closure) OR still forming.

    Raises:
        ValueError: if *bar_timestamp* or *now_utc* is timezone-naive.
        ValueError: if *timeframe* is not in the canonical QuantLab set.
    """
    if not is_bar_expected(bar_timestamp, timeframe, calendar):
        return False
    return _time_is_bar_finalized(
        bar_timestamp,
        timeframe,
        current_time=now_utc,
        buffer_seconds=safety_buffer,
    )
