"""
Evaluation Readiness Service — Phase 2O.9.

Orchestrates: load draft → compile semantics → validate bindings →
run readiness lint rules → return EvaluationReadinessResponse.

No evaluation. No execution. No state mutation.
"""
from __future__ import annotations

from backend.api.schemas.evaluation_readiness import EvaluationReadinessResponse
from backend.strategy_registry.draft_repository import DraftRepository
from backend.strategy_registry.evaluation_readiness import check_readiness
from backend.strategy_registry.semantic_binding_validator import validate_semantic_bindings
from backend.strategy_registry.semantic_compiler import compile_semantics
from backend.strategy_registry.semantics import StrategySemantics
from backend.tools.registry import ToolRegistry


def check_draft_readiness(
    draft_id:   str,
    repository: DraftRepository,
    registry:   ToolRegistry | None = None,
) -> EvaluationReadinessResponse:
    """
    Load draft, compile semantics, validate bindings, run readiness lint.

    Raises DraftNotFoundError if the draft does not exist.
    Returns a blocked report if the draft has no semantics.
    """
    draft = repository.load(draft_id)

    if draft.semantics is None:
        report = check_readiness(
            compiled=False,
            errors=("draft has no semantics defined; use PUT /drafts/{id}/semantics first",),
        )
        return EvaluationReadinessResponse(
            draft_id=draft_id,
            ready=report.ready,
            status=report.status,
            summary=report.summary,
            issues=list(report.issues),
        )

    result  = compile_semantics(draft.semantics, draft_id=draft_id)
    binding = (
        validate_semantic_bindings(draft.semantics, draft.toolset, registry)
        if result.compiled and result.evaluation_plan is not None
        else None
    )

    report = check_readiness(
        compiled=result.compiled,
        errors=result.errors,
        plan=result.evaluation_plan,
        binding_result=binding,
    )

    return EvaluationReadinessResponse(
        draft_id=draft_id,
        ready=report.ready,
        status=report.status,
        summary=report.summary,
        issues=list(report.issues),
    )


def check_semantics_payload_readiness(
    semantics: StrategySemantics,
) -> EvaluationReadinessResponse:
    """
    Compile an arbitrary semantics payload and run readiness lint.

    No draft loading. No binding validation (no toolset context).
    No state mutation.
    """
    result = compile_semantics(semantics, draft_id=None)

    report = check_readiness(
        compiled=result.compiled,
        errors=result.errors,
        plan=result.evaluation_plan,
        binding_result=None,
    )

    return EvaluationReadinessResponse(
        draft_id=None,
        ready=report.ready,
        status=report.status,
        summary=report.summary,
        issues=list(report.issues),
    )
