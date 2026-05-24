# Historical Tool Computation Pipeline — Phase 2R.0

## Purpose

Bridges the gap between OHLCV price bars and the Historical Evaluation engine.

Before this pipeline, callers had to manually compute indicator values and inject them as `tool_outputs` per bar. Now callers can provide a `StrategyToolSet` and let the server compute outputs automatically.

---

## Architecture Position

```
StrategyToolSet + OHLCV bars
        ↓
compute_tool_outputs_for_history()
        ↓
ToolComputationResult
        ↓
build_bar_tool_outputs()
        ↓
dict[bar_index → dict[ref, float]]
        ↓
HistoricalBarContext.tool_outputs
        ↓
evaluate_history()
```

---

## Output Reference Format

All tool outputs use the dot-notation reference key:

```
"{instance_id}.{output_name}"
```

Examples:
- `sma_fast.sma` — SMA instance named "sma_fast", output "sma"
- `sma_slow.sma` — SMA instance named "sma_slow", output "sma"

This key is consumed by `ScalarOperandResolver` when processing `kind: "tool_output"` conditions in semantics.

---

## Warmup Bars

Warmup bars produce **no entry** in the output dict. This is deliberate:

- The evaluator's `resolve_tool_output()` raises `OperandResolutionError` when a key is absent
- This propagates to `outcome=None` (indeterminate) for that bar
- No false signals are generated during warmup
- No lookahead bias: bar N's SMA uses only bars 0..N

Warmup count per tool: `period - 1`

---

## Input Contract

### `ToolComputationBarInput`

```python
class ToolComputationBarInput(BaseModel):
    bar_index:    int
    timestamp:    datetime | None = None
    price_fields: dict[str, float]  # must contain "close" for SMA
```

- `bar_index` must be unique across all bars
- Bars may be provided in any order; the pipeline sorts by `bar_index` internally

---

## Output Contracts

### `ToolOutputPoint`

```python
class ToolOutputPoint(BaseModel):
    bar_index: int
    timestamp: datetime | None
    value:     float
```

Only produced for post-warmup bars.

### `ToolOutputSeries`

```python
class ToolOutputSeries(BaseModel):
    instance_id:      str
    tool_id:          str
    output_name:      str
    warmup_bar_count: int
    points:           tuple[ToolOutputPoint, ...]
    
    @property
    def output_ref(self) -> str:
        return f"{self.instance_id}.{self.output_name}"
```

One series per `(instance_id, output_name)` pair.

### `ToolComputationResult`

```python
class ToolComputationResult(BaseModel):
    toolset_id:  str
    total_bars:  int
    series:      tuple[ToolOutputSeries, ...]
```

---

## API Integration

### Request Schema

`POST /semantics/evaluate-history` now accepts an optional `toolset` field:

```json
{
  "semantics": { ... },
  "bars": [
    { "bar_index": 0, "price_fields": { "close": 105.0 }, "tool_outputs": {} },
    ...
  ],
  "toolset": {
    "toolset_id": "my_toolset",
    "tools": [
      { "instance_id": "sma_fast", "tool_id": "sma", "parameters": { "period": 20 } },
      { "instance_id": "sma_slow", "tool_id": "sma", "parameters": { "period": 50 } }
    ]
  }
}
```

### Two Input Modes

**Mode 1 — Manual (original, still supported):**  
Caller computes indicator values and supplies them per bar in `tool_outputs`.

**Mode 2 — Toolset (new):**  
Caller supplies `toolset`; server computes from `price_fields["close"]`.

### Ambiguity Rule

If `toolset` is provided **and** any bar has non-empty `tool_outputs`, the request is rejected with HTTP 422. This prevents silent source-of-truth conflicts.

---

## Dispatcher Architecture

Tool computation is dispatched via a registry dict:

```python
_TOOL_DISPATCHERS: dict[str, Callable] = {
    "sma": _compute_sma_series,
    # "ema": _compute_ema_series,   ← add future tools here
    # "rsi": _compute_rsi_series,
}
```

Adding a new tool requires:
1. Implementing `_compute_<tool>_series(config, bars) → list[ToolOutputSeries]`
2. Registering the tool in `SMA_METADATA` / the tool registry
3. Adding one entry to `_TOOL_DISPATCHERS`

---

## SMA Computation Details

- **Source field:** always `price_fields["close"]`
- **Algorithm:** running sum (O(n), no lookahead)
- **Warmup:** first `period - 1` bars produce no output point
- **Output name:** `"sma"` (matches `SMA_METADATA.output_feature_names[0]`)
- **Output ref:** `"{instance_id}.sma"`

---

## Error Handling

| Error | Cause |
|-------|-------|
| `ToolComputationError` | Unknown tool_id, missing "close" field, duplicate bar_index, invalid parameters |
| `HistoricalEvaluationError` | Toolset computation failed, or ambiguous input (toolset + manual tool_outputs) |

---

## Architecture Boundaries

`historical_computation.py` must NOT import from:
- `backend.strategy_runtime`
- `backend.execution`
- `backend.forward_testing`
- `backend.backtesting`

`computation_models.py` has the same boundary. Both modules are pure computation contracts.

---

## Files

| File | Purpose |
|------|---------|
| `backend/tools/computation_models.py` | Output contracts: Point, Series, Result |
| `backend/tools/historical_computation.py` | Computation service + SMA dispatcher |
| `backend/tools/__init__.py` | Public exports |
| `backend/api/schemas/historical_evaluation.py` | `toolset` field on request DTO |
| `backend/api/services/historical_evaluation_service.py` | Toolset path orchestration |
| `tests/unit/test_historical_tool_computation.py` | 52 tests covering all paths |
