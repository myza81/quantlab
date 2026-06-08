# FT_RUNTIME_CONCURRENCY_PERSISTENCE_AUDIT.md

**Audit:** FT-2C — Forward Test Runtime Concurrency & Persistence Audit  
**Date:** 2026-06-06  
**Author:** Architecture Audit Agent  
**Status:** Complete — No runtime code modified  
**Follows:** FT-2 (Autonomous Scheduler), FT-2B (Lifecycle Integrity Hardening)

---

## 1. Executive Summary

The forward-test runtime is built on three JSON-backed filesystem stores: the session repository (one file per session), the bar store (one array file per session), and the signal store (one array file per session). The FT-2 scheduler introduces a new concurrent caller alongside the existing manual `/run-cycle` HTTP route.

**The key finding is that all three stores use a read-modify-write pattern with no locking.** Two concurrent callers for the same session will each read the current file, compute an update, and overwrite it. The last writer wins. For the bar and signal stores this is partially mitigated by their deduplication logic — the final file state will have no duplicates — but the intermediate write can be lost entirely if the two writers overlap at the OS level, depending on whether `write_text` is atomic on the target filesystem.

For the session repository the risk is more significant: both callers load the session, compute independent counter increments, and write back. The result is that one caller's counter increments are silently discarded. On macOS (APFS) and most Linux ext4/xfs filesystems `write_text` (a single `open+write+close`) is not guaranteed atomic for a full file overwrite — a crash mid-write yields a truncated or empty file.

**None of this is catastrophic at current scale.** The scheduler runs at 60-second intervals, the manual route is human-triggered, and both paths are idempotent at the bar and signal level. The practical risk is counter drift (bars_evaluated, signal_eligible_bars_processed) rather than data corruption. However, before building FT-3 incremental computation (which requires reading state that the previous cycle left behind), these races must be characterized precisely.

**Recommendation:** Implement per-session file locking (Python `fcntl.flock` on POSIX, or `filelock` cross-platform) for the session repository only, before implementing FT-3. Bar/signal stores can remain append-only with deduplication until PostgreSQL migration.

---

## 2. Current Runtime Write Paths

### 2.1 Manual `/run-cycle` route (HTTP, synchronous)

```
POST /forward-tests/{session_id}/run-cycle
    → ForwardTestService.run_cycle()
        → repository.load()                         READ  session JSON
        → ohlcv_service.get_bars_since()            PROVIDER CALL
        → bar_store.list_bars()                     READ  bar JSON
        → bar_store.append_bar() × N               READ+WRITE bar JSON (per bar)
        → signal_store.append_signal() × M         READ+WRITE signal JSON (per signal)
        → repository.update()                       WRITE session JSON (counters+cursor)
        → emit_audit_event()                        WRITE  logging handler (GIL-protected)
```

### 2.2 Scheduler tick (BackgroundScheduler thread, periodic)

```
BackgroundScheduler thread (interval = ft_scheduler_interval_seconds)
    → ForwardTestSchedulerJob.run_tick()
        → repository.list_all_running_globally()    READ  all session JSONs
        → for each session:
            → repository.update(last_cycle_attempted_at)  WRITE session JSON
            → _build_provider_for_session()         (no I/O)
            → ForwardTestService.run_cycle()        (same path as 2.1)
            → repository.update(failure_counter)    WRITE session JSON (on failure)
            → repository.update(counter reset)      WRITE session JSON (on success)
```

### 2.3 Lifecycle promotion route (HTTP, synchronous)

```
POST /forward-tests/{session_id}/promote-draft
    → repository.load()                             READ  session JSON
    → bar_store.list_bars()                         READ  bar JSON
    → assess_ft_promotion_readiness()               (pure computation, no writes)
    → draft_repository.update()                     WRITE draft JSON (not FT stores)
    → emit_audit_event()                            WRITE logging
```

### 2.4 Lifecycle control routes (pause/resume/terminate)

```
POST /forward-tests/{session_id}/pause|resume|terminate
    → repository.load()                             READ  session JSON
    → repository.update(new status)                 WRITE session JSON
```

### 2.5 Key observations from code inspection

1. `ForwardTestRepository.update()` calls `load()` first (ownership + existence check), then calls `path.write_text()`. The read and the write are **not atomic**. Between the `load()` and the `write_text()`, another writer can overwrite the file.

2. `ForwardTestBarStore.append_bar()` and `ForwardTestSignalStore.append_signal()` follow a read-entire-array → dedup check → append → write-entire-array pattern. Both operations on the same session file from two concurrent callers will produce a last-write-wins result on the file, even though the in-memory dedup check within each caller prevents logical duplicates.

3. `emit_audit_event()` uses Python's standard `logging` module, which is internally serialized via a threading lock (CPython GIL + `logging.Handler` lock). Audit writes are safe under concurrency.

---

## 3. Concurrency Risk Matrix

The FT-2 scheduler runs in a `BackgroundScheduler` daemon thread. FastAPI handles HTTP requests in Uvicorn worker threads (or, under default single-process ASGI, in the same process via async handlers running in the event loop's thread pool). Both paths can execute `run_cycle()` for the same session at the same time.

| Scenario | Probability | Data Outcome | Business Impact |
|---|---|---|---|
| Scheduler + manual `/run-cycle` run simultaneously, same session, different new bars | Low (requires precise timing) | Bar store: last writer wins; one set of bars may be partially lost if writes interleave at OS level | Bars_evaluated counter drift; bars may need reprocessing on next cycle |
| Scheduler + manual `/run-cycle` run simultaneously, same session, same new bars | Low-Medium | Bar store: both callers load same bars; dedup prevents logical duplicates in the final file if writes don't interleave | Benign if last writer includes all bars; dangerous if interleaved at OS level |
| Scheduler writes `last_cycle_attempted_at`; service writes session counters; both racing | Medium (happens every tick) | Session JSON: last writer wins; one update is lost | Counter drift on `bars_evaluated`, `signal_eligible_bars_processed`; cursor loss possible |
| Scheduler auto-pauses session (status=PAUSED) while HTTP request is mid-cycle | Low | HTTP cycle completes, then writes session with status=RUNNING over the PAUSED write | Session incorrectly back to RUNNING; auto-pause silently reverted |
| `promote-draft` reads bar store while scheduler is mid-write to bar store | Low-Medium | Read may see partial file or pre-write state | Readiness assessment based on stale bar count; may block promotion that should succeed |
| `pause` route writes status=PAUSED; scheduler tick in same moment reads RUNNING and starts cycle | Low | Scheduler starts evaluation, finishes, writes back RUNNING | Pause silently reverted for one cycle |
| Process crash during `write_text` (SIGKILL) | Rare | File truncated or empty (OS-level atomic write depends on filesystem+block size) | Session lost until manual recovery; bars/signals intact (separate files) |

### 3.1 Most Likely Races in Production

At 60-second scheduler intervals with manual route usage:

- **Most likely (Medium):** Scheduler writes `last_cycle_attempted_at` at tick start; then service finishes cycle and writes session counters. These are two separate `repository.update()` calls. The second write does NOT carry the `last_cycle_attempted_at` from the first write — it carries the stale version of the session loaded before the cycle. Result: `last_cycle_attempted_at` is written then immediately overwritten with an older value.

- **Second most likely (Low-Medium):** Scheduler tick and manual `/run-cycle` both see the same `last_processed_bar_timestamp` cursor, both call `get_bars_since()` with the same timestamp, both process the same bars. Bar store dedup prevents duplicate records in the final file (assuming no interleaved OS write). Session counters are double-incremented by both callers, then one overwrites the other — net result: one cycle's counter increment is lost.

---

## 4. Store-by-Store Safety Assessment

### 4.1 Session Repository (`ForwardTestRepository`)

**Pattern:** One JSON file per session. Writes use `path.write_text()`.

**Safety rating: UNSAFE under concurrent writes.**

- No locking on `update()`.
- `update()` reads the file, then writes it. Two concurrent writers see the same pre-update state and both write their own version.
- The last `write_text()` call wins. The other's changes are silently discarded.
- Fields at risk: `bars_evaluated`, `signal_eligible_bars_processed`, `signals_recorded`, `last_processed_bar_timestamp`, `consecutive_provider_failures`, `last_cycle_attempted_at`, `status`.
- `status` race (e.g., auto-pause vs counter update) is the most dangerous: a PAUSED status write can be silently reverted to RUNNING.
- No atomic temp-file rename pattern (`write to .tmp`, then `os.rename()`) is used.

**Crash safety:** `write_text()` on macOS APFS and Linux ext4 for files under 4KB is typically atomic (single block write) but this is a filesystem implementation detail, not a POSIX guarantee. Files >4KB or spanning multiple blocks are not guaranteed atomic. Session JSON files are small (<2KB) in practice, so crash-truncation risk is low but not zero.

### 4.2 Bar Store (`ForwardTestBarStore`)

**Pattern:** One JSON array file per session. Append writes read the full array, check for dedup, append, and rewrite the full array.

**Safety rating: EVENTUALLY CORRECT but NOT SAFE under simultaneous concurrent writes.**

- Within a single caller: deduplication by `bar_timestamp` ensures no logical duplicates.
- Across two concurrent callers: each loads the array independently. If both callers have new bars to write and their `write_text()` calls interleave at the OS level, one write may overwrite the other. This can cause bars written by caller A to disappear from the file if caller B's write lands last with an older in-memory view.
- In practice: the scheduler and manual route will rarely have truly new bars to write simultaneously (the cursor advances after the first writer completes). But during activation (PENDING→RUNNING warmup) or the first cycle after restart, this window is wider.
- No file-level lock. No temp-file-rename.

**Dedup guarantee:** Only within a single in-memory write operation. Does NOT guarantee dedup across concurrent writers if their array loads interleave.

**Crash safety:** Same as session repository. Array files are typically <100KB; risk is low but not zero.

### 4.3 Signal Store (`ForwardTestSignalStore`)

**Pattern:** One JSON array file per session. Same read-modify-write pattern as bar store.

**Safety rating: Same as bar store — EVENTUALLY CORRECT, NOT SAFE under simultaneous writes.**

- Dedup key: `(bar_timestamp, signal_direction)`.
- Same concurrent write hazard as bar store.
- Signals are less frequently written than bars (only when entry/exit conditions trigger), so the exposure window is smaller.

### 4.4 Audit Log (`emit_audit_event`)

**Pattern:** Python `logging.Logger.info()` call. Internally serialized by the logging module's handler lock.

**Safety rating: SAFE.**

CPython's `logging.Handler` base class uses a `threading.Lock` for all emit calls. All callers — scheduler thread and HTTP thread — serialize through this lock. Audit records are never lost or corrupted due to concurrency.

Note: audit records are currently log-only (no persistence store). If audit records are later persisted to a file or database, that store will require its own safety assessment.

### 4.5 Bar Store for Promotion Gate (`assess_ft_promotion_readiness`)

**Pattern:** `bar_store.list_bars()` → pure computation → no writes.

**Safety rating: STALE READ possible.**

The promotion readiness check is a pure read from the bar store. If the scheduler is mid-write to the bar store when the promotion route reads it, the promotion route may see either the pre-write or post-write state. In practice this only matters when the session is near the promotion threshold:
- If bar count is well below threshold: no race matters.
- If bar count is exactly at threshold: one bar being written concurrently could make the readiness check return "blocked" when the session actually has enough bars. The user would need to retry the promotion request after the write completes.

This is a **soft race** (a transient false-negative) — it does not corrupt data or produce false promotions.

---

## 5. Promotion Gate Race Assessment

### 5.1 Can a session be promoted while a scheduler cycle is in progress?

**Yes.** The promotion route and the scheduler run independently. There is no coordination between them.

### 5.2 Scenarios and outcomes

**Scenario A: Promotion reads bar store before scheduler writes new bars**

Promotion gate evaluates with N bars. Scheduler then writes bar N+1. Promotion succeeds based on N bars meeting the threshold. This is **correct** — the session had enough evidence at promotion time.

**Scenario B: Promotion reads bar store while scheduler is mid-write (interleaved)**

Promotion gate reads a partially written or pre-update bar file. If bar count is below threshold, promotion is blocked (false negative — user can retry). If bar count is already above threshold, promotion succeeds regardless.

**Outcome: Benign soft race — no false promotions, no data corruption.**

**Scenario C: Scheduler auto-pauses session while promotion is mid-evaluation**

1. Scheduler loads session, finds consecutive failures at threshold, writes status=PAUSED.
2. Promotion route runs: `repository.load()` loads status=PAUSED.
3. But promotion route does NOT check session status — it only checks draft status.
4. Promotion can succeed even on a PAUSED session if the bar evidence threshold is met.

**This is acceptable behavior.** A paused session still has its bars stored. Promoting based on accumulated evidence from a paused session is consistent with the evidence model.

**Scenario D: Promotion completes; scheduler tick starts in same moment; scheduler writes status=RUNNING over completed session**

The scheduler writes `last_cycle_attempted_at` + counter updates to the session. This does NOT change `draft.lifecycle_status` (the session and draft are separate objects). The session itself has no `lifecycle_status` field beyond `status` (RUNNING/PAUSED etc.). The draft's `forward_tested` lifecycle status lives in the draft repository, not the session repository. This write-back from the scheduler does not revert the promotion.

**Outcome: No promotion corruption.**

### 5.3 Summary: promotion gate is safe

The promotion gate race does not produce false promotions, data corruption, or irreversible lifecycle transitions. The only risk is a transient false-negative at the exact promotion threshold boundary, which resolves on retry.

---

## 6. Restart and Partial Write Assessment

### 6.1 Normal shutdown (SIGTERM via `scheduler.shutdown(wait=False)`)

The scheduler may be mid-tick when shutdown is called. `wait=False` means the current tick is not awaited. The tick completes in the background thread, but the process exits while it's running.

- **Session write in progress:** If the process exits before `write_text()` completes, the file is either fully written (small files, single syscall) or truncated. On restart, `_deserialize()` will raise `ForwardTestPersistenceError` on a truncated/empty file, which propagates to `list_all_running_globally()`, which the scheduler catches and logs as an error without crashing.
- **Bar/signal write in progress:** Same — truncated file means the array is invalid JSON and will raise `ForwardTestPersistenceError` on next read. This produces a `list_bars()` failure on the next cycle. The session is still intact; the service will treat the bar fetch as a provider failure and increment the failure counter.

**Practical risk:** Low. Session files are typically written in a single `write_text()` syscall for files under ~4KB. Complete writes are far more common than partial writes on clean shutdown.

### 6.2 Crash (SIGKILL / power loss)

On most POSIX filesystems, `write_text()` maps to `open()`, `write()`, `close()`. For small files that fit in one block write, this is effectively atomic. For files that span multiple blocks, crash mid-write can produce partial content.

- Session files: ~1–2KB → effectively single-block → crash-safe in practice on ext4/APFS.
- Bar files: grow over time. After weeks of daily data (20+ bars × ~200 bytes = ~4KB), bar files may span multiple blocks. Crash during write can produce truncated JSON.
- **Mitigation without locking:** Use temp-file-rename pattern: write to `{session_id}.json.tmp`, then `os.rename()`. `rename()` is atomic on POSIX for files on the same filesystem. This provides crash safety without requiring inter-process locking.

### 6.3 Restart recovery

On restart the scheduler calls `list_all_running_globally()`. Sessions with `status=RUNNING` are picked up and resumed. The cursor (`last_processed_bar_timestamp`) was last written at the end of the most recent successful cycle. If the crash happened mid-cycle (after bars were written but before session counters were updated), the cursor points to the last bar before the crash. On the next cycle, `get_bars_since(cursor)` fetches those bars again. The bar store dedup prevents double-counting.

**Counter drift on restart:** `bars_evaluated` and `signal_eligible_bars_processed` on the session may undercount by up to one cycle's worth of bars. This is a cosmetic issue for the UI progress display; it does not affect promotion readiness (which is computed from the bar store directly, not from session counters).

### 6.4 Audit log recovery

Audit logs are emitted to Python's logging infrastructure. On process crash, any log records buffered in memory are lost. This is inherent to the current log-only audit model and is not unique to the forward-testing path.

---

## 7. Recommended Locking/Persistence Design

### 7.1 What to implement for FT-3 (minimum viable safety)

**Per-session file lock on the session repository.**

Implement using Python's `fcntl.flock` (POSIX) or the cross-platform `filelock` library (which uses a companion `.lock` file). The lock scope is one session at a time — sessions do not share a global lock, so throughput scales with session count.

```python
# Pattern for ForwardTestRepository.update()
from filelock import FileLock

def update(self, session: ForwardTestSession, owner_id: str) -> None:
    lock_path = self._session_path(session.session_id).with_suffix(".lock")
    with FileLock(str(lock_path), timeout=10):
        # load (ownership check) + write inside the lock
        self.load(session.session_id, owner_id=owner_id)
        self._session_path(session.session_id).write_text(
            self._serialize(session), encoding="utf-8"
        )
```

The scheduler's `_evaluate_session()` takes the lock twice (once for `last_cycle_attempted_at`, once after the cycle). This is acceptable — the lock duration is milliseconds per write.

**Atomic temp-file rename for all stores.**

Replace `path.write_text(content)` with:
```python
tmp = path.with_suffix(".tmp")
tmp.write_text(content)
os.replace(tmp, path)  # atomic on POSIX same-filesystem
```

This eliminates crash-truncation risk for bar and signal store files. `os.replace()` is POSIX-atomic and is the correct primitive for this pattern.

This does NOT solve the concurrent read-modify-write race (two callers can still read the old version simultaneously) but it eliminates the crash-safety window for each individual write.

### 7.2 What to defer to FT-4/PostgreSQL migration

- **Read-modify-write race on bar/signal stores.** The practical consequence — counter drift — is cosmetic. Promotion is computed from bar timestamps (not session counters), so drift does not affect lifecycle correctness. Lock the session repository first; the stores can wait until PostgreSQL provides row-level locking.
- **Distributed locking.** If QuantLab ever runs multiple processes, per-file `flock` does not work across processes unless they share the same filesystem. This is a PostgreSQL migration trigger, not a short-term concern.
- **Event sourcing or WAL-style append-only log.** Would fully eliminate all race conditions but requires a substantial architecture change. Deferred to PostgreSQL migration.

### 7.3 What is NOT needed

- Global scheduler lock (a `threading.Lock` on the whole scheduler) — too coarse; blocks all sessions for one slow provider call.
- In-process session cache / session manager object — premature abstraction; adds complexity without solving the persistent-file race.
- Retry logic on write failure — if a write fails due to a race, the next cycle will correct the counter drift automatically. Retry adds complexity without meaningful benefit.

### 7.4 Priority order for FT-3 persistence changes

1. **Per-session `FileLock` on `ForwardTestRepository.update()`** — prevents status race (auto-pause revert) and counter corruption.
2. **Atomic temp-file rename on all three stores** — eliminates crash-truncation risk.
3. **Single `repository.update()` call per cycle in the scheduler** — the scheduler currently writes `last_cycle_attempted_at` before calling `run_cycle()`, then potentially writes again for failure/success counters. Consolidating these into a single post-cycle write (carrying all fields) reduces write count and narrows the race window.

---

## 8. Recommended FT-3 Implementation Scope

FT-3 should address two independent concerns:

### 8.1 Concurrency and persistence hardening (prerequisite for correctness)

Files to change:

| File | Change |
|---|---|
| `backend/forward_testing/repository.py` | `update()` wrapped in per-session `FileLock`; atomic temp-file rename in `save()` and `update()` |
| `backend/forward_testing/stores.py` | Atomic temp-file rename in `_save_raw()` for both `ForwardTestBarStore` and `ForwardTestSignalStore` |
| `backend/jobs/ft_scheduler.py` | Consolidate pre-cycle and post-cycle `repository.update()` calls into a single write after cycle completion |
| `pyproject.toml` | Add `filelock>=3.13` dependency |

Tests:
- `tests/unit/test_ft_persistence.py` — verify atomic rename behavior; verify lock prevents concurrent write corruption via threading simulation

### 8.2 Incremental tool computation optimization (performance, not correctness)

Only safe to implement after 8.1 is complete, because incremental computation relies on reading a "last successfully computed watermark" that must not drift due to concurrent writes.

**Prerequisite state needed for incremental computation:**
- `last_computed_bar_index: int | None` on `ForwardTestSession` — the index of the last bar for which tool outputs were computed. The service skips re-computation for bars below this index.
- This field must be written atomically with the session update after each cycle (inside the file lock).

Without the file lock from 8.1, `last_computed_bar_index` is subject to the same last-write-wins race, which would cause the service to re-compute bars that were already done (harmless but wasteful) or skip bars that were not yet computed (incorrect).

---

## 9. Explicit Non-Goals

The following are not in scope for FT-3 and must not be introduced:

- Broker execution logic
- Paper trading session locking (paper trading has a separate service and stores)
- Live trading behavior
- Strategy-specific scheduling logic
- Frontend business logic
- Global in-process session registry
- Distributed locking (multi-process not in scope until PostgreSQL migration)
- Audit event persistence (audit log remains log-only)
- Retry logic on write failure

---

## 10. Validation Checklist for FT-3 Implementation

### Persistence hardening

- [ ] `ForwardTestRepository.update()` uses `FileLock` with a timeout (≥10s)
- [ ] `ForwardTestRepository.save()` uses atomic temp-file rename
- [ ] `ForwardTestRepository.update()` uses atomic temp-file rename
- [ ] `ForwardTestBarStore._save_raw()` uses atomic temp-file rename
- [ ] `ForwardTestSignalStore._save_raw()` uses atomic temp-file rename
- [ ] `filelock` added to `pyproject.toml` dependencies
- [ ] `.lock` files excluded from version control (add `storage/**/*.lock` to `.gitignore`)
- [ ] `ForwardTestSchedulerJob` consolidates pre/post-cycle writes into one `repository.update()` call per evaluated session

### Correctness verification

- [ ] Concurrent test: two threads calling `repository.update()` on the same session simultaneously — only one update applied; no exception
- [ ] Crash test: verify truncated JSON file raises `ForwardTestPersistenceError` and is not silently loaded as an empty session
- [ ] After atomic rename: temp file does not persist on disk after write
- [ ] Scheduler still processes all RUNNING sessions after persistence change
- [ ] Manual `/run-cycle` still works alongside scheduler without session corruption
- [ ] Promotion readiness still reads correct bar count after concurrent bar write

### Architecture compliance

- [ ] No broker logic introduced
- [ ] No paper trading stores modified
- [ ] No live trading behavior
- [ ] No strategy logic changes
- [ ] `filelock` does not introduce cross-process locking requirements
- [ ] Lock timeout does not cause indefinite hangs (timeout parameter set)

---

## Appendix A: Race Timeline for Counter Drift (Illustrative)

```
Thread 1 (Scheduler):   load(session)  →  [bars_evaluated=50]
Thread 2 (HTTP route):  load(session)  →  [bars_evaluated=50]
Thread 1:               compute 1 bar  →  writes session [bars_evaluated=51, last_ts=T]
Thread 2:               compute 1 bar  →  writes session [bars_evaluated=51, last_ts=T]
                                                          ^^ T1's write silently overwritten
                                                          bars_evaluated correct but T1's
                                                          last_cycle_attempted_at is lost
```

If both threads process different bars (cursor mismatch):
```
Thread 1:               load session  →  cursor=T-1
Thread 2:               load session  →  cursor=T-1
Thread 1:               fetches bar T  →  writes bar [OK], writes session [cursor=T, bars=51]
Thread 2:               fetches bar T  →  bar_store dedup skips it; writes session [cursor=T, bars=51]
                                                          ^^ redundant but correct, assuming
                                                          T2 loads fresh session before computing
                                                          counter delta (it does not — T2 loaded at start)
```

In practice, Thread 2's counter update is `session.bars_evaluated + bars_processed_this_cycle`. If bars_processed_this_cycle=0 (bar was a dedup skip), the counter update is a no-op overwrite. This is benign.

The dangerous case is two threads with genuinely different new bars, both computing non-zero `bars_processed_this_cycle` from the same stale `session.bars_evaluated` baseline:

```
Thread 1 base: bars_evaluated=50  → processes 2 bars → writes bars_evaluated=52
Thread 2 base: bars_evaluated=50  → processes 1 bar  → writes bars_evaluated=51
Final: bars_evaluated=51 (Thread 2 wins) — one increment lost
```

After the file lock is in place, Thread 2 blocks until Thread 1's write completes, then re-reads the updated session and increments from 52.

---

## Appendix B: `os.replace()` Atomicity Guarantee

POSIX specification (IEEE Std 1003.1): `rename()` and `os.replace()` (which calls `rename()` internally) are required to be atomic with respect to other processes on the same filesystem. Specifically, at no point will another process see neither the old nor the new file — the old name is atomically replaced by the new one.

This means:
- A reader that opens the file between the `tmp.write_text()` and `os.replace()` sees the old content.
- After `os.replace()` completes, all subsequent opens see the new content.
- No reader ever sees a partial write.

Limitation: atomicity is **not** guaranteed across different filesystems (e.g., NFS, CIFS/SMB). QuantLab's current single-process deployment on local filesystem makes this safe. For networked storage, a different strategy is required.
