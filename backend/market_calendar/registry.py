"""
Market calendar registry — resolves market context to a TradingCalendar.

Current resolution policy:
    crypto / digital_asset / cryptocurrency / coin
        → TwentyFourSevenCalendar

    equity / stock / etf / fund / equity_etf / reit
        → WeekdayMarketCalendar

    anything else (unknown, unrecognized)
        → DefaultCalendar  (conservative: weekday-only)

Exchange-specific calendars (NYSE, LSE, Bursa, NYMEX) are deferred.
The ``provider_name``, ``exchange``, and ``symbol`` parameters are accepted
for forward compatibility but are not yet used in routing decisions.
See docs/MARKET_CALENDAR.md §5 for the planned expansion path.
"""
from backend.market_calendar.base import TradingCalendar
from backend.market_calendar.calendars import (
    DefaultCalendar,
    TwentyFourSevenCalendar,
    WeekdayMarketCalendar,
)

_CRYPTO_CLASSES: frozenset[str] = frozenset({
    "crypto",
    "digital_asset",
    "cryptocurrency",
    "coin",
})

_EQUITY_CLASSES: frozenset[str] = frozenset({
    "equity",
    "stock",
    "etf",
    "fund",
    "equity_etf",
    "reit",
})


def get_calendar(
    asset_class: str = "unknown",
    *,
    provider_name: str = "",
    exchange: str = "",
    symbol: str = "",
) -> TradingCalendar:
    """
    Resolve a TradingCalendar for the given market context.

    Resolution is asset_class-first.  Future versions will layer in
    exchange-specific and provider-specific overrides using the reserved
    parameters.

    Resolution priority:
    1. ``asset_class`` in crypto set  → TwentyFourSevenCalendar
    2. ``asset_class`` in equity set  → WeekdayMarketCalendar
    3. Fallback                       → DefaultCalendar (weekday-only, conservative)

    Asset class matching is case-insensitive and ignores leading/trailing
    whitespace.

    Args:
        asset_class:   Instrument asset class (e.g. "crypto", "equity", "etf").
                       Defaults to "unknown" → DefaultCalendar fallback.
        provider_name: Data provider name (e.g. "yahoo", "polygon").
                       Reserved for future exchange-specific routing.
        exchange:      Exchange/venue name (e.g. "NASDAQ", "NYSE", "Bursa").
                       Reserved for future exchange-specific routing.
        symbol:        Instrument symbol (e.g. "AAPL", "BTC-USD").
                       Reserved for future symbol-specific overrides.

    Returns:
        A TradingCalendar appropriate for the given market context.
    """
    normalized = asset_class.strip().lower()
    if normalized in _CRYPTO_CLASSES:
        return TwentyFourSevenCalendar()
    if normalized in _EQUITY_CLASSES:
        return WeekdayMarketCalendar()
    return DefaultCalendar()
