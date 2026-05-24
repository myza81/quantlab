"""
Evaluation Readiness Routes — Phase 2O.9.

Two routers following the established prefix-separation pattern:

draft_router   (prefix /drafts):
    GET /drafts/{draft_id}/semantics/readiness
        Compiles stored semantics, validates bindings, runs readiness lint.
        Returns blocking/warning/info issues and an overall ready flag.
        Does NOT evaluate. Does NOT execute.

payload_router (prefix /semantics):
    POST /semantics/readiness
        Lints an arbitrary semantics payload.
        No draft loading. No binding validation.
        Does NOT evaluate. Does NOT execute.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.api.routes.drafts import get_draft_repository
from backend.api.routes.tools import get_tool_registry
from backend.api.schemas.evaluation_readiness import (
    EvaluationReadinessRequest,
    EvaluationReadinessResponse,
)
from backend.api.services.evaluation_readiness_service import (
    check_draft_readiness,
    check_semantics_payload_readiness,
)
from backend.strategy_registry.draft_repository import (
    DraftNotFoundError,
    DraftRepository,
)
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

draft_router   = APIRouter(prefix="/drafts",    tags=["evaluation-readiness"])
payload_router = APIRouter(prefix="/semantics", tags=["evaluation-readiness"])


@draft_router.get(
    "/{draft_id}/semantics/readiness",
    response_model=EvaluationReadinessResponse,
)
def get_draft_readiness(
    draft_id:   str,
    repository: DraftRepository = Depends(get_draft_repository),
    registry:   ToolRegistry    = Depends(get_tool_registry),
) -> EvaluationReadinessResponse:
    """
    Run evaluation readiness lint against the draft's compiled semantics.

    Compiles semantics, validates bindings against the draft's toolset, and
    runs all static readiness checks. Returns a ready flag, status, and
    per-issue list. Does NOT evaluate conditions or generate signals.
    """
    try:
        return check_draft_readiness(draft_id, repository, registry)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@payload_router.post(
    "/readiness",
    response_model=EvaluationReadinessResponse,
)
def post_semantics_readiness(
    request: EvaluationReadinessRequest,
) -> EvaluationReadinessResponse:
    """
    Run evaluation readiness lint against an arbitrary semantics payload.

    No draft loading. No binding validation (no toolset context).
    Useful for checking plan readiness before saving semantics to a draft.
    Does NOT evaluate. Does NOT execute.
    """
    return check_semantics_payload_readiness(request.semantics)
