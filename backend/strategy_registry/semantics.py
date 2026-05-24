"""
Strategy Semantic Layer — Phase 2O.1.

Defines deterministic, execution-free semantic contracts for strategy logic.
These models describe WHAT a strategy means, not HOW it executes.

Design:
- All models are frozen Pydantic v2 (immutable, deterministic serialisation)
- No runtime evaluation, signal generation, or market-data computation
- Recursive ConditionGroup supports arbitrarily nested AND/OR logic
- ConditionGroup.model_rebuild() resolves the forward-reference self-cycle

Portability contract:
    These definitions are consumed identically by research, backtesting,
    forward testing, and future live systems without rewriting strategy logic.
"""
from __future__ import annotations

from enum import Enum
from typing import Union

from pydantic import BaseModel, ConfigDict, field_validator


# ---------------------------------------------------------------------------
# Operand contracts
# ---------------------------------------------------------------------------

class OperandKind(str, Enum):
    TOOL_OUTPUT = "tool_output"   # ref format: "instance_id.output_name"
    CONSTANT    = "constant"       # ref format: numeric string, e.g. "30"
    PRICE       = "price"          # ref format: "close" | "open" | "high" | "low" | "volume"


class OperandReference(BaseModel):
    """
    Typed operand reference. Avoids raw unstructured strings.

    Examples:
        OperandReference(kind="tool_output", ref="sma_fast.value")
        OperandReference(kind="constant",    ref="30")
        OperandReference(kind="price",       ref="close")
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: OperandKind
    ref: str

    @field_validator("ref")
    @classmethod
    def _ref_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("ref must not be empty or whitespace")
        return v.strip()


# ---------------------------------------------------------------------------
# Condition — atomic comparison
# ---------------------------------------------------------------------------

class ConditionOperator(str, Enum):
    GT            = ">"
    LT            = "<"
    GTE           = ">="
    LTE           = "<="
    EQ            = "=="
    NEQ           = "!="
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"


class Condition(BaseModel):
    """
    Atomic comparison between two operands.

    Example: SMA_20 > SMA_50
        left     = OperandReference(kind="tool_output", ref="sma_fast.value")
        operator = ConditionOperator.GT
        right    = OperandReference(kind="tool_output", ref="sma_slow.value")
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    condition_id: str | None = None  # stable ID; None for legacy/pre-injection
    left:         OperandReference
    operator:     ConditionOperator
    right:        OperandReference
    label:        str | None = None


# ---------------------------------------------------------------------------
# ConditionGroup — logical composition (supports nesting)
# ---------------------------------------------------------------------------

class LogicalOperator(str, Enum):
    AND = "AND"
    OR  = "OR"


class ConditionGroup(BaseModel):
    """
    Logical composition of conditions or nested groups.

    Example: (SMA20 > SMA50) AND (RSI < 30)
        operator   = LogicalOperator.AND
        conditions = (
            Condition(left=..., operator=GT, right=...),
            Condition(left=..., operator=LT, right=...),
        )

    Nesting: conditions may contain further ConditionGroup objects,
    enabling arbitrarily complex condition graphs.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    group_id:   str | None = None  # stable ID; None for legacy/pre-injection
    operator:   LogicalOperator
    conditions: tuple[Union[Condition, "ConditionGroup"], ...]
    label:      str | None = None

    @field_validator("conditions")
    @classmethod
    def _conditions_not_empty(cls, v: tuple) -> tuple:
        if len(v) == 0:
            raise ValueError("ConditionGroup must contain at least one condition")
        return v


# Resolve the forward reference introduced by Union[Condition, "ConditionGroup"]
ConditionGroup.model_rebuild()


# ---------------------------------------------------------------------------
# Entry & Exit rules
# ---------------------------------------------------------------------------

class EntryRule(BaseModel):
    """Declarative entry logic wrapping a condition group. Execution-free."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id:         str | None = None  # stable ID; None for legacy/pre-injection
    condition_group: ConditionGroup
    label:           str | None = None
    notes:           str | None = None


class ExitRule(BaseModel):
    """Declarative exit logic wrapping a condition group. Execution-free."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id:         str | None = None  # stable ID; None for legacy/pre-injection
    condition_group: ConditionGroup
    label:           str | None = None
    notes:           str | None = None


# ---------------------------------------------------------------------------
# Metadata & root semantic structure
# ---------------------------------------------------------------------------

class SemanticsMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version:     str      = "1.0"
    author:      str | None = None
    description: str | None = None


class StrategySemantics(BaseModel):
    """
    Root semantic structure for a strategy.

    Captures complete declarative strategy logic — entry rules, exit rules,
    and metadata — without any runtime evaluation or execution coupling.

    Portable across research, backtesting, forward testing, and future live
    systems without rewriting the strategy logic definition.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_rules: tuple[EntryRule, ...]
    exit_rules:  tuple[ExitRule, ...]
    metadata:    SemanticsMetadata = SemanticsMetadata()
