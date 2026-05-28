"""
Semantic Compilation Routes — Phase 2O.4.

Two routers to maintain consistent prefix separation:

draft_router  (prefix /drafts):
    POST /drafts/{draft_id}/semantics/compile
        Compiles the semantics stored on the given draft.
        Returns a passive EvaluationPlan. Does NOT execute.

payload_router (prefix /semantics):
    POST /semantics/compile
        Compiles an arbitrary semantics payload without a draft.
        Useful for pre-flight inspection before persisting.
        Does NOT execute.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.api.routes.drafts import get_draft_repository
from backend.api.routes.tools import get_tool_registry
from backend.api.schemas.semantic_compilation import (
    CompilationResponse,
    CompileRequest,
)
from backend.api.services.semantic_compilation_service import (
    compile_draft_semantics,
    compile_semantics_payload,
)
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.strategy_registry.draft_repository import (
    DraftNotFoundError,
    DraftRepository,
)
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

draft_router   = APIRouter(prefix="/drafts",    tags=["semantic-compilation"])
payload_router = APIRouter(prefix="/semantics", tags=["semantic-compilation"])


@draft_router.post(
    "/{draft_id}/semantics/compile",
    response_model=CompilationResponse,
)
def post_compile_draft_semantics(
    draft_id: str,
    repository: DraftRepository = Depends(get_draft_repository),
    registry:   ToolRegistry    = Depends(get_tool_registry),
    current_user: User = Depends(require_active_subscription),
) -> CompilationResponse:
    """
    Compile the semantics stored on draft `draft_id` into a passive EvaluationPlan.

    Also performs semantic binding validation against the draft's toolset.
    Does NOT execute conditions, compute indicators, or call runtime systems.
    Returns compiled=False with an error if the draft has no semantics.
    """
    try:
        return compile_draft_semantics(draft_id, repository, registry, owner_id=current_user.user_id)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@payload_router.post("/compile", response_model=CompilationResponse)
def post_compile_semantics_payload(
    request: CompileRequest,
) -> CompilationResponse:
    """
    Compile an arbitrary semantics payload into a passive EvaluationPlan.

    No draft loading. No persistence. No execution.
    Useful for inspecting the plan before saving semantics to a draft.
    """
    return compile_semantics_payload(request.semantics)
