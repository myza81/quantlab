"""
Draft composition schemas — Phase 2N.10.

Request and response models for draft composition endpoints.
These are passive data-transfer types only. No execution or validation logic.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from backend.tools.configuration import ToolConfiguration


class AddToolRequest(BaseModel):
    """Request body for POST /drafts/{draft_id}/tools."""

    model_config = ConfigDict(extra="forbid")

    tool: ToolConfiguration
    index: int | None = None  # insertion position; None = append at end


class ReorderToolsRequest(BaseModel):
    """Request body for POST /drafts/{draft_id}/tools/reorder."""

    model_config = ConfigDict(extra="forbid")

    ordered_instance_ids: list[str]


class PatchToolRequest(BaseModel):
    """
    Request body for PATCH /drafts/{draft_id}/tools/{instance_id}.

    All fields are optional. Only fields explicitly provided are applied.
    parameters are merged into the existing dict — keys not present in the
    request are preserved unchanged.
    """

    model_config = ConfigDict(extra="forbid")

    parameters: dict[str, Any] | None = None
    enabled: bool | None = None
    display_name: str | None = None
    color: str | None = None


class CompositionValidationResponse(BaseModel):
    """Response body for POST /drafts/{draft_id}/validate."""

    valid: bool
    errors: list[str]
    lifecycle_promoted: bool = False
