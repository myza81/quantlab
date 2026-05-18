"""
Draft composition service — Phase 2N.10.

Composition orchestration for StrategyDraft toolsets.

All operations are:
  - immutable: frozen models → new models via model_validate; no in-place mutation
  - deterministic: same inputs produce same persisted JSON
  - persistence-bound: load → transform → validate → update
  - execution-independent: no compute_sma(), no runtime invocation

Workflow per operation:
    repository.load(draft_id)
    → build new StrategyToolSet immutably
    → build new StrategyDraft with bumped updated_at
    → repository.update(updated_draft)
    → return DraftResponse
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.api.schemas.draft_composition import (
    AddToolRequest,
    CompositionValidationResponse,
    PatchToolRequest,
)
from backend.api.schemas.drafts import DraftResponse
from backend.strategy_registry.draft_repository import DraftRepository
from backend.strategy_registry.drafts import StrategyDraft
from backend.tools.configuration import ToolConfiguration
from backend.tools.registry import ToolNotFoundError, ToolRegistry
from backend.tools.toolset import StrategyToolSet
from backend.tools.validation import (
    ConfigurationValidationError,
    validate_tool_configuration,
)

_UTC = timezone.utc


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------

class DraftCompositionError(Exception):
    """Raised on composition conflicts, e.g. duplicate instance_id on add."""


class ToolInstanceNotFoundError(Exception):
    """Raised when the target instance_id is absent from the draft's toolset."""


class ToolOrderError(Exception):
    """Raised when a reorder request is inconsistent with the existing toolset."""


class ToolPatchError(Exception):
    """Raised when a patch produces an invalid tool configuration."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_response(draft: StrategyDraft) -> DraftResponse:
    return DraftResponse.model_validate(draft.model_dump())


def _rebuild_draft(draft: StrategyDraft, new_toolset: StrategyToolSet) -> StrategyDraft:
    """Return a new StrategyDraft with an updated toolset and refreshed updated_at."""
    data = draft.model_dump()
    data["toolset"] = new_toolset.model_dump()
    data["updated_at"] = datetime.now(_UTC)
    return StrategyDraft.model_validate(data)


def _new_toolset(old_toolset: StrategyToolSet, tools: list[ToolConfiguration]) -> StrategyToolSet:
    """Build a new StrategyToolSet from the old toolset metadata + new tools list."""
    data = old_toolset.model_dump()
    data["tools"] = [t.model_dump() for t in tools]
    return StrategyToolSet.model_validate(data)


def _validate_tool_against_registry(tool: ToolConfiguration, registry: ToolRegistry) -> None:
    """Validate a single ToolConfiguration against the registry. Raises ToolPatchError on failure."""
    try:
        metadata = registry.get(tool.tool_id)
    except ToolNotFoundError:
        raise ToolPatchError([f"tool_id '{tool.tool_id}' not found in registry"])

    try:
        validate_tool_configuration(tool, metadata)
    except ConfigurationValidationError as exc:
        raise ToolPatchError(exc.errors)


# ---------------------------------------------------------------------------
# Composition operations
# ---------------------------------------------------------------------------

def add_tool(
    draft_id: str,
    request: AddToolRequest,
    registry: ToolRegistry,
    repository: DraftRepository,
) -> DraftResponse:
    """
    Add a ToolConfiguration to the draft's toolset.

    Validates the tool against the registry.
    Rejects duplicate instance_id with DraftCompositionError (409).
    Inserts at request.index if provided, otherwise appends.
    Raises ToolOrderError if index is out of range.
    Raises ToolPatchError if registry validation fails.
    """
    draft = repository.load(draft_id)
    tool = request.tool

    if tool.instance_id in draft.toolset:
        raise DraftCompositionError(
            f"instance_id '{tool.instance_id}' already exists in draft '{draft_id}'"
        )

    _validate_tool_against_registry(tool, registry)

    tools = list(draft.toolset.tools)
    if request.index is None:
        tools.append(tool)
    else:
        if request.index < 0 or request.index > len(tools):
            raise ToolOrderError(
                f"index {request.index} out of range for toolset of length {len(tools)}"
            )
        tools.insert(request.index, tool)

    updated = _rebuild_draft(draft, _new_toolset(draft.toolset, tools))
    repository.update(updated)
    return _to_response(updated)


def remove_tool(
    draft_id: str,
    instance_id: str,
    repository: DraftRepository,
) -> DraftResponse:
    """
    Remove a tool by instance_id from the draft's toolset.

    Raises ToolInstanceNotFoundError if instance_id is absent.
    """
    draft = repository.load(draft_id)
    key = instance_id.strip().lower()

    if key not in draft.toolset:
        raise ToolInstanceNotFoundError(
            f"instance_id '{key}' not found in draft '{draft_id}'"
        )

    tools = [t for t in draft.toolset.tools if t.instance_id != key]
    updated = _rebuild_draft(draft, _new_toolset(draft.toolset, tools))
    repository.update(updated)
    return _to_response(updated)


def reorder_tools(
    draft_id: str,
    ordered_instance_ids: list[str],
    repository: DraftRepository,
) -> DraftResponse:
    """
    Reorder the draft's toolset tools.

    ordered_instance_ids must be an exact permutation of the current toolset's
    instance_ids — no additions, no omissions, no duplicates.

    Raises ToolOrderError if the request is inconsistent.
    """
    draft = repository.load(draft_id)
    current_ids = set(draft.toolset.instance_ids())
    normalized = [iid.strip().lower() for iid in ordered_instance_ids]

    if len(normalized) != len(set(normalized)):
        raise ToolOrderError("ordered_instance_ids must not contain duplicates")

    requested_ids = set(normalized)
    if current_ids != requested_ids:
        missing = sorted(current_ids - requested_ids)
        extra = sorted(requested_ids - current_ids)
        parts: list[str] = []
        if missing:
            parts.append(f"missing from request: {missing}")
        if extra:
            parts.append(f"unexpected in request: {extra}")
        raise ToolOrderError(
            "ordered_instance_ids must be a permutation of existing tool ids; "
            + ", ".join(parts)
        )

    tool_index = {t.instance_id: t for t in draft.toolset.tools}
    reordered = [tool_index[iid] for iid in normalized]

    updated = _rebuild_draft(draft, _new_toolset(draft.toolset, reordered))
    repository.update(updated)
    return _to_response(updated)


def patch_tool(
    draft_id: str,
    instance_id: str,
    request: PatchToolRequest,
    registry: ToolRegistry,
    repository: DraftRepository,
) -> DraftResponse:
    """
    Patch a single tool's parameters, enabled state, display_name, or color.

    Parameters are merged into the existing parameter dict: keys present in
    request.parameters are updated; all other existing keys are preserved.

    When parameters are changed, the resulting ToolConfiguration is validated
    against the registry.  Raises ToolPatchError if validation fails.

    Raises ToolInstanceNotFoundError if instance_id is absent.
    """
    draft = repository.load(draft_id)
    key = instance_id.strip().lower()

    existing = draft.toolset.get_tool(key)
    if existing is None:
        raise ToolInstanceNotFoundError(
            f"instance_id '{key}' not found in draft '{draft_id}'"
        )

    tool_data = existing.model_dump()

    if request.parameters is not None:
        tool_data["parameters"] = {**tool_data["parameters"], **request.parameters}
    if request.enabled is not None:
        tool_data["enabled"] = request.enabled
    if request.display_name is not None:
        tool_data["display_name"] = request.display_name
    if request.color is not None:
        tool_data["color"] = request.color

    patched = ToolConfiguration.model_validate(tool_data)

    if request.parameters is not None:
        _validate_tool_against_registry(patched, registry)

    tools = [patched if t.instance_id == key else t for t in draft.toolset.tools]
    updated = _rebuild_draft(draft, _new_toolset(draft.toolset, tools))
    repository.update(updated)
    return _to_response(updated)


def validate_draft(
    draft_id: str,
    registry: ToolRegistry,
    repository: DraftRepository,
) -> CompositionValidationResponse:
    """
    Validate the draft's toolset against the registry.

    Never raises — validation errors are surfaced in the response body.
    """
    draft = repository.load(draft_id)
    result = draft.validate_against_registry(registry)
    return CompositionValidationResponse(
        valid=result.valid,
        errors=list(result.errors),
    )
