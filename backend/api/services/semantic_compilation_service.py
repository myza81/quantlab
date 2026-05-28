"""
Semantic Compilation Service — Phase 2O.4 / 2O.5.

Thin orchestration between compilation routes and the semantic compiler.

Responsibilities:
    load draft → get semantics → compile → (optionally) validate bindings → return response

Does NOT evaluate semantics, call runtime systems, or modify any state.
"""
from __future__ import annotations

from backend.api.schemas.semantic_compilation import CompilationResponse
from backend.strategy_registry.draft_repository import DraftRepository
from backend.strategy_registry.semantic_binding_validator import validate_semantic_bindings
from backend.strategy_registry.semantic_compiler import compile_semantics
from backend.strategy_registry.semantics import StrategySemantics
from backend.tools.registry import ToolRegistry


def _make_response(result) -> CompilationResponse:
    """Convert CompilationResult → CompilationResponse (no binding fields)."""
    diagnostics = (
        list(result.evaluation_plan.diagnostics)
        if result.evaluation_plan is not None
        else []
    )
    return CompilationResponse(
        compiled=result.compiled,
        errors=list(result.errors),
        diagnostics=diagnostics,
        evaluation_plan=result.evaluation_plan,
    )


def compile_draft_semantics(
    draft_id: str,
    repository: DraftRepository,
    registry: ToolRegistry | None = None,
    owner_id: str | None = None,
) -> CompilationResponse:
    """
    Load the draft, compile its semantics, return a passive CompilationResponse.

    If registry is provided, also runs semantic binding validation against the
    draft's toolset and populates binding_valid / binding_diagnostics /
    dependency_summary in the response.

    Returns compiled=False with an error if the draft has no semantics.
    Raises DraftNotFoundError if the draft does not exist.
    """
    draft = repository.load(draft_id, owner_id=owner_id)

    if draft.semantics is None:
        return CompilationResponse(
            compiled=False,
            errors=["draft has no semantics defined; use PUT /drafts/{id}/semantics first"],
            diagnostics=[],
            evaluation_plan=None,
        )

    result = compile_semantics(draft.semantics, draft_id=draft_id)
    response = _make_response(result)

    # Binding validation — requires toolset context available only on draft endpoint
    binding = validate_semantic_bindings(draft.semantics, draft.toolset, registry)
    return CompilationResponse(
        compiled=response.compiled,
        errors=response.errors,
        diagnostics=response.diagnostics,
        evaluation_plan=response.evaluation_plan,
        binding_valid=binding.valid,
        binding_diagnostics=list(binding.diagnostics),
        dependency_summary=binding.summary,
    )


def compile_semantics_payload(
    semantics: StrategySemantics,
) -> CompilationResponse:
    """
    Compile an arbitrary StrategySemantics payload without loading a draft.

    No repository interaction. No state mutation. Purely structural.
    """
    result = compile_semantics(semantics, draft_id=None)
    return _make_response(result)
