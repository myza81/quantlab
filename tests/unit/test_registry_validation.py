"""
Tests for Phase 2N.6 — Registry-Backed StrategyToolSet Validation.

Covers:
  - ToolSetValidationResult model invariants
  - validate_strategy_toolset_against_registry() happy path
  - Unknown tool_id detection with clear error messages
  - Parameter validation errors surfaced through registry lookup
  - Multi-tool, multi-error collection (all errors, not fail-fast)
  - Ordering: errors follow toolset insertion order
  - Empty toolset validation (no tools → valid)
  - Disabled tools are still validated (enabled ≠ skipped)
  - Registry is not mutated during validation
  - Execution independence (no compute_sma calls)
"""
import pytest

from backend.tools import (
    SMA_METADATA,
    StrategyToolSet,
    ToolConfiguration,
    ToolRegistry,
    ToolSetValidationResult,
    create_default_registry,
    validate_strategy_toolset_against_registry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sma(instance_id: str, period: int, **kw: object) -> ToolConfiguration:
    return ToolConfiguration(
        instance_id=instance_id,
        tool_id="sma",
        parameters={"period": period},
        **kw,
    )


def _unknown(instance_id: str) -> ToolConfiguration:
    return ToolConfiguration(
        instance_id=instance_id,
        tool_id="ghost_tool",
        parameters={},
    )


def _toolset(*tools: ToolConfiguration, toolset_id: str = "test_set") -> StrategyToolSet:
    return StrategyToolSet(toolset_id=toolset_id, tools=tools)


# ---------------------------------------------------------------------------
# TestToolSetValidationResult — invariants
# ---------------------------------------------------------------------------

class TestToolSetValidationResult:
    def test_valid_result_empty_errors(self) -> None:
        r = ToolSetValidationResult(valid=True, errors=())
        assert r.valid is True
        assert r.errors == ()

    def test_invalid_result_with_errors(self) -> None:
        r = ToolSetValidationResult(valid=False, errors=("error one", "error two"))
        assert r.valid is False
        assert len(r.errors) == 2

    def test_valid_true_with_non_empty_errors_raises(self) -> None:
        with pytest.raises(ValueError, match="valid=True but errors is non-empty"):
            ToolSetValidationResult(valid=True, errors=("oops",))

    def test_valid_false_with_empty_errors_raises(self) -> None:
        with pytest.raises(ValueError, match="valid=False but errors is empty"):
            ToolSetValidationResult(valid=False, errors=())

    def test_frozen(self) -> None:
        r = ToolSetValidationResult(valid=True, errors=())
        with pytest.raises(Exception):
            r.valid = False  # type: ignore[misc]

    def test_errors_is_tuple(self) -> None:
        r = ToolSetValidationResult(valid=False, errors=("e1", "e2"))
        assert isinstance(r.errors, tuple)


# ---------------------------------------------------------------------------
# TestValidateStrategyToolSetAgainstRegistry — happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_valid_single_sma_passes(self) -> None:
        registry = create_default_registry()
        ts = _toolset(_sma("sma_fast", 20))
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert result.valid is True
        assert result.errors == ()

    def test_valid_multiple_smas_pass(self) -> None:
        registry = create_default_registry()
        ts = _toolset(_sma("a", 20), _sma("b", 50), _sma("c", 200))
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert result.valid is True

    def test_empty_toolset_is_valid(self) -> None:
        registry = create_default_registry()
        ts = _toolset()
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert result.valid is True
        assert result.errors == ()

    def test_sma_with_optional_params_passes(self) -> None:
        registry = create_default_registry()
        ts = _toolset(
            ToolConfiguration(
                instance_id="sma_styled",
                tool_id="sma",
                parameters={"period": 20, "name": "MA20", "color": "#2196f3"},
            )
        )
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert result.valid is True

    def test_disabled_tool_still_validated_and_passes(self) -> None:
        registry = create_default_registry()
        ts = _toolset(_sma("sma_off", 20, enabled=False))
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert result.valid is True


# ---------------------------------------------------------------------------
# TestUnknownToolId — missing registry entry
# ---------------------------------------------------------------------------

class TestUnknownToolId:
    def test_unknown_tool_id_fails(self) -> None:
        registry = create_default_registry()
        ts = _toolset(_unknown("ghost_inst"))
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert result.valid is False
        assert len(result.errors) == 1

    def test_error_names_instance_id(self) -> None:
        registry = create_default_registry()
        ts = _toolset(_unknown("my_ghost"))
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert "my_ghost" in result.errors[0]

    def test_error_names_tool_id(self) -> None:
        registry = create_default_registry()
        ts = _toolset(_unknown("x"))
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert "ghost_tool" in result.errors[0]

    def test_error_indicates_not_found(self) -> None:
        registry = create_default_registry()
        ts = _toolset(_unknown("x"))
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert "not found" in result.errors[0]

    def test_empty_registry_flags_all_tools(self) -> None:
        registry = ToolRegistry()
        ts = _toolset(_sma("a", 20), _sma("b", 50))
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert result.valid is False
        assert len(result.errors) == 2


# ---------------------------------------------------------------------------
# TestParameterErrors — metadata-aware param validation via registry
# ---------------------------------------------------------------------------

class TestParameterErrors:
    def test_missing_required_param_fails(self) -> None:
        registry = create_default_registry()
        ts = _toolset(
            ToolConfiguration(instance_id="sma_bad", tool_id="sma", parameters={})
        )
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert result.valid is False
        assert any("period" in e and "missing" in e for e in result.errors)

    def test_error_prefixed_with_instance_id(self) -> None:
        registry = create_default_registry()
        ts = _toolset(
            ToolConfiguration(instance_id="sma_broken", tool_id="sma", parameters={})
        )
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert all("sma_broken" in e for e in result.errors)

    def test_period_below_min_fails(self) -> None:
        registry = create_default_registry()
        ts = _toolset(
            ToolConfiguration(instance_id="sma_zero", tool_id="sma", parameters={"period": 0})
        )
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert result.valid is False
        assert any("below minimum" in e for e in result.errors)

    def test_unknown_param_fails(self) -> None:
        registry = create_default_registry()
        ts = _toolset(
            ToolConfiguration(
                instance_id="sma_ghost_param",
                tool_id="sma",
                parameters={"period": 20, "nonexistent": True},
            )
        )
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert result.valid is False
        assert any("nonexistent" in e for e in result.errors)

    def test_wrong_type_for_period_fails(self) -> None:
        registry = create_default_registry()
        ts = _toolset(
            ToolConfiguration(
                instance_id="sma_wrong_type",
                tool_id="sma",
                parameters={"period": "twenty"},
            )
        )
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert result.valid is False


# ---------------------------------------------------------------------------
# TestMultiToolErrorCollection — all errors collected, not fail-fast
# ---------------------------------------------------------------------------

class TestMultiToolErrorCollection:
    def test_two_invalid_tools_both_reported(self) -> None:
        registry = create_default_registry()
        ts = _toolset(
            ToolConfiguration(instance_id="bad_a", tool_id="sma", parameters={}),
            ToolConfiguration(instance_id="bad_b", tool_id="sma", parameters={}),
        )
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert result.valid is False
        assert any("bad_a" in e for e in result.errors)
        assert any("bad_b" in e for e in result.errors)

    def test_mix_of_valid_and_invalid_tools(self) -> None:
        registry = create_default_registry()
        ts = _toolset(
            _sma("good_a", 20),
            ToolConfiguration(instance_id="bad_b", tool_id="sma", parameters={}),
            _sma("good_c", 200),
        )
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert result.valid is False
        assert any("bad_b" in e for e in result.errors)
        assert not any("good_a" in e for e in result.errors)
        assert not any("good_c" in e for e in result.errors)

    def test_unknown_tool_and_bad_param_both_reported(self) -> None:
        registry = create_default_registry()
        ts = _toolset(
            _unknown("ghost_inst"),
            ToolConfiguration(instance_id="sma_bad", tool_id="sma", parameters={}),
        )
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert result.valid is False
        assert any("ghost_inst" in e for e in result.errors)
        assert any("sma_bad" in e for e in result.errors)

    def test_error_count_matches_violation_count(self) -> None:
        registry = create_default_registry()
        ts = _toolset(
            _unknown("x"),
            _unknown("y"),
            _unknown("z"),
        )
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert len(result.errors) == 3


# ---------------------------------------------------------------------------
# TestErrorOrdering — deterministic ordering by toolset insertion order
# ---------------------------------------------------------------------------

class TestErrorOrdering:
    def test_errors_follow_tool_insertion_order(self) -> None:
        registry = ToolRegistry()
        ts = _toolset(
            ToolConfiguration(instance_id="first", tool_id="sma", parameters={}),
            ToolConfiguration(instance_id="second", tool_id="sma", parameters={}),
            ToolConfiguration(instance_id="third", tool_id="sma", parameters={}),
        )
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert result.valid is False
        error_str = " ".join(result.errors)
        assert error_str.index("first") < error_str.index("second") < error_str.index("third")

    def test_identical_inputs_produce_identical_results(self) -> None:
        registry = create_default_registry()
        ts = _toolset(
            ToolConfiguration(instance_id="sma_bad", tool_id="sma", parameters={}),
        )
        r1 = validate_strategy_toolset_against_registry(ts, registry)
        r2 = validate_strategy_toolset_against_registry(ts, registry)
        assert r1.valid == r2.valid
        assert r1.errors == r2.errors


# ---------------------------------------------------------------------------
# TestRegistryIntegrity — registry is not mutated during validation
# ---------------------------------------------------------------------------

class TestRegistryIntegrity:
    def test_registry_unchanged_after_valid_toolset(self) -> None:
        registry = create_default_registry()
        before = registry.list_tools()
        ts = _toolset(_sma("a", 20))
        validate_strategy_toolset_against_registry(ts, registry)
        assert registry.list_tools() == before

    def test_registry_unchanged_after_invalid_toolset(self) -> None:
        registry = create_default_registry()
        before = registry.list_tools()
        ts = _toolset(_unknown("ghost"))
        validate_strategy_toolset_against_registry(ts, registry)
        assert registry.list_tools() == before

    def test_function_never_raises(self) -> None:
        registry = ToolRegistry()
        ts = _toolset(_sma("a", 20), _unknown("b"), _sma("c", -999))
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert isinstance(result, ToolSetValidationResult)

    def test_disabled_tool_still_validated(self) -> None:
        registry = create_default_registry()
        ts = _toolset(
            ToolConfiguration(
                instance_id="sma_disabled_bad",
                tool_id="sma",
                parameters={},
                enabled=False,
            )
        )
        result = validate_strategy_toolset_against_registry(ts, registry)
        assert result.valid is False
        assert any("sma_disabled_bad" in e for e in result.errors)
