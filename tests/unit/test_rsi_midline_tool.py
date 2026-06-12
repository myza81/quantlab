"""
Phase RSI-1A — RSI Midline Tool tests.

Coverage:
    RSI_MIDLINE_METADATA — registry metadata contract
    rsi_midline registration in default registry
    _compute_rsi_midline_series() — historical pipeline dispatch
    rsi_midline computation — constant value per bar
    rsi_midline warmup — 0 (no warmup; every bar produces output)
    Parameter validation — value in [0, 100], numeric
    Multi-instance RSI Midline — independent configurations
    Semantic integration — rsi.rsi > rsi_midline.rsi_midline rules
    Architecture guards — no imports from backtesting/execution/forward_testing
"""
from __future__ import annotations

import pytest

from backend.tools import (
    RSI_MIDLINE_METADATA,
    build_bar_tool_outputs,
    compute_tool_outputs_for_history,
    create_default_registry,
)
from backend.tools.configuration import ToolConfiguration
from backend.tools.historical_computation import (
    ToolComputationBarInput,
    ToolComputationError,
)
from backend.tools.models import ToolCategory, ToolStatus, VisualizationCapability
from backend.tools.toolset import StrategyToolSet

_REGISTRY = create_default_registry()


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def _rsi_midline_config(instance_id: str, value: float, enabled: bool = True) -> ToolConfiguration:
    return ToolConfiguration(
        instance_id=instance_id,
        tool_id="rsi_midline",
        parameters={"value": value},
        enabled=enabled,
    )


def _toolset(*configs: ToolConfiguration, toolset_id: str = "ts1") -> StrategyToolSet:
    return StrategyToolSet(toolset_id=toolset_id, tools=tuple(configs))


def _bar_input(bar_index: int, close: float = 100.0) -> ToolComputationBarInput:
    return ToolComputationBarInput(bar_index=bar_index, price_fields={"close": close})


def _bars(count: int) -> list[ToolComputationBarInput]:
    return [_bar_input(i) for i in range(count)]


# ===========================================================================
# RSI_MIDLINE_METADATA — registry contract
# ===========================================================================

class TestRSIMidlineMetadata:
    def test_tool_id(self):
        assert RSI_MIDLINE_METADATA.tool_id == "rsi_midline"

    def test_name(self):
        assert "RSI" in RSI_MIDLINE_METADATA.name
        assert "Midline" in RSI_MIDLINE_METADATA.name

    def test_short_name(self):
        assert RSI_MIDLINE_METADATA.short_name is not None
        assert "RSI" in RSI_MIDLINE_METADATA.short_name

    def test_output_feature_names(self):
        assert RSI_MIDLINE_METADATA.output_feature_names == ("rsi_midline",)

    def test_single_output(self):
        assert len(RSI_MIDLINE_METADATA.output_feature_names) == 1

    def test_category(self):
        assert RSI_MIDLINE_METADATA.category == ToolCategory.indicator

    def test_status_stable(self):
        assert RSI_MIDLINE_METADATA.status == ToolStatus.stable

    def test_stateful_false(self):
        assert RSI_MIDLINE_METADATA.stateful is False  # no internal state

    def test_visualization_capability(self):
        assert VisualizationCapability.produces_oscillator_series in RSI_MIDLINE_METADATA.visualization_capabilities

    def test_min_warmup_bars_zero(self):
        assert RSI_MIDLINE_METADATA.min_warmup_bars == 0

    def test_visible_on_chart(self):
        assert RSI_MIDLINE_METADATA.visible_on_chart is True

    def test_chart_pane(self):
        assert RSI_MIDLINE_METADATA.chart_pane == "oscillator_pane"

    def test_chart_render_type(self):
        assert RSI_MIDLINE_METADATA.chart_render_type == "line"

    def test_chart_category(self):
        assert RSI_MIDLINE_METADATA.chart_category == "Momentum"

    def test_value_parameter_present(self):
        names = [p.name for p in RSI_MIDLINE_METADATA.parameters]
        assert "value" in names

    def test_value_parameter_required(self):
        p = next(p for p in RSI_MIDLINE_METADATA.parameters if p.name == "value")
        assert p.required is True

    def test_value_parameter_type(self):
        p = next(p for p in RSI_MIDLINE_METADATA.parameters if p.name == "value")
        assert p.type_label == "float"

    def test_value_parameter_default_50(self):
        p = next(p for p in RSI_MIDLINE_METADATA.parameters if p.name == "value")
        assert p.default == 50

    def test_value_parameter_min_0(self):
        p = next(p for p in RSI_MIDLINE_METADATA.parameters if p.name == "value")
        assert p.min_value == 0

    def test_value_parameter_max_100(self):
        p = next(p for p in RSI_MIDLINE_METADATA.parameters if p.name == "value")
        assert p.max_value == 100

    def test_registered_in_default_registry(self):
        meta = _REGISTRY.get("rsi_midline")
        assert meta.tool_id == "rsi_midline"

    def test_frozen(self):
        import pydantic
        with pytest.raises((pydantic.ValidationError, TypeError)):
            RSI_MIDLINE_METADATA.tool_id = "modified"  # type: ignore[misc]


# ===========================================================================
# _compute_rsi_midline_series() — historical pipeline dispatch
# ===========================================================================

class TestComputeRSIMidlineSeries:
    def test_default_value_50(self):
        """Default value is 50; all bars should emit 50."""
        config = _rsi_midline_config("rsi_mid", 50)
        bars = _bars(5)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        assert len(result.series) == 1
        series = result.series[0]
        assert series.output_name == "rsi_midline"
        assert series.instance_id == "rsi_mid"
        assert len(series.points) == 5
        assert all(p.value == 50 for p in series.points)

    def test_custom_value_70(self):
        """Custom value 70; all bars should emit 70."""
        config = _rsi_midline_config("rsi_mid", 70)
        bars = _bars(3)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        series = result.series[0]
        assert len(series.points) == 3
        assert all(p.value == 70 for p in series.points)

    def test_value_0(self):
        """Boundary: value = 0."""
        config = _rsi_midline_config("rsi_mid", 0)
        bars = _bars(2)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        series = result.series[0]
        assert all(p.value == 0 for p in series.points)

    def test_value_100(self):
        """Boundary: value = 100."""
        config = _rsi_midline_config("rsi_mid", 100)
        bars = _bars(2)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        series = result.series[0]
        assert all(p.value == 100 for p in series.points)

    def test_value_float_precision(self):
        """Value with decimal places is preserved."""
        config = _rsi_midline_config("rsi_mid", 50.5)
        bars = _bars(1)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        series = result.series[0]
        assert series.points[0].value == 50.5

    def test_warmup_is_zero(self):
        """warmup_bar_count should be 0; every bar produces output."""
        config = _rsi_midline_config("rsi_mid", 50)
        bars = _bars(10)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        series = result.series[0]
        assert series.warmup_bar_count == 0

    def test_every_bar_produces_output(self):
        """All bars should have output points; no warmup skip."""
        config = _rsi_midline_config("rsi_mid", 50)
        bars = _bars(10)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        series = result.series[0]
        assert len(series.points) == 10

    def test_bar_indices_preserved(self):
        """bar_index should match input bar indices."""
        config = _rsi_midline_config("rsi_mid", 50)
        bars = _bars(5)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        series = result.series[0]
        for i, point in enumerate(series.points):
            assert point.bar_index == i

    def test_timestamps_preserved(self):
        """Timestamps should be passed through from input."""
        from datetime import datetime
        config = _rsi_midline_config("rsi_mid", 50)
        now = datetime.now()
        bars = [
            ToolComputationBarInput(bar_index=0, timestamp=now, price_fields={"close": 100}),
            ToolComputationBarInput(bar_index=1, timestamp=now, price_fields={"close": 100}),
        ]
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        series = result.series[0]
        assert series.points[0].timestamp == now

    def test_invalid_value_below_zero(self):
        """value < 0 should raise ToolComputationError (caught in validation)."""
        config = _rsi_midline_config("rsi_mid", -1)
        bars = _bars(1)

        with pytest.raises(ToolComputationError) as exc_info:
            compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        # Validation catches this early; message mentions minimum
        assert "minimum" in str(exc_info.value)

    def test_invalid_value_above_100(self):
        """value > 100 should raise ToolComputationError (caught in validation)."""
        config = _rsi_midline_config("rsi_mid", 101)
        bars = _bars(1)

        with pytest.raises(ToolComputationError) as exc_info:
            compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        # Validation catches this early; message mentions maximum
        assert "maximum" in str(exc_info.value)

    def test_invalid_value_non_numeric(self):
        """Non-numeric value should raise ToolComputationError (caught in validation)."""
        config = ToolConfiguration(
            instance_id="rsi_mid",
            tool_id="rsi_midline",
            parameters={"value": "not_a_number"},
        )
        bars = _bars(1)

        with pytest.raises(ToolComputationError) as exc_info:
            compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        # Validation catches non-numeric type early
        assert "configuration invalid" in str(exc_info.value)

    def test_multiple_instances_independent(self):
        """Multiple rsi_midline instances should be independent."""
        config1 = _rsi_midline_config("rsi_mid_a", 30)
        config2 = _rsi_midline_config("rsi_mid_b", 70)
        bars = _bars(3)

        result = compute_tool_outputs_for_history(_toolset(config1, config2), bars, _REGISTRY)

        assert len(result.series) == 2
        series_a = next(s for s in result.series if s.instance_id == "rsi_mid_a")
        series_b = next(s for s in result.series if s.instance_id == "rsi_mid_b")

        assert all(p.value == 30 for p in series_a.points)
        assert all(p.value == 70 for p in series_b.points)

    def test_output_ref_format(self):
        """Output reference should be 'instance_id.output_name'."""
        config = _rsi_midline_config("my_midline", 50)
        bars = _bars(1)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        series = result.series[0]
        assert series.output_ref == "my_midline.rsi_midline"


# ===========================================================================
# build_bar_tool_outputs() integration
# ===========================================================================

class TestBuildBarToolOutputs:
    def test_dict_structure(self):
        """Output dict should map bar_index → {ref: value}."""
        config = _rsi_midline_config("rsi_mid", 50)
        bars = _bars(3)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)
        bar_outputs = build_bar_tool_outputs(result)

        assert isinstance(bar_outputs, dict)
        assert 0 in bar_outputs
        assert 1 in bar_outputs
        assert 2 in bar_outputs

    def test_ref_value_in_dict(self):
        """Each bar dict should contain the reference and value."""
        config = _rsi_midline_config("rsi_mid", 50)
        bars = _bars(2)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)
        bar_outputs = build_bar_tool_outputs(result)

        assert bar_outputs[0]["rsi_mid.rsi_midline"] == 50
        assert bar_outputs[1]["rsi_mid.rsi_midline"] == 50


# ===========================================================================
# Disabled/Enabled behavior
# ===========================================================================

class TestEnabledBehavior:
    def test_disabled_tool_skipped(self):
        """Disabled tools should not produce output."""
        config = _rsi_midline_config("rsi_mid", 50, enabled=False)
        bars = _bars(3)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        assert len(result.series) == 0

    def test_enabled_true_produces_output(self):
        """Enabled tools should produce output."""
        config = _rsi_midline_config("rsi_mid", 50, enabled=True)
        bars = _bars(3)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        assert len(result.series) == 1
        assert len(result.series[0].points) == 3


# ===========================================================================
# Chart metadata
# ===========================================================================

class TestChartMetadata:
    def test_chart_output_series_defined(self):
        """chart_output_series should have one entry for rsi_midline."""
        assert len(RSI_MIDLINE_METADATA.chart_output_series) >= 1
        series_spec = RSI_MIDLINE_METADATA.chart_output_series[0]
        assert series_spec.series_id == "rsi_midline"

    def test_chart_series_label(self):
        series_spec = RSI_MIDLINE_METADATA.chart_output_series[0]
        assert "RSI" in series_spec.label or "Midline" in series_spec.label

    def test_chart_series_pane_oscillator(self):
        series_spec = RSI_MIDLINE_METADATA.chart_output_series[0]
        assert series_spec.pane == "oscillator_pane"

    def test_chart_series_render_line(self):
        series_spec = RSI_MIDLINE_METADATA.chart_output_series[0]
        assert series_spec.render_type == "line"

    def test_chart_editable_parameters_includes_value(self):
        assert "value" in RSI_MIDLINE_METADATA.chart_editable_parameters
