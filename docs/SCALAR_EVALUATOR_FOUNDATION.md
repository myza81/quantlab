# SCALAR_EVALUATOR_FOUNDATION.md

## Purpose

Documents the design, responsibilities, constraints, and intentional limitations of the Phase 2P.1 scalar evaluator — the first concrete `EvaluationEngineContract` implementation in QuantLab.

---

## What the Scalar Evaluator Does

The scalar evaluator is the first concrete implementation of the evaluator contract architecture established in Phase 2O.6.

It evaluates a pre-compiled `EvaluationPlan` against a pre-populated `ScalarEvaluationContext` and produces a passive `EvaluationTrace` capturing the full evaluation path.

### Evaluation path

```
StrategySemantics
    ↓ semantic_compiler.compile_semantics()
EvaluationPlan (IR)
    ↓ ScalarEvaluationEngine.evaluate_plan()
EvaluationTrace
```

The evaluation is **single-snapshot**: one context, one pass, no iteration.

---

## Components

### `ScalarEvaluationContext`

Concrete `EvaluationContext` backed by a flat `dict[str, float]`.

Key conventions:

| Context key format               | Example                       | Maps to                         |
|----------------------------------|-------------------------------|----------------------------------|
| `price.{field}`                  | `price.close: 100.0`          | `resolve_price_field("close")`  |
| `tool.{instance_id}.{output}`    | `tool.sma_fast.value: 98.0`   | `resolve_tool_output("sma_fast", "value")` |

Constants are resolved directly from their string representation: `"30"` → `30.0`.

The context performs **zero computation**. All values must be injected by the caller.

---

### `ScalarOperandResolver`

Implements `OperandResolver`. Dispatches `(kind, ref)` pairs to `EvaluationContext` resolution:

| Operand kind  | Ref format                  | Resolution                    |
|---------------|-----------------------------|-------------------------------|
| `constant`    | `"30"`, `"0.75"`            | `float(ref)`                  |
| `price`       | `"close"`, `"open"`         | `context.resolve_price_field` |
| `tool_output` | `"sma_fast.value"`          | `context.resolve_tool_output` |

---

### `ScalarOperatorEvaluator`

Implements `OperatorEvaluator`. Supports six scalar operators:

```
>   <   >=   <=   ==   !=
```

All operands are cast to `float` before comparison. This provides int/float compatibility without special-casing.

---

### `ScalarConditionEvaluator`

Implements `ConditionEvaluator`. Orchestrates resolver → operator evaluator → `ConditionEvaluationResult`.

Resolution or operator failures produce an `EvaluationDiagnostic` with `outcome=None` rather than raising to the caller. This preserves the full evaluation trace even when individual conditions fail.

---

### `ScalarGroupEvaluator`

Implements `GroupEvaluator`. Recursively evaluates nested condition groups.

All children are always evaluated (no short-circuit) to produce complete traces.

Logical semantics (correct for indeterminate outcomes):

| Operator | Condition | Outcome |
|----------|-----------|---------|
| AND | any False | False |
| AND | no False, any None | None |
| AND | all True | True |
| OR | any True | True |
| OR | no True, any None | None |
| OR | all False | False |

---

### `ScalarRuleEvaluator`

Implements `RuleEvaluator`. Delegates to `ScalarGroupEvaluator`. Returns `RuleEvaluationResult` with `triggered` flag. Does not generate signals — triggered flag is for the calling layer to interpret.

---

### `ScalarEvaluationEngine`

Implements `EvaluationEngineContract`. Top-level concrete engine.

Evaluates all `rule_nodes` in plan order, aggregates rule results, and returns a complete `EvaluationTrace`. Entry/exit trigger aggregation uses OR semantics: any triggered rule makes the aggregate triggered.

---

## Supported Operators

```
>    <    >=    <=    ==    !=
```

---

## Intentionally Unsupported Features

### `crosses_above` / `crosses_below`

These operators require access to the **previous bar's** resolved values to determine whether a crossover event occurred. The scalar evaluator is a **single-snapshot** evaluator — it has no previous-bar state.

Both operators raise `UnsupportedOperatorError` if requested. They are deferred to a future multi-bar evaluator that maintains previous-bar context.

### Multi-bar evaluation / bar iteration

The scalar evaluator evaluates **one context snapshot**. Iterating bars (e.g., for backtesting) is the responsibility of the calling runtime layer, not the evaluator. The evaluator exposes no loop, no history, and no previous-bar state.

### Tool computation

Tool outputs (e.g., SMA values, RSI values) must be **pre-computed and injected** into the `ScalarEvaluationContext` by the caller. The evaluator only reads values — it never computes them.

### Backtesting

No backtesting infrastructure exists in this evaluator. Backtesting involves bar iteration, position state, fill simulation, and portfolio accounting — none of which belong to the evaluation layer.

### Signal generation

The evaluator returns `triggered=True/False/None` in rule results. Interpreting triggers as trading signals is the responsibility of the calling layer (future strategy runtime or backtesting engine).

### Portfolio logic / trade simulation

No concept of positions, capital, fills, or PnL exists anywhere in the evaluator.

---

## Architecture Boundary

The scalar evaluator modules **MUST NOT import from**:

```
backend.strategy_runtime
backend.backtesting
backend.execution
backend.forward_testing
```

The evaluator is a pure, standalone IR interpreter. It has no awareness of execution modes, runtime environments, or broker infrastructure.

---

## Generic IR-Driven Design

The evaluator contains **no hardcoded indicator logic**. There is no:

```python
if operator == "sma_cross":   # FORBIDDEN
if instance_id == "rsi":      # FORBIDDEN
```

All evaluation is driven by the `EvaluationPlan` IR structure:
- `ConditionPlanNode.left_kind` / `left_ref` / `operator` / `right_kind` / `right_ref`
- `ConditionGroupPlanNode.operator` ("AND" / "OR") + recursive nodes
- `RulePlanNode.kind` ("entry" / "exit") + condition_group

New indicator tool types, new operand kinds, and new rule structures can be supported by updating the IR — the evaluator logic remains unchanged.

---

## Optional API Endpoint

`POST /semantics/evaluate-scalar`

Accepts a `StrategySemantics` + `scalar_context` dict. Compiles the semantics internally, evaluates against the context, and returns the `EvaluationTrace`.

This endpoint is optional and intended for development-time inspection and testing. It is not the primary path for backtesting — that will iterate bars externally and call the engine per-bar.

---

## Future Extension Path

| Capability | Required for | How to extend |
|------------|-------------|---------------|
| `crosses_above` / `crosses_below` | Crossover strategies | Multi-bar context carrying previous-bar resolved values |
| Bar iteration | Backtesting | Calling layer loops bars, creates one context per bar, calls `evaluate_plan()` |
| Tool computation | Online evaluation | Context implementation calls tool compute functions before evaluation |
| Strategy signal generation | Runtime | Calling layer reads `EvaluationTrace.entry_triggered` / `exit_triggered` |
| Portfolio simulation | Backtesting | Separate engine layer on top of evaluation results |

The evaluator's contract-based design (all components are swappable `ABC` implementations) allows any of these extensions to be introduced without modifying the scalar evaluator itself.
