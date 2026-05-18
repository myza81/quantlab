"""
Tests for Phase 2N.8 — StrategyDraft Contracts.

Covers:
  - StrategyDraft construction and field defaults
  - draft_id normalization (lowercase, strip)
  - display_name and description validation
  - UTC datetime enforcement (naive rejected, non-UTC normalized)
  - Frozen model invariants (immutable fields, extra fields rejected)
  - validate_against_registry() — valid toolset, invalid toolset, never raises
  - Serialization determinism (model_dump, model_dump_json)
  - Layer separation: no compute_sma(), independence from runtime execution
  - Tags as tuple of strings
"""
import json
from datetime import datetime, timezone, timedelta

import pytest
from pydantic import ValidationError

from backend.strategy_registry.drafts import StrategyDraft
from backend.tools import (
    StrategyToolSet,
    ToolConfiguration,
    ToolRegistry,
    ToolSetValidationResult,
    create_default_registry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

UTC = timezone.utc
_NOW = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
_LATER = datetime(2026, 5, 18, 13, 0, 0, tzinfo=UTC)


def _sma(instance_id: str, period: int) -> ToolConfiguration:
    return ToolConfiguration(
        instance_id=instance_id,
        tool_id="sma",
        parameters={"period": period},
    )


def _toolset(*tools: ToolConfiguration, toolset_id: str = "ts1") -> StrategyToolSet:
    return StrategyToolSet(toolset_id=toolset_id, tools=tools)


def _draft(
    draft_id: str = "draft_alpha",
    display_name: str = "Alpha Draft",
    toolset: StrategyToolSet | None = None,
    **kw: object,
) -> StrategyDraft:
    if toolset is None:
        toolset = _toolset(_sma("sma_fast", 20))
    return StrategyDraft(
        draft_id=draft_id,
        display_name=display_name,
        toolset=toolset,
        created_at=_NOW,
        updated_at=_LATER,
        **kw,
    )


# ---------------------------------------------------------------------------
# TestStrategyDraftConstruction
# ---------------------------------------------------------------------------

class TestStrategyDraftConstruction:
    def test_basic_construction(self) -> None:
        d = _draft()
        assert d.draft_id == "draft_alpha"
        assert d.display_name == "Alpha Draft"

    def test_draft_id_lowercased(self) -> None:
        d = _draft(draft_id="TREND_FOLLOW_V1")
        assert d.draft_id == "trend_follow_v1"

    def test_draft_id_stripped(self) -> None:
        d = _draft(draft_id="  my_draft  ")
        assert d.draft_id == "my_draft"

    def test_draft_id_empty_raises(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            _draft(draft_id="")

    def test_draft_id_whitespace_only_raises(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            _draft(draft_id="   ")

    def test_display_name_preserved(self) -> None:
        d = _draft(display_name="Trend Following Prototype")
        assert d.display_name == "Trend Following Prototype"

    def test_display_name_empty_raises(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            _draft(display_name="")

    def test_display_name_whitespace_only_raises(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            _draft(display_name="   ")

    def test_description_defaults_to_none(self) -> None:
        d = _draft()
        assert d.description is None

    def test_description_set(self) -> None:
        d = _draft(description="MA crossover research")
        assert d.description == "MA crossover research"

    def test_enabled_defaults_to_true(self) -> None:
        d = _draft()
        assert d.enabled is True

    def test_enabled_can_be_false(self) -> None:
        d = _draft(enabled=False)
        assert d.enabled is False

    def test_tags_default_empty_tuple(self) -> None:
        d = _draft()
        assert d.tags == ()
        assert isinstance(d.tags, tuple)

    def test_tags_set_as_tuple(self) -> None:
        d = _draft(tags=("momentum", "crypto"))
        assert d.tags == ("momentum", "crypto")
        assert isinstance(d.tags, tuple)

    def test_notes_defaults_to_none(self) -> None:
        d = _draft()
        assert d.notes is None

    def test_notes_set(self) -> None:
        d = _draft(notes="Needs parameter tuning")
        assert d.notes == "Needs parameter tuning"

    def test_toolset_stored(self) -> None:
        ts = _toolset(_sma("a", 20), _sma("b", 50))
        d = _draft(toolset=ts)
        assert len(d.toolset) == 2

    def test_importable_from_drafts_module(self) -> None:
        from backend.strategy_registry.drafts import StrategyDraft as _D
        assert _D is StrategyDraft


# ---------------------------------------------------------------------------
# TestStrategyDraftDatetimes
# ---------------------------------------------------------------------------

class TestStrategyDraftDatetimes:
    def test_created_at_stored_as_utc(self) -> None:
        d = _draft()
        assert d.created_at.tzinfo == UTC

    def test_updated_at_stored_as_utc(self) -> None:
        d = _draft()
        assert d.updated_at.tzinfo == UTC

    def test_naive_created_at_raises(self) -> None:
        with pytest.raises(ValidationError, match="UTC-aware"):
            StrategyDraft(
                draft_id="x",
                display_name="X",
                toolset=_toolset(_sma("a", 10)),
                created_at=datetime(2026, 1, 1),   # naive
                updated_at=_LATER,
            )

    def test_naive_updated_at_raises(self) -> None:
        with pytest.raises(ValidationError, match="UTC-aware"):
            StrategyDraft(
                draft_id="x",
                display_name="X",
                toolset=_toolset(_sma("a", 10)),
                created_at=_NOW,
                updated_at=datetime(2026, 1, 1),   # naive
            )

    def test_non_utc_aware_datetime_normalized_to_utc(self) -> None:
        eastern = timezone(timedelta(hours=-5))
        non_utc = datetime(2026, 5, 18, 7, 0, 0, tzinfo=eastern)
        d = StrategyDraft(
            draft_id="x",
            display_name="X",
            toolset=_toolset(_sma("a", 10)),
            created_at=non_utc,
            updated_at=_LATER,
        )
        assert d.created_at.tzinfo == UTC
        assert d.created_at.hour == 12


# ---------------------------------------------------------------------------
# TestStrategyDraftFrozen
# ---------------------------------------------------------------------------

class TestStrategyDraftFrozen:
    def test_cannot_mutate_draft_id(self) -> None:
        d = _draft()
        with pytest.raises(Exception):
            d.draft_id = "new_id"  # type: ignore[misc]

    def test_cannot_mutate_enabled(self) -> None:
        d = _draft()
        with pytest.raises(Exception):
            d.enabled = False  # type: ignore[misc]

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StrategyDraft(
                draft_id="x",
                display_name="X",
                toolset=_toolset(_sma("a", 10)),
                created_at=_NOW,
                updated_at=_LATER,
                unexpected_field="surprise",
            )


# ---------------------------------------------------------------------------
# TestStrategyDraftValidation
# ---------------------------------------------------------------------------

class TestStrategyDraftValidation:
    def test_valid_toolset_returns_valid_true(self) -> None:
        registry = create_default_registry()
        d = _draft(toolset=_toolset(_sma("a", 20)))
        result = d.validate_against_registry(registry)
        assert result.valid is True
        assert result.errors == ()

    def test_invalid_toolset_returns_valid_false(self) -> None:
        registry = create_default_registry()
        ts = _toolset(
            ToolConfiguration(instance_id="bad", tool_id="sma", parameters={})
        )
        d = _draft(toolset=ts)
        result = d.validate_against_registry(registry)
        assert result.valid is False

    def test_unknown_tool_id_surfaces_in_result(self) -> None:
        registry = create_default_registry()
        ts = _toolset(
            ToolConfiguration(instance_id="ghost", tool_id="does_not_exist", parameters={})
        )
        d = _draft(toolset=ts)
        result = d.validate_against_registry(registry)
        assert result.valid is False
        assert any("does_not_exist" in e for e in result.errors)

    def test_validate_against_registry_never_raises(self) -> None:
        registry = ToolRegistry()  # empty — all tools unknown
        ts = _toolset(
            ToolConfiguration(instance_id="a", tool_id="ghost", parameters={}),
            ToolConfiguration(instance_id="b", tool_id="also_ghost", parameters={}),
        )
        d = _draft(toolset=ts)
        result = d.validate_against_registry(registry)
        assert isinstance(result, ToolSetValidationResult)

    def test_validate_returns_toolset_validation_result(self) -> None:
        registry = create_default_registry()
        d = _draft()
        result = d.validate_against_registry(registry)
        assert isinstance(result, ToolSetValidationResult)

    def test_empty_toolset_is_valid(self) -> None:
        registry = create_default_registry()
        d = _draft(toolset=_toolset())
        result = d.validate_against_registry(registry)
        assert result.valid is True

    def test_multiple_errors_all_collected(self) -> None:
        registry = create_default_registry()
        ts = _toolset(
            ToolConfiguration(instance_id="bad_a", tool_id="sma", parameters={}),
            ToolConfiguration(instance_id="bad_b", tool_id="sma", parameters={}),
        )
        d = _draft(toolset=ts)
        result = d.validate_against_registry(registry)
        assert result.valid is False
        assert any("bad_a" in e for e in result.errors)
        assert any("bad_b" in e for e in result.errors)

    def test_registry_not_mutated_by_validation(self) -> None:
        registry = create_default_registry()
        before = registry.list_tools()
        d = _draft()
        d.validate_against_registry(registry)
        assert registry.list_tools() == before


# ---------------------------------------------------------------------------
# TestStrategyDraftSerialization
# ---------------------------------------------------------------------------

class TestStrategyDraftSerialization:
    def test_model_dump_returns_dict(self) -> None:
        d = _draft()
        result = d.model_dump()
        assert isinstance(result, dict)

    def test_model_dump_contains_expected_keys(self) -> None:
        d = _draft()
        result = d.model_dump()
        assert "draft_id" in result
        assert "display_name" in result
        assert "toolset" in result
        assert "created_at" in result
        assert "updated_at" in result
        assert "enabled" in result
        assert "tags" in result
        assert "notes" in result

    def test_model_dump_json_is_valid_json(self) -> None:
        d = _draft()
        raw = d.model_dump_json()
        parsed = json.loads(raw)
        assert parsed["draft_id"] == "draft_alpha"

    def test_identical_drafts_produce_identical_dumps(self) -> None:
        d1 = _draft()
        d2 = _draft()
        assert d1.model_dump() == d2.model_dump()

    def test_identical_drafts_produce_identical_json(self) -> None:
        d1 = _draft()
        d2 = _draft()
        assert d1.model_dump_json() == d2.model_dump_json()

    def test_tags_serialized_as_list_in_dump(self) -> None:
        d = _draft(tags=("research", "crypto"))
        result = d.model_dump()
        assert result["tags"] == ("research", "crypto")

    def test_toolset_nested_in_dump(self) -> None:
        ts = _toolset(_sma("sma_20", 20), toolset_id="inner")
        d = _draft(toolset=ts)
        result = d.model_dump()
        assert result["toolset"]["toolset_id"] == "inner"


# ---------------------------------------------------------------------------
# TestStrategyDraftLayerSeparation
# ---------------------------------------------------------------------------

class TestStrategyDraftLayerSeparation:
    def test_construction_does_not_call_compute_sma(self, monkeypatch) -> None:
        def _explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("compute_sma() must never be called by StrategyDraft")

        monkeypatch.setattr("backend.tools.compute_sma", _explode)
        monkeypatch.setattr("backend.tools.sma.compute_sma", _explode)

        d = _draft()
        assert d.draft_id == "draft_alpha"

    def test_validation_does_not_call_compute_sma(self, monkeypatch) -> None:
        def _explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("compute_sma() must never be called during validation")

        monkeypatch.setattr("backend.tools.compute_sma", _explode)
        monkeypatch.setattr("backend.tools.sma.compute_sma", _explode)

        registry = create_default_registry()
        d = _draft()
        result = d.validate_against_registry(registry)
        assert isinstance(result, ToolSetValidationResult)

    def test_draft_does_not_reference_runtime_runner(self) -> None:
        import backend.strategy_registry.drafts as drafts_module
        assert not hasattr(drafts_module, "StrategyRuntimeRunner")

    def test_multiple_drafts_are_independent(self) -> None:
        d1 = _draft(draft_id="alpha", toolset=_toolset(_sma("a", 20)))
        d2 = _draft(draft_id="beta", toolset=_toolset(_sma("b", 50)))
        assert d1.draft_id != d2.draft_id
        assert d1.toolset.instance_ids() != d2.toolset.instance_ids()
