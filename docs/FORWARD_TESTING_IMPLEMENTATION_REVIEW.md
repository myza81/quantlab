# FORWARD_TESTING_IMPLEMENTATION_REVIEW.md

Phase 4B — Forward Testing Runtime: Architecture Review and Implementation Planning

Produced by the Primary Implementation Agent after a full codebase survey against
the completed Phase 4A architecture documents.  
No runtime code was written.  
This document is the implementation authority for Phase 4C and beyond.

---

## Table of Contents

1. [Purpose and Scope](#1-purpose-and-scope)
2. [Architecture Documents Reviewed](#2-architecture-documents-reviewed)
3. [Directly Reusable Components](#3-directly-reusable-components)
4. [Components Requiring Extension](#4-components-requiring-extension)
5. [Missing Components](#5-missing-components)
6. [Lifecycle State Machine Gap Analysis](#6-lifecycle-state-machine-gap-analysis)
7. [Audit Infrastructure Gap Analysis](#7-audit-infrastructure-gap-analysis)
8. [Data Acquisition Design Requirements](#8-data-acquisition-design-requirements)
9. [ForwardTestSession Model Design](#9-forwardtestsession-model-design)
10. [API Surface Design](#10-api-surface-design)
11. [Tool Computation Strategy for Forward Testing](#11-tool-computation-strategy-for-forward-testing)
12. [Ownership, Entitlement, and Security](#12-ownership-entitlement-and-security)
13. [Frontend Integration Requirements](#13-frontend-integration-requirements)
14. [Testing Strategy](#14-testing-strategy)
15. [Phased Implementation Roadmap](#15-phased-implementation-roadmap)
16. [Risks and Open Questions](#16-risks-and-open-questions)
17. [Non-Negotiable Constraints](#17-non-negotiable-constraints)

---

## §1 Purpose and Scope

This document is the implementation planning artifact for the QuantLab Forward Testing Runtime.  
It reviews the actual codebase state against the architecture contracts established in Phase 4A
and produces an actionable, phased implementation plan.

**What this document covers:**

- Inventory of what can be reused without modification
- Inventory of what needs extension
- Inventory of what is completely absent and must be built
- Specific design decisions for the session model, API surface, and data layer
- Explicit gap analysis against the lifecycle and audit contracts
- Ordered roadmap for phased delivery

**What this document does not cover:**

- Paper trading (Phase 4A.3) — separate phase after forward testing is stable
- Live trading infrastructure — deferred (see TASKS.md)
- Broker adapters — deferred
- Distributed execution — deferred

---

## §2 Architecture Documents Reviewed

The following documents were read in full before producing this review:

| Document | Role |
|----------|------|
| `docs/EXECUTION_CONTRACT.md` | Core execution philosophy, 7 objects, session model, safety constraints |
| `docs/FORWARD_TESTING_ARCHITECTURE.md` | ForwardTestSession model, lifecycle states, REST-polling model, signal recording |
| `docs/PAPER_TRADING_ARCHITECTURE.md` | Defines boundary between forward testing and paper trading |
| `docs/EXECUTION_AUDIT_MODEL.md` | 6 audit categories, FT_ event taxonomy, 13-field envelope |
| `docs/BACKTESTING_ENGINE_CONTRACT.md` | Pipeline contracts reused for forward testing evaluation |
| `docs/STRATEGY_PROMOTION_LIFECYCLE.md` | Promotion lifecycle, FORWARD_TESTED gate, evidence requirements |
| `agent/HANDOFF.md` | Current platform state, maturity summary |
| `agent/TASKS.md` | Active roadmap |

The following backend modules were read to understand actual implementation state:

| Module | Relevance |
|--------|-----------|
| `backend/strategy_registry/lifecycle.py` | Current 6-state enum — gap analysis |
| `backend/strategy_registry/historical_evaluator.py` | Core evaluate_history() — FT reuse |
| `backend/strategy_registry/draft_repository.py` | Repository pattern — template for FT |
| `backend/strategy_registry/drafts.py` | StrategyDraft model — snapshot design |
| `backend/tools/historical_computation.py` | Tool pipeline — FT computation strategy |
| `backend/api/services/backtest_run_service.py` | Full pipeline pattern — FT service template |
| `backend/services/ohlcv_service.py` | Historical-only ingestion — extension required |
| `backend/data_providers/provider_factory.py` | Factory pattern — already supports Yahoo/Polygon |
| `backend/core/audit.py` | Log-only audit, ~33 events, no FT taxonomy |
| `backend/auth/entitlement.py` | require_active_subscription, require_admin_role |
| `backend/api/routes/drafts.py` | Ownership enforcement pattern |
| `backend/api/main.py` | Current router registration |
| `backend/execution/__init__.py` | Empty placeholder |
| `backend/forward_testing/__init__.py` | Empty placeholder |
| `backend/jobs/__init__.py` | Empty placeholder |

---

## §3 Directly Reusable Components

These components require no modification for forward testing use.

---

### 3.1 `evaluate_history()` — Per-Bar Evaluation Engine

**Location:** `backend/strategy_registry/historical_evaluator.py`

```python
def evaluate_history(input: HistoricalEvaluationInput) -> HistoricalEvaluationResult
```

This is the single most important reusable component.  
The function processes bars one at a time internally via `TwoBarEvaluationContext`, which
carries the previous bar's tool output values forward to support crossover operator detection.

**How forward testing reuses it:**  
For each polling cycle, pass the warmup bars + new bar(s) as a full batch.  
The per-bar results slice out the new bars only.  
The evaluation engine remains unmodified — it does not need to know it is being called from
a forward testing scheduler rather than a backtest runner.

**Architecture boundary on this module:**

```
MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.forward_testing
    backend.backtesting
```

This boundary is correct and should remain.  
Forward testing code imports from this module — never the reverse.

---

### 3.2 `compile_semantics()` — Semantic Compilation

**Location:** `backend/strategy_registry/semantic_compiler.py`

Compiles a `StrategySemantics` object into an `EvaluationPlan`.  
For forward testing, the plan is compiled once at session start and reused across all
polling cycles.  
No modification required.

---

### 3.3 `StrategyDraft` and `DraftRepository` — Repository Pattern

**Location:**  
- `backend/strategy_registry/drafts.py` — `StrategyDraft` model  
- `backend/strategy_registry/draft_repository.py` — `DraftRepository`

`DraftRepository` is the exact template for `ForwardTestRepository`.  
Key characteristics to replicate:

- JSON filesystem storage with atomic write (tempfile + rename)
- `owner_id` enforcement: wrong-owner access raises `*NotFoundError` (information hiding, maps to HTTP 404)
- `load(id, owner_id=...)` — ownership-scoped retrieval
- `list_all(owner_id=...)` — ownership-filtered list
- Active vs. archived path separation (`storage/ft_sessions/` vs. `storage/ft_sessions/archive/`)

`StrategyDraft` is frozen (`ConfigDict(frozen=True, extra="forbid")`).  
`ForwardTestSession` should follow the same immutability pattern (state transitions via replace/new object).

---

### 3.4 `ProviderAdapterFactory` — Provider Resolution

**Location:** `backend/data_providers/provider_factory.py`

The factory already supports Yahoo Finance and Polygon.io — the two providers suitable for
live bar polling (real-time or near-real-time data).

**Current registered providers:**

| Provider | Use for FT |
|----------|-----------|
| `yahoo`  | Yes — near-real-time intraday (20-min delayed but free) |
| `polygon` | Yes — real-time with API key |
| `csv`    | No — static files, not suitable for live polling |
| `parquet` | No — static files, not suitable for live polling |

The vault-based API key resolution for Polygon is already in place — no changes to the factory.  
Forward testing service calls `factory.build("polygon", api_key=resolved_key, ...)` exactly as
the backtest pipeline does.

---

### 3.5 `require_active_subscription` — Entitlement Guard

**Location:** `backend/auth/entitlement.py`

All forward testing routes must gate on `require_active_subscription`.  
This guard:
- Passes admins unconditionally (role-based governance)
- Passes regular users with active, non-expired subscriptions
- Performs lazy expiry evaluation on every request
- Emits `ENTITLEMENT_DENIED` audit event on rejection

No modification required.  
Use as `Depends(require_active_subscription)` on all FT route handlers.

---

### 3.6 `validate_uuid_id()` — Path Parameter Safety

**Location:** `backend/core/request_validation.py`

Reuse exactly as in `drafts.py` and `backtest_runs.py`.  
Apply to every `{session_id}` path parameter in FT routes.  
Returns HTTP 400 before any filesystem path construction.

---

### 3.7 `AuditEvent` / `emit_audit_event()` — Audit Infrastructure

**Location:** `backend/core/audit.py`

The audit emission infrastructure is reusable as-is.  
`emit_audit_event(AuditEvent(event_kind=..., details=...))` works for any new event kinds.  
The infrastructure gap is in the taxonomy (see §7) and persistence (log-only) — not the
emission API itself.

---

### 3.8 `BacktestRunService` Pipeline Pattern

**Location:** `backend/api/services/backtest_run_service.py`

The 10-step pipeline in `create_backtest_run()` is the template for the forward testing
session activation flow:

```
load draft → validate semantics → compile plan → compute tool outputs
→ evaluate new bar(s) → extract signal events → extract trade intents
→ record ForwardTestSignal → persist session → return result
```

Not an exact copy — forward testing is event-driven and stateful across polling cycles — but
the pipeline decomposition, draft loading, tool registry usage, and report persistence
patterns are directly applicable.

---

## §4 Components Requiring Extension

These components exist and are correct for their current use but need new methods or
behaviors to support forward testing.

---

### 4.1 `OHLCVService` — Historical-Only to Polling-Aware

**Location:** `backend/services/ohlcv_service.py`

Current signature:

```python
def get_ohlcv(request: OHLCVRequest) -> NormalizedOHLCVDataset
```

The module's own docstring states:

> "NOT a live-streaming system. Historical / research-grade ingestion only."

**Two new methods required:**

**Method A — Warmup Bar Fetch:**

```python
def get_recent_bars(
    symbol: str,
    timeframe: str,
    bar_count: int,
    provider_name: str,
    credential_id: str | None = None,
    user_id: str | None = None,
) -> NormalizedOHLCVDataset
```

Purpose: fetch the most recent `N` completed bars for warmup at session start.  
`N` = max warmup requirement across all configured tools + safety buffer.  
These bars will NOT trigger signals — they exist solely to seed tool states correctly.

**Method B — Incremental Poll:**

```python
def get_bars_since(
    symbol: str,
    timeframe: str,
    since_timestamp: datetime,
    provider_name: str,
    credential_id: str | None = None,
    user_id: str | None = None,
) -> NormalizedOHLCVDataset
```

Purpose: fetch completed bars with `timestamp > since_timestamp` since the last processed bar.  
Returns empty dataset (not an error) when no new completed bars are available.  
Bar finalization (the "unseen-bar detection" defined in FORWARD_TESTING_ARCHITECTURE.md) is
implemented here by comparing `bar.timestamp` to the expected next timestamp based on timeframe.

**Critical invariant:**  
Both methods must use the existing provider abstraction and vault credential resolution.  
No direct provider imports in this service.  
Sanitize all provider errors before returning to callers — identical to the existing pattern.

---

### 4.2 `AuditEventKind` — Taxonomy Extension

**Location:** `backend/core/audit.py`

The current `AuditEventKind` enum has ~33 events covering credentials, auth, subscription,
and governance safety.  
All execution-domain events (`FT_`, `PT_`, `GOV_`, `LT_`) are absent.

**Required additions for forward testing (Phase 4C minimum):**

```python
# Forward Testing events
FT_SESSION_CREATED       = "FT_SESSION_CREATED"
FT_SESSION_STARTED       = "FT_SESSION_STARTED"
FT_SESSION_PAUSED        = "FT_SESSION_PAUSED"
FT_SESSION_RESUMED       = "FT_SESSION_RESUMED"
FT_SESSION_STOPPED       = "FT_SESSION_STOPPED"
FT_SESSION_COMPLETED     = "FT_SESSION_COMPLETED"
FT_SESSION_FAILED        = "FT_SESSION_FAILED"
FT_BAR_EVALUATED         = "FT_BAR_EVALUATED"
FT_SIGNAL_RECORDED       = "FT_SIGNAL_RECORDED"
FT_DATA_FETCH_ERROR      = "FT_DATA_FETCH_ERROR"
FT_PROVIDER_TIMEOUT      = "FT_PROVIDER_TIMEOUT"
FT_WARMUP_COMPLETED      = "FT_WARMUP_COMPLETED"

# Governance events (for promotion)
GOV_STRATEGY_PROMOTED    = "GOV_STRATEGY_PROMOTED"
GOV_PROMOTION_REVOKED    = "GOV_PROMOTION_REVOKED"
GOV_STRATEGY_APPROVED_FOR_LIVE = "GOV_STRATEGY_APPROVED_FOR_LIVE"
```

The existing `AuditEvent` frozen dataclass fields are sufficient for forward testing:  
`event_kind`, `provider_name`, `details`, `timestamp`.  
The `correlation_id` field defined in EXECUTION_AUDIT_MODEL.md is not yet in the dataclass
and should be added when implementing FT audit emission.

---

### 4.3 `StrategyLifecycleStatus` — Three Missing States

**Location:** `backend/strategy_registry/lifecycle.py`

See §6 for full gap analysis.  
The extension itself is straightforward — adding enum values and transition rules.

---

### 4.4 `compute_tool_outputs_for_history()` — Incremental Window Usage

**Location:** `backend/tools/historical_computation.py`

The function processes an entire bar sequence in one call, which is correct for backtesting.  
For forward testing, it will be called on a growing window (warmup bars + new bar(s)) on
each polling cycle.

The function is stateless — it recomputes from scratch each call.  
This is architecturally correct for forward testing's initial implementation (no incremental
optimization needed until performance profiling identifies it as a bottleneck).

**What callers must do:**  
On each polling cycle, maintain the full bar history seen so far in the session.  
Pass the full window (not just new bars) to `compute_tool_outputs_for_history()`.  
Use `build_bar_tool_outputs()` to index results.  
Evaluate only the new bars from `evaluate_history()` output.

This re-computation approach is deterministic, testable, and aligned with the backtesting
engine contract — no special code path needed.

---

## §5 Missing Components

These components do not exist in any form and must be built from scratch.

---

### 5.1 `ForwardTestSession` Model

**Location to create:** `backend/forward_testing/session.py`

The session model must capture all state required to resume, inspect, and persist a forward
test across polling cycles. Minimum required fields (aligned with FORWARD_TESTING_ARCHITECTURE.md):

```python
class ForwardTestSession:
    session_id: str              # UUID
    draft_id: str                # strategy under test
    user_id: str                 # owner (from JWT, never from request body)
    symbol: str
    timeframe: str
    provider_name: str
    credential_id: str | None    # vault credential for Polygon; None for Yahoo
    warmup_bar_count: int        # computed from toolset at session creation
    status: ForwardTestSessionStatus
    created_at: datetime
    started_at: datetime | None
    stopped_at: datetime | None
    last_processed_bar_timestamp: datetime | None
    bars_processed: int
    signals_recorded: int
    draft_snapshot: StrategyDraftSnapshot  # immutable copy at session start
    evaluation_plan_hash: str    # SHA-256 of compiled plan (reproducibility)
```

`ForwardTestSessionStatus` enum:
```
CREATED → ACTIVE → PAUSED → STOPPED (terminal)
ACTIVE → COMPLETED (terminal, if time-bound)
Any → FAILED (terminal, on unrecoverable error)
```

`StrategyDraftSnapshot` captures the strategy state at session activation:
```python
class StrategyDraftSnapshot:
    draft_id: str
    display_name: str
    lifecycle_status_at_start: str
    semantics_hash: str | None
    toolset_hash: str | None
```

This snapshot design mirrors the `DraftProvenance` pattern in `BacktestRunSummary`.

---

### 5.2 `ForwardTestRepository`

**Location to create:** `backend/forward_testing/session_repository.py`

Exactly mirrors `DraftRepository` structure:

```python
class ForwardTestRepository:
    def save(self, session: ForwardTestSession) -> None: ...
    def load(self, session_id: str, owner_id: str) -> ForwardTestSession: ...
    def update(self, session: ForwardTestSession, owner_id: str) -> None: ...
    def list_all(self, owner_id: str) -> list[ForwardTestSession]: ...
    def list_active(self, owner_id: str) -> list[ForwardTestSession]: ...
    def stop(self, session_id: str, owner_id: str) -> None: ...
```

Storage layout (under `settings.forward_test_sessions_storage_path`):

```
storage/
  ft_sessions/
    {session_id}.json          # CREATED, ACTIVE, PAUSED
    archive/
      {session_id}.json        # STOPPED, COMPLETED, FAILED
```

Ownership enforcement identical to `DraftRepository`:
- Wrong-owner `load()` raises `ForwardTestSessionNotFoundError` (same as not-found)
- `user_id` never from request body — always from `owner_id` parameter (passed from JWT)

---

### 5.3 `ForwardTestSignal`

**Location to create:** `backend/forward_testing/signal.py`

Captures one signal event produced by a forward testing polling cycle.  
Per FORWARD_TESTING_ARCHITECTURE.md:

```python
class ForwardTestSignal:
    signal_id: str           # UUID
    session_id: str
    bar_index: int           # relative within the session's bar window
    bar_timestamp: datetime  # timestamp of the bar that triggered the signal
    signal_type: str         # "entry" | "exit"
    rule_id: str             # the semantic rule that fired
    recorded_at: datetime    # server time of recording (not bar time)
    tool_outputs_snapshot: dict[str, float]  # tool values at this bar
```

Signal persistence: stored as a JSON list alongside the session record, or in a separate
`{session_id}_signals.json` file under the same storage directory.  
Recommendation: separate file per session for clean separation of session state from signal log.

---

### 5.4 `ForwardTestService`

**Location to create:** `backend/api/services/forward_test_service.py`

Core service functions:

```python
def create_session(
    request: CreateForwardTestSessionRequest,
    repository: ForwardTestRepository,
    draft_repository: DraftRepository,
    user_id: str,
) -> ForwardTestSession

def start_session(
    session_id: str,
    repository: ForwardTestRepository,
    user_id: str,
) -> ForwardTestSession

def poll_session(
    session_id: str,
    repository: ForwardTestRepository,
    signal_store: ForwardTestSignalStore,
    ohlcv_service: OHLCVService,
    user_id: str,
) -> ForwardTestPollResult

def stop_session(
    session_id: str,
    repository: ForwardTestRepository,
    user_id: str,
) -> ForwardTestSession

def get_session_signals(
    session_id: str,
    signal_store: ForwardTestSignalStore,
    user_id: str,
) -> list[ForwardTestSignal]
```

The `poll_session()` function implements the polling cycle:

1. Load session (ownership check)
2. Verify session is in `ACTIVE` status
3. Fetch new bars since `last_processed_bar_timestamp` via `OHLCVService.get_bars_since()`
4. If no new completed bars: return `ForwardTestPollResult(new_bars=0, new_signals=[])`
5. Reconstruct full bar window (stored history + new bars)
6. Compute tool outputs over full window
7. Evaluate new bars only via `evaluate_history()`
8. Extract signal events from new-bar evaluation results
9. Persist any new signals
10. Update `last_processed_bar_timestamp`, increment `bars_processed` and `signals_recorded`
11. Persist updated session
12. Emit `FT_BAR_EVALUATED` and `FT_SIGNAL_RECORDED` audit events

---

### 5.5 Forward Testing API Routes

**Location to create:** `backend/api/routes/forward_testing.py`

No forward testing routes exist in `backend/api/main.py`.  
The following routes are required (minimum viable set):

```
POST   /forward-testing/sessions              — create session
GET    /forward-testing/sessions              — list user's sessions
GET    /forward-testing/sessions/{session_id} — get session detail
POST   /forward-testing/sessions/{session_id}/start  — activate session
POST   /forward-testing/sessions/{session_id}/stop   — stop session
POST   /forward-testing/sessions/{session_id}/poll   — trigger poll cycle
GET    /forward-testing/sessions/{session_id}/signals — list session signals
```

All routes:
- `Depends(require_active_subscription)` — entitlement gate
- `validate_uuid_id(session_id, "session_id")` — path parameter safety
- `user_id` from `current_user.user_id` only
- Wrong-owner → HTTP 404

---

### 5.6 Polling Scheduler / Background Worker

**Location to create:** `backend/jobs/forward_test_poller.py`

The `backend/jobs/` package is an empty placeholder.

The FORWARD_TESTING_ARCHITECTURE.md defines a REST-polling model (not WebSocket streaming).  
The implementation plan supports two polling architectures:

**Option A — Client-Driven Polling (Recommended for Phase 4C):**
The frontend calls `POST /forward-testing/sessions/{session_id}/poll` on a timer.  
No background worker required.  
The server executes the poll cycle synchronously on each request.  
Simple to implement, test, and reason about.  
Limitation: depends on browser tab being open.

**Option B — Server-Driven Polling (Phase 4D or later):**
A background scheduler (e.g., APScheduler, Celery beat) polls active sessions on a
server-managed interval.  
More robust (runs when browser is closed) but adds scheduler infrastructure.  
Recommended for production readiness but deferred until Option A is validated.

**Phase 4C implements Option A.**  
The polling endpoint exists; the frontend is responsible for calling it.  
A comment in the route docstring should note the upgrade path to Option B.

---

### 5.7 `settings.forward_test_sessions_storage_path`

**Location:** `backend/core/config.py`

A new `settings` field is required:

```python
forward_test_sessions_storage_path: str = "storage/ft_sessions"
```

Following the same pattern as `settings.drafts_storage_path` and
`settings.backtest_runs_storage_path`.  
The route layer injects this via `Depends(get_forward_test_repository)` in
`backend/api/dependencies.py`.

---

### 5.8 Bar History Store

**Location to create:** `backend/forward_testing/bar_store.py`

The polling cycle requires access to the full bar window accumulated over the session
(warmup bars + all bars seen in previous polling cycles) in order to recompute tool
outputs correctly.

Design: a lightweight per-session JSON store of accumulated `NormalizedOHLCV` bars.

```
storage/
  ft_sessions/
    {session_id}.json              # session metadata
    {session_id}_bars.json         # accumulated bar history (grows each poll)
    {session_id}_signals.json      # signal log (appended each poll)
```

Maximum bar count cap: aligned with `MAX_BACKTEST_BARS` default (50,000) — an active FT
session should rarely need more than a few hundred to a few thousand bars.

---

## §6 Lifecycle State Machine Gap Analysis

---

### 6.1 Current Implementation State

**File:** `backend/strategy_registry/lifecycle.py`

Current enum values:

```python
class StrategyLifecycleStatus(str, Enum):
    DRAFT          = "draft"
    VALIDATED      = "validated"
    BACKTESTED     = "backtested"
    PAPER_TESTED   = "paper_tested"
    APPROVED_FOR_LIVE = "approved_for_live"
    ARCHIVED       = "archived"
```

Current allowed transitions (from `ALLOWED_TRANSITIONS`):

```
draft          → validated, archived
validated      → backtested, draft, archived
backtested     → paper_tested, validated, archived
paper_tested   → approved_for_live, backtested, archived
approved_for_live → archived
archived       → (terminal)
```

---

### 6.2 States Missing Against STRATEGY_PROMOTION_LIFECYCLE.md

The authoritative lifecycle (Phase 4A.5) defines 9 states.  
Three are absent from the current implementation:

| Missing State | Why Needed | When to Add |
|---------------|-----------|-------------|
| `FORWARD_TESTED` | Captures that a strategy has completed a forward testing session; gates promotion to PAPER_TESTED | Phase 4C — at session completion |
| `LIVE` | Runtime state indicating an active live trading session | Phase 4E+ (live trading, deferred) |
| `REVOKED` | Governance-triggered state for high-stakes revocations from LIVE/APPROVED_FOR_LIVE/PAPER_TESTED | Phase 4E+ |

---

### 6.3 Backward Compatibility Issue

The current transition `backtested → paper_tested` bypasses the future `FORWARD_TESTED` gate.

This was an explicit Phase 4A.5 design decision: existing strategies that reached
`backtested` before the `forward_tested` state existed must continue to function.

**Resolution for Phase 4C:**  
When `FORWARD_TESTED` is added to the enum, the transition table should be updated to:

```
backtested → forward_tested, validated, archived    # forward_tested replaces paper_tested here
forward_tested → paper_tested, backtested, archived  # new gate in path
```

**The legacy direct path `backtested → paper_tested` should be removed** once `FORWARD_TESTED`
is added. Existing strategies in `backtested` state can transition through `FORWARD_TESTED`
by completing a forward testing session.

If backward compatibility for the legacy path is required (e.g., strategies already at
`paper_tested` that bypassed FT), those are grandfather-claused — they remain at their
current state and are not demoted.

---

### 6.4 Lifecycle Enforcement Gap

Current lifecycle comment in `lifecycle.py`:

> "lifecycle does not gate API access or trigger execution"

For forward testing, the lifecycle MUST gate session activation.  
A session `start` operation on a draft in `DRAFT` or `VALIDATED` status (i.e., below `BACKTESTED`)
should be rejected — the strategy has not been backtested and is not eligible for forward testing
(per STRATEGY_PROMOTION_LIFECYCLE.md §10: technical minimum for FT session activation is `backtested`).

**Implementation:**  
Add a check in `ForwardTestService.start_session()`:

```python
if draft.lifecycle_status.value not in {"backtested", "forward_tested", "paper_tested", "approved_for_live"}:
    raise ForwardTestSessionError(
        "Strategy must be in at least 'backtested' status to start a forward test session."
    )
```

This does NOT require changing the lifecycle module — it is enforced at the service layer,
consistent with the existing architecture boundary.

---

## §7 Audit Infrastructure Gap Analysis

---

### 7.1 Current State

`backend/core/audit.py`:

- `AuditEventKind` enum: ~33 event kinds
- `AuditEvent` frozen dataclass: `event_kind`, `provider_name`, `details`, `timestamp`
- `emit_audit_event()`: emits JSON to `quantlab.audit` Python logger at INFO level
- **No persistence.** No DB store. No query capability.
- **No execution taxonomy.** `FT_`, `PT_`, `GOV_`, `LT_` prefixes are all absent.

---

### 7.2 What Must Be Added for Forward Testing

**New `AuditEventKind` values** (defined in §4.2):  
`FT_SESSION_CREATED`, `FT_SESSION_STARTED`, `FT_SESSION_PAUSED`, `FT_SESSION_RESUMED`,
`FT_SESSION_STOPPED`, `FT_SESSION_COMPLETED`, `FT_SESSION_FAILED`,
`FT_BAR_EVALUATED`, `FT_SIGNAL_RECORDED`, `FT_DATA_FETCH_ERROR`,
`FT_PROVIDER_TIMEOUT`, `FT_WARMUP_COMPLETED`

**`correlation_id` field on `AuditEvent`:**  
EXECUTION_AUDIT_MODEL.md §4 defines a 13-field common audit record envelope including
`correlation_id` (links audit events for a single session lifecycle).  
The current `AuditEvent` dataclass lacks this field.  
Add `correlation_id: str | None = None` to `AuditEvent`.  
For FT, pass `session_id` as `correlation_id` on all FT audit events.

---

### 7.3 Audit Persistence Decision

The current audit system is log-only.  
EXECUTION_AUDIT_MODEL.md §8 defines retention tiers:
- Governance evidence and live trading fills → permanent
- Forward test signals and paper fills → minimum 2 years
- Session events → minimum 1 year

**For Phase 4C:**  
Accept log-only audit initially.  
`emit_audit_event()` already outputs structured JSON to the `quantlab.audit` logger.  
Add a clear comment to `ForwardTestService` noting the log-only limitation and that
audit persistence (database store or structured file store) is a deferred Phase 4E+ concern.

**Do NOT attempt to build audit persistence in Phase 4C.**  
It is a significant infrastructure addition (storage schema, query layer, retention policies)
that should be scoped as a separate phase after forward testing is functional.

---

### 7.4 Audit Events That Must Fire in Phase 4C

At minimum, the following must be emitted (even as log-only) during Phase 4C:

| Event | When |
|-------|------|
| `FT_SESSION_CREATED` | Session record first persisted |
| `FT_SESSION_STARTED` | Session transitions to ACTIVE |
| `FT_SESSION_STOPPED` | Session stopped by user |
| `FT_SESSION_FAILED` | Session reaches FAILED terminal state |
| `FT_SIGNAL_RECORDED` | Each new signal recorded |
| `FT_DATA_FETCH_ERROR` | Provider error during polling |

---

## §8 Data Acquisition Design Requirements

---

### 8.1 OHLCVService Extension

The two new methods described in §4.1 (`get_recent_bars()` and `get_bars_since()`) must:

1. Use `OHLCVService._resolve_provider()` (or equivalent) to get an adapter via the factory
2. Resolve Polygon credentials from vault using the existing `credential_id` → `VaultService.resolve_secret()` pattern — never accept raw key from caller
3. Sanitize all provider errors before returning to callers (same as existing `get_ohlcv()`)
4. Not cache forward-testing fetches in the existing OHLCV store (forward test bars are
   live/near-live; caching live data introduces staleness risk). Use `BYPASS_CACHE` policy.

---

### 8.2 Bar Finalization Model

A polling cycle fetches bars since the last processed timestamp.  
**Critical:** Only return bars whose timeframe period is confirmed complete.

Bar finalization rule (from FORWARD_TESTING_ARCHITECTURE.md §7):

> A bar is considered "finalized" when the server clock has passed the bar's expected
> close timestamp by at least one timeframe period.

Implementation: when `get_bars_since()` receives bars from the provider, filter to bars
whose timestamp is at least one full timeframe period in the past relative to `datetime.now(utc)`.

Example for `1d` timeframe: bar for 2026-05-28 is not considered finalized until
server clock ≥ 2026-05-29 00:00:00 UTC.

This guard prevents acting on a still-forming candle.

---

### 8.3 Provider Availability for Forward Testing

| Provider | Suitable for FT | Notes |
|----------|-----------------|-------|
| Yahoo Finance | Yes (dev/research) | 15–20 min delay. Free. Acceptable for research-grade FT. |
| Polygon.io | Yes (production) | Requires paid subscription for real-time. Vault credential required. |
| CSV/Parquet | No | Static datasets; cannot provide new bars on subsequent polls. |

The forward testing session creation request must validate that the chosen provider
is one of `{yahoo, polygon}`.  
Use `request_validation.validate_provider_type()` or add a FT-specific validator.

---

### 8.4 Symbol and Timeframe Validation

Reuse existing `validate_symbol()` and the provider capability check from `OHLCVService`.  
Do not add new validation logic — existing validators cover these cases.

---

## §9 ForwardTestSession Model Design

---

### 9.1 Session Identity and Ownership

```
session_id    — UUID4, server-generated, never client-supplied
user_id       — from JWT (current_user.user_id), never from request body
draft_id      — must exist and be owned by user_id at session creation
```

---

### 9.2 Session Status Transitions

```
CREATED   → ACTIVE     (via POST .../start)
ACTIVE    → PAUSED     (via POST .../pause — Phase 4D, deferred)
PAUSED    → ACTIVE     (via POST .../resume — Phase 4D, deferred)
ACTIVE    → STOPPED    (via POST .../stop — terminal)
ACTIVE    → COMPLETED  (time-bound sessions — Phase 4D, deferred)
ACTIVE    → FAILED     (unrecoverable error during polling — terminal)
CREATED   → STOPPED    (cancelled before start — terminal)
```

**Phase 4C implements:** `CREATED → ACTIVE → STOPPED` and `ACTIVE → FAILED`.

---

### 9.3 Immutability and State Transitions

`ForwardTestSession` should be a frozen Pydantic model (like `StrategyDraft`).  
State transitions produce a new session object with updated fields.  
`ForwardTestRepository.update()` atomically writes the new state.

---

### 9.4 Draft Snapshot

At session creation, a `StrategyDraftSnapshot` is captured from the draft's current state.  
This snapshot is immutable and stored in the session record.  
Purpose: the strategy may evolve (draft is mutable) while the session is running;
the session must record what it was testing, not what the draft currently is.

Fields to capture:
- `draft_id`
- `display_name`
- `lifecycle_status_at_start`
- `semantics_hash` (SHA-256 of semantics JSON, same as BacktestRunService does)
- `toolset_hash` (SHA-256 of toolset JSON)

---

## §10 API Surface Design

---

### 10.1 Route Summary

```
POST   /forward-testing/sessions
GET    /forward-testing/sessions
GET    /forward-testing/sessions/{session_id}
POST   /forward-testing/sessions/{session_id}/start
POST   /forward-testing/sessions/{session_id}/stop
POST   /forward-testing/sessions/{session_id}/poll
GET    /forward-testing/sessions/{session_id}/signals
```

All routes: `Depends(require_active_subscription)`.

---

### 10.2 Route Details

**`POST /forward-testing/sessions`**  
Request body:
```json
{
  "draft_id": "uuid",
  "symbol": "AAPL",
  "timeframe": "1d",
  "provider_name": "yahoo",
  "credential_id": null
}
```
Response: `ForwardTestSessionResponse` (full session record, no bar data).  
Creates session in `CREATED` status.  
Validates: draft exists + owned by user, provider in `{yahoo, polygon}`, credential exists if Polygon.

**`POST /forward-testing/sessions/{session_id}/start`**  
No request body.  
Transitions `CREATED → ACTIVE`.  
Fetches warmup bars immediately. Stores in bar history.  
Emits `FT_SESSION_STARTED`.

**`POST /forward-testing/sessions/{session_id}/poll`**  
No request body.  
Request body optional: `{"force": false}` — force re-fetch even if no new bars expected.  
Returns `ForwardTestPollResponse`:
```json
{
  "new_bars": 1,
  "new_signals": 2,
  "last_processed_bar_timestamp": "2026-05-28T16:00:00Z",
  "signals": [...]
}
```

**`POST /forward-testing/sessions/{session_id}/stop`**  
No request body.  
Transitions `ACTIVE → STOPPED` or `CREATED → STOPPED`.  
Archives session to `storage/ft_sessions/archive/`.  
Emits `FT_SESSION_STOPPED`.

**`GET /forward-testing/sessions/{session_id}/signals`**  
Query params: `?limit=100&offset=0`  
Returns list of `ForwardTestSignalResponse` objects.  
Ownership-enforced.

---

### 10.3 Response Schema Invariants

- `session_id` always in responses (durable identity)
- `user_id` never in list responses (avoid unnecessary PII exposure in bulk reads)
- `draft_snapshot` included in full session response
- No `file_path` anywhere in any response
- No `credential_id` secret values — only metadata

---

### 10.4 Router Registration

Add to `backend/api/main.py`:

```python
from backend.api.routes import forward_testing
app.include_router(forward_testing.router)
```

---

## §11 Tool Computation Strategy for Forward Testing

---

### 11.1 Full-Window Recomputation Per Poll

For each polling cycle that yields new bars:

1. Load full accumulated bar history from `{session_id}_bars.json`
2. Append new bars
3. Call `compute_tool_outputs_for_history(toolset, all_bars, registry)` over the full window
4. Call `evaluate_history()` over the full window
5. Extract results for new bars only (by `bar_index`)

This approach is correct and deterministic. The cost grows linearly with session duration,
but for research-grade forward testing (days to weeks of daily bars), the bar counts are
small (hundreds to low thousands) and re-computation is negligible.

---

### 11.2 Warmup Bar Count Calculation

At session creation, compute the maximum warmup requirement across all tools in the draft's toolset:

```python
max_warmup = max(
    derive_warmup_bars_required(tool_config, registry.get(tool_config.tool_id))
    for tool_config in draft.toolset.tools
    if tool_config.enabled
)
warmup_bars = max_warmup + 20  # safety buffer
```

Store `warmup_bar_count` in `ForwardTestSession`.

At session start (`CREATED → ACTIVE`), fetch `warmup_bars` historical bars via
`OHLCVService.get_recent_bars()`.

---

### 11.3 Bar Index Continuity

In backtesting, `bar_index` starts at 0 and increments by 1.  
In forward testing, the warmup bars should also use this scheme:

- Warmup bars: `bar_index = 0, 1, ..., warmup_bar_count - 1`
- First live bar: `bar_index = warmup_bar_count`
- Subsequent bars: continue incrementing

Store `total_bars_in_window` in the session to track continuity across polls.  
When new bars arrive, assign their `bar_index` as `total_bars_in_window + i` for i=0,1,...

---

### 11.4 No Lookahead in Forward Testing

The tool pipeline and evaluation engine enforce no-lookahead by design.  
Bar N's tool values only use closes 0..N.  
This is automatically correct in forward testing because bars arrive in chronological order
and the window grows monotonically.

No additional lookahead protection required beyond what the existing engine provides.

---

## §12 Ownership, Entitlement, and Security

---

### 12.1 Session Ownership Rules

All ownership rules mirror the existing draft/backtest pattern:

| Rule | Value |
|------|-------|
| `session.user_id` | Always from `current_user.user_id` (JWT) |
| Wrong-owner load | `ForwardTestSessionNotFoundError` → HTTP 404 (information hiding) |
| List sessions | Always filtered to `owner_id == current_user.user_id` |
| Poll/start/stop | Ownership verified before any state change |

---

### 12.2 Credential Security

If `provider_name == "polygon"`, a `credential_id` is required.  
Credential resolution follows the existing vault pattern:

```
credential_id → VaultService.resolve_secret(credential_id, owner_id=user_id)
                → raw key passed to ProviderAdapterFactory.build("polygon", api_key=...)
```

`credential_id` may be stored in `ForwardTestSession` (it is metadata, not a secret).  
The raw secret value is resolved per-poll and never stored.

---

### 12.3 Payload Guards

Apply the same bar count guard to FT bar history as used in backtesting:

```python
if len(accumulated_bars) > MAX_BACKTEST_BARS:
    raise ForwardTestSessionError(
        f"Session bar history ({len(accumulated_bars)}) exceeds MAX_BACKTEST_BARS "
        f"({MAX_BACKTEST_BARS}). Stop the session and start a new one."
    )
```

Emit `OVERSIZED_PAYLOAD_REJECTED` audit event (existing event kind).

---

### 12.4 Path Validation

`validate_uuid_id(session_id, "session_id")` on all `{session_id}` path parameters.  
Apply at route handler level (before any service call), exactly as in `drafts.py` and `backtest_runs.py`.

---

## §13 Frontend Integration Requirements

---

### 13.1 Current Frontend State

The frontend currently has no forward testing components.  
The nav bar shows: Chart | Composer | Credentials | Datasets | History | Report (conditional) | Admin

There is no "Forward Tests" tab.

---

### 13.2 Minimum Required Frontend Components

**Phase 4C Frontend Scope (minimal viable UI):**

1. **`ForwardTestPanel.tsx`** — session list + create new session button
   - Lists user's sessions (`GET /forward-testing/sessions`)
   - Status badge per session (CREATED / ACTIVE / STOPPED / FAILED)
   - "Start" / "Stop" / "Poll" action buttons per session
   - Polling interval timer (auto-poll on user-selectable interval while tab is open)

2. **`ForwardTestSignalList.tsx`** — signal feed for a selected session
   - Renders `GET /forward-testing/sessions/{session_id}/signals`
   - Timestamp, signal type (entry/exit), rule ID, bar index

3. **Nav tab:** "Forward Tests" — always visible when authenticated (like "History")

**Deferred to Phase 4D:** Signal overlay on Chart, full session report view, session
replay, paper trading connection.

---

### 13.3 API Client

Add `frontend/src/api/forwardTesting.ts`:

```typescript
export async function createSession(req: CreateFTSessionRequest): Promise<FTSessionResponse>
export async function listSessions(): Promise<FTSessionListResponse>
export async function startSession(sessionId: string): Promise<FTSessionResponse>
export async function stopSession(sessionId: string): Promise<FTSessionResponse>
export async function pollSession(sessionId: string): Promise<FTPollResponse>
export async function getSignals(sessionId: string): Promise<FTSignalListResponse>
```

All calls use `authedFetch` — no raw `fetch`.

---

### 13.4 Type Definitions

Add `frontend/src/types/forwardTesting.ts`:

```typescript
export type FTSessionStatus = "created" | "active" | "stopped" | "failed" | "completed";

export interface FTSession {
  session_id: string;
  draft_id: string;
  symbol: string;
  timeframe: string;
  provider_name: string;
  status: FTSessionStatus;
  created_at: string;
  started_at: string | null;
  stopped_at: string | null;
  bars_processed: number;
  signals_recorded: number;
  draft_snapshot: FTDraftSnapshot;
}

export interface FTSignal {
  signal_id: string;
  session_id: string;
  bar_timestamp: string;
  signal_type: "entry" | "exit";
  rule_id: string;
  recorded_at: string;
}
```

---

## §14 Testing Strategy

---

### 14.1 Unit Tests Required

| Test module | Tests |
|-------------|-------|
| `tests/unit/test_forward_test_session.py` | Session model creation, status transitions, snapshot capture |
| `tests/unit/test_forward_test_repository.py` | Save/load/update/list, ownership enforcement, wrong-owner → error |
| `tests/unit/test_forward_test_service.py` | Session creation, start, stop, poll cycle (zero new bars, one new bar, multiple new bars), lifecycle gate enforcement |
| `tests/unit/test_forward_test_signals.py` | Signal recording, signal retrieval, signal store |
| `tests/unit/test_ohlcv_service_extension.py` | get_recent_bars, get_bars_since, bar finalization, empty result on no new bars |

---

### 14.2 Test Infrastructure

For FT service tests, mock `OHLCVService` methods.  
Use a `tmp_path` fixture for `ForwardTestRepository` (same pattern as `DraftRepository` tests).  
Do NOT mock `evaluate_history()` or `compute_tool_outputs_for_history()` — these are
deterministic and their behavior should be validated in integration.

---

### 14.3 Target Test Count

The current backend test count is 3,721.  
Phase 4C should add approximately 60–90 new tests:

| Area | Estimated tests |
|------|----------------|
| Session model + repository | ~20 |
| Service layer (poll, start, stop, signal) | ~30 |
| API routes (auth, ownership, validation) | ~20 |
| OHLCVService extension | ~15 |
| Audit events | ~5 |

---

### 14.4 TypeScript / Frontend Tests

Frontend test count is currently 155.  
Add tests for:
- `forwardTesting.ts` API client functions (mock fetch)
- `ForwardTestPanel.tsx` component (render states: empty, loading, active sessions)
- Navigation: "Forward Tests" tab visibility

Estimated +15–25 frontend tests.

---

## §15 Phased Implementation Roadmap

---

### Phase 4C.1 — Foundation (no API yet)

**Scope:**
1. `backend/forward_testing/session.py` — `ForwardTestSession`, `ForwardTestSessionStatus`, `StrategyDraftSnapshot`, `ForwardTestSignal`, `ForwardTestPollResult`
2. `backend/forward_testing/session_repository.py` — `ForwardTestRepository` (mirrors DraftRepository)
3. `backend/forward_testing/bar_store.py` — `ForwardTestBarStore` (accumulated bar persistence)
4. `backend/forward_testing/signal_store.py` — `ForwardTestSignalStore` (signal persistence)
5. `settings.forward_test_sessions_storage_path` in `backend/core/config.py`
6. `get_forward_test_repository()` + `get_forward_test_signal_store()` in `backend/api/dependencies.py`

**Tests:** session model + repository + stores (target ~25 tests)

---

### Phase 4C.2 — Lifecycle and Audit Extension

**Scope:**
1. Add `forward_tested` to `StrategyLifecycleStatus` enum
2. Update `ALLOWED_TRANSITIONS` (note: defer removing `backtested → paper_tested` until Phase 4C.4 validation)
3. Add FT_ and GOV_ event kinds to `AuditEventKind`
4. Add `correlation_id: str | None = None` to `AuditEvent`
5. Update regression tests for lifecycle transitions

**Tests:** lifecycle transition tests (~10 tests)

---

### Phase 4C.3 — OHLCVService Extension

**Scope:**
1. `OHLCVService.get_recent_bars()` — warmup fetch
2. `OHLCVService.get_bars_since()` — incremental poll
3. Bar finalization filter (timeframe-aware completed-bar detection)
4. Provider validation (only yahoo/polygon allowed for FT)

**Tests:** OHLCV extension tests (~15 tests)

---

### Phase 4C.4 — ForwardTestService

**Scope:**
1. `backend/api/services/forward_test_service.py`
   - `create_session()`, `start_session()`, `stop_session()`, `poll_session()`, `get_signals()`
2. Lifecycle gate enforcement in `start_session()` (backtested or above required)
3. Audit event emission (FT_SESSION_CREATED, FT_SESSION_STARTED, FT_SESSION_STOPPED, FT_SIGNAL_RECORDED)

**Tests:** service layer tests (~30 tests)

---

### Phase 4C.5 — API Routes and Frontend

**Scope:**
1. `backend/api/routes/forward_testing.py` — all 7 routes
2. Register in `backend/api/main.py`
3. `frontend/src/api/forwardTesting.ts`
4. `frontend/src/types/forwardTesting.ts`
5. `ForwardTestPanel.tsx` + `ForwardTestSignalList.tsx`
6. Nav tab addition

**Tests:** route-level tests (~20 backend + ~20 frontend)

---

### Phase 4C.6 — Integration Validation

**Scope:**
1. End-to-end test: create session → start → poll (mocked bars) → verify signals
2. Verify audit log output for all FT events
3. Verify ownership isolation (user A cannot access user B's sessions)
4. Update `agent/HANDOFF.md` and `agent/TASKS.md`

---

## §16 Risks and Open Questions

---

### Risk 1 — Bar Finalization Complexity

Bar finalization logic (detecting when a forming candle is complete) is provider-specific.  
Yahoo Finance and Polygon have different update behaviors.  
**Mitigation:** Implement conservative finalization (one full timeframe period of lag)
and document the tradeoff. Accuracy over latency for research-grade forward testing.

---

### Risk 2 — OHLCVService Historical Cache Pollution

The existing `OHLCVService` cache is designed for historical research data.  
Polling cycles for forward testing must use `BYPASS_CACHE` to avoid writing live/near-live
bar data into the historical cache.  
**Mitigation:** Explicitly document the cache policy choice in the new methods.

---

### Risk 3 — Tool Warmup vs. Available History

For short-history symbols or wide warmup requirements (e.g., MACD with slow=200),
`get_recent_bars()` may not return enough bars.  
**Mitigation:** Fail session start with a clear error message: "Insufficient history:
required {warmup_bars} bars but provider returned {available_bars}."

---

### Risk 4 — Stateful Bar History Growth

Sessions running over months on intraday timeframes can accumulate tens of thousands of bars.  
The `MAX_BACKTEST_BARS` guard (§12.3) prevents unbounded growth.  
**Open question:** Should long-running sessions automatically stop at the cap, or should
they compress/trim older bars (not needed for most current tool warmups)?  
**Recommendation for Phase 4C:** Stop with error at cap. Revisit in Phase 4D.

---

### Risk 5 — No Audit Persistence

All FT audit events emit to the Python logger only.  
If the process restarts, the log may not be retained.  
This is acceptable for Phase 4C (research-grade) but must be noted as a known limitation
in the route docstrings and implementation comments.  
**Deferred:** Audit persistence is a Phase 4E+ concern.

---

### Risk 6 — Lifecycle Transition Breakage

Adding `FORWARD_TESTED` to `StrategyLifecycleStatus` changes the `BACKTESTED → paper_tested`
transition path.  
Existing strategy drafts at `backtested` status stored in JSON files are unaffected —
they remain at `backtested` and can still transition to `paper_tested` via the legacy path
(which should be kept temporarily during the transition period).  
**Mitigation:** Keep `backtested → paper_tested` as an allowed transition in Phase 4C.2.
Remove it in a subsequent cleanup phase after documentation of the governance path is updated.

---

### Open Question 1 — Polling Interval UX

The frontend is responsible for driving polls (Option A, §5.6).  
What polling interval is appropriate?  
For daily bars: 5-minute polling is overkill; once per hour is sufficient.  
For intraday (1h bars): once per 10–15 minutes.  
**Recommendation:** Let the user configure the poll interval in the session creation UI,
with a default of `15m` and a minimum of `5m`.

---

### Open Question 2 — Signal-to-Promotion Evidence Threshold

STRATEGY_PROMOTION_LIFECYCLE.md §8 defines evidence requirements for BACKTESTED → FORWARD_TESTED
promotion as "completion of at least one promotion-grade forward test session."  
**Open question:** Does Phase 4C auto-transition the draft to `forward_tested` when a session
reaches `COMPLETED` status, or does this require an explicit admin review step?  
**Recommendation for Phase 4C:** Auto-transition to `forward_tested` on session completion
(simple, no review workflow needed for the initial phase). The admin review workflow defined
in STRATEGY_PROMOTION_LIFECYCLE.md is deferred to Phase 4D.

---

## §17 Non-Negotiable Constraints

All constraints inherited from ARCHITECTURE_GUARDRAILS.md and the Phase 4A architecture documents:

1. `session.user_id` always from JWT — never from request body or path parameter
2. Wrong-owner access → HTTP 404 (information hiding)
3. `file_path` never in any API response
4. `credential_id` secrets never in any response — resolve via vault per poll, never store raw key
5. Forward testing code must not import from `backend.backtesting`, `backend.strategy_runtime`, `backend.api`, or `backend.data_providers` directly (use service layers and factory)
6. `evaluate_history()` and `compile_semantics()` are the canonical evaluation path — no parallel strategy evaluation logic
7. Bar index continuity must be maintained across polls — no gap, no reset
8. Tool computation must be deterministic: identical bar window → identical tool outputs → identical signals
9. Session activation requires `lifecycle_status >= backtested` (per STRATEGY_PROMOTION_LIFECYCLE.md)
10. All provider errors must be sanitized before HTTP responses (no file paths, no API key values in errors)
11. No self-promotion of strategies — lifecycle promotion requires admin review (deferred to Phase 4D)
12. Audit events must be emitted for all session lifecycle transitions, even with log-only storage

---

## Summary

| Dimension | Assessment |
|-----------|-----------|
| **Reusable without modification** | `evaluate_history()`, `compile_semantics()`, `ProviderAdapterFactory`, `require_active_subscription`, `validate_uuid_id()`, `AuditEvent`/`emit_audit_event()`, `DraftRepository` pattern, `BacktestRunService` pipeline pattern |
| **Requires extension** | `OHLCVService` (2 new methods), `AuditEventKind` (FT_ + GOV_ events), `AuditEvent` (correlation_id field), `StrategyLifecycleStatus` (forward_tested + transition rules) |
| **Missing — must build** | `ForwardTestSession` model, `ForwardTestRepository`, `ForwardTestSignalStore`, `ForwardTestBarStore`, `ForwardTestService`, 7 API routes, frontend panel + API client, `settings.forward_test_sessions_storage_path`, `get_forward_test_repository()` dependency |
| **Lifecycle gap** | 3 missing states (forward_tested, live, revoked); Phase 4C adds forward_tested only |
| **Audit gap** | No FT_ events, no persistence; Phase 4C adds event kinds + log emission; persistence deferred |
| **Polling model** | Client-driven (Option A) for Phase 4C; server-side scheduler deferred to Phase 4D |
| **Phase 4C test target** | ~3,800 backend tests, ~180 frontend tests |
| **Architecture readiness** | High — the evaluation engine, provider abstraction, ownership model, and entitlement layer are production-grade and directly reusable; no architectural blockers for implementation |

**Recommended next phase:** Phase 4C.1 — Foundation (ForwardTestSession model, repository, stores)

---

*Document created: Phase 4B — Forward Testing Runtime Architecture Review & Implementation Planning*  
*No runtime code was written. This document is the implementation authority for Phase 4C.*
