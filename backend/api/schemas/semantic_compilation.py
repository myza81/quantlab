"""
Semantic Compilation API Schemas — Phase 2O.4 / 2O.5.

Passive data-transfer types for compilation endpoints.
No business logic. No execution. No runtime coupling.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from backend.strategy_registry.semantic_binding_validator import (
    BindingDiagnostic,
    DependencySummary,
)
from backend.strategy_registry.semantic_plan import (
    CompilationDiagnostic,
    EvaluationPlan,
)
from backend.strategy_registry.semantics import StrategySemantics


class CompileRequest(BaseModel):
    """Request body for POST /semantics/compile."""
    model_config = ConfigDict(extra="forbid")

    semantics: StrategySemantics


class CompilationResponse(BaseModel):
    """
    Response for compilation endpoints.

    compiled=True  → evaluation_plan is populated
    compiled=False → errors explains why; evaluation_plan is None

    Binding fields (Phase 2O.5) are only populated for draft compilation
    endpoints where the toolset is available. They are None for payload-only
    compilation (no draft, no toolset context).
    """
    compiled:        bool
    errors:          list[str]
    diagnostics:     list[CompilationDiagnostic]
    evaluation_plan: EvaluationPlan | None
    # Binding validation — populated by draft compile endpoint only
    binding_valid:        bool | None = None
    binding_diagnostics:  list[BindingDiagnostic] = []
    dependency_summary:   DependencySummary | None = None
