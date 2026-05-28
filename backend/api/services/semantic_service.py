"""
Semantic service — Phase 2O.1.

Thin orchestration layer between semantics routes and domain infrastructure.
Responsibilities: load draft, apply semantic update immutably, delegate validation.

No business logic beyond coordinate-and-return. No runtime evaluation.
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.api.schemas.semantics import (
    SemanticsResponse,
    SemanticsValidationResponse,
)
from backend.strategy_registry.draft_repository import DraftRepository
from backend.strategy_registry.drafts import StrategyDraft
from backend.strategy_registry.semantic_identity import inject_ids
from backend.strategy_registry.semantic_validator import validate_semantics_structure
from backend.strategy_registry.semantics import StrategySemantics

_UTC = timezone.utc


def _rebuild_with_semantics(
    draft: StrategyDraft,
    semantics: StrategySemantics | None,
) -> StrategyDraft:
    """Return a new immutable StrategyDraft with semantics replaced."""
    data = draft.model_dump()
    data["semantics"] = semantics.model_dump() if semantics is not None else None
    data["updated_at"] = datetime.now(_UTC)
    return StrategyDraft.model_validate(data)


def get_semantics(
    draft_id: str,
    repository: DraftRepository,
    owner_id: str | None = None,
) -> SemanticsResponse:
    """
    Return the semantics currently stored on a draft.

    Raises DraftNotFoundError if the draft does not exist.
    """
    draft = repository.load(draft_id, owner_id=owner_id)
    return SemanticsResponse(draft_id=draft.draft_id, semantics=draft.semantics)


def set_semantics(
    draft_id: str,
    semantics: StrategySemantics,
    repository: DraftRepository,
    owner_id: str | None = None,
) -> SemanticsResponse:
    """
    Replace the semantics on a draft with the provided StrategySemantics.

    Performs an immutable rebuild (model_dump → model_validate round-trip)
    and bumps updated_at. Persists via repository.update().

    Raises DraftNotFoundError if the draft does not exist.
    """
    draft = repository.load(draft_id, owner_id=owner_id)
    updated = _rebuild_with_semantics(draft, inject_ids(semantics))
    repository.update(updated, owner_id=owner_id)
    return SemanticsResponse(draft_id=updated.draft_id, semantics=updated.semantics)


def validate_draft_semantics(
    draft_id: str,
    repository: DraftRepository,
    owner_id: str | None = None,
) -> SemanticsValidationResponse:
    """
    Structurally validate the semantics currently stored on a draft.

    Returns valid=False with an error message if the draft has no semantics.
    Never raises for structural issues — errors are returned in the response.
    Raises DraftNotFoundError if the draft does not exist.
    """
    draft = repository.load(draft_id, owner_id=owner_id)
    if draft.semantics is None:
        return SemanticsValidationResponse(
            valid=False,
            errors=["draft has no semantics defined; use PUT /drafts/{id}/semantics first"],
        )
    result = validate_semantics_structure(draft.semantics)
    return SemanticsValidationResponse(valid=result.valid, errors=result.errors)


def validate_semantics_payload(
    semantics: StrategySemantics,
) -> SemanticsValidationResponse:
    """
    Structurally validate a StrategySemantics payload without persisting.

    Useful for client-side pre-flight checks before committing via PUT.
    No draft loading, no repository interaction.
    """
    result = validate_semantics_structure(semantics)
    return SemanticsValidationResponse(valid=result.valid, errors=result.errors)
