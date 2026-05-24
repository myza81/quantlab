# Signal Event Contracts — Phase 2P.4

## Overview

Phase 2P.4 introduces the first passive signal event layer for QuantLab.

Signal events convert evaluation outcomes into traceable, auditable, execution-free records.

This document describes the signal event contract, its meaning, its traceability fields, and what it explicitly does NOT do.

---

## Critical Architectural Separation

```
rule triggered  ≠  trade executed
entry signal    ≠  buy order
exit signal     ≠  sell order
signal event    ≠  execution intent
```

Signal events are informational. They record that a semantic rule evaluated to `True` on a given bar. They make no capital allocation decisions, generate no orders, and have no knowledge of positions, portfolio state, or broker systems.

---

## Signal Event Meaning

A `SignalEvent` is emitted when:

```
entry_triggered = True  →  entry SignalEvent (kind="entry")
exit_triggered  = True  →  exit SignalEvent  (kind="exit")
```

A `SignalEvent` is **NOT** emitted when:

```
outcome = False   →  rule did not trigger
outcome = None    →  indeterminate (e.g. first-bar crossover, missing price)
```

---

## Models

### `SignalEventKind`

```python
class SignalEventKind(str, Enum):
    ENTRY      = "entry"       # entry rule triggered True
    EXIT       = "exit"        # exit rule triggered True
    DIAGNOSTIC = "diagnostic"  # reserved; not emitted by default extractor
```

### `SignalEventSource`

Traceability metadata linking the event back to its origin:

| Field | Type | Meaning |
|-------|------|---------|
| `bar_index` | `int` | Index of the bar where the event occurred |
| `timestamp` | `datetime \| None` | Bar timestamp if provided |
| `rule_id` | `str \| None` | Rule ID from the compiled plan (may be None) |
| `rule_kind` | `"entry" \| "exit"` | Whether this was an entry or exit rule |
| `rule_index` | `int` | Position of the rule within entry/exit rules list |

### `SignalEvent`

| Field | Type | Meaning |
|-------|------|---------|
| `event_id` | `str` | Deterministic ID: `"{bar_index}:{rule_kind}:{rule_index}:{rule_id}"` |
| `kind` | `SignalEventKind` | `entry`, `exit`, or `diagnostic` |
| `source` | `SignalEventSource` | Full traceability to bar + rule origin |
| `outcome` | `bool` | Always `True` for emitted signal events |
| `diagnostics` | `tuple[EvaluationDiagnostic, ...]` | Diagnostics from the rule trace |

**Forbidden fields** (never present):
- `order` — no orders
- `trade` — no trades
- `fill` — no fills
- `position` — no positions
- `pnl` — no PnL
- `broker` — no broker concepts

### `SignalEventSummary`

| Field | Type | Meaning |
|-------|------|---------|
| `total_events` | `int` | Total signal events in batch |
| `entry_events` | `int` | Count of entry-kind events |
| `exit_events` | `int` | Count of exit-kind events |
| `diagnostic_events` | `int` | Count of diagnostic-kind events (0 from default extractor) |
| `bars_with_events` | `int` | Unique bar indices with at least one event |
| `first_event_bar_index` | `int \| None` | Bar index of earliest event |
| `last_event_bar_index` | `int \| None` | Bar index of latest event |

### `SignalEventBatch`

| Field | Type | Meaning |
|-------|------|---------|
| `plan_draft_id` | `str \| None` | Draft ID linkage from source evaluation |
| `events` | `tuple[SignalEvent, ...]` | Ordered events |
| `summary` | `SignalEventSummary` | Aggregated counts |

---

## Deterministic Ordering

Events within a batch are always sorted by:

```
1. bar_index          (ascending)
2. rule_kind          (entry before exit)
3. rule_index         (ascending)
4. rule_id            (lexicographic; None → "")
```

Identical inputs always produce identical event ordering. Tests enforce this invariant.

---

## Extraction

### Function

```python
from backend.strategy_registry.signal_event_extractor import extract_signal_events

batch: SignalEventBatch = extract_signal_events(historical_result)
```

### Rules

- Only `triggered=True` outcomes produce events
- `triggered=False` → no event
- `triggered=None` (indeterminate) → no event

### API Endpoint

```
POST /semantics/extract-signal-events
```

Accepts the same request format as `POST /semantics/evaluate-history`:

```json
{
  "semantics": { ... },
  "bars": [ { "bar_index": 0, "price_fields": {"close": 100.0}, "tool_outputs": {} } ]
}
```

Returns `SignalEventBatch`.

---

## Example

```python
from backend.strategy_registry.historical_evaluator import (
    HistoricalBarContext, HistoricalEvaluationInput, evaluate_history,
)
from backend.strategy_registry.signal_event_extractor import extract_signal_events

# Assuming plan is a compiled EvaluationPlan with an entry rule: close > 50

bars = [
    HistoricalBarContext(bar_index=0, price_fields={"close": 40.0}),  # False → no event
    HistoricalBarContext(bar_index=1, price_fields={"close": 80.0}),  # True  → entry event
    HistoricalBarContext(bar_index=2, price_fields={"close": 30.0}),  # False → no event
    HistoricalBarContext(bar_index=3, price_fields={"close": 90.0}),  # True  → entry event
]

historical_result = evaluate_history(HistoricalEvaluationInput(plan=plan, bars=bars))
batch = extract_signal_events(historical_result)

# batch.summary.total_events == 2
# batch.summary.entry_events == 2
# batch.events[0].source.bar_index == 1
# batch.events[1].source.bar_index == 3
```

---

## Forbidden Assumptions

Signal events **do not** imply:

- Capital allocation
- Long or short direction
- Order size or quantity
- Entry or exit price
- Stop loss or take profit levels
- Portfolio state changes
- Risk-adjusted sizing
- Compliance validation
- Broker readiness

These responsibilities belong to future execution and portfolio layers.

---

## Future Relationship to Backtesting

Signal events are the output surface that a backtesting engine will consume.

```
HistoricalEvaluationResult
→ SignalEventBatch                    ← Phase 2P.4 (this phase)
→ BacktestSimulation (future)
→ TradeRecord, PositionRecord (future)
→ BacktestResult with PnL (future)
```

The backtesting engine will:
- read signal events from this layer
- decide whether and how to simulate a trade
- apply slippage, fees, position sizing
- track portfolio state

None of that happens here. This layer records what the strategy said — not what was done about it.

---

## Architecture Boundary

All Phase 2P.4 modules must NOT import from:

- `backend.strategy_runtime`
- `backend.backtesting`
- `backend.execution`
- `backend.forward_testing`
