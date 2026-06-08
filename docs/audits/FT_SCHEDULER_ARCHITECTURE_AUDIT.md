# FT_SCHEDULER_ARCHITECTURE_AUDIT.md

**Audit:** FT-SCHED-ARCH-AUDIT-1  
**Date:** 2026-06-05  
**Author:** Architecture Audit Agent  
**Status:** Complete — No code was modified  
**Output files:** `docs/audits/FT_SCHEDULER_ARCHITECTURE_AUDIT.md`, `agent/HANDOFF.md`, `agent/TASKS.md`

---

## 1. Executive Summary

QuantLab's forward-test evaluation engine (`ForwardTestService.run_cycle()`) is fully functional and explicitly designed for external scheduling. The service docstring states verbatim: *"caller is responsible for scheduling repeated calls via whatever mechanism suits their runtime."* The evaluation logic, bar cursor, deduplication, gap detection, strategy deserialization, and audit emission are all already implemented correctly.

The missing piece is exactly one module: a scheduler that reads all RUNNING sessions from persistent storage on a configurable interval and calls `run_cycle()` for each one, supplying the provider adapter.

The recommended architecture is a **single global APScheduler instance embedded in the FastAPI `lifespan` context**, using an interval job that scans all RUNNING sessions across all users, reconstructs the provider per session, and calls the existing service. No new domain models, no new storage, no new strategy logic, no broker integration.

If the app is closed, sessions remain durable in JSON files. When the app restarts, the scheduler resumes from each session's `last_processed_bar_timestamp` cursor with zero data loss.

**Classification of current implementation:** Class C (backend-driven, manually triggered). FT-2 promotes it to Class D (backend scheduled polling) using the architecture described in this document.

---

## 2. Current Architecture Findings

### 2.1 What already works

| Component | Location | Status |
|---|---|---|
| Session state machine (PENDING/RUNNING/PAUSED/COMPLETED/FAILED/TERMINATED) | `forward_testing/models.py` | Complete |
| Session persistence (JSON-backed filesystem repository) | `forward_testing/repository.py` | Complete |
| Bar cursor (`last_processed_bar_timestamp`) | `ForwardTestSession.last_processed_bar_timestamp` | Complete |
| Bar deduplication by timestamp | `ForwardTestBarStore.append_bar()` | Complete |
| Signal deduplication by (session_id, bar_timestamp, direction) | `ForwardTestSignalStore.append_signal()` | Complete |
| Single-cycle evaluation engine | `forward_testing/service.py` | Complete |
| Warmup-phase activation (PENDING → RUNNING) | `ForwardTestService._activate()` | Complete |
| Poll-phase (RUNNING → fetch since cursor → evaluate → persist) | `ForwardTestService._poll_cycle()` | Complete |
| Gap detection (market calendar aware) | `_poll_cycle()` + `market_calendar/policy.py` | Complete |
| Provider adapter factory | `data_providers/provider_factory.py` | Complete |
| Vault credential resolution | `vault/service.py` | Complete |
| Bar finalization buffer (configurable) | `settings.forward_test_bar_finalization_buffer_seconds` | Complete |
| Audit event emission | `core/audit.py` — 19 FT_* event kinds | Complete |
| `list_active()` — scans all RUNNING/PENDING/PAUSED sessions for a user | `ForwardTestRepository.list_active()` | Complete |
| Architecture boundary: `forward_testing` does not import `data_providers` | Enforced via `TYPE_CHECKING` guard | Complete |

### 2.2 What is absent

| Missing Component | Impact |
|---|---|
| Global `list_all_running_sessions()` across all users | Scheduler needs to iterate all active sessions, not just per-user |
| Scheduler entry point | No periodic trigger exists |
| Provider reconstruction from session metadata | Route layer does this; needs extracting to a reusable helper |
| `cycle_interval_seconds` per-session config | Scheduler needs to know how often to run each session |
| `last_cycle_attempted_at` / `last_cycle_succeeded_at` session fields | Monitoring and failure detection |
| `consecutive_provider_failures` counter | Auto-pause after N failures |
| FastAPI `lifespan` context | `main.py` has no startup/shutdown hooks |
| Scheduler observability: structured log per tick | None |

### 2.3 Storage observation

All session state is persisted to the filesystem (`storage/forward_tests/sessions/{session_id}.json`). The repository `list_all()` method currently requires `owner_id` — a cross-user scan for the scheduler requires either a new repository method or a known user registry query. This is the only notable gap in the existing repository API.

### 2.4 FastAPI application observation

`backend/api/main.py` uses a bare `app = FastAPI(...)` with no `lifespan` parameter, no `@app.on_event("startup")` hooks, and no background task wiring. APScheduler integration requires adding a `lifespan` context manager — a small and well-understood change to one file.

---

## 3. Recommended Scheduler Architecture

### 3.1 Design choice: Single global scheduler (recommended)

One APScheduler `AsyncScheduler` (or `BackgroundScheduler`) instance is created at FastAPI startup, registered as a `lifespan` context, and runs an interval job on a configurable tick (recommended default: 60 seconds).

Each tick:
1. Repository scans all session files for RUNNING status (cross-user scan — see §3.3).
2. For each RUNNING session, reconstruct `DatasetIdentity` + provider adapter from session metadata.
3. Call `ForwardTestService.run_cycle(session_id, owner_id, identity, provider)`.
4. Emit structured audit log for the tick outcome.
5. If provider failure count exceeds threshold, auto-pause the session.

### 3.2 Execution flow per tick

```
SchedulerTick (interval = settings.ft_scheduler_interval_seconds)
    │
    ├── FTSchedulerRepository.list_all_running()       ← new cross-user query
    │
    └── for each session in running_sessions:
            │
            ├── if session.status != RUNNING: skip (state may have changed mid-tick)
            │
            ├── _reconstruct_provider(session)
            │     ├── factory.build(provider_name, symbol, asset_class, ...)
            │     └── vault.resolve_secret(credential_id, session.user_id, provider_name)
            │
            ├── ForwardTestService.run_cycle(
            │       session_id, owner_id=session.user_id,
            │       identity=DatasetIdentity(...),
            │       provider=provider,
            │       now_utc=datetime.now(timezone.utc)
            │   )
            │
            └── handle CycleResult:
                    ├── provider_failure=True → increment failure counter → auto-pause if >= threshold
                    ├── gap_detected=True → emit audit, continue
                    └── bars_processed=0, message="no new finalized bars" → normal, skip
```

### 3.3 Cross-user session scan

Add one method to `ForwardTestRepository`:

```python
def list_all_running_globally(self) -> list[ForwardTestSession]:
    """
    Return all sessions with status=RUNNING across all users.
    Used exclusively by the scheduler — never by user-facing routes.
    """
```

This reads all session files, returns those with `status == RUNNING`, regardless of `user_id`. The scheduler owns the caller context for this method; it is never exposed via API routes.

### 3.4 Provider reconstruction

The route layer already reconstructs the provider inline. For the scheduler, extract this into a helper (or module-level function) in a new `backend/jobs/ft_scheduler.py`:

```python
def _build_provider_for_session(
    session: ForwardTestSession,
    factory: ProviderAdapterFactory,
    vault: VaultService,
) -> RangeProviderAdapter:
    api_key = vault.resolve_secret(session.credential_id, session.user_id, session.provider_name)
    return factory.build(session.provider_name, ...)
```

The `VaultService` is already safe for server-side use — `resolve_secret()` is internal-only and never exposed to clients. The scheduler is server-side.

### 3.5 Session fields to add (minimal)

Add three optional fields to `ForwardTestSession` (all backward-compatible, defaulting to `None`/`0`):

| Field | Type | Purpose |
|---|---|---|
| `cycle_interval_seconds` | `int` (default: 300) | How often this session should be polled |
| `consecutive_provider_failures` | `int` (default: 0) | Incremented on each failed cycle; reset on success |
| `last_cycle_attempted_at` | `datetime | None` | Set by scheduler on each attempt |

These additions are purely additive to the frozen Pydantic model via `model_copy(update={...})`.

### 3.6 Auto-pause threshold

Add to `settings`:

```python
ft_scheduler_max_consecutive_failures: int = 5
```

When `consecutive_provider_failures >= ft_scheduler_max_consecutive_failures`, the scheduler calls the repository directly to transition the session to PAUSED with `failure_reason="scheduler_auto_pause_consecutive_provider_failures"`. This prevents stale RUNNING sessions accumulating without evidence.

### 3.7 APScheduler integration point

```python
# backend/api/main.py

from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from backend.jobs.ft_scheduler import ForwardTestSchedulerJob

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    job = ForwardTestSchedulerJob()
    scheduler.add_job(
        job.run_tick,
        "interval",
        seconds=settings.ft_scheduler_interval_seconds,
        id="ft_scheduler",
        max_instances=1,        # prevent overlapping ticks
        coalesce=True,          # skip missed ticks, don't pile up
    )
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)

app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
```

`max_instances=1` and `coalesce=True` are critical safety properties — they prevent a slow tick from spawning concurrent duplicate evaluations.

---

## 4. Rejected Alternatives and Reasons

### 4.1 One scheduler per session (rejected)

**Proposal:** Create a separate APScheduler job for each RUNNING session at session-creation time.

**Problems:**
- Requires in-memory job registry that does not survive restart. After restart, all per-session jobs are gone and must be reconstructed from storage — adding a "reconcile all RUNNING sessions on startup" step that is functionally identical to the global scanner anyway.
- More scheduler state to manage; jobs must be cancelled when sessions are paused/terminated.
- No benefit over the global scanner model because the evaluation cadence is already configurable per-session via `cycle_interval_seconds`.

### 4.2 Celery worker queue (rejected for FT-2)

**Proposal:** Use Celery + Redis/RabbitMQ for distributed task dispatch.

**Problems:**
- Adds two new infrastructure dependencies (message broker + Celery worker process).
- QuantLab is a single-process monolith with JSON-backed filesystem storage. Celery would be over-engineering for this phase.
- The architecture guardrails explicitly warn against unscoped dependency additions.
- APScheduler embedded in FastAPI is zero additional infrastructure — same process, same deployment.

**Reserved for:** FT-4/FT-5 when multiple worker processes and distributed load become a real constraint.

### 4.3 External cron job calling the existing `/run-cycle` API endpoint (rejected)

**Proposal:** Use `cron` or a separate script that HTTP-POSTs to `/forward-tests/{id}/run-cycle` on a schedule.

**Problems:**
- Requires valid JWT for each request — managing bot credentials adds an auth complexity surface.
- Introduces HTTP round-trip and serialization overhead for an operation that could be a direct function call.
- Exposes internal scheduler behavior to the HTTP layer, which mixes concerns.
- Does not handle credential resolution cleanly (the vault API key must never travel over HTTP in a cron script).

### 4.4 WebSocket push-triggered evaluation (rejected for FT-2)

**Proposal:** Subscribe to a live data WebSocket and trigger evaluation on each incoming tick.

**Problems:**
- No WebSocket infrastructure exists yet. Building it in FT-2 would be FT-3 scope.
- REST polling with finalization buffer is already designed and implemented. It is the correct FT-2 model.
- WebSocket is an upgrade path (FT-3), not a prerequisite.

### 4.5 Database-backed scheduler (e.g., storing "next_run_at" in session JSON and polling it) (rejected)

**Proposal:** Add `next_run_at` to session; scheduler queries all sessions with `next_run_at <= now`.

**Problems:**
- Requires scanning all session files on every tick anyway (same as the global scan).
- Adds write contention: the scheduler would write `next_run_at` updates to session files every cycle, increasing I/O.
- The `cycle_interval_seconds` per-session field + scheduler-side skip logic achieves the same cadence control without the write overhead.

---

## 5. Required Data/State Contracts

### 5.1 Session model additions (backward-compatible)

All fields added with defaults — existing sessions deserialize correctly.

```python
# New optional fields on ForwardTestSession (frozen Pydantic)
cycle_interval_seconds: int = 300          # default: poll every 5 minutes
consecutive_provider_failures: int = 0
last_cycle_attempted_at: datetime | None = None
```

### 5.2 New repository method (no schema changes)

```python
# ForwardTestRepository
def list_all_running_globally(self) -> list[ForwardTestSession]:
    """
    Return all RUNNING sessions across all users.
    Scheduler-internal — never exposed via API routes.
    """
```

### 5.3 New settings (environment-overridable)

```python
# backend/core/config.py additions
ft_scheduler_enabled: bool = True
ft_scheduler_interval_seconds: int = 60        # global tick cadence
ft_scheduler_max_consecutive_failures: int = 5 # auto-pause threshold
```

### 5.4 DatasetIdentity reconstruction

The scheduler reconstructs `DatasetIdentity` from session fields already stored:

```
DatasetIdentity(
    instrument=Instrument(
        symbol=session.symbol,
        asset_class=session.asset_class,
        exchange=session.exchange,
    ),
    provider=session.provider_name,
    timeframe=session.timeframe,
    adjustment_mode=AdjustmentMode.RAW,
)
```

This is already done in the route layer — no new contracts needed.

### 5.5 Architecture boundary: scheduler must not contain strategy logic

The scheduler module (`backend/jobs/ft_scheduler.py`) must import from:
- `backend.forward_testing.repository` (load sessions)
- `backend.forward_testing.service` (call run_cycle)
- `backend.data_providers.provider_factory` (build provider)
- `backend.vault.service` (resolve credential)
- `backend.data.models.dataset` (DatasetIdentity)
- `backend.core.config` (settings)
- `backend.core.audit` (emit_audit_event)

The scheduler must NOT import from:
- `backend.strategy_registry.*` directly (strategy logic stays in ForwardTestService)
- `backend.strategy_runtime.*`
- `backend.execution.*`
- `backend.api.*` (no HTTP coupling)
- Any frontend module

---

## 6. Required Idempotency Rules

### 6.1 Bar-level idempotency (already implemented)

`ForwardTestBarStore.append_bar()` deduplicates by `(session_id, bar_timestamp)`. If the scheduler calls `run_cycle()` twice for the same session before the cursor advances (e.g., after a restart), the duplicate bars are silently ignored. No double-counting occurs.

### 6.2 Signal-level idempotency (already implemented)

`ForwardTestSignalStore.append_signal()` deduplicates by `(session_id, bar_timestamp, signal_direction)`. Duplicate signals from a rerun are silently suppressed; `signals_suppressed` counter increments in `CycleResult`.

### 6.3 Cycle-level idempotency (via cursor)

The cursor `last_processed_bar_timestamp` is advanced only to the last bar actually stored this cycle. If `run_cycle()` is called again before any new bars exist (e.g., scheduler ran twice for a daily bar before market close), the provider returns zero bars, the cursor does not advance, and the result is `bars_processed=0, message="no new finalized bars"`. This is correct and safe.

### 6.4 Session state idempotency (via status check)

`ForwardTestService.run_cycle()` checks session status before any work. PAUSED and terminal sessions return a no-op `CycleResult` immediately. The scheduler should also check session status after loading it from the repository before calling the service, as a defensive first-pass filter.

### 6.5 Scheduler tick idempotency (via APScheduler config)

`max_instances=1` on the APScheduler job prevents a new tick from starting if the previous tick is still running. `coalesce=True` skips accumulated ticks rather than running them all at once after a delay. Together, these prevent tick pile-up under slow provider responses.

---

## 7. Required Persistence/Recovery Behavior

### 7.1 Normal stop (SIGTERM / process exit)

All session state is already on disk. The scheduler calls `scheduler.shutdown(wait=False)` in the `lifespan` cleanup. The current tick may be interrupted mid-cycle. On the next restart:
- Sessions whose last cycle was interrupted mid-bar: the bar and signal stores have idempotent appends. On the next cycle, `get_bars_since(cursor)` will fetch the same or newer bars; duplicates are silently ignored.
- Cursor is only advanced after successful persistence. An interrupted cycle means the cursor stays at its last committed position — the next cycle re-fetches from that point.

**No explicit recovery step is needed.** The cursor + idempotency model is naturally crash-safe.

### 7.2 Backend restart

On startup, the `lifespan` context starts the scheduler. The scheduler's first tick calls `list_all_running_globally()`, finds all RUNNING sessions, and resumes them. The first cycle after restart will call `get_bars_since(last_processed_bar_timestamp)` and fetch all bars that accumulated during the downtime.

**The session will "catch up" on restart.** For daily-bar strategies this means one cycle after restart processes all missing days. For minute-bar strategies with many missed bars, the full-window recomputation in `_poll_cycle()` (stored + new bars) handles the backfill correctly — this is already implemented.

### 7.3 Provider failure

`ForwardTestService.run_cycle()` catches all provider exceptions and returns `CycleResult(provider_failure=True)`. The scheduler increments `consecutive_provider_failures` on the session and writes it back. After N failures (configurable), the session is auto-paused. The user can resume it when the provider is restored.

### 7.4 Application crash (SIGKILL)

Same as 7.2. Cursor is on disk. Store files are append-only JSON. The worst-case outcome is one partially-written bar or signal file. The deduplication key logic handles this: on restart, the same bar timestamp is seen again and the append is silently skipped.

### 7.5 What the scheduler does NOT need to persist

The scheduler holds no per-session state in memory. Every tick reconstructs context from the repository. No in-memory session registry is required. This means restart recovery is completely automatic.

---

## 8. Risks and Architectural Weak Points

### 8.1 Cross-user scan on every tick (LOW-MEDIUM risk)

`list_all_running_globally()` reads and deserializes every session file in `storage/forward_tests/sessions/` on every tick. At current JSON-on-filesystem storage, this is O(n sessions) reads per tick. For tens or hundreds of sessions this is acceptable; for thousands it becomes a disk I/O bottleneck.

**Mitigation for FT-2:** Acceptable at current scale. Add a note to the architecture doc that PostgreSQL migration is the scale path when sessions exceed ~500 concurrent.

### 8.2 Full-window tool recomputation on every cycle (MEDIUM risk)

`_poll_cycle()` recomputes tool outputs (SMA, RSI, etc.) over all stored bars + new bars on every cycle. For a daily strategy with 200 warmup bars and 1 new bar per day, this is 201 bars of computation per cycle — cheap. For a 1-minute strategy running for months with hundreds of thousands of stored bars, this becomes expensive.

**Mitigation for FT-2:** The current design is correct for the current scale. For FT-3, add incremental tool computation (compute only the new bars, carry forward state). This is a service-layer optimization that does not change the scheduler design.

### 8.3 Vault credential access in scheduler context (LOW risk)

The scheduler calls `vault.resolve_secret()` to decrypt provider API keys. This is server-side and correct — the vault service is already designed for internal use. The scheduler never exposes the resolved key to any response or log.

**Verification required:** Confirm that `VaultService` does not hold any per-request context (e.g., HTTP request object). A quick read of `vault/service.py` is needed before implementation.

### 8.4 APScheduler as an additional dependency (LOW risk)

APScheduler is a well-maintained Python library. Adding it requires:
```
python -m pip install apscheduler
```
And updating `requirements.txt` / `pyproject.toml`. It has no transitive infrastructure dependencies (unlike Celery). This is a well-understood addition.

**Action required:** Verify `apscheduler` is not already present in `.venv` before adding it.

### 8.5 Scheduler tick competing with user-triggered `/run-cycle` (LOW risk)

Both paths call `ForwardTestService.run_cycle()` with the same `session_id`. The idempotency model handles this: if the user manually triggers a cycle while the scheduler is mid-cycle for the same session, the second cycle will find no new bars (cursor already advanced) and return `bars_processed=0`. No corruption results.

**Theoretical edge case:** Both calls execute `_poll_cycle()` simultaneously (true concurrency). Both call `get_bars_since(same_cursor)`, both see the same new bar, both call `append_bar()`. The idempotent `append_bar()` deduplication prevents double storage, but both calls update `session.bars_evaluated` counter before either writes back — producing a race on the counter write. This is a write-write race on the JSON session file.

**Mitigation:** For FT-2, document that manual run-cycle while scheduler is active may cause a benign counter discrepancy. A file-level lock (e.g., `FileLock`) on the session JSON during scheduler writes would eliminate this. Not blocking for FT-2 at current scale.

### 8.6 No session heartbeat visible in UI (MEDIUM UX risk)

The ForwardTestPanel currently shows `last_processed_bar_timestamp` but not `last_cycle_attempted_at`. After FT-2, sessions run silently in the background and the user has no visibility into recent scheduler activity unless they trigger a manual refresh.

**Mitigation:** Add `last_cycle_attempted_at` to session detail response (new field, no breaking change). ForwardTestPanel can display "Last checked: X minutes ago" without any backend logic changes.

---

## 9. Recommended FT-2 Implementation Scope

Minimum viable FT-2 includes exactly these changes, in this order:

### Step 1 — Add APScheduler dependency
- Add `apscheduler` to `.venv` and `requirements.txt`

### Step 2 — Add settings fields
- `ft_scheduler_enabled: bool = True`
- `ft_scheduler_interval_seconds: int = 60`
- `ft_scheduler_max_consecutive_failures: int = 5`

### Step 3 — Add session fields (backward-compatible)
- `cycle_interval_seconds: int = 300` to `ForwardTestSession`
- `consecutive_provider_failures: int = 0` to `ForwardTestSession`
- `last_cycle_attempted_at: datetime | None = None` to `ForwardTestSession`

### Step 4 — Add cross-user repository method
- `ForwardTestRepository.list_all_running_globally() -> list[ForwardTestSession]`

### Step 5 — Create `backend/jobs/ft_scheduler.py`
- `ForwardTestSchedulerJob` class
- `run_tick()` async method (scans, reconstructs provider, calls service, handles failures, emits audit)
- `_build_provider_for_session()` helper (extract from route layer)

### Step 6 — Add `lifespan` to `main.py`
- Wire `ForwardTestSchedulerJob` as APScheduler interval job
- `max_instances=1`, `coalesce=True`
- `scheduler.shutdown(wait=False)` on lifespan exit

### Step 7 — Tests
- `tests/unit/test_ft_scheduler.py` — mock repository + service, verify tick calls run_cycle for RUNNING sessions only, verify auto-pause on N failures, verify PAUSED sessions are skipped
- `tests/integration/test_ft_scheduler_integration.py` — PENDING→RUNNING activation on first tick, cursor advance on second tick, restart recovery (cursor preserved across scheduler stop/start)

### Step 8 — Frontend: add `last_cycle_attempted_at` to session detail display
- Add field to `ForwardTestSessionDetailResponse` schema
- Display "Scheduler last checked: X" in ForwardTestPanel operator view

---

## 10. Files/Modules Likely Affected by FT-2

| File | Change |
|---|---|
| `backend/core/config.py` | +3 settings fields |
| `backend/forward_testing/models.py` | +3 optional session fields |
| `backend/forward_testing/repository.py` | +`list_all_running_globally()` method |
| `backend/jobs/ft_scheduler.py` | **New file** — scheduler job |
| `backend/jobs/__init__.py` | Currently empty — no change required |
| `backend/api/main.py` | Add `lifespan` context, import scheduler |
| `backend/api/schemas/forward_testing.py` | +`last_cycle_attempted_at` field in detail response |
| `requirements.txt` | +`apscheduler` |
| `tests/unit/test_ft_scheduler.py` | **New file** |
| `tests/integration/test_ft_scheduler_integration.py` | **New file** |
| `frontend/src/components/ForwardTestPanel.tsx` | Add `last_cycle_attempted_at` display in operator view |
| `frontend/src/types/forwardTesting.ts` | Add `last_cycle_attempted_at?: string | null` to detail type |

**Files that must NOT be modified:**
- `backend/forward_testing/service.py` — no changes to the evaluation engine
- `backend/strategy_registry/` — no changes to strategy logic
- Any paper trading module
- Any backtest module
- Any frontend business logic beyond the display field addition

---

## 11. Explicit Non-Goals for FT-2

The following are explicitly out of scope for FT-2 and must not be implemented:

- WebSocket / live streaming data ingestion
- Celery or distributed task queue
- Incremental tool computation (optimization for scale)
- Multi-process/multi-worker scheduler
- Broker integration or order placement of any kind
- Live trading enablement
- Paper trading scheduler (paper trading remains manually triggered in FT-2)
- Session evidence threshold changes (promotion gate stays at `>= 1 signal-eligible bar`)
- PostgreSQL migration for session storage
- Notification / webhook on signal generation
- File-level locking for concurrent write safety
- Frontend auto-refresh / WebSocket push updates

---

## 12. Validation Checklist for Future Implementation

The implementing agent must confirm each item before marking FT-2 complete:

**Architecture compliance:**
- [ ] Scheduler module does not import from `backend.strategy_registry`, `backend.strategy_runtime`, or `backend.execution`
- [ ] Scheduler module does not import from `backend.api`
- [ ] Provider adapter is built via `ProviderAdapterFactory`, not constructed directly
- [ ] Vault `resolve_secret()` is called server-side only; resolved key is never logged or returned
- [ ] `DatasetIdentity` is constructed from session fields; no provider-specific schema leaks into `ForwardTestService`
- [ ] No live trading behavior introduced

**Correctness:**
- [ ] Scheduler only processes sessions with `status == RUNNING` (not PENDING, PAUSED, or terminal)
- [ ] `max_instances=1` and `coalesce=True` are set on the APScheduler job
- [ ] `consecutive_provider_failures` resets to 0 on a successful cycle
- [ ] Auto-pause writes session update to repository with `failure_reason` set
- [ ] Scheduler is disabled when `settings.ft_scheduler_enabled == False` (allows test environments to opt out)

**Persistence/recovery:**
- [ ] After `app` restart, all RUNNING sessions resume from their stored cursor
- [ ] A session that accumulated missed bars while the app was down processes them all on the first post-restart tick
- [ ] Bars processed during a mid-tick restart are not double-counted on the next run

**Idempotency:**
- [ ] Duplicate bar timestamps are silently skipped (not errors)
- [ ] Duplicate signals are silently suppressed (not errors)
- [ ] Two simultaneous calls to `run_cycle()` for the same session do not corrupt the bar store

**Tests:**
- [ ] Unit test: RUNNING session → `run_cycle()` called once per tick
- [ ] Unit test: PAUSED session → `run_cycle()` not called
- [ ] Unit test: Terminal session → `run_cycle()` not called
- [ ] Unit test: N consecutive provider failures → session auto-paused
- [ ] Unit test: Successful cycle after failures → `consecutive_provider_failures` reset to 0
- [ ] Integration test: First tick activates PENDING session (PENDING → RUNNING)
- [ ] Integration test: Second tick polls and advances cursor
- [ ] Integration test: Scheduler restart → cursor preserved → no duplicate bars

**Observability:**
- [ ] Structured audit event emitted at scheduler tick start: `FT_SCHEDULER_TICK_STARTED`
- [ ] Audit event emitted per session evaluated: `FT_SCHEDULER_SESSION_EVALUATED`
- [ ] Audit event emitted when session skipped: `FT_SCHEDULER_SESSION_SKIPPED` with reason
- [ ] Audit event emitted on auto-pause: `FT_SCHEDULER_SESSION_AUTO_PAUSED`
- [ ] All existing `FT_POLL_COMPLETED`, `FT_SIGNAL_GENERATED`, etc. events continue to fire from within the service (no duplication in scheduler)

**Frontend:**
- [ ] `last_cycle_attempted_at` visible in ForwardTestPanel operator view
- [ ] Display degrades gracefully when `last_cycle_attempted_at` is null (session not yet run by scheduler)

---

## Appendix A: Audit Event Additions Required

The following new `AuditEventKind` values should be added to `backend/core/audit.py` for FT-2:

| Event Kind | When |
|---|---|
| `FT_SCHEDULER_TICK_STARTED` | Beginning of each scheduler tick |
| `FT_SCHEDULER_TICK_COMPLETED` | End of each tick (includes `sessions_evaluated`, `sessions_skipped`, `sessions_failed` counts) |
| `FT_SCHEDULER_SESSION_EVALUATED` | Per-session evaluation attempt in a tick |
| `FT_SCHEDULER_SESSION_SKIPPED` | Session skipped (not RUNNING, or `cycle_interval_seconds` not elapsed) |
| `FT_SCHEDULER_SESSION_AUTO_PAUSED` | Session auto-paused after N consecutive failures |
| `FT_SCHEDULER_RECOVERY` | Emitted once on startup when RUNNING sessions are found (restart recovery event) |

---

## Appendix B: Proposed Module Structure

```
backend/
└── jobs/
    ├── __init__.py          (currently empty — no changes required)
    └── ft_scheduler.py      (new — FT-2 scheduler job)
        ├── class ForwardTestSchedulerJob
        │     ├── __init__(repository, service_factory, vault, provider_factory, settings)
        │     ├── async run_tick() → None
        │     └── _build_provider_for_session(session) → RangeProviderAdapter
        └── module-level: create_ft_scheduler_job() → ForwardTestSchedulerJob
```

The `jobs/` package exists and is empty — no restructuring required.

---

## Appendix C: Timeframe-to-Interval Guidance

The scheduler runs on a fixed global interval (default 60s). Sessions with slow timeframes need not be evaluated every tick. The `cycle_interval_seconds` per-session field controls this. Recommended defaults:

| Strategy Timeframe | Recommended `cycle_interval_seconds` |
|---|---|
| 1 minute | 90 (slightly longer than bar duration for finalization buffer) |
| 5 minutes | 360 |
| 15 minutes | 1000 |
| 1 hour | 3660 |
| 4 hour | 14 700 |
| Daily | 86 460 (slightly after midnight UTC) |

The scheduler compares `last_cycle_attempted_at + cycle_interval_seconds` against `now_utc`. If not enough time has passed, the session is skipped and a `FT_SCHEDULER_SESSION_SKIPPED` event is emitted with `reason="interval_not_elapsed"`. This prevents unnecessary provider API calls for long-timeframe strategies.
