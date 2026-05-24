"""
Two-Bar Evaluation Context — Phase 2P.3.

Extends ScalarEvaluationContext with previous-bar values for crossover evaluation.

The current-bar values are accessed via inherited resolution methods.
The previous-bar values are accessed via the dedicated resolve_previous_* methods.

When previous_values is None (first bar), has_previous_bar is False.
Calling resolve_previous_* without a previous bar raises PreviousBarMissingError.
The crossover evaluator catches this and returns outcome=None with diagnostics.

Key layout for both current and previous value dicts:
    "price.{field}"               → e.g. "price.close": 100.0
    "tool.{instance_id}.{output}" → e.g. "tool.sma_fast.value": 98.0

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.backtesting
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

from backend.strategy_registry.evaluator_contracts import ResolvedValue
from backend.strategy_registry.scalar_evaluation_context import (
    ScalarContextError,
    ScalarEvaluationContext,
)


class PreviousBarMissingError(Exception):
    """Raised when previous-bar resolution is attempted but no previous bar exists."""


class TwoBarEvaluationContext(ScalarEvaluationContext):
    """
    EvaluationContext carrying both current and previous bar scalar values.

    Inherits all current-bar resolution methods from ScalarEvaluationContext.
    Adds has_previous_bar property and resolve_previous_* methods for crossover
    operator support.

    When previous_values is None (first bar in a historical sequence), all
    resolve_previous_* calls raise PreviousBarMissingError — callers must
    check has_previous_bar before calling these methods.
    """

    def __init__(
        self,
        evaluation_id:   str,
        current_values:  dict[str, float],
        previous_values: dict[str, float] | None = None,
        plan_draft_id:   str | None = None,
    ) -> None:
        super().__init__(
            evaluation_id=evaluation_id,
            scalar_values=current_values,
            plan_draft_id=plan_draft_id,
        )
        self._previous_values: dict[str, float] | None = (
            dict(previous_values) if previous_values is not None else None
        )

    @property
    def has_previous_bar(self) -> bool:
        """True if previous-bar values are available for crossover evaluation."""
        return self._previous_values is not None

    # ------------------------------------------------------------------
    # Previous-bar resolution methods
    # ------------------------------------------------------------------

    def resolve_previous_price_field(self, field: str) -> ResolvedValue:
        if self._previous_values is None:
            raise PreviousBarMissingError(
                f"Cannot resolve previous price field '{field}': "
                "no previous bar exists (this is the first bar in the sequence)."
            )
        key = f"price.{field}"
        if key not in self._previous_values:
            raise ScalarContextError(
                f"Previous price field '{field}' not found (key '{key}'). "
                f"Available previous keys: {sorted(self._previous_values)}"
            )
        return self._previous_values[key]

    def resolve_previous_tool_output(
        self, instance_id: str, output_name: str
    ) -> ResolvedValue:
        if self._previous_values is None:
            raise PreviousBarMissingError(
                f"Cannot resolve previous tool output '{instance_id}.{output_name}': "
                "no previous bar exists (this is the first bar in the sequence)."
            )
        key = f"tool.{instance_id}.{output_name}"
        if key not in self._previous_values:
            raise ScalarContextError(
                f"Previous tool output '{instance_id}.{output_name}' not found "
                f"(key '{key}'). Available previous keys: {sorted(self._previous_values)}"
            )
        return self._previous_values[key]

    def resolve_previous_constant(self, ref: str) -> ResolvedValue:
        """Resolve a constant from its string representation (same as current bar)."""
        if self._previous_values is None:
            raise PreviousBarMissingError(
                f"Cannot resolve previous constant '{ref}': "
                "no previous bar exists (this is the first bar in the sequence)."
            )
        try:
            return float(ref)
        except (ValueError, TypeError) as exc:
            raise ScalarContextError(
                f"Previous constant '{ref}' cannot be parsed as a numeric value."
            ) from exc
