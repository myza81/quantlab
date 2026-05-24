"""
Evaluation Readiness API Schemas — Phase 2O.9.

Passive DTOs for evaluation readiness endpoints.
No business logic. No execution. No runtime coupling.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from backend.strategy_registry.evaluation_readiness import (
    ReadinessIssue,
    ReadinessSummary,
)
from backend.strategy_registry.semantics import StrategySemantics


class EvaluationReadinessRequest(BaseModel):
    """Request body for POST /semantics/readiness (payload inspection without a draft)."""
    model_config = ConfigDict(extra="forbid")

    semantics: StrategySemantics


class EvaluationReadinessResponse(BaseModel):
    """
    Response for evaluation readiness endpoints.

    ready=True   → no blocking issues; plan is structurally ready for evaluation
    ready=False  → at least one blocking issue found

    status: "ready" | "degraded" | "blocked"
    Binding fields are only populated for draft readiness (toolset context available).
    """
    draft_id: str | None
    ready:    bool
    status:   str            # ReadinessStatus literal
    summary:  ReadinessSummary
    issues:   list[ReadinessIssue]
