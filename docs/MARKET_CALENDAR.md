# MARKET_CALENDAR.md

## Purpose

This document describes the minimal market calendar and session finalization policy introduced in Phase 4C.3A.

The market calendar determines whether market activity is expected at a given UTC timestamp.  It is the mechanism by which QuantLab's forward testing subsystem distinguishes between:

- **Market closure** — expected absence of a bar (weekend, holiday, exchange closure).  Not a provider failure.  Not a data gap.
- **Provider failure or data gap** — unexpected absence of a bar that the exchange calendar expected to exist.

Without a market calendar, `ForwardTestService` would incorrectly treat every Saturday daily bar absence as a provider failure or data gap.

---

## Architectural Rule

> Forward testing must evaluate only bars that are both **finalized** and **expected**.
>
> Normal market closure must not be treated as provider failure.

This rule is enforced by `market_calendar.policy.is_bar_finalized()`, which gates on both:
1. The candle period + safety buffer has elapsed (time check — Phase 4C.3 invariant).
2. The calendar expected the bar to exist (calendar check — Phase 4C.3A invariant).

---

## 1. TradingCalendar Abstraction

`TradingCalendar` is the abstract base class for all market calendars.

```
backend/market_calendar/base.py
```

### Responsibilities

- Determine whether a market session is expected at a given UTC datetime.
- Determine whether a bar should exist at a given timestamp and timeframe.
- Distinguish market-closed periods from possible provider failure.

### Interface

```python
class TradingCalendar(ABC):
    def is_session_open(self, dt: datetime) -> bool: ...
    def is_bar_expected(self, bar_timestamp: datetime, timeframe: str) -> bool: ...
```

Both methods:
- Accept only UTC-aware datetimes; raise `ValueError` for naive inputs.
- Have no I/O dependencies; no database or network access.

### Extension

To add a new calendar type, subclass `TradingCalendar` and implement both abstract methods.  The calendar must be UTC-pure.

---

## 2. Built-in Calendar Types

```
backend/market_calendar/calendars.py
```

### TwentyFourSevenCalendar

For crypto and always-open markets.

- Every timestamp on every day of the week is an expected trading period.
- Weekends, holidays, and closures do not apply.
- `is_session_open()` always returns `True`.
- `is_bar_expected()` always returns `True` for any timeframe.

Applicable instruments: `BTC-USD`, `ETH-USD`, and any asset that trades continuously.

### WeekdayMarketCalendar

For Monday–Friday equity and ETF markets.

- Saturdays and Sundays are not expected trading days.
- `is_session_open()` returns `True` Monday–Friday, `False` Saturday–Sunday.
- `is_bar_expected()` returns `True` Monday–Friday, `False` Saturday–Sunday.
- Weekday determination uses `datetime.weekday()`: 0=Monday … 4=Friday, 5=Saturday, 6=Sunday.

**Deferred**: holiday database (NYSE, LSE, Bursa, etc.), intraday session windows (e.g. 09:30–16:00 NYSE), half-day closures.

Applicable instruments: `AAPL`, `MSFT`, `SPY`, and standard equity/ETF instruments.

### DefaultCalendar

Conservative fallback for unknown or unclassified asset classes.

- Behaves identically to `WeekdayMarketCalendar`: Monday–Friday sessions, weekends excluded.
- Errs on the side of caution: does not assume 24/7 availability for unrecognized asset classes.

Used by `get_calendar()` when no explicit mapping exists.

---

## 3. Calendar Registry

```
backend/market_calendar/registry.py
```

### get_calendar()

Resolves a `TradingCalendar` from market context.

```python
get_calendar(
    asset_class: str = "unknown",
    *,
    provider_name: str = "",
    exchange: str = "",
    symbol: str = "",
) -> TradingCalendar
```

**Resolution policy (current)**:

| Asset class | Calendar |
|---|---|
| `crypto`, `digital_asset`, `cryptocurrency`, `coin` | `TwentyFourSevenCalendar` |
| `equity`, `stock`, `etf`, `fund`, `equity_etf`, `reit` | `WeekdayMarketCalendar` |
| All other values (including `"unknown"` and empty string) | `DefaultCalendar` |

- `asset_class` matching is case-insensitive and whitespace-trimmed.
- `provider_name`, `exchange`, `symbol` are accepted for forward compatibility but are not yet used in routing decisions.

### Example usage

```python
from backend.market_calendar import get_calendar

cal = get_calendar("crypto")                         # TwentyFourSevenCalendar
cal = get_calendar("equity", exchange="NASDAQ")      # WeekdayMarketCalendar
cal = get_calendar()                                 # DefaultCalendar (unknown)
```

---

## 4. Bar Finalization Policy

```
backend/market_calendar/policy.py
```

### is_bar_expected()

```python
is_bar_expected(
    bar_timestamp: datetime,
    timeframe: str,
    calendar: TradingCalendar,
) -> bool
```

Returns `True` if the calendar expects a bar to exist at `bar_timestamp`.

**Primary use**: gap detection in `ForwardTestService`.

- If `is_bar_expected()` returns `False`: the absent bar is a normal closure — do not record a gap or provider failure.
- If `is_bar_expected()` returns `True` but the bar is absent: record a gap event.

### is_bar_finalized()

```python
is_bar_finalized(
    bar_timestamp: datetime,
    timeframe: str,
    now_utc: datetime,
    calendar: TradingCalendar,
    safety_buffer: int = 60,
) -> bool
```

Returns `True` when a bar is **both time-finalized and expected by the calendar**.

Evaluation order:
1. Calendar check: `calendar.is_bar_expected(bar_timestamp, timeframe)` — if `False`, returns `False` immediately.
2. Time check: delegates to `ohlcv_service.is_bar_finalized()` — returns `True` only when `now_utc >= bar_timestamp + timeframe_duration + safety_buffer`.

**Primary use**: bar processing gate in `ForwardTestService`.

**Relationship to Phase 4C.3**:

`ohlcv_service.is_bar_finalized()` is the time-only primitive introduced in Phase 4C.3.  It has no calendar context and is the correct general-purpose helper for historical research workflows.

`market_calendar.policy.is_bar_finalized()` wraps the Phase 4C.3 primitive and adds the calendar guard.  It is the correct helper for forward testing, where "finalized" means both time-elapsed and market-expected.

---

## 5. UTC Timezone Policy

All calendar logic is UTC-only.

- Every `datetime` argument must be UTC-aware (carry `tzinfo`).
- Naive datetimes (no `tzinfo`) are rejected with `ValueError`.
- No user local timezone is used in any calendar, policy, or registry function.
- User timezone is display-only; it must never affect bar finalization or expected-bar determination.

**Example**: a daily equity bar at `2026-05-29T00:00:00Z` (UTC Friday) is an expected trading day because `weekday() == 4`.  Whether the user is in UTC+8, UTC-5, or UTC is irrelevant to this determination.

---

## 6. Current Limitations

The following are intentionally not implemented in Phase 4C.3A.  They are deferred to future phases.

| Limitation | Deferred to |
|---|---|
| Exchange-specific holiday databases (NYSE, LSE, Bursa, SGX) | Future calendar phase |
| Intraday session window enforcement (e.g. 09:30–16:00 NYSE) | Future calendar phase |
| Half-day / early-close modeling | Future calendar phase |
| Futures market hours and settlement windows | Future calendar phase |
| Exchange-specific weekend trading (some crypto venues) | Future calendar phase |
| Holiday feeds / external calendar data sources | Future calendar phase |

The `provider_name`, `exchange`, and `symbol` parameters in `get_calendar()` are reserved for future exchange-specific routing.  They are accepted now but have no effect on resolution.

---

## 7. Future Expansion Path

When a more specific calendar is needed (e.g. NYSE with holidays, Bursa Malaysia with specific settlement windows):

1. Create a new subclass of `TradingCalendar` (e.g. `NYSECalendar`, `BursaMalaysiaCalendar`).
2. Add the holiday logic to `is_bar_expected()` and `is_session_open()`.
3. Register the new calendar in `registry.py` using `exchange=` or `symbol=` routing in `get_calendar()`.
4. No changes to `is_bar_finalized()` or `is_bar_expected()` in `policy.py` — the calendar abstraction handles it.

Strategy logic must never import from `backend.market_calendar`.  Calendar resolution belongs in the forward testing service layer or data service layer only.

---

## 8. Package Structure

```
backend/market_calendar/
    __init__.py      — public exports
    base.py          — TradingCalendar ABC
    calendars.py     — TwentyFourSevenCalendar, WeekdayMarketCalendar, DefaultCalendar
    registry.py      — get_calendar() resolver
    policy.py        — is_bar_expected(), is_bar_finalized() (calendar-aware)
```

---

## 9. Import Constraints

The market calendar package:

- May import from `backend.services.ohlcv_service` (for time-check delegation).
- May import from `backend.core.config` (for settings).
- Must NOT import from `strategy_runtime`, `execution`, `backtesting`, `api`, `data_providers`, or any frontend module.

Strategy logic must NOT import from `backend.market_calendar`.

---

## 10. Phase Summary

| Phase | Contribution |
|---|---|
| 4C.3 | `is_bar_finalized()` (time-only), `timeframe_to_timedelta()`, `get_recent_bars()`, `get_bars_since()` |
| 4C.3A | `TradingCalendar`, built-in calendars, `get_calendar()` registry, `is_bar_expected()`, `is_bar_finalized()` (calendar-aware) |
| 4C.4 (next) | `ForwardTestService` consumes both 4C.3 and 4C.3A primitives |
