"""
Phase 2O.7 — Plan Inspector domain tests.

Covers:
- inspect_plan() basic output shape
- topology: entry/exit rule counts
- topology: condition node counts
- topology: group node counts
- topology: max nesting depth (flat = 0, one level = 1)
- topology: operator usage counts
- topology: unique_operators sorted
- dependency inspection: tool_outputs, price_fields, constants counts + values
- diagnostics summary: error/warning/info counts
- diagnostics summary: messages tuple
- rule summaries: rule_id, kind, index preservation
- rule summaries: per-rule condition and group counts
- rule summaries: per-rule max_nesting_depth
- rule summaries: per-rule operators_used sorted
- determinism: identical plans → identical summaries
- empty plan (no rules): all counts zero
- multiple rules: aggregation correct
- nested groups: depth tracking
- architecture boundary: no runtime imports
"""
from __future__ import annotations

import importlib
import inspect
from datetime import datetime, timezone

import pytest

from backend.strategy_registry.plan_inspector import (
    DiagnosticsSummary,
    EvaluationPlanSummary,
    RuleNodeSummary,
    TopologySummary,
    inspect_plan,
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
# Plan node factories
# ---------------------------------------------------------------------------

def _cond(
    condition_id: str = "c1",
    operator: str = ">",
    left_kind: str = "price",
    left_ref: str = "close",
    right_kind: str = "constant",
    right_ref: str = "30",
) -> ConditionPlanNode:
    return ConditionPlanNode(
        condition_id=condition_id,
        left_kind=left_kind,
        left_ref=left_ref,
        operator=operator,
        right_kind=right_kind,
        right_ref=right_ref,
        label=None,
    )


def _group(
    *nodes: ConditionPlanNode | ConditionGroupPlanNode,
    group_id: str = "g1",
    operator: str = "AND",
) -> ConditionGroupPlanNode:
    return ConditionGroupPlanNode(
        group_id=group_id,
        operator=operator,
        nodes=nodes or (_cond(),),
        label=None,
    )


def _rule(
    kind: str = "entry",
    index: int = 0,
    rule_id: str = "r1",
    condition_group: ConditionGroupPlanNode | None = None,
) -> RulePlanNode:
    return RulePlanNode(
        rule_id=rule_id,
        kind=kind,
        index=index,
        label=None,
        condition_group=condition_group or _group(),
    )


def _plan(
    *rules: RulePlanNode,
    tool_outputs: tuple[str, ...] = (),
    price_fields: tuple[str, ...] = (),
    constants: tuple[str, ...] = (),
    diagnostics: tuple[CompilationDiagnostic, ...] = (),
    draft_id: str | None = "draft-test",
) -> EvaluationPlan:
    return EvaluationPlan(
        draft_id=draft_id,
        semantic_version="1.0",
        rule_nodes=rules or (_rule(),),
        dependencies=DependencySet(
            tool_outputs=tool_outputs,
            price_fields=price_fields,
            constants=constants,
        ),
        diagnostics=diagnostics,
        node_count=sum(1 for _ in rules),
        compiled_at=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Tests — basic output shape
# ---------------------------------------------------------------------------

class TestBasicShape:
    def test_returns_evaluation_plan_summary(self):
        result = inspect_plan(_plan(_rule()))
        assert isinstance(result, EvaluationPlanSummary)

    def test_draft_id_preserved(self):
        result = inspect_plan(_plan(_rule(), draft_id="my-draft"))
        assert result.draft_id == "my-draft"

    def test_draft_id_none(self):
        result = inspect_plan(_plan(_rule(), draft_id=None))
        assert result.draft_id is None

    def test_semantic_version_preserved(self):
        result = inspect_plan(_plan(_rule()))
        assert result.semantic_version == "1.0"

    def test_has_topology(self):
        result = inspect_plan(_plan(_rule()))
        assert isinstance(result.topology, TopologySummary)

    def test_has_rules_tuple(self):
        result = inspect_plan(_plan(_rule()))
        assert isinstance(result.rules, tuple)


# ---------------------------------------------------------------------------
# Tests — topology: rule counts
# ---------------------------------------------------------------------------

class TestTopologyRuleCounts:
    def test_single_entry_rule(self):
        result = inspect_plan(_plan(_rule(kind="entry")))
        assert result.topology.entry_rule_count == 1
        assert result.topology.exit_rule_count == 0

    def test_single_exit_rule(self):
        result = inspect_plan(_plan(_rule(kind="exit")))
        assert result.topology.entry_rule_count == 0
        assert result.topology.exit_rule_count == 1

    def test_two_entry_one_exit(self):
        plan = _plan(
            _rule(kind="entry", index=0, rule_id="r1"),
            _rule(kind="entry", index=1, rule_id="r2"),
            _rule(kind="exit",  index=2, rule_id="r3"),
        )
        result = inspect_plan(plan)
        assert result.topology.entry_rule_count == 2
        assert result.topology.exit_rule_count == 1

    def test_total_rules(self):
        plan = _plan(
            _rule(kind="entry", index=0, rule_id="r1"),
            _rule(kind="exit",  index=1, rule_id="r2"),
        )
        result = inspect_plan(plan)
        assert result.total_rules == 2


# ---------------------------------------------------------------------------
# Tests — topology: condition and group node counts
# ---------------------------------------------------------------------------

class TestNodeCounts:
    def test_single_condition(self):
        result = inspect_plan(_plan(_rule(condition_group=_group(_cond("c1")))))
        assert result.topology.total_condition_nodes == 1

    def test_two_conditions_flat(self):
        grp = _group(_cond("c1"), _cond("c2"))
        result = inspect_plan(_plan(_rule(condition_group=grp)))
        assert result.topology.total_condition_nodes == 2

    def test_nested_group_condition_count(self):
        inner = _group(_cond("c-inner"), group_id="g-inner")
        outer = _group(_cond("c-outer"), inner, group_id="g-outer")
        result = inspect_plan(_plan(_rule(condition_group=outer)))
        assert result.topology.total_condition_nodes == 2

    def test_group_count_flat(self):
        grp = _group(_cond("c1"), _cond("c2"), group_id="g1")
        result = inspect_plan(_plan(_rule(condition_group=grp)))
        assert result.topology.total_group_nodes == 1

    def test_group_count_nested(self):
        inner = _group(_cond("c-inner"), group_id="g-inner")
        outer = _group(_cond("c-outer"), inner, group_id="g-outer")
        result = inspect_plan(_plan(_rule(condition_group=outer)))
        assert result.topology.total_group_nodes == 2

    def test_two_rules_conditions_aggregated(self):
        r1 = _rule(kind="entry", index=0, rule_id="r1",
                   condition_group=_group(_cond("c1"), _cond("c2"), group_id="g1"))
        r2 = _rule(kind="exit",  index=1, rule_id="r2",
                   condition_group=_group(_cond("c3"), group_id="g2"))
        result = inspect_plan(_plan(r1, r2))
        assert result.topology.total_condition_nodes == 3


# ---------------------------------------------------------------------------
# Tests — topology: nesting depth
# ---------------------------------------------------------------------------

class TestNestingDepth:
    def test_flat_plan_depth_zero(self):
        result = inspect_plan(_plan(_rule(condition_group=_group(_cond()))))
        assert result.topology.max_nesting_depth == 0

    def test_one_level_nesting_depth_one(self):
        inner = _group(_cond("c-inner"), group_id="g-inner")
        outer = _group(_cond("c-outer"), inner, group_id="g-outer")
        result = inspect_plan(_plan(_rule(condition_group=outer)))
        assert result.topology.max_nesting_depth == 1

    def test_two_level_nesting_depth_two(self):
        level3 = _group(_cond("c3"), group_id="g3")
        level2 = _group(_cond("c2"), level3, group_id="g2")
        level1 = _group(_cond("c1"), level2, group_id="g1")
        result = inspect_plan(_plan(_rule(condition_group=level1)))
        assert result.topology.max_nesting_depth == 2

    def test_max_depth_across_rules(self):
        flat_rule   = _rule(kind="entry", index=0, rule_id="r1",
                            condition_group=_group(_cond("c1"), group_id="gf"))
        inner       = _group(_cond("c-inner"), group_id="g-inner")
        nested_rule = _rule(kind="exit",  index=1, rule_id="r2",
                            condition_group=_group(_cond("c-outer"), inner, group_id="g-outer"))
        result = inspect_plan(_plan(flat_rule, nested_rule))
        assert result.topology.max_nesting_depth == 1


# ---------------------------------------------------------------------------
# Tests — topology: operator usage
# ---------------------------------------------------------------------------

class TestOperatorUsage:
    def test_single_operator(self):
        result = inspect_plan(_plan(_rule(condition_group=_group(_cond(operator=">")))))
        assert result.topology.operator_usage == {">": 1}
        assert result.topology.unique_operators == (">",)

    def test_multiple_conditions_same_operator(self):
        grp = _group(_cond("c1", operator=">"), _cond("c2", operator=">"))
        result = inspect_plan(_plan(_rule(condition_group=grp)))
        assert result.topology.operator_usage[">"] == 2

    def test_mixed_operators(self):
        grp = _group(
            _cond("c1", operator=">"),
            _cond("c2", operator="<"),
            _cond("c3", operator=">"),
        )
        result = inspect_plan(_plan(_rule(condition_group=grp)))
        assert result.topology.operator_usage[">"] == 2
        assert result.topology.operator_usage["<"] == 1

    def test_unique_operators_sorted(self):
        grp = _group(
            _cond("c1", operator=">="),
            _cond("c2", operator="<"),
            _cond("c3", operator=">"),
        )
        result = inspect_plan(_plan(_rule(condition_group=grp)))
        assert result.topology.unique_operators == tuple(sorted(result.topology.operator_usage))

    def test_operator_usage_keys_sorted(self):
        grp = _group(
            _cond("c1", operator=">="),
            _cond("c2", operator=">"),
        )
        result = inspect_plan(_plan(_rule(condition_group=grp)))
        keys = list(result.topology.operator_usage.keys())
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Tests — dependency inspection
# ---------------------------------------------------------------------------

class TestDependencyInspection:
    def test_tool_outputs_preserved(self):
        result = inspect_plan(_plan(_rule(), tool_outputs=("sma_fast.sma", "rsi.rsi")))
        assert result.dependencies.tool_outputs == ("sma_fast.sma", "rsi.rsi")
        assert result.dependencies.tool_output_count == 2

    def test_price_fields_preserved(self):
        result = inspect_plan(_plan(_rule(), price_fields=("close", "open")))
        assert result.dependencies.price_fields == ("close", "open")
        assert result.dependencies.price_field_count == 2

    def test_constants_preserved(self):
        result = inspect_plan(_plan(_rule(), constants=("30", "70")))
        assert result.dependencies.constants == ("30", "70")
        assert result.dependencies.constant_count == 2

    def test_empty_dependencies(self):
        result = inspect_plan(_plan(_rule()))
        assert result.dependencies.tool_output_count == 0
        assert result.dependencies.price_field_count == 0
        assert result.dependencies.constant_count == 0


# ---------------------------------------------------------------------------
# Tests — diagnostics summary
# ---------------------------------------------------------------------------

class TestDiagnosticsSummary:
    def test_no_diagnostics(self):
        result = inspect_plan(_plan(_rule()))
        assert result.diagnostics.error_count == 0
        assert result.diagnostics.warning_count == 0
        assert result.diagnostics.info_count == 0
        assert result.diagnostics.messages == ()

    def test_warning_diagnostic(self):
        diag = CompilationDiagnostic(severity="warning", message="empty semantics")
        result = inspect_plan(_plan(_rule(), diagnostics=(diag,)))
        assert result.diagnostics.warning_count == 1
        assert "empty semantics" in result.diagnostics.messages

    def test_mixed_diagnostics(self):
        diags = (
            CompilationDiagnostic(severity="error",   message="bad"),
            CompilationDiagnostic(severity="warning", message="warn"),
            CompilationDiagnostic(severity="info",    message="fyi"),
        )
        result = inspect_plan(_plan(_rule(), diagnostics=diags))
        assert result.diagnostics.error_count == 1
        assert result.diagnostics.warning_count == 1
        assert result.diagnostics.info_count == 1
        assert len(result.diagnostics.messages) == 3


# ---------------------------------------------------------------------------
# Tests — rule summaries
# ---------------------------------------------------------------------------

class TestRuleSummaries:
    def test_rule_id_preserved(self):
        result = inspect_plan(_plan(_rule(rule_id="r-abc")))
        assert result.rules[0].rule_id == "r-abc"

    def test_rule_kind_preserved(self):
        plan = _plan(
            _rule(kind="entry", index=0, rule_id="r1"),
            _rule(kind="exit",  index=1, rule_id="r2"),
        )
        result = inspect_plan(plan)
        assert result.rules[0].kind == "entry"
        assert result.rules[1].kind == "exit"

    def test_rule_index_preserved(self):
        plan = _plan(
            _rule(kind="entry", index=0, rule_id="r1"),
            _rule(kind="exit",  index=1, rule_id="r2"),
        )
        result = inspect_plan(plan)
        assert result.rules[0].index == 0
        assert result.rules[1].index == 1

    def test_per_rule_condition_count(self):
        r1 = _rule(kind="entry", index=0, rule_id="r1",
                   condition_group=_group(_cond("c1"), _cond("c2"), group_id="g1"))
        r2 = _rule(kind="exit",  index=1, rule_id="r2",
                   condition_group=_group(_cond("c3"), group_id="g2"))
        result = inspect_plan(_plan(r1, r2))
        assert result.rules[0].condition_count == 2
        assert result.rules[1].condition_count == 1

    def test_per_rule_group_count(self):
        inner = _group(_cond("c-inner"), group_id="g-inner")
        outer = _group(_cond("c-outer"), inner, group_id="g-outer")
        result = inspect_plan(_plan(_rule(condition_group=outer)))
        assert result.rules[0].group_count == 2

    def test_per_rule_max_nesting_depth(self):
        inner = _group(_cond("c-inner"), group_id="g-inner")
        outer = _group(_cond("c-outer"), inner, group_id="g-outer")
        result = inspect_plan(_plan(_rule(condition_group=outer)))
        assert result.rules[0].max_nesting_depth == 1

    def test_per_rule_operators_used_sorted(self):
        grp = _group(_cond("c1", operator=">="), _cond("c2", operator=">"))
        result = inspect_plan(_plan(_rule(condition_group=grp)))
        ops = result.rules[0].operators_used
        assert ops == tuple(sorted(ops))


# ---------------------------------------------------------------------------
# Tests — determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_plan_same_summary(self):
        plan = _plan(
            _rule(kind="entry", index=0, rule_id="r1",
                  condition_group=_group(_cond("c1", operator=">"), group_id="g1")),
            _rule(kind="exit",  index=1, rule_id="r2",
                  condition_group=_group(_cond("c2", operator="<"), group_id="g2")),
        )
        r1 = inspect_plan(plan)
        r2 = inspect_plan(plan)
        assert r1.topology.total_condition_nodes == r2.topology.total_condition_nodes
        assert r1.topology.operator_usage == r2.topology.operator_usage
        assert r1.topology.unique_operators == r2.topology.unique_operators
        assert r1.rules[0].condition_count == r2.rules[0].condition_count

    def test_summary_is_frozen(self):
        result = inspect_plan(_plan(_rule()))
        with pytest.raises(Exception):
            result.total_rules = 99


# ---------------------------------------------------------------------------
# Tests — empty plan
# ---------------------------------------------------------------------------

class TestEmptyPlan:
    def test_empty_plan_all_zeros(self):
        empty_plan = EvaluationPlan(
            draft_id=None,
            semantic_version="1.0",
            rule_nodes=(),
            dependencies=DependencySet(tool_outputs=(), price_fields=(), constants=()),
            diagnostics=(),
            node_count=0,
            compiled_at=datetime.now(tz=timezone.utc),
        )
        result = inspect_plan(empty_plan)
        assert result.total_rules == 0
        assert result.topology.entry_rule_count == 0
        assert result.topology.exit_rule_count == 0
        assert result.topology.total_condition_nodes == 0
        assert result.topology.total_group_nodes == 0
        assert result.topology.max_nesting_depth == 0
        assert result.topology.operator_usage == {}
        assert result.rules == ()


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

    MODULES = [
        "backend.strategy_registry.plan_inspector",
        "backend.api.services.plan_inspection_service",
        "backend.api.routes.plan_inspection",
        "backend.api.schemas.plan_inspection",
    ]

    def test_no_strategy_runtime(self):
        for mod in self.MODULES:
            for line in self._import_lines(mod):
                assert "strategy_runtime" not in line, f"{mod}: {line!r}"

    def test_no_backtesting(self):
        for mod in self.MODULES:
            for line in self._import_lines(mod):
                assert "backtesting" not in line, f"{mod}: {line!r}"

    def test_no_execution(self):
        for mod in self.MODULES:
            for line in self._import_lines(mod):
                assert "backend.execution" not in line, f"{mod}: {line!r}"

    def test_no_forward_testing(self):
        for mod in self.MODULES:
            for line in self._import_lines(mod):
                assert "forward_testing" not in line, f"{mod}: {line!r}"
