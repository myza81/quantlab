# EXECUTION_MULTI_SIGNAL_CONFLICT_AUDIT

**Audit ID:** EXEC-2C
**Date:** 2026-06-08
**Status:** Complete — findings implemented in EXEC-2D (2026-06-08)
**Auditor:** Primary Implementation Agent
**Scope:** Multi-signal same-bar conflict ordering, deduplication, and BT/PT behavioral consistency
**Predecessor audits:** EXECUTION_TIMING_LOOKAHEAD_AUDIT, EXECUTION_LIFECYCLE_FILL_AUDIT

> **EXEC-2D implementation note (2026-06-08):** Fixes 1–4 from Section 9 were implemented.
> Fix 2 (BT wash trade) was applied to both NBO and SBC paths using signal-time position state.
> Fix 3 (PENDING_SELL_EXISTS) was implemented as `PENDING_EXIT_EXISTS`.
> Fix 1/4 (conflict reason code) was implemented as `CONFLICT_EXIT_SUPPRESSED` (backtest) and
> `NO_POSITION_TO_CLOSE` continues to fire for true flat-position exits in PT (no rename needed there).
> All 5117 backend tests pass.

---

## 1. Executive Summary

A same-bar multi-signal conflict arises when both `entry_triggered` and `exit_triggered` evaluate to `True` for the same strategy on the same bar. This audit traces how such conflicts are handled across the signal extraction pipeline, the backtesting engine, and paper trading, and identifies where behavior diverges.

**Critical finding:** A same-bar BUY+SELL from a flat position produces a wash trade in backtest (NBO), but produces only a BUY in paper trading. This is a **fundamental behavioral mismatch** between backtest simulation and paper trading execution. Any strategy that fires simultaneous entry and exit signals from a flat state will produce different outcomes in these two modes, undermining forward validation of the backtest hypothesis.

**Secondary finding:** Paper trading has no `PENDING_SELL_EXISTS` guard in `_process_exit_signal()`. On consecutive bars where exit triggers while a prior pending SELL is still unfilled, duplicate pending SELL orders are created. A safety net in `_resolve_pending_order` cancels the duplicate at fill time, but the intermediate state is incorrect and produces spurious `NO_SIGNAL` / cancellation audit events.

**Summary of severity:**

| Finding | Severity | Scope |
|---|---|---|
| BT/PT same-bar BUY+SELL from flat: wash trade vs BUY-only | **High** | Behavioral correctness |
| No PENDING_SELL_EXISTS guard in PT `_process_exit_signal()` | **Medium** | Correctness, observable as spurious cancel events |
| Signal extractor ordering deterministic and tested | None (no issue) | — |
| Signal store dedup allows entry+exit on same bar | None (by design) | — |
| `_resolve_pending_order` SELL safety net functional | None (mitigates medium finding) | — |

---

## 2. Current Multi-Signal Behavior Map

### 2.1 When can both signals fire on the same bar?

`_aggregate_trigger()` in `scalar_evaluator.py` returns `True` if **any** rule of that kind triggered. Both `entry_triggered` and `exit_triggered` are evaluated independently per `BarResult`. A bar result can carry both `entry_triggered=True` and `exit_triggered=True` simultaneously whenever at least one entry rule and at least one exit rule each independently satisfied their conditions.

### 2.2 Signal extraction ordering

`signal_event_extractor.py` applies a deterministic sort key:

```python
_RULE_KIND_ORDER = {"entry": 0, "exit": 1}
# Sort key: (bar_index, rule_kind_order, rule_index, rule_id)
```

For any two signals on the same bar, entry always precedes exit. This ordering is preserved through `TradeIntentBatch` into the backtesting simulator. The ordering is tested in `test_entry_before_exit_same_bar` (both `test_signal_events.py:428` and `test_trade_intents.py:531`).

### 2.3 Signal combinations and initial positions

The meaningful conflict combinations are:

| Scenario | Initial position | Entry signal | Exit signal | Complexity |
|---|---|---|---|---|
| A | Flat | OPEN_LONG | CLOSE_LONG | **Critical mismatch** |
| B | Long | OPEN_LONG | CLOSE_LONG | Consistent across BT/PT |
| C | Flat | OPEN_LONG only | — | No conflict |
| D | Long | — | CLOSE_LONG only | No conflict |

Short side (OPEN_SHORT, CLOSE_SHORT) is not implemented; excluded.

### 2.4 Signal store deduplication (FT/PT)

`ForwardTestSignalStore` deduplicates by `(session_id, bar_timestamp, signal_direction)`. Because `entry_long` and `exit_long` are distinct `signal_direction` values, both are stored when they fire on the same bar. Same-direction same-bar signals are deduplicated across repeated cycles (correct behavior — guards against retry cycles double-recording). No conflict here.

---

## 3. Backtest Conflict Handling Findings

### 3.1 Next-Bar-Open (NBO) path — Scenario A (from flat)

1. Signal extractor emits `[OPEN_LONG, CLOSE_LONG]` for bar N (entry before exit).
2. `trade_intent_extractor.py` converts to `[TradeIntent(OPEN_LONG), TradeIntent(CLOSE_LONG)]`.
3. Simulator queues both to `pending_nbo[N+1]`.
4. At bar N+1 open price:
   - `OPEN_LONG` executes: position opened at N+1 open.
   - `CLOSE_LONG` executes: position closed immediately at N+1 open (same price).
5. Net result: **wash trade** — position opened and closed at the same fill price, no net exposure, no PnL (minus costs).

This is the backtest's implicit conflict resolution for Scenario A: **both execute sequentially, producing a wash trade**.

### 3.2 NBO path — Scenario B (from long)

1. `OPEN_LONG` executes first: `position_tracker._open_long()` rejects with `ALREADY_LONG` (guard: `state.is_long`). Intent skipped.
2. `CLOSE_LONG` executes second: position closed at N+1 open. ✓

No wash trade. Consistent intent.

### 3.3 Same-Bar-Close (SBC) path — Scenario A (from flat)

1. Both intents execute at bar N close price.
2. `OPEN_LONG` at N close → position opened.
3. `CLOSE_LONG` at N close → position closed immediately (same price).
4. Net result: **wash trade at bar N close**.

### 3.4 Same-Bar-Close (SBC) path — Scenario B (from long)

1. `OPEN_LONG` at N close → `ALREADY_LONG`, rejected.
2. `CLOSE_LONG` at N close → position closed. ✓

### 3.5 Position tracker guards

`_open_long()` rejects with `ALREADY_LONG` when `state.is_long`.
`_close_long()` rejects with `ALREADY_FLAT` when `state.is_flat`.

These guards prevent double-open and double-close. They do **not** prevent the wash trade in Scenario A from flat — both intents are valid at their moment of execution since state transitions between them.

### 3.6 Backtest summary

| Scenario | NBO outcome | SBC outcome |
|---|---|---|
| A (flat: BUY+SELL) | Wash trade at N+1 open | Wash trade at N close |
| B (long: BUY+SELL) | BUY rejected (ALREADY_LONG), SELL executes | Same |

---

## 4. Forward-Test Conflict Handling Findings

Forward testing records signals; it does not execute orders. There is no execution conflict in forward testing itself.

### 4.1 Signal recording

In `forward_testing/service.py`, entry and exit are checked independently:

```python
if getattr(bar_result, "entry_triggered", None) is True:
    # record ForwardTestSignal(signal_direction="entry_long", ...)
if getattr(bar_result, "exit_triggered", None) is True:
    # record ForwardTestSignal(signal_direction="exit_long", ...)
```

Both `if` branches are independent — both fire when both are `True`.

Both signals are stored (different `signal_direction` values → no dedup collision). A consumer reading the signal log for bar N will see both `entry_long` and `exit_long` signals. No conflict resolution is applied; the conflict is surfaced to the consumer as-is.

### 4.2 `actionable_from_bar_timestamp` (EXEC-2B)

The `actionable_from_bar_timestamp` field was added in EXEC-2B. Both the entry and exit signal for the same bar receive the same `actionable_from_bar_timestamp` (the next bar's timestamp, if present). This is correct — both signals are nominally actionable from the same bar boundary.

### 4.3 No FT-specific conflict concern

Forward testing has no ordering or deduplication gap. The behavioral mismatch documented in Section 3 is an **execution layer concern** (backtest vs paper trading), not a signal recording concern.

---

## 5. Paper-Trading Conflict Handling Findings

### 5.1 Signal processing loop

In both `forward_testing/service.py` (FT) and `paper_trading/service.py` (PT), the same-bar entry and exit signals are generated independently and processed in **entry-first order**:

```python
if getattr(bar_result, "entry_triggered", False):
    ... _process_entry_signal(...)
if getattr(bar_result, "exit_triggered", False):
    ... _process_exit_signal(...)
```

Both branches are independent `if` statements; both can fire on the same bar.

### 5.2 Scenario A (from flat): BUY+SELL on same bar

1. **Entry processed first:** `_process_entry_signal()` runs three guards:
   - `DUPLICATE_LONG_ENTRY` — no existing long → passes.
   - `PENDING_ENTRY_EXISTS` (EXEC-2A) — no existing pending BUY → passes.
   - `MAX_POSITIONS_EXCEEDED` — under limit → passes.
   - Pending BUY order created. Signal recorded as `entry_long`.

2. **Exit processed second:** `_process_exit_signal()` runs one guard:
   - `NO_POSITION_TO_CLOSE` — no **open** position exists (pending BUY is not yet filled) → **rejected**.
   - Signal recorded as `exit_long` with `NO_POSITION_TO_CLOSE` suppression reason.

3. **Net result:** Only BUY executes. No SELL.

**Backtest produces a wash trade. Paper trading produces only a BUY. These are different outcomes.**

### 5.3 Scenario B (from long): BUY+SELL on same bar

1. **Entry processed first:** `_process_entry_signal()`:
   - `DUPLICATE_LONG_ENTRY` — already long → **rejected**.

2. **Exit processed second:** `_process_exit_signal()`:
   - Open position exists → pending SELL created. ✓

3. **Net result:** Only SELL executes.

**Consistent with backtest.** ✓

### 5.4 Missing PENDING_SELL_EXISTS guard

`_process_exit_signal()` does not check whether a pending SELL already exists before creating a new one. The entry side gained a `PENDING_ENTRY_EXISTS` guard in EXEC-2A; the exit side has no equivalent.

**Scenario:** Strategy is long. Bar N triggers exit → pending SELL created. Bar N+1 triggers exit again (SELL still unfilled). `_process_exit_signal()`: open position still exists (pending SELL not yet filled) → **second pending SELL created**. Two pending SELLs now exist for the same position.

When the first pending SELL fills:
- Position closed. ✓

When the second pending SELL reaches `_resolve_pending_order`:
- Lines 1027–1047: verifies open position exists for the pending SELL. No open position. → Cancelled with `"no_position_to_close"`.

**The safety net fires correctly, but the intermediate state is wrong** — there should never be two pending SELLs for a single position. The spurious cancel event creates noise in the signal/order log and could mislead signal consumers or audit trails.

### 5.5 `_resolve_pending_order` SELL safety net

For pending SELL orders at fill time, the resolver verifies an open long position exists. If not (e.g., position already closed by a prior fill), the pending SELL is cancelled with `"no_position_to_close"`. This prevents double-close fills. Functionally correct as a last-resort guard, but not a substitute for a pre-creation guard.

---

## 6. Backtest vs Paper-Trading Consistency Matrix

| Scenario | BT (NBO) | BT (SBC) | PT | Consistent? |
|---|---|---|---|---|
| A: flat + BUY+SELL | Wash trade (buy+sell) | Wash trade (buy+sell) | BUY only | **No — critical mismatch** |
| B: long + BUY+SELL | SELL only (BUY rejected ALREADY_LONG) | SELL only | SELL only | **Yes** |
| C: flat + BUY only | BUY executes | BUY executes | BUY executes | Yes |
| D: long + SELL only | SELL executes | SELL executes | SELL executes | Yes |
| E: long + repeated SELL (consecutive bars, pending) | N/A (no pending concept) | N/A | Second SELL created then cancelled | PT-only concern |

---

## 7. Determinism and Accidental-Ordering Assessment

### 7.1 Signal extraction ordering: deterministic

The sort key in `signal_event_extractor.py` is fully deterministic:

```python
(bar_index, _RULE_KIND_ORDER[signal.rule_kind], rule_index, rule_id)
```

- `rule_kind` maps to `{"entry": 0, "exit": 1}` — same-bar entry always precedes exit.
- `rule_index` and `rule_id` provide stable tiebreakers within a kind.

This ordering is not incidental; it is explicit and tested. No accidental ordering concern at extraction.

### 7.2 Trade intent ordering: deterministic

`trade_intent_extractor.py` preserves the input signal order. OPEN_LONG always precedes CLOSE_LONG in the `TradeIntentBatch` when both are present. No accidental ordering concern at intent extraction.

### 7.3 Backtest simulation ordering: deterministic

The simulator iterates `TradeIntentBatch` in the order provided. For same-bar conflicts, intent ordering is guaranteed by the upstream sort. No accidental ordering concern at simulation.

### 7.4 Paper trading ordering: deterministic but produces the wrong outcome

PT processes entry before exit by construction (two independent `if` blocks, entry block first). This is deterministic. However, the deterministic outcome for Scenario A is **not the same** as the deterministic backtest outcome. The ordering is not the problem; the asymmetry in state availability between BT and PT is the problem.

### 7.5 Summary

Ordering is fully deterministic end-to-end. No store-insertion-order dependencies. The behavioral mismatch is structural (BT executes against simulated state transitions; PT executes against real position state), not an ordering bug.

---

## 8. Recommended Default Conflict Policy

The root cause of the Scenario A mismatch is that backtest processes both intents in the same sequential transaction against transitioning simulated state, while paper trading evaluates exit eligibility against position state at signal time (no open position yet because BUY hasn't filled).

Three policy options exist:

### Option 1: Entry wins (suppress exit when no position exists) — Recommended for consistency

**Rule:** When both entry and exit fire on the same bar and no open position exists, suppress the exit signal with a new suppression reason `CONFLICT_ENTRY_WINS`.

**BT impact:** None — backtest NBO already rejects `ALREADY_FLAT` on any close-long attempt when flat. For SBC: currently produces a wash trade; with this policy BT would also need to suppress the exit. Requires a BT-side change.

**PT impact:** Exit already suppressed with `NO_POSITION_TO_CLOSE` — no behavioral change, but a more accurate suppression reason would be added.

**Pros:** Eliminates wash trades in BT (speculative buy+sell on same bar was never intentional). Aligns BT and PT for Scenario A. Simplest to reason about.

**Cons:** Any strategy that deliberately intends a same-bar reversal (exit existing long then re-enter) would need to express this as a multi-bar signal sequence, not a simultaneous entry+exit.

### Option 2: Exit wins (suppress entry when exit fires and position is open)

**Rule:** When both fire on the same bar and a position is open, suppress the entry; when both fire and no position exists, suppress the exit.

**BT impact:** From long: already consistent (ALREADY_LONG guard). From flat: NBO currently produces wash trade; with exit-wins policy from flat, entry would be suppressed and exit would be rejected (`ALREADY_FLAT`) → no trade. A no-trade outcome is arguably worse for strategy evaluation.

**Cons:** Complex policy with position-state-dependent branch; non-obvious semantics; would require explicit BT-side enforcement.

### Option 3: Document and let strategies be responsible

**Rule:** No engine-level conflict resolution. Document that simultaneous entry+exit on the same bar produces a wash trade in BT and a BUY-only in PT. Require strategy authors to avoid this condition.

**Pros:** No engine changes.
**Cons:** Perpetuates the BT/PT mismatch, which undermines forward validation. The mismatch is hidden — strategy authors are unlikely to discover it without careful audit.

**Recommendation: Option 1 (Entry wins)**. The wash trade in backtest is an implementation artifact, not a strategy intent. Option 1 eliminates it cleanly from both BT and PT, aligns the two modes, and is the simpler reasoning model for strategy authors.

---

## 9. Required Fixes

The following fixes are identified. They are **not implemented in this audit**; they belong to a future directive.

### Fix 1 (Critical): Add `CONFLICT_ENTRY_WINS` suppression in PT `_process_exit_signal()`

**File:** `backend/paper_trading/service.py`
**Location:** `_process_exit_signal()`, before the pending SELL is created
**Change:** When both entry and exit triggered on the same bar, and no open position exists (entry pending has been created but not filled), suppress the exit with reason `CONFLICT_ENTRY_WINS` instead of `NO_POSITION_TO_CLOSE`. This makes the suppression reason semantically accurate. Functionally, the behavior is already correct (exit suppressed); only the reason code changes.

If Option 1 conflict policy is adopted, an explicit conflict check should be added:

```python
# Pseudo-code, not implementation
if entry_triggered_this_bar and not self._has_open_position(session_id):
    return self._record_suppressed_signal(..., reason="CONFLICT_ENTRY_WINS")
```

### Fix 2 (Critical): Eliminate wash trade in backtest NBO for Scenario A (from flat)

**File:** `backend/backtesting/simulator.py`
**Location:** `pending_nbo` processing loop, or upstream at `trade_intent_extractor.py`
**Change:** When both `OPEN_LONG` and `CLOSE_LONG` are queued for the same NBO slot, and the current position is flat, suppress `CLOSE_LONG` (it would immediately follow `OPEN_LONG` and produce a wash trade). This requires a conflict-resolution pass when building or draining `pending_nbo`.

Alternative: suppress the exit-side `TradeIntent` in `trade_intent_extractor.py` when the entry-side intent is present and position is flat — keeping the conflict resolution upstream of the simulator.

### Fix 3 (Medium): Add `PENDING_SELL_EXISTS` guard in PT `_process_exit_signal()`

**File:** `backend/paper_trading/service.py`
**Location:** `_process_exit_signal()`, before creating a pending SELL
**Change:** Check whether a pending SELL order already exists for this session. If yes, suppress with reason `PENDING_SELL_EXISTS`. Mirrors the `PENDING_ENTRY_EXISTS` guard added in EXEC-2A.

```python
# Pseudo-code, not implementation
if self._has_pending_sell(session_id):
    return self._record_suppressed_signal(..., reason="PENDING_SELL_EXISTS")
```

### Fix 4 (Low): Rename suppression reason for Scenario A in PT

**Current:** `NO_POSITION_TO_CLOSE` is used when exit fires with no open position.
**Issue:** When entry+exit fire simultaneously from flat, the exit is rejected with `NO_POSITION_TO_CLOSE`, which is technically accurate but misleading (the position would exist shortly after the pending BUY fills). A separate reason `CONFLICT_ENTRY_WINS` makes the conflict diagnosis explicit in signal logs.

---

## 10. Recommended Implementation Phases

### Phase 1: Documentation and detection

- Add `CONFLICT_ENTRY_WINS` and `PENDING_SELL_EXISTS` to the suppression reason enum/constants.
- Add unit tests that explicitly assert the current Scenario A behavior (PT: entry wins, exit suppressed; BT NBO: wash trade) to establish a regression baseline before any behavioral fix.

### Phase 2: PT guard alignment (Fix 3)

- Add `PENDING_SELL_EXISTS` guard to `_process_exit_signal()`.
- Low behavioral risk; mirrors EXEC-2A's pattern exactly.
- Add unit tests for consecutive-bar exit while SELL pending.

### Phase 3: Suppression reason accuracy (Fix 4)

- Introduce `CONFLICT_ENTRY_WINS` suppression reason.
- Update `_process_exit_signal()` to return this reason when entry triggered on same bar and no open position exists.
- Functional behavior unchanged; only reason code changes.

### Phase 4: BT wash trade elimination (Fix 2)

- Highest behavioral impact; requires BT simulation change.
- Must be validated against full backtest regression suite.
- Requires careful decision on where conflict resolution lives (simulator vs intent extractor).
- Deferred to a dedicated directive.

---

## 11. Test Coverage Gaps

The following test scenarios are absent from the current test suite. These should be added in Phase 1 before any behavioral fixes.

| Gap | Severity | Proposed test location |
|---|---|---|
| BT NBO: same-bar BUY+SELL from flat produces wash trade | High | `tests/unit/test_backtest_simulation.py` |
| BT NBO: same-bar BUY+SELL from long: BUY rejected, SELL executes | Medium | `tests/unit/test_backtest_simulation.py` |
| BT SBC: same-bar BUY+SELL from flat produces wash trade | High | `tests/unit/test_backtest_simulation.py` |
| PT: same-bar BUY+SELL from flat: entry executes, exit suppressed with `NO_POSITION_TO_CLOSE` | High | `tests/unit/test_paper_trading_service.py` |
| PT: same-bar BUY+SELL from long: entry rejected (DUPLICATE_LONG_ENTRY), exit executes | Medium | `tests/unit/test_paper_trading_service.py` |
| PT: consecutive-bar exit while SELL pending: second SELL created then cancelled | Medium | `tests/unit/test_paper_trading_service.py` |
| FT: same-bar BUY+SELL: both signals recorded, different direction, no dedup | Low | `tests/unit/test_forward_test_service.py` |

**Existing coverage confirmed present:**

- `test_signal_events.py:428` — `test_entry_before_exit_same_bar` confirms entry-before-exit ordering in signal extractor. ✓
- `test_trade_intents.py:531` — `test_entry_before_exit_same_bar` confirms OPEN_LONG before CLOSE_LONG ordering. ✓

---

## 12. Explicit Non-Goals

The following are explicitly out of scope for this audit and any resulting fix directive:

- **Short-side signals.** `OPEN_SHORT` and `CLOSE_SHORT` are not implemented. Multi-signal conflicts involving short positions are not in scope.
- **Partial position sizing.** Order sizing logic is not examined here.
- **Broker integration.** No broker logic is introduced or recommended.
- **Live trading behavior.** This audit covers backtest simulation and paper trading (simulated execution). Live trading is not in scope.
- **Exchange calendar inference.** No calendar logic is examined or recommended.
- **Strategy logic changes.** No strategy rules or `generate_signals()` implementations are modified.
- **Scheduler changes.** No changes to `ft_scheduler.py` or polling cadence.
- **Frontend conflict display.** How the UI surfaces conflicting signals is not addressed here.
- **Multi-strategy conflicts.** This audit covers single-strategy multi-signal conflicts (entry+exit from the same strategy on the same bar). Cross-strategy conflicts on shared positions are not in scope.
- **Fixing any of the identified issues.** This is an audit. All identified issues require separate directives before implementation.

---

## Appendix A: Source Files Referenced

| File | Purpose |
|---|---|
| `backend/strategy_registry/signal_event_extractor.py` | Signal sort order; `_RULE_KIND_ORDER` |
| `backend/strategy_registry/trade_intent_extractor.py` | Intent construction; ordering preserved |
| `backend/strategy_registry/scalar_evaluator.py` | `_aggregate_trigger`; both can be True |
| `backend/backtesting/simulator.py` | NBO/SBC intent processing; `pending_nbo` |
| `backend/backtesting/position_tracker.py` | `ALREADY_LONG`, `ALREADY_FLAT` guards |
| `backend/paper_trading/service.py` | `_process_entry_signal`, `_process_exit_signal`, `_resolve_pending_order` |
| `backend/forward_testing/service.py` | Independent entry+exit recording |
| `backend/forward_testing/stores.py` | Dedup key: `(session_id, bar_timestamp, signal_direction)` |
| `tests/unit/test_signal_events.py:428` | `test_entry_before_exit_same_bar` |
| `tests/unit/test_trade_intents.py:531` | `test_entry_before_exit_same_bar` |
| `docs/audits/EXECUTION_LIFECYCLE_FILL_AUDIT.md` | Finding 6: multi-signal conflict untested (predecessor) |
| `docs/audits/EXECUTION_TIMING_LOOKAHEAD_AUDIT.md` | BT/PT timing behavior baseline (predecessor) |
