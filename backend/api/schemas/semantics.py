"""
Semantic API schemas — Phase 2O.1.

Passive data-transfer types for the /drafts/{id}/semantics endpoints.
No business logic, no runtime evaluation.

The domain model (StrategySemantics) is used directly as the payload type
since it is already a clean, frozen Pydantic v2 model suitable for API exposure.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from backend.strategy_registry.semantics import StrategySemantics


class SemanticsUpdateRequest(BaseModel):
    """Request body for PUT /drafts/{draft_id}/semantics."""
    model_config = ConfigDict(extra="forbid")

    semantics: StrategySemantics


class SemanticsValidateRequest(BaseModel):
    """Request body for POST /drafts/{draft_id}/semantics/validate."""
    model_config = ConfigDict(extra="forbid")

    semantics: StrategySemantics


class SemanticsValidationResponse(BaseModel):
    """Structural validation result for a StrategySemantics payload."""
    valid:  bool
    errors: list[str]


class SemanticsResponse(BaseModel):
    """Response for GET /drafts/{draft_id}/semantics."""
    draft_id:  str
    semantics: StrategySemantics | None
