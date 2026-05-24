"""
Semantic routes — Phase 2O.1.

Two routers to avoid path collision with draft_composition's POST /{draft_id}/validate.

draft_router  (prefix /drafts):
    GET  /drafts/{draft_id}/semantics            — retrieve stored semantics
    PUT  /drafts/{draft_id}/semantics            — replace semantics (immutable update)
    POST /drafts/{draft_id}/semantics/validate   — validate stored semantics (no persist)

payload_router (prefix /semantics):
    POST /semantics/validate                     — validate arbitrary payload (no draft, no persist)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.api.routes.drafts import get_draft_repository
from backend.api.schemas.semantics import (
    SemanticsResponse,
    SemanticsUpdateRequest,
    SemanticsValidateRequest,
    SemanticsValidationResponse,
)
from backend.api.services.semantic_service import (
    get_semantics,
    set_semantics,
    validate_draft_semantics,
    validate_semantics_payload,
)
from backend.strategy_registry.draft_repository import DraftNotFoundError, DraftRepository

logger = logging.getLogger(__name__)

draft_router   = APIRouter(prefix="/drafts",    tags=["semantics"])
payload_router = APIRouter(prefix="/semantics", tags=["semantics"])


@draft_router.get("/{draft_id}/semantics", response_model=SemanticsResponse)
def get_draft_semantics(
    draft_id: str,
    repository: DraftRepository = Depends(get_draft_repository),
) -> SemanticsResponse:
    try:
        return get_semantics(draft_id, repository)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@draft_router.put("/{draft_id}/semantics", response_model=SemanticsResponse)
def put_draft_semantics(
    draft_id: str,
    request: SemanticsUpdateRequest,
    repository: DraftRepository = Depends(get_draft_repository),
) -> SemanticsResponse:
    try:
        return set_semantics(draft_id, request.semantics, repository)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@draft_router.post("/{draft_id}/semantics/validate", response_model=SemanticsValidationResponse)
def post_validate_draft_semantics(
    draft_id: str,
    repository: DraftRepository = Depends(get_draft_repository),
) -> SemanticsValidationResponse:
    """Validate the semantics currently stored on the draft. Does not persist."""
    try:
        return validate_draft_semantics(draft_id, repository)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@payload_router.post("/validate", response_model=SemanticsValidationResponse)
def post_validate_semantics_payload(
    request: SemanticsValidateRequest,
) -> SemanticsValidationResponse:
    """Validate an arbitrary semantics payload without loading or persisting a draft."""
    return validate_semantics_payload(request.semantics)
