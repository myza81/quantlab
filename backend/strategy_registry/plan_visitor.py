"""
EvaluationPlan Visitor Architecture — Phase 2O.6.

Generic visitor/traversal contract for EvaluationPlan IR.

Enables future evaluators to walk plan trees without coupling to evaluation
logic — the visitor determines what to do at each node; the traversal handles
only structural tree walking.

No evaluation occurs here. No market data is accessed. No values are computed.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.backtesting
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict

from backend.strategy_registry.semantic_plan import (
    ConditionGroupPlanNode,
    ConditionPlanNode,
    EvaluationPlan,
    RulePlanNode,
)


# ---------------------------------------------------------------------------
# Traversal context
# ---------------------------------------------------------------------------

class TraversalContext(BaseModel):
    """
    Passive context carried through plan tree traversal.

    Describes the current position in the traversal — useful for diagnostic
    path construction, depth-aware processing, and audit tracing.

    Does NOT carry evaluation state. Does NOT carry market data.
    """
    model_config = ConfigDict(frozen=True)

    rule_index: int
    rule_kind:  str           # "entry" or "exit"
    rule_id:    str | None
    depth:      int           # group nesting depth; 0 = rule's top-level group
    path:       str           # dot-separated position path, e.g. "rule[0].group[1]"


# ---------------------------------------------------------------------------
# Visitor interface
# ---------------------------------------------------------------------------

class PlanNodeVisitor(ABC):
    """
    Abstract visitor for EvaluationPlan nodes.

    Implementations define behavior at each node type without controlling
    traversal order. Traversal is handled by traverse_plan().

    visit methods:
        visit_condition_node — called for each ConditionPlanNode (leaf)
        visit_group_node     — called for each ConditionGroupPlanNode after
                               all children have been visited (post-order)
        visit_rule_node      — called for each RulePlanNode after its
                               condition group has been visited (post-order)

    Return values are passed upward to parent visit calls as child_results
    or group_result. The concrete visitor decides what to accumulate.
    """

    @abstractmethod
    def visit_condition_node(
        self,
        node:    ConditionPlanNode,
        context: TraversalContext,
    ) -> Any:
        """Visit an atomic ConditionPlanNode (leaf node)."""

    @abstractmethod
    def visit_group_node(
        self,
        node:          ConditionGroupPlanNode,
        child_results: tuple[Any, ...],
        context:       TraversalContext,
    ) -> Any:
        """
        Visit a ConditionGroupPlanNode after all children have been visited.

        Args:
            child_results: Results returned by visiting each child node in order.
        """

    @abstractmethod
    def visit_rule_node(
        self,
        node:         RulePlanNode,
        group_result: Any,
        context:      TraversalContext,
    ) -> Any:
        """
        Visit a RulePlanNode after its condition group has been visited.

        Args:
            group_result: Result returned by visiting the rule's condition group.
        """


# ---------------------------------------------------------------------------
# Traversal engine (concrete — structural only)
# ---------------------------------------------------------------------------

def traverse_plan(
    plan:    EvaluationPlan,
    visitor: PlanNodeVisitor,
) -> tuple[Any, ...]:
    """
    Traverse all rule nodes in an EvaluationPlan, calling visitor methods.

    Traversal order: depth-first, post-order (children visited before parent).

    Returns a tuple of results from visit_rule_node for each rule, preserving
    the order of rule_nodes in the plan.

    This function performs ONLY structural tree walking — no evaluation,
    no data access, no computation.

    Args:
        plan:    EvaluationPlan to traverse
        visitor: PlanNodeVisitor implementation

    Returns:
        Tuple of per-rule results as returned by visitor.visit_rule_node.
    """
    results = []
    for rule_node in plan.rule_nodes:
        ctx = TraversalContext(
            rule_index=rule_node.index,
            rule_kind=rule_node.kind,
            rule_id=rule_node.rule_id,
            depth=0,
            path=f"rule[{rule_node.index}]",
        )
        group_result = _traverse_group(rule_node.condition_group, visitor, ctx)
        rule_result  = visitor.visit_rule_node(rule_node, group_result, ctx)
        results.append(rule_result)
    return tuple(results)


def _traverse_group(
    node:    ConditionGroupPlanNode,
    visitor: PlanNodeVisitor,
    ctx:     TraversalContext,
) -> Any:
    """Internal post-order traversal of a condition group node."""
    child_results = []
    for i, child in enumerate(node.nodes):
        if isinstance(child, ConditionPlanNode):
            child_ctx = TraversalContext(
                rule_index=ctx.rule_index,
                rule_kind=ctx.rule_kind,
                rule_id=ctx.rule_id,
                depth=ctx.depth,
                path=f"{ctx.path}.condition[{i}]",
            )
            child_results.append(visitor.visit_condition_node(child, child_ctx))
        else:
            nested_ctx = TraversalContext(
                rule_index=ctx.rule_index,
                rule_kind=ctx.rule_kind,
                rule_id=ctx.rule_id,
                depth=ctx.depth + 1,
                path=f"{ctx.path}.group[{i}]",
            )
            child_results.append(_traverse_group(child, visitor, nested_ctx))

    group_ctx = TraversalContext(
        rule_index=ctx.rule_index,
        rule_kind=ctx.rule_kind,
        rule_id=ctx.rule_id,
        depth=ctx.depth,
        path=ctx.path,
    )
    return visitor.visit_group_node(node, tuple(child_results), group_ctx)
