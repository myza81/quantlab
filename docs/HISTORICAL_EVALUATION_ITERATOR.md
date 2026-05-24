# HISTORICAL_EVALUATION_ITERATOR.md

## Purpose

Documents the design, responsibilities, constraints, and intentional limitations of the Phase 2P.2 historical evaluation iterator.

---

## What the Historical Evaluator Does

The historical evaluator applies a pre-compiled `EvaluationPlan` to each bar in a historical bar sequence and collects a per-bar `EvaluationTrace`.

```
EvaluationPlan
+ [HistoricalBarContext × N bars]
    ↓ evaluate_history()
HistoricalEvaluationResult
    bar_results: [BarEvaluationResult × N]
    entry_triggered_count
    exit_triggered_count
```

Each bar is evaluated independently via the same `ScalarEvaluationEngine` used in Phase 2P.1. No state transfers between bars.

---

## Why This Is Not Backtesting

| Feature | Historical Iterator | Backtesting Engine |
|---|---|---|
| Bar iteration | Yes | Yes |
| Per-bar condition evaluation | Yes | Yes |
| Portfolio state | **No** | Yes |
| Positions | **No** | Yes |
| Fills / order simulation | **No** | Yes |
| PnL / returns | **No** | Yes |
| Trade lifecycle | **No** | Yes |
| Signal generation | **No** | Yes |
| Slippage / fees | **No** | Yes |

The historical iterator answers: *"For each bar, did the conditions hold?"*

A backtesting engine answers: *"Given condition results, what trades would have been executed, and what would the PnL be?"*

These are explicitly separate responsibilities.

---

## Why No Portfolio

Portfolio accounting requires:
- Tracking entry/exit prices
- Maintaining position state between bars
- Computing returns relative to a starting capital
- Handling concurrent positions, partial fills, fees

None of this is possible from condition evaluation results alone. A future backtesting layer will consume `HistoricalEvaluationResult.bar_results` and perform portfolio simulation on top.

---

## Why Tool Outputs Are Externally Injected

Tool outputs (SMA values, RSI values, etc.) must be pre-computed and injected into each `HistoricalBarContext.tool_outputs` by the caller.

This enforces the architectural boundary:
- The evaluator is a **pure IR interpreter**
- Tool computation belongs to the **data preparation layer**
- The same evaluator works regardless of how tools compute their values

If tool computation were embedded in the iterator, the evaluator would become coupled to specific indicator implementations — breaking the generic IR-driven design.

---

## Why Crossover Operators Are Deferred

`crosses_above` and `crosses_below` require:
- The **current bar's** resolved value
- The **previous bar's** resolved value
- Comparison of the two to detect sign change

The scalar evaluator operates on a single snapshot. Even within the historical iterator, each bar's `ScalarEvaluationContext` contains only that bar's values — there is no mechanism to pass the previous bar's context.

A future multi-bar evaluator (Phase 2P.3 or similar) will maintain a rolling previous-bar state and implement crossover semantics.

---

## Iteration Design

### Sequential, Deterministic

Bars are evaluated in the order they appear in `HistoricalEvaluationInput.bars`. Equivalent inputs always produce identical outputs.

### Per-Bar Independence

Each bar is fully independent:
1. Build `ScalarEvaluationContext` from `HistoricalBarContext`
2. Call `ScalarEvaluationEngine.evaluate_plan(plan, context)`
3. Collect `EvaluationTrace` into `BarEvaluationResult`

No rollover state. No accumulation between bars.

### Context Key Convention

| Bar field | Context key | Example |
|---|---|---|
| `price_fields["close"]` | `"price.close"` | `price.close: 101.5` |
| `price_fields["open"]` | `"price.open"` | `price.open: 100.0` |
| `tool_outputs["sma_fast.value"]` | `"tool.sma_fast.value"` | `tool.sma_fast.value: 99.0` |

---

## Result Structure

### `BarEvaluationResult`

Per-bar result containing:
- `bar_index` — position in history
- `timestamp` — optional bar timestamp
- `entry_triggered` — `True/False/None` aggregate for entry rules
- `exit_triggered` — `True/False/None` aggregate for exit rules
- `trace` — full `EvaluationTrace` with all rule results and diagnostics

### `HistoricalEvaluationResult`

Aggregated result containing:
- `bars_evaluated` — total bars processed
- `entry_triggered_count` — bars where `entry_triggered is True` (not None)
- `exit_triggered_count` — bars where `exit_triggered is True` (not None)
- `bar_results` — full per-bar detail

---

## Architecture Boundary

The historical evaluator modules **MUST NOT import from**:

```
backend.strategy_runtime
backend.backtesting
backend.execution
backend.forward_testing
```

The evaluator is a standalone, pure, execution-free iterator.

---

## Future Extension Path

| Capability | Required for | How to extend |
|---|---|---|
| Crossover operators | Crossover strategies | Maintain previous-bar context per bar |
| Portfolio simulation | Backtesting | Consume `bar_results.entry_triggered`/`exit_triggered` in a separate layer |
| Slippage / fills | Realistic backtesting | Portfolio layer applies execution assumptions |
| Signal generation | Strategy runtime | Calling layer reads triggered flags and emits signals |
| Multi-asset iteration | Portfolio backtesting | Run iterator per asset, combine in portfolio layer |
| Online tool computation | Forward testing | Replace externally-injected tool outputs with live compute calls |

---

## API Endpoint

`POST /semantics/evaluate-history`

Accepts `StrategySemantics` + list of `HistoricalBarPayload`. Compiles semantics internally, constructs bar contexts, evaluates sequentially, returns `HistoricalEvaluationResult`.

Each bar payload must include all required `price_fields` and pre-computed `tool_outputs`. Missing values produce `outcome=None` with diagnostics — the iteration continues.
