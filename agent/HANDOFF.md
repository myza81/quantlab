# HANDOFF.md

Operational continuity document for QuantLab implementation sessions.
Optimized for fast AI-agent onboarding. Historical phase detail → `agent/archive/HANDOFF_HISTORY.md`.

---

# Current Platform State

## Identity

**QuantLab** — modular strategy research and execution ecosystem.
Architecture-first, governance-disciplined, AI-orchestrated development.

## Test Counts (as of Phase 4C.6)

| Layer    | Tests  | Status |
|----------|--------|--------|
| Backend  | 4 188  | ✓ all pass |
| Frontend | 183    | ✓ all pass |
| TypeScript | —    | ✓ `tsc --noEmit` clean |

## Backend Maturity

- **Auth**: JWT bearer tokens, bcrypt passwords, `UserRepository` (JSON-backed), three-tier roles (`user / admin / superadmin`), subscription lifecycle for regular users
- **Entitlement**: `require_active_subscription` (lazy expiry evaluation), `require_admin_role`, `require_superadmin_role`; `User.has_platform_access` is canonical discriminant
- **Ownership**: all resources (drafts, catalog entries, backtest runs, vault credentials) are user-owned; `user_id` always from JWT
- **Vault**: Fernet-encrypted credential storage per user; `VaultService` with ownership enforcement; `resolve_secret()` internal-only
- **Market data**: two-source model — Source A: external provider (Yahoo/Polygon via `ProviderAdapterFactory`) + vault credential resolver; Source B: local CSV/Parquet via dataset catalog
- **Dataset catalog**: `DatasetCatalog` (JSON registry); `file_path` backend-only (never in responses); `catalog_id` is sole durable identity
- **Provider abstraction**: `ProviderAdapterFactory` (len=4: yahoo, csv, parquet, polygon); `OHLCVService` (coverage-based incremental fetch + cache policies); `DatasetFetchIdentity` (SHA-256 fingerprint)
- **Strategy layer**: tool registry (SMA/EMA/RSI/MACD/ATR/Bollinger Bands), `StrategyDraft` + `DraftRepository`, semantic evaluation engine (`StrategySemantics` → `EvaluationPlan` → `evaluate_history`), backtest simulation (cost model, position sizing, equity curve, exports)
- **Admin governance**: `AdminService` (approve/suspend/reactivate/update-expiry/promote/demote); last-admin protection; self-suspension guard; no hard-delete path
- **Audit**: `emit_audit_event()` → structured JSON log to `quantlab.audit`; 33 `AuditEventKind` values (incl. `OVERSIZED_PAYLOAD_REJECTED`, `LIFECYCLE_TRANSITION_DENIED`, `POLYGON_ENV_FALLBACK_USED`)
- **Security baseline**: `EnvironmentCredentialResolver`; request validation (`validate_date_range`, `validate_provider_type`, `validate_symbol`, `validate_bar_count`, `validate_uuid_id`); all provider errors sanitized before HTTP response
- **UUID path validation**: `validate_uuid_id()` in `request_validation.py`; applied at route handler level in `backtest_runs.py` (all 4 `{run_id}` routes) and `drafts.py` (all 4 `{draft_id}` routes); returns 400 for non-UUID path params before any file-path construction
- **Compute endpoint protection**: all 5 compute-heavy routes (`/semantics/evaluate-history`, `/semantics/evaluate-scalar`, `/semantics/extract-signal-events`, `/semantics/extract-trade-intents`, `/backtests/simulate`) require `require_active_subscription`
- **Payload guards**: `MAX_BACKTEST_BARS` (default 50 000) enforced on `/backtests/simulate` (price_bars) and `/backtests/runs` (bars); oversized → HTTP 400 + audit event; guard fires before any computation
- **Polygon ENV fallback gate**: `settings.polygon_allow_env_fallback` (default `False`); ENV-based API key resolution disabled by default; requires explicit opt-in; violation emits audit event
- **Strategy lifecycle**: `StrategyLifecycleStatus` enum (draft/validated/backtested/paper_tested/approved_for_live/archived); explicit transition table; `validate_lifecycle_transition()` enforced in draft service; `ARCHIVED` is terminal; invalid transitions emit `LIFECYCLE_TRANSITION_DENIED` audit event
- **Dependency injection**: `backend/api/dependencies.py` — canonical `get_draft_repository()`, `get_backtest_storage_path()`, `get_forward_test_repository()`, `get_forward_test_signal_store()`, `get_forward_test_bar_store()`; all route modules import from there (no more duplicates)
- **Config-driven paths**: `settings.drafts_storage_path`, `settings.backtest_runs_storage_path`, and `settings.forward_test_sessions_storage_path` replace all hardcoded `Path("storage/...")` patterns
- **Forward testing foundation** (`backend/forward_testing/`): `ForwardTestSession` (frozen Pydantic, 6-state lifecycle PENDING→RUNNING→PAUSED/COMPLETED/FAILED/TERMINATED, source_mode consistency, UUID field guards, UTC enforcement), `ForwardTestSignal` (immutable, no fills/positions/P&L, bar OHLCV snapshot), `ForwardTestBar` (warmup flag, bar_index, processed_at), `StrategySnapshot` (sealed strategy copy), `ForwardTestRepository` (JSON-backed, ownership-safe, UUID path guard, wrong-owner → `ForwardTestSessionNotFoundError`), `ForwardTestSignalStore` (idempotency: session_id + bar_timestamp + signal_direction), `ForwardTestBarStore` (idempotency: session_id + bar_timestamp; last timestamp queries); storage: `storage/forward_tests/sessions/`, `signals/`, `bars/`
- **Strategy lifecycle** (`backend/strategy_registry/lifecycle.py`): `StrategyLifecycleStatus.FORWARD_TESTED` added; canonical path `draft→validated→backtested→forward_tested→paper_tested→approved_for_live→archived`; `backtested→paper_tested` retained as deprecated transitional (exploratory, not promotion-eligible per `docs/STRATEGY_PROMOTION_LIFECYCLE.md §5`); `forward_tested→backtested` rollback allowed
- **Audit taxonomy** (`backend/core/audit.py`): 19 `FT_*` event kinds added (`FT_SESSION_CREATED`…`FT_SESSION_REVIEWED`); 9 `GOV_*` event kinds added (`GOV_PROMOTION_REQUESTED`…`GOV_LIFECYCLE_TRANSITION_DENIED`); `AuditEvent.correlation_id: str | None` added (optional, backward-compatible, serializes to JSON when present, absent from JSON when None); existing `LIFECYCLE_TRANSITION_DENIED` kept for backward compat alongside new `GOV_LIFECYCLE_TRANSITION_DENIED`
- **OHLCVService extensions** (`backend/services/ohlcv_service.py`): `timeframe_to_timedelta(timeframe) → timedelta` (all 15 canonical timeframes; "1M" = 30 days approximation); `is_bar_finalized(bar_timestamp, timeframe, *, current_time, buffer_seconds=60) → bool` (bar finalized when `current_time >= bar_open + tf_duration + buffer`); `OHLCVService.get_recent_bars(identity, limit, provider, *, reference_time, bar_finalization_buffer_seconds, lookback_multiplier)` (latest N finalized bars, BYPASS_CACHE, ascending); `OHLCVService.get_bars_since(identity, since_timestamp, provider, *, reference_time, bar_finalization_buffer_seconds)` (finalized bars strictly after cursor, BYPASS_CACHE, ascending); `settings.forward_test_bar_finalization_buffer_seconds = 60` added to config; no session coupling, no storage writes, no forming-candle evaluation
- **Market calendar** (`backend/market_calendar/`): `TradingCalendar` ABC; `TwentyFourSevenCalendar` (crypto/24-7, all bars expected); `WeekdayMarketCalendar` (Mon–Fri equity, weekends not expected, holiday DB deferred); `DefaultCalendar` (conservative fallback = WeekdayMarketCalendar); `get_calendar(asset_class, *, provider_name, exchange, symbol) → TradingCalendar` registry (crypto→24/7, equity→weekday, unknown→default, case-insensitive); `is_bar_expected(bar_timestamp, timeframe, calendar) → bool` (gap detection: market closure vs. provider failure); `is_bar_finalized(bar_timestamp, timeframe, now_utc, calendar, safety_buffer=60) → bool` (calendar-aware: time-finalized AND expected; wraps Phase 4C.3 time-check; Saturday equity bar always False); UTC-only enforcement throughout; no external calendar dependency; no strategy-layer imports; documented in `docs/MARKET_CALENDAR.md`
- **ForwardTestService** (`backend/forward_testing/service.py`): single-cycle evaluation engine; `CycleResult` frozen dataclass (session_id, status, bars_fetched, bars_processed, warmup_bars_processed, signal_eligible_bars_processed, signals_generated, signals_suppressed, last_processed_bar_timestamp, gap_detected, provider_failure, activated, message); `run_cycle(session_id, owner_id, identity, provider, *, now_utc)` — PENDING→`_activate()`, RUNNING→`_poll_cycle()`, PAUSED/terminal→no-op; `_activate()` — `validate_session_transition(PENDING→RUNNING)`, `get_recent_bars()` warmup (warmup_period bars), all stored with `is_warmup_bar=True`, cursor = last warmup bar timestamp or `now_utc`, audit `FT_SESSION_ACTIVATED`; `_poll_cycle()` — `get_bars_since(cursor)` + gap detection via `_calendar_is_bar_expected(expected_next_ts)` + full-window recomputation (stored bars + new bars via `compute_tool_outputs_for_history()`) + `evaluate_history()` on all bars + signal emit only for new bar indices + idempotent `append_bar/append_signal` + cursor advance to last new bar timestamp + session counter updates + audit `FT_POLL_COMPLETED`; `_prepare_strategy()` — `StrategyDraft.model_validate_json(strategy_json)` + `compile_semantics(draft.semantics, draft_id)` → `(draft, plan, error_message)`; `RangeProviderAdapter` imported only under `TYPE_CHECKING` guard (boundary: `forward_testing` must not import from `data_providers`); `DatasetIdentity` passed by caller (route layer sets exchange/asset_class); no scheduler, no polling loop, no background workers, no API routes, no frontend, no broker execution
- **Forward Testing API** (`backend/api/routes/forward_testing.py`, `backend/api/schemas/forward_testing.py`): 9 protected routes under `/forward-tests`; all require `require_active_subscription`; `user_id` always from JWT; wrong-owner → 404 (information hiding); `file_path`/`strategy_json`/`user_id` never in responses; session creation: draft ownership + lifecycle gate (>= backtested) + snapshot seal + warmup derivation + `FT_SESSION_CREATED` audit; run-cycle: catalog rejection (422) + vault credential resolution + provider build + `DatasetIdentity` + `ForwardTestService.run_cycle()`; pause/terminate: explicit pre-check that `resume` requires PAUSED status (PENDING→RUNNING allowed by state machine for activation only); DI providers `get_ohlcv_service`, `get_tool_registry`, `get_provider_factory` added to `backend/api/dependencies.py`; `ForwardTestSession` model extended with `credential_id`, `exchange`, `asset_class` (all defaulted, backward-compatible); 37 backend route tests in `tests/unit/test_forward_testing_routes.py`
- **Forward Testing Frontend** (`frontend/src/types/forwardTesting.ts`, `frontend/src/api/forwardTests.ts`, `frontend/src/components/ForwardTestPanel.tsx`): TypeScript types mirror backend schemas (no `strategy_json`, no `user_id` in summaries); `authedFetch` for all API calls; no `setInterval` auto-polling; MVP panel: session list with status badges, run-cycle/pause/resume/terminate buttons, signal history drill-in, create form (draft_id + symbol + timeframe + provider + exchange + credential); "Forward Test" nav tab added to `App.tsx`; 28 frontend tests (13 API + 15 component)

## Frontend Maturity

- **Auth**: `AuthContext` (JWT in localStorage, `authedFetch`, `refreshUser()`), `AuthGuard`, `LoginPage`, `RegisterPage`
- **Entitlement**: `SubscriptionGate` (blocks pending/expired/suspended users; admin passthrough)
- **Market data**: `Controls.tsx` — provider selector, credential selector (Polygon), Fetch button; `DatasetMetaBadge` (provenance strip)
- **Dataset catalog**: `CatalogManager.tsx` — list/register/remove/load; `CatalogMetaBadge`; `file_path` cleared after submit, never rendered; `handleCatalogLoad` in App.tsx switches to chart with catalog data
- **Credentials**: `CredentialManager.tsx` — list/add/disable/delete; secret cleared from state after API call
- **Strategy**: `DraftWorkspace.tsx` (full CRUD + archive), `SemanticEditorPanel.tsx`, `PlanInspectionPanel.tsx`, `StrategyTestPanel.tsx` (composition + backtest trigger + session context display + Composer shortcut)
- **Chart**: `Chart.tsx` — lightweight-charts v5, two-pane (price + oscillator), overlay lifecycle managed, `CatalogMetaBadge` / `DatasetMetaBadge` above chart
- **Research session**: `ResearchSession` type + `SessionProvenanceStrip.tsx` — persistent strip below nav showing active dataset/strategy/last-run; `no file_path` ever rendered in session context; Phase 3S-C adds "Resume Last Report" button (restore last run after page refresh)
- **Session persistence**: `useSessionPersistence` hook — sessionStorage (`ql_session_v1`), partial merge saves, path sanitization on load; never stores JWT, secrets, file_path, raw candle data; clears on window close
- **Report flow**: `BacktestReportPage.tsx` — source provenance label, "Edit Strategy" → Composer; "Report" nav tab appears once a backtest result exists; Phase 3S-C adds Run Provenance section (dataset + draft provenance with short-hash display)
- **Backtest History**: `BacktestHistoryPanel.tsx` — `GET /backtests/runs`, ownership-filtered, newest-first; "Reopen" fetches full report; loading/empty/error states; History nav tab (always visible)
- **Admin**: `AdminConsole.tsx` (approve/suspend/reactivate/update-expiry/promote/demote); superadmin-tier buttons gated on `isSuperadminViewer`
- **Nav**: Chart | Composer | Credentials | Datasets | History | Forward Test | Report (when backtest exists) | Admin (admin/superadmin only)
- **Forward Test Panel**: `ForwardTestPanel.tsx` — session list with status badges (pending/running/paused/completed/failed/terminated), contextual action buttons (Activate/Run Cycle/Pause/Resume/Terminate), signal history drill-in via session ID link, create session form (draft_id, symbol, timeframe, provider, exchange, credential_id)

---

# Architecture Invariants — MUST NOT VIOLATE

## Identity & Ownership

- `user_id` **always** from `current_user.user_id` (JWT) — never from request body, query param, or client claim
- Wrong-owner access → HTTP **404** (same exception as not-found — information hiding)
- Legacy resources (`user_id=None`) inaccessible to all authenticated users

## Entitlement Model

- `require_admin_role` must **never** depend on `require_active_subscription` (admins manage users even after their own subscription expires)
- `User.has_platform_access`: admin/superadmin = `True` (role-based, subscription irrelevant); regular user = subscription-based
- Superadmin can promote `user→admin` and demote `admin→user`; regular admin cannot
- No self-promotion, no self-demotion (service guard + audit)
- No hard-delete user path anywhere (no endpoint, no button, no service method)

## Data Isolation

- `file_path` never in any API response (catalog service resolves internally)
- `encrypted_secret` never in any API response (vault service resolves internally)
- `password_hash` never in any API response (auth schema has no such field)
- `CredentialMetadataResponse` has no `secret_value`, `encrypted_secret`, or `raw_secret`

## Provider & Strategy Layer

- Strategies must never import from: `data_providers/`, `vault/`, `api/`, `storage/`, or any frontend module
- `market_data_service.py` has no concrete adapter imports (factory pattern only)
- Provider errors must be sanitized before HTTP responses (no file paths, no API key values)
- `resolve_secret()` in `VaultService` is internal-only — never called from routes

## Frontend

- All ownership-scoped endpoints use `authedFetch` (never raw `fetch`)
- `AuthError` on 401 → `logout()` → `AuthGuard` shows `LoginPage`
- `file_path` cleared from state in `resetForm()` immediately after successful catalog registration
- `catalog_id` is sole durable frontend resource identity for catalog entries

---

# Admin / Governance Model

```
superadmin  → is_admin=True, is_superadmin=True  (promote/demote, all admin actions)
admin       → is_admin=True, is_superadmin=False  (approve/suspend/reactivate/update-expiry)
user        → subscription-based access
```

**Bootstrap**: first registration matching `admin_bootstrap_email` config → `role=superadmin`.
**Migration**: `backend/scripts/promote_superadmin.py <email>` (idempotent; one-time for existing `role=admin` accounts).
**Subscription lifecycle**: `pending → active → expired/suspended → active`. Lazy expiry on every protected request.

---

# Completed Milestones

| Phase | Milestone |
|-------|-----------|
| 4D | Paper trading architecture review: `docs/PAPER_TRADING_IMPLEMENTATION_REVIEW.md` produced; full codebase survey against `PAPER_TRADING_ARCHITECTURE.md`, `EXECUTION_CONTRACT.md`, `EXECUTION_AUDIT_MODEL.md`, `STRATEGY_PROMOTION_LIFECYCLE.md`; inventoried 10 directly reusable FT components (evaluate_history, compile_semantics, StrategySnapshot seal, OHLCVService, ProviderAdapterFactory, ForwardTestBarStore, ForwardTestSignalStore, AuditEvent infrastructure, ownership enforcement, _prepare_strategy); identified 18 missing components (PaperTradingSession, SimulationAssumptions, PaperAccount, PaperOrder, PaperFill, PaperPosition, AccountStateSnapshot, PaperBrokerAdapter, ExecutionGateway, PaperTradingRepository, 3 stores, PaperAccountStore, metrics calculator, 29 PT_* AuditEventKind values, API routes, schemas, PaperTradingPanel); phased roadmap 4E.1–4E.6 defined; readiness rating **A−** (architecture complete, implementation complexity manageable, `next_bar_open` cross-bar state and `PAPER_TESTED` enum presence flagged for pre-implementation verification); no code changes |
| 4C.6 | Forward testing integration validation: `tests/integration/test_forward_testing_integration.py` — 65 tests across 10 sections; all 13 validation objectives passed; 4 test defects fixed (sessions missing semantics in poll-path tests); no production defects found; integration readiness rating **B** (all Phase 4C objectives met; known limitations: log-only audit, JSON-backed storage, no holiday calendar, no FT_SESSION_COMPLETED route in Phase 4C scope); test counts: backend 4 188 total |
| 4C.5 | Forward testing API routes + frontend panel: 9 routes under `/forward-tests` (create, list, get, run-cycle, pause, resume, terminate, signals, bars); all require `require_active_subscription`; snapshot seal + SHA-256 hash + warmup derivation at creation; catalog mode rejected on run-cycle (422); `ForwardTestPanel.tsx` with status badges + action buttons + signal drill-in + create form; "Forward Test" nav tab; 37 backend + 28 frontend tests |
| 4C.4 | ForwardTestService single-cycle evaluation engine: `backend/forward_testing/service.py` — `CycleResult` frozen dataclass; `run_cycle()` with PENDING→`_activate()` + RUNNING→`_poll_cycle()` + PAUSED/terminal no-op; `_activate()` fetches warmup bars via `get_recent_bars()`, stores with `is_warmup_bar=True`, sets cursor, transitions session to RUNNING, emits `FT_SESSION_ACTIVATED`; `_poll_cycle()` uses `get_bars_since(cursor)` + gap detection (`is_bar_expected` calendar check) + full-window recomputation (`compute_tool_outputs_for_history()`) + `evaluate_history()` + idempotent signal/bar persistence + cursor advance + session counter updates + emits `FT_POLL_COMPLETED` / `FT_GAP_DETECTED` / `FT_SIGNAL_GENERATED` / `FT_SIGNAL_SUPPRESSED`; `_prepare_strategy()` deserializes + compiles `StrategySemantics`; `RangeProviderAdapter` imported only under `TYPE_CHECKING` guard (boundary: `forward_testing` ≠ `data_providers`); no scheduler, no polling loop, no API routes, no broker execution; 41 new tests |
| 4C.3A | Exchange calendar & market session finalization policy: `backend/market_calendar/` — `TradingCalendar` ABC; `TwentyFourSevenCalendar` + `WeekdayMarketCalendar` + `DefaultCalendar`; `get_calendar()` registry; `is_bar_expected()`; `is_bar_finalized()` calendar-aware; 60 new tests |
| 4C.3 | OHLCVService forward-testing extensions: `timeframe_to_timedelta()` (all 15 canonical timeframes); `is_bar_finalized()` (candle close + safety buffer, UTC-aware, raises on naive datetimes); `OHLCVService.get_recent_bars()` (latest N finalized bars, BYPASS_CACHE); `OHLCVService.get_bars_since()` (finalized bars strictly after cursor, BYPASS_CACHE); `settings.forward_test_bar_finalization_buffer_seconds = 60` added to config; normalizer enforces monotonic timestamps (stub providers must supply ascending bars); no session coupling, no storage writes; 44 new tests |
| 4C.2 | Forward testing lifecycle + audit taxonomy integration: `StrategyLifecycleStatus.FORWARD_TESTED` added to `lifecycle.py`; canonical promotion path `backtested→forward_tested→paper_tested` established; `backtested→paper_tested` retained (deprecated transitional per STRATEGY_PROMOTION_LIFECYCLE.md §5); `forward_tested→backtested` rollback allowed; 19 `FT_*` + 9 `GOV_*` audit event kinds added to `audit.py`; `AuditEvent.correlation_id: str | None` added (optional, backward-compat, serializes in JSON when present); existing audit callers unaffected; `ForwardTestSessionStatus` vocabulary mapping documented (pending=created, terminated=stopped); 95 new tests; no API routes, no scheduler, no strategy evaluation |
| 4C.1 | Forward testing foundation: `backend/forward_testing/` package — `exceptions.py` (4 exception classes), `models.py` (`ForwardTestSessionStatus` 6-state enum + transition table + `StrategySnapshot` + `ForwardTestSession` + `ForwardTestSignal` + `ForwardTestBar`), `repository.py` (`ForwardTestRepository` — JSON-backed, ownership enforcement, UUID path guard, wrong-owner → same error as not-found, `save`/`load`/`update`/`list_all`/`list_active`/`exists`), `stores.py` (`ForwardTestSignalStore` + `ForwardTestBarStore` — idempotent append, ordering, last-timestamp queries); `settings.forward_test_sessions_storage_path` added to `backend/core/config.py`; 3 DI factories in `backend/api/dependencies.py`; 125 new tests (models: 51, repository: 30, stores: 29, plus idempotency datetime-comparison fix — Pydantic JSON serializes UTC as `Z` vs Python `.isoformat()` as `+00:00`, fixed by parsing stored timestamps via `datetime.fromisoformat()` before comparison); no API routes, no scheduler, no strategy evaluation |
| 4B | Forward testing implementation review: `docs/FORWARD_TESTING_IMPLEMENTATION_REVIEW.md` produced; full codebase survey against 4A architecture documents; identified directly reusable components (`evaluate_history()`, `ProviderAdapterFactory`, `DraftRepository` pattern, `require_active_subscription`, `compile_semantics()`); identified extension targets (`OHLCVService` needs 2 new methods, `AuditEventKind` needs FT_/GOV_ events, `AuditEvent` needs `correlation_id`, `StrategyLifecycleStatus` needs `forward_tested`); identified 8 missing components (`ForwardTestSession`, `ForwardTestRepository`, `ForwardTestService`, `ForwardTestSignalStore`, `ForwardTestBarStore`, 7 API routes, frontend panel, settings path); confirmed `backend/forward_testing/` + `backend/jobs/` + `backend/execution/` are empty placeholders; audit is log-only (no persistence, no execution taxonomy); lifecycle missing `forward_tested`/`LIVE`/`REVOKED`; phased roadmap 4C.1–4C.6 defined; no code changes |
| 4A.5 | Strategy promotion lifecycle: `docs/STRATEGY_PROMOTION_LIFECYCLE.md` established; authoritative lifecycle with 9 states (DRAFT → VALIDATED → BACKTESTED → FORWARD_TESTED → PAPER_TESTED → APPROVED_FOR_LIVE → LIVE → REVOKED → ARCHIVED); 6 evidence categories; per-gate evidence requirements (§7–§9); no numerical thresholds — evidence completeness + human review; self-promotion prohibited; `GOV_STRATEGY_APPROVED_FOR_LIVE` requires `explicit_acknowledgment_text`; revocation model from LIVE/APPROVED_FOR_LIVE/PAPER_TESTED; backward-compatibility alignment with current 6-state implementation; `forward_tested`, `live`, `revoked` states defined as future additions; promotion readiness philosophy established; 9 non-negotiable constraints |
| 4A.4 | Execution audit model: `docs/EXECUTION_AUDIT_MODEL.md` established; authoritative audit event taxonomy across all execution subsystems; 6 audit categories (`FT_`, `PT_`, `LT_`, `GOV_`, `ADMIN_`, `FAILURE_`); 13-field common audit record envelope with `correlation_id`; 19 FT_ events + 22 PT_ events + 8 LT_ conceptual events + 8 GOV_ events with `explicit_acknowledgment_text` on `GOV_STRATEGY_APPROVED_FOR_LIVE`; immutability model (append-only, corrections via new records); 4 retention tiers (governance + live fills = permanent); 4 review types; 7 query patterns; three-part evidence base for live trading authorization; LT_ extension path defined; 7 non-negotiable constraints |
| 4A.3 | Paper trading architecture: `docs/PAPER_TRADING_ARCHITECTURE.md` established; defines `PaperTradingSession` (extends `ForwardTestSession`), `PaperAccount`, `PaperPosition`, `PaperOrder`, `PaperFill` models; execution intent flow through `PaperBrokerAdapter`; fill simulation philosophy (market orders, 2 fill timing models, declared slippage/fee, 3 sizing modes); account state ownership rules; equity curve model; 20+ audit event categories; drawdown stop mechanism; relationship to forward testing and live trading; 19 non-negotiable constraints |
| 4A.2 | Forward testing architecture: `docs/FORWARD_TESTING_ARCHITECTURE.md` established; defines `ForwardTestSession` model, session lifecycle state machine, REST-polling data acquisition model, bar finalization and unseen-bar detection, per-bar evaluation reusing existing engine, `ForwardTestSignal` recording contract, provenance/ownership/persistence/audit/failure models, UI workflow concept, polling→streaming upgrade path, relationship to paper trading and promotion lifecycle documents |
| 4A.1 | Execution contract architecture: `docs/EXECUTION_CONTRACT.md` established as foundational contract for all future execution subsystems (forward testing, paper trading, live trading); defines execution philosophy, 5 execution modes, 7 core objects, session model, gateway contract, state management principles, determinism rules, ownership/provenance/audit requirements, 12 safety constraints, relationships to existing architecture, and 4 future documents |
| 3S-D | Legacy route decommissioning & path safety hardening: `/datasets/*` + `POST /strategy-runs/run` gated with auth; `validate_uuid_id()` added to `request_validation.py`; UUID enforcement on all 4 `{run_id}` + 4 `{draft_id}` path-param routes; `POST /semantics/validate` + `POST /tools/validate-toolset` protected; `GET /tools` + `GET /market-data/providers` documented as intentionally public; frontend `semantics.ts` + `strategyRuns.ts` switched to `authedFetch`; 36 new hardening tests; 35 regression tests updated to use valid UUIDs; TypeScript fix |
| 3S-C | Research provenance & workflow continuity: `GET /backtests/runs` history API, `BacktestHistoryPanel`, dataset/draft provenance snapshots, `useSessionPersistence`, "Resume Last Report", Run Provenance section in report; 48 new tests |
| 3S-B | Security & runtime boundary fixes: compute endpoint auth, payload guards, lifecycle state machine, Polygon ENV gate, storage path DI, dependency consolidation |
| 3R | Research workflow UX (ResearchSession, SessionProvenanceStrip, report→Composer, Report nav tab) |
| 3Q | Operational documentation refactor (HANDOFF.md compression, archive) |
| 3P-E | Dataset catalog UX (CatalogManager, Source Mode B, file_path safety) |
| 3P-D | Superadmin role tier, promote/demote governance |
| 3P-C | Lazy subscription expiry enforcement |
| 3P-B.1 | Governance safety: expiry workflow, self-suspension guard, last-admin protection |
| 3P-B | Admin Console browser UI |
| 3P-A.1 | Admin entitlement separation (`has_platform_access`) |
| 3P-A | Subscription eligibility & admin approval foundation |
| 3O | Credential-aware market data UX (Polygon + vault) |
| 3N | Frontend credential management UI |
| 3M.1 | Browser auth & ownership validation (4 bugs fixed) |
| 3M | Frontend ownership integration (`authedFetch` everywhere) |
| 3L | User ownership & resource scoping (user_id from JWT) |
| 3J | Provider credential resolver (vault→polygon) |
| 3I | User provider credential vault (Fernet encryption) |
| 3H | Auth & user identity (JWT, bcrypt, UserRepository) |
| 3G | Polygon.io provider (15 timeframes, pagination) |
| 3F | Security baseline (credentials, audit, request validation) |
| 3E | Dataset catalog & file path resolution |
| 3D | Local CSV/Parquet providers |
| 3C | Dataset cache & storage architecture |
| 3B | Dataset fetch identity (SHA-256 fingerprint) |
| 3A | Provider abstraction layer (ProviderAdapterFactory) |
| 2T–2U | Tool output visualization (two-pane chart), 6-tool registry |
| 2N–2S | Full backtest pipeline (simulation, costs, sizing, report, exports) |
| 2J–2M | Strategy semantic & evaluation engine |
| 2D–2I | Strategy tools builder layer (drafts, toolset, composition) |
| 2A–2C | Core data schemas, storage, OHLCVService |

Full phase detail: `agent/archive/HANDOFF_HISTORY.md`

---

# Recommended Next Phases

**Immediate:**
- **Phase 2V — Custom Research Tools**: First non-standard indicator (swing high/low, divergence, custom feature tool); must register in `_TOOL_DISPATCHERS`, expose `output_feature_names`, respect warmup/lookahead enforcement; marks start of QuantLab-specific research layer
- **Bollinger Bands visualization**: Backend implementation complete; frontend overlay rendering not yet wired

**Near-term:**
- **Phase 4E — Paper Trading Implementation**: Models + repository foundation → PaperBrokerAdapter + fill simulation → PaperTradingService → API routes + schemas → PaperTradingPanel frontend → integration validation; governed by `docs/PAPER_TRADING_IMPLEMENTATION_REVIEW.md` (Phase 4D output); pre-start: verify `PAPER_TESTED` in `lifecycle.py`; design `next_bar_open` pending order persistence before Phase 4E.3
- **Payment / Subscription Integration**: Webhook-driven approval flow; connect `validate_future_expiry` / `approve_user` to a payment provider
- **PostgreSQL migration**: Replace JSON-backed `UserRepository`, `CredentialRepository`, `DraftRepository` with PostgreSQL when multi-instance or durability requirements emerge

**Deferred:**
- Live trading infrastructure (WebSocket, tick streaming)
- Broker adapters (IBKR, Binance)
- Distributed execution / microservices
- Per-candle gap detection in OHLCVService
- Instrument master database
- Audit persistence (DB or event store; currently log-only)
- Holiday calendar (currently weekday/24-7 only)
- Alternative / astronomical datasets

---

# Strategic Timeframe Roadmap

## Current Validated Target

Phase 4C validated the full Research → Backtest → Forward Test → Signal workflow at the following timeframes:

| Timeframe | Status |
|-----------|--------|
| Daily (1d) | ✅ Validated |
| 4-Hour (4h) | ✅ Validated |
| 1-Hour (1h) | ✅ Validated |
| 30-Minute (30m) | ✅ Validated |
| 15-Minute (15m) | ✅ Validated |

These timeframes work with the current single-cycle polling model and full-window recomputation architecture without modification.

## Phase 4H — Intraday Engine Optimization (5m)

**Status:** Planned — after Paper Trading maturity (Phase 4D+)

**Objective:** Enable production-grade 5-minute strategy support.

At 5-minute timeframes, the full-window recomputation model accumulates sessions with hundreds of bars per day. A long-running forward test session will require engine-level optimization to remain performant.

**Required capabilities:**

- **ToolStateSnapshot architecture**: persist intermediate indicator state so each poll cycle computes only the incremental delta rather than the full history
- **Incremental indicator computation**: SMA/EMA/RSI/MACD/ATR/Bollinger Bands must support state-resumption from a snapshot
- **Incremental evaluator execution**: `evaluate_history()` must support evaluating only new bars using persisted rule state from prior bars
- **Session pagination**: `list_bars` / `list_signals` API routes must support cursor-based pagination as bar counts grow into the thousands
- **Provider polling optimization**: `get_bars_since()` fetch windows must be bounded; avoid unbounded lookback as session age grows
- **Long-running session validation**: integration tests covering sessions with 500+ bars

**Outcome:** 5m forward testing; 5m paper trading

## Phase 5A — Realtime Market Data & Streaming Architecture (1m)

**Status:** Planned — after Phase 4H

**Objective:** Enable production-grade 1-minute strategy support.

At 1-minute timeframes, client-driven polling is no longer viable. Bar windows are too short for reliable round-trip latency, and polling introduces systematic latency that degrades signal quality. A streaming ingestion layer is required.

**Required capabilities:**

- **WebSocket ingestion layer**: persistent WebSocket connection to market data providers; per-symbol subscription management
- **Event-driven market data pipeline**: bar events emitted on close; downstream consumers decouple from transport layer
- **Reconnect / recovery logic**: automatic reconnect with missed-bar detection on reconnect; gap audit on resume
- **Event deduplication**: idempotent event processing; duplicate bars from reconnect storms must not produce duplicate signals or store entries
- **Late-bar handling**: bars arriving after the finalization window must be flagged, not silently discarded; audit event emitted
- **Persistent event storage**: streaming bar events must be persisted durably (not in-memory) to survive service restarts without data loss
- **Streaming audit integration**: all stream lifecycle events (`STREAM_CONNECTED`, `STREAM_DISCONNECTED`, `STREAM_RECONNECTED`, `STREAM_GAP_DETECTED`, `STREAM_LATE_BAR`) must emit structured audit events

**Outcome:** 1m forward testing; 1m paper trading; foundation for live execution layer

---

# Operational Rules

1. Read `WORKFLOW_AGENT.md` + `ARCHITECTURE_GUARDRAILS.md` before any implementation session
2. Do not invent scope — all work originates from structured directives
3. Never merge responsibilities across architecture boundaries (API ≠ strategy ≠ provider ≠ storage ≠ frontend)
4. Update `HANDOFF.md` (latest completed work) + `TASKS.md` (active phase) at the end of every session
5. If architecture violation discovered: document in HANDOFF.md, do not silently build on top of it
6. High-impact architecture changes require external (orchestration-layer) approval before implementation
