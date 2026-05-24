# Backtest Position Sizing — Phase 2P.8

## Overview

Phase 2P.8 extends the backtest simulator from fixed-quantity sizing to support equity-fraction sizing. Both modes are deterministic and long-only. No leverage, no margin, no multiple simultaneous positions.

---

## Supported Sizing Modes

### FIXED_QUANTITY (default)

```
quantity = fixed_quantity  (constant, e.g. 1.0 share per trade)
```

The same unit count is used for every open trade, regardless of current equity. This is the Phase 2P.6 / 2P.7 baseline and remains the default. All prior behavior is preserved.

### EQUITY_FRACTION

```
available_budget = current_equity × equity_fraction
quantity = floor(available_budget / adjusted_entry_price)
```

Where:
- `current_equity = cash` (position is always flat at open time — no unrealized PnL possible)
- `adjusted_entry_price = bar_close + slippage` (slippage-adjusted entry price)
- `floor()` ensures whole-unit positions — no fractional shares

**No leverage** — `equity_fraction` is constrained to `(0, 1]`. A value of `1.0` allocates the entire equity. Values above `1.0` are rejected at configuration time.

---

## Quantity Formula

```
For EQUITY_FRACTION:
    budget = equity × equity_fraction
    quantity = floor(budget / adjusted_entry_price)

For FIXED_QUANTITY:
    quantity = fixed_quantity
```

The `resolve_position_quantity()` function in `backend/backtesting/position_tracker.py` implements this formula deterministically.

---

## Cost-Aware Cash Sufficiency

Opening a position must satisfy:

```
total_cash_out = quantity × adjusted_entry_price + commission
if total_cash_out > cash → reject with INSUFFICIENT_CASH
```

The quantity is resolved first, then the full all-in cost (slippage + commission) is checked. If the cost check fails after sizing, the position is rejected with `INSUFFICIENT_CASH`.

---

## Rejection Reasons

| Reason | Condition |
|--------|-----------|
| `ALREADY_LONG` | open_long while position is held |
| `ALREADY_FLAT` | close_long while no position held |
| `ZERO_QUANTITY` | equity_fraction sizing resolved to 0 units (budget < price) |
| `INSUFFICIENT_CASH` | quantity × adjusted_price + commission > cash |
| `MISSING_PRICE` | no price bar for the intent's bar_index |
| `UNSUPPORTED_ACTION` | action not handled by long-only tracker |

`ZERO_QUANTITY` is specific to `EQUITY_FRACTION` mode. It occurs when the allocated budget cannot afford even one unit at the current (slippage-adjusted) price.

---

## Audit Fields on SimulatedTrade

Every `SimulatedTrade` now carries sizing traceability:

| Field | Meaning |
|-------|---------|
| `position_size_mode` | The sizing mode used for this trade |
| `sizing_value` | The configured sizing parameter |
| `quantity` | The resolved (actual) units traded |

For `FIXED_QUANTITY`: `sizing_value = fixed_quantity` (e.g., `5.0`)
For `EQUITY_FRACTION`: `sizing_value = equity_fraction` (e.g., `0.25`)

This allows post-hoc audit of exactly how each trade quantity was determined.

---

## Configuration

```python
# Fixed quantity (default — backward-compatible)
BacktestSimulationConfig(
    initial_cash=10_000.0,
    fixed_quantity=5.0,
)

# Equity fraction — allocate 25% of equity per trade
BacktestSimulationConfig(
    initial_cash=10_000.0,
    position_size_mode=PositionSizeMode.EQUITY_FRACTION,
    equity_fraction=0.25,
)

# Equity fraction with cost model
BacktestSimulationConfig(
    initial_cash=10_000.0,
    position_size_mode=PositionSizeMode.EQUITY_FRACTION,
    equity_fraction=0.5,
    commission_mode=CommissionMode.FIXED,
    commission_value=1.50,
    slippage_mode=SlippageMode.PERCENTAGE,
    slippage_value=0.001,
)
```

---

## Equity Compounding

With `EQUITY_FRACTION`, the position size adapts to current cash after each trade:

- After a profitable close: `cash` increases → next budget is larger → more units can be opened
- After a losing close: `cash` decreases → next budget is smaller → fewer units

This is automatic — the quantity is computed fresh at each open using the current cash at that point in the simulation. The equity curve therefore reflects compounding effects across the simulation period.

---

## Constraints

| Constraint | Enforcement |
|------------|-------------|
| No leverage | `equity_fraction` validated ≤ 1.0 at config time |
| No margin | No borrowed funds; cash must cover full cost |
| No short selling | Only `OPEN_LONG` and `CLOSE_LONG` actions supported |
| Single position | `ALREADY_LONG` rejection prevents pyramiding |
| Single instrument | One position tracker per simulation run |
| Deterministic | Identical config + bars + intents → identical result |

---

## Modules

| Module | Responsibility |
|--------|---------------|
| `backend/backtesting/models.py` | `PositionSizeMode`, extended `BacktestSimulationConfig`, `SimulatedTrade` audit fields, `ZERO_QUANTITY` rejection reason |
| `backend/backtesting/position_tracker.py` | `resolve_position_quantity()`, extended `PositionState`, updated `_open_long()` |
| `backend/backtesting/simulator.py` | Passes `position_size_mode` + `equity_fraction` to `PositionState` |

---

## What Is NOT Implemented

| Feature | Status |
|---------|--------|
| Risk-per-trade sizing | Not implemented |
| Stop-loss based sizing | Not implemented |
| Volatility targeting | Not implemented |
| Kelly criterion | Not implemented |
| Portfolio allocation | Not implemented |
| Compounding with reinvestment rules | Not implemented |
| Leverage / margin | Not implemented |
| Short selling | Not implemented |
| Multiple simultaneous positions | Not implemented |

---

## Architecture Boundary

All Phase 2P.8 modules MUST NOT import from:

- `backend.strategy_runtime`
- `backend.execution`
- `backend.forward_testing`

No broker concepts. No order routing. No compliance decisions. Sizing is a simulation-internal concern only.

---

## Future Extension Path

```
Equity-fraction sizing (Phase 2P.8 — this layer)
→ Advanced analytics (future)
  → Sharpe ratio, max drawdown, CAGR, volatility
→ Compliance Policy Layer (future)
  → halal screening, risk limits, exposure limits
→ Multi-asset portfolio (future)
  → per-instrument positions, allocation across instruments
→ ExecutionPolicy Layer (future)
  → interpret intents into compliant order candidates
```
