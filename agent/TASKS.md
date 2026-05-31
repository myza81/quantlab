# TASKS.md

Active implementation coordination for QuantLab. Answers: what's next, what's active, what's blocked, what's deferred.
Not a historical archive — completed phase detail lives in `agent/archive/HANDOFF_HISTORY.md`.

---

# Current Phase Status

**Phase 4D — Paper Trading Architecture Review — COMPLETE**
(no code changes; architecture-only phase)
- `docs/PAPER_TRADING_IMPLEMENTATION_REVIEW.md` — 18 sections: purpose/scope, architecture docs reviewed, directly reusable components (10), missing components (18), account/order/fill/position/portfolio/session model recommendations, promotion lifecycle, audit taxonomy (29 PT_* events), storage assessment, workflow design (14 routes + UI), risks (6 risks + 2 open questions), implementation roadmap (4E.1–4E.6), readiness assessment, recommended next phase
- Architecture documents reviewed: `PAPER_TRADING_ARCHITECTURE.md`, `EXECUTION_CONTRACT.md`, `EXECUTION_AUDIT_MODEL.md`, `STRATEGY_PROMOTION_LIFECYCLE.md`, `FORWARD_TESTING_IMPLEMENTATION_REVIEW.md`
- Codebase surveyed: `backend/forward_testing/`, `backend/strategy_registry/`, `backend/execution/`, `backend/core/audit.py`, `backend/api/routes/forward_tests.py`
- Readiness rating: **A−** — all architecture documents complete; implementation complexity manageable; `next_bar_open` cross-bar state concern requires explicit design before Phase 4E.3; `PAPER_TESTED` enum presence requires pre-start verification

**Phase 4C.6 — Integration Validation — COMPLETE**
(backend: 4 188 tests | 65 new tests added)
- `tests/integration/__init__.py` — new integration test package
- `tests/integration/test_forward_testing_integration.py` — 65 tests across 10 sections (A: service E2E, B: signal idempotency, C: calendar gap detection, D: ownership isolation, E: lifecycle gate, F: entitlement gate, G: lifecycle transitions HTTP, H: audit event emission, I: API security invariants, J: full workflow HTTP)
- All 13 validation objectives PASSED: end-to-end workflow, ownership isolation, lifecycle gate, entitlement gate, warmup bar correctness, signal generation, signal idempotency, calendar gap detection, audit taxonomy, API security, UUID validation, terminal state guards, resume pre-check
- 4 test defects fixed: sessions missing `semantics=` in poll-path tests caused `_prepare_strategy()` early return; no production code defects
- Forward testing integration readiness rating: **B** — all Phase 4C objectives met; known limitations: log-only audit, JSON-backed storage, no holiday calendar, no FT_SESSION_COMPLETED route in Phase 4C scope

**Phase 4C.5 — Forward Testing API Routes + Frontend Panel — COMPLETE**
(backend: 4 123 tests | 37 new tests added | frontend: 183 tests | 28 new tests added)
- `backend/api/schemas/forward_testing.py` — 7 request/response schemas; no `strategy_json`, no `user_id` in list/summary responses; no `file_path`
- `backend/api/routes/forward_testing.py` — 9 routes under `/forward-tests`; all require `require_active_subscription`; `user_id` always from JWT; wrong-owner→404; session creation: lifecycle gate (>=backtested) + snapshot seal + SHA-256 hash + warmup derivation; run-cycle: catalog rejection (422) + vault credential resolution + provider build + `DatasetIdentity` + `ForwardTestService.run_cycle()`; resume pre-check (PAUSED only); pause/terminate; signals; bars
- `backend/api/dependencies.py` — `get_ohlcv_service()`, `get_tool_registry()`, `get_provider_factory()` added
- `backend/forward_testing/models.py` — `ForwardTestSession` extended: `credential_id`, `exchange="NASDAQ"`, `asset_class="equity"` (defaulted, backward-compatible)
- `tests/unit/test_forward_testing_routes.py` — 37 tests: create (7), list (5), get (3), run-cycle (4), pause (3), resume (3), terminate (4), signals (3), bars (3), auth (1)
- `frontend/src/types/forwardTesting.ts` — TypeScript types mirror backend schemas
- `frontend/src/api/forwardTests.ts` — 9 API functions; all use `authedFetch`; no `setInterval` auto-polling
- `frontend/src/components/ForwardTestPanel.tsx` — session list + status badges + contextual action buttons + create form + signal history drill-in
- `frontend/src/App.tsx` — "Forward Test" nav tab added; `ActiveView` type extended
- `frontend/src/api/__tests__/forwardTests.test.ts` — 13 API client tests
- `frontend/src/components/__tests__/ForwardTestPanel.test.tsx` — 15 component tests

**Phase 4C.4 — ForwardTestService Single-Cycle Evaluation Engine — COMPLETE**
(backend: 4 086 tests | 41 new tests added)
- `backend/forward_testing/service.py` — `CycleResult` frozen dataclass (13 fields); `ForwardTestService` with `run_cycle(session_id, owner_id, identity, provider, *, now_utc)`; `_activate()` (warmup bars via `get_recent_bars()`, `is_warmup_bar=True`, cursor = last warmup ts or `now_utc`, PENDING→RUNNING transition, `FT_SESSION_ACTIVATED`); `_poll_cycle()` (`get_bars_since(cursor)`, gap detection via `_calendar_is_bar_expected`, full-window recomputation via `compute_tool_outputs_for_history()`, `evaluate_history()`, idempotent bar/signal persistence, cursor advance, `FT_POLL_COMPLETED` / `FT_GAP_DETECTED` / `FT_SIGNAL_GENERATED` / `FT_SIGNAL_SUPPRESSED`); `_prepare_strategy()` (`StrategyDraft.model_validate_json` + `compile_semantics`); PAUSED/terminal → no-op; `RangeProviderAdapter` under `TYPE_CHECKING` guard only (boundary: `forward_testing` ≠ `data_providers`)
- `tests/unit/test_forward_test_service.py` — 41 tests: `TestActivation` (11), `TestPollCycle` (17), `TestStatusGuards` (6), `TestStrategyErrors` (2), `TestOwnership` (2), `TestSignalFields` (3)

**Phase 4C.3A — Exchange Calendar & Market Session Finalization Policy — COMPLETE**
(backend: 4 045 tests | 60 new tests added)
- `backend/market_calendar/base.py` — `TradingCalendar` ABC (UTC-only, `is_session_open`, `is_bar_expected`)
- `backend/market_calendar/calendars.py` — `TwentyFourSevenCalendar` (24/7, crypto); `WeekdayMarketCalendar` (Mon–Fri, equity); `DefaultCalendar` (conservative fallback = weekday)
- `backend/market_calendar/registry.py` — `get_calendar(asset_class, *, provider_name, exchange, symbol)` resolver; crypto→24/7; equity/stock/etf/fund→weekday; unknown→default; case-insensitive; reserved params for future exchange routing
- `backend/market_calendar/policy.py` — `is_bar_expected(bar_timestamp, timeframe, calendar) → bool`; `is_bar_finalized(bar_timestamp, timeframe, now_utc, calendar, safety_buffer=60) → bool` (wraps Phase 4C.3 time-check + calendar gate; Saturday equity bar always False)
- `backend/market_calendar/__init__.py` — public exports
- `tests/unit/test_market_calendar.py` — 60 tests (24/7 + weekday + default calendars, registry routing, is_bar_expected, is_bar_finalized, UTC enforcement, safety buffer, no-false-gap architectural rule)
- `docs/MARKET_CALENDAR.md` — minimal calendar architecture, limitations, UTC policy, future expansion path
- Key constraint: `is_bar_finalized` in policy.py returns False for unexpected bars regardless of time; ForwardTestService uses this to distinguish market closure from provider failure

**Phase 4C.3 — OHLCVService Extensions for Forward Testing — COMPLETE**
(backend: 3 985 tests | 44 new tests added)
- `backend/services/ohlcv_service.py` — `timeframe_to_timedelta()` (all 15 canonical TFs; "1M"=30d); `is_bar_finalized()` (UTC-aware, buffer_seconds=60, raises on naive dt); `OHLCVService.get_recent_bars()` (limit, reference_time, lookback_multiplier=2, BYPASS_CACHE); `OHLCVService.get_bars_since()` (strict `>` cursor, BYPASS_CACHE); no session coupling; no storage writes
- `backend/core/config.py` — `forward_test_bar_finalization_buffer_seconds = 60`
- `tests/unit/test_ohlcv_forward_test_extensions.py` — 44 tests (timeframe utilities, finalization logic, get_recent_bars, get_bars_since, UTC safety, BYPASS_CACHE verification)
- Key constraint: DataNormalizer enforces monotonic ascending timestamps; stub providers must return bars in ascending order

**Phase 4C.2 — Forward Testing Lifecycle & Audit Taxonomy Integration — COMPLETE**
(backend: 3 941 tests | 95 new tests added)
- `backend/strategy_registry/lifecycle.py` — `StrategyLifecycleStatus.FORWARD_TESTED` added; canonical path `backtested→forward_tested→paper_tested`; `backtested→paper_tested` retained (deprecated transitional); `forward_tested→backtested` rollback; invalid shortcuts rejected; docstring updated
- `backend/core/audit.py` — 19 FT_* event kinds added (FT_SESSION_CREATED through FT_SESSION_REVIEWED); 9 GOV_* event kinds added (GOV_PROMOTION_REQUESTED through GOV_LIFECYCLE_TRANSITION_DENIED); `AuditEvent.correlation_id: str | None = None` (optional, backward-compat); `emit_audit_event()` serializes correlation_id when present
- `tests/unit/test_strategy_lifecycle.py` — updated _VALID_TRANSITIONS + _INVALID_TRANSITIONS for forward_tested
- `tests/unit/test_security_baseline.py` — updated `test_all_event_kinds_defined` with all new FT_* + GOV_* values
- `tests/unit/test_forward_testing_lifecycle_audit.py` — new test file: lifecycle transitions, audit taxonomy, correlation_id, status vocabulary mapping

**Phase 4C.1 — Forward Testing Foundation — COMPLETE**
(backend: 3 846 tests | 125 new tests added)
- `backend/forward_testing/__init__.py` — package established
- `backend/forward_testing/exceptions.py` — `ForwardTestSessionNotFoundError`, `ForwardTestSessionAlreadyExistsError`, `ForwardTestPersistenceError`, `ForwardTestInvalidTransitionError`
- `backend/forward_testing/models.py` — `ForwardTestSessionStatus` (6-state enum + transition table + terminal detection), `StrategySnapshot`, `ForwardTestSession` (frozen, UUID guards, UTC enforcement, source_mode consistency), `ForwardTestSignal` (immutable, no fills/P&L), `ForwardTestBar` (warmup flag, bar_index)
- `backend/forward_testing/repository.py` — `ForwardTestRepository` (JSON-backed, ownership enforcement, UUID path guard, wrong-owner → same exception as not-found)
- `backend/forward_testing/stores.py` — `ForwardTestSignalStore` (idempotency: bar_timestamp + signal_direction), `ForwardTestBarStore` (idempotency: bar_timestamp; last-timestamp queries; warmup/signal-eligible counts)
- `backend/core/config.py` — `forward_test_sessions_storage_path` added
- `backend/api/dependencies.py` — `get_forward_test_repository()`, `get_forward_test_signal_store()`, `get_forward_test_bar_store()`
- `tests/unit/test_forward_test_models.py` — 51 tests
- `tests/unit/test_forward_test_repository.py` — 30 tests
- `tests/unit/test_forward_test_stores.py` — 29 tests (+ idempotency datetime fix: Pydantic `Z` vs `.isoformat()` `+00:00`)

**Phase 4B — Forward Testing Runtime Architecture Review & Implementation Planning — COMPLETE**
(`docs/FORWARD_TESTING_IMPLEMENTATION_REVIEW.md` created; no code changes; review and planning only)

**Phase 4A.5 — STRATEGY_PROMOTION_LIFECYCLE.md — COMPLETE**
(`docs/STRATEGY_PROMOTION_LIFECYCLE.md` established; no code changes; architecture-only)

**Phase 4A.4 — EXECUTION_AUDIT_MODEL.md — COMPLETE**
(`docs/EXECUTION_AUDIT_MODEL.md` established; no code changes; architecture-only)

**Phase 4A.3 — PAPER_TRADING_ARCHITECTURE.md — COMPLETE**
(`docs/PAPER_TRADING_ARCHITECTURE.md` established; no code changes; architecture-only)

**Phase 4A.2 — FORWARD_TESTING_ARCHITECTURE.md — COMPLETE**
(`docs/FORWARD_TESTING_ARCHITECTURE.md` established; no code changes; architecture-only)

**Phase 4A.1 — EXECUTION_CONTRACT.md — COMPLETE**
(`docs/EXECUTION_CONTRACT.md` established; no code changes; architecture-only)

**Phase 3S-D — Legacy Route Decommissioning & Path Safety Hardening — COMPLETE**
(backend: 3 721 tests | frontend: 155 tests | tsc clean)

**Phase 3S-C — Research Provenance & Workflow Continuity — COMPLETE**

**Phase 3S-B — Critical Security & Runtime Boundary Fixes — COMPLETE**

Completed phases: 4D, 4C.6, 4C.5, 4C.4, 4C.3A, 4C.3, 4C.2, 4C.1, 4B, 4A.5, 4A.4, 4A.3, 4A.2, 4A.1, 3S-D, 3S-C, 3S-B, 3P-E, 3P-D, 3P-C, 3P-B.1, 3P-B, 3P-A.1, 3P-A, 3O, 3N, 3M.1, 3M, 3L, 3J, 3I, 3H, 3G, 3F, 3E, 3D, 3C, 3B, 3A, 2T–2U, 2N–2S, 2J–2M, 2D–2I, 2A–2C

---

# Immediate Active Roadmap

## Phase 4C — Forward Testing Runtime Implementation

**Status:** IN PROGRESS (4C.1 complete)

**Implementation authority:** `docs/FORWARD_TESTING_IMPLEMENTATION_REVIEW.md`

### Phase 4C.1 — Foundation

**Status:** COMPLETE (125 tests added; 3 846 total)

### Phase 4C.2 — Lifecycle and Audit Extension

**Status:** COMPLETE (95 tests added; 3 941 total)

### Phase 4C.3 — OHLCVService Extension

**Status:** COMPLETE (44 tests added; 3 985 total)

### Phase 4C.3A — Exchange Calendar & Market Session Finalization Policy

**Status:** COMPLETE (60 tests added; 4 045 total)

### Phase 4C.4 — ForwardTestService

**Status:** COMPLETE (41 tests added; 4 086 total)

### Phase 4C.5 — API Routes + Frontend

**Status:** COMPLETE (37 backend + 28 frontend tests added)

### Phase 4C.6 — Integration Validation

**Status:** COMPLETE (65 tests added; 4 188 total)  
**Scope:** End-to-end test (create → start → poll → signals); ownership isolation; update HANDOFF.md + TASKS.md

---

## Phase 2V — Custom Research Tools

**Status:** PENDING

**Objective:** First non-standard indicator — marks start of the QuantLab-specific research tool layer.

**Expected scope:** Swing high/low detector, or divergence signal, or custom feature computation tool. Must register in `_TOOL_DISPATCHERS`, expose `output_feature_names`, respect warmup/lookahead enforcement.

---

# Near-Term Roadmap

| Phase | Objective | Dependency |
|-------|-----------|------------|
| **Phase 4C.1 — FT Foundation** | ✓ COMPLETE — 125 tests; session model, repository, stores, settings path | 4B complete |
| **Phase 4C.2 — Lifecycle + Audit** | ✓ COMPLETE — 95 tests; forward_tested state, FT_/GOV_ events, correlation_id | 4C.1 complete |
| **Phase 4C.3 — OHLCVService** | ✓ COMPLETE — 44 tests; get_recent_bars, get_bars_since, bar finalization | 4C.1 complete |
| **Phase 4C.3A — Market Calendar** | ✓ COMPLETE — 60 tests; TradingCalendar, 24/7 + weekday calendars, registry, is_bar_expected, is_bar_finalized (calendar-aware) | 4C.3 complete |
| **Phase 4C.4 — ForwardTestService** | ✓ COMPLETE — 41 tests; single-cycle engine, PENDING activation, RUNNING poll, audit emission | 4C.2 + 4C.3 + 4C.3A complete |
| **Phase 4C.5 — Routes + Frontend** | ✓ COMPLETE — 9 routes, ForwardTestPanel, nav tab | 4C.4 complete |
| **Phase 4C.6 — Integration** | ✓ COMPLETE — 65 tests; all 13 objectives passed; readiness rating B | 4C.5 complete |
| **Phase 4D — Paper Trading Review** | ✓ COMPLETE — `docs/PAPER_TRADING_IMPLEMENTATION_REVIEW.md`; 18 sections; readiness rating A− | 4C.6 complete |
| **Phase 4E — Paper Trading Implementation** | PENDING — 4E.1 models → 4E.2 broker adapter → 4E.3 service → 4E.4 routes → 4E.5 frontend → 4E.6 integration | 4D complete |
| 2V — Custom Research Tools | Swing high/low or divergence indicator | None |
| Payment / Subscription | Webhook-driven approval, connect `approve_user` to payment provider | 3R complete |
| PostgreSQL migration | Replace JSON-backed repositories (User, Credential, Draft, Catalog) | Durability need |
| Bollinger Bands visualization | Wire 3-series band overlay to frontend chart (backend already complete) | None |
| Provider expansion | Binance, IBKR adapters in `ProviderAdapterFactory` | 3A architecture ready |

---

# Planned Future Phases

## Phase 4H — Intraday Engine Optimization

**Status:** PLANNED
**Dependency:** After Paper Trading maturity (Phase 4D+)

**Objective:** Enable production-grade 5-minute strategy support.

Required: ToolStateSnapshot architecture; incremental indicator computation; incremental evaluator execution; session pagination; provider polling optimization; long-running session validation.

**Outcome:** 5m forward testing; 5m paper trading

## Phase 5A — Realtime Streaming Architecture

**Status:** PLANNED
**Dependency:** After Phase 4H

**Objective:** Enable production-grade 1-minute strategy support.

Required: WebSocket ingestion layer; event-driven market data pipeline; reconnect/recovery logic; event deduplication; late-bar handling; persistent event storage; streaming audit integration.

**Outcome:** 1m forward testing; 1m paper trading; foundation for live execution

---

# Deferred / Long-Term Infrastructure

- **Live trading**: WebSocket streaming, tick-to-candle aggregation, broker execution, risk layer — **NOT current priority**
- **Distributed execution**: microservices, Celery/RQ workers, cloud orchestration — deferred until multi-strategy / live trading need
- **Per-candle gap detection**: `OHLCVService` currently uses coverage windows; intra-window gaps not detected
- **Instrument master database**: no centralized symbol/exchange registry; each provider resolves symbols independently
- **Alternative / astronomical datasets**: research layer deferred until core strategy loop is stable
- **Audit persistence**: `emit_audit_event()` is log-only; no DB or audit store yet
- **Credential rotation**: `EnvironmentCredentialResolver` reads env var statically per request; no rotation detection

---

# Architectural Constraints (non-negotiable)

| Constraint | Why |
|------------|-----|
| `user_id` always from JWT | No client-controlled ownership |
| Wrong-owner → HTTP 404 | Information hiding (same as not-found) |
| `require_admin_role` never depends on `require_active_subscription` | Admins must manage users even after own expiry |
| `file_path` never in any API response | Prevents filesystem path leakage |
| `encrypted_secret` never in any API response | Defense-in-depth on vault responses |
| `password_hash` never in any API response | Auth schema invariant |
| Strategies import nothing from api/provider/storage/frontend | Portability across all runtime modes |
| `resolve_secret()` internal to VaultService only | Route layer never handles raw secrets |
| Backtest results must be reproducible | Deterministic candle+config inputs required |

---

# Governance Foundation Status

All governance documents established:

| Document | Status |
|----------|--------|
| `ARCHITECTURE_GUARDRAILS.md` | ✓ complete |
| `WORKFLOW_GOVERNANCE.md` | ✓ complete |
| `WORKFLOW_AGENT.md` | ✓ complete |
| `PROMPT_RULES.md` | ✓ complete |
| `ARCHITECTURE.md` | ✓ complete |
| `docs/ADMIN_GOVERNANCE.md` | ✓ complete |
| `docs/OWNERSHIP_SCOPING.md` | ✓ complete |
| `docs/ADMIN_ENTITLEMENT_SEPARATION.md` | ✓ complete |
| `docs/SUBSCRIPTION_EXPIRY_ENFORCEMENT.md` | ✓ complete |
| `docs/BACKTESTING_ENGINE_CONTRACT.md` | ✓ complete |

Minor outstanding note: `directives/` folder not yet documented in `REPOSITORY_STRUCTURE.md` (non-blocking).

---

# Execution Domain Notes

**Orchestration domain** (human + ChatGPT): architecture decisions, governance, phase planning, scope definition.
**Implementation domain** (Claude, Codex): coding, module implementation, testing, documentation updates.

Implementation work originates from structured directives only. Do not invent scope.
