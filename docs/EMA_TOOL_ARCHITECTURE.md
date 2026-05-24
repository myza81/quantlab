# EMA Tool Architecture — Phase 2R.1

## Purpose

This document describes the EMA (Exponential Moving Average) tool implementation and its role in proving the extensibility of the Historical Tool Computation Pipeline.

Phase 2R.1 validates:

```text
OHLCV → SMA + EMA computation → computed outputs → semantic evaluation → crossover evaluation
```

without any manual tool output injection.

---

## Computation Formula

```
alpha = 2 / (period + 1)

EMA[t] = alpha × close[t] + (1 − alpha) × EMA[t−1]
```

**Seed (first valid EMA):**

```
EMA[period−1] = SMA(close[0 .. period−1])
```

The seed is the simple moving average of the first `period` bars. This ensures the EMA starts from a meaningful value rather than an arbitrary anchor.

### Example: period=3, closes=[10, 20, 30, 40, 50]

```
alpha = 2/(3+1) = 0.5

warmup bars 0,1 → no output

EMA[2] = (10+20+30)/3 = 20.0       ← seed (SMA)
EMA[3] = 0.5×40 + 0.5×20 = 30.0
EMA[4] = 0.5×50 + 0.5×30 = 40.0
```

---

## Warmup Handling

| bars available | behavior |
|---|---|
| < period | no output produced |
| == period | first output: EMA = SMA seed |
| > period | EMA recursive formula applied |

Warmup count: `period - 1`

Warmup bars produce **no entry** in `bar_tool_outputs`. Their absence causes the evaluator to return `outcome=None` (indeterminate) — no false signals are generated.

---

## No-Lookahead Guarantee

EMA[t] uses only:
- `close[0]` through `close[t]` (via the seed and recursive state)

It never reads `close[t+1]` or beyond. The computation pass processes bars in sorted order by `bar_index`. Recursive state is local to each computation pass and does not leak between instances.

---

## Stateful vs Deterministic

EMA is `stateful=True` in metadata: each bar depends on the previous EMA value.

**But it is globally deterministic:** identical inputs always produce identical outputs. The state is purely local to each computation pass — it is not stored between calls. Two calls with the same bars and period produce byte-identical results.

---

## Seed Behavior Justification

Alternative seeds considered:

| Approach | Rejected reason |
|---|---|
| EMA[0] = close[0] | Produces inaccurate initial values; decays slowly toward true EMA |
| EMA[0] = 0.0 | Always wrong; introduces artificial warmup distortion |
| SMA of first period bars | Industry standard; stable starting point; matches charting platforms |

SMA seed was chosen as it matches industry convention and produces stable, predictable warmup behavior.

---

## Dispatcher Integration

EMA is registered in `_TOOL_DISPATCHERS` in [backend/tools/historical_computation.py](../backend/tools/historical_computation.py):

```python
_TOOL_DISPATCHERS: dict[str, Callable] = {
    "sma": _compute_sma_series,
    "ema": _compute_ema_series,   # ← Phase 2R.1
    # "rsi": _compute_rsi_series, # ← future: one line per tool
}
```

No evaluator changes were required. The pipeline remains:

```
tool_id → dispatcher → ToolOutputSeries → output_ref → evaluator
```

---

## Output Reference Format

EMA output references follow the same convention as SMA:

```
"{instance_id}.ema"
```

Examples:
- `ema_fast.ema` — EMA instance "ema_fast", output "ema"
- `ema_slow.ema` — EMA instance "ema_slow", output "ema"

In semantics, reference as:
```json
{ "kind": "tool_output", "ref": "ema_fast.ema" }
```

---

## Multi-Instance Support

Each EMA instance has independent recursive state within its computation pass:

```python
toolset = StrategyToolSet(tools=[
    ToolConfiguration(instance_id="ema_fast", tool_id="ema", parameters={"period": 12}),
    ToolConfiguration(instance_id="ema_slow", tool_id="ema", parameters={"period": 26}),
])
```

Produces:
- `ema_fast.ema` — independent series, period=12, warmup=11
- `ema_slow.ema` — independent series, period=26, warmup=25

No state leaks between instances.

---

## Multi-Tool Computation Proof

SMA and EMA coexist cleanly in the same toolset:

```python
toolset = StrategyToolSet(tools=[
    ToolConfiguration(instance_id="sma_fast", tool_id="sma", parameters={"period": 20}),
    ToolConfiguration(instance_id="ema_fast", tool_id="ema", parameters={"period": 20}),
    ToolConfiguration(instance_id="ema_slow", tool_id="ema", parameters={"period": 50}),
])
```

Produces three independent series:
- `sma_fast.sma`
- `ema_fast.ema`
- `ema_slow.ema`

No ref collisions. No shared mutable state. No tool-type assumptions in the evaluator.

### Key difference: EMA vs SMA after a price spike

For the same period and a step-change price series, EMA reacts faster than SMA:

```
closes = [100, 100, 100, 130, ...]   period=3, alpha=0.5

bar 3: SMA = (100+100+130)/3 = 110.0
bar 3: EMA = 0.5×130 + 0.5×100  = 115.0   ← EMA > SMA
```

This divergence is the basis for EMA-over-SMA crossover semantics.

---

## Semantic Integration

EMA outputs are consumed exactly like SMA outputs — no evaluator changes needed.

### Threshold comparison

```json
{
  "left":  { "kind": "tool_output", "ref": "ema_fast.ema" },
  "operator": ">",
  "right": { "kind": "constant", "ref": "100" }
}
```

### EMA crossover

```json
{
  "left":  { "kind": "tool_output", "ref": "ema_fast.ema" },
  "operator": "crosses_above",
  "right": { "kind": "tool_output", "ref": "ema_slow.ema" }
}
```

### Mixed SMA/EMA comparison

```json
{
  "left":  { "kind": "tool_output", "ref": "ema_fast.ema" },
  "operator": ">",
  "right": { "kind": "tool_output", "ref": "sma_fast.sma" }
}
```

---

## Parameters

| Parameter | Required | Type | Default | Notes |
|-----------|----------|------|---------|-------|
| `period`  | yes | int | — | ≥ 1; warmup = period − 1 |
| `source`  | no | str | "close" | only "close" used in current implementation |
| `name`    | no | str | None | UI display label |
| `color`   | no | str | None | hex color e.g. "#ff6b00" |

---

## Architecture Boundaries

`backend/tools/ema.py` and `backend/tools/historical_computation.py` must NOT import from:
- `backend.strategy_runtime`
- `backend.execution`
- `backend.forward_testing`
- `backend.backtesting`

The evaluator must NOT compute EMA. It only reads pre-computed values from `tool_outputs`.

---

## Files

| File | Purpose |
|------|---------|
| `backend/tools/ema.py` | `EMA_METADATA` + `compute_ema()` (visualization path) |
| `backend/tools/historical_computation.py` | `_compute_ema_series()` + `_TOOL_DISPATCHERS` registration |
| `backend/tools/__init__.py` | Public exports; `create_default_registry()` includes EMA |
| `tests/unit/test_ema_tool.py` | 71 tests covering all paths |

---

## Future Extensibility

Adding the next indicator (e.g., RSI):

1. Create `backend/tools/rsi.py` with `RSI_METADATA` and `compute_rsi()`
2. Implement `_compute_rsi_series()` in `historical_computation.py`
3. Register: `_TOOL_DISPATCHERS["rsi"] = _compute_rsi_series`
4. Register: `registry.register(RSI_METADATA)` in `create_default_registry()`
5. No evaluator changes. No semantic-layer changes.

The dispatcher pattern keeps indicator additions to 4 targeted lines across 2 files.
