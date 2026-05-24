# Trade Intent Contracts — Phase 2P.5

## Overview

Phase 2P.5 introduces the passive trade intent layer — the intermediate contract
between semantic signal events and future simulation or execution systems.

A trade intent is a declaration that a future simulator or execution-policy layer
*may consider*. It is not an order, not a fill, and not a position mutation.

---

## Critical Architectural Separations

```
signal event   ≠  trade intent
trade intent   ≠  order
trade intent   ≠  position
trade intent   ≠  PnL
entry signal   ≠  buy order
exit signal    ≠  sell order
```

Trade intents are passive and informational. They record what a strategy's rules
implied without executing anything.

---

## Trade Intent Meaning

A `TradeIntent` is emitted when a `SignalEvent` maps to a recognized action:

```
entry signal  →  open_long intent
exit signal   →  close_long intent
diagnostic    →  ignored (tracked in ignored_event_ids)
```

A `TradeIntent` does **NOT** represent:
- orders
- fills
- positions
- broker instructions
- capital allocation
- quantity or price
- execution timing
- PnL expectations

---

## Action Minimalism and Halal Compatibility

`TradeIntentAction` deliberately contains only:

```python
OPEN_LONG  = "open_long"
CLOSE_LONG = "close_long"
```

**Not present by design:**
- `short_sell` / `open_short` — excluded for halal equity compatibility
- `leverage` — belongs to execution policy, not intents
- `margin` — belongs to execution policy, not intents
- `order_type` — belongs to order layer, not intents

Rationale: QuantLab must remain compatible with halal constraints. Short selling
of equities is prohibited under many interpretations of Islamic finance. Execution
policy layers will later decide how to interpret open/close intents by asset class
and compliance configuration — this layer makes no compliance decisions.

---

## Models

### `TradeIntentAction`

```python
class TradeIntentAction(str, Enum):
    OPEN_LONG  = "open_long"
    CLOSE_LONG = "close_long"
```

### `TradeIntentSource`

Traceability metadata linking the intent to its originating signal event:

| Field | Type | Meaning |
|-------|------|---------|
| `signal_event_id` | `str` | `event_id` from the originating `SignalEvent` |
| `bar_index` | `int` | Bar where the signal was generated |
| `timestamp` | `datetime \| None` | Bar timestamp if provided |
| `rule_id` | `str \| None` | Rule ID from the compiled plan |
| `rule_kind` | `"entry" \| "exit"` | Whether this was entry or exit |

### `TradeIntent`

| Field | Type | Meaning |
|-------|------|---------|
| `intent_id` | `str` | Deterministic: `"intent:{signal_event_id}"` |
| `action` | `TradeIntentAction` | `open_long` or `close_long` |
| `source` | `TradeIntentSource` | Full traceability to bar + rule origin |

**Forbidden fields** (never present):
- `order`, `trade`, `fill`, `position`, `pnl`, `quantity`, `price`, `broker`, `margin`, `leverage`

### `TradeIntentSummary`

| Field | Type | Meaning |
|-------|------|---------|
| `total_intents` | `int` | All intents in batch |
| `open_long_intents` | `int` | Count of open_long intents |
| `close_long_intents` | `int` | Count of close_long intents |
| `ignored_signal_events` | `int` | Diagnostic events not converted |
| `first_intent_bar_index` | `int \| None` | Earliest intent's bar |
| `last_intent_bar_index` | `int \| None` | Latest intent's bar |

### `TradeIntentBatch`

| Field | Type | Meaning |
|-------|------|---------|
| `plan_draft_id` | `str \| None` | Draft linkage from source evaluation |
| `intents` | `tuple[TradeIntent, ...]` | Ordered intents |
| `summary` | `TradeIntentSummary` | Aggregated counts |
| `ignored_event_ids` | `tuple[str, ...]` | IDs of signals not converted |

---

## Deterministic Intent IDs

Intent IDs are built deterministically from the source signal event ID:

```
intent_id = f"intent:{signal_event_id}"
```

Since `signal_event_id` is itself deterministic (e.g. `"5:entry:0:r1"`), the
full intent ID is reproducible from identical inputs. No random UUIDs are used.

---

## Extraction

### Function

```python
from backend.strategy_registry.trade_intent_extractor import extract_trade_intents

batch: TradeIntentBatch = extract_trade_intents(signal_event_batch)
```

### Ordering

Output ordering matches the input `SignalEventBatch` ordering, which is:

```
bar_index → entry-before-exit → rule_index → rule_id
```

No re-sorting is needed — the ordering is inherited.

### API Endpoint

```
POST /semantics/extract-trade-intents
```

Accepts a `SignalEventBatch` (JSON body). Returns `TradeIntentBatch`.

The caller typically:
1. Calls `POST /semantics/extract-signal-events` → gets `SignalEventBatch`
2. Calls `POST /semantics/extract-trade-intents` with that batch → gets `TradeIntentBatch`

---

## Example

```python
from backend.strategy_registry.signal_event_extractor import extract_signal_events
from backend.strategy_registry.trade_intent_extractor import extract_trade_intents

# Assuming historical_result is a HistoricalEvaluationResult

signal_batch = extract_signal_events(historical_result)
intent_batch = extract_trade_intents(signal_batch)

# intent_batch.summary.open_long_intents == number of entry triggers
# intent_batch.summary.close_long_intents == number of exit triggers
# intent_batch.intents[0].action == TradeIntentAction.OPEN_LONG
# intent_batch.intents[0].intent_id == "intent:0:entry:0:r1"
```

---

## Future Relationship to Execution Policy and Backtesting

Trade intents are the input surface that a backtesting engine or execution policy
will consume. The layered relationship:

```
HistoricalEvaluationResult
→ SignalEventBatch              ← Phase 2P.4
→ TradeIntentBatch              ← Phase 2P.5 (this layer)
→ BacktestSimulation (future)
  → apply sizing, slippage, fees
  → TradeRecord, PositionRecord
  → BacktestResult with PnL
→ ExecutionPolicy (future live)
  → compliance validation
  → order sizing
  → broker routing
```

At each transition, the responsibility grows. This layer establishes only
the clean passive declaration of intent — what the strategy implied.

---

## Architecture Boundary

All Phase 2P.5 modules must NOT import from:

- `backend.strategy_runtime`
- `backend.backtesting`
- `backend.execution`
- `backend.forward_testing`
