"""
Semantic Binding API Schemas — Phase 2O.5.

Passive data-transfer types for the validate-bindings endpoint.
No business logic. No execution. No runtime coupling.
"""
from __future__ import annotations

from pydantic import BaseModel

from backend.strategy_registry.semantic_binding_validator import (
    BindingDiagnostic,
    DependencySummary,
)


class BindingValidationResponse(BaseModel):
    """
    Response for POST /drafts/{draft_id}/semantics/validate-bindings.

    valid=True  → all tool_output refs resolved with no error-severity diagnostics
    valid=False → at least one tool_output ref could not be resolved
    """
    valid:               bool
    binding_diagnostics: list[BindingDiagnostic]
    dependency_summary:  DependencySummary
