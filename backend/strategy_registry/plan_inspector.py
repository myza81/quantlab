"""
EvaluationPlan Inspector — Phase 2O.7.

Passive, deterministic inspection of compiled EvaluationPlan IR.

Uses the PlanNodeVisitor pattern to walk the plan tree and accumulate
structural statistics — node counts, nesting depth, operator usage,
dependency fanout, and diagnostic summaries.

No evaluation occurs here. No market data is loaded. No indicators compute.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.backtesting
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from backend.strategy_registry.plan_visitor import (
    PlanNodeVisitor,
    TraversalContext,
    traverse_plan,
)
from backend.strategy_registry.semantic_plan import (
    CompilationDiagnostic,
    ConditionGroupPlanNode,
    ConditionPlanNode,
    EvaluationPlan,
    RulePlanNode,
)


# ---------------------------------------------------------------------------
# Inspection models (passive, frozen Pydantic v2)
# ---------------------------------------------------------------------------

class ConditionNodeSummary(BaseModel):
    """Per-condition structural summary. No evaluation. No values."""
    model_config = ConfigDict(frozen=True)

    condition_id: str | None
    operator:     str
    left_kind:    str
    left_ref:     str
    right_kind:   str
    right_ref:    str
    depth:        int    # group nesting depth at which this condition appears


class RuleNodeSummary(BaseModel):
    """Per-rule structural summary derived from plan traversal."""
    model_config = ConfigDict(frozen=True)

    rule_id:           str | None
    kind:              Literal["entry", "exit"]
    index:             int
    condition_count:   int
    group_count:       int
    max_nesting_depth: int              # deepest group within this rule (0 = flat)
    operators_used:    tuple[str, ...]  # sorted unique operator strings


class TopologySummary(BaseModel):
    """
    Aggregate topology across all rules in the plan.

    operator_usage: maps each operator string to its total usage count.
    unique_operators: sorted tuple of all operators appearing in the plan.
    """
    model_config = ConfigDict(frozen=True)

    entry_rule_count:      int
    exit_rule_count:       int
    total_condition_nodes: int
    total_group_nodes:     int
    max_nesting_depth:     int
    operator_usage:        dict[str, int]     # sorted by key for determinism
    unique_operators:      tuple[str, ...]    # sorted


class DependencyInspectionSummary(BaseModel):
    """Dependency summary derived from EvaluationPlan.dependencies (static, no computation)."""
    model_config = ConfigDict(frozen=True)

    tool_output_count: int
    price_field_count: int
    constant_count:    int
    tool_outputs:      tuple[str, ...]
    price_fields:      tuple[str, ...]
    constants:         tuple[str, ...]


class DiagnosticsSummary(BaseModel):
    """Summary of compilation diagnostics attached to the plan."""
    model_config = ConfigDict(frozen=True)

    error_count:   int
    warning_count: int
    info_count:    int
    messages:      tuple[str, ...]  # all diagnostic messages in source order


class EvaluationPlanSummary(BaseModel):
    """
    Complete deterministic inspection summary for a compiled EvaluationPlan.

    Produced by inspect_plan() — a pure function over EvaluationPlan IR.
    Equivalent plans always produce identical summaries.
    """
    model_config = ConfigDict(frozen=True)

    draft_id:         str | None
    semantic_version: str
    total_rules:      int
    topology:         TopologySummary
    dependencies:     DependencyInspectionSummary
    diagnostics:      DiagnosticsSummary
    rules:            tuple[RuleNodeSummary, ...]


# ---------------------------------------------------------------------------
# Internal visitor accumulator
# ---------------------------------------------------------------------------

@dataclass
class _Acc:
    """
    Mutable accumulator for per-rule structural statistics.

    Used only inside _InspectorVisitor — never exposed in public API.
    """
    condition_count: int                       = 0
    group_count:     int                       = 0
    max_depth:       int                       = 0
    operators:       dict[str, int]            = field(default_factory=dict)
    conditions:      list[ConditionNodeSummary] = field(default_factory=list)

    def merge(self, other: _Acc) -> None:
        self.condition_count += other.condition_count
        self.group_count     += other.group_count
        self.max_depth        = max(self.max_depth, other.max_depth)
        self.conditions.extend(other.conditions)
        for op, count in other.operators.items():
            self.operators[op] = self.operators.get(op, 0) + count


# ---------------------------------------------------------------------------
# Concrete inspector visitor
# ---------------------------------------------------------------------------

class _InspectorVisitor(PlanNodeVisitor):
    """
    Visitor that collects structural statistics during plan traversal.

    Returns _Acc objects that are merged bottom-up through the tree.
    Performs NO evaluation. Accesses NO market data. Computes NO values.
    """

    def visit_condition_node(
        self,
        node:    ConditionPlanNode,
        context: TraversalContext,
    ) -> _Acc:
        acc = _Acc(
            condition_count=1,
            max_depth=context.depth,
            operators={node.operator: 1},
        )
        acc.conditions.append(ConditionNodeSummary(
            condition_id=node.condition_id,
            operator=node.operator,
            left_kind=node.left_kind,
            left_ref=node.left_ref,
            right_kind=node.right_kind,
            right_ref=node.right_ref,
            depth=context.depth,
        ))
        return acc

    def visit_group_node(
        self,
        node:          ConditionGroupPlanNode,
        child_results: tuple[Any, ...],
        context:       TraversalContext,
    ) -> _Acc:
        acc = _Acc(group_count=1, max_depth=context.depth)
        for child in child_results:
            acc.merge(child)
        return acc

    def visit_rule_node(
        self,
        node:         RulePlanNode,
        group_result: Any,
        context:      TraversalContext,
    ) -> tuple[RulePlanNode, _Acc]:
        return (node, group_result)


# ---------------------------------------------------------------------------
# Public inspection API
# ---------------------------------------------------------------------------

def inspect_plan(plan: EvaluationPlan) -> EvaluationPlanSummary:
    """
    Produce a deterministic, execution-free summary of a compiled EvaluationPlan.

    Walks the plan tree via traverse_plan(), accumulating structural statistics.
    Equivalent plans always produce identical summaries (deterministic).

    No evaluation. No data access. No computation.

    Args:
        plan: A compiled EvaluationPlan from semantic_compiler.compile_semantics()

    Returns:
        EvaluationPlanSummary with topology, dependency, and diagnostic summaries.
    """
    visitor     = _InspectorVisitor()
    raw_results = traverse_plan(plan, visitor)

    rule_summaries: list[RuleNodeSummary] = []
    global_acc = _Acc()

    for rule_node, acc in raw_results:  # type: ignore[misc]
        ops_sorted = tuple(sorted(acc.operators.keys()))
        rule_summaries.append(RuleNodeSummary(
            rule_id=rule_node.rule_id,
            kind=rule_node.kind,
            index=rule_node.index,
            condition_count=acc.condition_count,
            group_count=acc.group_count,
            max_nesting_depth=acc.max_depth,
            operators_used=ops_sorted,
        ))
        global_acc.merge(acc)

    entry_count = sum(1 for r in rule_summaries if r.kind == "entry")
    exit_count  = sum(1 for r in rule_summaries if r.kind == "exit")
    op_usage    = dict(sorted(global_acc.operators.items()))

    topology = TopologySummary(
        entry_rule_count=entry_count,
        exit_rule_count=exit_count,
        total_condition_nodes=global_acc.condition_count,
        total_group_nodes=global_acc.group_count,
        max_nesting_depth=global_acc.max_depth,
        operator_usage=op_usage,
        unique_operators=tuple(sorted(op_usage.keys())),
    )

    deps = plan.dependencies
    dep_summary = DependencyInspectionSummary(
        tool_output_count=len(deps.tool_outputs),
        price_field_count=len(deps.price_fields),
        constant_count=len(deps.constants),
        tool_outputs=deps.tool_outputs,
        price_fields=deps.price_fields,
        constants=deps.constants,
    )

    return EvaluationPlanSummary(
        draft_id=plan.draft_id,
        semantic_version=plan.semantic_version,
        total_rules=len(rule_summaries),
        topology=topology,
        dependencies=dep_summary,
        diagnostics=_summarise_diagnostics(plan.diagnostics),
        rules=tuple(rule_summaries),
    )


def _summarise_diagnostics(
    diagnostics: tuple[CompilationDiagnostic, ...],
) -> DiagnosticsSummary:
    errors   = sum(1 for d in diagnostics if d.severity == "error")
    warnings = sum(1 for d in diagnostics if d.severity == "warning")
    info     = sum(1 for d in diagnostics if d.severity == "info")
    return DiagnosticsSummary(
        error_count=errors,
        warning_count=warnings,
        info_count=info,
        messages=tuple(d.message for d in diagnostics),
    )
