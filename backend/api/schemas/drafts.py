"""
Draft API schemas — Phase 2N.9.

Request and response models for the /drafts REST endpoints.
These are passive data-transfer types only. No execution or validation logic.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from backend.tools.toolset import StrategyToolSet


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class DraftCreateRequest(BaseModel):
    """Request body for POST /drafts."""

    model_config = ConfigDict(extra="forbid")

    draft_id: str
    display_name: str
    description: str | None = None
    toolset: StrategyToolSet
    enabled: bool = True
    tags: list[str] = []
    notes: str | None = None


class DraftUpdateRequest(BaseModel):
    """
    Request body for PUT /drafts/{draft_id}.

    All fields are optional. Only explicitly provided fields are applied.
    Omitting a field leaves the existing value unchanged.
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    description: str | None = None
    toolset: StrategyToolSet | None = None
    enabled: bool | None = None
    tags: list[str] | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class DraftToolConfigResponse(BaseModel):
    instance_id: str
    tool_id: str
    parameters: dict[str, Any]
    enabled: bool
    display_name: str | None
    color: str | None


class DraftToolSetResponse(BaseModel):
    toolset_id: str
    display_name: str | None
    tools: list[DraftToolConfigResponse]
    enabled: bool


class DraftResponse(BaseModel):
    draft_id: str
    display_name: str
    description: str | None
    toolset: DraftToolSetResponse
    created_at: datetime
    updated_at: datetime
    enabled: bool
    tags: list[str]
    notes: str | None


class DraftListResponse(BaseModel):
    drafts: list[DraftResponse]
    count: int
