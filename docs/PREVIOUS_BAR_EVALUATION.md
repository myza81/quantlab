# Previous-Bar Evaluation — Phase 2P.3

## Overview

Phase 2P.3 extends the evaluator stack with temporal crossover operator support.
`crosses_above` and `crosses_below` require two consecutive bar values — the
previous bar and the current bar — to determine whether a crossover event occurred.

---

## Crossover Semantics

### `crosses_above`

```
previous_left <= previous_right  AND  current_left > current_right
```

Triggers when the left operand transitions from at-or-below the right operand to
strictly above it between two consecutive bars.

### `crosses_below`

```
previous_left >= previous_right  AND  current_left < current_right
```

Triggers when the left operand transitions from at-or-above the right operand to
strictly below it between two consecutive bars.

---

## Architecture

### New modules (Phase 2P.3)

| Module | Purpose |
|--------|---------|
| `backend/strategy_registry/two_bar_context.py` | `TwoBarEvaluationContext`, `PreviousBarMissingError` |
| `backend/strategy_registry/crossover_evaluator.py` | `CrossoverConditionEvaluator`, `TwoBarScalarEngine` |

### Modified modules (Phase 2P.3)

| Module | Change |
|--------|--------|
| `backend/strategy_registry/historical_evaluator.py` | Uses `TwoBarScalarEngine` and `TwoBarEvaluationContext`; propagates previous bar values between iterations |

---

## TwoBarEvaluationContext

`TwoBarEvaluationContext` subclasses `ScalarEvaluationContext`. It carries:

- **`current_values`** — flat scalar dict for the current bar (accessible via inherited `resolve_price_field`, `resolve_tool_output`, `resolve_constant`)
- **`previous_values`** — flat scalar dict for the previous bar (accessible via `resolve_previous_price_field`, `resolve_previous_tool_output`, `resolve_previous_constant`)
- **`has_previous_bar`** — `True` if `previous_values` was supplied; `False` on the first bar

Key layout (same for both current and previous dicts):

```
"price.{field}"               →  e.g. "price.close": 100.0
"tool.{instance_id}.{output}" →  e.g. "tool.sma.value": 98.0
```

---

## First-Bar Behavior

When previous bar values do not exist (`has_previous_bar=False`), crossover
operators return `outcome=None` with an `EvaluationDiagnostic`:

```
severity: "info"
code:     "no_previous_bar"
```

This is deterministic and never silently coerced to `False`. The first bar is
always indeterminate for crossover conditions.

---

## CrossoverConditionEvaluator

`CrossoverConditionEvaluator` wraps `ScalarConditionEvaluator`:

- **Scalar operators** (`>`, `<`, `>=`, `<=`, `==`, `!=`) are delegated entirely to the wrapped `ScalarConditionEvaluator`.
- **Crossover operators** (`crosses_above`, `crosses_below`) are handled directly, requiring `TwoBarEvaluationContext`.

---

## TwoBarScalarEngine

`TwoBarScalarEngine` is a concrete `EvaluationEngineContract` that supports all
scalar and crossover operators. It composes `CrossoverConditionEvaluator` into
the standard `ScalarGroupEvaluator → ScalarRuleEvaluator` stack from Phase 2P.1.

**Supported operators:**
```
>   <   >=   <=   ==   !=   crosses_above   crosses_below
```

---

## Historical Evaluation (evaluate_history)

`evaluate_history` in `historical_evaluator.py` propagates previous bar values
between iterations:

```python
previous_values: dict[str, float] | None = None

for bar in input.bars:
    current_values = _build_scalar_values(bar)
    context = TwoBarEvaluationContext(
        evaluation_id=f"{plan_draft_id or 'plan'}:bar:{bar.bar_index}",
        current_values=current_values,
        previous_values=previous_values,
        plan_draft_id=plan_draft_id,
    )
    trace = _TWO_BAR_ENGINE.evaluate_plan(input.plan, context)
    # ... collect results
    previous_values = current_values  # propagate for next bar
```

The first bar always has `previous_values=None`. The second bar receives the
first bar's values as `previous_values`, and so on.

---

## Example

```python
from backend.strategy_registry.semantic_compiler import SemanticCompiler
from backend.strategy_registry.historical_evaluator import (
    HistoricalBarContext,
    HistoricalEvaluationInput,
    evaluate_history,
)

# Semantics: close crosses_above 50
semantics = {
    "entry_rules": [{
        "rule_id": "r1", "label": "Close crosses 50",
        "condition_group": {
            "group_id": "g1", "operator": "AND",
            "conditions": [{
                "condition_id": "c1", "label": None,
                "left":  {"kind": "price",    "ref": "close"},
                "operator": "crosses_above",
                "right": {"kind": "constant", "ref": "50"},
            }],
        },
    }],
    "exit_rules": [],
}

plan = SemanticCompiler().compile(semantics_obj).evaluation_plan

bars = [
    HistoricalBarContext(bar_index=0, price_fields={"close": 40.0}),  # first bar → None
    HistoricalBarContext(bar_index=1, price_fields={"close": 60.0}),  # crosses above → True
    HistoricalBarContext(bar_index=2, price_fields={"close": 70.0}),  # still above → False
    HistoricalBarContext(bar_index=3, price_fields={"close": 45.0}),  # drops below → False
    HistoricalBarContext(bar_index=4, price_fields={"close": 55.0}),  # crosses above → True
]

result = evaluate_history(HistoricalEvaluationInput(plan=plan, bars=bars))
# result.entry_triggered_count == 2  (bars 1 and 4)
# result.bar_results[0].entry_triggered is None
# result.bar_results[1].entry_triggered is True
```

---

## Architecture Boundary

All Phase 2P.3 modules must NOT import from:

- `backend.strategy_runtime`
- `backend.backtesting`
- `backend.execution`
- `backend.forward_testing`
