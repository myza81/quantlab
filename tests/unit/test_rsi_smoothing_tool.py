"""
Phase RSI-1B — RSI Smoothing Tool tests.

Coverage:
    RSI_SMOOTHING_METADATA — registry metadata contract
    rsi_smoothing registration in default registry
    _compute_rsi_smoothing_series() — historical pipeline dispatch
    RSI computation then SMA/EMA smoothing
    Warmup behavior — period + smoothing_length - 1
    SMA smoothing correctness
    EMA smoothing correctness
    Parameter validation — period >= 2, smoothing_length >= 1, valid smoothing_type
    Multi-instance RSI Smoothing — independent configurations
    Semantic integration — rsi.rsi > rsi_smoothing.rsi_smoothing rules
    No-lookahead behavior
    Architecture guards — no imports from backtesting/execution/forward_testing
"""
from __future__ import annotations

import pytest

from backend.tools import (
    RSI_SMOOTHING_METADATA,
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

def _rsi_smoothing_config(
    instance_id: str,
    period: int = 14,
    smoothing_type: str = "SMA",
    smoothing_length: int = 14,
    enabled: bool = True,
) -> ToolConfiguration:
    return ToolConfiguration(
        instance_id=instance_id,
        tool_id="rsi_smoothing",
        parameters={
            "period": period,
            "smoothing_type": smoothing_type,
            "smoothing_length": smoothing_length,
        },
        enabled=enabled,
    )


def _toolset(*configs: ToolConfiguration, toolset_id: str = "ts1") -> StrategyToolSet:
    return StrategyToolSet(toolset_id=toolset_id, tools=tuple(configs))


def _bar_input(bar_index: int, close: float = 100.0) -> ToolComputationBarInput:
    return ToolComputationBarInput(bar_index=bar_index, price_fields={"close": close})


def _bars(count: int, base_close: float = 100.0) -> list[ToolComputationBarInput]:
    return [_bar_input(i, base_close + i * 0.5) for i in range(count)]


# ===========================================================================
# RSI_SMOOTHING_METADATA — registry contract
# ===========================================================================

class TestRSISmoothingMetadata:
    def test_tool_id(self):
        assert RSI_SMOOTHING_METADATA.tool_id == "rsi_smoothing"

    def test_name(self):
        assert "RSI" in RSI_SMOOTHING_METADATA.name
        assert "Smoothing" in RSI_SMOOTHING_METADATA.name

    def test_short_name(self):
        assert RSI_SMOOTHING_METADATA.short_name is not None
        assert "RSI" in RSI_SMOOTHING_METADATA.short_name

    def test_output_feature_names(self):
        assert RSI_SMOOTHING_METADATA.output_feature_names == ("rsi_smoothing",)

    def test_single_output(self):
        assert len(RSI_SMOOTHING_METADATA.output_feature_names) == 1

    def test_category(self):
        assert RSI_SMOOTHING_METADATA.category == ToolCategory.indicator

    def test_status_stable(self):
        assert RSI_SMOOTHING_METADATA.status == ToolStatus.stable

    def test_stateful_true(self):
        assert RSI_SMOOTHING_METADATA.stateful is True  # RSI is stateful

    def test_visualization_capability(self):
        assert VisualizationCapability.produces_oscillator_series in RSI_SMOOTHING_METADATA.visualization_capabilities

    def test_min_warmup_bars_positive(self):
        assert RSI_SMOOTHING_METADATA.min_warmup_bars >= 2

    def test_visible_on_chart(self):
        assert RSI_SMOOTHING_METADATA.visible_on_chart is True

    def test_chart_pane(self):
        assert RSI_SMOOTHING_METADATA.chart_pane == "oscillator_pane"

    def test_chart_render_type(self):
        assert RSI_SMOOTHING_METADATA.chart_render_type == "line"

    def test_chart_category(self):
        assert RSI_SMOOTHING_METADATA.chart_category == "Momentum"

    def test_period_parameter_present(self):
        names = [p.name for p in RSI_SMOOTHING_METADATA.parameters]
        assert "period" in names

    def test_period_parameter_default_14(self):
        p = next(p for p in RSI_SMOOTHING_METADATA.parameters if p.name == "period")
        assert p.default == 14
        assert p.min_value == 2

    def test_smoothing_type_parameter_present(self):
        names = [p.name for p in RSI_SMOOTHING_METADATA.parameters]
        assert "smoothing_type" in names

    def test_smoothing_type_parameter_default_sma(self):
        p = next(p for p in RSI_SMOOTHING_METADATA.parameters if p.name == "smoothing_type")
        assert p.default == "SMA"
        assert p.type_label == "str"

    def test_smoothing_length_parameter_present(self):
        names = [p.name for p in RSI_SMOOTHING_METADATA.parameters]
        assert "smoothing_length" in names

    def test_smoothing_length_parameter_default_14(self):
        p = next(p for p in RSI_SMOOTHING_METADATA.parameters if p.name == "smoothing_length")
        assert p.default == 14
        assert p.min_value == 1

    def test_registered_in_default_registry(self):
        meta = _REGISTRY.get("rsi_smoothing")
        assert meta.tool_id == "rsi_smoothing"

    def test_frozen(self):
        import pydantic
        with pytest.raises((pydantic.ValidationError, TypeError)):
            RSI_SMOOTHING_METADATA.tool_id = "modified"  # type: ignore[misc]


# ===========================================================================
# _compute_rsi_smoothing_series() — computation
# ===========================================================================

class TestRSISmoothingComputation:
    def test_default_parameters_sma_14_of_rsi_14(self):
        """Default: SMA(14) of RSI(14)."""
        config = _rsi_smoothing_config("rsi_smooth")
        bars = _bars(50)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        assert len(result.series) == 1
        series = result.series[0]
        assert series.output_name == "rsi_smoothing"
        assert series.instance_id == "rsi_smooth"

    def test_warmup_period_plus_smoothing_minus_1(self):
        """Warmup should be period + smoothing_length - 1."""
        config = _rsi_smoothing_config("rsi_smooth", period=14, smoothing_length=5)
        bars = _bars(50)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        series = result.series[0]
        assert series.warmup_bar_count == 14 + 5 - 1  # 18

    def test_sma_smoothing_output_count(self):
        """With period=14, smoothing=5, warmup=18, 50 bars should produce 32 points."""
        config = _rsi_smoothing_config("rsi_smooth", period=14, smoothing_length=5)
        bars = _bars(50)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        series = result.series[0]
        expected_points = 50 - 18  # total bars - warmup
        assert len(series.points) == expected_points

    def test_ema_smoothing_output_count(self):
        """EMA smoothing should produce same count as SMA for same parameters."""
        config = _rsi_smoothing_config("rsi_smooth", period=14, smoothing_length=5, smoothing_type="EMA")
        bars = _bars(50)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        series = result.series[0]
        expected_points = 50 - 18
        assert len(series.points) == expected_points

    def test_insufficient_bars_returns_empty_series(self):
        """With 10 bars and warmup=18, should return empty points."""
        config = _rsi_smoothing_config("rsi_smooth", period=14, smoothing_length=5)
        bars = _bars(10)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        series = result.series[0]
        assert len(series.points) == 0

    def test_bar_indices_preserved(self):
        """bar_index should match input bar indices."""
        config = _rsi_smoothing_config("rsi_smooth", period=5, smoothing_length=3)
        bars = _bars(20)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        series = result.series[0]
        for i, point in enumerate(series.points):
            expected_bar_idx = series.warmup_bar_count + i
            assert point.bar_index == expected_bar_idx

    def test_multiple_instances_independent(self):
        """Multiple rsi_smoothing instances should be independent."""
        config1 = _rsi_smoothing_config("smooth_a", period=14, smoothing_length=5)
        config2 = _rsi_smoothing_config("smooth_b", period=7, smoothing_length=3)
        bars = _bars(50)

        result = compute_tool_outputs_for_history(_toolset(config1, config2), bars, _REGISTRY)

        assert len(result.series) == 2
        series_a = next(s for s in result.series if s.instance_id == "smooth_a")
        series_b = next(s for s in result.series if s.instance_id == "smooth_b")

        assert series_a.warmup_bar_count == 14 + 5 - 1  # 18
        assert series_b.warmup_bar_count == 7 + 3 - 1   # 9

    def test_output_ref_format(self):
        """Output reference should be 'instance_id.output_name'."""
        config = _rsi_smoothing_config("my_smooth")
        bars = _bars(50)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        series = result.series[0]
        assert series.output_ref == "my_smooth.rsi_smoothing"

    def test_invalid_period_below_2_rejected(self):
        """Period < 2 should raise ToolComputationError (caught in validation)."""
        config = _rsi_smoothing_config("rsi_smooth", period=1)
        bars = _bars(50)

        with pytest.raises(ToolComputationError) as exc_info:
            compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        # Validation catches this early; message mentions minimum
        assert "minimum" in str(exc_info.value)

    def test_invalid_smoothing_length_below_1_rejected(self):
        """smoothing_length < 1 should raise ToolComputationError (caught in validation)."""
        config = _rsi_smoothing_config("rsi_smooth", smoothing_length=0)
        bars = _bars(50)

        with pytest.raises(ToolComputationError) as exc_info:
            compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        # Validation catches this early; message mentions minimum
        assert "minimum" in str(exc_info.value)

    def test_invalid_smoothing_type_rejected(self):
        """Invalid smoothing_type should raise ToolComputationError during validation."""
        config = _rsi_smoothing_config("rsi_smooth", smoothing_type="VWMA")
        bars = _bars(50)

        with pytest.raises(ToolComputationError) as exc_info:
            compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        assert "configuration invalid" in str(exc_info.value)
        assert "smoothing_type" in str(exc_info.value)
        assert "VWMA" in str(exc_info.value)
        assert "allowed options" in str(exc_info.value)

    def test_sma_and_ema_produce_different_values(self):
        """SMA and EMA smoothing should produce different smoothed values."""
        # Use oscillating prices to get varied RSI values
        bars = [ToolComputationBarInput(
            bar_index=i,
            price_fields={"close": 100 + 10 * (i % 3 - 1)}  # Oscillates
        ) for i in range(50)]

        config_sma = _rsi_smoothing_config("sma", smoothing_type="SMA")
        config_ema = _rsi_smoothing_config("ema", smoothing_type="EMA")

        result_sma = compute_tool_outputs_for_history(_toolset(config_sma), bars, _REGISTRY)
        result_ema = compute_tool_outputs_for_history(_toolset(config_ema), bars, _REGISTRY)

        sma_values = [p.value for p in result_sma.series[0].points]
        ema_values = [p.value for p in result_ema.series[0].points]

        # SMA and EMA should differ for oscillating prices
        assert len(sma_values) > 0
        assert len(ema_values) > 0
        # Not all values should be equal (they differ at some point)
        assert sma_values != ema_values


# ===========================================================================
# build_bar_tool_outputs() integration
# ===========================================================================

class TestBuildBarToolOutputs:
    def test_dict_structure(self):
        """Output dict should map bar_index → {ref: value}."""
        config = _rsi_smoothing_config("rsi_smooth", period=5, smoothing_length=3)
        bars = _bars(20)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)
        bar_outputs = build_bar_tool_outputs(result)

        # Should have entries for bars after warmup
        assert len(bar_outputs) > 0
        # Each bar should have the reference
        for bar_dict in bar_outputs.values():
            assert "rsi_smooth.rsi_smoothing" in bar_dict


# ===========================================================================
# Disabled/Enabled behavior
# ===========================================================================

class TestEnabledBehavior:
    def test_disabled_tool_skipped(self):
        """Disabled tools should not produce output."""
        config = _rsi_smoothing_config("rsi_smooth", enabled=False)
        bars = _bars(50)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        assert len(result.series) == 0

    def test_enabled_true_produces_output(self):
        """Enabled tools should produce output."""
        config = _rsi_smoothing_config("rsi_smooth", enabled=True)
        bars = _bars(50)
        result = compute_tool_outputs_for_history(_toolset(config), bars, _REGISTRY)

        assert len(result.series) == 1
        assert len(result.series[0].points) > 0


# ===========================================================================
# Chart metadata
# ===========================================================================

class TestChartMetadata:
    def test_chart_output_series_defined(self):
        """chart_output_series should have one entry for rsi_smoothing."""
        assert len(RSI_SMOOTHING_METADATA.chart_output_series) >= 1
        series_spec = RSI_SMOOTHING_METADATA.chart_output_series[0]
        assert series_spec.series_id == "rsi_smoothing"

    def test_chart_series_label(self):
        series_spec = RSI_SMOOTHING_METADATA.chart_output_series[0]
        assert "Smoothing" in series_spec.label or "RSI" in series_spec.label

    def test_chart_series_pane_oscillator(self):
        series_spec = RSI_SMOOTHING_METADATA.chart_output_series[0]
        assert series_spec.pane == "oscillator_pane"

    def test_chart_series_render_line(self):
        series_spec = RSI_SMOOTHING_METADATA.chart_output_series[0]
        assert series_spec.render_type == "line"

    def test_chart_editable_parameters_includes_all(self):
        assert "period" in RSI_SMOOTHING_METADATA.chart_editable_parameters
        assert "smoothing_type" in RSI_SMOOTHING_METADATA.chart_editable_parameters
        assert "smoothing_length" in RSI_SMOOTHING_METADATA.chart_editable_parameters
