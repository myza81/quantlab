"""
Tests for Phase 2N.4 — Tool Configuration Contracts.

Covers:
  - ToolConfiguration model construction and validation
  - validate_tool_configuration() against ToolMetadata / ParameterSpec
  - Multiple configured instances referencing the same tool_id
  - Deterministic serialization (model_dump / model_dump_json)
"""
import json

import pytest

from backend.tools import (
    ConfigurationValidationError,
    ParameterSpec,
    SMA_METADATA,
    ToolCategory,
    ToolConfiguration,
    ToolMetadata,
    ToolStatus,
    VisualizationCapability,
    validate_tool_configuration,
)
from backend.strategy_registry.models import RuntimeMode


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_ALL_RUNTIME_MODES = frozenset(RuntimeMode)


def _minimal_metadata(**overrides: object) -> ToolMetadata:
    """Return a minimal ToolMetadata with optional field overrides."""
    defaults: dict = {
        "tool_id": "test_tool",
        "name": "Test Tool",
        "version": "1.0.0",
        "category": ToolCategory.indicator,
        "status": ToolStatus.stable,
        "description": "Test tool for unit tests.",
        "input_data_family": "ohlcv",
        "output_feature_names": ("out",),
        "parameters": (),
        "supported_runtime_modes": _ALL_RUNTIME_MODES,
        "visualization_capabilities": frozenset({VisualizationCapability.no_visualization}),
    }
    defaults.update(overrides)
    return ToolMetadata(**defaults)


def _param(name: str, type_label: str, *, required: bool = True, **kw: object) -> ParameterSpec:
    return ParameterSpec(
        name=name,
        description=f"{name} parameter",
        type_label=type_label,
        required=required,
        **kw,
    )


# ---------------------------------------------------------------------------
# TestToolConfiguration — model construction and field validation
# ---------------------------------------------------------------------------

class TestToolConfiguration:
    def test_valid_minimal_construction(self) -> None:
        cfg = ToolConfiguration(
            instance_id="my_sma",
            tool_id="sma",
            parameters={"period": 20},
        )
        assert cfg.instance_id == "my_sma"
        assert cfg.tool_id == "sma"
        assert cfg.parameters == {"period": 20}
        assert cfg.enabled is True
        assert cfg.display_name is None
        assert cfg.color is None

    def test_instance_id_normalized_to_lowercase(self) -> None:
        cfg = ToolConfiguration(instance_id="SMA_Fast", tool_id="sma", parameters={})
        assert cfg.instance_id == "sma_fast"

    def test_instance_id_stripped_of_whitespace(self) -> None:
        cfg = ToolConfiguration(instance_id="  sma_fast  ", tool_id="sma", parameters={})
        assert cfg.instance_id == "sma_fast"

    def test_tool_id_normalized_to_lowercase(self) -> None:
        cfg = ToolConfiguration(instance_id="x", tool_id="SMA", parameters={})
        assert cfg.tool_id == "sma"

    def test_tool_id_stripped_of_whitespace(self) -> None:
        cfg = ToolConfiguration(instance_id="x", tool_id="  sma  ", parameters={})
        assert cfg.tool_id == "sma"

    def test_instance_id_empty_raises(self) -> None:
        with pytest.raises(Exception):
            ToolConfiguration(instance_id="", tool_id="sma", parameters={})

    def test_instance_id_whitespace_only_raises(self) -> None:
        with pytest.raises(Exception):
            ToolConfiguration(instance_id="   ", tool_id="sma", parameters={})

    def test_tool_id_empty_raises(self) -> None:
        with pytest.raises(Exception):
            ToolConfiguration(instance_id="x", tool_id="", parameters={})

    def test_enabled_default_true(self) -> None:
        cfg = ToolConfiguration(instance_id="x", tool_id="sma", parameters={})
        assert cfg.enabled is True

    def test_enabled_false_accepted(self) -> None:
        cfg = ToolConfiguration(instance_id="x", tool_id="sma", parameters={}, enabled=False)
        assert cfg.enabled is False

    def test_display_name_accepted(self) -> None:
        cfg = ToolConfiguration(instance_id="x", tool_id="sma", parameters={}, display_name="SMA (20)")
        assert cfg.display_name == "SMA (20)"

    def test_color_accepted(self) -> None:
        cfg = ToolConfiguration(instance_id="x", tool_id="sma", parameters={}, color="#2196f3")
        assert cfg.color == "#2196f3"

    def test_frozen_prevents_mutation(self) -> None:
        cfg = ToolConfiguration(instance_id="x", tool_id="sma", parameters={})
        with pytest.raises(Exception):
            cfg.enabled = False  # type: ignore[misc]

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(Exception):
            ToolConfiguration(
                instance_id="x",
                tool_id="sma",
                parameters={},
                nonexistent_field="value",  # type: ignore[call-arg]
            )

    def test_empty_parameters_accepted(self) -> None:
        cfg = ToolConfiguration(instance_id="x", tool_id="sma", parameters={})
        assert cfg.parameters == {}

    def test_multiple_parameters_accepted(self) -> None:
        cfg = ToolConfiguration(
            instance_id="x",
            tool_id="sma",
            parameters={"period": 20, "name": "SMA20", "color": "#ff0000"},
        )
        assert cfg.parameters["period"] == 20
        assert cfg.parameters["name"] == "SMA20"


# ---------------------------------------------------------------------------
# TestValidateToolConfiguration — validation against ToolMetadata
# ---------------------------------------------------------------------------

class TestValidateToolConfiguration:
    def test_valid_sma_fast_passes(self) -> None:
        cfg = ToolConfiguration(
            instance_id="sma_fast",
            tool_id="sma",
            parameters={"period": 20},
        )
        validate_tool_configuration(cfg, SMA_METADATA)  # must not raise

    def test_valid_sma_with_all_params_passes(self) -> None:
        cfg = ToolConfiguration(
            instance_id="sma_full",
            tool_id="sma",
            parameters={"period": 50, "name": "SMA50", "color": "#ff9800"},
        )
        validate_tool_configuration(cfg, SMA_METADATA)

    def test_required_parameter_missing_raises(self) -> None:
        metadata = _minimal_metadata(
            parameters=(_param("period", "int", required=True, min_value=1),)
        )
        cfg = ToolConfiguration(instance_id="x", tool_id="test_tool", parameters={})
        with pytest.raises(ConfigurationValidationError) as exc_info:
            validate_tool_configuration(cfg, metadata)
        assert "period" in str(exc_info.value)
        assert "missing" in str(exc_info.value)

    def test_optional_parameter_may_be_omitted(self) -> None:
        metadata = _minimal_metadata(
            parameters=(_param("label", "str", required=False),)
        )
        cfg = ToolConfiguration(instance_id="x", tool_id="test_tool", parameters={})
        validate_tool_configuration(cfg, metadata)  # must not raise

    def test_unknown_parameter_raises(self) -> None:
        metadata = _minimal_metadata(parameters=())
        cfg = ToolConfiguration(
            instance_id="x", tool_id="test_tool", parameters={"ghost": 99}
        )
        with pytest.raises(ConfigurationValidationError) as exc_info:
            validate_tool_configuration(cfg, metadata)
        assert "ghost" in str(exc_info.value)
        assert "unknown" in str(exc_info.value)

    def test_tool_id_mismatch_raises(self) -> None:
        metadata = _minimal_metadata(tool_id="indicator_a")
        cfg = ToolConfiguration(instance_id="x", tool_id="indicator_b", parameters={})
        with pytest.raises(ConfigurationValidationError) as exc_info:
            validate_tool_configuration(cfg, metadata)
        assert "indicator_b" in str(exc_info.value)
        assert "indicator_a" in str(exc_info.value)

    def test_int_param_correct_type_passes(self) -> None:
        metadata = _minimal_metadata(parameters=(_param("n", "int"),))
        cfg = ToolConfiguration(instance_id="x", tool_id="test_tool", parameters={"n": 10})
        validate_tool_configuration(cfg, metadata)

    def test_int_param_bool_rejected(self) -> None:
        metadata = _minimal_metadata(parameters=(_param("n", "int"),))
        cfg = ToolConfiguration(instance_id="x", tool_id="test_tool", parameters={"n": True})
        with pytest.raises(ConfigurationValidationError) as exc_info:
            validate_tool_configuration(cfg, metadata)
        assert "n" in str(exc_info.value)

    def test_int_param_float_rejected(self) -> None:
        metadata = _minimal_metadata(parameters=(_param("n", "int"),))
        cfg = ToolConfiguration(instance_id="x", tool_id="test_tool", parameters={"n": 1.5})
        with pytest.raises(ConfigurationValidationError) as exc_info:
            validate_tool_configuration(cfg, metadata)
        assert "n" in str(exc_info.value)

    def test_float_param_int_value_accepted(self) -> None:
        metadata = _minimal_metadata(parameters=(_param("threshold", "float"),))
        cfg = ToolConfiguration(
            instance_id="x", tool_id="test_tool", parameters={"threshold": 2}
        )
        validate_tool_configuration(cfg, metadata)

    def test_float_param_float_value_accepted(self) -> None:
        metadata = _minimal_metadata(parameters=(_param("threshold", "float"),))
        cfg = ToolConfiguration(
            instance_id="x", tool_id="test_tool", parameters={"threshold": 2.5}
        )
        validate_tool_configuration(cfg, metadata)

    def test_float_param_bool_rejected(self) -> None:
        metadata = _minimal_metadata(parameters=(_param("threshold", "float"),))
        cfg = ToolConfiguration(
            instance_id="x", tool_id="test_tool", parameters={"threshold": True}
        )
        with pytest.raises(ConfigurationValidationError):
            validate_tool_configuration(cfg, metadata)

    def test_bool_param_correct_type_passes(self) -> None:
        metadata = _minimal_metadata(parameters=(_param("smooth", "bool"),))
        cfg = ToolConfiguration(
            instance_id="x", tool_id="test_tool", parameters={"smooth": True}
        )
        validate_tool_configuration(cfg, metadata)

    def test_bool_param_int_rejected(self) -> None:
        metadata = _minimal_metadata(parameters=(_param("smooth", "bool"),))
        cfg = ToolConfiguration(
            instance_id="x", tool_id="test_tool", parameters={"smooth": 1}
        )
        with pytest.raises(ConfigurationValidationError) as exc_info:
            validate_tool_configuration(cfg, metadata)
        assert "smooth" in str(exc_info.value)

    def test_str_param_correct_type_passes(self) -> None:
        metadata = _minimal_metadata(parameters=(_param("label", "str"),))
        cfg = ToolConfiguration(
            instance_id="x", tool_id="test_tool", parameters={"label": "Fast"}
        )
        validate_tool_configuration(cfg, metadata)

    def test_str_param_int_rejected(self) -> None:
        metadata = _minimal_metadata(parameters=(_param("label", "str"),))
        cfg = ToolConfiguration(
            instance_id="x", tool_id="test_tool", parameters={"label": 42}
        )
        with pytest.raises(ConfigurationValidationError) as exc_info:
            validate_tool_configuration(cfg, metadata)
        assert "label" in str(exc_info.value)

    def test_below_min_value_raises(self) -> None:
        metadata = _minimal_metadata(
            parameters=(_param("period", "int", min_value=1),)
        )
        cfg = ToolConfiguration(
            instance_id="x", tool_id="test_tool", parameters={"period": 0}
        )
        with pytest.raises(ConfigurationValidationError) as exc_info:
            validate_tool_configuration(cfg, metadata)
        assert "below minimum" in str(exc_info.value)

    def test_above_max_value_raises(self) -> None:
        metadata = _minimal_metadata(
            parameters=(_param("period", "int", max_value=200),)
        )
        cfg = ToolConfiguration(
            instance_id="x", tool_id="test_tool", parameters={"period": 201}
        )
        with pytest.raises(ConfigurationValidationError) as exc_info:
            validate_tool_configuration(cfg, metadata)
        assert "above maximum" in str(exc_info.value)

    def test_at_min_value_passes(self) -> None:
        metadata = _minimal_metadata(
            parameters=(_param("period", "int", min_value=1),)
        )
        cfg = ToolConfiguration(
            instance_id="x", tool_id="test_tool", parameters={"period": 1}
        )
        validate_tool_configuration(cfg, metadata)

    def test_at_max_value_passes(self) -> None:
        metadata = _minimal_metadata(
            parameters=(_param("period", "int", max_value=200),)
        )
        cfg = ToolConfiguration(
            instance_id="x", tool_id="test_tool", parameters={"period": 200}
        )
        validate_tool_configuration(cfg, metadata)

    def test_multiple_errors_all_reported(self) -> None:
        metadata = _minimal_metadata(
            parameters=(
                _param("period", "int", required=True, min_value=1),
                _param("label", "str", required=True),
            )
        )
        cfg = ToolConfiguration(instance_id="x", tool_id="test_tool", parameters={})
        with pytest.raises(ConfigurationValidationError) as exc_info:
            validate_tool_configuration(cfg, metadata)
        assert len(exc_info.value.errors) == 2

    def test_errors_attribute_contains_list(self) -> None:
        metadata = _minimal_metadata(
            parameters=(_param("period", "int", required=True),)
        )
        cfg = ToolConfiguration(instance_id="x", tool_id="test_tool", parameters={})
        with pytest.raises(ConfigurationValidationError) as exc_info:
            validate_tool_configuration(cfg, metadata)
        assert isinstance(exc_info.value.errors, list)
        assert len(exc_info.value.errors) >= 1

    def test_sma_period_one_valid(self) -> None:
        cfg = ToolConfiguration(
            instance_id="sma_1", tool_id="sma", parameters={"period": 1}
        )
        validate_tool_configuration(cfg, SMA_METADATA)

    def test_sma_period_zero_raises(self) -> None:
        cfg = ToolConfiguration(
            instance_id="sma_bad", tool_id="sma", parameters={"period": 0}
        )
        with pytest.raises(ConfigurationValidationError):
            validate_tool_configuration(cfg, SMA_METADATA)


# ---------------------------------------------------------------------------
# TestMultipleInstancesSameToolId — multiple configs from same definition
# ---------------------------------------------------------------------------

class TestMultipleInstancesSameToolId:
    def test_sma_fast_and_slow_independent(self) -> None:
        fast = ToolConfiguration(
            instance_id="sma_fast", tool_id="sma", parameters={"period": 20}
        )
        slow = ToolConfiguration(
            instance_id="sma_slow", tool_id="sma", parameters={"period": 50}
        )
        assert fast.instance_id != slow.instance_id
        assert fast.parameters["period"] == 20
        assert slow.parameters["period"] == 50
        assert fast.tool_id == slow.tool_id == "sma"

    def test_both_instances_validate_against_same_metadata(self) -> None:
        instances = [
            ToolConfiguration(instance_id="sma_20", tool_id="sma", parameters={"period": 20}),
            ToolConfiguration(instance_id="sma_50", tool_id="sma", parameters={"period": 50}),
            ToolConfiguration(instance_id="sma_200", tool_id="sma", parameters={"period": 200}),
        ]
        for inst in instances:
            validate_tool_configuration(inst, SMA_METADATA)

    def test_instance_list_uniqueness_by_instance_id(self) -> None:
        instances = [
            ToolConfiguration(instance_id="a", tool_id="sma", parameters={"period": 20}),
            ToolConfiguration(instance_id="b", tool_id="sma", parameters={"period": 50}),
        ]
        ids = [i.instance_id for i in instances]
        assert len(ids) == len(set(ids))

    def test_each_instance_independent_enabled_state(self) -> None:
        active = ToolConfiguration(
            instance_id="sma_on", tool_id="sma", parameters={"period": 20}, enabled=True
        )
        inactive = ToolConfiguration(
            instance_id="sma_off", tool_id="sma", parameters={"period": 20}, enabled=False
        )
        assert active.enabled is True
        assert inactive.enabled is False


# ---------------------------------------------------------------------------
# TestConfigurationSerialization — deterministic model_dump / model_dump_json
# ---------------------------------------------------------------------------

class TestConfigurationSerialization:
    def test_model_dump_returns_dict(self) -> None:
        cfg = ToolConfiguration(
            instance_id="sma_fast",
            tool_id="sma",
            parameters={"period": 20},
        )
        d = cfg.model_dump()
        assert isinstance(d, dict)
        assert d["instance_id"] == "sma_fast"
        assert d["tool_id"] == "sma"
        assert d["parameters"] == {"period": 20}
        assert d["enabled"] is True
        assert d["display_name"] is None
        assert d["color"] is None

    def test_model_dump_json_is_valid_json(self) -> None:
        cfg = ToolConfiguration(
            instance_id="sma_slow",
            tool_id="sma",
            parameters={"period": 50, "name": "SMA50"},
        )
        raw = cfg.model_dump_json()
        parsed = json.loads(raw)
        assert parsed["instance_id"] == "sma_slow"
        assert parsed["parameters"]["period"] == 50

    def test_identical_configs_produce_identical_dump(self) -> None:
        cfg_a = ToolConfiguration(
            instance_id="sma_x", tool_id="sma", parameters={"period": 20}
        )
        cfg_b = ToolConfiguration(
            instance_id="sma_x", tool_id="sma", parameters={"period": 20}
        )
        assert cfg_a.model_dump() == cfg_b.model_dump()
        assert cfg_a.model_dump_json() == cfg_b.model_dump_json()

    def test_model_dump_json_stable_across_calls(self) -> None:
        cfg = ToolConfiguration(
            instance_id="sma_stable",
            tool_id="sma",
            parameters={"period": 100, "color": "#ffffff"},
        )
        assert cfg.model_dump_json() == cfg.model_dump_json()
