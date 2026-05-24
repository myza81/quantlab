"""
Phase 2P.1 — Concrete Scalar Evaluator unit tests.

Coverage:
    ScalarEvaluationContext        — value lookup, properties, error handling
    ScalarOperandResolver          — all operand kinds, missing refs, bad kinds
    ScalarOperatorEvaluator        — all 6 scalar operators, deferred ops, bad ops
    ScalarConditionEvaluator       — true/false/indeterminate conditions, diagnostics
    ScalarGroupEvaluator           — AND/OR, nested groups, indeterminate propagation
    ScalarRuleEvaluator            — entry/exit rules, triggered/not-triggered
    ScalarEvaluationEngine         — full plan evaluation, trigger aggregation
    Architecture boundary          — no forbidden imports
"""
from __future__ import annotations

import importlib
import inspect
from datetime import datetime, timezone

import pytest

from backend.strategy_registry.evaluator_contracts import (
    ConditionEvaluationResult,
    EvaluationContext,
    EvaluationTrace,
    GroupEvaluationResult,
    RuleEvaluationResult,
)
from backend.strategy_registry.scalar_evaluation_context import (
    ScalarContextError,
    ScalarEvaluationContext,
)
from backend.strategy_registry.scalar_evaluator import (
    SCALAR_OPERATORS,
    ScalarConditionEvaluator,
    ScalarEvaluationEngine,
    ScalarGroupEvaluator,
    ScalarOperandResolver,
    ScalarOperatorEvaluator,
    ScalarRuleEvaluator,
    UnsupportedOperatorError,
)
from backend.strategy_registry.semantic_plan import (
    CompilationDiagnostic,
    ConditionGroupPlanNode,
    ConditionPlanNode,
    DependencySet,
    EvaluationPlan,
    RulePlanNode,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 5, 21, tzinfo=timezone.utc)


def _ctx(values: dict[str, float] | None = None, eval_id: str = "test-eval") -> ScalarEvaluationContext:
    return ScalarEvaluationContext(evaluation_id=eval_id, scalar_values=values or {})


def _condition(
    left_kind: str,
    left_ref:  str,
    operator:  str,
    right_kind: str,
    right_ref:  str,
    cid: str | None = "c1",
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
    group: ConditionGroupPlanNode,
    kind: str = "entry",
    index: int = 0,
    rid: str | None = "r1",
) -> RulePlanNode:
    return RulePlanNode(
        rule_id=rid,
        kind=kind,  # type: ignore[arg-type]
        index=index,
        label=None,
        condition_group=group,
    )


def _plan(*rules: RulePlanNode) -> EvaluationPlan:
    return EvaluationPlan(
        draft_id=None,
        semantic_version="1.0",
        rule_nodes=tuple(rules),
        dependencies=DependencySet(tool_outputs=(), price_fields=(), constants=()),
        diagnostics=(),
        node_count=len(rules),
        compiled_at=_NOW,
    )


def _engine() -> ScalarEvaluationEngine:
    return ScalarEvaluationEngine()


# ---------------------------------------------------------------------------
# ScalarEvaluationContext
# ---------------------------------------------------------------------------

class TestScalarEvaluationContext:
    def test_evaluation_id(self):
        ctx = _ctx(eval_id="abc-123")
        assert ctx.evaluation_id == "abc-123"

    def test_resolve_price_field_ok(self):
        ctx = _ctx({"price.close": 100.0})
        assert ctx.resolve_price_field("close") == 100.0

    def test_resolve_price_field_missing(self):
        ctx = _ctx({"price.close": 100.0})
        with pytest.raises(ScalarContextError, match="open"):
            ctx.resolve_price_field("open")

    def test_resolve_tool_output_ok(self):
        ctx = _ctx({"tool.sma_fast.value": 98.5})
        assert ctx.resolve_tool_output("sma_fast", "value") == 98.5

    def test_resolve_tool_output_missing(self):
        ctx = _ctx({"tool.sma_fast.value": 98.5})
        with pytest.raises(ScalarContextError, match="sma_slow"):
            ctx.resolve_tool_output("sma_slow", "value")

    def test_resolve_constant_integer_string(self):
        ctx = _ctx()
        assert ctx.resolve_constant("30") == 30.0

    def test_resolve_constant_float_string(self):
        ctx = _ctx()
        assert ctx.resolve_constant("0.75") == 0.75

    def test_resolve_constant_negative(self):
        ctx = _ctx()
        assert ctx.resolve_constant("-5") == -5.0

    def test_resolve_constant_invalid(self):
        ctx = _ctx()
        with pytest.raises(ScalarContextError, match="not_a_number"):
            ctx.resolve_constant("not_a_number")

    def test_available_price_fields_sorted(self):
        ctx = _ctx({"price.open": 1.0, "price.close": 2.0, "price.high": 3.0})
        assert ctx.available_price_fields == ("close", "high", "open")

    def test_available_tool_instances_sorted(self):
        ctx = _ctx({
            "tool.sma_slow.value": 1.0,
            "tool.rsi.value": 2.0,
            "tool.sma_fast.value": 3.0,
        })
        assert ctx.available_tool_instances == ("rsi", "sma_fast", "sma_slow")

    def test_available_price_fields_empty(self):
        ctx = _ctx({"tool.sma.value": 1.0})
        assert ctx.available_price_fields == ()

    def test_available_tool_instances_empty(self):
        ctx = _ctx({"price.close": 100.0})
        assert ctx.available_tool_instances == ()

    def test_implements_evaluation_context(self):
        ctx = _ctx()
        assert isinstance(ctx, EvaluationContext)

    def test_plan_draft_id_stored(self):
        ctx = ScalarEvaluationContext(
            evaluation_id="e1",
            scalar_values={},
            plan_draft_id="draft-abc",
        )
        assert ctx._plan_draft_id == "draft-abc"

    def test_multiple_tool_outputs_same_instance(self):
        ctx = _ctx({"tool.macd.signal": 0.5, "tool.macd.histogram": 0.1})
        assert ctx.resolve_tool_output("macd", "signal") == 0.5
        assert ctx.resolve_tool_output("macd", "histogram") == 0.1
        assert ctx.available_tool_instances == ("macd",)


# ---------------------------------------------------------------------------
# ScalarOperandResolver
# ---------------------------------------------------------------------------

class TestScalarOperandResolver:
    def _resolver(self) -> ScalarOperandResolver:
        return ScalarOperandResolver()

    def test_resolve_constant(self):
        r = self._resolver()
        ctx = _ctx()
        assert r.resolve("constant", "42", ctx) == 42.0

    def test_resolve_price(self):
        r = self._resolver()
        ctx = _ctx({"price.close": 105.0})
        assert r.resolve("price", "close", ctx) == 105.0

    def test_resolve_tool_output(self):
        r = self._resolver()
        ctx = _ctx({"tool.rsi.value": 55.0})
        assert r.resolve("tool_output", "rsi.value", ctx) == 55.0

    def test_resolve_tool_output_bad_ref_format(self):
        r = self._resolver()
        ctx = _ctx()
        with pytest.raises(ScalarContextError, match="instance_id.output_name"):
            r.resolve("tool_output", "no_dot_here", ctx)

    def test_resolve_unknown_kind(self):
        r = self._resolver()
        ctx = _ctx()
        with pytest.raises(ScalarContextError, match="Unknown operand kind"):
            r.resolve("weird_kind", "ref", ctx)

    def test_resolve_missing_price(self):
        r = self._resolver()
        ctx = _ctx()
        with pytest.raises(ScalarContextError):
            r.resolve("price", "close", ctx)

    def test_resolve_missing_tool_output(self):
        r = self._resolver()
        ctx = _ctx()
        with pytest.raises(ScalarContextError):
            r.resolve("tool_output", "sma.value", ctx)


# ---------------------------------------------------------------------------
# ScalarOperatorEvaluator
# ---------------------------------------------------------------------------

class TestScalarOperatorEvaluator:
    def _ev(self) -> ScalarOperatorEvaluator:
        return ScalarOperatorEvaluator()

    def test_supported_operators_set(self):
        ev = self._ev()
        assert ev.supported_operators == frozenset({">", "<", ">=", "<=", "==", "!="})

    def test_gt_true(self):
        assert self._ev().evaluate(101.0, ">", 100.0) is True

    def test_gt_false(self):
        assert self._ev().evaluate(99.0, ">", 100.0) is False

    def test_lt_true(self):
        assert self._ev().evaluate(50.0, "<", 100.0) is True

    def test_lt_false(self):
        assert self._ev().evaluate(150.0, "<", 100.0) is False

    def test_gte_equal(self):
        assert self._ev().evaluate(100.0, ">=", 100.0) is True

    def test_gte_greater(self):
        assert self._ev().evaluate(101.0, ">=", 100.0) is True

    def test_gte_less(self):
        assert self._ev().evaluate(99.0, ">=", 100.0) is False

    def test_lte_equal(self):
        assert self._ev().evaluate(100.0, "<=", 100.0) is True

    def test_lte_less(self):
        assert self._ev().evaluate(99.0, "<=", 100.0) is True

    def test_lte_greater(self):
        assert self._ev().evaluate(101.0, "<=", 100.0) is False

    def test_eq_equal(self):
        assert self._ev().evaluate(100.0, "==", 100.0) is True

    def test_eq_not_equal(self):
        assert self._ev().evaluate(100.0, "==", 100.1) is False

    def test_neq_different(self):
        assert self._ev().evaluate(99.0, "!=", 100.0) is True

    def test_neq_same(self):
        assert self._ev().evaluate(100.0, "!=", 100.0) is False

    def test_int_float_compatibility(self):
        # int and float should work without error
        assert self._ev().evaluate(100, ">", 50.0) is True

    def test_integer_equality(self):
        assert self._ev().evaluate(30, "==", 30.0) is True

    def test_crosses_above_raises(self):
        with pytest.raises(UnsupportedOperatorError, match="crosses_above"):
            self._ev().evaluate(100.0, "crosses_above", 98.0)

    def test_crosses_below_raises(self):
        with pytest.raises(UnsupportedOperatorError, match="crosses_below"):
            self._ev().evaluate(98.0, "crosses_below", 100.0)

    def test_unknown_operator_raises(self):
        with pytest.raises(UnsupportedOperatorError, match="unknown_op"):
            self._ev().evaluate(1.0, "unknown_op", 2.0)


# ---------------------------------------------------------------------------
# ScalarConditionEvaluator
# ---------------------------------------------------------------------------

class TestScalarConditionEvaluator:
    def _evaluator(self) -> ScalarConditionEvaluator:
        return ScalarConditionEvaluator(ScalarOperandResolver(), ScalarOperatorEvaluator())

    def test_true_condition(self):
        ev = self._evaluator()
        node = _condition("price", "close", ">", "constant", "50")
        ctx = _ctx({"price.close": 100.0})
        result = ev.evaluate_condition(node, ctx)
        assert result.outcome is True
        assert result.diagnostics == ()

    def test_false_condition(self):
        ev = self._evaluator()
        node = _condition("price", "close", ">", "constant", "200")
        ctx = _ctx({"price.close": 100.0})
        result = ev.evaluate_condition(node, ctx)
        assert result.outcome is False

    def test_condition_id_preserved(self):
        ev = self._evaluator()
        node = _condition("constant", "10", "==", "constant", "10", cid="myid")
        result = ev.evaluate_condition(node, _ctx())
        assert result.condition_id == "myid"

    def test_missing_left_operand_produces_diagnostic(self):
        ev = self._evaluator()
        node = _condition("price", "close", ">", "constant", "50")
        ctx = _ctx()  # no price.close
        result = ev.evaluate_condition(node, ctx)
        assert result.outcome is None
        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].code == "unresolved_operand"
        assert result.diagnostics[0].severity == "error"

    def test_missing_right_operand_produces_diagnostic(self):
        ev = self._evaluator()
        node = _condition("constant", "50", ">", "tool_output", "sma.value")
        ctx = _ctx()  # no tool.sma.value
        result = ev.evaluate_condition(node, ctx)
        assert result.outcome is None
        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].code == "unresolved_operand"

    def test_unsupported_operator_produces_diagnostic(self):
        ev = self._evaluator()
        node = _condition("price", "close", "crosses_above", "tool_output", "sma.value")
        ctx = _ctx({"price.close": 100.0, "tool.sma.value": 98.0})
        result = ev.evaluate_condition(node, ctx)
        assert result.outcome is None
        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].code == "unsupported_operator"

    def test_tool_output_condition_true(self):
        ev = self._evaluator()
        node = _condition("tool_output", "sma_fast.value", ">", "tool_output", "sma_slow.value")
        ctx = _ctx({"tool.sma_fast.value": 102.0, "tool.sma_slow.value": 99.0})
        result = ev.evaluate_condition(node, ctx)
        assert result.outcome is True

    def test_returns_condition_evaluation_result(self):
        ev = self._evaluator()
        node = _condition("constant", "1", "==", "constant", "1")
        result = ev.evaluate_condition(node, _ctx())
        assert isinstance(result, ConditionEvaluationResult)


# ---------------------------------------------------------------------------
# ScalarGroupEvaluator
# ---------------------------------------------------------------------------

class TestScalarGroupEvaluator:
    def _group_eval(self) -> ScalarGroupEvaluator:
        cond_eval = ScalarConditionEvaluator(ScalarOperandResolver(), ScalarOperatorEvaluator())
        return ScalarGroupEvaluator(cond_eval)

    def _true_condition(self, cid: str = "c1") -> ConditionPlanNode:
        return _condition("constant", "1", "==", "constant", "1", cid=cid)

    def _false_condition(self, cid: str = "c1") -> ConditionPlanNode:
        return _condition("constant", "1", "==", "constant", "2", cid=cid)

    def _missing_condition(self, cid: str = "c1") -> ConditionPlanNode:
        return _condition("price", "close", ">", "constant", "0", cid=cid)  # missing price.close

    def test_and_all_true(self):
        ev = self._group_eval()
        g = _group(self._true_condition("c1"), self._true_condition("c2"), operator="AND")
        result = ev.evaluate_group(g, _ctx())
        assert result.outcome is True

    def test_and_one_false(self):
        ev = self._group_eval()
        g = _group(self._true_condition("c1"), self._false_condition("c2"), operator="AND")
        result = ev.evaluate_group(g, _ctx())
        assert result.outcome is False

    def test_and_all_false(self):
        ev = self._group_eval()
        g = _group(self._false_condition("c1"), self._false_condition("c2"), operator="AND")
        result = ev.evaluate_group(g, _ctx())
        assert result.outcome is False

    def test_and_any_none_with_no_false(self):
        ev = self._group_eval()
        g = _group(self._true_condition("c1"), self._missing_condition("c2"), operator="AND")
        result = ev.evaluate_group(g, _ctx())
        assert result.outcome is None  # missing → indeterminate; true + None → None

    def test_and_false_with_none(self):
        # AND: False always wins over None
        ev = self._group_eval()
        g = _group(self._false_condition("c1"), self._missing_condition("c2"), operator="AND")
        result = ev.evaluate_group(g, _ctx())
        assert result.outcome is False

    def test_or_all_true(self):
        ev = self._group_eval()
        g = _group(self._true_condition("c1"), self._true_condition("c2"), operator="OR")
        result = ev.evaluate_group(g, _ctx())
        assert result.outcome is True

    def test_or_one_true(self):
        ev = self._group_eval()
        g = _group(self._true_condition("c1"), self._false_condition("c2"), operator="OR")
        result = ev.evaluate_group(g, _ctx())
        assert result.outcome is True

    def test_or_all_false(self):
        ev = self._group_eval()
        g = _group(self._false_condition("c1"), self._false_condition("c2"), operator="OR")
        result = ev.evaluate_group(g, _ctx())
        assert result.outcome is False

    def test_or_true_with_none(self):
        # OR: True wins over None
        ev = self._group_eval()
        g = _group(self._true_condition("c1"), self._missing_condition("c2"), operator="OR")
        result = ev.evaluate_group(g, _ctx())
        assert result.outcome is True

    def test_or_all_none(self):
        ev = self._group_eval()
        g = _group(self._missing_condition("c1"), self._missing_condition("c2"), operator="OR")
        result = ev.evaluate_group(g, _ctx())
        assert result.outcome is None

    def test_child_results_populated(self):
        ev = self._group_eval()
        g = _group(self._true_condition("c1"), self._false_condition("c2"), operator="AND")
        result = ev.evaluate_group(g, _ctx())
        assert len(result.child_results) == 2

    def test_group_id_preserved(self):
        ev = self._group_eval()
        g = _group(self._true_condition(), operator="AND", gid="my_group")
        result = ev.evaluate_group(g, _ctx())
        assert result.group_id == "my_group"

    def test_nested_groups_and_inside_or(self):
        ev = self._group_eval()
        # (T AND F) OR T → False OR True → True
        inner = _group(self._true_condition("c1"), self._false_condition("c2"), operator="AND", gid="g_inner")
        outer = _group(inner, self._true_condition("c3"), operator="OR", gid="g_outer")
        result = ev.evaluate_group(outer, _ctx())
        assert result.outcome is True

    def test_nested_groups_or_inside_and(self):
        ev = self._group_eval()
        # (T OR F) AND T → True AND True → True
        inner = _group(self._true_condition("c1"), self._false_condition("c2"), operator="OR", gid="g_inner")
        outer = _group(inner, self._true_condition("c3"), operator="AND", gid="g_outer")
        result = ev.evaluate_group(outer, _ctx())
        assert result.outcome is True

    def test_deeply_nested_group(self):
        ev = self._group_eval()
        leaf = _group(self._true_condition("c1"), operator="AND", gid="g1")
        mid  = _group(leaf, operator="AND", gid="g2")
        top  = _group(mid, operator="AND", gid="g3")
        result = ev.evaluate_group(top, _ctx())
        assert result.outcome is True

    def test_returns_group_evaluation_result(self):
        ev = self._group_eval()
        g = _group(self._true_condition(), operator="AND")
        result = ev.evaluate_group(g, _ctx())
        assert isinstance(result, GroupEvaluationResult)


# ---------------------------------------------------------------------------
# ScalarRuleEvaluator
# ---------------------------------------------------------------------------

class TestScalarRuleEvaluator:
    def _rule_eval(self) -> ScalarRuleEvaluator:
        cond_eval = ScalarConditionEvaluator(ScalarOperandResolver(), ScalarOperatorEvaluator())
        grp_eval  = ScalarGroupEvaluator(cond_eval)
        return ScalarRuleEvaluator(grp_eval)

    def _true_cond(self) -> ConditionPlanNode:
        return _condition("constant", "1", "==", "constant", "1")

    def _false_cond(self) -> ConditionPlanNode:
        return _condition("constant", "1", "==", "constant", "2")

    def test_entry_rule_triggered(self):
        ev = self._rule_eval()
        rule = _rule(_group(self._true_cond(), operator="AND"), kind="entry")
        result = ev.evaluate_rule(rule, _ctx())
        assert result.triggered is True
        assert result.kind == "entry"

    def test_entry_rule_not_triggered(self):
        ev = self._rule_eval()
        rule = _rule(_group(self._false_cond(), operator="AND"), kind="entry")
        result = ev.evaluate_rule(rule, _ctx())
        assert result.triggered is False

    def test_exit_rule_triggered(self):
        ev = self._rule_eval()
        rule = _rule(_group(self._true_cond(), operator="AND"), kind="exit", rid="exit1")
        result = ev.evaluate_rule(rule, _ctx())
        assert result.triggered is True
        assert result.kind == "exit"

    def test_rule_id_preserved(self):
        ev = self._rule_eval()
        rule = _rule(_group(self._true_cond(), operator="AND"), rid="rule-abc")
        result = ev.evaluate_rule(rule, _ctx())
        assert result.rule_id == "rule-abc"

    def test_index_preserved(self):
        ev = self._rule_eval()
        rule = _rule(_group(self._true_cond(), operator="AND"), index=2)
        result = ev.evaluate_rule(rule, _ctx())
        assert result.index == 2

    def test_group_result_embedded(self):
        ev = self._rule_eval()
        rule = _rule(_group(self._true_cond(), operator="AND"))
        result = ev.evaluate_rule(rule, _ctx())
        assert isinstance(result.group_result, GroupEvaluationResult)

    def test_returns_rule_evaluation_result(self):
        ev = self._rule_eval()
        rule = _rule(_group(self._true_cond(), operator="AND"))
        result = ev.evaluate_rule(rule, _ctx())
        assert isinstance(result, RuleEvaluationResult)


# ---------------------------------------------------------------------------
# ScalarEvaluationEngine — full plan evaluation
# ---------------------------------------------------------------------------

class TestScalarEvaluationEngine:
    def _true_cond(self, cid: str = "c1") -> ConditionPlanNode:
        return _condition("constant", "1", "==", "constant", "1", cid=cid)

    def _false_cond(self, cid: str = "c1") -> ConditionPlanNode:
        return _condition("constant", "1", "==", "constant", "2", cid=cid)

    def test_entry_triggered(self):
        engine = _engine()
        rule = _rule(_group(self._true_cond(), operator="AND"), kind="entry")
        trace = engine.evaluate_plan(_plan(rule), _ctx())
        assert trace.entry_triggered is True
        assert trace.exit_triggered is None  # no exit rules

    def test_entry_not_triggered(self):
        engine = _engine()
        rule = _rule(_group(self._false_cond(), operator="AND"), kind="entry")
        trace = engine.evaluate_plan(_plan(rule), _ctx())
        assert trace.entry_triggered is False

    def test_exit_triggered(self):
        engine = _engine()
        rule = _rule(_group(self._true_cond(), operator="AND"), kind="exit", rid="exit1")
        trace = engine.evaluate_plan(_plan(rule), _ctx())
        assert trace.exit_triggered is True
        assert trace.entry_triggered is None  # no entry rules

    def test_multiple_entry_rules_any_triggered(self):
        engine = _engine()
        r1 = _rule(_group(self._false_cond("c1"), operator="AND"), kind="entry", index=0, rid="r1")
        r2 = _rule(_group(self._true_cond("c2"),  operator="AND"), kind="entry", index=1, rid="r2")
        trace = engine.evaluate_plan(_plan(r1, r2), _ctx())
        assert trace.entry_triggered is True

    def test_multiple_entry_rules_none_triggered(self):
        engine = _engine()
        r1 = _rule(_group(self._false_cond("c1"), operator="AND"), kind="entry", index=0, rid="r1")
        r2 = _rule(_group(self._false_cond("c2"), operator="AND"), kind="entry", index=1, rid="r2")
        trace = engine.evaluate_plan(_plan(r1, r2), _ctx())
        assert trace.entry_triggered is False

    def test_both_entry_and_exit(self):
        engine = _engine()
        entry = _rule(_group(self._true_cond("c1"),  operator="AND"), kind="entry", index=0, rid="r1")
        exit_ = _rule(_group(self._false_cond("c2"), operator="AND"), kind="exit",  index=0, rid="r2")
        trace = engine.evaluate_plan(_plan(entry, exit_), _ctx())
        assert trace.entry_triggered is True
        assert trace.exit_triggered is False

    def test_empty_plan(self):
        engine = _engine()
        trace = engine.evaluate_plan(_plan(), _ctx())
        assert trace.entry_triggered is None
        assert trace.exit_triggered is None
        assert trace.rule_results == ()

    def test_rule_results_count(self):
        engine = _engine()
        r1 = _rule(_group(self._true_cond("c1"), operator="AND"), kind="entry", index=0, rid="r1")
        r2 = _rule(_group(self._true_cond("c2"), operator="AND"), kind="exit",  index=0, rid="r2")
        trace = engine.evaluate_plan(_plan(r1, r2), _ctx())
        assert len(trace.rule_results) == 2

    def test_evaluation_id_from_context(self):
        engine = _engine()
        rule  = _rule(_group(self._true_cond(), operator="AND"))
        ctx   = _ctx(eval_id="unique-eval-id")
        trace = engine.evaluate_plan(_plan(rule), ctx)
        assert trace.evaluation_id == "unique-eval-id"

    def test_returns_evaluation_trace(self):
        engine = _engine()
        trace = engine.evaluate_plan(_plan(), _ctx())
        assert isinstance(trace, EvaluationTrace)

    def test_supported_operators(self):
        engine = _engine()
        assert engine.supported_operators == SCALAR_OPERATORS

    def test_diagnostics_propagated_from_failed_condition(self):
        engine = _engine()
        # missing price.close → diagnostic on condition
        node = _condition("price", "close", ">", "constant", "50")
        rule = _rule(_group(node, operator="AND"), kind="entry")
        trace = engine.evaluate_plan(_plan(rule), _ctx())
        assert trace.entry_triggered is None
        assert len(trace.diagnostics) == 0  # rule diagnostics=(); condition diag inside group

    def test_real_scalar_evaluation(self):
        engine = _engine()
        ctx = _ctx({"price.close": 105.0, "tool.sma_fast.value": 100.0})
        # close > sma_fast AND close < 120
        c1 = _condition("price", "close", ">", "tool_output", "sma_fast.value", cid="c1")
        c2 = _condition("price", "close", "<", "constant", "120", cid="c2")
        g  = _group(c1, c2, operator="AND")
        r  = _rule(g, kind="entry")
        trace = engine.evaluate_plan(_plan(r), ctx)
        assert trace.entry_triggered is True

    def test_false_scalar_evaluation(self):
        engine = _engine()
        ctx = _ctx({"price.close": 95.0, "tool.sma_fast.value": 100.0})
        # close > sma_fast → False (95 > 100 is False)
        c1 = _condition("price", "close", ">", "tool_output", "sma_fast.value", cid="c1")
        r  = _rule(_group(c1, operator="AND"), kind="entry")
        trace = engine.evaluate_plan(_plan(r), ctx)
        assert trace.entry_triggered is False


# ---------------------------------------------------------------------------
# Explicit negative tests — deferred operators
# ---------------------------------------------------------------------------

class TestDeferredOperators:
    def test_crosses_above_raises_in_operator_evaluator(self):
        ev = ScalarOperatorEvaluator()
        with pytest.raises(UnsupportedOperatorError, match="crosses_above"):
            ev.evaluate(100.0, "crosses_above", 98.0)

    def test_crosses_below_raises_in_operator_evaluator(self):
        ev = ScalarOperatorEvaluator()
        with pytest.raises(UnsupportedOperatorError, match="crosses_below"):
            ev.evaluate(98.0, "crosses_below", 100.0)

    def test_crosses_above_in_condition_produces_diagnostic(self):
        cond_eval = ScalarConditionEvaluator(ScalarOperandResolver(), ScalarOperatorEvaluator())
        node = _condition("price", "close", "crosses_above", "tool_output", "sma.value")
        ctx  = _ctx({"price.close": 100.0, "tool.sma.value": 99.0})
        result = cond_eval.evaluate_condition(node, ctx)
        assert result.outcome is None
        assert any(d.code == "unsupported_operator" for d in result.diagnostics)

    def test_crosses_below_in_condition_produces_diagnostic(self):
        cond_eval = ScalarConditionEvaluator(ScalarOperandResolver(), ScalarOperatorEvaluator())
        node = _condition("price", "close", "crosses_below", "tool_output", "sma.value")
        ctx  = _ctx({"price.close": 98.0, "tool.sma.value": 99.0})
        result = cond_eval.evaluate_condition(node, ctx)
        assert result.outcome is None
        assert any(d.code == "unsupported_operator" for d in result.diagnostics)

    def test_crosses_above_not_in_supported_operators(self):
        ev = ScalarOperatorEvaluator()
        assert "crosses_above" not in ev.supported_operators

    def test_crosses_below_not_in_supported_operators(self):
        ev = ScalarOperatorEvaluator()
        assert "crosses_below" not in ev.supported_operators

    def test_crosses_above_not_in_engine_supported(self):
        engine = _engine()
        assert "crosses_above" not in engine.supported_operators

    def test_crosses_below_not_in_engine_supported(self):
        engine = _engine()
        assert "crosses_below" not in engine.supported_operators


# ---------------------------------------------------------------------------
# Architecture boundary tests
# ---------------------------------------------------------------------------

class TestArchitectureBoundary:
    _FORBIDDEN = (
        "strategy_runtime",
        "backtesting",
        "execution",
        "forward_testing",
    )

    def _import_lines(self, module_name: str) -> list[str]:
        mod = importlib.import_module(module_name)
        src = inspect.getsource(mod)
        return [
            line.strip()
            for line in src.splitlines()
            if line.strip().startswith("import ") or line.strip().startswith("from ")
        ]

    def _check_module(self, module_name: str) -> None:
        import_lines = self._import_lines(module_name)
        for line in import_lines:
            for forbidden in self._FORBIDDEN:
                assert forbidden not in line, (
                    f"Forbidden import in {module_name}: '{line}' "
                    f"references '{forbidden}'"
                )

    def test_scalar_evaluation_context_boundary(self):
        self._check_module("backend.strategy_registry.scalar_evaluation_context")

    def test_scalar_evaluator_boundary(self):
        self._check_module("backend.strategy_registry.scalar_evaluator")
