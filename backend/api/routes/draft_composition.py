"""
Draft composition routes — Phase 2N.10.

Thin layer delegating to draft_composition_service. No business logic in routes.

Endpoints:
    POST   /drafts/{draft_id}/tools                     — add a tool to the toolset
    DELETE /drafts/{draft_id}/tools/{instance_id}       — remove a tool by instance_id
    POST   /drafts/{draft_id}/tools/reorder             — reorder tools
    PATCH  /drafts/{draft_id}/tools/{instance_id}       — patch tool params / state
    POST   /drafts/{draft_id}/validate                  — validate against registry
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.api.routes.drafts import get_draft_repository
from backend.api.routes.tools import get_tool_registry
from backend.api.schemas.draft_composition import (
    AddToolRequest,
    CompositionValidationResponse,
    PatchToolRequest,
    ReorderToolsRequest,
)
from backend.api.schemas.drafts import DraftResponse
from backend.api.services.draft_composition_service import (
    DraftCompositionError,
    ToolInstanceNotFoundError,
    ToolOrderError,
    ToolPatchError,
    add_tool,
    patch_tool,
    remove_tool,
    reorder_tools,
    validate_draft,
)
from backend.strategy_registry.draft_repository import DraftNotFoundError, DraftRepository
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/drafts", tags=["draft-composition"])


@router.post("/{draft_id}/tools", response_model=DraftResponse)
def post_add_tool(
    draft_id: str,
    request: AddToolRequest,
    registry: ToolRegistry = Depends(get_tool_registry),
    repository: DraftRepository = Depends(get_draft_repository),
) -> DraftResponse:
    try:
        return add_tool(draft_id, request, registry, repository)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DraftCompositionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ToolPatchError, ToolOrderError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{draft_id}/tools/{instance_id}", response_model=DraftResponse)
def delete_remove_tool(
    draft_id: str,
    instance_id: str,
    repository: DraftRepository = Depends(get_draft_repository),
) -> DraftResponse:
    try:
        return remove_tool(draft_id, instance_id, repository)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolInstanceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{draft_id}/tools/reorder", response_model=DraftResponse)
def post_reorder_tools(
    draft_id: str,
    request: ReorderToolsRequest,
    repository: DraftRepository = Depends(get_draft_repository),
) -> DraftResponse:
    try:
        return reorder_tools(draft_id, request.ordered_instance_ids, repository)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolOrderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{draft_id}/tools/{instance_id}", response_model=DraftResponse)
def patch_patch_tool(
    draft_id: str,
    instance_id: str,
    request: PatchToolRequest,
    registry: ToolRegistry = Depends(get_tool_registry),
    repository: DraftRepository = Depends(get_draft_repository),
) -> DraftResponse:
    try:
        return patch_tool(draft_id, instance_id, request, registry, repository)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolInstanceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolPatchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{draft_id}/validate", response_model=CompositionValidationResponse)
def post_validate_draft(
    draft_id: str,
    registry: ToolRegistry = Depends(get_tool_registry),
    repository: DraftRepository = Depends(get_draft_repository),
) -> CompositionValidationResponse:
    try:
        return validate_draft(draft_id, registry, repository)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
