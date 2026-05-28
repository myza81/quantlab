"""
Draft API routes — Phase 2N.9.

Thin layer delegating to draft_service. No business logic in routes.

Endpoints:
    GET    /drafts                     — list all active drafts
    POST   /drafts                     — create a new draft
    GET    /drafts/{draft_id}          — retrieve a single draft
    PUT    /drafts/{draft_id}          — partial update a draft
    POST   /drafts/{draft_id}/archive  — archive (soft-delete) a draft
    DELETE /drafts/{draft_id}          — hard-delete a draft
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from backend.api.schemas.drafts import (
    DraftCreateRequest,
    DraftListResponse,
    DraftResponse,
    DraftUpdateRequest,
)
from backend.api.services import draft_service
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.strategy_registry.draft_repository import (
    DraftAlreadyExistsError,
    DraftNotFoundError,
    DraftRepository,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/drafts", tags=["drafts"])

_DEFAULT_STORAGE = Path("storage/strategy_drafts")


def get_draft_repository() -> DraftRepository:
    """Dependency — overridable in tests via app.dependency_overrides."""
    return DraftRepository(_DEFAULT_STORAGE)


@router.get("", response_model=DraftListResponse)
def list_drafts(
    repository: DraftRepository = Depends(get_draft_repository),
    current_user: User = Depends(require_active_subscription),
) -> DraftListResponse:
    return draft_service.list_drafts(repository, user_id=current_user.user_id)


@router.post("", response_model=DraftResponse, status_code=201)
def create_draft(
    request: DraftCreateRequest,
    repository: DraftRepository = Depends(get_draft_repository),
    current_user: User = Depends(require_active_subscription),
) -> DraftResponse:
    try:
        return draft_service.create_draft(request, repository, user_id=current_user.user_id)
    except DraftAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{draft_id}", response_model=DraftResponse)
def get_draft(
    draft_id: str,
    repository: DraftRepository = Depends(get_draft_repository),
    current_user: User = Depends(require_active_subscription),
) -> DraftResponse:
    try:
        return draft_service.get_draft(draft_id, repository, owner_id=current_user.user_id)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{draft_id}", response_model=DraftResponse)
def update_draft(
    draft_id: str,
    request: DraftUpdateRequest,
    repository: DraftRepository = Depends(get_draft_repository),
    current_user: User = Depends(require_active_subscription),
) -> DraftResponse:
    try:
        return draft_service.update_draft(draft_id, request, repository, owner_id=current_user.user_id)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{draft_id}/archive", status_code=204)
def archive_draft(
    draft_id: str,
    repository: DraftRepository = Depends(get_draft_repository),
    current_user: User = Depends(require_active_subscription),
) -> None:
    try:
        draft_service.archive_draft(draft_id, repository, owner_id=current_user.user_id)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{draft_id}", status_code=204)
def delete_draft(
    draft_id: str,
    repository: DraftRepository = Depends(get_draft_repository),
    current_user: User = Depends(require_active_subscription),
) -> None:
    try:
        draft_service.delete_draft(draft_id, repository, owner_id=current_user.user_id)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
