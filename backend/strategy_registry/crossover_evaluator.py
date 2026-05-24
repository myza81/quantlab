"""
Crossover Evaluator — Phase 2P.3.

Extends the scalar evaluator stack to support temporal crossover operators:
    crosses_above — previous_left <= previous_right AND current_left > current_right
    crosses_below — previous_left >= previous_right AND current_left < current_right

Design:
    CrossoverConditionEvaluator wraps ScalarConditionEvaluator:
        - Scalar operators (>, <, >=, <=, ==, !=) are delegated to ScalarConditionEvaluator.
        - Crossover operators are handled here, requiring TwoBarEvaluationContext.

    TwoBarScalarEngine composes CrossoverConditionEvaluator into the standard
    ScalarGroupEvaluator → ScalarRuleEvaluator → TwoBarScalarEngine stack.
    It uses the same ScalarGroupEvaluator and ScalarRuleEvaluator from Phase 2P.1.

First-bar behavior:
    When context.has_previous_bar is False, crossover operators return outcome=None
    with a "no_previous_bar" diagnostic. This is deterministic and never coerced to False.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.backtesting
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

from backend.strategy_registry.evaluator_contracts import (
    ConditionEvaluationResult,
    ConditionEvaluator,
    EvaluationContext,
    EvaluationDiagnostic,
    EvaluationEngineContract,
    EvaluationTrace,
    GroupEvaluator,
    RuleEvaluator,
)
from backend.strategy_registry.scalar_evaluation_context import ScalarContextError
from backend.strategy_registry.scalar_evaluator import (
    SCALAR_OPERATORS,
    ScalarConditionEvaluator,
    ScalarGroupEvaluator,
    ScalarOperandResolver,
    ScalarOperatorEvaluator,
    ScalarRuleEvaluator,
    _aggregate_trigger,
)
from backend.strategy_registry.semantic_plan import (
    ConditionGroupPlanNode,
    ConditionPlanNode,
    EvaluationPlan,
    RulePlanNode,
)
from backend.strategy_registry.two_bar_context import (
    PreviousBarMissingError,
    TwoBarEvaluationContext,
)


# ---------------------------------------------------------------------------
# Supported crossover operator set
# ---------------------------------------------------------------------------

CROSSOVER_OPERATORS: frozenset[str] = frozenset({"crosses_above", "crosses_below"})

ALL_TWO_BAR_OPERATORS: frozenset[str] = SCALAR_OPERATORS | CROSSOVER_OPERATORS


# ---------------------------------------------------------------------------
# Crossover resolution helpers
# ---------------------------------------------------------------------------

def _resolve_previous(
    kind:    str,
    ref:     str,
    context: TwoBarEvaluationContext,
    condition_id: str | None,
) -> tuple[float | None, EvaluationDiagnostic | None]:
    """Resolve an operand against the previous bar. Returns (value, diagnostic)."""
    try:
        if kind == "constant":
            return context.resolve_previous_constant(ref), None
        if kind == "price":
            return context.resolve_previous_price_field(ref), None
        if kind == "tool_output":
            parts = ref.split(".", 1)
            if len(parts) != 2:
                raise ScalarContextError(
                    f"tool_output ref '{ref}' must be 'instance_id.output_name'"
                )
            return context.resolve_previous_tool_output(parts[0], parts[1]), None
        raise ScalarContextError(f"Unknown operand kind '{kind}'")
    except (PreviousBarMissingError, ScalarContextError, Exception) as exc:
        diag = EvaluationDiagnostic(
            severity="error",
            code="unresolved_operand",
            reference=f"previous:{kind}:{ref}",
            message=str(exc),
            condition_id=condition_id,
        )
        return None, diag


def _resolve_current(
    kind:    str,
    ref:     str,
    context: EvaluationContext,
    condition_id: str | None,
) -> tuple[float | None, EvaluationDiagnostic | None]:
    """Resolve an operand against the current bar. Returns (value, diagnostic)."""
    resolver = ScalarOperandResolver()
    try:
        value = resolver.resolve(kind, ref, context)
        return value, None
    except Exception as exc:
        diag = EvaluationDiagnostic(
            severity="error",
            code="unresolved_operand",
            reference=f"current:{kind}:{ref}",
            message=str(exc),
            condition_id=condition_id,
        )
        return None, diag


# ---------------------------------------------------------------------------
# CrossoverConditionEvaluator
# ---------------------------------------------------------------------------

class CrossoverConditionEvaluator(ConditionEvaluator):
    """
    Concrete condition evaluator supporting both scalar and crossover operators.

    Scalar operators are delegated to a wrapped ScalarConditionEvaluator.
    Crossover operators require TwoBarEvaluationContext.

    Crossover semantics:
        crosses_above:
            previous_left <= previous_right  AND  current_left > current_right
        crosses_below:
            previous_left >= previous_right  AND  current_left < current_right

    First-bar behavior:
        When context.has_previous_bar is False, outcome=None with "no_previous_bar"
        diagnostic. Never silently coerced to False.
    """

    def __init__(
        self,
        scalar_condition_evaluator: ScalarConditionEvaluator,
    ) -> None:
        self._scalar_eval = scalar_condition_evaluator

    def evaluate_condition(
        self,
        node:    ConditionPlanNode,
        context: EvaluationContext,
    ) -> ConditionEvaluationResult:
        # Scalar operators — delegate entirely
        if node.operator in SCALAR_OPERATORS:
            return self._scalar_eval.evaluate_condition(node, context)

        # Crossover operators
        if node.operator in CROSSOVER_OPERATORS:
            return self._evaluate_crossover(node, context)

        # Unknown operator
        return ConditionEvaluationResult(
            condition_id=node.condition_id,
            outcome=None,
            diagnostics=(EvaluationDiagnostic(
                severity="error",
                code="unsupported_operator",
                reference=node.operator,
                message=(
                    f"Operator '{node.operator}' is not supported. "
                    f"Supported operators: {sorted(ALL_TWO_BAR_OPERATORS)}"
                ),
                condition_id=node.condition_id,
            ),),
        )

    def _evaluate_crossover(
        self,
        node:    ConditionPlanNode,
        context: EvaluationContext,
    ) -> ConditionEvaluationResult:
        cid = node.condition_id

        # Must have TwoBarEvaluationContext for crossover
        if not isinstance(context, TwoBarEvaluationContext):
            return ConditionEvaluationResult(
                condition_id=cid,
                outcome=None,
                diagnostics=(EvaluationDiagnostic(
                    severity="error",
                    code="context_unavailable",
                    reference=node.operator,
                    message=(
                        f"Operator '{node.operator}' requires TwoBarEvaluationContext. "
                        f"Got: {type(context).__name__}"
                    ),
                    condition_id=cid,
                ),),
            )

        # First bar — no previous bar available
        if not context.has_previous_bar:
            return ConditionEvaluationResult(
                condition_id=cid,
                outcome=None,
                diagnostics=(EvaluationDiagnostic(
                    severity="info",
                    code="no_previous_bar",
                    reference=node.operator,
                    message=(
                        f"Operator '{node.operator}' requires a previous bar. "
                        "This is the first bar in the sequence — outcome is indeterminate."
                    ),
                    condition_id=cid,
                ),),
            )

        # Resolve current bar operands
        curr_left, curr_left_diag = _resolve_current(
            node.left_kind, node.left_ref, context, cid
        )
        if curr_left_diag is not None:
            return ConditionEvaluationResult(
                condition_id=cid, outcome=None,
                diagnostics=(curr_left_diag,),
            )

        curr_right, curr_right_diag = _resolve_current(
            node.right_kind, node.right_ref, context, cid
        )
        if curr_right_diag is not None:
            return ConditionEvaluationResult(
                condition_id=cid, outcome=None,
                diagnostics=(curr_right_diag,),
            )

        # Resolve previous bar operands
        prev_left, prev_left_diag = _resolve_previous(
            node.left_kind, node.left_ref, context, cid
        )
        if prev_left_diag is not None:
            return ConditionEvaluationResult(
                condition_id=cid, outcome=None,
                diagnostics=(prev_left_diag,),
            )

        prev_right, prev_right_diag = _resolve_previous(
            node.right_kind, node.right_ref, context, cid
        )
        if prev_right_diag is not None:
            return ConditionEvaluationResult(
                condition_id=cid, outcome=None,
                diagnostics=(prev_right_diag,),
            )

        # Apply crossover logic
        cl, cr = float(curr_left), float(curr_right)  # type: ignore[arg-type]
        pl, pr = float(prev_left), float(prev_right)  # type: ignore[arg-type]

        if node.operator == "crosses_above":
            outcome = (pl <= pr) and (cl > cr)
        else:  # crosses_below
            outcome = (pl >= pr) and (cl < cr)

        return ConditionEvaluationResult(
            condition_id=cid,
            outcome=outcome,
            diagnostics=(),
        )


# ---------------------------------------------------------------------------
# TwoBarScalarEngine — top-level engine with crossover support
# ---------------------------------------------------------------------------

class TwoBarScalarEngine(EvaluationEngineContract):
    """
    EvaluationEngineContract supporting scalar and crossover operators.

    Composes CrossoverConditionEvaluator into the standard evaluator stack.
    Expects TwoBarEvaluationContext to be provided by the caller (historical
    evaluator builds and injects it per bar).

    Supported operators:
        Scalar:    >  <  >=  <=  ==  !=
        Crossover: crosses_above  crosses_below
    """

    def __init__(self) -> None:
        resolver         = ScalarOperandResolver()
        op_eval          = ScalarOperatorEvaluator()
        scalar_cond_eval = ScalarConditionEvaluator(resolver, op_eval)
        cross_cond_eval  = CrossoverConditionEvaluator(scalar_cond_eval)
        grp_eval         = ScalarGroupEvaluator(cross_cond_eval)
        self._rule_eval  = ScalarRuleEvaluator(grp_eval)

    @property
    def supported_operators(self) -> frozenset[str]:
        return ALL_TWO_BAR_OPERATORS

    def evaluate_plan(
        self,
        plan:    EvaluationPlan,
        context: EvaluationContext,
    ) -> EvaluationTrace:
        from backend.strategy_registry.evaluator_contracts import (
            EvaluationDiagnostic,
            RuleEvaluationResult,
        )

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
