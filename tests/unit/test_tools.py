"""
Tests for backend/tools/ — Tool metadata model, ToolRegistry, and SMA tool.
"""
from datetime import datetime, timezone

import pytest

from backend.data.schemas import NormalizedOHLCV
from backend.strategy_registry.models import RuntimeMode
from backend.strategy_runtime.visualization import (
    IndicatorPane,
    IndicatorSeriesKind,
)
from backend.tools import (
    DuplicateToolError,
    ParameterSpec,
    SMA_METADATA,
    ToolCategory,
    ToolMetadata,
    ToolNotFoundError,
    ToolRegistry,
    ToolStatus,
    VisualizationCapability,
    compute_sma,
    create_default_registry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_TS = datetime(2024, 1, 1, tzinfo=timezone.utc)
_ALL_RUNTIME_MODES = frozenset(RuntimeMode)


def _utc(day: int) -> datetime:
    return datetime(2024, 1, day, tzinfo=timezone.utc)


def _make_candles(closes: list[float]) -> list[NormalizedOHLCV]:
    return [
        NormalizedOHLCV(
            symbol="TEST",
            asset_class="equity",
            venue="TEST",
            timeframe="1d",
            source="test",
            timestamp=_utc(i + 1),
            open=c,
            high=c,
            low=c,
            close=c,
            volume=1000.0,
        )
        for i, c in enumerate(closes)
    ]


def _minimal_metadata(**overrides: object) -> ToolMetadata:
    base: dict[str, object] = {
        "tool_id": "test_tool",
        "name": "Test Tool",
        "version": "1.0.0",
        "category": ToolCategory.indicator,
        "status": ToolStatus.stable,
        "description": "A test tool.",
        "input_data_family": "ohlcv",
        "output_feature_names": ("out",),
        "parameters": (),
        "supported_runtime_modes": frozenset({RuntimeMode.RESEARCH}),
        "visualization_capabilities": frozenset({VisualizationCapability.no_visualization}),
    }
    base.update(overrides)
    return ToolMetadata(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ParameterSpec
# ---------------------------------------------------------------------------

class TestParameterSpec:
    def test_valid_construction(self) -> None:
        p = ParameterSpec(name="period", description="Window size", type_label="int")
        assert p.name == "period"
        assert p.required is True
        assert p.default is None

    def test_optional_with_default(self) -> None:
        p = ParameterSpec(
            name="color",
            description="Hex color",
            type_label="str",
            required=False,
            default="#ffffff",
        )
        assert p.required is False
        assert p.default == "#ffffff"

    def test_frozen(self) -> None:
        p = ParameterSpec(name="period", description="desc", type_label="int")
        with pytest.raises(Exception):
            p.name = "changed"  # type: ignore[misc]

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(Exception):
            ParameterSpec(  # type: ignore[call-arg]
                name="period", description="d", type_label="int", unknown_field=True
            )

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(Exception):
            ParameterSpec(name="  ", description="d", type_label="int")

    def test_empty_description_rejected(self) -> None:
        with pytest.raises(Exception):
            ParameterSpec(name="period", description="", type_label="int")

    def test_empty_type_label_rejected(self) -> None:
        with pytest.raises(Exception):
            ParameterSpec(name="period", description="d", type_label="")


# ---------------------------------------------------------------------------
# ToolMetadata
# ---------------------------------------------------------------------------

class TestToolMetadata:
    def test_valid_construction(self) -> None:
        m = _minimal_metadata()
        assert m.tool_id == "test_tool"
        assert m.status == ToolStatus.stable
        assert m.category == ToolCategory.indicator

    def test_tool_id_normalized_to_lowercase(self) -> None:
        m = _minimal_metadata(tool_id="MyTool")
        assert m.tool_id == "mytool"

    def test_tool_id_whitespace_stripped(self) -> None:
        m = _minimal_metadata(tool_id="  sma  ")
        assert m.tool_id == "sma"

    def test_empty_tool_id_rejected(self) -> None:
        with pytest.raises(Exception):
            _minimal_metadata(tool_id="")

    def test_whitespace_tool_id_rejected(self) -> None:
        with pytest.raises(Exception):
            _minimal_metadata(tool_id="   ")

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(Exception):
            _minimal_metadata(name="")

    def test_empty_description_rejected(self) -> None:
        with pytest.raises(Exception):
            _minimal_metadata(description="")

    def test_empty_input_data_family_rejected(self) -> None:
        with pytest.raises(Exception):
            _minimal_metadata(input_data_family="")

    def test_empty_version_rejected(self) -> None:
        with pytest.raises(Exception):
            _minimal_metadata(version="")

    def test_negative_warmup_rejected(self) -> None:
        with pytest.raises(Exception):
            _minimal_metadata(min_warmup_bars=-1)

    def test_zero_warmup_accepted(self) -> None:
        m = _minimal_metadata(min_warmup_bars=0)
        assert m.min_warmup_bars == 0

    def test_frozen(self) -> None:
        m = _minimal_metadata()
        with pytest.raises(Exception):
            m.name = "changed"  # type: ignore[misc]

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(Exception):
            ToolMetadata(  # type: ignore[call-arg]
                tool_id="t",
                name="T",
                version="1.0.0",
                category=ToolCategory.indicator,
                status=ToolStatus.stable,
                description="d",
                input_data_family="ohlcv",
                output_feature_names=("out",),
                parameters=(),
                supported_runtime_modes=frozenset({RuntimeMode.RESEARCH}),
                visualization_capabilities=frozenset({VisualizationCapability.no_visualization}),
                unknown_field="bad",
            )

    def test_stateful_default_false(self) -> None:
        m = _minimal_metadata()
        assert m.stateful is False

    def test_min_warmup_default_zero(self) -> None:
        m = _minimal_metadata()
        assert m.min_warmup_bars == 0


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------

class TestToolRegistry:
    def test_register_and_get(self) -> None:
        reg = ToolRegistry()
        m = _minimal_metadata()
        reg.register(m)
        assert reg.get("test_tool") is m

    def test_get_case_insensitive(self) -> None:
        reg = ToolRegistry()
        reg.register(_minimal_metadata(tool_id="sma"))
        assert reg.get("SMA").tool_id == "sma"
        assert reg.get("Sma").tool_id == "sma"
        assert reg.get("  sma  ").tool_id == "sma"

    def test_duplicate_raises(self) -> None:
        reg = ToolRegistry()
        reg.register(_minimal_metadata())
        with pytest.raises(DuplicateToolError):
            reg.register(_minimal_metadata())

    def test_not_found_raises(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(ToolNotFoundError):
            reg.get("nonexistent")

    def test_not_found_message_lists_available(self) -> None:
        reg = ToolRegistry()
        reg.register(_minimal_metadata(tool_id="sma"))
        with pytest.raises(ToolNotFoundError, match="sma"):
            reg.get("ema")

    def test_deregister(self) -> None:
        reg = ToolRegistry()
        reg.register(_minimal_metadata())
        reg.deregister("test_tool")
        assert "test_tool" not in reg

    def test_deregister_not_found_raises(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(ToolNotFoundError):
            reg.deregister("nonexistent")

    def test_list_tools_sorted(self) -> None:
        reg = ToolRegistry()
        reg.register(_minimal_metadata(tool_id="sma"))
        reg.register(_minimal_metadata(tool_id="ema"))
        reg.register(_minimal_metadata(tool_id="rsi"))
        assert reg.list_tools() == ["ema", "rsi", "sma"]

    def test_list_tools_empty(self) -> None:
        reg = ToolRegistry()
        assert reg.list_tools() == []

    def test_contains_true(self) -> None:
        reg = ToolRegistry()
        reg.register(_minimal_metadata(tool_id="sma"))
        assert "sma" in reg
        assert "SMA" in reg

    def test_contains_false(self) -> None:
        reg = ToolRegistry()
        assert "sma" not in reg

    def test_contains_non_string_returns_false(self) -> None:
        reg = ToolRegistry()
        assert 42 not in reg  # type: ignore[operator]

    def test_len(self) -> None:
        reg = ToolRegistry()
        assert len(reg) == 0
        reg.register(_minimal_metadata(tool_id="sma"))
        assert len(reg) == 1
        reg.register(_minimal_metadata(tool_id="ema"))
        assert len(reg) == 2

    def test_register_after_deregister_succeeds(self) -> None:
        reg = ToolRegistry()
        m = _minimal_metadata()
        reg.register(m)
        reg.deregister("test_tool")
        reg.register(m)  # should not raise
        assert "test_tool" in reg


# ---------------------------------------------------------------------------
# SMA Metadata
# ---------------------------------------------------------------------------

class TestSmaMetadata:
    def test_tool_id(self) -> None:
        assert SMA_METADATA.tool_id == "sma"

    def test_status_stable(self) -> None:
        assert SMA_METADATA.status == ToolStatus.stable

    def test_category_indicator(self) -> None:
        assert SMA_METADATA.category == ToolCategory.indicator

    def test_stateless(self) -> None:
        assert SMA_METADATA.stateful is False

    def test_visualization_capability_line_overlay(self) -> None:
        assert VisualizationCapability.produces_line_overlay in SMA_METADATA.visualization_capabilities

    def test_all_runtime_modes_supported(self) -> None:
        for mode in RuntimeMode:
            assert mode in SMA_METADATA.supported_runtime_modes

    def test_has_period_parameter(self) -> None:
        names = [p.name for p in SMA_METADATA.parameters]
        assert "period" in names

    def test_period_parameter_required(self) -> None:
        param = next(p for p in SMA_METADATA.parameters if p.name == "period")
        assert param.required is True

    def test_output_feature_name(self) -> None:
        assert "sma" in SMA_METADATA.output_feature_names

    def test_input_data_family_ohlcv(self) -> None:
        assert SMA_METADATA.input_data_family == "ohlcv"


# ---------------------------------------------------------------------------
# compute_sma
# ---------------------------------------------------------------------------

class TestComputeSma:
    def test_basic_sma_period_3(self) -> None:
        candles = _make_candles([1.0, 2.0, 3.0, 4.0, 5.0])
        result = compute_sma(candles, period=3)
        values = [p.value for p in result.points]
        assert values == pytest.approx([2.0, 3.0, 4.0])

    def test_period_1_returns_every_bar(self) -> None:
        closes = [10.0, 20.0, 30.0]
        candles = _make_candles(closes)
        result = compute_sma(candles, period=1)
        assert len(result.points) == 3
        assert [p.value for p in result.points] == pytest.approx(closes)

    def test_warmup_bars_excluded(self) -> None:
        candles = _make_candles([1.0, 2.0])
        result = compute_sma(candles, period=5)
        assert result.points == []

    def test_exactly_period_bars_returns_one_point(self) -> None:
        candles = _make_candles([1.0, 2.0, 3.0])
        result = compute_sma(candles, period=3)
        assert len(result.points) == 1
        assert result.points[0].value == pytest.approx(2.0)

    def test_empty_candles_returns_empty_series(self) -> None:
        result = compute_sma([], period=5)
        assert result.points == []

    def test_deterministic_output(self) -> None:
        candles = _make_candles([1.0, 2.0, 3.0, 4.0, 5.0])
        r1 = compute_sma(candles, period=3)
        r2 = compute_sma(candles, period=3)
        assert [p.value for p in r1.points] == [p.value for p in r2.points]
        assert [p.timestamp for p in r1.points] == [p.timestamp for p in r2.points]

    def test_output_timestamps_match_candle_timestamps(self) -> None:
        candles = _make_candles([10.0, 20.0, 30.0])
        result = compute_sma(candles, period=2)
        # period=2: first valid point at index 1
        assert result.points[0].timestamp == _utc(2)
        assert result.points[1].timestamp == _utc(3)

    def test_output_timestamps_are_utc_aware(self) -> None:
        candles = _make_candles([1.0, 2.0, 3.0])
        result = compute_sma(candles, period=1)
        for point in result.points:
            assert point.timestamp.tzinfo is not None

    def test_unsorted_input_produces_correct_output(self) -> None:
        # Provide candles out of order — compute_sma sorts internally
        candles = _make_candles([1.0, 2.0, 3.0])
        candles_reversed = list(reversed(candles))
        result_sorted = compute_sma(candles, period=3)
        result_unsorted = compute_sma(candles_reversed, period=3)
        assert len(result_sorted.points) == len(result_unsorted.points)
        assert result_sorted.points[0].value == pytest.approx(result_unsorted.points[0].value)

    def test_default_name_includes_period(self) -> None:
        result = compute_sma(_make_candles([1.0, 2.0]), period=14)
        assert "14" in result.name

    def test_custom_name_used(self) -> None:
        result = compute_sma(_make_candles([1.0, 2.0]), period=5, name="MA5")
        assert result.name == "MA5"

    def test_custom_color_passed_through(self) -> None:
        result = compute_sma(_make_candles([1.0, 2.0]), period=1, color="#ff0000")
        assert result.color == "#ff0000"

    def test_no_color_is_none(self) -> None:
        result = compute_sma(_make_candles([1.0, 2.0]), period=1)
        assert result.color is None

    def test_period_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="period must be >= 1"):
            compute_sma(_make_candles([1.0, 2.0, 3.0]), period=0)

    def test_period_negative_raises(self) -> None:
        with pytest.raises(ValueError):
            compute_sma(_make_candles([1.0, 2.0, 3.0]), period=-5)

    def test_output_is_indicator_series(self) -> None:
        from backend.strategy_runtime.visualization import IndicatorSeries
        result = compute_sma(_make_candles([1.0, 2.0, 3.0]), period=2)
        assert isinstance(result, IndicatorSeries)

    def test_output_kind_is_line(self) -> None:
        result = compute_sma(_make_candles([1.0, 2.0, 3.0]), period=2)
        assert result.kind == IndicatorSeriesKind.line

    def test_output_pane_is_price(self) -> None:
        result = compute_sma(_make_candles([1.0, 2.0, 3.0]), period=2)
        assert result.pane == IndicatorPane.price

    def test_numerical_precision(self) -> None:
        # 10+20+30 = 60 / 3 = 20.0 exactly
        candles = _make_candles([10.0, 20.0, 30.0])
        result = compute_sma(candles, period=3)
        assert result.points[0].value == pytest.approx(20.0)

    def test_large_period_sma(self) -> None:
        closes = list(range(1, 21))  # 1..20
        candles = _make_candles([float(c) for c in closes])
        result = compute_sma(candles, period=20)
        assert len(result.points) == 1
        assert result.points[0].value == pytest.approx(10.5)  # mean of 1..20


# ---------------------------------------------------------------------------
# create_default_registry
# ---------------------------------------------------------------------------

class TestCreateDefaultRegistry:
    def test_sma_registered(self) -> None:
        reg = create_default_registry()
        assert "sma" in reg

    def test_sma_metadata_correct(self) -> None:
        reg = create_default_registry()
        m = reg.get("sma")
        assert m.tool_id == "sma"
        assert m.status == ToolStatus.stable

    def test_registry_is_independent(self) -> None:
        # Each call returns a separate registry instance
        r1 = create_default_registry()
        r2 = create_default_registry()
        r1.deregister("sma")
        assert "sma" in r2  # r2 unaffected
