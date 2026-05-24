"""
Phase 2O.6 — Evaluator Contract Architecture tests.

Covers:
- EvaluationDiagnostic frozen Pydantic model
- ConditionEvaluationResult structure and serialization
- GroupEvaluationResult recursive structure
- RuleEvaluationResult structure
- EvaluationTrace structure
- EvaluationContext ABC cannot be instantiated directly
- OperandResolver ABC cannot be instantiated directly
- OperatorEvaluator ABC cannot be instantiated directly
- ConditionEvaluator ABC cannot be instantiated directly
- GroupEvaluator ABC cannot be instantiated directly
- RuleEvaluator ABC cannot be instantiated directly
- EvaluationEngineContract ABC cannot be instantiated directly
- Concrete implementations of all ABCs are valid
- EvaluationContextDescriptor structure
- EvaluationRequirements structure
- ContextSatisfactionReport: satisfied and unsatisfied cases
- extract_requirements() pure function
- check_context_satisfaction() pure function
- TraversalContext frozen Pydantic model
- PlanNodeVisitor ABC cannot be instantiated directly
- traverse_plan() visits all nodes in correct order
- traverse_plan() depth tracking for nested groups
- Architecture boundaries: no runtime imports in any contract module
- Generic contract: no SMA/RSI/indicator-specific symbols in contract modules
"""
from __future__ import annotations

import importlib
import inspect

import pytest

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
from backend.strategy_registry.evaluation_context import (
    ContextSatisfactionReport,
    EvaluationContextDescriptor,
    EvaluationRequirements,
    check_context_satisfaction,
    extract_requirements,
)
from backend.strategy_registry.plan_visitor import (
    PlanNodeVisitor,
    TraversalContext,
    traverse_plan,
)
from backend.strategy_registry.semantic_plan import (
    ConditionGroupPlanNode,
    ConditionPlanNode,
    DependencySet,
    EvaluationPlan,
    RulePlanNode,
)

from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Helpers — plan node factories
# ---------------------------------------------------------------------------

def _make_condition_node(condition_id: str = "c1") -> ConditionPlanNode:
    return ConditionPlanNode(
        condition_id=condition_id,
        left_kind="price",
        left_ref="close",
        operator=">",
        right_kind="constant",
        right_ref="30",
        label=None,
    )

def _make_group_node(
    *nodes: ConditionPlanNode | ConditionGroupPlanNode,
    group_id: str = "g1",
) -> ConditionGroupPlanNode:
    return ConditionGroupPlanNode(
        group_id=group_id,
        operator="AND",
        nodes=nodes or (_make_condition_node(),),
        label=None,
    )

def _make_rule_node(
    kind: str = "entry",
    index: int = 0,
    rule_id: str = "r1",
) -> RulePlanNode:
    return RulePlanNode(
        rule_id=rule_id,
        kind=kind,
        index=index,
        label=None,
        condition_group=_make_group_node(),
    )

def _make_plan(
    *rule_nodes: RulePlanNode,
    draft_id: str | None = "draft-test",
) -> EvaluationPlan:
    return EvaluationPlan(
        draft_id=draft_id,
        semantic_version="1.0",
        rule_nodes=rule_nodes or (_make_rule_node(),),
        dependencies=DependencySet(
            tool_outputs=(),
            price_fields=("close",),
            constants=("30",),
        ),
        diagnostics=(),
        node_count=1,
        compiled_at=datetime.now(tz=timezone.utc),
    )

# ---------------------------------------------------------------------------
# Minimal concrete implementations for ABC tests
# ---------------------------------------------------------------------------

class _ConcreteContext(EvaluationContext):
    @property
    def evaluation_id(self) -> str: return "test-eval"
    @property
    def available_tool_instances(self) -> tuple[str, ...]: return ("sma_fast",)
    @property
    def available_price_fields(self) -> tuple[str, ...]: return ("close",)
    def resolve_tool_output(self, instance_id: str, output_name: str) -> ResolvedValue: return 42.0
    def resolve_price_field(self, field: str) -> ResolvedValue: return 100.0
    def resolve_constant(self, ref: str) -> ResolvedValue: return float(ref)


class _ConcreteOperandResolver(OperandResolver):
    def resolve(self, kind: str, ref: str, context: EvaluationContext) -> ResolvedValue:
        if kind == "constant":
            return context.resolve_constant(ref)
        if kind == "price":
            return context.resolve_price_field(ref)
        instance_id, output_name = ref.split(".", 1)
        return context.resolve_tool_output(instance_id, output_name)


class _ConcreteOperatorEvaluator(OperatorEvaluator):
    @property
    def supported_operators(self) -> frozenset[str]:
        return frozenset({">", "<", ">=", "<=", "==", "!=", "crosses_above", "crosses_below"})

    def evaluate(self, left: ResolvedValue, operator: str, right: ResolvedValue) -> bool | None:
        if operator == ">":  return left > right
        if operator == "<":  return left < right
        if operator == ">=": return left >= right
        if operator == "<=": return left <= right
        if operator == "==": return left == right
        if operator == "!=": return left != right
        return None


def _make_condition_result(cid: str = "c1", outcome: bool | None = True) -> ConditionEvaluationResult:
    return ConditionEvaluationResult(condition_id=cid, outcome=outcome, diagnostics=())


def _make_group_result(gid: str = "g1", outcome: bool | None = True) -> GroupEvaluationResult:
    return GroupEvaluationResult(
        group_id=gid,
        outcome=outcome,
        child_results=(_make_condition_result(),),
        diagnostics=(),
    )


class _ConcreteConditionEvaluator(ConditionEvaluator):
    def evaluate_condition(self, node, context) -> ConditionEvaluationResult:
        return _make_condition_result(node.condition_id)


class _ConcreteGroupEvaluator(GroupEvaluator):
    def evaluate_group(self, node, context) -> GroupEvaluationResult:
        return _make_group_result(node.group_id)


class _ConcreteRuleEvaluator(RuleEvaluator):
    def evaluate_rule(self, node, context) -> RuleEvaluationResult:
        return RuleEvaluationResult(
            rule_id=node.rule_id,
            kind=node.kind,
            index=node.index,
            triggered=True,
            group_result=_make_group_result(),
            diagnostics=(),
        )


class _ConcreteEngine(EvaluationEngineContract):
    @property
    def supported_operators(self) -> frozenset[str]:
        return frozenset({">", "<", ">=", "<=", "==", "!="})

    def evaluate_plan(self, plan, context) -> EvaluationTrace:
        return EvaluationTrace(
            plan_draft_id=plan.draft_id,
            evaluation_id="test",
            rule_results=(),
            diagnostics=(),
        )


class _CountingVisitor(PlanNodeVisitor):
    """Visitor that counts nodes visited."""
    def __init__(self):
        self.conditions_visited = []
        self.groups_visited = []
        self.rules_visited = []

    def visit_condition_node(self, node, context):
        self.conditions_visited.append(node.condition_id)
        return f"cond:{node.condition_id}"

    def visit_group_node(self, node, child_results, context):
        self.groups_visited.append(node.group_id)
        return f"group:{node.group_id}:{child_results}"

    def visit_rule_node(self, node, group_result, context):
        self.rules_visited.append(node.rule_id)
        return f"rule:{node.rule_id}"

# ---------------------------------------------------------------------------
# Tests — EvaluationDiagnostic
# ---------------------------------------------------------------------------

class TestEvaluationDiagnostic:
    def test_creates_with_all_fields(self):
        d = EvaluationDiagnostic(
            severity="error",
            code="unresolved_operand",
            reference="sma_fast.sma",
            message="could not resolve",
        )
        assert d.severity == "error"
        assert d.code == "unresolved_operand"
        assert d.reference == "sma_fast.sma"

    def test_optional_fields_default_none(self):
        d = EvaluationDiagnostic(
            severity="warning",
            code="context_unavailable",
            reference="close",
            message="x",
        )
        assert d.rule_id is None
        assert d.condition_id is None

    def test_with_optional_fields(self):
        d = EvaluationDiagnostic(
            severity="info",
            code="ok",
            reference="ref",
            message="m",
            rule_id="r1",
            condition_id="c1",
        )
        assert d.rule_id == "r1"
        assert d.condition_id == "c1"

    def test_frozen(self):
        d = EvaluationDiagnostic(severity="error", code="x", reference="y", message="z")
        with pytest.raises(Exception):
            d.code = "mutated"

    def test_json_serializable(self):
        d = EvaluationDiagnostic(severity="error", code="x", reference="y", message="z")
        data = d.model_dump()
        assert data["severity"] == "error"

# ---------------------------------------------------------------------------
# Tests — ConditionEvaluationResult
# ---------------------------------------------------------------------------

class TestConditionEvaluationResult:
    def test_true_outcome(self):
        r = ConditionEvaluationResult(condition_id="c1", outcome=True, diagnostics=())
        assert r.outcome is True

    def test_false_outcome(self):
        r = ConditionEvaluationResult(condition_id="c1", outcome=False, diagnostics=())
        assert r.outcome is False

    def test_none_outcome_indeterminate(self):
        r = ConditionEvaluationResult(condition_id="c1", outcome=None, diagnostics=())
        assert r.outcome is None

    def test_none_condition_id(self):
        r = ConditionEvaluationResult(condition_id=None, outcome=True, diagnostics=())
        assert r.condition_id is None

    def test_frozen(self):
        r = ConditionEvaluationResult(condition_id="c1", outcome=True, diagnostics=())
        with pytest.raises(Exception):
            r.outcome = False

    def test_with_diagnostics(self):
        diag = EvaluationDiagnostic(severity="warning", code="x", reference="y", message="m")
        r = ConditionEvaluationResult(condition_id="c1", outcome=None, diagnostics=(diag,))
        assert len(r.diagnostics) == 1

# ---------------------------------------------------------------------------
# Tests — GroupEvaluationResult (recursive)
# ---------------------------------------------------------------------------

class TestGroupEvaluationResult:
    def test_basic_structure(self):
        child = _make_condition_result()
        g = GroupEvaluationResult(group_id="g1", outcome=True, child_results=(child,), diagnostics=())
        assert g.outcome is True
        assert len(g.child_results) == 1

    def test_recursive_nesting(self):
        child_condition = _make_condition_result("c1")
        inner_group = GroupEvaluationResult(
            group_id="g-inner",
            outcome=True,
            child_results=(child_condition,),
            diagnostics=(),
        )
        outer_group = GroupEvaluationResult(
            group_id="g-outer",
            outcome=True,
            child_results=(child_condition, inner_group),
            diagnostics=(),
        )
        assert outer_group.group_id == "g-outer"
        assert len(outer_group.child_results) == 2

    def test_frozen(self):
        g = _make_group_result()
        with pytest.raises(Exception):
            g.outcome = False

    def test_none_outcome(self):
        g = GroupEvaluationResult(
            group_id="g1", outcome=None, child_results=(), diagnostics=()
        )
        assert g.outcome is None

# ---------------------------------------------------------------------------
# Tests — RuleEvaluationResult
# ---------------------------------------------------------------------------

class TestRuleEvaluationResult:
    def test_entry_rule_triggered(self):
        r = RuleEvaluationResult(
            rule_id="r1",
            kind="entry",
            index=0,
            triggered=True,
            group_result=_make_group_result(),
            diagnostics=(),
        )
        assert r.triggered is True
        assert r.kind == "entry"

    def test_exit_rule_not_triggered(self):
        r = RuleEvaluationResult(
            rule_id="r2",
            kind="exit",
            index=1,
            triggered=False,
            group_result=_make_group_result(outcome=False),
            diagnostics=(),
        )
        assert r.triggered is False
        assert r.kind == "exit"

    def test_frozen(self):
        r = RuleEvaluationResult(
            rule_id="r1", kind="entry", index=0, triggered=True,
            group_result=_make_group_result(), diagnostics=(),
        )
        with pytest.raises(Exception):
            r.triggered = False

# ---------------------------------------------------------------------------
# Tests — EvaluationTrace
# ---------------------------------------------------------------------------

class TestEvaluationTrace:
    def test_basic_structure(self):
        t = EvaluationTrace(
            plan_draft_id="draft-1",
            evaluation_id="eval-abc",
            rule_results=(),
            diagnostics=(),
        )
        assert t.evaluation_id == "eval-abc"
        assert t.entry_triggered is None
        assert t.exit_triggered is None

    def test_with_trigger_flags(self):
        t = EvaluationTrace(
            plan_draft_id="draft-1",
            evaluation_id="eval-abc",
            rule_results=(),
            diagnostics=(),
            entry_triggered=True,
            exit_triggered=False,
        )
        assert t.entry_triggered is True
        assert t.exit_triggered is False

    def test_frozen(self):
        t = EvaluationTrace(plan_draft_id=None, evaluation_id="x", rule_results=(), diagnostics=())
        with pytest.raises(Exception):
            t.evaluation_id = "mutated"

    def test_none_draft_id(self):
        t = EvaluationTrace(plan_draft_id=None, evaluation_id="x", rule_results=(), diagnostics=())
        assert t.plan_draft_id is None

# ---------------------------------------------------------------------------
# Tests — ABCs cannot be instantiated directly
# ---------------------------------------------------------------------------

class TestAbstractsCannotInstantiate:
    def test_evaluation_context_abstract(self):
        with pytest.raises(TypeError):
            EvaluationContext()  # type: ignore

    def test_operand_resolver_abstract(self):
        with pytest.raises(TypeError):
            OperandResolver()  # type: ignore

    def test_operator_evaluator_abstract(self):
        with pytest.raises(TypeError):
            OperatorEvaluator()  # type: ignore

    def test_condition_evaluator_abstract(self):
        with pytest.raises(TypeError):
            ConditionEvaluator()  # type: ignore

    def test_group_evaluator_abstract(self):
        with pytest.raises(TypeError):
            GroupEvaluator()  # type: ignore

    def test_rule_evaluator_abstract(self):
        with pytest.raises(TypeError):
            RuleEvaluator()  # type: ignore

    def test_evaluation_engine_abstract(self):
        with pytest.raises(TypeError):
            EvaluationEngineContract()  # type: ignore

    def test_plan_node_visitor_abstract(self):
        with pytest.raises(TypeError):
            PlanNodeVisitor()  # type: ignore

# ---------------------------------------------------------------------------
# Tests — concrete implementations satisfy ABC contracts
# ---------------------------------------------------------------------------

class TestConcreteImplementations:
    def test_concrete_context_instantiates(self):
        ctx = _ConcreteContext()
        assert ctx.evaluation_id == "test-eval"
        assert "sma_fast" in ctx.available_tool_instances
        assert ctx.resolve_price_field("close") == 100.0
        assert ctx.resolve_constant("30") == 30.0
        assert ctx.resolve_tool_output("sma_fast", "sma") == 42.0

    def test_concrete_operand_resolver(self):
        resolver = _ConcreteOperandResolver()
        ctx = _ConcreteContext()
        assert resolver.resolve("price", "close", ctx) == 100.0
        assert resolver.resolve("constant", "30", ctx) == 30.0
        assert resolver.resolve("tool_output", "sma_fast.sma", ctx) == 42.0

    def test_concrete_operator_evaluator_supported(self):
        op = _ConcreteOperatorEvaluator()
        assert ">" in op.supported_operators
        assert "crosses_above" in op.supported_operators
        assert len(op.supported_operators) == 8

    def test_concrete_operator_evaluator_gt(self):
        op = _ConcreteOperatorEvaluator()
        assert op.evaluate(50.0, ">", 30.0) is True
        assert op.evaluate(20.0, ">", 30.0) is False

    def test_concrete_operator_evaluator_lt(self):
        op = _ConcreteOperatorEvaluator()
        assert op.evaluate(20.0, "<", 30.0) is True

    def test_concrete_operator_evaluator_eq(self):
        op = _ConcreteOperatorEvaluator()
        assert op.evaluate(30.0, "==", 30.0) is True
        assert op.evaluate(30.0, "!=", 30.0) is False

    def test_concrete_operator_evaluator_unsupported_returns_none(self):
        op = _ConcreteOperatorEvaluator()
        assert op.evaluate(1.0, "crosses_above", 0.5) is None

    def test_concrete_condition_evaluator(self):
        evaluator = _ConcreteConditionEvaluator()
        node = _make_condition_node("c-test")
        ctx = _ConcreteContext()
        result = evaluator.evaluate_condition(node, ctx)
        assert isinstance(result, ConditionEvaluationResult)
        assert result.condition_id == "c-test"

    def test_concrete_group_evaluator(self):
        evaluator = _ConcreteGroupEvaluator()
        node = _make_group_node(group_id="g-test")
        ctx = _ConcreteContext()
        result = evaluator.evaluate_group(node, ctx)
        assert isinstance(result, GroupEvaluationResult)
        assert result.group_id == "g-test"

    def test_concrete_rule_evaluator(self):
        evaluator = _ConcreteRuleEvaluator()
        node = _make_rule_node(kind="entry", rule_id="r-test")
        ctx = _ConcreteContext()
        result = evaluator.evaluate_rule(node, ctx)
        assert isinstance(result, RuleEvaluationResult)
        assert result.triggered is True
        assert result.kind == "entry"

    def test_concrete_engine(self):
        engine = _ConcreteEngine()
        plan = _make_plan()
        ctx = _ConcreteContext()
        trace = engine.evaluate_plan(plan, ctx)
        assert isinstance(trace, EvaluationTrace)
        assert ">" in engine.supported_operators

# ---------------------------------------------------------------------------
# Tests — EvaluationContextDescriptor
# ---------------------------------------------------------------------------

class TestEvaluationContextDescriptor:
    def test_basic_structure(self):
        d = EvaluationContextDescriptor(
            evaluation_id="eval-1",
            declared_tool_outputs=("sma_fast.sma",),
            declared_price_fields=("close",),
            declared_constants=("30",),
        )
        assert d.evaluation_id == "eval-1"
        assert "sma_fast.sma" in d.declared_tool_outputs

    def test_optional_draft_id(self):
        d = EvaluationContextDescriptor(
            evaluation_id="x",
            declared_tool_outputs=(),
            declared_price_fields=(),
            declared_constants=(),
        )
        assert d.plan_draft_id is None

    def test_frozen(self):
        d = EvaluationContextDescriptor(
            evaluation_id="x",
            declared_tool_outputs=(),
            declared_price_fields=(),
            declared_constants=(),
        )
        with pytest.raises(Exception):
            d.evaluation_id = "mutated"

# ---------------------------------------------------------------------------
# Tests — extract_requirements and check_context_satisfaction
# ---------------------------------------------------------------------------

class TestContextSatisfaction:
    def _make_dep_set(
        self,
        tool_outputs=(),
        price_fields=(),
        constants=(),
    ) -> "DependencySet":
        return DependencySet(
            tool_outputs=tool_outputs,
            price_fields=price_fields,
            constants=constants,
        )

    def test_extract_requirements_maps_dependency_set(self):
        dep = self._make_dep_set(
            tool_outputs=("sma_fast.sma",),
            price_fields=("close",),
            constants=("30",),
        )
        req = extract_requirements(dep)
        assert req.required_tool_outputs == ("sma_fast.sma",)
        assert req.required_price_fields == ("close",)
        assert req.required_constants == ("30",)

    def test_extract_requirements_empty_dependency_set(self):
        dep = self._make_dep_set()
        req = extract_requirements(dep)
        assert req.required_tool_outputs == ()
        assert req.required_price_fields == ()
        assert req.required_constants == ()

    def test_satisfaction_check_satisfied(self):
        req = EvaluationRequirements(
            required_tool_outputs=("sma_fast.sma",),
            required_price_fields=("close",),
            required_constants=("30",),
        )
        descriptor = EvaluationContextDescriptor(
            evaluation_id="e1",
            declared_tool_outputs=("sma_fast.sma",),
            declared_price_fields=("close",),
            declared_constants=("30",),
        )
        report = check_context_satisfaction(req, descriptor)
        assert report.satisfied is True
        assert report.missing_tool_outputs == ()
        assert report.missing_price_fields == ()
        assert report.missing_constants == ()

    def test_satisfaction_check_missing_tool_output(self):
        req = EvaluationRequirements(
            required_tool_outputs=("rsi.value",),
            required_price_fields=(),
            required_constants=(),
        )
        descriptor = EvaluationContextDescriptor(
            evaluation_id="e1",
            declared_tool_outputs=(),
            declared_price_fields=(),
            declared_constants=(),
        )
        report = check_context_satisfaction(req, descriptor)
        assert report.satisfied is False
        assert "rsi.value" in report.missing_tool_outputs

    def test_satisfaction_check_missing_price_field(self):
        req = EvaluationRequirements(
            required_tool_outputs=(),
            required_price_fields=("close",),
            required_constants=(),
        )
        descriptor = EvaluationContextDescriptor(
            evaluation_id="e1",
            declared_tool_outputs=(),
            declared_price_fields=(),
            declared_constants=(),
        )
        report = check_context_satisfaction(req, descriptor)
        assert report.satisfied is False
        assert "close" in report.missing_price_fields

    def test_satisfaction_check_partial(self):
        req = EvaluationRequirements(
            required_tool_outputs=("sma_fast.sma", "rsi.rsi"),
            required_price_fields=(),
            required_constants=(),
        )
        descriptor = EvaluationContextDescriptor(
            evaluation_id="e1",
            declared_tool_outputs=("sma_fast.sma",),
            declared_price_fields=(),
            declared_constants=(),
        )
        report = check_context_satisfaction(req, descriptor)
        assert report.satisfied is False
        assert "rsi.rsi" in report.missing_tool_outputs
        assert "sma_fast.sma" not in report.missing_tool_outputs

    def test_satisfaction_check_empty_requirements_satisfied(self):
        req = EvaluationRequirements(
            required_tool_outputs=(),
            required_price_fields=(),
            required_constants=(),
        )
        descriptor = EvaluationContextDescriptor(
            evaluation_id="e1",
            declared_tool_outputs=(),
            declared_price_fields=(),
            declared_constants=(),
        )
        report = check_context_satisfaction(req, descriptor)
        assert report.satisfied is True

# ---------------------------------------------------------------------------
# Tests — TraversalContext
# ---------------------------------------------------------------------------

class TestTraversalContext:
    def test_basic_structure(self):
        ctx = TraversalContext(
            rule_index=0,
            rule_kind="entry",
            rule_id="r1",
            depth=0,
            path="rule[0]",
        )
        assert ctx.depth == 0
        assert ctx.path == "rule[0]"

    def test_frozen(self):
        ctx = TraversalContext(rule_index=0, rule_kind="entry", rule_id=None, depth=0, path="x")
        with pytest.raises(Exception):
            ctx.depth = 99

# ---------------------------------------------------------------------------
# Tests — traverse_plan visitor
# ---------------------------------------------------------------------------

class TestTraversePlan:
    def test_visits_single_rule_single_condition(self):
        plan = _make_plan(_make_rule_node(rule_id="r1"))
        visitor = _CountingVisitor()
        traverse_plan(plan, visitor)
        assert "r1" in visitor.rules_visited
        assert "c1" in visitor.conditions_visited

    def test_visits_multiple_rules(self):
        plan = _make_plan(
            _make_rule_node(kind="entry", index=0, rule_id="r-entry"),
            _make_rule_node(kind="exit",  index=1, rule_id="r-exit"),
        )
        visitor = _CountingVisitor()
        results = traverse_plan(plan, visitor)
        assert "r-entry" in visitor.rules_visited
        assert "r-exit" in visitor.rules_visited
        assert len(results) == 2

    def test_returns_tuple_of_rule_results(self):
        plan = _make_plan(_make_rule_node(rule_id="r1"))
        visitor = _CountingVisitor()
        results = traverse_plan(plan, visitor)
        assert isinstance(results, tuple)
        assert len(results) == 1

    def test_post_order_children_before_parent(self):
        plan = _make_plan(_make_rule_node(rule_id="r1"))
        visit_order = []

        class OrderVisitor(PlanNodeVisitor):
            def visit_condition_node(self, node, ctx):
                visit_order.append(f"cond:{node.condition_id}")
                return None
            def visit_group_node(self, node, child_results, ctx):
                visit_order.append(f"group:{node.group_id}")
                return None
            def visit_rule_node(self, node, group_result, ctx):
                visit_order.append(f"rule:{node.rule_id}")
                return None

        traverse_plan(plan, OrderVisitor())
        # condition and group must come before rule
        cond_i  = next(i for i, x in enumerate(visit_order) if x.startswith("cond"))
        group_i = next(i for i, x in enumerate(visit_order) if x.startswith("group"))
        rule_i  = next(i for i, x in enumerate(visit_order) if x.startswith("rule"))
        assert cond_i < group_i < rule_i

    def test_depth_increments_for_nested_group(self):
        inner_cond  = _make_condition_node("c-inner")
        inner_group = _make_group_node(inner_cond, group_id="g-inner")
        outer_cond  = _make_condition_node("c-outer")
        outer_group = ConditionGroupPlanNode(
            group_id="g-outer",
            operator="AND",
            nodes=(outer_cond, inner_group),
            label=None,
        )
        rule = RulePlanNode(
            rule_id="r1", kind="entry", index=0, label=None,
            condition_group=outer_group,
        )
        plan = _make_plan(rule)

        depths: dict[str, int] = {}

        class DepthVisitor(PlanNodeVisitor):
            def visit_condition_node(self, node, ctx):
                depths[node.condition_id] = ctx.depth
                return None
            def visit_group_node(self, node, child_results, ctx):
                depths[node.group_id] = ctx.depth
                return None
            def visit_rule_node(self, node, group_result, ctx):
                return None

        traverse_plan(plan, DepthVisitor())
        assert depths["g-outer"] == 0
        assert depths["g-inner"] == 1
        assert depths["c-outer"] == 0
        assert depths["c-inner"] == 1

    def test_empty_plan_returns_empty_tuple(self):
        plan = EvaluationPlan(
            draft_id=None,
            semantic_version="1.0",
            rule_nodes=(),
            dependencies=DependencySet(tool_outputs=(), price_fields=(), constants=()),
            diagnostics=(),
            node_count=0,
            compiled_at=datetime.now(tz=timezone.utc),
        )
        visitor = _CountingVisitor()
        results = traverse_plan(plan, visitor)
        assert results == ()
        assert visitor.rules_visited == []

# ---------------------------------------------------------------------------
# Tests — architecture boundary
# ---------------------------------------------------------------------------

class TestArchitectureBoundary:
    def _import_lines(self, module_name: str) -> list[str]:
        mod = importlib.import_module(module_name)
        return [
            line.strip()
            for line in inspect.getsource(mod).splitlines()
            if line.strip().startswith(("import ", "from "))
        ]

    def _check_module(self, module_name: str, forbidden: str) -> None:
        for line in self._import_lines(module_name):
            assert forbidden not in line, (
                f"Architecture violation in {module_name}: "
                f"'{forbidden}' found in import line: {line!r}"
            )

    MODULES = [
        "backend.strategy_registry.evaluator_contracts",
        "backend.strategy_registry.evaluation_context",
        "backend.strategy_registry.plan_visitor",
    ]
    FORBIDDEN = [
        "strategy_runtime",
        "backtesting",
        "backend.execution",
        "forward_testing",
    ]

    def test_no_strategy_runtime_import(self):
        for mod in self.MODULES:
            self._check_module(mod, "strategy_runtime")

    def test_no_backtesting_import(self):
        for mod in self.MODULES:
            self._check_module(mod, "backtesting")

    def test_no_execution_import(self):
        for mod in self.MODULES:
            self._check_module(mod, "backend.execution")

    def test_no_forward_testing_import(self):
        for mod in self.MODULES:
            self._check_module(mod, "forward_testing")

# ---------------------------------------------------------------------------
# Tests — generic contract (no indicator-specific symbols)
# ---------------------------------------------------------------------------

class TestGenericContracts:
    def _source(self, module_name: str) -> str:
        import backend.strategy_registry.evaluator_contracts as ec
        import backend.strategy_registry.plan_visitor as pv
        import backend.strategy_registry.evaluation_context as ctx_mod
        mods = {
            "backend.strategy_registry.evaluator_contracts": ec,
            "backend.strategy_registry.plan_visitor": pv,
            "backend.strategy_registry.evaluation_context": ctx_mod,
        }
        return inspect.getsource(mods[module_name])

    def test_evaluator_contracts_no_sma(self):
        src = self._source("backend.strategy_registry.evaluator_contracts")
        assert "SMA" not in src and "sma" not in src.lower().split("# sma")[0][:100]

    def test_evaluator_contracts_no_rsi(self):
        src = self._source("backend.strategy_registry.evaluator_contracts")
        assert "RSI" not in src

    def test_plan_visitor_no_sma(self):
        src = self._source("backend.strategy_registry.plan_visitor")
        assert "SMA" not in src

    def test_plan_visitor_no_rsi(self):
        src = self._source("backend.strategy_registry.plan_visitor")
        assert "RSI" not in src

    def test_evaluation_context_no_sma(self):
        src = self._source("backend.strategy_registry.evaluation_context")
        assert "SMA" not in src

    def test_evaluation_context_no_rsi(self):
        src = self._source("backend.strategy_registry.evaluation_context")
        assert "RSI" not in src

    def test_operator_contract_declares_all_eight_operators(self):
        op = _ConcreteOperatorEvaluator()
        expected = {">", "<", ">=", "<=", "==", "!=", "crosses_above", "crosses_below"}
        assert expected == op.supported_operators

    def test_resolved_value_is_any(self):
        from backend.strategy_registry.evaluator_contracts import ResolvedValue
        from typing import Any
        assert ResolvedValue is Any
