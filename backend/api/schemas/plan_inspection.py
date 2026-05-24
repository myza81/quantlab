"""
Plan Inspection API Schemas — Phase 2O.7.

Passive DTOs for EvaluationPlan inspection endpoints.
No business logic. No execution. No runtime coupling.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from backend.strategy_registry.semantic_binding_validator import (
    BindingDiagnostic,
    DependencySummary,
)
from backend.strategy_registry.semantic_plan import EvaluationPlan
from backend.strategy_registry.semantics import StrategySemantics
from backend.strategy_registry.plan_inspector import EvaluationPlanSummary


class PlanInspectionRequest(BaseModel):
    """Request body for POST /semantics/plan (payload inspection without a draft)."""
    model_config = ConfigDict(extra="forbid")

    semantics: StrategySemantics


class PlanInspectionResponse(BaseModel):
    """
    Response for EvaluationPlan inspection endpoints.

    compiled=True   → evaluation_plan and summary are populated
    compiled=False  → errors explains why; evaluation_plan and summary are None

    Binding fields are only populated for draft inspection (toolset available).
    They are None for payload-only inspection.
    """
    draft_id:        str | None
    compiled:        bool
    errors:          list[str]
    evaluation_plan: EvaluationPlan | None
    summary:         EvaluationPlanSummary | None
    # Binding info — populated by draft endpoint only
    binding_valid:              bool | None       = None
    binding_diagnostics:        list[BindingDiagnostic] = []
    binding_dependency_summary: DependencySummary | None = None
