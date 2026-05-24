"""
Evaluator Contract Architecture — Phase 2O.6.

Abstract interfaces and passive result contracts for EvaluationPlan interpretation.

This module defines WHAT a future evaluator MUST implement, not HOW it executes.
No evaluation is performed here. No market data is loaded. No indicators compute.

Architecture layers:
    StrategySemantics  (semantics.py)
        ↓ semantic_compiler.py
    EvaluationPlan IR  (semantic_plan.py)
        ↓
    Evaluator Contracts (this module)          ← Phase 2O.6
        ↓
    Concrete Evaluators  (future phases)
        backend.backtesting   — historical bar-by-bar evaluation
        backend.forward_testing — streaming/live evaluation

Compiler responsibility:
    StrategySemantics → EvaluationPlan     (structural, static, no execution)

Evaluator responsibility (contracts only — no implementation here):
    EvaluationPlan + EvaluationContext → EvaluationTrace

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.backtesting
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict

from backend.strategy_registry.semantic_plan import (
    ConditionGroupPlanNode,
    ConditionPlanNode,
    EvaluationPlan,
    RulePlanNode,
)

# Generic resolved value type alias.
# Intentionally unbound — concrete evaluators determine what resolution means
# (float, bool, time series, etc.). This keeps contracts indicator-agnostic.
ResolvedValue = Any


# ---------------------------------------------------------------------------
# Evaluation diagnostics
# ---------------------------------------------------------------------------

class EvaluationDiagnostic(BaseModel):
    """
    A diagnostic produced during evaluation (not compilation).

    Compilation diagnostics describe structural issues.
    Evaluation diagnostics describe runtime resolution failures.

    Examples of codes:
        "unresolved_operand"     — operand could not be resolved in context
        "operator_type_mismatch" — resolved values incompatible with operator
        "context_unavailable"    — required context source not accessible
        "indeterminate_result"   — could not determine True/False outcome

    All fields are passive. No execution occurs here.
    """
    model_config = ConfigDict(frozen=True)

    severity:     Literal["error", "warning", "info"]
    code:         str
    reference:    str           # e.g. "sma_fast.sma" or "condition_id:abc123"
    message:      str
    rule_id:      str | None = None
    condition_id: str | None = None


# ---------------------------------------------------------------------------
# Evaluation result contracts (passive, frozen Pydantic v2)
# ---------------------------------------------------------------------------

class ConditionEvaluationResult(BaseModel):
    """
    Passive result of evaluating a single ConditionPlanNode.

    outcome=True    → condition held at evaluation time
    outcome=False   → condition did not hold
    outcome=None    → result indeterminate (resolution failure, operator error)
    """
    model_config = ConfigDict(frozen=True)

    condition_id: str | None
    outcome:      bool | None
    diagnostics:  tuple[EvaluationDiagnostic, ...]


class GroupEvaluationResult(BaseModel):
    """
    Passive result of evaluating a ConditionGroupPlanNode.

    Recursive: child_results contains ConditionEvaluationResult OR
    nested GroupEvaluationResult entries, matching the plan tree structure.

    outcome=None if any child is indeterminate and the group cannot determine
    a definitive result under its logical operator (AND/OR).
    """
    model_config = ConfigDict(frozen=True)

    group_id:      str | None
    outcome:       bool | None
    child_results: tuple[Union[ConditionEvaluationResult, "GroupEvaluationResult"], ...]
    diagnostics:   tuple[EvaluationDiagnostic, ...]


GroupEvaluationResult.model_rebuild()


class RuleEvaluationResult(BaseModel):
    """
    Passive result of evaluating a RulePlanNode.

    triggered=True   → rule's condition group evaluated to True
    triggered=False  → rule did not trigger
    triggered=None   → indeterminate (propagated from group evaluation)
    """
    model_config = ConfigDict(frozen=True)

    rule_id:      str | None
    kind:         Literal["entry", "exit"]
    index:        int
    triggered:    bool | None
    group_result: GroupEvaluationResult
    diagnostics:  tuple[EvaluationDiagnostic, ...]


class EvaluationTrace(BaseModel):
    """
    Complete, auditable trace of evaluating an EvaluationPlan at one point in time.

    Intended for:
        - audit and replay
        - debugging evaluation failures
        - test assertions
        - evaluation observability

    NOT for signal generation or execution. Signal generation is the
    responsibility of the calling runtime layer, which reads triggered flags.
    """
    model_config = ConfigDict(frozen=True)

    plan_draft_id:    str | None
    evaluation_id:    str
    rule_results:     tuple[RuleEvaluationResult, ...]
    diagnostics:      tuple[EvaluationDiagnostic, ...]
    entry_triggered:  bool | None = None   # True if any entry rule triggered
    exit_triggered:   bool | None = None   # True if any exit rule triggered


# ---------------------------------------------------------------------------
# Abstract evaluator interfaces
# ---------------------------------------------------------------------------

class EvaluationContext(ABC):
    """
    Abstract context provided to evaluators at evaluation time.

    Concrete implementations supply resolved values for a specific bar or
    streaming tick — market snapshots, tool outputs, price fields.

    Evaluator contract:
        - Evaluators MUST NOT load market data themselves
        - Evaluators MUST NOT compute indicators themselves
        - All data access goes through this interface
        - Context implementations are responsible for data provisioning

    The context lifecycle is managed by the calling runtime layer
    (backtesting engine, forward-testing runtime, etc.), not the evaluator.
    """

    @abstractmethod
    def resolve_tool_output(self, instance_id: str, output_name: str) -> ResolvedValue:
        """
        Resolve a tool output reference to its value for this evaluation.

        Args:
            instance_id: Tool instance identifier (e.g. "sma_fast")
            output_name: Declared output name on the tool (e.g. "sma")

        Raises:
            An implementation-defined error if the output is unavailable.
        """

    @abstractmethod
    def resolve_price_field(self, field: str) -> ResolvedValue:
        """
        Resolve a price field name to its value for this evaluation bar.

        Args:
            field: Price field string ("open", "high", "low", "close", "volume")
        """

    @abstractmethod
    def resolve_constant(self, ref: str) -> ResolvedValue:
        """
        Resolve a constant reference string to a typed value.

        Args:
            ref: Numeric string representation, e.g. "30" or "0.75"
        """

    @property
    @abstractmethod
    def evaluation_id(self) -> str:
        """Unique identifier for this evaluation run."""

    @property
    @abstractmethod
    def available_tool_instances(self) -> tuple[str, ...]:
        """Tuple of instance_ids declared available in this context."""

    @property
    @abstractmethod
    def available_price_fields(self) -> tuple[str, ...]:
        """Tuple of price field names declared available in this context."""


class OperandResolver(ABC):
    """
    Abstract contract for resolving a plan node operand to a value.

    Maps (kind, ref) pairs — as stored in ConditionPlanNode fields — to
    concrete values via an EvaluationContext.

    Must NOT compute indicators. Must NOT load data. Delegates entirely
    to the EvaluationContext for value provisioning.
    """

    @abstractmethod
    def resolve(
        self,
        kind:    str,
        ref:     str,
        context: EvaluationContext,
    ) -> ResolvedValue:
        """
        Resolve an operand (kind, ref) pair to a value.

        Args:
            kind:    OperandKind value string ("tool_output", "price", "constant")
            ref:     Operand reference string from the plan node
            context: EvaluationContext for value access
        """


class OperatorEvaluator(ABC):
    """
    Abstract contract for evaluating a comparison between two resolved values.

    Operator evaluators are generic — they must NOT contain logic specific
    to any indicator, tool, data type, or strategy pattern.

    All eight ConditionOperator values must be supportable:
        ">"   "<"   ">="   "<="   "=="   "!="
        "crosses_above"   "crosses_below"

    Whether crosses_above/crosses_below require historical context (e.g.
    previous-bar values) is an implementation detail — this contract only
    defines the interface.
    """

    @property
    @abstractmethod
    def supported_operators(self) -> frozenset[str]:
        """The set of operator strings this evaluator handles."""

    @abstractmethod
    def evaluate(
        self,
        left:     ResolvedValue,
        operator: str,
        right:    ResolvedValue,
    ) -> bool | None:
        """
        Evaluate a comparison between two resolved operand values.

        Args:
            left:     Resolved left operand
            operator: ConditionOperator value string
            right:    Resolved right operand

        Returns:
            True/False if determinable; None if indeterminate.
        """


class ConditionEvaluator(ABC):
    """
    Abstract contract for evaluating a single ConditionPlanNode.

    Orchestrates OperandResolver + OperatorEvaluator for one condition.
    Must NOT compute indicators. Must NOT load market data.
    """

    @abstractmethod
    def evaluate_condition(
        self,
        node:    ConditionPlanNode,
        context: EvaluationContext,
    ) -> ConditionEvaluationResult:
        """
        Evaluate one compiled condition node.

        Args:
            node:    Compiled condition plan node (from EvaluationPlan IR)
            context: Evaluation context providing value access

        Returns:
            ConditionEvaluationResult with outcome and any diagnostics.
        """


class GroupEvaluator(ABC):
    """
    Abstract contract for evaluating a ConditionGroupPlanNode.

    Must support arbitrary nesting — groups may contain groups.
    Must apply the logical operator (AND/OR) across child results.
    Must NOT compute indicators. Must NOT load market data.
    """

    @abstractmethod
    def evaluate_group(
        self,
        node:    ConditionGroupPlanNode,
        context: EvaluationContext,
    ) -> GroupEvaluationResult:
        """
        Evaluate a compiled condition group node (recursively if nested).

        Args:
            node:    Compiled condition group plan node
            context: Evaluation context providing value access

        Returns:
            GroupEvaluationResult with outcome, child results, and diagnostics.
        """


class RuleEvaluator(ABC):
    """
    Abstract contract for evaluating a RulePlanNode.

    A rule is triggered (triggered=True) if its condition group evaluates True.
    Must NOT generate signals. Must NOT modify external state.
    """

    @abstractmethod
    def evaluate_rule(
        self,
        node:    RulePlanNode,
        context: EvaluationContext,
    ) -> RuleEvaluationResult:
        """
        Evaluate a compiled rule plan node.

        Args:
            node:    Compiled rule plan node
            context: Evaluation context providing value access

        Returns:
            RuleEvaluationResult with triggered status and full group result.
        """


class EvaluationEngineContract(ABC):
    """
    Top-level abstract contract for a complete evaluation engine.

    An engine consumes a pre-compiled EvaluationPlan and a pre-populated
    EvaluationContext, orchestrates all evaluator components, and returns
    a passive EvaluationTrace.

    Critical constraints:
        - Engine NEVER re-compiles semantics (receives pre-compiled plan)
        - Engine NEVER loads market data (receives pre-populated context)
        - Engine NEVER generates signals (returns trace; runtime decides)
        - Signal generation is the calling runtime layer's responsibility

    Concrete implementations belong in future modules:
        backend.backtesting     — historical bar-by-bar evaluation
        backend.forward_testing — live/streaming evaluation
    """

    @abstractmethod
    def evaluate_plan(
        self,
        plan:    EvaluationPlan,
        context: EvaluationContext,
    ) -> EvaluationTrace:
        """
        Evaluate a full EvaluationPlan against a populated context.

        Args:
            plan:    Pre-compiled evaluation plan (from semantic_compiler)
            context: Pre-populated evaluation context (from runtime layer)

        Returns:
            EvaluationTrace with all rule results, diagnostics, and trigger flags.
        """

    @property
    @abstractmethod
    def supported_operators(self) -> frozenset[str]:
        """The set of condition operator strings this engine can evaluate."""
