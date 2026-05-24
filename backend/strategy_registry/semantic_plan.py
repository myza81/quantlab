"""
Semantic Evaluation Plan — Phase 2O.4.

Passive contract describing what a StrategySemantics requires for evaluation.

NOT an execution plan. Nothing here is computed or evaluated.
Suitable for consumption by future evaluation engines (backtesting, forward
testing, paper trading) as a deterministic, inspectable, serializable contract.

Design:
- All plan nodes preserve semantic IDs from source (condition_id, group_id, rule_id)
- DependencySet is static extraction — no computation, no evaluation
- CompilationDiagnostic replaces raises for expected structural issues
- All models are frozen Pydantic v2 and JSON-serializable
- ConditionGroupPlanNode is recursive; model_rebuild() resolves the forward ref
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Union

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Condition plan nodes
# ---------------------------------------------------------------------------

class ConditionPlanNode(BaseModel):
    """Compiled representation of an atomic Condition. Execution-free."""
    model_config = ConfigDict(frozen=True)

    condition_id: str | None  # preserved from source Condition.condition_id
    left_kind:    str          # OperandKind.value string
    left_ref:     str
    operator:     str          # ConditionOperator.value string
    right_kind:   str
    right_ref:    str
    label:        str | None


class ConditionGroupPlanNode(BaseModel):
    """Compiled representation of a ConditionGroup (recursive). Execution-free."""
    model_config = ConfigDict(frozen=True)

    group_id:  str | None  # preserved from source ConditionGroup.group_id
    operator:  str          # "AND" | "OR"
    nodes:     tuple[Union[ConditionPlanNode, "ConditionGroupPlanNode"], ...]
    label:     str | None


# Resolve the self-referential type in nodes
ConditionGroupPlanNode.model_rebuild()


# ---------------------------------------------------------------------------
# Rule plan node
# ---------------------------------------------------------------------------

class RulePlanNode(BaseModel):
    """Compiled representation of an EntryRule or ExitRule. Execution-free."""
    model_config = ConfigDict(frozen=True)

    rule_id:         str | None           # preserved from source rule.rule_id
    kind:            Literal["entry", "exit"]
    index:           int                   # position within entry_rules or exit_rules
    label:           str | None
    condition_group: ConditionGroupPlanNode


# ---------------------------------------------------------------------------
# Dependency extraction
# ---------------------------------------------------------------------------

class DependencySet(BaseModel):
    """
    Static dependency extraction from a StrategySemantics tree.

    All sets are sorted for deterministic serialisation.
    No computation is performed — these are reference strings only.
    """
    model_config = ConfigDict(frozen=True)

    tool_outputs: tuple[str, ...]  # e.g. ("rsi.value", "sma_fast.value")
    price_fields: tuple[str, ...]  # e.g. ("close", "high")
    constants:    tuple[str, ...]  # e.g. ("30", "70")


# ---------------------------------------------------------------------------
# Compilation diagnostics
# ---------------------------------------------------------------------------

class CompilationDiagnostic(BaseModel):
    """A non-fatal or informational message produced during compilation."""
    model_config = ConfigDict(frozen=True)

    severity: Literal["error", "warning", "info"]
    message:  str
    path:     str | None = None


# ---------------------------------------------------------------------------
# Evaluation plan & compilation result
# ---------------------------------------------------------------------------

class EvaluationPlan(BaseModel):
    """
    Passive evaluation plan produced by the semantic compiler.

    Describes what would need to be evaluated to assess the strategy's
    conditions, without performing any evaluation itself.

    Future evaluators (backtesting engine, forward-testing runtime, etc.) may
    consume this plan as a deterministic, inspectable contract.

    Portability contract:
        This structure must remain execution-free. Any evaluation engine
        consuming it must perform its own computation outside this model.
    """
    model_config = ConfigDict(frozen=True)

    draft_id:         str | None   # None for payload-only compilations
    semantic_version: str
    rule_nodes:       tuple[RulePlanNode, ...]
    dependencies:     DependencySet
    diagnostics:      tuple[CompilationDiagnostic, ...]
    node_count:       int           # total condition + group nodes compiled
    compiled_at:      datetime


class CompilationResult(BaseModel):
    """
    Result of a semantic compilation attempt.

    compiled=True  → evaluation_plan is populated; errors is empty
    compiled=False → errors explains why compilation failed; evaluation_plan is None
    """
    model_config = ConfigDict(frozen=True)

    compiled:        bool
    errors:          tuple[str, ...]
    evaluation_plan: EvaluationPlan | None
