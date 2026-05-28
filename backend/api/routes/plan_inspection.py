"""
Plan Inspection Routes — Phase 2O.7.

Two routers maintaining the established prefix-separation pattern:

draft_router   (prefix /drafts):
    GET /drafts/{draft_id}/semantics/plan
        Compiles the stored semantics and returns a passive EvaluationPlan
        inspection response including topology, dependency, and binding summaries.
        Does NOT evaluate. Does NOT execute.

payload_router (prefix /semantics):
    POST /semantics/plan
        Compiles an arbitrary semantics payload and returns inspection response.
        No draft loading. No persistence. No binding validation.
        Does NOT evaluate. Does NOT execute.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.api.routes.drafts import get_draft_repository
from backend.api.routes.tools import get_tool_registry
from backend.api.schemas.plan_inspection import (
    PlanInspectionRequest,
    PlanInspectionResponse,
)
from backend.api.services.plan_inspection_service import (
    inspect_draft_plan,
    inspect_semantics_payload,
)
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.strategy_registry.draft_repository import (
    DraftNotFoundError,
    DraftRepository,
)
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

draft_router   = APIRouter(prefix="/drafts",    tags=["plan-inspection"])
payload_router = APIRouter(prefix="/semantics", tags=["plan-inspection"])


@draft_router.get(
    "/{draft_id}/semantics/plan",
    response_model=PlanInspectionResponse,
)
def get_draft_plan_inspection(
    draft_id:   str,
    repository: DraftRepository = Depends(get_draft_repository),
    registry:   ToolRegistry    = Depends(get_tool_registry),
    current_user: User = Depends(require_active_subscription),
) -> PlanInspectionResponse:
    """
    Compile the stored semantics and return a passive EvaluationPlan inspection.

    Includes topology summary, dependency summary, and binding validation
    against the draft's toolset. Does NOT evaluate conditions or compute anything.
    Returns compiled=False with an error if the draft has no semantics.
    """
    try:
        return inspect_draft_plan(draft_id, repository, registry, owner_id=current_user.user_id)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@payload_router.post(
    "/plan",
    response_model=PlanInspectionResponse,
)
def post_semantics_plan_inspection(
    request: PlanInspectionRequest,
) -> PlanInspectionResponse:
    """
    Compile an arbitrary semantics payload and return a passive inspection response.

    No draft loading. No binding validation (no toolset context).
    Useful for inspecting plan topology before saving semantics to a draft.
    Does NOT evaluate. Does NOT execute.
    """
    return inspect_semantics_payload(request.semantics)
