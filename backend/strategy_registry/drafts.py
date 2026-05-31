"""
StrategyDraft — Phase 2N.8.

A StrategyDraft is a structured, deterministic research object that groups a
StrategyToolSet under stable identity and human-readable metadata.

It is NOT an execution engine, runtime, or backtest container.

Layer contract:
    ToolMetadata ≠ ToolConfiguration ≠ StrategyToolSet ≠ StrategyDraft ≠ Runtime Execution
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, field_validator

from backend.strategy_registry.lifecycle import StrategyLifecycleStatus
from backend.strategy_registry.semantics import StrategySemantics
from backend.tools.registry import ToolRegistry
from backend.tools.toolset import StrategyToolSet
from backend.tools.validation import (
    ToolSetValidationResult,
    validate_strategy_toolset_against_registry,
)


class StrategyDraft(BaseModel):
    """
    Deterministic, serializable strategy research draft.

    Contains stable identity, human-readable metadata, and an associated
    StrategyToolSet. Supports registry-backed validation without executing tools.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    draft_id: str
    display_name: str
    description: str | None = None
    toolset: StrategyToolSet
    created_at: datetime
    updated_at: datetime
    enabled: bool = True
    tags: tuple[str, ...] = ()
    notes: str | None = None
    user_id: str | None = None
    semantics: StrategySemantics | None = None
    lifecycle_status: StrategyLifecycleStatus = StrategyLifecycleStatus.DRAFT

    @field_validator("draft_id")
    @classmethod
    def _draft_id_valid(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("draft_id must not be empty or whitespace")
        return stripped.lower()

    @field_validator("display_name")
    @classmethod
    def _display_name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("display_name must not be empty or whitespace")
        return v

    @field_validator("created_at", "updated_at")
    @classmethod
    def _must_be_utc_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("datetime fields must be UTC-aware; naive datetime rejected")
        return v.astimezone(timezone.utc)

    def validate_against_registry(self, registry: ToolRegistry) -> ToolSetValidationResult:
        """Validate the draft's toolset against the registry. Never raises."""
        return validate_strategy_toolset_against_registry(self.toolset, registry)
