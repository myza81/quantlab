"""
Draft service — Phase 2N.9.

Thin orchestration layer between the /drafts routes and DraftRepository.
Responsibilities: timestamp injection, schema conversion, repository delegation.
No business logic beyond coordinating its dependencies.
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.api.schemas.drafts import (
    DraftCreateRequest,
    DraftListResponse,
    DraftResponse,
    DraftUpdateRequest,
)
from backend.strategy_registry.draft_repository import DraftRepository
from backend.strategy_registry.drafts import StrategyDraft

_UTC = timezone.utc


def _to_response(draft: StrategyDraft) -> DraftResponse:
    """Convert a StrategyDraft domain object to its API response schema."""
    return DraftResponse.model_validate(draft.model_dump())


def create_draft(request: DraftCreateRequest, repository: DraftRepository) -> DraftResponse:
    """Build and persist a new StrategyDraft from the create request."""
    now = datetime.now(_UTC)
    draft = StrategyDraft(
        draft_id=request.draft_id,
        display_name=request.display_name,
        description=request.description,
        toolset=request.toolset,
        created_at=now,
        updated_at=now,
        enabled=request.enabled,
        tags=tuple(request.tags),
        notes=request.notes,
    )
    repository.save(draft)
    return _to_response(draft)


def get_draft(draft_id: str, repository: DraftRepository) -> DraftResponse:
    """Load and return a single active draft."""
    draft = repository.load(draft_id)
    return _to_response(draft)


def list_drafts(repository: DraftRepository) -> DraftListResponse:
    """Return all active drafts sorted by draft_id."""
    drafts = repository.list_all()
    return DraftListResponse(
        drafts=[_to_response(d) for d in drafts],
        count=len(drafts),
    )


def update_draft(
    draft_id: str,
    request: DraftUpdateRequest,
    repository: DraftRepository,
) -> DraftResponse:
    """
    Apply partial updates to an existing draft and persist.

    Only fields explicitly set in the request body are applied.
    Omitted fields retain their existing values.
    updated_at is always refreshed.
    """
    existing = repository.load(draft_id)
    existing_data = existing.model_dump()

    updates = request.model_dump(exclude_unset=True)
    if "tags" in updates and isinstance(updates["tags"], list):
        updates["tags"] = tuple(updates["tags"])
    existing_data.update(updates)
    existing_data["updated_at"] = datetime.now(_UTC)

    updated = StrategyDraft.model_validate(existing_data)
    repository.update(updated)
    return _to_response(updated)


def archive_draft(draft_id: str, repository: DraftRepository) -> None:
    """Move a draft to the archive. It is removed from active listing."""
    repository.archive(draft_id)


def delete_draft(draft_id: str, repository: DraftRepository) -> None:
    """Hard-delete a draft."""
    repository.delete(draft_id)
