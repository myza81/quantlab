# Backtest Cost Model Foundation — Phase 2P.7

## Overview

Phase 2P.7 adds deterministic commission and slippage modeling to the backtest simulation layer established in Phase 2P.6. All cost behavior is explicit, configurable, and reproducible — no randomness, no stochastic fills, no order book simulation.

---

## Deterministic Cost Philosophy

Transaction costs in QuantLab backtesting are:

- **Explicit** — every cost is declared in config and recorded in `TradeCostBreakdown`
- **Deterministic** — identical inputs always produce identical cost outputs
- **Auditable** — each simulated trade carries a full per-trade cost breakdown
- **Isolated** — no broker concepts, no exchange IDs, no latency modeling

This is still deterministic simulation, NOT execution realism.

---

## Supported Commission Models

### NONE (default)
```
commission = 0
```

### FIXED
Flat monetary amount per trade, regardless of quantity or notional.
```
commission = commission_value  (e.g. $1.50 per trade)
```

### PERCENTAGE
Fraction of the trade notional (quantity × adjusted_price).
```
commission = quantity × adjusted_price × commission_value  (e.g. 0.1% → 0.001)
```

**Not supported:**
- Tiered exchange fees
- Maker/taker models
- Borrowing fees
- Overnight financing charges

---

## Supported Slippage Models

### NONE (default)
```
execution_price = bar_close  (exact close, no adjustment)
```

### FIXED
Fixed monetary amount per share, applied adversely to direction.
```
slippage_per_unit = slippage_value  (e.g. $0.05 per share)
```

### PERCENTAGE
Percentage of bar close, applied adversely to direction.
```
slippage_per_unit = bar_close × slippage_value  (e.g. 0.1% → 0.001)
```

**Not supported:**
- Stochastic slippage
- Volume-based impact
- Order book depth

---

## Execution Price Adjustment Rules

Slippage is applied **deterministically** and **direction-aware**:

```
open_long:   adjusted_price = close + slippage_per_unit   (buyer pays more)
close_long:  adjusted_price = close - slippage_per_unit   (seller receives less)
```

The adjusted price is used for:
- Cash deduction/addition
- Entry price stored in `PositionState.average_entry_price`
- `SimulatedTrade.price` field
- Commission computation (notional = qty × adjusted_price)

Unrealized PnL uses raw bar close (no hypothetical exit cost applied — position not closed yet).

---

## Per-Trade Cost Breakdown

Every `SimulatedTrade` carries a `TradeCostBreakdown`:

| Field | Meaning |
|-------|---------|
| `raw_price` | Bar close before slippage |
| `adjusted_price` | Execution price after slippage |
| `gross_value` | `quantity × adjusted_price` |
| `commission_paid` | Commission for this trade |
| `slippage_paid` | `abs(adjusted_price - raw_price) × quantity` |
| `total_cost` | `commission_paid + slippage_paid` |
| `net_cash_impact` | Signed cash impact (negative for opens, positive for closes) |

---

## Realized PnL Definition

Phase 2P.7 defines `realized_pnl` as **all-in net PnL**, including all costs from both sides of the trade:

```
realized_pnl = (adjusted_close_price - avg_entry_price) × quantity
               - commission_close
               - commission_open (stored at entry)
```

This gives a true economic P&L that accounts for:
- Entry slippage (captured in `avg_entry_price`)
- Exit slippage (captured in `adjusted_close_price`)
- Both commissions

---

## Configuration

Extend `BacktestSimulationConfig` with cost fields (all default to zero-cost):

```python
BacktestSimulationConfig(
    initial_cash=10_000.0,
    fixed_quantity=1.0,
    commission_mode=CommissionMode.FIXED,    # or NONE / PERCENTAGE
    commission_value=1.50,                   # $1.50 per trade
    slippage_mode=SlippageMode.PERCENTAGE,   # or NONE / FIXED
    slippage_value=0.001,                    # 0.1% of close
)
```

Backward compatibility: all cost fields default to NONE/0.0 — Phase 2P.6 behavior is preserved when no cost config is provided.

---

## Aggregate Cost Summary

`BacktestSimulationSummary` now includes:

| Field | Meaning |
|-------|---------|
| `total_commission_paid` | Sum of all commission across trades |
| `total_slippage_paid` | Sum of all slippage across trades |
| `total_cost_paid` | `total_commission_paid + total_slippage_paid` |
| `average_cost_per_trade` | `total_cost_paid / total_trades` (0.0 if no trades) |

---

## Insufficient Cash Handling

With costs enabled, the insufficient-cash check uses the **all-in cost**:

```
total_cash_required = qty × adjusted_open_price + commission
if total_cash_required > cash → reject with INSUFFICIENT_CASH
```

This prevents silent position opening that would result in negative cash.

---

## API

The existing `POST /backtests/simulate` endpoint accepts the extended config:

```json
{
  "intent_batch": { ... },
  "price_bars": [...],
  "config": {
    "initial_cash": 10000.0,
    "fixed_quantity": 1.0,
    "commission_mode": "fixed",
    "commission_value": 1.50,
    "slippage_mode": "percentage",
    "slippage_value": 0.001
  }
}
```

No new endpoint required.

---

## Modules

| Module | Responsibility |
|--------|---------------|
| `backend/backtesting/cost_model.py` | Enums, `TradeCostBreakdown`, computation helpers |
| `backend/backtesting/models.py` | Extended `BacktestSimulationConfig`, `SimulatedTrade`, `BacktestSimulationSummary` |
| `backend/backtesting/position_tracker.py` | Cost-aware open/close logic, `entry_commission` tracking |
| `backend/backtesting/simulator.py` | Cost config propagation to `PositionState`, cost aggregate in summary |

---

## What Is NOT Implemented

| Feature | Status |
|---------|--------|
| Stochastic/random slippage | Not implemented |
| Latency modeling | Not implemented |
| Order book simulation | Not implemented |
| Partial fills | Not implemented |
| Market impact | Not implemented |
| Tiered/maker-taker fees | Not implemented |
| Multi-asset portfolio | Not implemented |
| Leverage / margin | Not implemented |
| Short selling | Not implemented |

---

## Architecture Boundary

All Phase 2P.7 modules MUST NOT import from:

- `backend.strategy_runtime`
- `backend.execution`
- `backend.forward_testing`

No broker concepts, no exchange IDs, no routing logic.

---

## Future Extension Path

```
Deterministic cost model (Phase 2P.7 — this layer)
→ Percentage position sizing (future)
  → quantity = floor(capital_fraction × equity / adjusted_price)
→ Multi-asset portfolio (future)
  → per-instrument positions + correlation tracking
→ Advanced analytics (future)
  → Sharpe ratio, drawdown series, CAGR, volatility
→ Compliance Policy Layer (future)
  → halal screening, risk limits, exposure limits
→ ExecutionPolicy Layer (future)
  → interpret intents into compliant order candidates
```
