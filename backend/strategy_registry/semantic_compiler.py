"""
Semantic Compiler — Phase 2O.4.

Converts StrategySemantics into a passive EvaluationPlan.

Public API:
    compile_semantics(semantics, draft_id=None) -> CompilationResult

This module performs TREE TRAVERSAL AND STATIC EXTRACTION only.

CRITICAL — what this module does NOT do:
    - compute indicator values
    - evaluate conditions against market data
    - interpret operators as boolean logic
    - generate trading signals
    - load OHLCV data
    - call strategy runtime systems
    - interact with backtesting or forward-testing engines

Architecture boundary:
    This module must NOT import from:
        backend.strategy_runtime
        backend.backtesting
        backend.execution
        backend.forward_testing

Semantic IDs (condition_id, group_id, rule_id) are preserved in plan nodes to
enable future diagnostics, explainability, and UI highlighting workflows.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Union

from backend.strategy_registry.semantic_plan import (
    CompilationDiagnostic,
    CompilationResult,
    ConditionGroupPlanNode,
    ConditionPlanNode,
    DependencySet,
    EvaluationPlan,
    RulePlanNode,
)
from backend.strategy_registry.semantics import (
    Condition,
    ConditionGroup,
    EntryRule,
    ExitRule,
    OperandKind,
    StrategySemantics,
)

_UTC = timezone.utc


# ---------------------------------------------------------------------------
# Internal tree-walking helpers
# ---------------------------------------------------------------------------

def _compile_condition(cond: Condition) -> ConditionPlanNode:
    return ConditionPlanNode(
        condition_id=cond.condition_id,
        left_kind=cond.left.kind.value,
        left_ref=cond.left.ref,
        operator=cond.operator.value,
        right_kind=cond.right.kind.value,
        right_ref=cond.right.ref,
        label=cond.label,
    )


def _compile_group(
    group: ConditionGroup,
) -> tuple[ConditionGroupPlanNode, int]:
    """
    Recursively compile a ConditionGroup into a ConditionGroupPlanNode.

    Returns:
        (compiled_node, node_count) where node_count is the count of
        ConditionPlanNode leaves and nested ConditionGroupPlanNode sub-nodes
        within this group (not counting the group itself).
    """
    compiled: list[Union[ConditionPlanNode, ConditionGroupPlanNode]] = []
    node_count = 0

    for node in group.conditions:
        if isinstance(node, Condition):
            compiled.append(_compile_condition(node))
            node_count += 1
        elif isinstance(node, ConditionGroup):
            sub_node, sub_count = _compile_group(node)
            compiled.append(sub_node)
            node_count += sub_count + 1  # +1 for the sub-group node itself

    return (
        ConditionGroupPlanNode(
            group_id=group.group_id,
            operator=group.operator.value,
            nodes=tuple(compiled),
            label=group.label,
        ),
        node_count,
    )


def _compile_rule(
    rule: EntryRule | ExitRule,
    kind: str,
    index: int,
) -> tuple[RulePlanNode, int]:
    """Compile a rule into a RulePlanNode. Returns (node, node_count)."""
    compiled_group, node_count = _compile_group(rule.condition_group)
    plan_node = RulePlanNode(
        rule_id=rule.rule_id,
        kind=kind,  # type: ignore[arg-type]
        index=index,
        label=rule.label,
        condition_group=compiled_group,
    )
    return plan_node, node_count


def _extract_dependencies(semantics: StrategySemantics) -> DependencySet:
    """
    Walk the full semantics tree and collect all operand references.

    No computation is performed. References are collected as-is.
    All sets are sorted for deterministic serialization.
    """
    tool_outputs: set[str] = set()
    price_fields: set[str] = set()
    constants:    set[str] = set()

    def _visit_group(group: ConditionGroup) -> None:
        for node in group.conditions:
            if isinstance(node, Condition):
                for operand in (node.left, node.right):
                    if operand.kind == OperandKind.TOOL_OUTPUT:
                        tool_outputs.add(operand.ref)
                    elif operand.kind == OperandKind.PRICE:
                        price_fields.add(operand.ref)
                    elif operand.kind == OperandKind.CONSTANT:
                        constants.add(operand.ref)
            elif isinstance(node, ConditionGroup):
                _visit_group(node)

    for rule in (*semantics.entry_rules, *semantics.exit_rules):
        _visit_group(rule.condition_group)

    return DependencySet(
        tool_outputs=tuple(sorted(tool_outputs)),
        price_fields=tuple(sorted(price_fields)),
        constants=tuple(sorted(constants)),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compile_semantics(
    semantics: StrategySemantics,
    draft_id: str | None = None,
) -> CompilationResult:
    """
    Compile a StrategySemantics into a passive EvaluationPlan.

    This is a structural compilation only — no conditions are evaluated,
    no values are computed, no runtime systems are called.

    Args:
        semantics:  The strategy semantics to compile.
        draft_id:   Optional source draft ID for traceability in the plan.

    Returns:
        CompilationResult with:
            compiled=True  → evaluation_plan is populated
            compiled=False → errors list explains why; evaluation_plan is None
    """
    errors:      list[str] = []
    diagnostics: list[CompilationDiagnostic] = []

    if not semantics.entry_rules and not semantics.exit_rules:
        diagnostics.append(CompilationDiagnostic(
            severity="warning",
            message="semantics has no entry or exit rules; evaluation plan will be empty",
            path=None,
        ))

    rule_nodes:       list[RulePlanNode] = []
    total_node_count: int = 0

    for i, rule in enumerate(semantics.entry_rules):
        try:
            node, count = _compile_rule(rule, "entry", i)
            rule_nodes.append(node)
            total_node_count += count + 1  # +1 for the rule node itself
        except Exception as exc:
            errors.append(f"entry_rules[{i}]: compilation failed — {exc}")
            diagnostics.append(CompilationDiagnostic(
                severity="error",
                message=str(exc),
                path=f"entry_rules[{i}]",
            ))

    for i, rule in enumerate(semantics.exit_rules):
        try:
            node, count = _compile_rule(rule, "exit", i)
            rule_nodes.append(node)
            total_node_count += count + 1
        except Exception as exc:
            errors.append(f"exit_rules[{i}]: compilation failed — {exc}")
            diagnostics.append(CompilationDiagnostic(
                severity="error",
                message=str(exc),
                path=f"exit_rules[{i}]",
            ))

    if errors:
        return CompilationResult(
            compiled=False,
            errors=tuple(errors),
            evaluation_plan=None,
        )

    dependencies = _extract_dependencies(semantics)

    plan = EvaluationPlan(
        draft_id=draft_id,
        semantic_version=semantics.metadata.version,
        rule_nodes=tuple(rule_nodes),
        dependencies=dependencies,
        diagnostics=tuple(diagnostics),
        node_count=total_node_count,
        compiled_at=datetime.now(_UTC),
    )

    return CompilationResult(
        compiled=True,
        errors=(),
        evaluation_plan=plan,
    )
