"""
Concrete Scalar Evaluator — Phase 2P.1.

First concrete EvaluationEngineContract implementation.
Evaluates single-bar scalar conditions against a pre-populated context.

Supported operators (scalar, single-bar only):
    >   <   >=   <=   ==   !=

Explicitly deferred (require previous-bar state):
    crosses_above   crosses_below

Single-snapshot evaluation only. No bar iteration. No historical state.
Tool outputs MUST be pre-injected into context — no computation here.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.backtesting
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

from typing import Union

from backend.strategy_registry.evaluator_contracts import (
    ConditionEvaluationResult,
    ConditionEvaluator,
    EvaluationContext,
    EvaluationDiagnostic,
    EvaluationEngineContract,
    EvaluationTrace,
    GroupEvaluationResult,
    GroupEvaluator,
    OperandResolver,
    OperatorEvaluator,
    ResolvedValue,
    RuleEvaluationResult,
    RuleEvaluator,
)
from backend.strategy_registry.scalar_evaluation_context import ScalarContextError
from backend.strategy_registry.semantic_plan import (
    ConditionGroupPlanNode,
    ConditionPlanNode,
    EvaluationPlan,
    RulePlanNode,
)


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------

class UnsupportedOperatorError(Exception):
    """Raised when the requested operator is not supported by this evaluator."""


# ---------------------------------------------------------------------------
# Supported / deferred operator sets
# ---------------------------------------------------------------------------

SCALAR_OPERATORS: frozenset[str] = frozenset({"<", ">", "<=", ">=", "==", "!="})

# Deferred: require previous-bar state unavailable in single-snapshot context.
_DEFERRED_OPERATORS: frozenset[str] = frozenset({"crosses_above", "crosses_below"})

# Operand kind string constants (matches OperandKind enum values in semantics.py)
_KIND_CONSTANT    = "constant"
_KIND_PRICE       = "price"
_KIND_TOOL_OUTPUT = "tool_output"


# ---------------------------------------------------------------------------
# ScalarOperandResolver
# ---------------------------------------------------------------------------

class ScalarOperandResolver(OperandResolver):
    """
    Concrete operand resolver for scalar evaluation.

    Dispatches (kind, ref) pairs to EvaluationContext resolution methods.
    For tool_output kind, splits ref as "instance_id.output_name".
    """

    def resolve(
        self,
        kind:    str,
        ref:     str,
        context: EvaluationContext,
    ) -> ResolvedValue:
        if kind == _KIND_CONSTANT:
            return context.resolve_constant(ref)

        if kind == _KIND_PRICE:
            return context.resolve_price_field(ref)

        if kind == _KIND_TOOL_OUTPUT:
            parts = ref.split(".", 1)
            if len(parts) != 2:
                raise ScalarContextError(
                    f"tool_output ref '{ref}' must be 'instance_id.output_name' "
                    f"(e.g. 'sma_fast.value')"
                )
            return context.resolve_tool_output(parts[0], parts[1])

        raise ScalarContextError(
            f"Unknown operand kind '{kind}'. "
            f"Expected one of: {_KIND_CONSTANT!r}, {_KIND_PRICE!r}, {_KIND_TOOL_OUTPUT!r}"
        )


# ---------------------------------------------------------------------------
# ScalarOperatorEvaluator
# ---------------------------------------------------------------------------

class ScalarOperatorEvaluator(OperatorEvaluator):
    """
    Concrete operator evaluator for scalar (single-bar) comparisons.

    Supports: >  <  >=  <=  ==  !=
    Rejects crosses_above / crosses_below (deferred — require previous-bar state).
    """

    @property
    def supported_operators(self) -> frozenset[str]:
        return SCALAR_OPERATORS

    def evaluate(
        self,
        left:     ResolvedValue,
        operator: str,
        right:    ResolvedValue,
    ) -> bool | None:
        if operator in _DEFERRED_OPERATORS:
            raise UnsupportedOperatorError(
                f"Operator '{operator}' requires previous-bar state and is deferred. "
                f"ScalarOperatorEvaluator supports single-snapshot operators only: "
                f"{sorted(SCALAR_OPERATORS)}"
            )
        if operator not in SCALAR_OPERATORS:
            raise UnsupportedOperatorError(
                f"Unknown operator '{operator}'. "
                f"Supported: {sorted(SCALAR_OPERATORS)}"
            )
        lv, rv = float(left), float(right)
        if operator == ">":  return lv > rv
        if operator == "<":  return lv < rv
        if operator == ">=": return lv >= rv
        if operator == "<=": return lv <= rv
        if operator == "==": return lv == rv
        if operator == "!=": return lv != rv
        return None  # unreachable — operator already validated above


# ---------------------------------------------------------------------------
# ScalarConditionEvaluator
# ---------------------------------------------------------------------------

class ScalarConditionEvaluator(ConditionEvaluator):
    """
    Concrete condition evaluator.

    Orchestrates OperandResolver → OperatorEvaluator for one ConditionPlanNode.
    Resolution or operator failures produce EvaluationDiagnostics; outcome=None.
    """

    def __init__(
        self,
        resolver:           OperandResolver,
        operator_evaluator: OperatorEvaluator,
    ) -> None:
        self._resolver = resolver
        self._op_eval  = operator_evaluator

    def evaluate_condition(
        self,
        node:    ConditionPlanNode,
        context: EvaluationContext,
    ) -> ConditionEvaluationResult:
        diagnostics: list[EvaluationDiagnostic] = []

        # Resolve left operand
        try:
            left = self._resolver.resolve(node.left_kind, node.left_ref, context)
        except Exception as exc:
            diagnostics.append(EvaluationDiagnostic(
                severity="error",
                code="unresolved_operand",
                reference=f"{node.left_kind}:{node.left_ref}",
                message=str(exc),
                condition_id=node.condition_id,
            ))
            return ConditionEvaluationResult(
                condition_id=node.condition_id,
                outcome=None,
                diagnostics=tuple(diagnostics),
            )

        # Resolve right operand
        try:
            right = self._resolver.resolve(node.right_kind, node.right_ref, context)
        except Exception as exc:
            diagnostics.append(EvaluationDiagnostic(
                severity="error",
                code="unresolved_operand",
                reference=f"{node.right_kind}:{node.right_ref}",
                message=str(exc),
                condition_id=node.condition_id,
            ))
            return ConditionEvaluationResult(
                condition_id=node.condition_id,
                outcome=None,
                diagnostics=tuple(diagnostics),
            )

        # Apply operator
        try:
            outcome = self._op_eval.evaluate(left, node.operator, right)
        except UnsupportedOperatorError as exc:
            diagnostics.append(EvaluationDiagnostic(
                severity="error",
                code="unsupported_operator",
                reference=node.operator,
                message=str(exc),
                condition_id=node.condition_id,
            ))
            return ConditionEvaluationResult(
                condition_id=node.condition_id,
                outcome=None,
                diagnostics=tuple(diagnostics),
            )
        except Exception as exc:
            diagnostics.append(EvaluationDiagnostic(
                severity="error",
                code="operator_type_mismatch",
                reference=node.operator,
                message=str(exc),
                condition_id=node.condition_id,
            ))
            return ConditionEvaluationResult(
                condition_id=node.condition_id,
                outcome=None,
                diagnostics=tuple(diagnostics),
            )

        return ConditionEvaluationResult(
            condition_id=node.condition_id,
            outcome=outcome,
            diagnostics=(),
        )


# ---------------------------------------------------------------------------
# ScalarGroupEvaluator
# ---------------------------------------------------------------------------

class ScalarGroupEvaluator(GroupEvaluator):
    """
    Concrete group evaluator for AND/OR logic.

    Recursively evaluates nested conditions and groups in plan order.
    All children are always evaluated (no short-circuit) for complete traces.

    Outcome semantics:
        AND: False if any child False; None if any remaining are None; else True.
        OR:  True if any child True; None if any remaining are None; else False.
    """

    def __init__(self, condition_evaluator: ConditionEvaluator) -> None:
        self._cond_eval = condition_evaluator

    def evaluate_group(
        self,
        node:    ConditionGroupPlanNode,
        context: EvaluationContext,
    ) -> GroupEvaluationResult:
        child_results: list[Union[ConditionEvaluationResult, GroupEvaluationResult]] = []

        for child in node.nodes:
            if isinstance(child, ConditionPlanNode):
                child_results.append(self._cond_eval.evaluate_condition(child, context))
            else:
                child_results.append(self.evaluate_group(child, context))

        outcomes = [r.outcome for r in child_results]
        group_outcome = _apply_logical_operator(node.operator, outcomes)

        return GroupEvaluationResult(
            group_id=node.group_id,
            outcome=group_outcome,
            child_results=tuple(child_results),
            diagnostics=(),
        )


def _apply_logical_operator(operator: str, outcomes: list[bool | None]) -> bool | None:
    """
    Apply AND/OR logical reduction over a list of boolean-or-None outcomes.

    AND: any False → False; any None remaining → None; else True.
    OR:  any True  → True;  any None remaining → None; else False.
    """
    if operator == "AND":
        if any(o is False for o in outcomes):
            return False
        if any(o is None for o in outcomes):
            return None
        return True

    if operator == "OR":
        if any(o is True for o in outcomes):
            return True
        if any(o is None for o in outcomes):
            return None
        return False

    return None  # unknown operator — indeterminate


# ---------------------------------------------------------------------------
# ScalarRuleEvaluator
# ---------------------------------------------------------------------------

class ScalarRuleEvaluator(RuleEvaluator):
    """
    Concrete rule evaluator.

    Delegates condition group evaluation to GroupEvaluator.
    Returns RuleEvaluationResult with triggered flag and full group trace.
    No signal generation; triggered flag is returned for the caller to act on.
    """

    def __init__(self, group_evaluator: GroupEvaluator) -> None:
        self._group_eval = group_evaluator

    def evaluate_rule(
        self,
        node:    RulePlanNode,
        context: EvaluationContext,
    ) -> RuleEvaluationResult:
        group_result = self._group_eval.evaluate_group(node.condition_group, context)
        return RuleEvaluationResult(
            rule_id=node.rule_id,
            kind=node.kind,
            index=node.index,
            triggered=group_result.outcome,
            group_result=group_result,
            diagnostics=(),
        )


# ---------------------------------------------------------------------------
# ScalarEvaluationEngine — top-level concrete engine
# ---------------------------------------------------------------------------

class ScalarEvaluationEngine(EvaluationEngineContract):
    """
    Concrete EvaluationEngineContract for single-bar scalar evaluation.

    Evaluates a pre-compiled EvaluationPlan against a pre-populated context
    and returns a passive EvaluationTrace.

    Constraints:
        - Single-snapshot evaluation; no multi-bar or historical state
        - Tool outputs must be pre-injected into context; no tool computation
        - No signal generation; triggered flags are for the caller to interpret
        - No runtime coupling; standalone and pure
        - Scalar operators only: >  <  >=  <=  ==  !=
    """

    def __init__(self) -> None:
        resolver   = ScalarOperandResolver()
        op_eval    = ScalarOperatorEvaluator()
        cond_eval  = ScalarConditionEvaluator(resolver, op_eval)
        grp_eval   = ScalarGroupEvaluator(cond_eval)
        self._rule_eval = ScalarRuleEvaluator(grp_eval)

    @property
    def supported_operators(self) -> frozenset[str]:
        return SCALAR_OPERATORS

    def evaluate_plan(
        self,
        plan:    EvaluationPlan,
        context: EvaluationContext,
    ) -> EvaluationTrace:
        rule_results:    list[RuleEvaluationResult]  = []
        all_diagnostics: list[EvaluationDiagnostic]  = []

        for rule_node in plan.rule_nodes:
            result = self._rule_eval.evaluate_rule(rule_node, context)
            rule_results.append(result)
            all_diagnostics.extend(result.diagnostics)

        entry_triggered = _aggregate_trigger(
            [r.triggered for r in rule_results if r.kind == "entry"]
        )
        exit_triggered = _aggregate_trigger(
            [r.triggered for r in rule_results if r.kind == "exit"]
        )

        return EvaluationTrace(
            plan_draft_id=plan.draft_id,
            evaluation_id=context.evaluation_id,
            rule_results=tuple(rule_results),
            diagnostics=tuple(all_diagnostics),
            entry_triggered=entry_triggered,
            exit_triggered=exit_triggered,
        )


def _aggregate_trigger(outcomes: list[bool | None]) -> bool | None:
    """Return True if any triggered; None if no outcomes; else False."""
    if not outcomes:
        return None
    if any(o is True for o in outcomes):
        return True
    if all(o is None for o in outcomes):
        return None
    return False
