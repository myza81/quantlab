# PAPER_TRADING_IMPLEMENTATION_REVIEW.md

Phase 4D — Paper Trading Foundation: Architecture Review and Implementation Planning

Produced by the Primary Implementation Agent after a full codebase survey against
the completed Phase 4C architecture documents.  
No implementation code was written.  
This document is the implementation authority for Phase 4E and beyond.

---

## Table of Contents

1. [Purpose and Scope](#1-purpose-and-scope)
2. [Architecture Documents Reviewed](#2-architecture-documents-reviewed)
3. [Directly Reusable Components](#3-directly-reusable-components)
4. [Missing Components](#4-missing-components)
5. [Account Model Recommendation](#5-account-model-recommendation)
6. [Order Model Recommendation](#6-order-model-recommendation)
7. [Fill Model Recommendation](#7-fill-model-recommendation)
8. [Position Model Recommendation](#8-position-model-recommendation)
9. [Portfolio Model Recommendation](#9-portfolio-model-recommendation)
10. [Session Model Recommendation](#10-session-model-recommendation)
11. [Promotion Lifecycle Recommendation](#11-promotion-lifecycle-recommendation)
12. [Audit Taxonomy Recommendation](#12-audit-taxonomy-recommendation)
13. [Storage Assessment](#13-storage-assessment)
14. [Workflow Design](#14-workflow-design)
15. [Risks and Open Questions](#15-risks-and-open-questions)
16. [Implementation Roadmap](#16-implementation-roadmap)
17. [Readiness Assessment](#17-readiness-assessment)
18. [Recommended Next Phase](#18-recommended-next-phase)

---

## §1 Purpose and Scope

This document is the implementation planning artifact for the QuantLab Paper Trading subsystem.  
It reviews the actual codebase state — in particular the completed Phase 4C Forward Testing
implementation — against the architecture contracts established in `docs/PAPER_TRADING_ARCHITECTURE.md`,
`docs/EXECUTION_CONTRACT.md`, `docs/EXECUTION_AUDIT_MODEL.md`, and
`docs/STRATEGY_PROMOTION_LIFECYCLE.md`, and produces an actionable, phased implementation plan.

**What this document covers:**

- Inventory of what Phase 4C built that can be directly reused
- Inventory of what must be built fresh for paper trading
- Specific design recommendations for all six data models (account, order, fill, position,
  portfolio, session)
- Explicit gap analysis against lifecycle governance and audit contracts
- API surface design and frontend integration requirements
- Ordered roadmap for phased delivery

**What this document does not cover:**

- Broker integration or live trading infrastructure — deferred
- Streaming / WebSocket market data — deferred to Phase 5A
- Sub-15m timeframe support — deferred to Phase 4H
- Performance-threshold-based promotion rules — reviewer discretion (by contract)
- Partial fills, limit orders, trailing stops — explicitly out of scope per architecture

---

## §2 Architecture Documents Reviewed

The following documents were read in full before producing this review:

| Document | Role |
|----------|------|
| `docs/PAPER_TRADING_ARCHITECTURE.md` | Primary specification: session, account, order, fill, position, broker adapter |
| `docs/EXECUTION_CONTRACT.md` | Core execution philosophy, intent flow, gateway contract, safety constraints |
| `docs/EXECUTION_AUDIT_MODEL.md` | Complete PT_ audit event taxonomy, 13-field envelope, immutability rules |
| `docs/STRATEGY_PROMOTION_LIFECYCLE.md` | Promotion governance: PAPER_TESTED gate, evidence requirements |
| `docs/FORWARD_TESTING_ARCHITECTURE.md` | Shared architecture baseline inherited by paper trading |
| `docs/FORWARD_TESTING_IMPLEMENTATION_REVIEW.md` | Template: structure of a Phase 4B review document |

The following backend modules were surveyed to understand actual implementation state:

| Module | Relevance |
|--------|-----------|
| `backend/forward_testing/models.py` | `ForwardTestSession`, `ForwardTestStatus` — inheritance base |
| `backend/forward_testing/service.py` | `ForwardTestService._poll_cycle()` — extension point for execution layer |
| `backend/forward_testing/repository.py` | Repository pattern — template for `PaperTradingRepository` |
| `backend/forward_testing/stores.py` | `ForwardTestBarStore`, `ForwardTestSignalStore` — directly reusable |
| `backend/forward_testing/exceptions.py` | Exception taxonomy — template for PT exceptions |
| `backend/strategy_registry/historical_evaluator.py` | `evaluate_history()` — FT already reuses; PT does too |
| `backend/strategy_registry/semantic_compiler.py` | `compile_semantics()` — reusable as-is |
| `backend/strategy_registry/lifecycle.py` | `StrategyLifecycleStatus` enum — check for PAPER_TESTED |
| `backend/strategy_registry/draft_repository.py` | `DraftRepository` pattern |
| `backend/services/ohlcv_service.py` | `OHLCVService.get_recent_bars()`, `get_bars_since()` — reusable |
| `backend/data_providers/provider_factory.py` | `ProviderAdapterFactory` — reusable |
| `backend/core/audit.py` | `AuditEventKind`, `emit_audit_event()` — extension required for PT_ |
| `backend/api/routes/forward_tests.py` | Route pattern, ownership enforcement, response schemas |
| `backend/execution/__init__.py` | Empty placeholder — paper trading execution layer goes here |
| `backend/tools/historical_computation.py` | Tool pipeline — same path as forward testing |

---

## §3 Directly Reusable Components

These components require **no modification** for paper trading use.

---

### 3.1 `evaluate_history()` — Per-Bar Evaluation Engine

**Location:** `backend/strategy_registry/historical_evaluator.py`

Forward testing already uses this in full-window recomputation mode: warmup bars + new bars
are passed as a single batch per poll cycle; per-bar results for new bars only are sliced
out and evaluated.

Paper trading reuses the exact same approach — it adds the execution layer **after**
`evaluate_history()` returns per-bar signals, not inside it. The evaluation engine
remains unmodified and unaware of execution mode.

**Reuse boundary:** The evaluator returns feature values and rule-fire flags per bar.
Paper trading reads those flags to produce `ExecutionIntent` objects.
The evaluator never receives or returns position state.

---

### 3.2 `compile_semantics()` — Semantics Compiler

**Location:** `backend/strategy_registry/semantic_compiler.py`

Produces the `EvaluationPlan` consumed by `evaluate_history()`.  
Zero modification required.

---

### 3.3 `StrategySnapshot` + Snapshot Sealing

**Location:** `backend/forward_testing/models.py`, `backend/api/routes/forward_tests.py`

The snapshot sealing logic established in Phase 4C — capturing the sealed strategy definition
at session creation, linking it by hash — applies identically to paper trading.

Paper trading sessions carry the same `strategy_snapshot` field.  
The snapshot is immutable from session creation onward.

**Reuse boundary:** No modification required. The snapshot contract from Phase 4C applies
in full to paper trading.

---

### 3.4 `OHLCVService.get_recent_bars()` and `get_bars_since()`

**Location:** `backend/services/ohlcv_service.py`

Paper trading polls for new bars using the same two-method pattern:
- `get_recent_bars()` for warmup bar acquisition at session activation
- `get_bars_since(last_processed_bar_timestamp)` for incremental polling per cycle

No change to `OHLCVService` required.

---

### 3.5 `ProviderAdapterFactory`

**Location:** `backend/data_providers/provider_factory.py`

Paper trading uses the same provider abstraction as forward testing.  
Yahoo Finance and future providers are available without modification.

---

### 3.6 `ForwardTestBarStore`

**Location:** `backend/forward_testing/stores.py`

Paper trading produces the same bar store requirements as forward testing —
raw OHLCV bars stored per session for warmup recomputation.

The `ForwardTestBarStore` is either shared directly or used as the template
for a thin `PaperTradingBarStore` alias.

---

### 3.7 `ForwardTestSignalStore`

**Location:** `backend/forward_testing/stores.py`

Paper trading produces `ForwardTestSignal` records for every signal that fires —
identical to forward testing. The signal schema does not change.

The `ForwardTestSignalStore` is directly shared: paper trading sessions write
to the same signal store infrastructure.

**Architecture note:** Paper trading is a strict superset of forward testing's outputs
per `PAPER_TRADING_ARCHITECTURE.md` §17. Signal records are identical.

---

### 3.8 `AuditEvent` + `emit_audit_event()`

**Location:** `backend/core/audit.py`

The existing audit infrastructure — log-based, JSON-structured, `quantlab.audit` logger —
is the correct mechanism for paper trading audit events.

**Extension required:** `AuditEventKind` enum must gain 29 new `PT_*` values.
The emit function itself requires no change.  
See §12 for the full taxonomy.

---

### 3.9 Ownership and Entitlement Enforcement

**Location:** `backend/api/routes/forward_tests.py`, `backend/auth/entitlement.py`

The ownership pattern established in Phase 4C is the correct model:
- `user_id` always from `current_user.user_id` (JWT) — never from request body
- Wrong-owner access → HTTP 404 (information hiding)
- `require_active_subscription` dependency on all write routes
- `validate_uuid_id()` on all `session_id` path parameters

No change to the entitlement layer required.

---

### 3.10 `ForwardTestService._prepare_strategy()`

**Location:** `backend/forward_testing/service.py`

The strategy preparation logic — deserializing snapshot, compiling semantics, detecting
missing semantics — is directly reused by the paper trading service.

Paper trading's service class either inherits from or delegates to this method.  
Modification to the method is not required.

---

## §4 Missing Components

These components are completely absent from the codebase and must be built.

---

### 4.1 `PaperTradingSession` Model

A new dataclass (or Pydantic model) inheriting all `ForwardTestSession` fields and
extending with paper-trading-specific fields: `account_id`, `simulation_assumptions`,
`max_concurrent_positions`, `max_drawdown_stop_pct`, `starting_equity`, `session_type`.

**Location:** `backend/paper_trading/models.py` (new module)

---

### 4.2 `SimulationAssumptions` Model

An immutable, frozen dataclass declaring the execution mechanics for a session:
`fill_timing_model`, `fee_mode`, `fee_value`, `slippage_mode`, `slippage_value`,
`position_size_mode`, `position_size_value`.

Must be declared at session creation. Immutable after activation.

**Location:** `backend/paper_trading/models.py`

---

### 4.3 `PaperAccount` Model

The simulated financial account associated with a paper trading session.
Fields: `account_id`, `owner_user_id`, `session_id`, `currency`, `starting_cash`,
`cash_balance`, `equity`, `peak_equity`, `current_drawdown_pct`,
`total_realized_pnl`, `total_fees_paid`, `total_slippage_applied`,
`status`, `created_timestamp`, `updated_timestamp`.

**Location:** `backend/paper_trading/models.py`

---

### 4.4 `PaperOrder` Model

Internal execution layer record. Fields: `order_id`, `session_id`, `account_id`,
`created_timestamp`, `bar_timestamp`, `symbol`, `side`, `quantity`, `order_type`,
`limit_price`, `status`, `source_intent_id`, `source_signal_id`, `rejection_reason`, `fills`.

**Location:** `backend/paper_trading/models.py`

---

### 4.5 `PaperFill` Model

Atomic execution record. Fields: `fill_id`, `order_id`, `session_id`, `account_id`,
`fill_timestamp`, `bar_timestamp`, `symbol`, `side`, `fill_quantity`,
`gross_fill_price`, `slippage_applied`, `net_fill_price`, `fee_applied`,
`execution_reason`, `source_signal_id`.

**Location:** `backend/paper_trading/models.py`

---

### 4.6 `PaperPosition` Model

Open or closed position record. Fields: `position_id`, `session_id`, `account_id`,
`symbol`, `side`, `quantity`, `average_entry_price`, `current_market_value`,
`unrealized_pnl`, `realized_pnl`, `open_timestamp`, `close_timestamp`,
`status`, `opening_signal_id`, `closing_signal_id`.

**Location:** `backend/paper_trading/models.py`

---

### 4.7 `AccountStateSnapshot` Model

Per-bar equity curve data point. Fields: `snapshot_id`, `session_id`, `account_id`,
`bar_timestamp`, `cash_balance`, `equity`, `peak_equity`, `current_drawdown_pct`,
`open_positions_count`, `created_timestamp`.

One snapshot per processed bar, minimum.

**Location:** `backend/paper_trading/models.py`

---

### 4.8 `PaperBrokerAdapter`

The fill simulation engine. Responsibilities:
1. Receive `ExecutionIntent` from evaluation layer
2. Validate against account state and session constraints (cash, max_positions, close target)
3. Translate validated intent to `PaperOrder`
4. Simulate fill price from `simulation_assumptions.fill_timing_model`
5. Apply declared slippage and fee
6. Create immutable `PaperFill`
7. Update `PaperPosition` (open / scale / close)
8. Update `PaperAccount` (cash, equity, drawdown)
9. Emit PT_ audit events at each step

**Location:** `backend/paper_trading/broker_adapter.py` (new file)

This is the most complex new component. It has no counterpart in the forward testing layer.

---

### 4.9 Execution Gateway (Minimal)

A routing layer that accepts `ExecutionIntent` objects and dispatches them to the
appropriate adapter (only `PaperBrokerAdapter` in Phase 4E scope).

In the current single-adapter scope, the gateway is thin — it validates that an intent
is non-null and routes it to `PaperBrokerAdapter`. Full adapter substitution support
becomes important in Phase 5 (live trading).

**Location:** `backend/execution/gateway.py` (new file in existing placeholder module)

---

### 4.10 `PaperTradingRepository`

JSON-backed repository for `PaperTradingSession` records. Modeled on `ForwardTestRepository`.
Implements: save, get_by_id (ownership-scoped), list_for_user, update_status.

**Location:** `backend/paper_trading/repository.py` (new file)

---

### 4.11 `PaperOrderStore`, `PaperFillStore`, `PaperPositionStore`

Append-only JSON-backed stores for order, fill, and position records respectively.
All records are immutable after creation. Stores support:
- Append new record
- List by session_id (ownership already enforced at service layer)
- Get by record ID

**Location:** `backend/paper_trading/stores.py` (new file)

---

### 4.12 `PaperAccountStore`

Mutable store for `PaperAccount` (single running state per session) plus
append-only store for `AccountStateSnapshot` records (equity curve).

Account record is updated in-place after each fill and after each bar.
Snapshot records are append-only.

**Location:** `backend/paper_trading/stores.py`

---

### 4.13 `PaperTradingService`

The session management and poll cycle orchestration service for paper trading.
Extends the pattern established by `ForwardTestService`, adding the execution layer
after signal generation.

Core method: `run_cycle(session_id, user_id)` — mirrors `ForwardTestService.run_cycle()`
but routes `ExecutionIntent` objects through the gateway after signal recording.

**Location:** `backend/paper_trading/service.py` (new file)

---

### 4.14 Session-Level Metrics Calculator

Computes final session metrics at session completion:
- Total return (%)
- Maximum drawdown (%)
- Win rate
- Trade count (filled)
- Profit factor
- Average hold duration
- Signal count vs fill count (fill rate)
- Total fees paid
- Total slippage applied

Consumed when session transitions to `completed`.

**Location:** `backend/paper_trading/metrics.py` (new file)

---

### 4.15 29 `PT_*` `AuditEventKind` Values

Extension to the existing `AuditEventKind` enum in `backend/core/audit.py`.
Full taxonomy defined in §12.

---

### 4.16 Paper Trading API Routes

9+ FastAPI routes under `/api/v1/paper-trading/` prefix.
Full surface defined in §14.

**Location:** `backend/api/routes/paper_trading.py` (new file)

---

### 4.17 Paper Trading API Schemas

Request and response Pydantic models for the paper trading API surface.

**Location:** `backend/api/schemas/paper_trading.py` (new file)

---

### 4.18 `PaperTradingPanel` Frontend Component

React component providing the paper trading session management UI.
Analogous to `ForwardTestPanel` established in Phase 4C.5.

**Location:** `frontend/src/components/PaperTradingPanel.tsx` (new file)

---

## §5 Account Model Recommendation

**Recommended model:** `PaperAccount` as a mutable running-state record,
with `AccountStateSnapshot` as the append-only equity curve.

### Design rationale

The `PaperAccount` record tracks the current state of the simulated account.
It is updated after every fill and after every bar (for mark-to-market).
It is the only mutable object in the paper trading domain; all other records
(orders, fills, positions, snapshots) are immutable after creation.

Separating the mutable account state from the immutable equity curve snapshots
avoids conflating two different concerns: current state (what does the account
look like right now?) versus historical record (what was the equity at each bar?).

### Update sequence (after each fill)

1. Update `PaperPosition` (open / scale / close)
2. `cash_balance` ← deduct (buy) or add (sell), net of fees
3. `equity` ← cash_balance + sum(open position current_market_value)
4. `total_realized_pnl` ← add realized P&L from closed position
5. `total_fees_paid` ← add fee_applied from fill
6. `total_slippage_applied` ← add slippage_applied from fill
7. Check `max_drawdown_stop_pct` — pause session if breached

### Update sequence (after each bar, with no fills)

1. Mark all open positions with current close price → update `current_market_value` and `unrealized_pnl`
2. `equity` ← recalculate
3. `peak_equity` ← update if current equity exceeds previous peak
4. `current_drawdown_pct` ← (peak_equity − equity) / peak_equity × 100
5. Record `AccountStateSnapshot` (equity curve point)

### Currency

`currency` field is declarative (e.g., `USD`). No currency conversion is performed.
All numeric values are in the declared currency. Multi-currency operations are out of scope.

### No real money invariant

The account model must contain no mechanism for funding, withdrawal, transfer, or linkage
to any real financial account. These are arithmetic constructs only.

---

## §6 Order Model Recommendation

**Recommended model:** `PaperOrder` as an immutable record after creation,
with structured `rejection_reason` codes (not raw exception messages).

### Design rationale

`PaperOrder` is an internal execution layer object — it is never produced by strategy
logic and never returned to the frontend in raw form. It exists solely as an
auditable record of what the `PaperBrokerAdapter` was instructed to do and why.

The `rejection_reason` field must use structured codes (`insufficient_cash`,
`max_positions_exceeded`, `no_position_to_close`, `quantity_resolved_to_zero`)
rather than raw exception strings. Raw exceptions may contain internal paths or
stack traces that must not appear in API responses or audit records.

### Market orders only in Phase 4E scope

Current scope: market orders only. `order_type = market`, `limit_price = null`.

Limit order support is acknowledged as a future extension. The `order_type` and
`limit_price` fields are present in the model to accommodate future limit order
implementation without a schema migration.

### Provenance chain integrity

Every `PaperOrder` carries both `source_intent_id` and `source_signal_id`.
This ensures the full provenance chain (signal → intent → order → fill) is
navigable in both directions.

---

## §7 Fill Model Recommendation

**Recommended model:** `PaperFill` as a fully self-documenting, immutable record
capturing every parameter used in the fill computation.

### Self-documenting fills

Every `PaperFill` must store:
- `gross_fill_price` (before slippage)
- `slippage_applied` (in price units)
- `net_fill_price` (after slippage)
- `fee_applied` (in currency units)
- `execution_reason` (why this fill was generated)
- `source_signal_id` (provenance back to strategy rule)

A reviewer must be able to recompute the fill from the `PaperFill` record alone.
No external reference to simulation assumptions should be required to verify a fill.

### Fill timing models

Both fill timing models must be implemented:

**`signal_bar_close`** — `gross_fill_price = bar.close` of the signal bar.
Optimistic; assumes instantaneous execution at bar close.

**`next_bar_open`** — `gross_fill_price = bar.open` of the bar following the signal.
Conservative; recommended default.

For `next_bar_open`, the `PaperBrokerAdapter` must retain the pending order through
the bar boundary and apply the fill when the next bar's open is available.
This requires that the service's poll cycle processes fills from the prior bar before
evaluating the current bar's signals.

### Slippage

Three modes: `none`, `fixed` (price units), `percentage` (decimal fraction).
Slippage is applied to `gross_fill_price` to produce `net_fill_price`.
For buys: `net_fill_price = gross_fill_price + slippage_applied`.
For sells: `net_fill_price = gross_fill_price − slippage_applied`.

### Fees

Three modes: `none`, `flat` (currency amount per trade), `percentage` (fraction of
gross fill value: `fill_quantity × gross_fill_price × fee_value`).
Fee is applied after slippage. Stored as `fee_applied` in the fill record.

### Determinism invariant

Given the same bar data and the same `simulation_assumptions`, fill simulation
must always produce the same result. No randomness. No dynamic market impact.
This is a testability requirement: fills must be reproducible in unit tests.

---

## §8 Position Model Recommendation

**Recommended model:** `PaperPosition` as a mutable running-state record for open
positions, transitioning to a closed, immutable record when fully exited.

### Single net position per symbol

Phase 4E scope: one net position per symbol per session.
A session holding AAPL cannot open a second AAPL position without closing the first.
Attempting to open when a position is already open in the same direction is rejected
with `rejection_reason = position_already_open`.

### State transitions

```
(none)
    → open         (buy fill on new position)
    → scaled       (additional buy fill on existing long position)
    → closed       (sell fill fully closes position)
    → force_closed (session_end_close or drawdown_stop_close)
```

Each transition from `open` to `closed` or `force_closed` sets `close_timestamp`
and makes the record effectively immutable (no further updates after closure).

### Strategy portability invariant

The position model is owned by the execution environment.
Strategy logic must never receive a `PaperPosition` object.
Exit signals must be formulated in terms of market data features (price conditions,
indicator values). When those conditions are met, the strategy produces an
`ExecutionIntent(direction=EXIT_LONG)`. The `PaperBrokerAdapter` resolves whether
a position exists to close and produces the fill.

### Mark-to-market cadence

`current_market_value` and `unrealized_pnl` are updated after each bar,
not only after fills. This ensures the equity curve is accurate even in bars
where no fills occur.

---

## §9 Portfolio Model Recommendation

**Recommended approach:** No separate `Portfolio` model in Phase 4E scope.

### Rationale

Phase 4E is single-symbol, long-only, single-session. There is at most one
`PaperPosition` at any given time. The "portfolio" is simply the current
`PaperAccount` state plus the zero or one open `PaperPosition` records.

The `PaperAccount` already aggregates the relevant portfolio-level metrics:
`equity`, `cash_balance`, `current_drawdown_pct`, `total_realized_pnl`.

A separate `Portfolio` model would add complexity without adding capability
in the current scope.

### Future multi-position support

When `max_concurrent_positions > 1` is supported (Phase 4F or later), a
portfolio-level view will be needed: aggregate unrealized P&L across all open
positions, per-symbol exposure, portfolio-level heat. At that point, a
`PortfolioSummary` aggregate should be introduced.

For Phase 4E: the account record is the portfolio.

---

## §10 Session Model Recommendation

**Recommended model:** `PaperTradingSession` as a dataclass that extends
`ForwardTestSession` via composition (not inheritance) to avoid Python dataclass
inheritance fragility.

### Composition vs inheritance

`ForwardTestSession` is a dataclass with ~18 fields.
Python dataclass inheritance requires child class fields to have defaults if parent
fields lack defaults — this creates ordering constraints that are brittle to extend.

Preferred approach: `PaperTradingSession` contains all `ForwardTestSession` fields
explicitly (possibly via `@dataclass` with a `base: ForwardTestSession` field)
plus its extended fields, rather than inheriting from `ForwardTestSession`.

If the codebase already uses a `ForwardTestSession` that is well-constructed for
inheritance, direct subclassing is acceptable — but the implementation must verify
that field ordering does not produce `TypeError` during instantiation.

### Additional session fields

Beyond all `ForwardTestSession` fields:

| Field | Type | Description |
|-------|------|-------------|
| `account_id` | `str` | UUID of associated `PaperAccount` |
| `simulation_assumptions` | `SimulationAssumptions` | Immutable execution parameters |
| `max_concurrent_positions` | `int` | Maximum simultaneous open positions |
| `max_drawdown_stop_pct` | `Optional[float]` | Session-level drawdown stop threshold |
| `starting_equity` | `float` | Initial paper account balance |
| `session_type` | `str` | Literal `"paper_trading"` |

### Assumption immutability enforcement

`simulation_assumptions` must be stored as a frozen dataclass or equivalent.
The service layer must reject any attempt to modify `simulation_assumptions`
once `status` is `running`. This is enforced in the service layer, not the model.

### Activation lifecycle requirement

`lifecycle_status_at_activation` must be `>= backtested` at session activation.
The check is performed in `PaperTradingService.activate_session()` before the
session transitions to `running`.

---

## §11 Promotion Lifecycle Recommendation

### Current state of `StrategyLifecycleStatus`

**Verification required:** Check `backend/strategy_registry/lifecycle.py` to confirm
whether `PAPER_TESTED` is already present. Phase 4C.2 added `FORWARD_TESTED`; the
`PAPER_TESTED` value may or may not have been added at the same time.

If `PAPER_TESTED` is absent: it must be added before any paper trading session can
complete the `FORWARD_TESTED → PAPER_TESTED` transition.

### Promotion gate: `PAPER_TESTED`

Per `docs/STRATEGY_PROMOTION_LIFECYCLE.md` §9 and the `PAPER_TRADING_ARCHITECTURE.md`:

**Requirement for promotion from `FORWARD_TESTED` to `PAPER_TESTED`:**
- At least one paper trading session with `status = completed`
- The session's `lifecycle_status_at_activation >= forward_tested`
- Complete `PT_*` audit trail for the session
- Explicit human review and `GOV_PROMOTION_APPROVED` event

**What paper trading does NOT do automatically:**
- No automatic `PAPER_TESTED` status advancement on session completion
- No automatic promotion to `APPROVED_FOR_LIVE` at any point

### Activation gate: `lifecycle_status >= backtested`

The paper trading service must enforce:
```python
if session.strategy_snapshot.lifecycle_status_at_activation < LifecycleStatus.BACKTESTED:
    emit_audit_event(PT_ACTIVATION_DENIED, ...)
    raise PaperTradingActivationDenied(...)
```

A strategy at `VALIDATED` may not enter paper trading (exploratory paper trading
is not permitted — unlike forward testing which allows exploratory sessions at VALIDATED).

### Exploratory vs promotion-eligible sessions

Per `docs/STRATEGY_PROMOTION_LIFECYCLE.md` §16:
- `BACKTESTED` strategy in paper trading → exploratory (no promotion-eligible evidence)
- `FORWARD_TESTED` strategy in paper trading → promotion-eligible

The session record must carry `lifecycle_status_at_activation` to distinguish these.
Reviewers use this field to determine whether a session qualifies as promotion evidence.

---

## §12 Audit Taxonomy Recommendation

### Extension to `AuditEventKind`

The following 29 values must be added to `AuditEventKind` in `backend/core/audit.py`:

**Session Lifecycle (10 events)**

| Event Kind | Trigger |
|------------|---------|
| `PT_SESSION_CREATED` | `PaperTradingSession` record created |
| `PT_SESSION_ACTIVATED` | Session transitions to `running` |
| `PT_SESSION_PAUSED` | User-requested pause |
| `PT_SESSION_PAUSED_DRAWDOWN_STOP` | Drawdown stop threshold triggered |
| `PT_SESSION_PAUSED_PROVIDER_FAILURE` | Persistent provider failure |
| `PT_SESSION_RESUMED` | Transition from `paused` to `running` |
| `PT_SESSION_COMPLETED` | Session transitions to `completed` |
| `PT_SESSION_FAILED` | Unrecoverable error |
| `PT_SESSION_TERMINATED` | Admin or system termination |
| `PT_SESSION_INVALID_TRANSITION_DENIED` | Invalid lifecycle transition rejected |

**Strategy Activation (2 events)**

| Event Kind | Trigger |
|------------|---------|
| `PT_ACTIVATION_DENIED` | `lifecycle_status_at_activation < backtested` |
| `PT_ACTIVATION_APPROVED` | Activation check passed |

**Order Events (3 events)**

| Event Kind | Trigger |
|------------|---------|
| `PT_ORDER_CREATED` | `PaperBrokerAdapter` creates `PaperOrder` |
| `PT_ORDER_REJECTED` | Intent validation failed |
| `PT_ORDER_CANCELLED` | Limit order expired or session close (future) |

**Fill Events (1 event)**

| Event Kind | Trigger |
|------------|---------|
| `PT_FILL_GENERATED` | Fill simulation produces a `PaperFill` |

**Position Events (4 events)**

| Event Kind | Trigger |
|------------|---------|
| `PT_POSITION_OPENED` | New position opened by buy fill |
| `PT_POSITION_SCALED` | Existing position increased (additional buy fill) |
| `PT_POSITION_CLOSED` | Position fully closed by sell fill |
| `PT_POSITION_FORCE_CLOSED` | Closed by `session_end_close` or `drawdown_stop_close` |

**Account Events (3 events)**

| Event Kind | Trigger |
|------------|---------|
| `PT_ACCOUNT_UPDATED` | Account state updated after fill |
| `PT_DRAWDOWN_THRESHOLD_WARNING` | Drawdown exceeds 80% of `max_drawdown_stop_pct` |
| `PT_DRAWDOWN_STOP_TRIGGERED` | Drawdown exceeds `max_drawdown_stop_pct` |

**Data Events (5 events — parallel to FT_ data events)**

| Event Kind | Trigger |
|------------|---------|
| `PT_POLL_COMPLETED` | Poll cycle completed |
| `PT_PROVIDER_FAILURE` | Provider returned no bars or error |
| `PT_GAP_DETECTED` | Expected bar absent per market calendar |
| `PT_CATCHUP_STARTED` | Multiple missed bars detected; catch-up begins |
| `PT_CATCHUP_THRESHOLD_EXCEEDED` | Catch-up bar count exceeds configured limit |

**Access Events (2 events)**

| Event Kind | Trigger |
|------------|---------|
| `PT_SESSION_EXPORTED` | User requests session export |
| `PT_SESSION_REVIEWED` | Session accessed for lifecycle promotion review |

### Audit event payload requirements

Every PT_ event must include: `session_id`, `user_id`, `account_id`,
`event_timestamp` (UTC), and event-specific fields.

Audit events must never include: `file_path`, decrypted credentials,
raw provider error messages, internal stack traces, or any real account identifiers.

---

## §13 Storage Assessment

### Current storage pattern

Phase 4C implemented JSON-backed stores for forward testing:
`ForwardTestBarStore` and `ForwardTestSignalStore` in
`backend/forward_testing/stores.py`.

The pattern: a JSON file per session, loaded on access, appended on write.

### Acceptability for Phase 4E

JSON-backed storage is acceptable for paper trading in Phase 4E for the following reasons:
- Development and early deployment targets are low-volume (few concurrent sessions)
- The architecture explicitly acknowledges JSON storage as sufficient before PostgreSQL migration
- The forward testing stores have demonstrated this pattern works for the current scale

### Store structure recommendation

| Store | Pattern | Notes |
|-------|---------|-------|
| `PaperTradingRepository` | JSON file per session | Session record + metadata |
| `PaperAccountStore` | Single JSON file per session | Mutable account state + snapshot list |
| `PaperOrderStore` | Append-only JSON array per session | Immutable after creation |
| `PaperFillStore` | Append-only JSON array per session | Immutable after creation |
| `PaperPositionStore` | JSON dict by position_id per session | Mutable until closed; then immutable |
| `PaperBarStore` | Shared with / mirrors `ForwardTestBarStore` | OHLCV bars for warmup recompute |

### Equity curve storage

`AccountStateSnapshot` records are append-only — one per bar processed.
For a 1-year daily session (~252 bars), this is 252 snapshot records.
For a 1-year 15m session (~6700 bars), this is 6700 records.

JSON is adequate for daily and 4H timeframes. At 15m, snapshot lists will approach
sizes where JSON loading performance degrades. A separate, lightweight time-series
format (e.g., CSV or messagepack) should be considered for snapshot storage
if 15m paper trading is supported in Phase 4E scope.

Recommendation: start with JSON; document the 15m volume concern as a known
performance risk (see §15).

### PostgreSQL migration path

When session volume grows, the migration path is:
- `PaperTradingRepository` → `paper_trading_sessions` table
- `PaperAccountStore` → `paper_accounts` table (mutable) + `account_snapshots` table (append-only)
- `PaperOrderStore` → `paper_orders` table
- `PaperFillStore` → `paper_fills` table
- `PaperPositionStore` → `paper_positions` table

The store interfaces should be thin enough that the JSON-backed implementation can be
swapped for SQL-backed implementations without changing the service layer.

---

## §14 Workflow Design

### API surface

All routes under prefix `/api/v1/paper-trading/`.
All routes require `require_active_subscription` dependency.
All `session_id` path parameters validated with `validate_uuid_id()`.
Wrong-owner access → HTTP 404 (information hiding).

**Recommended route surface (9 routes):**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/paper-trading/sessions` | Create session (pending status) |
| `GET` | `/api/v1/paper-trading/sessions` | List user's sessions (no `strategy_json`, no `user_id` in response) |
| `GET` | `/api/v1/paper-trading/sessions/{session_id}` | Get session detail |
| `POST` | `/api/v1/paper-trading/sessions/{session_id}/activate` | Activate session (pending → running) |
| `POST` | `/api/v1/paper-trading/sessions/{session_id}/run-cycle` | Trigger one poll cycle |
| `POST` | `/api/v1/paper-trading/sessions/{session_id}/pause` | Pause session |
| `POST` | `/api/v1/paper-trading/sessions/{session_id}/resume` | Resume paused session |
| `POST` | `/api/v1/paper-trading/sessions/{session_id}/terminate` | Terminate session |
| `GET` | `/api/v1/paper-trading/sessions/{session_id}/signals` | List signals for session |
| `GET` | `/api/v1/paper-trading/sessions/{session_id}/orders` | List orders for session |
| `GET` | `/api/v1/paper-trading/sessions/{session_id}/fills` | List fills for session |
| `GET` | `/api/v1/paper-trading/sessions/{session_id}/positions` | List positions for session |
| `GET` | `/api/v1/paper-trading/sessions/{session_id}/account` | Get current account state |
| `GET` | `/api/v1/paper-trading/sessions/{session_id}/equity-curve` | Get equity curve snapshots |

### API response schema constraints

- No `strategy_json` in list or detail responses
- No `user_id` in list responses (bulk PII reduction)
- No `file_path` in any response
- `rejection_reason` in order responses must use structured codes, not raw exceptions
- `simulation_assumptions` present in detail response (session-level transparency)

### User workflow sequence

```
1. Create session
   POST /sessions
   Body: draft_id, symbol, timeframe, source_mode, provider_name,
         starting_equity, simulation_assumptions, max_concurrent_positions,
         max_drawdown_stop_pct (optional)
   Result: PaperTradingSession with status=pending

2. Activate session
   POST /sessions/{id}/activate
   Service: lifecycle check (>= backtested), warmup fetch, account creation
   Result: status=running; PT_SESSION_ACTIVATED audit event

3. Run cycle (user-triggered)
   POST /sessions/{id}/run-cycle
   Service: poll new bars, evaluate strategy, route intents, simulate fills
   Result: CycleResult with signal count, fill count, account summary

4. Observe
   GET /sessions/{id}/account        — current equity, drawdown, cash
   GET /sessions/{id}/positions      — open positions with unrealized P&L
   GET /sessions/{id}/fills          — fill history with gross/net price
   GET /sessions/{id}/equity-curve   — per-bar equity snapshots

5. Pause / Resume (optional)
   POST /sessions/{id}/pause
   POST /sessions/{id}/resume

6. Terminate or complete
   POST /sessions/{id}/terminate
   Service: force-close all open positions at last bar close;
            compute session metrics; transition to completed;
            PT_SESSION_COMPLETED audit event
```

### Frontend: `PaperTradingPanel` component

Analogous to `ForwardTestPanel` (Phase 4C.5).

Required views:
1. **Session list** — status badge, symbol/timeframe, equity, drawdown pct, fill count
2. **Create form** — draft_id, symbol, timeframe, starting_equity, fill_timing_model,
   fee_mode/value, slippage_mode/value, position_size_mode/value, max_concurrent_positions,
   max_drawdown_stop_pct (optional)
3. **Session detail** — account summary (equity, cash, drawdown), open positions table,
   fill history, signal vs fill comparison
4. **Equity curve** — line chart of equity over time (bar timestamps as x-axis)

The panel must never auto-poll. Run Cycle is user-triggered only.
No `setInterval` auto-polling in the frontend component.

---

## §15 Risks and Open Questions

### Risk 1: `next_bar_open` fill timing requires cross-bar state

**Severity:** High — affects correctness of fill simulation

For `next_bar_open` fill timing, the `PaperBrokerAdapter` must hold a pending order
from bar N and apply the fill at bar N+1's open. This requires the service's poll cycle
to carry forward pending orders between bar iterations.

The current `ForwardTestService._poll_cycle()` processes bars independently.
The paper trading service must extend this to track pending orders across bars
within a poll cycle, and across poll cycles if a cycle ends mid-sequence.

**Mitigation:** Design the broker adapter's `pending_orders` state to persist in the
session record between poll cycles, not in memory. Verify correctness with integration
tests that span two-cycle sequences.

---

### Risk 2: JSON-backed store performance at 15m timeframe

**Severity:** Medium — degrades user experience; no data loss

At 15m timeframe, a 30-day paper trading session produces ~1300 bars.
Each bar produces one `AccountStateSnapshot` plus potentially one signal, one order,
one fill. The equity curve JSON array will reach ~1300 entries.
Loading the full equity curve for display on each request degrades linearly.

**Mitigation:** Acceptable for Phase 4E if 15m is in scope. If performance is
unacceptable in testing, switch to CSV-backed snapshot storage for equity curve only.
The fuller PostgreSQL migration is the long-term solution.

---

### Risk 3: Drawdown stop check timing

**Severity:** Medium — affects correctness of session lifecycle

The drawdown stop check must fire after every fill and after every bar mark-to-market.
If the check only fires after fills, a sustained unrealized drawdown (no fills, but
open positions declining) will not trigger the stop until a fill occurs.

**Mitigation:** Ensure drawdown check runs in the per-bar update sequence (after
mark-to-market), not only in the post-fill update sequence.

---

### Risk 4: `PAPER_TESTED` lifecycle status may be absent

**Severity:** High — blocks session completion transition

If `PAPER_TESTED` is not in `backend/strategy_registry/lifecycle.py`,
the `FORWARD_TESTED → PAPER_TESTED` promotion path has no target state.

**Mitigation:** Verify at Phase 4E start. Add if absent. Confirm all lifecycle
gate checks in the strategy registry and promotion workflow reference the correct enum value.

---

### Risk 5: Force-close at session termination requires price availability

**Severity:** Medium — correctness risk at session termination

When a session transitions to `completed` or `terminated`, all open positions must
be force-closed at the last processed bar's close price. If `last_processed_bar_timestamp`
is null (session never ran a cycle), there is no price to close at.

**Mitigation:** Force-close should only fire when `last_processed_bar_timestamp` is
non-null AND at least one open position exists. If no positions are open at session end,
force-close is a no-op. Document this in the service layer.

---

### Risk 6: `next_bar_open` pending orders lost on service restart

**Severity:** Low for Phase 4E — paper trading is user-triggered; no background service

Because paper trading cycles are user-triggered (one HTTP request per cycle), there
is no background service that could be interrupted mid-cycle. However, if a cycle ends
with a pending `next_bar_open` order (the signal fired on the last bar of the cycle),
the pending order must be stored in the session record — not held only in memory —
so it survives the cycle boundary.

**Mitigation:** Store pending order IDs in the session record. The next run_cycle call
resolves them before evaluating new bars.

---

### Open Question OQ-1: Shared vs separate bar store

Should paper trading sessions share the same bar store as forward testing sessions
(keyed by session_id), or should `backend/paper_trading/stores.py` define a separate
`PaperTradingBarStore`?

**Recommendation:** Separate store class for clean module boundaries, but using identical
logic and storage format. Avoid cross-module storage dependencies.

---

### Open Question OQ-2: Session export format

The `PT_SESSION_EXPORTED` audit event is defined. The export format (CSV, JSON, Parquet)
and the export route are not specified in the architecture documents.

**Recommendation:** Defer export format definition to Phase 4E implementation.
The export route and schema should be designed alongside the `PaperTradingPanel`
session detail view.

---

## §16 Implementation Roadmap

Paper trading implementation follows the same phased pattern as forward testing (Phase 4C).
Recommended decomposition into 6 sub-phases:

---

### Phase 4E.1 — Models and Repository Foundation

**Scope:**
- `backend/paper_trading/` module creation (new directory)
- `PaperTradingSession`, `SimulationAssumptions`, `PaperAccount`, `PaperOrder`,
  `PaperFill`, `PaperPosition`, `AccountStateSnapshot` model definitions
- `PaperTradingRepository` (JSON-backed, ownership-scoped)
- `PaperAccountStore`, `PaperOrderStore`, `PaperFillStore`, `PaperPositionStore`
- 29 `PT_*` `AuditEventKind` values added to `backend/core/audit.py`
- `PAPER_TESTED` added to `StrategyLifecycleStatus` if absent
- Unit tests for all models and store operations

**No service logic. No routes. No broker adapter. No frontend.**

---

### Phase 4E.2 — PaperBrokerAdapter and Fill Simulation

**Scope:**
- `backend/paper_trading/broker_adapter.py` — `PaperBrokerAdapter` class
- Both fill timing models (`signal_bar_close`, `next_bar_open`)
- Slippage simulation (`none`, `fixed`, `percentage`)
- Fee simulation (`none`, `flat`, `percentage`)
- Position sizing resolution (`equity_fraction`, `fixed_quantity`, `fixed_cash`)
- Intent validation (cash check, max_positions check, close target check)
- Account state update sequence (post-fill and post-bar)
- Drawdown stop check
- `backend/execution/gateway.py` — minimal gateway routing to `PaperBrokerAdapter`
- Unit tests: determinism, fill price correctness, rejection codes, drawdown trigger

**No service integration yet. Broker adapter tested in isolation.**

---

### Phase 4E.3 — PaperTradingService

**Scope:**
- `backend/paper_trading/service.py` — `PaperTradingService` class
- `create_session()`, `activate_session()`, `run_cycle()`, `pause_session()`,
  `resume_session()`, `terminate_session()`
- Integration of `PaperBrokerAdapter` into the poll cycle (after signal recording)
- `next_bar_open` pending order persistence across cycle boundaries
- Force-close on termination/completion
- `metrics.py` — session-level metrics calculator
- Unit + integration tests for service, including two-cycle `next_bar_open` scenarios

---

### Phase 4E.4 — API Routes and Schemas

**Scope:**
- `backend/api/routes/paper_trading.py` — all routes (14 routes defined in §14)
- `backend/api/schemas/paper_trading.py` — request and response schemas
- Route registration in `backend/api/main.py`
- Security: ownership enforcement, `require_active_subscription`, `validate_uuid_id()`
- Schema constraints: no `strategy_json`, no `user_id` in lists, no `file_path`
- Unit tests: ownership isolation, lifecycle gate enforcement, entitlement gate

---

### Phase 4E.5 — Frontend PaperTradingPanel

**Scope:**
- `frontend/src/components/PaperTradingPanel.tsx`
- `frontend/src/api/paperTrading.ts` — API client
- `frontend/src/types/paperTrading.ts` — TypeScript types
- Session list with status badges and equity summary
- Create form with full simulation assumption inputs
- Session detail: account summary, open positions, fill history, equity chart
- Nav tab in `App.tsx`
- Frontend tests: loading/empty/error states, create form, action buttons

---

### Phase 4E.6 — Integration Validation

**Scope:**
- `tests/integration/test_paper_trading_integration.py`
- End-to-end workflow: create → activate → run cycle → pause → resume → terminate
- Fill correctness: signal_bar_close and next_bar_open
- Drawdown stop trigger
- Ownership isolation across users
- Lifecycle gate enforcement (VALIDATED rejected; BACKTESTED accepted)
- Entitlement gate (403 without subscription)
- Audit event emission for PT_ events
- Security invariants (no strategy_json, no file_path, no user_id in lists)
- Readiness rating produced after validation

---

## §17 Readiness Assessment

### Phase 4C Forward Testing — Foundation Quality

Phase 4C delivered:
- Fully operational `ForwardTestService` with poll cycle, gap detection, audit emission
- 9 API routes with complete ownership, entitlement, and lifecycle enforcement
- `ForwardTestPanel` UI with session management, signal view, and nav integration
- 65 integration tests across 10 sections; all passing
- Integration readiness rating: **B**

This is a high-quality foundation. Paper trading inherits every component listed in §3
without modification.

### Readiness for Phase 4E

**Codebase readiness: HIGH**

All reusable components are production-grade and tested.
The FT service pattern is well-understood and ready for extension.
The gap between FT and PT is well-defined: the execution layer is the only new
architectural concern, and it is fully specified in `PAPER_TRADING_ARCHITECTURE.md`.

**Architecture readiness: HIGH**

All four architecture documents are complete and internally consistent:
- `PAPER_TRADING_ARCHITECTURE.md` — fully defines the broker adapter, fill simulation,
  account model, position model, order model, and session extension
- `EXECUTION_CONTRACT.md` — establishes the gateway contract and safety invariants
- `EXECUTION_AUDIT_MODEL.md` — defines the full PT_ audit taxonomy
- `STRATEGY_PROMOTION_LIFECYCLE.md` — defines the promotion governance path

**Open risks: MANAGEABLE**

The `next_bar_open` cross-bar state risk (§15 Risk 1) is the most architecturally
significant. It requires careful design of the pending order persistence mechanism.
All other risks are implementation-level concerns with clear mitigations.

**Phase 4D overall rating: A−**

All architecture documents are complete. All reusable components are ready.
The implementation plan is actionable and phased. The remaining uncertainty
is implementation complexity, not architectural ambiguity.

The A− (vs A) reflects: the `next_bar_open` pending order state concern is real
and requires explicit design work before Phase 4E.3 begins; and the `PAPER_TESTED`
enum presence needs verification before Phase 4E.1 is considered ready to merge.

---

## §18 Recommended Next Phase

### Recommended: Phase 4E.1 — Models and Repository Foundation

**Start immediately.** All prerequisites are complete:
- Architecture fully specified
- Codebase foundation (Phase 4C) production-grade
- Reusable components inventoried and verified
- Implementation roadmap phased and scoped

**Phase 4E.1 scope is low-risk** — it is pure model and store definitions with no
service logic, no broker adapter, and no routes. It establishes the data layer
that all subsequent sub-phases build on.

**Before starting Phase 4E.1, verify:**
1. `PAPER_TESTED` presence in `backend/strategy_registry/lifecycle.py` (add if absent)
2. `backend/paper_trading/` directory does not already exist (if it does, survey its contents)

### Phase 4E sequencing

```
Phase 4E.1 — Models + repository foundation     (prerequisite for all)
    ↓
Phase 4E.2 — PaperBrokerAdapter + fill simulation  (prerequisite for service)
    ↓
Phase 4E.3 — PaperTradingService                (prerequisite for routes)
    ↓
Phase 4E.4 — API routes + schemas               (prerequisite for frontend)
    ↓
Phase 4E.5 — Frontend PaperTradingPanel         (prerequisite for integration)
    ↓
Phase 4E.6 — Integration validation             (terminal)
```

The sequence is strictly linear. Each phase depends on the previous phase being
production-grade before the next begins. Do not implement routes before the service
is tested. Do not implement the frontend before the routes are tested.

### Deferred

The following are explicitly deferred beyond Phase 4E:

| Item | Deferred to |
|------|-------------|
| PostgreSQL migration for paper trading stores | Phase 4F or later |
| Multi-symbol portfolio support | Phase 4F or later |
| Limit order support | Phase 4F or later |
| Session export (CSV/JSON/Parquet) | Phase 4E.4 or later |
| Short position support | Phase 4F or later |
| Sub-15m timeframe paper trading | Phase 4H (after intraday engine optimization) |
| Live trading infrastructure | Phase 5+ |
| Broker adapter implementations (IBKR, Binance) | Phase 5+ |

---

*End of Phase 4D Architecture Review*
