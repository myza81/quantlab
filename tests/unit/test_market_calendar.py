"""
Phase 4C.3A — Market Calendar & Session Finalization Policy tests.

Coverage:
- TwentyFourSevenCalendar: all timestamps expected, weekends included
- WeekdayMarketCalendar: weekdays expected, weekends excluded
- DefaultCalendar: conservative (same as WeekdayMarketCalendar)
- get_calendar(): asset_class routing
- is_bar_expected(): calendar dispatch, UTC enforcement
- is_bar_finalized(): combined time + calendar check, safety buffer
- UTC enforcement: naive datetime rejection throughout
- No false gap on weekend equity market closure (architectural rule)
"""
import pytest
from datetime import datetime, timezone, timedelta

from backend.market_calendar import (
    DefaultCalendar,
    TradingCalendar,
    TwentyFourSevenCalendar,
    WeekdayMarketCalendar,
    get_calendar,
    is_bar_expected,
    is_bar_finalized,
)

# ---------------------------------------------------------------------------
# Reference timestamps — all UTC-aware
# ---------------------------------------------------------------------------
# 2026-05-25 = Monday     (.weekday() == 0)
# 2026-05-26 = Tuesday    (.weekday() == 1)
# 2026-05-29 = Friday     (.weekday() == 4)
# 2026-05-30 = Saturday   (.weekday() == 5)
# 2026-05-31 = Sunday     (.weekday() == 6)

_UTC = timezone.utc

MONDAY    = datetime(2026, 5, 25, 0, 0, 0, tzinfo=_UTC)
TUESDAY   = datetime(2026, 5, 26, 0, 0, 0, tzinfo=_UTC)
FRIDAY    = datetime(2026, 5, 29, 0, 0, 0, tzinfo=_UTC)
SATURDAY  = datetime(2026, 5, 30, 0, 0, 0, tzinfo=_UTC)
SUNDAY    = datetime(2026, 5, 31, 0, 0, 0, tzinfo=_UTC)

SATURDAY_NOON  = datetime(2026, 5, 30, 12, 0, 0, tzinfo=_UTC)
MONDAY_MIDDAY  = datetime(2026, 5, 25, 14, 30, 0, tzinfo=_UTC)

NAIVE = datetime(2026, 5, 30, 0, 0, 0)  # no tzinfo


# ============================================================================
# TwentyFourSevenCalendar
# ============================================================================

class TestTwentyFourSevenCalendar:

    def setup_method(self):
        self.cal = TwentyFourSevenCalendar()

    def test_is_trading_calendar_subclass(self):
        assert isinstance(self.cal, TradingCalendar)

    def test_weekend_daily_bar_is_expected(self):
        assert self.cal.is_bar_expected(SATURDAY, "1d") is True

    def test_sunday_daily_bar_is_expected(self):
        assert self.cal.is_bar_expected(SUNDAY, "1d") is True

    def test_weekday_daily_bar_is_expected(self):
        assert self.cal.is_bar_expected(MONDAY, "1d") is True

    def test_saturday_intraday_bar_is_expected(self):
        assert self.cal.is_bar_expected(SATURDAY_NOON, "1h") is True

    def test_session_open_on_saturday(self):
        assert self.cal.is_session_open(SATURDAY) is True

    def test_session_open_on_sunday(self):
        assert self.cal.is_session_open(SUNDAY) is True

    def test_session_open_on_monday(self):
        assert self.cal.is_session_open(MONDAY) is True

    def test_naive_bar_timestamp_raises(self):
        with pytest.raises(ValueError, match="UTC-aware"):
            self.cal.is_bar_expected(NAIVE, "1d")

    def test_naive_session_raises(self):
        with pytest.raises(ValueError, match="UTC-aware"):
            self.cal.is_session_open(NAIVE)


# ============================================================================
# WeekdayMarketCalendar
# ============================================================================

class TestWeekdayMarketCalendar:

    def setup_method(self):
        self.cal = WeekdayMarketCalendar()

    def test_is_trading_calendar_subclass(self):
        assert isinstance(self.cal, TradingCalendar)

    def test_monday_bar_is_expected(self):
        assert self.cal.is_bar_expected(MONDAY, "1d") is True

    def test_tuesday_bar_is_expected(self):
        assert self.cal.is_bar_expected(TUESDAY, "1d") is True

    def test_friday_bar_is_expected(self):
        assert self.cal.is_bar_expected(FRIDAY, "1d") is True

    def test_saturday_bar_is_not_expected(self):
        assert self.cal.is_bar_expected(SATURDAY, "1d") is False

    def test_sunday_bar_is_not_expected(self):
        assert self.cal.is_bar_expected(SUNDAY, "1d") is False

    def test_saturday_intraday_bar_not_expected(self):
        assert self.cal.is_bar_expected(SATURDAY_NOON, "1h") is False

    def test_monday_intraday_bar_expected(self):
        assert self.cal.is_bar_expected(MONDAY_MIDDAY, "1h") is True

    def test_session_open_on_monday(self):
        assert self.cal.is_session_open(MONDAY) is True

    def test_session_open_on_friday(self):
        assert self.cal.is_session_open(FRIDAY) is True

    def test_session_closed_on_saturday(self):
        assert self.cal.is_session_open(SATURDAY) is False

    def test_session_closed_on_sunday(self):
        assert self.cal.is_session_open(SUNDAY) is False

    def test_naive_bar_timestamp_raises(self):
        with pytest.raises(ValueError, match="UTC-aware"):
            self.cal.is_bar_expected(NAIVE, "1d")

    def test_naive_session_raises(self):
        with pytest.raises(ValueError, match="UTC-aware"):
            self.cal.is_session_open(NAIVE)


# ============================================================================
# DefaultCalendar — must behave identically to WeekdayMarketCalendar
# ============================================================================

class TestDefaultCalendar:

    def setup_method(self):
        self.cal = DefaultCalendar()

    def test_is_weekday_market_calendar_subclass(self):
        assert isinstance(self.cal, WeekdayMarketCalendar)

    def test_weekday_bar_expected(self):
        assert self.cal.is_bar_expected(MONDAY, "1d") is True
        assert self.cal.is_bar_expected(FRIDAY, "1d") is True

    def test_weekend_bar_not_expected(self):
        assert self.cal.is_bar_expected(SATURDAY, "1d") is False
        assert self.cal.is_bar_expected(SUNDAY, "1d") is False

    def test_session_closed_on_weekend(self):
        assert self.cal.is_session_open(SATURDAY) is False
        assert self.cal.is_session_open(SUNDAY) is False


# ============================================================================
# Calendar registry — get_calendar()
# ============================================================================

class TestGetCalendar:

    def test_crypto_returns_twentyfourseven(self):
        assert isinstance(get_calendar("crypto"), TwentyFourSevenCalendar)

    def test_digital_asset_returns_twentyfourseven(self):
        assert isinstance(get_calendar("digital_asset"), TwentyFourSevenCalendar)

    def test_cryptocurrency_returns_twentyfourseven(self):
        assert isinstance(get_calendar("cryptocurrency"), TwentyFourSevenCalendar)

    def test_equity_returns_weekday(self):
        assert isinstance(get_calendar("equity"), WeekdayMarketCalendar)

    def test_stock_returns_weekday(self):
        assert isinstance(get_calendar("stock"), WeekdayMarketCalendar)

    def test_etf_returns_weekday(self):
        assert isinstance(get_calendar("etf"), WeekdayMarketCalendar)

    def test_fund_returns_weekday(self):
        assert isinstance(get_calendar("fund"), WeekdayMarketCalendar)

    def test_unknown_returns_default_calendar(self):
        cal = get_calendar("unknown")
        assert isinstance(cal, DefaultCalendar)

    def test_empty_string_returns_default_calendar(self):
        cal = get_calendar("")
        assert isinstance(cal, DefaultCalendar)

    def test_no_args_returns_default_calendar(self):
        cal = get_calendar()
        assert isinstance(cal, DefaultCalendar)

    def test_asset_class_case_insensitive_crypto(self):
        assert isinstance(get_calendar("CRYPTO"), TwentyFourSevenCalendar)
        assert isinstance(get_calendar("Crypto"), TwentyFourSevenCalendar)

    def test_asset_class_case_insensitive_equity(self):
        assert isinstance(get_calendar("Equity"), WeekdayMarketCalendar)
        assert isinstance(get_calendar("EQUITY"), WeekdayMarketCalendar)

    def test_unknown_asset_does_not_expect_weekend(self):
        """DefaultCalendar conservatively excludes weekends for unknown assets."""
        cal = get_calendar("exotic_derivatives")
        assert cal.is_bar_expected(SATURDAY, "1d") is False

    def test_reserved_params_accepted_without_error(self):
        """provider_name, exchange, symbol are reserved; must not raise."""
        cal = get_calendar(
            "equity",
            provider_name="yahoo",
            exchange="NASDAQ",
            symbol="AAPL",
        )
        assert isinstance(cal, WeekdayMarketCalendar)


# ============================================================================
# is_bar_expected() — module-level function
# ============================================================================

class TestIsBarExpected:

    def test_crypto_saturday_expected(self):
        cal = TwentyFourSevenCalendar()
        assert is_bar_expected(SATURDAY, "1d", cal) is True

    def test_equity_saturday_not_expected(self):
        cal = WeekdayMarketCalendar()
        assert is_bar_expected(SATURDAY, "1d", cal) is False

    def test_equity_monday_expected(self):
        cal = WeekdayMarketCalendar()
        assert is_bar_expected(MONDAY, "1d", cal) is True

    def test_default_weekend_not_expected(self):
        cal = DefaultCalendar()
        assert is_bar_expected(SATURDAY, "1d", cal) is False

    def test_naive_timestamp_raises(self):
        cal = WeekdayMarketCalendar()
        with pytest.raises(ValueError, match="UTC-aware"):
            is_bar_expected(NAIVE, "1d", cal)


# ============================================================================
# is_bar_finalized() — calendar-aware version (market_calendar.policy)
# ============================================================================

class TestIsBarFinalizedWithCalendar:
    """
    Tests for calendar-aware is_bar_finalized (market_calendar.policy).

    The time-only is_bar_finalized from Phase 4C.3 (ohlcv_service) is
    tested separately in test_ohlcv_forward_test_extensions.py.
    These tests verify the ADDITIONAL calendar guard layer.
    """

    # ---- equity calendar (weekday) ----------------------------------------

    def test_equity_weekday_bar_finalized_when_time_elapsed(self):
        # Friday daily bar; checked on Monday well past finalization
        bar = FRIDAY
        now = datetime(2026, 6, 1, 10, 0, 0, tzinfo=_UTC)  # Monday
        cal = WeekdayMarketCalendar()
        assert is_bar_finalized(bar, "1d", now, cal, safety_buffer=60) is True

    def test_equity_saturday_bar_not_finalized_regardless_of_time(self):
        """Saturday equity bar: fails calendar check even if time has elapsed."""
        bar = SATURDAY
        now = datetime(2026, 6, 8, 10, 0, 0, tzinfo=_UTC)  # far in the future
        cal = WeekdayMarketCalendar()
        assert is_bar_finalized(bar, "1d", now, cal, safety_buffer=60) is False

    def test_equity_sunday_bar_not_finalized(self):
        bar = SUNDAY
        now = datetime(2026, 6, 8, 10, 0, 0, tzinfo=_UTC)
        cal = WeekdayMarketCalendar()
        assert is_bar_finalized(bar, "1d", now, cal, safety_buffer=60) is False

    def test_equity_forming_candle_not_finalized(self):
        """Time guard: candle period not yet elapsed, equity weekday bar."""
        bar = FRIDAY
        # Closes at 2026-05-30 00:00 UTC; still forming at 2026-05-29 12:00 UTC
        now = datetime(2026, 5, 29, 12, 0, 0, tzinfo=_UTC)
        cal = WeekdayMarketCalendar()
        assert is_bar_finalized(bar, "1d", now, cal, safety_buffer=60) is False

    # ---- crypto calendar (24/7) -------------------------------------------

    def test_crypto_saturday_bar_finalized(self):
        """Crypto Saturday bar: passes calendar check; finalized when period elapsed."""
        bar = SATURDAY  # daily bar opens 2026-05-30 00:00 UTC
        # Closes 2026-05-31 00:00 UTC; with 60s buffer → finalized at 2026-05-31 00:01 UTC
        now = datetime(2026, 5, 31, 0, 2, 0, tzinfo=_UTC)
        cal = TwentyFourSevenCalendar()
        assert is_bar_finalized(bar, "1d", now, cal, safety_buffer=60) is True

    def test_crypto_saturday_bar_forming_not_finalized(self):
        """Forming candle: 24/7 calendar but candle period not yet elapsed."""
        bar = SATURDAY
        now = datetime(2026, 5, 30, 12, 0, 0, tzinfo=_UTC)  # midday, still forming
        cal = TwentyFourSevenCalendar()
        assert is_bar_finalized(bar, "1d", now, cal, safety_buffer=60) is False

    # ---- safety buffer (Phase 4C.3 integration) ---------------------------

    def test_safety_buffer_prevents_finalization_at_exact_close(self):
        """Bar is NOT finalized at exactly candle close time (buffer not yet elapsed)."""
        bar = SATURDAY  # daily, opens 2026-05-30 00:00 UTC
        # Candle closes 2026-05-31 00:00 UTC; 60s buffer → finalized at 2026-05-31 00:01 UTC
        exactly_closed = datetime(2026, 5, 31, 0, 0, 0, tzinfo=_UTC)
        cal = TwentyFourSevenCalendar()
        assert is_bar_finalized(bar, "1d", exactly_closed, cal, safety_buffer=60) is False

    def test_safety_buffer_satisfied_one_second_after(self):
        bar = SATURDAY
        just_after = datetime(2026, 5, 31, 0, 1, 0, tzinfo=_UTC)  # exactly 60s past close
        cal = TwentyFourSevenCalendar()
        assert is_bar_finalized(bar, "1d", just_after, cal, safety_buffer=60) is True

    def test_custom_safety_buffer_respected(self):
        bar = SATURDAY
        cal = TwentyFourSevenCalendar()
        # With 300s buffer, bar finalized at 2026-05-31 00:05 UTC
        not_yet = datetime(2026, 5, 31, 0, 3, 0, tzinfo=_UTC)   # 3 min past close
        now_ok  = datetime(2026, 5, 31, 0, 5, 0, tzinfo=_UTC)   # 5 min past close
        assert is_bar_finalized(bar, "1d", not_yet, cal, safety_buffer=300) is False
        assert is_bar_finalized(bar, "1d", now_ok,  cal, safety_buffer=300) is True

    # ---- UTC enforcement --------------------------------------------------

    def test_naive_bar_timestamp_raises(self):
        cal = WeekdayMarketCalendar()
        now = datetime(2026, 6, 1, 10, 0, 0, tzinfo=_UTC)
        with pytest.raises(ValueError, match="UTC-aware"):
            is_bar_finalized(NAIVE, "1d", now, cal)

    def test_naive_now_utc_raises(self):
        cal = WeekdayMarketCalendar()
        naive_now = datetime(2026, 6, 1, 10, 0, 0)  # no tzinfo
        with pytest.raises(ValueError):
            is_bar_finalized(FRIDAY, "1d", naive_now, cal)

    # ---- architectural rule: no false gap on weekend closure ---------------

    def test_no_false_gap_on_weekend_equity_closure(self):
        """
        Architectural rule: normal market closure must not be treated as a gap.

        If the equity calendar says a bar is NOT expected on Saturday, then
        an absent Saturday bar is a closure event, not a provider failure.
        Verify the full chain: registry → calendar → is_bar_expected.
        """
        cal = get_calendar("equity")
        # Saturday bar is not expected — its absence is closure, not a gap
        assert is_bar_expected(SATURDAY, "1d", cal) is False
        # Consequently, is_bar_finalized also returns False (calendar gate)
        far_future = datetime(2026, 12, 31, 0, 0, 0, tzinfo=_UTC)
        assert is_bar_finalized(SATURDAY, "1d", far_future, cal) is False

    def test_crypto_weekend_bar_expected_and_finalized(self):
        """
        Crypto contrast: Saturday bar IS expected and CAN be finalized.
        """
        cal = get_calendar("crypto")
        assert is_bar_expected(SATURDAY, "1d", cal) is True
        after_finalization = datetime(2026, 5, 31, 0, 2, 0, tzinfo=_UTC)
        assert is_bar_finalized(SATURDAY, "1d", after_finalization, cal) is True
