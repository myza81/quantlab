"""
Tests for Phase 2N.10 — DraftCompositionService.

Covers:
  - add_tool: append, insert at index, duplicate instance_id, unknown tool_id,
    invalid params, index out of range, updated_at refreshed, persisted
  - remove_tool: removes existing, ToolInstanceNotFoundError, order preserved,
    updated_at refreshed
  - reorder_tools: reorders, missing id, extra id, duplicate in request,
    order deterministic
  - patch_tool: merge params, enabled toggle, display_name, color, missing
    instance_id, invalid params after patch, unrelated params preserved
  - validate_draft: valid passes, invalid returns errors, missing draft raises,
    empty toolset valid, never raises for validation failures
  - immutability: original draft unchanged after each operation
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.api.schemas.draft_composition import (
    AddToolRequest,
    PatchToolRequest,
)
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
from backend.strategy_registry.drafts import StrategyDraft
from backend.tools import ToolRegistry, create_default_registry
from backend.tools.configuration import ToolConfiguration
from backend.tools.toolset import StrategyToolSet

_UTC = timezone.utc
_NOW = datetime(2026, 5, 18, 12, 0, 0, tzinfo=_UTC)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _sma(instance_id: str, period: int, **kw: object) -> ToolConfiguration:
    return ToolConfiguration(
        instance_id=instance_id,
        tool_id="sma",
        parameters={"period": period},
        **kw,
    )


def _toolset(*tools: ToolConfiguration) -> StrategyToolSet:
    return StrategyToolSet(toolset_id="ts1", tools=tools)


def _draft(
    draft_id: str = "alpha",
    *tools: ToolConfiguration,
) -> StrategyDraft:
    if not tools:
        tools = (_sma("sma_fast", 20),)
    return StrategyDraft(
        draft_id=draft_id,
        display_name="Alpha Draft",
        toolset=_toolset(*tools),
        created_at=_NOW,
        updated_at=_NOW,
    )


def _repo(tmp_path: Path) -> DraftRepository:
    return DraftRepository(tmp_path)


def _registry() -> ToolRegistry:
    return create_default_registry()


# ---------------------------------------------------------------------------
# TestAddTool
# ---------------------------------------------------------------------------

class TestAddTool:
    def test_add_appends_by_default(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", _sma("sma_fast", 20)))
        req = AddToolRequest(tool=_sma("sma_slow", 50))
        add_tool("alpha", req, _registry(), repo)
        loaded = repo.load("alpha")
        assert loaded.toolset.instance_ids() == ("sma_fast", "sma_slow")

    def test_add_inserts_at_index_zero(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", _sma("sma_fast", 20)))
        req = AddToolRequest(tool=_sma("sma_slow", 50), index=0)
        add_tool("alpha", req, _registry(), repo)
        loaded = repo.load("alpha")
        assert loaded.toolset.instance_ids()[0] == "sma_slow"

    def test_add_inserts_at_middle_index(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", _sma("sma_fast", 20), _sma("sma_slow", 50)))
        req = AddToolRequest(tool=_sma("sma_mid", 30), index=1)
        add_tool("alpha", req, _registry(), repo)
        ids = repo.load("alpha").toolset.instance_ids()
        assert ids == ("sma_fast", "sma_mid", "sma_slow")

    def test_add_duplicate_instance_id_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", _sma("sma_fast", 20)))
        req = AddToolRequest(tool=_sma("sma_fast", 50))
        with pytest.raises(DraftCompositionError, match="already exists"):
            add_tool("alpha", req, _registry(), repo)

    def test_add_unknown_tool_id_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        bad_tool = ToolConfiguration(
            instance_id="x", tool_id="nonexistent", parameters={}
        )
        req = AddToolRequest(tool=bad_tool)
        with pytest.raises(ToolPatchError):
            add_tool("alpha", req, _registry(), repo)

    def test_add_invalid_params_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        bad_tool = ToolConfiguration(
            instance_id="sma_bad", tool_id="sma", parameters={"period": -1}
        )
        req = AddToolRequest(tool=bad_tool)
        with pytest.raises(ToolPatchError):
            add_tool("alpha", req, _registry(), repo)

    def test_add_index_out_of_range_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", _sma("sma_fast", 20)))
        req = AddToolRequest(tool=_sma("sma_slow", 50), index=99)
        with pytest.raises(ToolOrderError, match="out of range"):
            add_tool("alpha", req, _registry(), repo)

    def test_add_refreshes_updated_at(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        req = AddToolRequest(tool=_sma("sma_slow", 50))
        add_tool("alpha", req, _registry(), repo)
        loaded = repo.load("alpha")
        assert loaded.updated_at > _NOW

    def test_add_persists_to_repository(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        req = AddToolRequest(tool=_sma("sma_slow", 50))
        add_tool("alpha", req, _registry(), repo)
        assert len(repo.load("alpha").toolset) == 2

    def test_add_missing_draft_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        req = AddToolRequest(tool=_sma("sma_fast", 20))
        with pytest.raises(DraftNotFoundError):
            add_tool("ghost", req, _registry(), repo)

    def test_add_returns_draft_response(self, tmp_path: Path) -> None:
        from backend.api.schemas.drafts import DraftResponse
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        req = AddToolRequest(tool=_sma("sma_slow", 50))
        result = add_tool("alpha", req, _registry(), repo)
        assert isinstance(result, DraftResponse)
        assert len(result.toolset.tools) == 2


# ---------------------------------------------------------------------------
# TestRemoveTool
# ---------------------------------------------------------------------------

class TestRemoveTool:
    def test_remove_existing_tool(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", _sma("sma_fast", 20), _sma("sma_slow", 50)))
        remove_tool("alpha", "sma_fast", repo)
        loaded = repo.load("alpha")
        assert loaded.toolset.instance_ids() == ("sma_slow",)

    def test_remove_missing_instance_id_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        with pytest.raises(ToolInstanceNotFoundError, match="not found"):
            remove_tool("alpha", "ghost", repo)

    def test_remove_preserves_remaining_order(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", _sma("a", 10), _sma("b", 20), _sma("c", 30)))
        remove_tool("alpha", "b", repo)
        assert repo.load("alpha").toolset.instance_ids() == ("a", "c")

    def test_remove_refreshes_updated_at(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", _sma("sma_fast", 20), _sma("sma_slow", 50)))
        remove_tool("alpha", "sma_fast", repo)
        assert repo.load("alpha").updated_at > _NOW

    def test_remove_missing_draft_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        with pytest.raises(DraftNotFoundError):
            remove_tool("ghost", "sma_fast", repo)

    def test_remove_result_has_correct_count(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", _sma("a", 10), _sma("b", 20), _sma("c", 30)))
        result = remove_tool("alpha", "b", repo)
        assert len(result.toolset.tools) == 2


# ---------------------------------------------------------------------------
# TestReorderTools
# ---------------------------------------------------------------------------

class TestReorderTools:
    def test_reorder_changes_order(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", _sma("a", 10), _sma("b", 20), _sma("c", 30)))
        reorder_tools("alpha", ["c", "a", "b"], repo)
        assert repo.load("alpha").toolset.instance_ids() == ("c", "a", "b")

    def test_reorder_missing_id_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", _sma("a", 10), _sma("b", 20)))
        with pytest.raises(ToolOrderError, match="missing"):
            reorder_tools("alpha", ["a"], repo)

    def test_reorder_extra_id_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", _sma("a", 10), _sma("b", 20)))
        with pytest.raises(ToolOrderError, match="unexpected"):
            reorder_tools("alpha", ["a", "b", "c"], repo)

    def test_reorder_duplicate_in_request_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", _sma("a", 10), _sma("b", 20)))
        with pytest.raises(ToolOrderError, match="duplicates"):
            reorder_tools("alpha", ["a", "a"], repo)

    def test_reorder_refreshes_updated_at(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", _sma("a", 10), _sma("b", 20)))
        reorder_tools("alpha", ["b", "a"], repo)
        assert repo.load("alpha").updated_at > _NOW

    def test_reorder_identity_no_change(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", _sma("a", 10), _sma("b", 20)))
        reorder_tools("alpha", ["a", "b"], repo)
        assert repo.load("alpha").toolset.instance_ids() == ("a", "b")

    def test_reorder_missing_draft_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        with pytest.raises(DraftNotFoundError):
            reorder_tools("ghost", ["a"], repo)


# ---------------------------------------------------------------------------
# TestPatchTool
# ---------------------------------------------------------------------------

class TestPatchTool:
    def test_patch_merges_parameters(self, tmp_path: Path) -> None:
        tool = ToolConfiguration(
            instance_id="sma_fast", tool_id="sma", parameters={"period": 20}
        )
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", tool))
        req = PatchToolRequest(parameters={"period": 50})
        patch_tool("alpha", "sma_fast", req, _registry(), repo)
        loaded = repo.load("alpha")
        assert loaded.toolset.get_tool("sma_fast").parameters["period"] == 50

    def test_patch_enables_tool(self, tmp_path: Path) -> None:
        tool = ToolConfiguration(
            instance_id="sma_fast", tool_id="sma", parameters={"period": 20}, enabled=True
        )
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", tool))
        req = PatchToolRequest(enabled=False)
        patch_tool("alpha", "sma_fast", req, _registry(), repo)
        assert not repo.load("alpha").toolset.get_tool("sma_fast").enabled

    def test_patch_display_name(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        req = PatchToolRequest(display_name="Fast SMA")
        patch_tool("alpha", "sma_fast", req, _registry(), repo)
        assert repo.load("alpha").toolset.get_tool("sma_fast").display_name == "Fast SMA"

    def test_patch_color(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        req = PatchToolRequest(color="#ff0000")
        patch_tool("alpha", "sma_fast", req, _registry(), repo)
        assert repo.load("alpha").toolset.get_tool("sma_fast").color == "#ff0000"

    def test_patch_missing_instance_id_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        req = PatchToolRequest(enabled=False)
        with pytest.raises(ToolInstanceNotFoundError, match="not found"):
            patch_tool("alpha", "ghost", req, _registry(), repo)

    def test_patch_invalid_params_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        req = PatchToolRequest(parameters={"period": -5})
        with pytest.raises(ToolPatchError):
            patch_tool("alpha", "sma_fast", req, _registry(), repo)

    def test_patch_preserves_other_tools(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", _sma("sma_fast", 20), _sma("sma_slow", 50)))
        req = PatchToolRequest(enabled=False)
        patch_tool("alpha", "sma_fast", req, _registry(), repo)
        loaded = repo.load("alpha")
        assert loaded.toolset.get_tool("sma_slow").enabled is True

    def test_patch_refreshes_updated_at(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        req = PatchToolRequest(enabled=False)
        patch_tool("alpha", "sma_fast", req, _registry(), repo)
        assert repo.load("alpha").updated_at > _NOW

    def test_patch_missing_draft_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        req = PatchToolRequest(enabled=False)
        with pytest.raises(DraftNotFoundError):
            patch_tool("ghost", "sma_fast", req, _registry(), repo)

    def test_patch_multiple_fields(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        req = PatchToolRequest(enabled=False, display_name="Patched", color="#abc")
        patch_tool("alpha", "sma_fast", req, _registry(), repo)
        tool = repo.load("alpha").toolset.get_tool("sma_fast")
        assert tool.enabled is False
        assert tool.display_name == "Patched"
        assert tool.color == "#abc"


# ---------------------------------------------------------------------------
# TestValidateDraft
# ---------------------------------------------------------------------------

class TestValidateDraft:
    def test_valid_draft_returns_valid_true(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        result = validate_draft("alpha", _registry(), repo)
        assert result.valid is True
        assert result.errors == []

    def test_empty_toolset_is_valid(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        draft = StrategyDraft(
            draft_id="empty",
            display_name="Empty Draft",
            toolset=StrategyToolSet(toolset_id="ts1", tools=()),
            created_at=_NOW,
            updated_at=_NOW,
        )
        repo.save(draft)
        result = validate_draft("empty", _registry(), repo)
        assert result.valid is True

    def test_invalid_tool_returns_errors(self, tmp_path: Path) -> None:
        bad_tool = ToolConfiguration(
            instance_id="bad", tool_id="nonexistent", parameters={}
        )
        draft = StrategyDraft(
            draft_id="alpha",
            display_name="Alpha",
            toolset=_toolset(bad_tool),
            created_at=_NOW,
            updated_at=_NOW,
        )
        repo = _repo(tmp_path)
        repo.save(draft)
        result = validate_draft("alpha", _registry(), repo)
        assert result.valid is False
        assert len(result.errors) > 0

    def test_missing_draft_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        with pytest.raises(DraftNotFoundError):
            validate_draft("ghost", _registry(), repo)

    def test_validate_never_raises_for_invalid_toolset(self, tmp_path: Path) -> None:
        bad_tool = ToolConfiguration(
            instance_id="bad", tool_id="nonexistent", parameters={}
        )
        draft = StrategyDraft(
            draft_id="alpha",
            display_name="Alpha",
            toolset=_toolset(bad_tool),
            created_at=_NOW,
            updated_at=_NOW,
        )
        repo = _repo(tmp_path)
        repo.save(draft)
        result = validate_draft("alpha", _registry(), repo)
        assert isinstance(result.errors, list)


# ---------------------------------------------------------------------------
# TestImmutability
# ---------------------------------------------------------------------------

class TestImmutability:
    def test_add_does_not_mutate_original(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        original = _draft("alpha", _sma("sma_fast", 20))
        repo.save(original)
        req = AddToolRequest(tool=_sma("sma_slow", 50))
        add_tool("alpha", req, _registry(), repo)
        assert original.toolset.instance_ids() == ("sma_fast",)

    def test_remove_does_not_mutate_original(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        original = _draft("alpha", _sma("sma_fast", 20), _sma("sma_slow", 50))
        repo.save(original)
        remove_tool("alpha", "sma_fast", repo)
        assert original.toolset.instance_ids() == ("sma_fast", "sma_slow")

    def test_reorder_does_not_mutate_original(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        original = _draft("alpha", _sma("a", 10), _sma("b", 20))
        repo.save(original)
        reorder_tools("alpha", ["b", "a"], repo)
        assert original.toolset.instance_ids() == ("a", "b")

    def test_patch_does_not_mutate_original(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        original = _draft("alpha", _sma("sma_fast", 20))
        repo.save(original)
        req = PatchToolRequest(parameters={"period": 99})
        patch_tool("alpha", "sma_fast", req, _registry(), repo)
        assert original.toolset.get_tool("sma_fast").parameters["period"] == 20
