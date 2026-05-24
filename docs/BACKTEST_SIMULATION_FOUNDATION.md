# Backtest Simulation Foundation — Phase 2P.6

## Overview

Phase 2P.6 introduces the first capital-aware simulation layer in QuantLab.
It consumes a `TradeIntentBatch` and price bars, and produces a deterministic
`BacktestSimulationResult` containing simulated trades, per-bar equity curve,
explicit rejections, and an aggregated summary.

---

## Critical Separations

```
TradeIntent     ≠  Order
TradeIntent     ≠  SimulatedTrade
SimulatedTrade  ≠  BrokerFill
SimulatedTrade  ≠  LiveTrade
BacktestResult  ≠  ExecutionRecord
```

The simulator interprets intents — it does not execute them.

---

## Scope: What Is Implemented

### Long-Only Position Tracking

- Open a long position from flat state (`open_long`)
- Close a long position from long state (`close_long`)
- Single position at a time — no partial positions
- No multiple simultaneous positions

### Fixed Quantity Sizing

- Quantity per trade comes from `BacktestSimulationConfig.fixed_quantity`
- No risk-based sizing, percentage sizing, or dynamic sizing in this phase

### Close-Price Execution Assumption

For this phase:
```
execution_price = bar close
```

No slippage. No bid/ask spread. No latency. No fill engine.

This assumption is explicit, not hidden. Future phases may introduce slippage and fee models.

### Simulated Trades

Each successful position change produces a `SimulatedTrade` record:

| Field | Meaning |
|-------|---------|
| `trade_id` | Deterministic: `"trade:{source_intent_id}"` |
| `source_intent_id` | Full traceability to originating intent |
| `action` | `"open_long"` or `"close_long"` |
| `bar_index` | Bar where this trade was simulated |
| `timestamp` | Bar timestamp if available |
| `quantity` | Fixed quantity from config |
| `price` | Bar close (execution price) |
| `cash_before` | Cash before this trade |
| `cash_after` | Cash after this trade |
| `realized_pnl` | Profit/loss realized on close; `None` for opens |
| `position_after` | Quantity held after this trade |

**Forbidden fields** — never present:
- broker, order_id, fill_id, exchange, routing, market_order, limit_order

### Equity Curve

One `BacktestEquityPoint` is produced per price bar regardless of whether
any intents occurred on that bar:

| Field | Meaning |
|-------|---------|
| `bar_index` | Bar index |
| `timestamp` | Bar timestamp if available |
| `cash` | Cash balance at end of this bar |
| `position_quantity` | Units held |
| `market_value` | `position_quantity × bar_close` |
| `realized_pnl` | Cumulative realized PnL (all closed trades) |
| `unrealized_pnl` | Paper gain/loss on open position |
| `equity` | `cash + market_value` |

### Explicit Rejection Handling

Invalid intent actions are rejected explicitly and never silently ignored.
Rejections are tracked in `BacktestSimulationResult.rejections`.

| Reason | Trigger |
|--------|---------|
| `already_long` | `open_long` while position already open |
| `already_flat` | `close_long` while no position open |
| `insufficient_cash` | Cost exceeds available cash |
| `missing_price` | No price bar for intent's `bar_index` |
| `unsupported_action` | Action not handled by long-only tracker |

### Summary

`BacktestSimulationSummary` provides basic aggregated statistics:
- Total bars, trades, rejections
- Initial and final cash and equity
- Total realized and final unrealized PnL
- Peak and trough equity (simple, not time-weighted)

---

## Scope: What Is NOT Implemented

| Feature | Status |
|---------|--------|
| Short selling | Not implemented — halal compatibility |
| Leverage | Not implemented |
| Margin | Not implemented |
| Slippage | Not implemented |
| Fees / commissions | Not implemented |
| Multi-asset portfolio | Not implemented |
| Percentage position sizing | Not implemented |
| Risk-based sizing | Not implemented |
| Drawdown series | Not implemented |
| Sharpe ratio | Not implemented |
| Benchmark comparison | Not implemented |
| Broker/execution integration | Not implemented |
| Live/paper trading | Not implemented |

---

## Halal Compatibility

Following the same constraint established in Phase 2P.5:

- No short selling
- No leverage
- No margin

The simulation is strictly long-only. Future compliance policy layers will
decide how to interpret intents for different asset classes and compliance
configurations — this layer makes no compliance decisions.

---

## Determinism

All simulation outputs are fully deterministic:

```
identical (TradeIntentBatch, price_bars, config)
→ identical BacktestSimulationResult
```

No randomness. No timestamps from wall clock. No floating-point non-determinism
beyond what Python/IEEE 754 guarantees.

Trade IDs are deterministic:
```
trade_id = f"trade:{source_intent_id}"
```

Rejection IDs are deterministic:
```
rejection_id = f"rejection:{intent_id}"
```

---

## API

```
POST /backtests/simulate
```

Input:

```json
{
  "intent_batch": { ... TradeIntentBatch ... },
  "price_bars": [
    { "bar_index": 0, "timestamp": "2024-01-01T00:00:00Z", "close": 100.5 },
    ...
  ],
  "config": {
    "initial_cash": 10000.0,
    "position_size_mode": "fixed_quantity",
    "fixed_quantity": 1.0
  }
}
```

Output: `BacktestSimulationResult`

Typical caller flow:
1. `POST /semantics/evaluate-history` → `HistoricalEvaluationResult`
2. `POST /semantics/extract-signal-events` → `SignalEventBatch`
3. `POST /semantics/extract-trade-intents` → `TradeIntentBatch`
4. `POST /backtests/simulate` → `BacktestSimulationResult`

---

## Modules

| Module | Responsibility |
|--------|---------------|
| `backend/backtesting/models.py` | All domain models (frozen Pydantic v2) |
| `backend/backtesting/position_tracker.py` | Mutable position state + intent processing |
| `backend/backtesting/simulator.py` | Orchestrates simulation over bars |
| `backend/api/schemas/backtest_simulation.py` | API request schema |
| `backend/api/services/backtest_simulation_service.py` | Thin service wrapper |
| `backend/api/routes/backtest_simulation.py` | `POST /backtests/simulate` |

---

## Architecture Boundary

All Phase 2P.6 modules MUST NOT import from:

- `backend.strategy_runtime`
- `backend.execution`
- `backend.forward_testing`

Signal regeneration inside the simulator is forbidden. The simulator consumes
a pre-built `TradeIntentBatch` — it does not re-evaluate strategy semantics.

---

## Future Extension Path

```
BacktestSimulationResult (Phase 2P.6 — this layer)
→ Slippage & Fee Model (future)
  → execution_price = close ± slippage; cash -= fee
→ Percentage / Risk Sizing (future)
  → quantity = floor(capital_fraction × equity / price)
→ Multi-Asset Portfolio (future)
  → PortfolioState tracks per-instrument positions
→ Advanced Analytics (future)
  → Sharpe, drawdown series, CAGR, volatility
→ Compliance Policy Layer (future)
  → halal screening, risk limits
→ ExecutionPolicy Layer (future)
  → interpret intents into compliant order candidates
→ Broker Layer (future)
  → route orders to live brokers
```
