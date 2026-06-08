# EXECUTION_LIFECYCLE_FILL_AUDIT.md

**Audit ID:** EXEC-2
**Date:** 2026-06-07
**Auditor:** Claude (Primary Implementation Agent)
**Scope:** Full execution lifecycle and order fill model across Backtest, Paper Trading, and Forward Test
**Predecessor audit:** `EXECUTION_TIMING_LOOKAHEAD_AUDIT.md` (EXEC-TIMING-AUDIT-1)
**Status:** COMPLETE — audit-only, no runtime code modified

---

## 1. Executive Summary

EXEC-1 corrected the backtest simulator's default execution timing from same-bar-close to NEXT_BAR_OPEN. This audit examines the full execution lifecycle that surrounds that timing fix: from signal generation through order creation, fill computation, position update, and realized P&L.

**Overall lifecycle realism rating:**

| Context | Timing | Fill Model | Lifecycle Completeness | Long-Only | Audit Trail |
|---|---|---|---|---|---|
| Backtest | ✓ NBO default | ✓ Open ± slippage | ⚠ No pending order record | ✓ Full | ✓ Trade log |
| Paper Trading | ✓ NBO default | ✓ Open ± slippage | ✓ Full order/fill/position | ✓ Enforced | ✓ PT audit events |
| Forward Test | ✓ Signal-only | N/A | ✓ Signal record only | N/A | ✓ FT signal log |

**Main gaps found:**

1. **Backtest has no serialized pending-order concept** — EXEC-1 uses an in-memory `pending_nbo` dict, not a persisted `PendingOrder` record. Correct for a sequential simulation, but it means the "pending" concept is invisible in the trade log.
2. **Scale-in asymmetry** — Backtest rejects ALREADY_LONG; paper trading implicitly allows adding to an existing position (scale-in) by skipping the max-positions check when a position already exists for the symbol.
3. **NBO cash/quantity estimate uses signal-bar close** — Paper trading's pre-signal cash check and quantity computation use `bar_close` as the price proxy for the next open. Gap-up opens can produce quantity mismatches or fill cancellations not caught at signal time.
4. **Commission fee base asymmetry** — Backtest PERCENTAGE commission is on slippage-adjusted notional; paper trading PERCENTAGE fee is on pre-slippage gross price. Numerically small but contractually different.
5. **`ForwardTestSignal` still missing `actionable_from_bar_timestamp`** — Not addressed by EXEC-1; still the EXEC-2 task.
6. **Multi-signal conflict ordering** is not documented or tested (same-bar entry + exit queue behavior).
7. **Stop loss / take profit** not implemented anywhere — correct for EOD long-only but must be explicitly declared non-goal.

---

## 2. Current Execution Lifecycle Map

### 2.1 Backtest Lifecycle (after EXEC-1)

```
Historical price bars + StrategyDraft
    ↓ compute_tool_outputs_for_history()   [tool indicators on all bars]
    ↓ evaluate_history()                   [signal rules evaluated per bar]
    ↓ extract_signal_events()              [SignalEvent(bar_index=N)]
    ↓ extract_trade_intents()              [TradeIntent(source.bar_index=N, action=OPEN/CLOSE_LONG)]

run_simulation()  [NEXT_BAR_OPEN default]
    ↓ _run_next_bar_open()
        ├── Pre-compute next_bar_map (bar_index → next SimulationPriceBar)
        ├── For each bar in order:
        │   ├── STEP 1: Resolve pending_nbo[bar.bar_index] — fills using bar.open ± slippage
        │   │       → SimulatedTrade(action=open_long, execution_bar_index=bar_index, price=bar.open±slip)
        │   │       → PositionState mutated: cash reduced, position_quantity set, avg_entry_price set
        │   ├── STEP 2: Queue intent_map[bar.bar_index] into pending_nbo[next_bar.bar_index]
        │   │       → FINAL_BAR_NO_FILL rejection if last bar
        │   └── STEP 3: Equity point (uses bar.close for mark-to-market)
        └── After loop: MISSING_PRICE rejection for intents with no price bar

Concepts present:
    signal_event     ← SignalEvent (rule id, bar_index)
    trade_intent     ← TradeIntent (action, source bar, intent_id)
    [pending order]  ← pending_nbo dict (in-memory only, NOT serialized)
    simulated_trade  ← SimulatedTrade (open_long / close_long record)
    position_state   ← PositionState (mutable, not serialized)
    equity_point     ← BacktestEquityPoint (per-bar equity snapshot)
    rejection        ← BacktestRejection (audit record)

Concepts absent:
    ✗ PendingOrder (no serialized order record — pending_nbo is internal loop state)
    ✗ Partial fills
    ✗ Multiple simultaneous positions
    ✗ Stop/limit orders
    ✗ Position scaling
```

### 2.2 Paper Trading Lifecycle (Phase 4E.3)

```
Per-cycle execution order:
    1. Resolve pending NEXT_BAR_OPEN orders at bar.open
       → PaperBrokerAdapter.build_fill(gross_price=bar.open)
       → PaperFill record created (self-documenting: gross, slip, fee, net)
       → PaperPosition opened/closed/scaled
       → PaperAccount.cash_balance adjusted
       → PaperOrderStore: PENDING_FILL → FILLED
    2. Compute tool outputs (full window)
    3. Evaluate strategy signal (if signal-eligible bar)
    4. Process signal:
       │  Entry (BUY):
       │    → Duplicate position check (see §3 below)
       │    → Quantity resolve using bar.close as price estimate
       │    → Cash check using bar.close as price estimate
       │    → NBO: create PaperOrder(PENDING_FILL) → persisted to PaperOrderStore
       │    → SBC: build fill immediately at bar.close
       │  Exit (SELL):
       │    → Find open position for symbol
       │    → Use full position.quantity as sell quantity
       │    → NBO: create PaperOrder(PENDING_FILL)
       │    → SBC: fill immediately at bar.close
    5. Mark-to-market all positions at bar.close → PaperAccount.equity updated
    6. Equity + drawdown recalculation
    7. Drawdown stop check → session PAUSED if exceeded
    8. AccountStateSnapshot appended (per signal-eligible bar)
    9. Persist bar + advance cursor

Concepts present:
    ForwardTestSignal   ← signal record (shared with FT — no fill info)
    PaperOrder          ← full order lifecycle: PENDING_FILL → FILLED/CANCELLED/REJECTED
    PaperFill           ← immutable fill record (self-documenting)
    PaperPosition       ← open/closed position with avg_entry_price, unrealized/realized PnL
    PaperAccount        ← session account with running cash/equity/drawdown
    AccountStateSnapshot ← per-bar equity curve data point
    PT_* audit events   ← full audit trail for all lifecycle events
```

### 2.3 Forward Test Lifecycle

```
Per-cycle execution order (signal-only):
    1. get_bars_since(cursor) → new finalized bars only
    2. compute_tool_outputs_for_history() (full window)
    3. evaluate_history()
    4. For each new bar: emit ForwardTestSignal if triggered
       → bar_timestamp (market time) recorded
       → signal_timestamp (wall-clock time) recorded
       → bar OHLCV snapshot recorded
       → feature_values_at_signal recorded
    5. Persist bars + advance cursor

Concepts present:
    ForwardTestSignal   ← signal record only; no fill, no order, no position
    ForwardTestBar      ← bar persistence for catch-up/watermark

Concepts absent (by design):
    ✗ Order, fill, position, P&L — all deferred to paper trading
    ✗ actionable_from_bar_timestamp (missing — EXEC-2 task)
```

---

## 3. Backtest Fill Model Findings

### 3.1 Entry Fill Price

| Mode | Fill Price |
|---|---|
| NEXT_BAR_OPEN (default) | `bar_N+1.open + slippage` (adverse to buyer) |
| SAME_BAR_CLOSE (explicit) | `bar_N.close + slippage` (adverse to buyer) |

Slippage formula: `adj_price = raw_price + slippage_per_unit` for open_long.

### 3.2 Exit Fill Price

| Mode | Fill Price |
|---|---|
| NEXT_BAR_OPEN (default) | `bar_N+1.open - slippage` (adverse to seller), floored at 0 |
| SAME_BAR_CLOSE (explicit) | `bar_N.close - slippage` (adverse to seller), floored at 0 |

### 3.3 Slippage Application

- NONE: no adjustment
- FIXED: `slippage_per_unit = slippage_value` (fixed price units per share)
- PERCENTAGE: `slippage_per_unit = raw_price × slippage_value`

Both modes adversely adjust the execution price. Floor at 0 on close. Correct.

### 3.4 Commission

- NONE: zero
- FIXED: `commission = commission_value` (flat per trade, NOT per share)
- PERCENTAGE: `commission = qty × adj_price × commission_value` (applied on slippage-adjusted notional)

**Note:** PERCENTAGE commission base uses `adj_price` (after slippage). This differs from paper trading which uses `gross_price` (before slippage) as the fee base. See §11.

### 3.5 Quantity Sizing

- FIXED_QUANTITY: constant `fixed_quantity` units
- EQUITY_FRACTION: `qty = floor(cash × equity_fraction / adj_entry_price)`
  - `cash` is used as equity when flat (no unrealized P&L while flat, correct)
  - Quantity is resolved at fill time using the actual fill price (open for NBO, close for SBC)

Sizing is correct — quantity is resolved at fill time using the actual execution price.

### 3.6 Available Cash Check

- At fill time: `total_cash_out = qty × adj_price + commission`
- If `total_cash_out > state.cash` → INSUFFICIENT_CASH rejection
- No pre-signal cash reservation or cash locking mechanism

**Gap:** In NBO mode, cash is not reserved at signal time. Between signal bar N and execution bar N+1, nothing prevents:
- Multiple signals queuing up for the same bar N+1
- Multiple signals from different bars all queued for the same execution bar
- The first fill consuming all cash; subsequent fills from the same execution bar get INSUFFICIENT_CASH rejections

This behavior is correct for a single-instrument single-position system (the second fill is ALREADY_LONG anyway), but matters for multi-signal scenarios.

### 3.7 Long-Only Enforcement

- ALREADY_LONG (open_long while holding): explicit rejection ✓
- ALREADY_FLAT (close_long while flat): explicit rejection ✓
- No short path in TradeIntentAction: only OPEN_LONG / CLOSE_LONG ✓
- No negative position_quantity possible ✓
- No leverage / margin: not modeled ✓

### 3.8 Duplicate Buy Prevention

In the backtest, ALREADY_LONG is a hard rejection at the position_tracker level. If a second OPEN_LONG intent fires while a position is open (from a prior fill), it is immediately rejected regardless of intent ordering.

In NBO mode: if OPEN_LONG intent is queued at bar N and hasn't yet been filled at bar N+1, and another OPEN_LONG fires at bar N+1, that second OPEN_LONG is also queued for bar N+2. At bar N+1, the first fill executes OPEN_LONG → position opens. At bar N+2, the second fill attempts OPEN_LONG → ALREADY_LONG rejection. Correct behavior.

### 3.9 Exit Without Position

ALREADY_FLAT rejection on close_long when position_quantity == 0. Correct.

### 3.10 Realized P&L Formula

```
realized_pnl = (adj_close_price - avg_entry_price) × qty
               - commission_close
               - commission_entry
```

Where `avg_entry_price` = `adj_open_price` (slippage already baked in from open fill). This is an all-in net P&L including both commissions and slippage. Correct and consistent.

---

## 4. Paper Trading Fill Model Findings

### 4.1 Entry Fill Flow (NBO mode)

```
Signal at bar N (step 4):
    1. Check existing position for this symbol
       - If position exists: SKIP max_positions check → proceed to quantity/cash check
       - If no position: check count_open >= max_concurrent_positions → MAX_POSITIONS_EXCEEDED
    2. Compute qty = PaperBrokerAdapter.compute_quantity(fill_price=bar.close)
       ⚠ Uses bar.close as fill price estimate even in NBO mode
    3. Cash sufficiency check (estimate using bar.close)
       ⚠ Uses bar.close not bar_N+1.open — may over- or under-estimate
    4. Create PaperOrder(PENDING_FILL) → save_pending()

At bar N+1 (step 1 of next cycle):
    1. load_pending() → [order]
    2. Build fill at bar_N+1.open ± slippage
    3. Cash sufficiency check AGAIN using actual fill values
       → If insufficient: CANCELLED ("insufficient_cash_at_fill")
    4. Apply fill → PaperPosition updated, PaperAccount.cash_balance reduced
```

### 4.2 Exit Fill Flow (NBO mode)

```
Signal at bar N:
    1. Find open position for symbol
       - No position → NO_POSITION_TO_CLOSE rejection
    2. qty = int(position.quantity)  ← full position close
    3. Create PaperOrder(PENDING_FILL, direction=SELL)

At bar N+1:
    1. Build fill at bar_N+1.open ± slippage
    2. Verify open position still exists → if not: CANCELLED ("no_position_to_close")
    3. Apply fill → position closed, cash_balance increased
```

### 4.3 Scale-In Behavior (Paper Trading)

**Finding:** Paper trading implicitly allows scale-in for an existing position.

```python
existing_pos = self._find_open_position(session_id, session.symbol)
if existing_pos is None:
    open_count = self._position_store.count_open(session_id)
    if open_count >= assumptions.max_concurrent_positions:
        # reject with MAX_POSITIONS_EXCEEDED
# else: existing position exists → skip max_positions check
# → proceed to create another BUY order (scale-in)
```

If a position is already open in this symbol, a new BUY signal will create another order and scale into the position. This is inconsistent with backtest behavior (ALREADY_LONG rejection for any second BUY while long).

For a typical single-position long-only strategy:
- Backtest: second BUY always rejected (ALREADY_LONG)
- Paper Trading: second BUY creates a scale-in (additional purchase)

**Risk:** This asymmetry means paper trading results can diverge from backtest results when multiple entry signals fire while a position is open (e.g., repeated crossover signals in a trending market).

### 4.4 NBO Quantity Estimate Discrepancy

For NEXT_BAR_OPEN mode, paper trading estimates the fill price using `bar.close` at signal time:

```python
qty = PaperBrokerAdapter.compute_quantity(
    assumptions=assumptions,
    fill_price=bar_close,          # ← bar N close, not bar N+1 open
    current_equity=account.equity,
)
```

**Scenario — gap-up open:**
- Bar N close: $100. Signal fires. Qty estimated: `floor(10000 × 0.95 / 100) = 95`.
- Bar N+1 open: $110 (gap up). Actual fill price: $110 + slippage.
- 95 units × $110 = $10,450 — exceeds estimated budget of $9,500.
- Second cash check at fill time: `required = 95 × $110 = $10,450 > cash` → CANCELLED.

**Consequence:** Order is cancelled at fill time even though it was accepted at signal time. The session is left flat when the strategy expected a position to open. This behavior is correct (conservative), but the mismatch between signal-time acceptance and fill-time cancellation is opaque to the user.

**Scenario — gap-down open:**
- Bar N close: $100. Cash check at signal time: `required = 95 × $100 = $9,500 < $10,000` → accepted.
- Bar N+1 open: $90 (gap down). Fill price: $90.
- `qty × $90 = $8,550` < available cash → fill succeeds, but fewer dollars were actually deployed.
- In EQUITY_FRACTION mode, qty was computed for $100 open; at $90 open, the allocated fraction is lower than intended.

**Assessment:** The quantity estimate using signal-bar close is a known approximation in NBO mode. The double cash check prevents over-allocation. However, the quantity mismatch for gap-down scenarios means the equity fraction allocation is not precise.

### 4.5 Fee Base Difference

Paper trading fee computation uses `gross_price` (pre-slippage):
```python
fee = quantity × gross_price × fee_value   # PERCENTAGE mode
fee = fee_value                             # FLAT mode
```

This differs from backtest which uses `adj_price × qty × rate` for PERCENTAGE commission. For reasonable slippage (<1%), the difference is negligible. For large slippage values, the fee base diverges.

### 4.6 Realized P&L

Paper trading tracks `realized_pnl` on `PaperPosition` and `PaperAccount`. The computation (from `_apply_sell_fill`, not inspected in this audit) closes a position by marking `is_open=False` and computing realized P&L from the fill record. The `PaperFill` is fully self-documenting: `(gross_price, slippage, fill_price, gross_value, fee, net_value)` — all values needed for independent verification are present.

---

## 5. Forward Test Compatibility Findings

### 5.1 Current Signal Record

`ForwardTestSignal` carries:

| Field | Present | Notes |
|---|---|---|
| `signal_id` | ✓ | UUID |
| `session_id` | ✓ | UUID |
| `bar_timestamp` | ✓ | Market time of triggering bar |
| `signal_timestamp` | ✓ | Wall-clock time of evaluation |
| `signal_direction` | ✓ | `entry_long` / `exit_long` |
| `rule_id` | ✓ | Originating strategy rule |
| `bar_open/high/low/close/volume` | ✓ | OHLCV snapshot |
| `feature_values_at_signal` | ✓ | Tool outputs at signal bar |
| `warmup_satisfied` | ✓ | |
| `strategy_snapshot_hash` | ✓ | |
| `symbol`, `timeframe` | ✓ | |

### 5.2 Missing Fields for Execution Consumers

| Missing Field | Why Needed | Status |
|---|---|---|
| `actionable_from_bar_timestamp` | Bar N+1 open time — earliest executable time | Still absent — EXEC-2 task |
| `intended_execution_model` | Whether signal expects NBO or SBC fill | Not present; inferred from session |
| `actionable_from_bar_index` | Bar N+1 index | Not present |

A paper trading session consuming FT signals must infer actionability from `bar_timestamp + timeframe_to_timedelta(timeframe)`. This is architecturally correct but not contractually specified.

### 5.3 Signal Provenance Adequacy

For the current consumption pattern (PT session uses FT session's signals via `signal_id` on `PaperOrder`), the signal record is sufficient. The `signal_bar_timestamp` is recorded on the `PaperOrder` for traceability. The missing `actionable_from_bar_timestamp` is a UX gap, not a correctness gap.

---

## 6. Backtest vs Paper Trading Consistency Matrix

| Property | Backtest | Paper Trading | Consistent? |
|---|---|---|---|
| Default execution model | NBO (signal bar N → fill bar N+1 open) | NBO (same) | ✓ |
| Entry fill price (NBO) | bar_N+1.open + slippage | bar_N+1.open + slippage | ✓ |
| Exit fill price (NBO) | bar_N+1.open − slippage | bar_N+1.open − slippage | ✓ |
| Slippage adversity direction | BUY+, SELL− | BUY+, SELL− | ✓ |
| Slippage floor at zero | ✓ | ✓ | ✓ |
| Commission/fee mode | NONE / FIXED / PERCENTAGE | NONE / FLAT / PERCENTAGE | ✓ (naming differs) |
| Commission/fee base (PERCENTAGE) | adj_price (after slippage) | gross_price (before slippage) | ⚠ Different base |
| Long-only enforcement | ALREADY_LONG rejection | max_positions + scale-in path | ⚠ Scale-in asymmetry |
| Sell without position | ALREADY_FLAT rejection | NO_POSITION_TO_CLOSE rejection | ✓ (equivalent) |
| Duplicate buy prevention | Hard reject (ALREADY_LONG) | Soft: max_positions + implicit scale-in | ⚠ Different semantics |
| Quantity sizing (EQUITY_FRACTION) | Resolved at fill time (actual fill price) | Resolved at signal time (close estimate) | ⚠ Different timing |
| Cash sufficiency check | At fill time only | At signal time (estimate) + at fill time | ⚠ Double-check |
| Pending order record | In-memory dict only (not serialized) | PaperOrder (persisted, auditable) | ⚠ Different lifecycle |
| Final-bar signal handling | FINAL_BAR_NO_FILL rejection | PENDING_FILL cancelled on terminate | ✓ (equivalent outcome) |
| Realized P&L formula | (adj_close − avg_entry) × qty − both commissions | Via PaperFill (net_value − entry cost) | ✓ Conceptually consistent |
| Unrealized P&L | (bar.close − avg_entry) × qty | (current_price − avg_entry) × qty | ✓ |
| Position scaling | Not supported (ALREADY_LONG) | Implicitly allowed | ⚠ Asymmetry |
| Audit trail | Trade list + rejection list | Full PT_* audit events | ✓ (PT more granular) |

**Summary of material asymmetries:** 3 items require attention (scale-in, commission base, quantity estimate timing). 2 items are informational differences (pending order serialization, audit granularity).

---

## 7. Stop-Loss / Take-Profit Modeling Assessment

**Status: Not implemented anywhere.**

Current execution models support only:
- Market entry at bar open (NBO) or bar close (SBC)
- Market exit at bar open (NBO) or bar close (SBC) when exit rule fires
- No limit orders
- No stop orders
- No intrabar price modeling (no high/low usage for exits)
- No gap-through stop scenario (stop at $95, bar opens at $90 → fill at $90 gap, not $95)
- No simultaneous stop + target evaluation within a bar

**Risk for intraday strategies:** On sub-daily timeframes, intrabar price movement matters. A stop at $95 on a bar that has `low=$88` would be hit mid-bar, but the current simulation ignores it. Exits only happen at bar open or bar close.

**Recommendation:**

| Decision | Recommended Action |
|---|---|
| Stop loss / take profit | **Explicitly deferred** — not a blocker for EOD long-only strategies |
| Intrabar modeling | **Document as non-goal** for current scope |
| Gap-through fills | **Document behavior**: fill at bar open regardless of stop price |
| Conservative default | Do not model stop/TP until a dedicated EXEC-3 (intrabar modeling) phase |

The scope constraint is already documented in `backend/backtesting/models.py`:
> Scope constraints — NOT implemented: stop-loss sizing, ...

This is appropriate. No action needed in current phases.

---

## 8. Gap Risk and Intrabar Ambiguity Assessment

### 8.1 Gap Risk (NEXT_BAR_OPEN)

For both backtest and paper trading in NBO mode:
- Fill happens at the actual `bar.open` of Bar N+1
- If bar N+1 opens far above/below bar N close, that gap is the fill price
- Slippage is applied ON TOP of the gap-open price (adverse direction)
- No cap on gap size; no "virtual mid-point" fill

**Assessment:** Gap risk is handled correctly. The gap-open fill is the realistic worst-case for market orders at next open. No intervention required.

### 8.2 Intrabar Ambiguity

For both systems, bar processing uses only `open` and `close`:
- `open` is used for NBO fills
- `close` is used for SBC fills and equity mark-to-market
- `high` and `low` are stored in ForwardTestBar and FT signals but not used for execution logic

**Implication:** A stop loss at a price that was hit intrabar (between `low` and `close`) would not trigger. This is documented as out of scope. Correct.

### 8.3 Paper Trading NBO Gap Cancellation Scenario

As noted in §4.4, a significant gap-up open can cause an NBO order to be cancelled at fill time even though it was accepted at signal time. The user sees: signal fired, no position opened. This is correct behavior but produces an invisible failure without an explicit `SIGNAL_ACCEPTED_BUT_FILL_CANCELLED` explanation in the session cycle result.

**Recommendation:** Consider adding a `gap_fill_cancellations: int` counter to `PaperCycleResult` in a future phase. Low priority.

---

## 9. Multi-Signal Conflict Assessment

### 9.1 Backtest: Same-Bar Entry + Exit

If a strategy's entry rule and exit rule both fire on bar N:
- Both OPEN_LONG and CLOSE_LONG intents are in `TradeIntentBatch.intents`
- Both get queued to `pending_nbo[bar_N+1.bar_index]`
- At bar N+1, they are processed in `TradeIntentBatch` order

Processing order depends on how `extract_trade_intents()` orders intents (entry before exit or exit before entry). If entry is processed first:
1. OPEN_LONG fills → position opens
2. CLOSE_LONG fills → position immediately closes
→ Result: a zero-holding round-trip in the same bar

If exit is processed first:
1. CLOSE_LONG → ALREADY_FLAT rejection (no position to close)
2. OPEN_LONG fills → position opens
→ Result: position opened

**Finding:** The signal evaluation engine fires both entry and exit conditions independently. The interaction is order-dependent and untested. For EOD crossover strategies, a bar is unlikely to produce both entry AND exit simultaneously. But this scenario is not explicitly guarded.

### 9.2 Paper Trading: Same-Bar Entry + Exit

In paper trading, both entry and exit signals are processed in the same step 4:

```python
if getattr(bar_result, "entry_triggered", False):
    # create BUY order (or fill for SBC)
if getattr(bar_result, "exit_triggered", False):
    # create SELL order (or fill for SBC)
```

For SBC: BUY fill + SELL fill in same step. The SELL checks for open position. If BUY was processed first and position was opened, SELL would close it. If SELL was processed first, NO_POSITION_TO_CLOSE rejection.

For NBO: two PENDING_FILL orders created (one BUY, one SELL). At next bar step 1:
- pending orders processed in `load_pending()` order (file store order → insertion order)
- BUY fills first → position opens; SELL fills next → position closes
- OR SELL fills first → CANCELLED (no position) → BUY fills → position opens

**Finding:** Multi-signal conflict behavior is deterministic but not explicitly documented or tested. Insertion order in the order store determines which resolves first.

### 9.3 Repeated Signal (Same Signal on Consecutive Bars)

For FT and PT: signal deduplication is enforced by `ForwardTestSignalStore.append_signal()` using `(session_id, bar_timestamp, signal_direction)` as the dedup key. A repeated signal on a different bar timestamp is a NEW signal. Correct.

For backtest: no signal deduplication — each `TradeIntent` is uniquely identified. A repeated entry signal on the next bar while already long → ALREADY_LONG rejection. Correct.

### 9.4 Pending Order While New Signal Fires

**Backtest NBO:** If OPEN_LONG intent queued for bar N+1, and another OPEN_LONG fires at bar N+1 (queued for bar N+2):
- At bar N+1 step 1: first OPEN_LONG fills → position opens
- At bar N+1 step 2: new OPEN_LONG queued for bar N+2
- At bar N+2 step 1: second OPEN_LONG attempts fill → ALREADY_LONG rejection

Correct behavior.

**Paper Trading NBO:** If BUY pending order exists from bar N signal, and another BUY signal fires at bar N (or bar N+1 before the first order resolves), a second PENDING_FILL BUY order is created. Both will be in pending store. At resolution:
- First BUY fills → position opens
- Second BUY fills → scale-in (not rejection, as discussed in §4.3)

This is the scale-in asymmetry described above.

---

## 10. Long-Only / Halal Guardrail Assessment

### 10.1 Backtest

- TradeIntentAction has only `OPEN_LONG` and `CLOSE_LONG` — no SHORT path
- ALREADY_LONG rejection prevents duplicate long entry
- ALREADY_FLAT rejection prevents SELL without position
- position_quantity can never go negative (only set to qty at open, reset to 0.0 at close)
- No leverage: cash must cover total cost
- No margin: all cash deducted immediately at fill

**Status: ✓ Long-only guardrails fully enforced at model level.**

### 10.2 Paper Trading

- `allow_short_selling: bool = False` in SimulationAssumptions
- `SHORT_SELLING_DISABLED` rejection reason defined
- `NO_POSITION_TO_CLOSE` rejection for SELL without position
- `OrderDirection.BUY` / `OrderDirection.SELL` are the only directions — no SELL_SHORT path
- Position quantity enforced positive when `is_open=True`

**Finding:** `allow_short_selling` field exists in `SimulationAssumptions` but the service layer enforcement of this field was not inspected in detail. Based on available code, SELL signals only close existing positions — no short-sell path exists in `_process_exit_signal`. The guard is correct by design (no code path for shorting).

**Status: ✓ Long-only guardrails enforced. Short-selling disabled by default and by code structure.**

### 10.3 Halal Compliance Readiness

Current system:
- No interest, no leverage, no margin (✓ structurally aligned)
- No short selling (✓ enforced)
- No instrument-specific compliance screening (deferred to policy layer)

The system does not enforce prohibited instruments (e.g., financials, tobacco) — this is documented as a deferred policy layer (Phase 4F+). No action needed now.

---

## 11. Test Coverage Review

### 11.1 Backtest Execution Tests (post EXEC-1)

| Test Scenario | File | Status |
|---|---|---|
| NBO entry fill at next open | `test_backtest_simulation.py::TestNextBarOpenExecution` | ✓ |
| NBO exit fill at next open | `test_backtest_simulation.py::TestNextBarOpenExecution` | ✓ |
| FINAL_BAR_NO_FILL rejection | `test_backtest_simulation.py::TestNextBarOpenExecution` | ✓ |
| Fill price = next open + slippage | `test_backtest_simulation.py::TestNextBarOpenExecution` | ✓ |
| signal_bar_index != execution_bar_index | `test_backtest_simulation.py::TestNextBarOpenExecution` | ✓ |
| signal_timestamp != execution_timestamp | `test_backtest_simulation.py::TestNextBarOpenExecution` | ✓ |
| SBC explicit only | `test_backtest_simulation.py::TestNextBarOpenExecution` | ✓ |
| Crossover timing regression | `test_backtest_simulation.py::TestNextBarOpenExecution` | ✓ |
| ALREADY_LONG rejection (duplicate buy) | `test_backtest_position_tracker.py` | ✓ |
| ALREADY_FLAT rejection (sell without position) | `test_backtest_position_tracker.py` | ✓ |
| INSUFFICIENT_CASH rejection | `test_backtest_position_tracker.py` | ✓ |
| ZERO_QUANTITY rejection (equity_fraction) | `test_backtest_position_sizing.py` | ✓ |
| Commission modes (NONE/FIXED/PCT) | `test_backtest_cost_model.py` | ✓ |
| Slippage modes (NONE/FIXED/PCT) | `test_backtest_cost_model.py` | ✓ |
| **NBO: pending buy exists + new entry signal** | None | ✗ Not tested |
| **NBO: entry + exit both queued same bar N+1** | None | ✗ Not tested |
| **Equity_fraction: gap-open qty mismatch** | None | ✗ Not applicable (backtest resolves qty at actual fill price) |
| **Commission base on adj_price vs raw_price** | Implicit in cost tests | ~ Partial |

### 11.2 Paper Trading Tests

| Test Scenario | File | Status |
|---|---|---|
| NBO creates PENDING_FILL order | `test_paper_trading_service.py` | ✓ |
| NBO fill deferred to next bar | `test_paper_trading_service.py` | ✓ |
| SBC fills immediately | `test_paper_trading_service.py` | ✓ |
| Pending order resolved at bar.open | `test_paper_trading_service.py` | ✓ |
| NO_POSITION_TO_CLOSE (SELL without pos) | `test_paper_trading_service.py` | ✓ |
| insufficient_cash_at_fill cancellation | `test_paper_trading_service.py` | ✓ |
| Drawdown stop triggers PAUSED | `test_paper_trading_service.py` | ✓ |
| AccountStateSnapshot appended per bar | `test_paper_trading_service.py` | ✓ |
| **Scale-in: second BUY while position open** | None | ✗ Not explicitly tested |
| **NBO gap-up: signal-time accept, fill-time cancel** | None | ✗ Not tested |
| **Same-bar entry + exit (NBO order conflict)** | None | ✗ Not tested |
| **Qty estimate vs actual fill price divergence** | None | ✗ Not tested |
| **Fee base (gross vs adj price)** | `test_paper_trading_broker_adapter.py` | ~ Partial |

### 11.3 Forward Test Tests

| Test Scenario | File | Status |
|---|---|---|
| Signal record created on rule fire | `test_forward_test_service.py` | ✓ |
| bar_timestamp vs signal_timestamp | `test_forward_test_service.py` | ✓ |
| Duplicate signal suppressed | `test_forward_test_service.py` | ✓ |
| No fill/position in FT signal | By design | ✓ |
| `actionable_from_bar_timestamp` field | None | ✗ Field does not exist |

---

## 12. Required Fixes

### Priority 1 — Scale-In Asymmetry (Backtest vs Paper Trading)

**Problem:** Backtest rejects all duplicate BUY signals (ALREADY_LONG). Paper trading silently allows scale-in when an open position already exists for the symbol.

**Impact:** Backtests and paper trading results diverge for strategies that generate repeated entry signals while long. The user cannot trust that paper trading replicates backtest behavior.

**Required change:**
- In `PaperTradingService._process_entry_signal()`, add an explicit check: if an open position exists for this symbol AND scale-in is not explicitly enabled, reject with a `DUPLICATE_LONG_ENTRY` rejection code.
- OR: add `allow_scale_in: bool = False` to `SimulationAssumptions` and enforce it consistently.
- Default must be: scale-in NOT allowed (consistent with backtest ALREADY_LONG behavior).

**Files affected:**
- `backend/paper_trading/execution_models.py` (new `RejectionReason.DUPLICATE_LONG_ENTRY`)
- `backend/paper_trading/models.py` (optional: `allow_scale_in` in SimulationAssumptions)
- `backend/paper_trading/service.py` (enforce in `_process_entry_signal`)

**Risk:** Low — additive rejection check. Tests must be updated.

### Priority 2 — Forward Test Signal Contract (`actionable_from_bar_timestamp`)

**Problem:** `ForwardTestSignal` does not record when the signal becomes actionable (Bar N+1 open). Users must infer this from `bar_timestamp + timeframe_to_timedelta(timeframe)`.

**Required change:**
- Add `actionable_from_bar_timestamp: datetime | None` to `ForwardTestSignal`
- Compute in `ForwardTestService._poll_cycle()` as `bar.timestamp + timeframe_to_timedelta(session.timeframe)`
- Also add to the paper trading signal record path (same ForwardTestSignal model is shared)
- Expose in `ForwardTestSignalResponse` schema and frontend type

**Files affected:**
- `backend/forward_testing/models.py`
- `backend/forward_testing/service.py`
- `backend/api/schemas/forward_testing.py`
- `frontend/src/types/forwardTesting.ts`

**Risk:** Low — additive field, backward compatible (None for legacy signals).

### Priority 3 — NBO Quantity Estimate Discrepancy Documentation and Optional Fix

**Problem:** In paper trading NBO mode, quantity is resolved using `bar.close` at signal time, but the actual fill happens at the next `bar.open`. Gap-up opens cause fill cancellations; gap-down opens cause under-allocation.

**Recommended approach:** Document the behavior explicitly in `SimulationAssumptions` docstring. Add a `gap_fill_cancellations` counter to `PaperCycleResult`. Do not change the estimation logic (it would require knowing the next bar open, which is unavailable at signal time).

**Files affected:**
- `backend/paper_trading/models.py` (docstring)
- `backend/paper_trading/service.py` (PaperCycleResult counter)

**Risk:** Minimal — documentation + counter only.

### Priority 4 — Commission Fee Base Alignment (Optional)

**Problem:** Backtest PERCENTAGE commission uses slippage-adjusted price; paper trading PERCENTAGE fee uses pre-slippage gross price. Numerically small for typical slippage (<1%) but contractually inconsistent.

**Recommended approach:** Document the difference explicitly in both `BacktestSimulationConfig` and `SimulationAssumptions` docstrings. Alignment is possible but requires changing one system's formula, which would be a breaking change to test expectations.

**Decision:** Document only. Do not change formulas until a dedicated contract-alignment phase.

---

## 13. Recommended Execution Lifecycle Contract

The following contract is recommended for all execution contexts after fixes are applied:

```
SIGNAL CONTRACT
    Signal on Bar N:
    - signal_bar_index = N
    - signal_bar_timestamp = Bar N market timestamp
    - actionable_from_bar_timestamp = Bar N timestamp + timeframe_delta (Bar N+1 open time)
    - signal_direction = entry_long | exit_long

ORDER CONTRACT
    Pending order created at signal time:
    - direction = BUY | SELL
    - quantity = floor(equity × fraction / close_estimate)  [NBO: close is estimate]
    - fill_timing_model = NEXT_BAR_OPEN
    - signal_bar_timestamp recorded on order

FILL CONTRACT
    Fill at Bar N+1 open:
    - gross_price = bar_N+1.open
    - fill_price = gross_price ± slippage (adverse)
    - fee = computed from gross_price
    - net_value = quantity × fill_price
    - fill_bar_timestamp = Bar N+1 timestamp
    - execution_bar_index = N+1
    - execution_bar_timestamp = Bar N+1 timestamp

POSITION CONTRACT
    After BUY fill:
    - position opened / scaled
    - average_entry_price = fill_price (or weighted avg for scale-in)
    - cash_balance -= net_value + fee
    After SELL fill:
    - position closed / reduced
    - realized_pnl = (fill_price - avg_entry) × qty - fees
    - cash_balance += net_value - fee

GUARDRAILS
    - No duplicate long entry (ALREADY_LONG / DUPLICATE_LONG_ENTRY)
    - No SELL without position (ALREADY_FLAT / NO_POSITION_TO_CLOSE)
    - No negative cash (INSUFFICIENT_CASH)
    - No short selling (SHORT_SELLING_DISABLED)
    - No leverage or margin

LONG-ONLY ENFORCEMENT
    Backtest:  ALREADY_LONG rejection at position_tracker layer
    Paper Trading: DUPLICATE_LONG_ENTRY rejection in service layer (after fix)
    Both:      consistent rejection behavior — no scale-in without explicit opt-in
```

---

## 14. Recommended Implementation Phases

### Phase EXEC-2A — Scale-In Guard (Highest Priority)

**Scope:** Prevent implicit scale-in in paper trading; align duplicate-buy behavior with backtest.

Tasks:
1. Add `DUPLICATE_LONG_ENTRY` to `RejectionReason` enum
2. In `_process_entry_signal`: if `existing_pos is not None`, reject with `DUPLICATE_LONG_ENTRY`
3. Update tests: `test_paper_trading_service.py` — second BUY while long → rejection
4. Document in `SimulationAssumptions` docstring: scale-in requires future `allow_scale_in=True` opt-in

**Risk:** Low. One guard added. No architecture change.
**Recommended:** Implement in the same session as EXEC-2B.

### Phase EXEC-2B — Forward Test Signal Contract Enrichment

**Scope:** Add `actionable_from_bar_timestamp` to `ForwardTestSignal`.

Tasks (same as prior EXEC-2 recommendation from EXEC-TIMING-AUDIT-1):
1. Add `actionable_from_bar_timestamp: datetime | None` to `ForwardTestSignal`
2. Compute in `ForwardTestService._poll_cycle()` using `timeframe_to_timedelta`
3. Expose in `ForwardTestSignalResponse` schema
4. Update frontend `ForwardTestSignal` type

**Risk:** Low — additive field.

### Phase EXEC-2C — Multi-Signal Conflict Tests

**Scope:** Add tests for multi-signal and conflicting-order scenarios.

Tests to add:
- Backtest: same-bar entry + exit both queued → correct resolution order
- Backtest: NBO pending buy exists, new entry signal fires → ALREADY_LONG at execution
- Paper Trading: same-bar BUY + SELL NBO → pending conflict → correct resolution
- Paper Trading: second BUY signal while position open → DUPLICATE_LONG_ENTRY (after EXEC-2A)

**Risk:** Very low. Tests only.

### Phase EXEC-3 (Deferred) — Intrabar Stop/Target Modeling

**Scope:** Support stop-loss and take-profit logic using intrabar `high`/`low` prices.

Tasks (future):
1. Add `StopLossConfig` / `TakeProfitConfig` to `BacktestSimulationConfig` (optional fields)
2. In the per-bar loop: check if `bar.low` hits stop or `bar.high` hits target
3. Model gap-through fills conservatively (fill at bar.open if bar opens through stop)
4. Emit `STOP_LOSS_TRIGGERED` / `TAKE_PROFIT_TRIGGERED` in trade records

**Risk:** Medium. Significant change to the simulation loop. Deferred until needed.

---

## 15. Explicit Non-Goals

This audit does NOT recommend:

- Modifying the signal evaluation engine (`evaluate_history`, `extract_trade_intents`)
- Changing indicator computation behavior
- Introducing broker execution or live trading behavior
- Adding randomness, stochastic fills, or order book simulation
- Implementing multi-asset portfolio tracking
- Implementing partial fills
- Implementing leverage or margin modeling
- Changing the bar finalization logic for forward testing
- Changing the halal instrument screening (deferred policy layer)
- Changing frontend behavior
- Adding stop-loss or take-profit logic (deferred to Phase EXEC-3)
- Adding per-candle gap detection in OHLCVService (known deferred item)

---

## Appendix A: Key File References

| Concern | File | Relevant Section |
|---|---|---|
| Backtest execution model | `backend/backtesting/models.py` | `BacktestExecutionModel`, `SimulatedTrade`, `BacktestRejectionReason` |
| Backtest NBO loop | `backend/backtesting/simulator.py` | `_run_next_bar_open()` |
| Backtest position tracker | `backend/backtesting/position_tracker.py` | `process_intent()`, `_open_long()`, `_close_long()` |
| Backtest cost model | `backend/backtesting/cost_model.py` | `apply_slippage()`, `compute_commission()` |
| PT simulation assumptions | `backend/paper_trading/models.py` | `SimulationAssumptions`, `FillTimingModel` |
| PT execution models | `backend/paper_trading/execution_models.py` | `PaperOrder`, `PaperFill`, `PaperPosition`, `RejectionReason` |
| PT broker adapter | `backend/paper_trading/broker_adapter.py` | `compute_fill_price()`, `compute_quantity()`, `build_fill()` |
| PT service cycle | `backend/paper_trading/service.py` | `_poll_cycle()`, `_process_entry_signal()`, `_resolve_pending_order()` |
| PT scale-in gap | `backend/paper_trading/service.py` | `_process_entry_signal()` L1099–L1130 |
| FT signal model | `backend/forward_testing/models.py` | `ForwardTestSignal` |
| FT service cycle | `backend/forward_testing/service.py` | `_poll_cycle()` |

---

## Appendix B: Compliance Status After EXEC-1

| Requirement | Backtest | Forward Test | Paper Trading |
|---|---|---|---|
| Signal from completed bar only | ✓ | ✓ | ✓ |
| Default execution at next bar open | ✓ (NBO default, EXEC-1) | N/A | ✓ (NBO default) |
| Signal bar recorded separately from execution bar | ✓ (EXEC-1) | N/A | ✓ |
| Duplicate long entry rejected | ✓ ALREADY_LONG | N/A | ⚠ Scale-in allowed (fix needed) |
| Sell without position rejected | ✓ ALREADY_FLAT | N/A | ✓ NO_POSITION_TO_CLOSE |
| Final-bar signal handled safely | ✓ FINAL_BAR_NO_FILL | N/A | ✓ CANCELLED on terminate |
| Long-only enforcement | ✓ | N/A | ✓ |
| Signal `actionable_from` timestamp | N/A (backtest) | ⚠ Missing | ⚠ Missing |
| Stop/limit order support | ✗ Deferred | N/A | ✗ Deferred |
| Full pending order lifecycle | ⚠ In-memory only | N/A | ✓ Persisted |
| Commission/fee base consistent | ⚠ Adj price | N/A | ⚠ Gross price |

---

*Audit completed: 2026-06-07. No runtime code was modified.*
