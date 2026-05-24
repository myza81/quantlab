"""
Semantic Binding Service — Phase 2O.5.

Thin orchestration: load draft → validate semantic bindings → return response.
No semantic evaluation. No runtime. No state mutation.
"""
from __future__ import annotations

from backend.api.schemas.semantic_binding import BindingValidationResponse
from backend.strategy_registry.draft_repository import DraftRepository
from backend.strategy_registry.semantic_binding_validator import (
    DependencySummary,
    validate_semantic_bindings,
)
from backend.tools.registry import ToolRegistry


def validate_draft_bindings(
    draft_id: str,
    repository: DraftRepository,
    registry: ToolRegistry,
) -> BindingValidationResponse:
    """
    Load the draft and validate semantic-to-toolset bindings.

    Returns valid=False with a diagnostic if the draft has no semantics.
    Raises DraftNotFoundError if the draft does not exist.
    """
    from backend.strategy_registry.semantic_binding_validator import BindingDiagnostic

    draft = repository.load(draft_id)

    if draft.semantics is None:
        empty_summary = DependencySummary(
            resolved_tool_outputs=(),
            unresolved_tool_outputs=(),
            warned_tool_outputs=(),
            price_fields=(),
            constants=(),
        )
        return BindingValidationResponse(
            valid=False,
            binding_diagnostics=[
                BindingDiagnostic(
                    severity="error",
                    code="no_semantics",
                    reference="",
                    message="draft has no semantics; use PUT /drafts/{id}/semantics first",
                )
            ],
            dependency_summary=empty_summary,
        )

    result = validate_semantic_bindings(draft.semantics, draft.toolset, registry)
    return BindingValidationResponse(
        valid=result.valid,
        binding_diagnostics=list(result.diagnostics),
        dependency_summary=result.summary,
    )
