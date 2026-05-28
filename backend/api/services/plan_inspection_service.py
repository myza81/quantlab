"""
Plan Inspection Service — Phase 2O.7.

Thin orchestration: load draft → compile semantics → inspect EvaluationPlan
→ (optionally) validate bindings → return passive PlanInspectionResponse.

No evaluation. No execution. No state mutation.
"""
from __future__ import annotations

from backend.api.schemas.plan_inspection import PlanInspectionResponse
from backend.strategy_registry.draft_repository import DraftRepository
from backend.strategy_registry.plan_inspector import inspect_plan
from backend.strategy_registry.semantic_binding_validator import validate_semantic_bindings
from backend.strategy_registry.semantic_compiler import compile_semantics
from backend.strategy_registry.semantics import StrategySemantics
from backend.tools.registry import ToolRegistry


def inspect_draft_plan(
    draft_id:   str,
    repository: DraftRepository,
    registry:   ToolRegistry | None = None,
    owner_id:   str | None = None,
) -> PlanInspectionResponse:
    """
    Load draft, compile its semantics, inspect the EvaluationPlan.

    If registry is provided, also validates semantic-to-toolset bindings.
    Returns compiled=False with an error if the draft has no semantics.
    Raises DraftNotFoundError if the draft does not exist.
    """
    draft = repository.load(draft_id, owner_id=owner_id)

    if draft.semantics is None:
        return PlanInspectionResponse(
            draft_id=draft_id,
            compiled=False,
            errors=["draft has no semantics defined; use PUT /drafts/{id}/semantics first"],
            evaluation_plan=None,
            summary=None,
        )

    result  = compile_semantics(draft.semantics, draft_id=draft_id)
    summary = inspect_plan(result.evaluation_plan) if result.evaluation_plan else None
    binding = validate_semantic_bindings(draft.semantics, draft.toolset, registry)

    return PlanInspectionResponse(
        draft_id=draft_id,
        compiled=result.compiled,
        errors=list(result.errors),
        evaluation_plan=result.evaluation_plan,
        summary=summary,
        binding_valid=binding.valid,
        binding_diagnostics=list(binding.diagnostics),
        binding_dependency_summary=binding.summary,
    )


def inspect_semantics_payload(
    semantics: StrategySemantics,
) -> PlanInspectionResponse:
    """
    Compile an arbitrary StrategySemantics payload and inspect the resulting plan.

    No draft loading. No binding validation. No state mutation.
    """
    result  = compile_semantics(semantics, draft_id=None)
    summary = inspect_plan(result.evaluation_plan) if result.evaluation_plan else None

    return PlanInspectionResponse(
        draft_id=None,
        compiled=result.compiled,
        errors=list(result.errors),
        evaluation_plan=result.evaluation_plan,
        summary=summary,
    )
