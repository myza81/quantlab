# EVALUATION CONTRACT ARCHITECTURE

## Purpose

This document defines the architecture of the Evaluation Contract layer in QuantLab.

The Evaluation Contract layer sits between the **Semantic Compilation IR** (EvaluationPlan) and future **Concrete Evaluators** (backtesting engine, forward-testing runtime).

Its purpose is to establish **what evaluators must implement** before any evaluator is built — preventing architectural drift, hardcoded indicator logic, and runtime coupling.

---

## Architecture Position

```
StrategySemantics          (authored by user; strategy_registry/semantics.py)
        ↓ semantic_compiler.py
EvaluationPlan IR          (frozen, passive; strategy_registry/semantic_plan.py)
        ↓
Evaluator Contracts        (abstract interfaces; Phase 2O.6)    ← THIS LAYER
        ↓
Concrete Evaluators        (future: backtesting, forward_testing, paper_trading)
        ↓
Signal Generation          (runtime layer — reads triggered flags, never in evaluator)
```

The Evaluation Contract layer is **not** an execution layer. It defines interfaces only.

---

## Responsibilities

### Compiler Responsibility

The semantic compiler (`semantic_compiler.py`) is responsible for:

- Walking the `StrategySemantics` tree
- Producing a deterministic, serializable `EvaluationPlan` IR
- Extracting static dependencies (`DependencySet`)
- Assigning node counts and compilation diagnostics

The compiler does **NOT**:
- Evaluate conditions
- Access market data
- Compute indicators
- Know which runtime will consume the plan

### Evaluator Responsibility (contract — future implementation)

A concrete evaluator is responsible for:

- Receiving a pre-compiled `EvaluationPlan`
- Receiving a pre-populated `EvaluationContext` (from the runtime layer)
- Resolving operand references to values via the context
- Applying operators generically
- Returning a passive `EvaluationTrace`

A concrete evaluator does **NOT**:
- Re-compile semantics
- Load market data
- Compute indicators (delegates via EvaluationContext)
- Generate signals (returns trace; runtime layer decides signal behavior)
- Know about specific tools (SMA, RSI, etc.)

### Runtime Layer Responsibility

The runtime layer (backtesting engine, forward-testing runner) is responsible for:

- Populating `EvaluationContext` with tool outputs and price data for each bar
- Calling the evaluator per bar/tick
- Reading `EvaluationTrace.entry_triggered` / `exit_triggered`
- Converting trigger flags into signals, orders, or research artifacts

---

## Contract Files

### `backend/strategy_registry/evaluator_contracts.py`

Defines all abstract evaluator interfaces and passive result contracts.

| Type | Category | Purpose |
|---|---|---|
| `EvaluationDiagnostic` | Frozen Pydantic | Runtime resolution diagnostic |
| `ConditionEvaluationResult` | Frozen Pydantic | Result of one condition evaluation |
| `GroupEvaluationResult` | Frozen Pydantic | Result of one group evaluation (recursive) |
| `RuleEvaluationResult` | Frozen Pydantic | Result of one rule evaluation |
| `EvaluationTrace` | Frozen Pydantic | Full audit trace for one evaluation pass |
| `ResolvedValue` | Type alias | Generic resolved operand value (`Any`) |
| `EvaluationContext` | ABC | Context interface — data access contract |
| `OperandResolver` | ABC | Resolves (kind, ref) → value via context |
| `OperatorEvaluator` | ABC | Evaluates comparison between resolved values |
| `ConditionEvaluator` | ABC | Evaluates one ConditionPlanNode |
| `GroupEvaluator` | ABC | Evaluates one ConditionGroupPlanNode (recursive) |
| `RuleEvaluator` | ABC | Evaluates one RulePlanNode |
| `EvaluationEngineContract` | ABC | Top-level engine: plan + context → trace |

### `backend/strategy_registry/evaluation_context.py`

Passive descriptor models for context requirements and pre-flight checking.

| Type | Purpose |
|---|---|
| `EvaluationContextDescriptor` | Declares what a context provides |
| `EvaluationRequirements` | Declares what a plan requires |
| `ContextSatisfactionReport` | Whether context satisfies requirements |
| `extract_requirements()` | Pure fn: DependencySet → EvaluationRequirements |
| `check_context_satisfaction()` | Pure fn: requirements × descriptor → report |

### `backend/strategy_registry/plan_visitor.py`

Generic visitor/traversal architecture for EvaluationPlan IR.

| Type | Purpose |
|---|---|
| `TraversalContext` | Frozen Pydantic — current traversal position |
| `PlanNodeVisitor` | ABC — visitor interface for plan nodes |
| `traverse_plan()` | Concrete traversal — post-order depth-first, no evaluation |

---

## Generic Operator Philosophy

**Operator contracts must remain generic.**

The `OperatorEvaluator` interface defines:

```
evaluate(left: ResolvedValue, operator: str, right: ResolvedValue) → bool | None
```

This contract is intentionally type-agnostic. It does **NOT**:

- Assume operands are floats
- Assume operands are time series
- Contain SMA-specific comparison logic
- Contain RSI threshold logic
- Contain crossover detection logic tied to any specific indicator

Whether `crosses_above` / `crosses_below` requires previous-bar state is an
implementation detail of the concrete `OperatorEvaluator`. The contract only
declares that the operator string must be handled.

This ensures:

- The same operator interface works for scalar values, series, and future data types
- No indicator-specific branches bleed into the evaluator contract layer
- Evaluator implementations remain fully substitutable

---

## EvaluationContext Lifecycle

```
Runtime Layer
    ↓ builds and populates
EvaluationContext (concrete implementation)
    ↓ passed to
EvaluationEngineContract.evaluate_plan(plan, context)
    ↓ returns
EvaluationTrace
    ↓ consumed by
Runtime Layer (signal generation, logging, backtesting loop)
```

The `EvaluationContext` ABC declares **what** an evaluator can access.
The runtime layer is responsible for **how** that data is provided.

---

## Visitor Pattern Usage

The `PlanNodeVisitor` and `traverse_plan()` function enable future evaluators
to implement evaluation as a tree-walking visitor:

```python
class MyEvaluator(PlanNodeVisitor):
    def visit_condition_node(self, node, ctx): ...
    def visit_group_node(self, node, child_results, ctx): ...
    def visit_rule_node(self, node, group_result, ctx): ...

results = traverse_plan(plan, MyEvaluator())
```

This separates traversal mechanics from evaluation logic, allowing:

- Different evaluators for different runtime modes
- Diagnostic/inspection visitors that don't evaluate at all
- Test visitors for contract verification

---

## Architecture Guardrails

### Forbidden in Evaluator Contract Layer

The following must NOT appear in evaluator contract modules:

| Forbidden | Reason |
|---|---|
| Imports from `backend.strategy_runtime` | Runtime coupling |
| Imports from `backend.backtesting` | Backtesting layer coupling |
| Imports from `backend.execution` | Execution layer coupling |
| Imports from `backend.forward_testing` | Forward-testing coupling |
| `compute_sma()` or any indicator call | Indicator-specific logic |
| SMA, RSI, MACD, ATR as named concepts | Indicator-specific branching |
| Signal generation logic | Runtime responsibility |
| Market data loading | Context responsibility |
| Order submission | Execution responsibility |

### Required in Evaluator Contract Layer

| Required | Reason |
|---|---|
| Abstract interfaces only | Contract, not implementation |
| Generic type signatures | Tool-agnostic evaluator reuse |
| Frozen Pydantic result models | Deterministic, serializable, auditable |
| No mutation of plan or context | Evaluators are pure functions |
| Architecture boundary docstrings | Enforce at read time |

---

## Future Evaluator Layering

When concrete evaluators are implemented in future phases, they must:

1. Import `EvaluationEngineContract` from `evaluator_contracts.py`
2. Implement all abstract methods
3. Receive `EvaluationPlan` and `EvaluationContext` as parameters
4. Return `EvaluationTrace`
5. Never import semantic domain models (only plan IR models)

Example future modules:

```
backend/backtesting/bar_evaluator.py         ← implements EvaluationEngineContract
backend/forward_testing/tick_evaluator.py    ← implements EvaluationEngineContract
```

Both implementations share the same contract but differ in:
- Context population mechanism (historical bars vs live ticks)
- Crossover operator state management (previous bar vs streaming window)
- Performance characteristics

---

## Relationship to Other Contracts

| Contract | Relationship |
|---|---|
| `DATA_CONTRACT.md` | Provides market data to EvaluationContext implementations |
| `STRATEGY_CONTRACT.md` | Strategy logic expressed as StrategySemantics |
| `STRATEGY_DEFINITION_ARCHITECTURE.md` | Semantic + compilation IR definition |
| `TOOL_REGISTRY_CONTRACT.md` | Tool outputs resolved by EvaluationContext via registry |
| `BACKTESTING_ENGINE_CONTRACT.md` | Future concrete evaluator using this contract |
| `EXECUTION_CONTRACT.md` | Downstream of signal generation; not involved in evaluation |
