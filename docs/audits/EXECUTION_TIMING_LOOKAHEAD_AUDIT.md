# EXECUTION_TIMING_LOOKAHEAD_AUDIT.md

**Audit ID:** EXEC-TIMING-AUDIT-1
**Date:** 2026-06-06
**Auditor:** Claude (Primary Implementation Agent)
**Scope:** Backtest / Forward Test / Paper Trading execution timing and lookahead bias
**Status:** COMPLETE — audit-only, no runtime code modified

---

## 1. Executive Summary

QuantLab's three execution contexts have **materially different timing models**, only one of which is fully correct.

| Context | Signal Bar | Execution Bar | Fill Price | Status |
|---|---|---|---|---|
| Backtest | Bar N | **Bar N** (same bar) | Bar N close ± slippage | ⚠ Unrealistic |
| Forward Test | Bar N (finalized) | N/A — signal-only recording | N/A | ✓ Correct |
| Paper Trading | Bar N | **Bar N+1 open** (NEXT_BAR_OPEN default) | Bar N+1 open ± slippage | ✓ Correct |

**Critical finding:** The backtest engine executes trades at the **close of the signal bar** (Bar N close), not at the next bar's open (Bar N+1 open). For indicator-based candle strategies such as EMA crossover, this is an unrealistic execution assumption that produces optimistic backtest results.

**Lookahead bias:** The backtest does NOT use future data (Bar N+1) to generate signals — indicator computation is correctly anchored to Bar N close. However, same-bar execution at the close price is practically impossible for daily-bar strategies (the market is already closed when the crossover is detected from that close).

**Paper trading** correctly defaults to `NEXT_BAR_OPEN` and explicitly models the signal-execution bar separation.

**Forward testing** correctly evaluates only finalized bars (bar close + timeframe duration + 60s buffer) and records signals without executing — no timing risk.

---

## 2. Current Backtest Timing Behavior

### 2.1 Execution Pipeline

The backtest pipeline is:
```
Historical bars
→ compute_tool_outputs_for_history()       [tools computed on bar closes]
→ evaluate_history()                       [signals detected using Bar N values]
→ extract_signal_events()                  [SignalEvent(bar_index=N)]
→ extract_trade_intents()                  [TradeIntent(source.bar_index=N)]
→ run_simulation()                         [execute at price_map[bar_index=N].close]
```

### 2.2 Signal Bar vs Execution Bar

**They are the same bar.**

In `simulator.py` (lines 116–126):
```python
for bar in sorted_bars:
    bar_close = bar.close

    # Process all intents for this bar (in intent batch order)
    for intent in intent_map.get(bar.bar_index, []):
        trade, rejection = process_intent(
            intent=intent,
            price=bar_close,   # ← Bar N close, same bar as signal
            state=state,
        )
```

The `intent_map` key is `intent.source.bar_index`, which is the same `bar_index` on which the signal was triggered in `evaluate_history()`.

### 2.3 Fill Price

**Fill price = signal bar close ± slippage.**

From `backtesting/models.py`:
> execution_price = bar close ± slippage (direction-aware)

From `position_tracker.py`:
> open_long: adjusted_price = close + slippage (adverse to buyer)
> close_long: adjusted_price = close - slippage (adverse to seller)

The `backtesting/simulator.py` route docstring explicitly states:
> "execution_price = bar close"

### 2.4 Signal/Execution Bar Separation

There is **no separation**. The `TradeIntent` model carries `source.bar_index` and `source.timestamp`, both pointing to the signal bar. The simulator uses `source.bar_index` to look up the price bar for execution. There is no `execution_bar_index` distinct from `signal_bar_index`.

### 2.5 Assessment

The backtest uses `SIGNAL_BAR_CLOSE` execution semantics implicitly and permanently. This is:

- **Not lookahead bias in the strict sense** — no future bar data is used to generate the signal or fill the order
- **Unrealistic for daily-bar strategies** — a crossover detected from today's daily close cannot realistically be executed at that same close (market already closed)
- **More realistic for sub-hourly bars** — on a 1-minute or 5-minute chart, the close of bar N and the open of bar N+1 are seconds apart; `SIGNAL_BAR_CLOSE` is a reasonable approximation

The current backtest behavior is documented in the models but is not labeled as a configurable choice — it is hardcoded as the only mode.

---

## 3. Current Forward Test Timing Behavior

### 3.1 Bar Finalization Gate

Forward testing correctly enforces bar finalization before evaluation. From `ohlcv_service.py`:

```python
def is_bar_finalized(bar_timestamp, timeframe, *, current_time, buffer_seconds=60) -> bool:
    # bar finalized when current_time >= bar_open + tf_duration + buffer
```

And `get_bars_since()` / `get_recent_bars()` only return finalized bars. This is correct: Bar N is never evaluated until it is fully closed and a 60-second buffer has elapsed.

### 3.2 Signal Recording

When a signal is detected from Bar N (finalized), the `ForwardTestSignal` record contains:

```python
ForwardTestSignal(
    bar_timestamp=bar.timestamp,      # Bar N timestamp (signal bar)
    signal_timestamp=now_utc,         # wall-clock time signal was processed
    bar_open=bar.open,                # Bar N OHLCV snapshot
    bar_high=bar.high,
    bar_low=bar.low,
    bar_close=bar.close,
    bar_volume=bar.volume,
    feature_values_at_signal=...,     # indicator values at signal bar
    signal_direction="entry_long" | "exit_long",
    ...
)
```

### 3.3 What Is Missing

The `ForwardTestSignal` record does **not** explicitly state:
- `execution_bar_index` — which bar the signal becomes tradeable at
- `actionable_from_timestamp` — the earliest timestamp at which a real order can be placed
- `intended_execution_price_type` — `next_bar_open` vs `same_bar_close`

A trader consuming FT signals must infer that the signal is actionable starting at Bar N+1 open. This is architecturally implicit but not contractually specified.

### 3.4 Assessment

Forward testing timing is **correct**: only finalized bars are evaluated, signals are informational (no execution), and bar finalization enforces that Bar N's close is fully confirmed before signal detection. There is no lookahead bias risk in forward testing.

---

## 4. Current Paper Trading Timing Behavior

### 4.1 Fill Timing Model

Paper trading has an explicit, configurable `FillTimingModel` enum (`backend/paper_trading/models.py`):

```python
class FillTimingModel(str, Enum):
    SIGNAL_BAR_CLOSE = "signal_bar_close"  # optimistic; fill at signal bar close
    NEXT_BAR_OPEN    = "next_bar_open"     # conservative; fill at next bar open
```

Default in `SimulationAssumptions`:
```python
fill_timing_model: FillTimingModel = FillTimingModel.NEXT_BAR_OPEN
```

### 4.2 NEXT_BAR_OPEN Execution Cycle

The paper trading service correctly implements NEXT_BAR_OPEN timing. Per-bar processing order (from `service.py` docstring):

```
1. Resolve NEXT_BAR_OPEN pending orders at bar.open  ← executes previous bar's signal
2. Compute tool outputs (full window)
3. Evaluate strategy signal (if bar is signal-eligible)
4. Process signal: NEXT_BAR_OPEN → create PENDING_FILL order
5. Mark open positions to bar.close
...
```

This correctly implements:
```
Bar N detected → PENDING_FILL order created → Bar N+1 cycle: step 1 resolves at bar_open
```

### 4.3 SIGNAL_BAR_CLOSE Mode

When `fill_timing_model = SIGNAL_BAR_CLOSE`, the fill is applied immediately at `bar.close` in the same processing step that detected the signal (step 4). This is an explicitly labeled and documented shortcut.

### 4.4 Signal Record Includes Signal Bar Timestamp

`PaperFill` records include `signal_bar_timestamp` (from `execution_stores.py`). This provides the distinction between the signal bar and the fill bar when in NEXT_BAR_OPEN mode.

### 4.5 Assessment

Paper trading timing is **correct and complete**. The default `NEXT_BAR_OPEN` model is realistic. The `SIGNAL_BAR_CLOSE` mode is explicitly labeled as "optimistic". The fill records include `signal_bar_timestamp`, enabling signal-to-execution traceability.

---

## 5. Fill Price Behavior Summary

| Context | Fill Price | Configurable |
|---|---|---|
| Backtest | Signal bar close ± slippage | No — hardcoded |
| Forward Test | N/A (signal only) | N/A |
| Paper Trading NEXT_BAR_OPEN | Next bar open ± slippage | Yes |
| Paper Trading SIGNAL_BAR_CLOSE | Signal bar close ± slippage | Yes |

The backtest fill price behavior matches `SIGNAL_BAR_CLOSE` in paper trading, but in the backtest this is an implicit assumption with no configuration option.

---

## 6. Signal-Bar vs Execution-Bar Assessment

### Backtest

```
EMA crossover detected on Bar N
→ signal_bar_index = N
→ execution_bar_index = N          ← same bar
→ fill_price = Bar N close ± slip
```

**Status: Non-compliant with next-bar-open model. Same-bar execution.**

There is no `signal_bar_index` vs `execution_bar_index` distinction anywhere in the backtest pipeline. The `TradeIntent.source.bar_index` serves both purposes — it is the signal origin AND the execution lookup key.

### Forward Test

```
EMA crossover detected on finalized Bar N
→ signal recorded with bar_timestamp = Bar N timestamp
→ no execution — signal is informational only
→ next tradeable price = Bar N+1 open (implicit, not recorded)
```

**Status: Compliant (no execution risk). Missing explicit actionable_from field.**

### Paper Trading (NEXT_BAR_OPEN default)

```
EMA crossover detected on Bar N
→ PENDING_FILL order created (signal_bar_timestamp = Bar N ts)
→ Bar N+1 cycle: resolved at bar_open
→ fill_price = Bar N+1 open ± slippage
```

**Status: Compliant with next-bar-open model.**

---

## 7. Lookahead Bias Risk Matrix

| Risk Category | Backtest | Forward Test | Paper Trading |
|---|---|---|---|
| Future bar data used for signal | ✓ None | ✓ None | ✓ None |
| Signal detected from forming candle | ✓ N/A (historical) | ✓ Finalization gate enforced | ✓ Finalization gate enforced |
| Execution uses future bar data | ✓ None — uses signal bar | ✓ N/A | ✓ None |
| Same-bar signal + execution | ⚠ **YES — always** | ✓ N/A | Optional (SBC mode) |
| Execution before signal is confirmed | ✓ None | ✓ None | ✓ None |
| Indicator computation uses future values | ✓ None | ✓ None | ✓ None |
| Warmup bars leak future state into signals | ✓ None | ✓ None | ✓ None |
| Gap bars suppress signals correctly | ✓ N/A (historical) | ✓ Gap detection active | ✓ Gap detection active |
| Last-bar signal creates orphan order | ⚠ Possible — simulator silently skips missing price bar | ✓ N/A | ✓ PENDING_FILL cancelled on terminate |

### Notes on "Same-bar signal + execution" risk

The backtest consistently uses `SIGNAL_BAR_CLOSE`. For daily bars, this means:
- Monday daily bar closes at 16:00 ET
- EMA crossover is detected from that 16:00 close
- Simulation executes at 16:00 close (market already closed — unreachable in reality)
- The earliest real execution would be Tuesday's open

For intraday bars (e.g. 1m, 5m), the gap between bar N close and bar N+1 open is small, making `SIGNAL_BAR_CLOSE` a reasonable approximation.

**This is not classic lookahead bias** (no future bar used), but it is an **optimistic execution assumption** that inflates backtest performance for daily-bar strategies.

---

## 8. Existing Test Coverage Review

### 8.1 Backtest Execution Timing

| Test | File | Coverage |
|---|---|---|
| Trade at correct bar_index | `test_backtest_simulation.py` | ✓ Implicit — bar_index matching |
| Fill price = bar close | `test_backtest_simulation.py` | ✓ Partial — cost model tests verify adj_price |
| Signal bar === execution bar | None | ✗ **Not tested explicitly** |
| Next-bar-open execution | None | ✗ **Not implemented / not tested** |
| Final bar signal = no trade next cycle | None | ✗ **Not tested** |
| Crossover at Bar N → fill at Bar N close | None | ✗ **Not tested end-to-end** |

### 8.2 Forward Test Timing

| Test | File | Coverage |
|---|---|---|
| Only finalized bars evaluated | `test_ohlcv_forward_test_extensions.py` | ✓ `is_bar_finalized` unit tests |
| Signal timestamp vs bar timestamp differ | `test_forward_test_service.py` | ✓ Partial |
| No execution on signal bar | N/A — FT is signal-only | ✓ By design |
| Actionable_from field exists | None | ✗ Field does not exist |

### 8.3 Paper Trading Timing

| Test | File | Coverage |
|---|---|---|
| NEXT_BAR_OPEN creates pending order | `test_paper_trading_service.py` | ✓ `test_nbo_creates_pending_order_only` |
| NEXT_BAR_OPEN fill deferred to next bar | `test_paper_trading_service.py` | ✓ `n_open == 0` assertion |
| SIGNAL_BAR_CLOSE fills immediately | `test_paper_trading_service.py` | ✓ `test_sbc_fills_immediately_and_opens_position` |
| Pending order resolved at bar.open | `test_paper_trading_service.py` | ✓ `test_buy_pending_order_resolves_at_bar_open` |
| Signal bar vs execution bar differ (NBO) | `test_paper_trading_service.py` | ✓ Implicit — pending order lifecycle |
| Crossover signal at Bar N executes Bar N+1 open | None | ✗ **No end-to-end crossover timing test** |

---

## 9. Required Fixes

### Priority 1 — Backtest: Add NEXT_BAR_OPEN Execution Model (Recommended)

**Problem:** The backtest simulator hardcodes `SIGNAL_BAR_CLOSE` execution. There is no `NEXT_BAR_OPEN` option.

**Impact:** Backtest results are systematically optimistic for daily-bar strategies. A trader following backtest results exactly cannot replicate performance because the fill prices in backtests are close prices that are unavailable to a real trader after a daily bar closes.

**Required changes (not implementing here — audit scope only):**
1. Add `execution_model: ExecutionModel` field to `BacktestSimulationConfig` with values `SIGNAL_BAR_CLOSE` (current, backward-compat default) and `NEXT_BAR_OPEN` (recommended)
2. Add `open: float` field to `SimulationPriceBar` (currently only has `close`)
3. Change `run_simulation()` to use `price_map[bar_index + 1].open` when `execution_model == NEXT_BAR_OPEN`
4. Handle the final-bar edge case: signal on the last available bar produces no trade in `NEXT_BAR_OPEN` mode (no N+1 bar)
5. Add `signal_bar_index` and `execution_bar_index` to `SimulatedTrade` for audit traceability

**Affected files:**
- `backend/backtesting/models.py`
- `backend/backtesting/simulator.py`
- `backend/backtesting/position_tracker.py`
- `backend/api/schemas/backtest_simulation.py`
- Tests: `tests/unit/test_backtest_simulation.py`

### Priority 2 — Forward Test Signal Contract: Add `actionable_from` Field (Nice-to-Have)

**Problem:** `ForwardTestSignal` records the signal bar OHLCV snapshot but does not specify when the signal becomes tradeable (i.e., at Bar N+1 open). A user consuming FT signals must infer this.

**Required changes:**
- Add `actionable_from_bar_timestamp: datetime | None` to `ForwardTestSignal`
- Compute as `bar_timestamp + timeframe_to_timedelta(session.timeframe)`
- Include in API responses via `ForwardTestSignalResponse`

**Affected files:**
- `backend/forward_testing/models.py`
- `backend/forward_testing/service.py`
- `backend/api/schemas/forward_testing.py`
- `frontend/src/types/forwardTesting.ts`

### Priority 3 — Backtest: Add Missing `open` Price to SimulationPriceBar (Prerequisite for Fix #1)

**Problem:** `SimulationPriceBar` only carries `close`. Once `NEXT_BAR_OPEN` mode is implemented, the next bar's `open` is required for fill pricing.

**Note:** This is a prerequisite for Priority 1, not a standalone fix.

---

## 10. Recommended Execution Timing Contract

The following contract is recommended for all execution contexts:

```
Bar N data is complete (candle closed + finalization buffer elapsed)
→ Indicators computed from Bar N close values only
→ Strategy evaluated using Bar N data
→ Signal generated (signal_bar_index = N, signal_timestamp = now_utc)
→ Order created as PENDING (no fill yet)
→ Bar N+1 arrives:
    → Order resolved at Bar N+1 open price
    → execution_bar_index = N+1
    → fill_price = Bar N+1 open ± slippage
```

**Special cases:**
- Signal on final available bar: no fill (no N+1 bar available)
- SIGNAL_BAR_CLOSE mode: acceptable for intraday research with explicit labeling
- Warmup bars: signals suppressed; no orders generated during warmup

**Required signal/trade data contract fields:**

| Field | Current Status | Recommendation |
|---|---|---|
| `signal_bar_index` | Implicit in backtest (intent.source.bar_index) | Add explicit field |
| `signal_timestamp` | Present in FT/PT | Add to backtest SimulatedTrade |
| `execution_bar_index` | Absent in backtest | Add as signal_bar_index + 1 for NBO mode |
| `execution_timestamp` | Absent in backtest | Add |
| `intended_execution_price_type` | Absent in backtest | Add ("next_open" / "same_close") |
| `fill_price` | Present in all (as SimulatedTrade.price) | ✓ |
| `fill_reason` | Absent in backtest | Add (e.g., "entry_signal", "exit_signal") |

---

## 11. Recommended Implementation Phases

### Phase EXEC-1 — Backtest Execution Model Upgrade

**Scope:** Add `NEXT_BAR_OPEN` as a configurable backtest execution model.

Tasks:
1. Add `open: float` to `SimulationPriceBar`
2. Add `ExecutionModel` enum to `BacktestSimulationConfig` (default: `SIGNAL_BAR_CLOSE` for backward compat)
3. Modify `run_simulation()` to support `NEXT_BAR_OPEN` path
4. Handle final-bar edge case in `NEXT_BAR_OPEN` mode
5. Add `signal_bar_index` and `execution_bar_index` to `SimulatedTrade`
6. Add tests: crossover signal at Bar N fills at Bar N+1 open; final bar produces no trade
7. Update `BacktestSimulationConfig` documentation

**Risk:** Medium — touching the core simulation path. Backward-compatible via default.

### Phase EXEC-2 — Forward Test Signal Contract Enrichment

**Scope:** Add `actionable_from_bar_timestamp` to `ForwardTestSignal`.

Tasks:
1. Add `actionable_from_bar_timestamp: datetime | None` to `ForwardTestSignal`
2. Compute in `ForwardTestService._poll_cycle()` using `timeframe_to_timedelta`
3. Expose in `ForwardTestSignalResponse` schema
4. Update frontend `ForwardTestSignal` type

**Risk:** Low — additive field, backward compatible.

### Phase EXEC-3 — Backtest Timing Tests

**Scope:** Add explicit timing contract tests for the backtest layer.

Tests to add:
- `test_signal_at_bar_N_executes_at_bar_N_close` (documents current behavior)
- `test_next_bar_open_mode_uses_next_bar_open` (after EXEC-1)
- `test_final_bar_signal_produces_no_trade_in_nbo_mode` (after EXEC-1)
- `test_ema_crossover_end_to_end_fill_price` (integration)

---

## 12. Explicit Non-Goals

This audit does NOT recommend:

- Modifying forward test evaluation logic
- Modifying paper trading execution logic (already correct)
- Changing signal generation behavior
- Changing indicator computation behavior
- Changing bar finalization logic
- Introducing broker execution logic
- Introducing live trading behavior
- Changing the frontend
- Changing strategy semantics
- Changing the crossover evaluator

---

## 13. Compliance Status Summary

| Requirement | Backtest | Forward Test | Paper Trading |
|---|---|---|---|
| Indicators computed from completed candles only | ✓ | ✓ | ✓ |
| Signals generated only after candle is complete | ✓ | ✓ | ✓ |
| Entries at next candle open after confirmed signal | ✗ (uses same-bar close) | N/A | ✓ (NEXT_BAR_OPEN default) |
| Exits at next candle open after confirmed exit signal | ✗ (uses same-bar close) | N/A | ✓ (NEXT_BAR_OPEN default) |
| No same-candle-close execution without explicit labeling | ✗ (unlabeled, hardcoded) | ✓ | ✓ (labeled "optimistic") |
| No future bar data in signal generation | ✓ | ✓ | ✓ |
| Signal timestamp recorded separately from execution timestamp | ✗ (no separation) | ✓ (bar_timestamp vs signal_timestamp) | ✓ (signal_bar_timestamp in fill) |
| Signal bar recorded separately from execution bar | ✗ | N/A | ✓ |
| Reproducible and deterministic | ✓ | ✓ | ✓ |
| Final-bar signal handled correctly | ⚠ Silently skipped (MISSING_PRICE rejection) | N/A | ✓ PENDING_FILL cancelled on terminate |

---

## 14. Appendix: Key File References

| Concern | File | Lines |
|---|---|---|
| Backtest same-bar execution | `backend/backtesting/simulator.py` | 116–126 |
| Backtest fill price = bar close | `backend/backtesting/position_tracker.py` | 27–30 |
| Backtest execution assumption stated | `backend/backtesting/models.py` | 14–15 |
| Route docstring: "execution_price = bar close" | `backend/api/routes/backtest_simulation.py` | 40–44 |
| FT bar finalization gate | `backend/services/ohlcv_service.py` | `is_bar_finalized()` |
| FT signal record (no execution_bar) | `backend/forward_testing/service.py` | 697–720 |
| PT FillTimingModel definition | `backend/paper_trading/models.py` | 131–142 |
| PT NEXT_BAR_OPEN default | `backend/paper_trading/models.py` | 186 |
| PT pending order resolution at bar.open | `backend/paper_trading/service.py` | 653–674 |
| PT fill includes signal_bar_timestamp | `backend/paper_trading/service.py` | 1111 |

---

*Audit completed: 2026-06-06. No runtime code was modified.*
