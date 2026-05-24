"""
Semantic Binding Routes — Phase 2O.5.

router (prefix /drafts):
    POST /drafts/{draft_id}/semantics/validate-bindings
        Validates that all tool_output references in the draft's semantics
        resolve to actual configured tool instances in the draft's toolset.
        Returns binding diagnostics and a dependency summary.
        Does NOT execute semantics or compute anything.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.api.routes.drafts import get_draft_repository
from backend.api.routes.tools import get_tool_registry
from backend.api.schemas.semantic_binding import BindingValidationResponse
from backend.api.services.semantic_binding_service import validate_draft_bindings
from backend.strategy_registry.draft_repository import (
    DraftNotFoundError,
    DraftRepository,
)
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/drafts", tags=["semantic-binding"])


@router.post(
    "/{draft_id}/semantics/validate-bindings",
    response_model=BindingValidationResponse,
)
def post_validate_bindings(
    draft_id:   str,
    repository: DraftRepository = Depends(get_draft_repository),
    registry:   ToolRegistry    = Depends(get_tool_registry),
) -> BindingValidationResponse:
    """
    Validate that all semantic tool_output references resolve in the draft's toolset.

    Checks:
    - instance_id exists in draft's StrategyToolSet
    - output_name is declared in the tool's registry metadata

    Does NOT evaluate semantics, compute indicators, or call runtime systems.
    Returns valid=False if the draft has no semantics or any ref is unresolvable.
    """
    try:
        return validate_draft_bindings(draft_id, repository, registry)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
