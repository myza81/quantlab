"""
Phase 2P.3 — Crossover Evaluator unit tests.

Coverage:
    TwoBarEvaluationContext     — construction, has_previous_bar, resolve methods,
                                  missing previous bar errors, inheritance from scalar
    CrossoverConditionEvaluator — scalar delegation, crosses_above, crosses_below,
                                  first-bar behavior, missing context type, unknown op
    TwoBarScalarEngine          — full plan evaluation, supported_operators, multi-rule
    Historical crossover        — evaluate_history() with crossover conditions,
                                  first-bar None propagation, subsequent bars resolve
    Architecture boundary       — no forbidden imports in two_bar_context,
                                  crossover_evaluator, updated historical_evaluator
"""
from __future__ import annotations

import importlib
import inspect
from datetime import datetime, timezone

import pytest

from backend.strategy_registry.crossover_evaluator import (
    CROSSOVER_OPERATORS,
    ALL_TWO_BAR_OPERATORS,
    CrossoverConditionEvaluator,
    TwoBarScalarEngine,
)
from backend.strategy_registry.evaluator_contracts import (
    ConditionEvaluationResult,
    EvaluationDiagnostic,
    EvaluationTrace,
)
from backend.strategy_registry.historical_evaluator import (
    HistoricalBarContext,
    HistoricalEvaluationInput,
    evaluate_history,
)
from backend.strategy_registry.scalar_evaluation_context import ScalarEvaluationContext
from backend.strategy_registry.scalar_evaluator import (
    ScalarConditionEvaluator,
    ScalarOperandResolver,
    ScalarOperatorEvaluator,
)
from backend.strategy_registry.semantic_plan import (
    CompilationDiagnostic,
    ConditionGroupPlanNode,
    ConditionPlanNode,
    DependencySet,
    EvaluationPlan,
    RulePlanNode,
)
from backend.strategy_registry.two_bar_context import (
    PreviousBarMissingError,
    TwoBarEvaluationContext,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 5, 22, tzinfo=timezone.utc)


def _condition(
    left_kind:  str = "price",
    left_ref:   str = "close",
    operator:   str = ">",
    right_kind: str = "constant",
    right_ref:  str = "50",
    cid:        str | None = "c1",
) -> ConditionPlanNode:
    return ConditionPlanNode(
        condition_id=cid,
        left_kind=left_kind,
        left_ref=left_ref,
        operator=operator,
        right_kind=right_kind,
        right_ref=right_ref,
        label=None,
    )


def _group(
    *nodes: ConditionPlanNode | ConditionGroupPlanNode,
    operator: str = "AND",
    gid: str | None = "g1",
) -> ConditionGroupPlanNode:
    return ConditionGroupPlanNode(
        group_id=gid,
        operator=operator,
        nodes=tuple(nodes),
        label=None,
    )


def _rule(
    group:  ConditionGroupPlanNode,
    kind:   str = "entry",
    index:  int = 0,
    rid:    str | None = "r1",
) -> RulePlanNode:
    return RulePlanNode(
        rule_id=rid,
        kind=kind,  # type: ignore[arg-type]
        index=index,
        label=None,
        condition_group=group,
    )


def _plan(*rules: RulePlanNode, draft_id: str | None = None) -> EvaluationPlan:
    return EvaluationPlan(
        draft_id=draft_id,
        semantic_version="1.0",
        rule_nodes=tuple(rules),
        dependencies=DependencySet(tool_outputs=(), price_fields=(), constants=()),
        diagnostics=(),
        node_count=len(rules),
        compiled_at=_NOW,
    )


def _two_bar_ctx(
    current:  dict[str, float],
    previous: dict[str, float] | None = None,
    eval_id:  str = "test-eval",
) -> TwoBarEvaluationContext:
    return TwoBarEvaluationContext(
        evaluation_id=eval_id,
        current_values=current,
        previous_values=previous,
    )


def _make_crossover_evaluator() -> CrossoverConditionEvaluator:
    resolver   = ScalarOperandResolver()
    op_eval    = ScalarOperatorEvaluator()
    scalar_ce  = ScalarConditionEvaluator(resolver, op_eval)
    return CrossoverConditionEvaluator(scalar_ce)


def _bar(
    index:   int,
    close:   float,
    tools:   dict[str, float] | None = None,
) -> HistoricalBarContext:
    return HistoricalBarContext(
        bar_index=index,
        price_fields={"close": close},
        tool_outputs=tools or {},
    )


def _hist_input(plan: EvaluationPlan, *bars: HistoricalBarContext) -> HistoricalEvaluationInput:
    return HistoricalEvaluationInput(plan=plan, bars=tuple(bars))


# ---------------------------------------------------------------------------
# TestTwoBarEvaluationContext
# ---------------------------------------------------------------------------

class TestTwoBarEvaluationContext:
    def test_is_scalar_subclass(self):
        ctx = _two_bar_ctx({"price.close": 100.0})
        assert isinstance(ctx, ScalarEvaluationContext)

    def test_has_previous_bar_true(self):
        ctx = _two_bar_ctx({"price.close": 100.0}, previous={"price.close": 90.0})
        assert ctx.has_previous_bar is True

    def test_has_previous_bar_false(self):
        ctx = _two_bar_ctx({"price.close": 100.0}, previous=None)
        assert ctx.has_previous_bar is False

    def test_evaluation_id_stored(self):
        ctx = _two_bar_ctx({"price.close": 100.0}, eval_id="ev-99")
        assert ctx.evaluation_id == "ev-99"

    def test_current_price_field_resolved(self):
        ctx = _two_bar_ctx({"price.close": 123.0})
        assert ctx.resolve_price_field("close") == 123.0

    def test_current_tool_output_resolved(self):
        ctx = _two_bar_ctx({"tool.sma.value": 80.0})
        assert ctx.resolve_tool_output("sma", "value") == 80.0

    def test_current_constant_resolved(self):
        ctx = _two_bar_ctx({})
        assert ctx.resolve_constant("42") == 42.0

    def test_previous_price_field_resolved(self):
        ctx = _two_bar_ctx(
            {"price.close": 100.0},
            previous={"price.close": 90.0},
        )
        assert ctx.resolve_previous_price_field("close") == 90.0

    def test_previous_tool_output_resolved(self):
        ctx = _two_bar_ctx(
            {"tool.sma.value": 100.0},
            previous={"tool.sma.value": 80.0},
        )
        assert ctx.resolve_previous_tool_output("sma", "value") == 80.0

    def test_previous_constant_resolved(self):
        ctx = _two_bar_ctx({}, previous={})
        assert ctx.resolve_previous_constant("30") == 30.0

    def test_resolve_previous_price_raises_when_no_previous(self):
        ctx = _two_bar_ctx({"price.close": 100.0})
        with pytest.raises(PreviousBarMissingError):
            ctx.resolve_previous_price_field("close")

    def test_resolve_previous_tool_raises_when_no_previous(self):
        ctx = _two_bar_ctx({"tool.sma.value": 100.0})
        with pytest.raises(PreviousBarMissingError):
            ctx.resolve_previous_tool_output("sma", "value")

    def test_resolve_previous_constant_raises_when_no_previous(self):
        ctx = _two_bar_ctx({})
        with pytest.raises(PreviousBarMissingError):
            ctx.resolve_previous_constant("50")

    def test_previous_price_missing_key_raises_scalar_error(self):
        from backend.strategy_registry.scalar_evaluation_context import ScalarContextError
        ctx = _two_bar_ctx({"price.close": 100.0}, previous={"price.open": 99.0})
        with pytest.raises(ScalarContextError):
            ctx.resolve_previous_price_field("close")  # "close" not in previous

    def test_previous_tool_missing_key_raises_scalar_error(self):
        from backend.strategy_registry.scalar_evaluation_context import ScalarContextError
        ctx = _two_bar_ctx(
            {"tool.sma.value": 100.0},
            previous={"tool.other.value": 50.0},
        )
        with pytest.raises(ScalarContextError):
            ctx.resolve_previous_tool_output("sma", "value")

    def test_previous_values_isolated_from_current(self):
        curr = {"price.close": 100.0}
        prev = {"price.close": 80.0}
        ctx = _two_bar_ctx(curr, previous=prev)
        assert ctx.resolve_price_field("close") == 100.0
        assert ctx.resolve_previous_price_field("close") == 80.0

    def test_available_price_fields_from_current(self):
        ctx = _two_bar_ctx({"price.close": 1.0, "price.open": 2.0})
        assert "close" in ctx.available_price_fields
        assert "open"  in ctx.available_price_fields

    def test_available_tool_instances_from_current(self):
        ctx = _two_bar_ctx({"tool.sma.value": 1.0, "tool.rsi.value": 2.0})
        assert "sma" in ctx.available_tool_instances
        assert "rsi" in ctx.available_tool_instances


# ---------------------------------------------------------------------------
# TestCrossoverConditionEvaluator — scalar delegation
# ---------------------------------------------------------------------------

class TestCrossoverConditionEvaluatorScalarDelegation:
    def test_scalar_gt_true(self):
        ce = _make_crossover_evaluator()
        cond = _condition("price", "close", ">", "constant", "50")
        ctx  = _two_bar_ctx({"price.close": 100.0})
        result = ce.evaluate_condition(cond, ctx)
        assert result.outcome is True

    def test_scalar_gt_false(self):
        ce = _make_crossover_evaluator()
        cond = _condition("price", "close", ">", "constant", "50")
        ctx  = _two_bar_ctx({"price.close": 30.0})
        result = ce.evaluate_condition(cond, ctx)
        assert result.outcome is False

    def test_scalar_eq(self):
        ce = _make_crossover_evaluator()
        cond = _condition("price", "close", "==", "constant", "50")
        ctx  = _two_bar_ctx({"price.close": 50.0})
        assert ce.evaluate_condition(cond, ctx).outcome is True

    def test_scalar_ne(self):
        ce = _make_crossover_evaluator()
        cond = _condition("price", "close", "!=", "constant", "50")
        ctx  = _two_bar_ctx({"price.close": 99.0})
        assert ce.evaluate_condition(cond, ctx).outcome is True

    def test_scalar_le(self):
        ce = _make_crossover_evaluator()
        cond = _condition("price", "close", "<=", "constant", "100")
        ctx  = _two_bar_ctx({"price.close": 100.0})
        assert ce.evaluate_condition(cond, ctx).outcome is True

    def test_scalar_ge(self):
        ce = _make_crossover_evaluator()
        cond = _condition("price", "close", ">=", "constant", "100")
        ctx  = _two_bar_ctx({"price.close": 100.0})
        assert ce.evaluate_condition(cond, ctx).outcome is True

    def test_scalar_missing_operand_none(self):
        ce = _make_crossover_evaluator()
        cond = _condition("price", "nonexistent", ">", "constant", "50")
        ctx  = _two_bar_ctx({"price.close": 100.0})
        result = ce.evaluate_condition(cond, ctx)
        assert result.outcome is None
        assert len(result.diagnostics) == 1


# ---------------------------------------------------------------------------
# TestCrossoverConditionEvaluator — crosses_above
# ---------------------------------------------------------------------------

class TestCrossesAbove:
    def test_crosses_above_true(self):
        # prev: close=45 (<=50), curr: close=60 (>50)
        ce   = _make_crossover_evaluator()
        cond = _condition("price", "close", "crosses_above", "constant", "50")
        ctx  = _two_bar_ctx(
            {"price.close": 60.0},
            previous={"price.close": 45.0},
        )
        assert ce.evaluate_condition(cond, ctx).outcome is True

    def test_crosses_above_false_stayed_above(self):
        # prev: close=60 (>50), curr: close=70 (>50) — was already above
        ce   = _make_crossover_evaluator()
        cond = _condition("price", "close", "crosses_above", "constant", "50")
        ctx  = _two_bar_ctx(
            {"price.close": 70.0},
            previous={"price.close": 60.0},
        )
        assert ce.evaluate_condition(cond, ctx).outcome is False

    def test_crosses_above_false_stayed_below(self):
        # prev: close=30, curr: close=40 — never crossed
        ce   = _make_crossover_evaluator()
        cond = _condition("price", "close", "crosses_above", "constant", "50")
        ctx  = _two_bar_ctx(
            {"price.close": 40.0},
            previous={"price.close": 30.0},
        )
        assert ce.evaluate_condition(cond, ctx).outcome is False

    def test_crosses_above_false_crossed_below(self):
        # prev: close=60, curr: close=40 — crossed below, not above
        ce   = _make_crossover_evaluator()
        cond = _condition("price", "close", "crosses_above", "constant", "50")
        ctx  = _two_bar_ctx(
            {"price.close": 40.0},
            previous={"price.close": 60.0},
        )
        assert ce.evaluate_condition(cond, ctx).outcome is False

    def test_crosses_above_at_threshold_boundary(self):
        # prev: close=50 (<=50 is True), curr: close=50.1 (>50 is True)
        ce   = _make_crossover_evaluator()
        cond = _condition("price", "close", "crosses_above", "constant", "50")
        ctx  = _two_bar_ctx(
            {"price.close": 50.1},
            previous={"price.close": 50.0},
        )
        assert ce.evaluate_condition(cond, ctx).outcome is True

    def test_crosses_above_no_previous_bar(self):
        ce   = _make_crossover_evaluator()
        cond = _condition("price", "close", "crosses_above", "constant", "50")
        ctx  = _two_bar_ctx({"price.close": 100.0}, previous=None)
        result = ce.evaluate_condition(cond, ctx)
        assert result.outcome is None
        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].code == "no_previous_bar"

    def test_crosses_above_no_previous_bar_diagnostic_info_severity(self):
        ce   = _make_crossover_evaluator()
        cond = _condition("price", "close", "crosses_above", "constant", "50")
        ctx  = _two_bar_ctx({"price.close": 100.0}, previous=None)
        result = ce.evaluate_condition(cond, ctx)
        assert result.diagnostics[0].severity == "info"

    def test_crosses_above_condition_id_in_diagnostic(self):
        ce   = _make_crossover_evaluator()
        cond = _condition("price", "close", "crosses_above", "constant", "50", cid="cond99")
        ctx  = _two_bar_ctx({"price.close": 100.0}, previous=None)
        result = ce.evaluate_condition(cond, ctx)
        assert result.diagnostics[0].condition_id == "cond99"

    def test_crosses_above_with_tool_output(self):
        # crosses_above with tool_output operand
        ce   = _make_crossover_evaluator()
        cond = _condition("tool_output", "sma.value", "crosses_above", "constant", "50")
        ctx  = _two_bar_ctx(
            {"tool.sma.value": 60.0},
            previous={"tool.sma.value": 40.0},
        )
        assert ce.evaluate_condition(cond, ctx).outcome is True


# ---------------------------------------------------------------------------
# TestCrossoverConditionEvaluator — crosses_below
# ---------------------------------------------------------------------------

class TestCrossesBelow:
    def test_crosses_below_true(self):
        # prev: close=60 (>=50), curr: close=40 (<50)
        ce   = _make_crossover_evaluator()
        cond = _condition("price", "close", "crosses_below", "constant", "50")
        ctx  = _two_bar_ctx(
            {"price.close": 40.0},
            previous={"price.close": 60.0},
        )
        assert ce.evaluate_condition(cond, ctx).outcome is True

    def test_crosses_below_false_stayed_below(self):
        # prev: close=30, curr: close=20 — was already below
        ce   = _make_crossover_evaluator()
        cond = _condition("price", "close", "crosses_below", "constant", "50")
        ctx  = _two_bar_ctx(
            {"price.close": 20.0},
            previous={"price.close": 30.0},
        )
        assert ce.evaluate_condition(cond, ctx).outcome is False

    def test_crosses_below_false_stayed_above(self):
        # prev: close=70, curr: close=80 — stayed above
        ce   = _make_crossover_evaluator()
        cond = _condition("price", "close", "crosses_below", "constant", "50")
        ctx  = _two_bar_ctx(
            {"price.close": 80.0},
            previous={"price.close": 70.0},
        )
        assert ce.evaluate_condition(cond, ctx).outcome is False

    def test_crosses_below_at_threshold_boundary(self):
        # prev: close=50 (>=50), curr: close=49.9 (<50)
        ce   = _make_crossover_evaluator()
        cond = _condition("price", "close", "crosses_below", "constant", "50")
        ctx  = _two_bar_ctx(
            {"price.close": 49.9},
            previous={"price.close": 50.0},
        )
        assert ce.evaluate_condition(cond, ctx).outcome is True

    def test_crosses_below_no_previous_bar(self):
        ce   = _make_crossover_evaluator()
        cond = _condition("price", "close", "crosses_below", "constant", "50")
        ctx  = _two_bar_ctx({"price.close": 30.0}, previous=None)
        result = ce.evaluate_condition(cond, ctx)
        assert result.outcome is None
        assert result.diagnostics[0].code == "no_previous_bar"

    def test_crosses_below_with_tool_output(self):
        ce   = _make_crossover_evaluator()
        cond = _condition("tool_output", "rsi.value", "crosses_below", "constant", "70")
        ctx  = _two_bar_ctx(
            {"tool.rsi.value": 65.0},
            previous={"tool.rsi.value": 75.0},
        )
        assert ce.evaluate_condition(cond, ctx).outcome is True


# ---------------------------------------------------------------------------
# TestCrossoverConditionEvaluator — edge cases
# ---------------------------------------------------------------------------

class TestCrossoverEvaluatorEdgeCases:
    def test_unknown_operator_produces_none(self):
        ce   = _make_crossover_evaluator()
        cond = _condition("price", "close", "unknown_op", "constant", "50")
        ctx  = _two_bar_ctx({"price.close": 100.0})
        result = ce.evaluate_condition(cond, ctx)
        assert result.outcome is None
        assert result.diagnostics[0].code == "unsupported_operator"

    def test_wrong_context_type_for_crossover(self):
        from backend.strategy_registry.scalar_evaluation_context import ScalarEvaluationContext
        ce   = _make_crossover_evaluator()
        cond = _condition("price", "close", "crosses_above", "constant", "50")
        ctx  = ScalarEvaluationContext(
            evaluation_id="ev-1",
            scalar_values={"price.close": 100.0},
        )
        result = ce.evaluate_condition(cond, ctx)
        assert result.outcome is None
        assert result.diagnostics[0].code == "context_unavailable"

    def test_crossover_missing_current_operand(self):
        ce   = _make_crossover_evaluator()
        cond = _condition("price", "missing_field", "crosses_above", "constant", "50")
        ctx  = _two_bar_ctx(
            {"price.close": 100.0},
            previous={"price.close": 40.0},
        )
        result = ce.evaluate_condition(cond, ctx)
        assert result.outcome is None
        assert result.diagnostics[0].code == "unresolved_operand"

    def test_crossover_missing_previous_operand(self):
        ce   = _make_crossover_evaluator()
        cond = _condition("price", "close", "crosses_above", "constant", "50")
        ctx  = _two_bar_ctx(
            {"price.close": 100.0},
            previous={"price.open": 40.0},  # "close" missing from previous
        )
        result = ce.evaluate_condition(cond, ctx)
        assert result.outcome is None
        assert result.diagnostics[0].code == "unresolved_operand"

    def test_crossover_condition_id_preserved(self):
        ce   = _make_crossover_evaluator()
        cond = _condition("price", "close", "crosses_above", "constant", "50", cid="myc")
        ctx  = _two_bar_ctx(
            {"price.close": 60.0},
            previous={"price.close": 40.0},
        )
        result = ce.evaluate_condition(cond, ctx)
        assert result.condition_id == "myc"
        assert result.outcome is True

    def test_crossover_no_diagnostics_on_success(self):
        ce   = _make_crossover_evaluator()
        cond = _condition("price", "close", "crosses_above", "constant", "50")
        ctx  = _two_bar_ctx(
            {"price.close": 60.0},
            previous={"price.close": 40.0},
        )
        result = ce.evaluate_condition(cond, ctx)
        assert result.diagnostics == ()


# ---------------------------------------------------------------------------
# TestTwoBarScalarEngine
# ---------------------------------------------------------------------------

class TestTwoBarScalarEngine:
    def test_supported_operators_contains_scalar(self):
        engine = TwoBarScalarEngine()
        for op in (">", "<", ">=", "<=", "==", "!="):
            assert op in engine.supported_operators

    def test_supported_operators_contains_crossover(self):
        engine = TwoBarScalarEngine()
        assert "crosses_above" in engine.supported_operators
        assert "crosses_below" in engine.supported_operators

    def test_evaluate_scalar_plan_true(self):
        engine = TwoBarScalarEngine()
        plan   = _plan(_rule(_group(_condition("price", "close", ">", "constant", "50"))))
        ctx    = _two_bar_ctx({"price.close": 100.0})
        trace  = engine.evaluate_plan(plan, ctx)
        assert trace.entry_triggered is True

    def test_evaluate_scalar_plan_false(self):
        engine = TwoBarScalarEngine()
        plan   = _plan(_rule(_group(_condition("price", "close", ">", "constant", "50"))))
        ctx    = _two_bar_ctx({"price.close": 30.0})
        trace  = engine.evaluate_plan(plan, ctx)
        assert trace.entry_triggered is False

    def test_evaluate_crossover_plan_true(self):
        engine = TwoBarScalarEngine()
        plan   = _plan(_rule(_group(_condition("price", "close", "crosses_above", "constant", "50"))))
        ctx    = _two_bar_ctx({"price.close": 60.0}, previous={"price.close": 40.0})
        trace  = engine.evaluate_plan(plan, ctx)
        assert trace.entry_triggered is True

    def test_evaluate_crossover_first_bar_none(self):
        engine = TwoBarScalarEngine()
        plan   = _plan(_rule(_group(_condition("price", "close", "crosses_above", "constant", "50"))))
        ctx    = _two_bar_ctx({"price.close": 60.0}, previous=None)
        trace  = engine.evaluate_plan(plan, ctx)
        assert trace.entry_triggered is None

    def test_evaluate_plan_returns_trace(self):
        engine = TwoBarScalarEngine()
        plan   = _plan(_rule(_group(_condition())))
        ctx    = _two_bar_ctx({"price.close": 100.0})
        trace  = engine.evaluate_plan(plan, ctx)
        assert isinstance(trace, EvaluationTrace)

    def test_evaluation_id_in_trace(self):
        engine = TwoBarScalarEngine()
        plan   = _plan(_rule(_group(_condition())))
        ctx    = _two_bar_ctx({"price.close": 100.0}, eval_id="ev-test-42")
        trace  = engine.evaluate_plan(plan, ctx)
        assert trace.evaluation_id == "ev-test-42"

    def test_empty_plan_no_triggered(self):
        engine = TwoBarScalarEngine()
        plan   = _plan(draft_id=None)
        ctx    = _two_bar_ctx({"price.close": 100.0})
        trace  = engine.evaluate_plan(plan, ctx)
        assert trace.entry_triggered is None
        assert trace.exit_triggered  is None

    def test_mixed_scalar_and_crossover_rules(self):
        engine = TwoBarScalarEngine()
        r1 = _rule(_group(_condition("price", "close", ">", "constant", "50")),
                   kind="entry", rid="r1", index=0)
        r2 = _rule(_group(_condition("price", "close", "crosses_above", "constant", "50")),
                   kind="entry", rid="r2", index=1)
        plan = _plan(r1, r2)
        # Bar 2: close=60, prev close=40 → r1=True, r2=True → entry=True
        ctx  = _two_bar_ctx({"price.close": 60.0}, previous={"price.close": 40.0})
        trace = engine.evaluate_plan(plan, ctx)
        assert trace.entry_triggered is True

    def test_plan_draft_id_in_trace(self):
        engine = TwoBarScalarEngine()
        plan   = _plan(_rule(_group(_condition())), draft_id="draft-007")
        ctx    = _two_bar_ctx({"price.close": 100.0})
        trace  = engine.evaluate_plan(plan, ctx)
        assert trace.plan_draft_id == "draft-007"


# ---------------------------------------------------------------------------
# TestHistoricalCrossoverIntegration
# ---------------------------------------------------------------------------

class TestHistoricalCrossoverIntegration:
    def _crossover_plan(self, operator: str = "crosses_above") -> EvaluationPlan:
        cond = _condition("price", "close", operator, "constant", "50")
        return _plan(_rule(_group(cond)))

    def test_first_bar_crossover_is_none(self):
        plan   = self._crossover_plan()
        result = evaluate_history(_hist_input(plan, _bar(0, 60.0)))
        assert result.bar_results[0].entry_triggered is None

    def test_first_bar_not_counted_in_entry_count(self):
        plan   = self._crossover_plan()
        result = evaluate_history(_hist_input(plan, _bar(0, 60.0)))
        assert result.entry_triggered_count == 0

    def test_second_bar_crosses_above(self):
        plan   = self._crossover_plan("crosses_above")
        # Bar 0: close=40 (first bar, prev=None → None)
        # Bar 1: close=60, prev=40 → crosses above 50 → True
        result = evaluate_history(_hist_input(plan, _bar(0, 40.0), _bar(1, 60.0)))
        assert result.bar_results[0].entry_triggered is None
        assert result.bar_results[1].entry_triggered is True

    def test_second_bar_does_not_cross_above(self):
        plan   = self._crossover_plan("crosses_above")
        # prev=60, curr=70 — already above, no cross
        result = evaluate_history(_hist_input(plan, _bar(0, 60.0), _bar(1, 70.0)))
        assert result.bar_results[1].entry_triggered is False

    def test_crosses_below_integration(self):
        plan   = self._crossover_plan("crosses_below")
        # Bar 0: close=60 (first bar → None)
        # Bar 1: close=40, prev=60 → crosses below 50 → True
        result = evaluate_history(_hist_input(plan, _bar(0, 60.0), _bar(1, 40.0)))
        assert result.bar_results[0].entry_triggered is None
        assert result.bar_results[1].entry_triggered is True

    def test_entry_count_excludes_first_bar_none(self):
        plan   = self._crossover_plan("crosses_above")
        # 3 bars: None, True, False
        result = evaluate_history(_hist_input(plan,
            _bar(0, 40.0),  # first bar → None
            _bar(1, 60.0),  # crosses above → True
            _bar(2, 70.0),  # still above, no new cross → False
        ))
        assert result.entry_triggered_count == 1

    def test_multiple_crossovers(self):
        plan   = self._crossover_plan("crosses_above")
        # bars: 40, 60 (cross↑), 40, 60 (cross↑), 40, 60 (cross↑)
        bars = [
            _bar(0, 40.0),
            _bar(1, 60.0),
            _bar(2, 40.0),
            _bar(3, 60.0),
            _bar(4, 40.0),
            _bar(5, 60.0),
        ]
        result = evaluate_history(_hist_input(plan, *bars))
        assert result.entry_triggered_count == 3

    def test_bars_evaluated_count(self):
        plan   = self._crossover_plan()
        result = evaluate_history(_hist_input(plan,
            _bar(0, 40.0), _bar(1, 60.0), _bar(2, 70.0)
        ))
        assert result.bars_evaluated == 3

    def test_empty_bars(self):
        plan   = self._crossover_plan()
        result = evaluate_history(_hist_input(plan))
        assert result.bars_evaluated == 0
        assert result.bar_results == ()

    def test_previous_bar_values_propagate_correctly(self):
        """Previous values from bar N become previous_values for bar N+1."""
        plan   = self._crossover_plan("crosses_above")
        # Sequence designed so only bar 3 triggers
        bars = [
            _bar(0, 40.0),   # first: None
            _bar(1, 45.0),   # prev=40, curr=45: both <=50 → False
            _bar(2, 48.0),   # prev=45, curr=48: both <=50 → False
            _bar(3, 60.0),   # prev=48 (<=50), curr=60 (>50) → True
        ]
        result = evaluate_history(_hist_input(plan, *bars))
        results = [r.entry_triggered for r in result.bar_results]
        assert results == [None, False, False, True]

    def test_scalar_plan_still_works_after_2p3(self):
        """Ensure existing scalar evaluation still works with TwoBarScalarEngine."""
        cond = _condition("price", "close", ">", "constant", "50")
        plan = _plan(_rule(_group(cond)))
        result = evaluate_history(_hist_input(plan,
            _bar(0, 100.0), _bar(1, 30.0), _bar(2, 70.0)
        ))
        triggers = [r.entry_triggered for r in result.bar_results]
        assert triggers == [True, False, True]
        assert result.entry_triggered_count == 2

    def test_bar_index_preserved_crossover(self):
        plan = self._crossover_plan()
        result = evaluate_history(_hist_input(plan, _bar(10, 60.0), _bar(20, 70.0)))
        assert result.bar_results[0].bar_index == 10
        assert result.bar_results[1].bar_index == 20

    def test_trace_evaluation_id_format(self):
        plan = _plan(_rule(_group(_condition())), draft_id="d1")
        result = evaluate_history(_hist_input(plan, _bar(5, 100.0)))
        eid = result.bar_results[0].trace.evaluation_id
        assert "d1" in eid and "5" in eid

    def test_plan_draft_id_preserved(self):
        plan = _plan(_rule(_group(_condition())), draft_id="draft-xyz")
        result = evaluate_history(_hist_input(plan, _bar(0, 100.0)))
        assert result.plan_draft_id == "draft-xyz"

    def test_crossover_with_tool_output_integration(self):
        cond = _condition("tool_output", "sma.value", "crosses_above", "constant", "80")
        plan = _plan(_rule(_group(cond)))
        bars = [
            HistoricalBarContext(
                bar_index=0, price_fields={"close": 100.0},
                tool_outputs={"sma.value": 70.0},
            ),
            HistoricalBarContext(
                bar_index=1, price_fields={"close": 100.0},
                tool_outputs={"sma.value": 90.0},
            ),
        ]
        result = evaluate_history(_hist_input(plan, *bars))
        assert result.bar_results[0].entry_triggered is None   # first bar
        assert result.bar_results[1].entry_triggered is True   # 70<=80 AND 90>80


# ---------------------------------------------------------------------------
# Architecture boundary
# ---------------------------------------------------------------------------

_FORBIDDEN = (
    "strategy_runtime",
    "backtesting",
    "backend.execution",
    "forward_testing",
)

_BOUNDARY_MODULES = [
    "backend.strategy_registry.two_bar_context",
    "backend.strategy_registry.crossover_evaluator",
    "backend.strategy_registry.historical_evaluator",
]


class TestArchitectureBoundary:
    @pytest.mark.parametrize("module_name", _BOUNDARY_MODULES)
    @pytest.mark.parametrize("forbidden", _FORBIDDEN)
    def test_no_forbidden_import(self, module_name: str, forbidden: str):
        mod = importlib.import_module(module_name)
        src = inspect.getsource(mod)
        lines = [
            ln for ln in src.splitlines()
            if ln.strip().startswith(("import ", "from ")) and forbidden in ln
        ]
        assert lines == [], (
            f"{module_name} imports from '{forbidden}': {lines}"
        )

    def test_crossover_operators_set_correct(self):
        assert "crosses_above" in CROSSOVER_OPERATORS
        assert "crosses_below" in CROSSOVER_OPERATORS
        assert len(CROSSOVER_OPERATORS) == 2

    def test_all_two_bar_operators_is_union(self):
        from backend.strategy_registry.scalar_evaluator import SCALAR_OPERATORS
        assert ALL_TWO_BAR_OPERATORS == SCALAR_OPERATORS | CROSSOVER_OPERATORS

    def test_two_bar_context_is_evaluation_context(self):
        from backend.strategy_registry.evaluator_contracts import EvaluationContext
        ctx = _two_bar_ctx({})
        assert isinstance(ctx, EvaluationContext)
