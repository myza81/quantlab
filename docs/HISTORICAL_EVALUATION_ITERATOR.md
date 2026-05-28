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

Each bar is evaluated by the two-bar scalar engine. Current-bar values are
evaluated with the previous historical bar's values available for crossover
operators.

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

## Crossover Operators

`crosses_above` and `crosses_below` require:
- The **current bar's** resolved value
- The **previous bar's** resolved value
- Comparison of the two to detect sign change

The historical evaluator maintains rolling previous-bar scalar values. The first
bar has no previous state, so crossover outcomes are `None` on that bar.

---

## Iteration Design

### Sequential, Deterministic

Bars are evaluated in canonical ascending `bar_index` order, regardless of
payload order. Duplicate `bar_index` values are rejected because they make
historical replay ambiguous. If timestamps are present, they must be
non-decreasing when ordered by `bar_index`.

### Per-Bar Context

Each bar is fully independent:
1. Build current scalar values from `HistoricalBarContext`
2. Pair them with the previous historical bar's scalar values
3. Call the two-bar scalar engine
3. Collect `EvaluationTrace` into `BarEvaluationResult`

No portfolio, position, PnL, or execution state is carried.

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
