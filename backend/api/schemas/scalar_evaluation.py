"""
Scalar Evaluation API schemas — Phase 2P.1.

Request and response DTOs for the optional POST /semantics/evaluate-scalar endpoint.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.strategy_registry.semantics import StrategySemantics


class ScalarEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semantics:      StrategySemantics
    scalar_context: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Pre-resolved scalar values keyed by 'price.{field}' or "
            "'tool.{instance_id}.{output_name}'. Tool outputs must be injected "
            "externally — the evaluator performs no indicator computation."
        ),
    )
    evaluation_id: str | None = Field(
        default=None,
        description="Optional evaluation ID; auto-generated if omitted.",
    )
