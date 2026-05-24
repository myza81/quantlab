"""
Concrete Scalar EvaluationContext — Phase 2P.1.

Minimal concrete EvaluationContext backed by a flat scalar dict.
Supports: price field lookup, tool output lookup, constant passthrough.

No OHLCV datasets. No history arrays. No streaming. No tool computation.
Tool outputs MUST be pre-resolved and injected by the caller.

Key layout in scalar_values:
    "price.{field}"               → e.g. "price.close": 100.0
    "tool.{instance_id}.{output}" → e.g. "tool.sma_fast.value": 98.0

Constants are resolved directly from their string representation ("30" → 30.0).

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.backtesting
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

from backend.strategy_registry.evaluator_contracts import EvaluationContext, ResolvedValue


class ScalarContextError(Exception):
    """Raised when a required value is not present in the scalar context."""


class ScalarEvaluationContext(EvaluationContext):
    """
    Concrete EvaluationContext backed by a flat scalar dict.

    All values must be pre-loaded by the caller. The context performs
    no computation — it is a passive value store with named key lookup.

    Example:
        ctx = ScalarEvaluationContext(
            evaluation_id="eval-001",
            scalar_values={
                "price.close": 100.0,
                "price.open":  99.0,
                "tool.sma_fast.value": 98.0,
            },
        )
    """

    _PRICE_PREFIX = "price."
    _TOOL_PREFIX  = "tool."

    def __init__(
        self,
        evaluation_id: str,
        scalar_values: dict[str, float],
        plan_draft_id: str | None = None,
    ) -> None:
        self._evaluation_id = evaluation_id
        self._plan_draft_id = plan_draft_id
        self._scalar_values: dict[str, float] = dict(scalar_values)

    # ------------------------------------------------------------------
    # EvaluationContext abstract properties
    # ------------------------------------------------------------------

    @property
    def evaluation_id(self) -> str:
        return self._evaluation_id

    @property
    def available_tool_instances(self) -> tuple[str, ...]:
        seen: set[str] = set()
        for key in self._scalar_values:
            if key.startswith(self._TOOL_PREFIX):
                # "tool.{instance_id}.{output_name}" → parts[1] is instance_id
                parts = key.split(".", 2)
                if len(parts) == 3:
                    seen.add(parts[1])
        return tuple(sorted(seen))

    @property
    def available_price_fields(self) -> tuple[str, ...]:
        prefix = self._PRICE_PREFIX
        fields = [k[len(prefix):] for k in self._scalar_values if k.startswith(prefix)]
        return tuple(sorted(fields))

    # ------------------------------------------------------------------
    # EvaluationContext abstract resolution methods
    # ------------------------------------------------------------------

    def resolve_tool_output(self, instance_id: str, output_name: str) -> ResolvedValue:
        key = f"tool.{instance_id}.{output_name}"
        if key not in self._scalar_values:
            raise ScalarContextError(
                f"Tool output '{instance_id}.{output_name}' not found in scalar context "
                f"(key '{key}'). Available tool instances: {self.available_tool_instances}"
            )
        return self._scalar_values[key]

    def resolve_price_field(self, field: str) -> ResolvedValue:
        key = f"price.{field}"
        if key not in self._scalar_values:
            raise ScalarContextError(
                f"Price field '{field}' not found in scalar context (key '{key}'). "
                f"Available price fields: {self.available_price_fields}"
            )
        return self._scalar_values[key]

    def resolve_constant(self, ref: str) -> ResolvedValue:
        try:
            return float(ref)
        except (ValueError, TypeError) as exc:
            raise ScalarContextError(
                f"Constant '{ref}' cannot be parsed as a numeric value."
            ) from exc
