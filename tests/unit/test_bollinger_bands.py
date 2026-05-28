"""
Tests for the Bollinger Bands tool — Phase 2U.

Covers:
  - Rolling SMA correctness (middle band)
  - Rolling population standard deviation
  - Band symmetry (upper/lower equidistant from middle)
  - Std dev multiplier effect on band width
  - Warmup behavior (no output before bar `period - 1`)
  - Flat prices → zero-width bands (std dev = 0)
  - Empty input handling
  - Determinism
  - Multi-instance isolation
  - Three output series per instance
  - Price field validation in pipeline
  - Visualization metadata (pane, kind, output feature names)
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from backend.tools.bollinger_bands import (
    BOLLINGER_METADATA,
    _bollinger_values,
    compute_bollinger,
)
from backend.tools.configuration import ToolConfiguration
from backend.tools.historical_computation import (
    ToolComputationBarInput,
    ToolComputationError,
    compute_tool_outputs_for_history,
    derive_warmup_bars_required,
)
from backend.tools.models import VisualizationCapability
from backend.tools.registry import ToolRegistry
from backend.tools.toolset import StrategyToolSet

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bar(i: int, close: float) -> ToolComputationBarInput:
    return ToolComputationBarInput(
        bar_index=i,
        timestamp=_BASE + timedelta(days=i),
        price_fields={"open": close, "high": close + 1, "low": close - 1,
                      "close": close, "volume": 1000.0},
    )


def _flat_bars(n: int, price: float = 100.0) -> list[ToolComputationBarInput]:
    return [_bar(i, price) for i in range(n)]


def _ramp_bars(n: int, start: float = 100.0, step: float = 1.0) -> list[ToolComputationBarInput]:
    return [_bar(i, start + i * step) for i in range(n)]


def _bb_config(instance_id: str = "bb1", period: int = 20, std_dev: float = 2.0) -> ToolConfiguration:
    return ToolConfiguration(
        instance_id=instance_id, tool_id="bollinger_bands",
        parameters={"period": period, "std_dev": std_dev},
    )


def _run_bb(bars: list[ToolComputationBarInput], period: int = 20, std_dev: float = 2.0, instance_id: str = "bb1"):
    toolset  = StrategyToolSet(toolset_id="ts", tools=(_bb_config(instance_id, period, std_dev),))
    registry = ToolRegistry()
    registry.register(BOLLINGER_METADATA)
    return compute_tool_outputs_for_history(toolset, bars, registry)


# ---------------------------------------------------------------------------
# _bollinger_values helper
# ---------------------------------------------------------------------------

class TestBollingerValues:
    def test_mean_matches_arithmetic_mean(self) -> None:
        window = [1.0, 2.0, 3.0, 4.0, 5.0]
        middle, _, _ = _bollinger_values(window, 2.0)
        assert abs(middle - 3.0) < 1e-12

    def test_flat_window_zero_std_dev(self) -> None:
        window = [100.0] * 10
        middle, upper, lower = _bollinger_values(window, 2.0)
        assert abs(middle - 100.0) < 1e-12
        assert abs(upper - 100.0) < 1e-12
        assert abs(lower - 100.0) < 1e-12

    def test_bands_symmetric_around_middle(self) -> None:
        window = [95.0, 97.0, 99.0, 101.0, 103.0, 105.0]
        middle, upper, lower = _bollinger_values(window, 2.0)
        assert abs((upper - middle) - (middle - lower)) < 1e-12

    def test_multiplier_scales_band_width(self) -> None:
        window = [95.0, 100.0, 105.0]
        _, upper1, lower1 = _bollinger_values(window, 1.0)
        _, upper2, lower2 = _bollinger_values(window, 2.0)
        width1 = upper1 - lower1
        width2 = upper2 - lower2
        assert abs(width2 - 2 * width1) < 1e-12

    def test_population_std_dev_calculation(self) -> None:
        # For [2, 4, 4, 4, 5, 5, 7, 9], population std dev = 2.0
        window = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
        middle, upper, lower = _bollinger_values(window, 1.0)
        assert abs(middle - 5.0) < 1e-12
        assert abs(upper - 7.0) < 1e-12
        assert abs(lower - 3.0) < 1e-12

    def test_upper_always_gte_lower(self) -> None:
        window = [100.0, 101.0, 99.0, 100.5]
        middle, upper, lower = _bollinger_values(window, 2.0)
        assert upper >= lower


# ---------------------------------------------------------------------------
# Bollinger Bands metadata
# ---------------------------------------------------------------------------

class TestBollingerMetadata:
    def test_tool_id(self) -> None:
        assert BOLLINGER_METADATA.tool_id == "bollinger_bands"

    def test_output_feature_names(self) -> None:
        assert BOLLINGER_METADATA.output_feature_names == ("middle_band", "upper_band", "lower_band")

    def test_no_oscillator_capability(self) -> None:
        assert VisualizationCapability.produces_oscillator_series not in BOLLINGER_METADATA.visualization_capabilities

    def test_stateless(self) -> None:
        assert BOLLINGER_METADATA.stateful is False

    def test_period_parameter_exists(self) -> None:
        names = [p.name for p in BOLLINGER_METADATA.parameters]
        assert "period" in names

    def test_period_default_20(self) -> None:
        param = next(p for p in BOLLINGER_METADATA.parameters if p.name == "period")
        assert param.default == 20

    def test_period_min_value_2(self) -> None:
        param = next(p for p in BOLLINGER_METADATA.parameters if p.name == "period")
        assert param.min_value == 2

    def test_std_dev_parameter_exists(self) -> None:
        names = [p.name for p in BOLLINGER_METADATA.parameters]
        assert "std_dev" in names

    def test_std_dev_default_2(self) -> None:
        param = next(p for p in BOLLINGER_METADATA.parameters if p.name == "std_dev")
        assert param.default == 2.0


# ---------------------------------------------------------------------------
# compute_bollinger (visualization path)
# ---------------------------------------------------------------------------

class TestComputeBollingerVisualization:
    def _make_normalized(self, n: int, close: float = 100.0):
        from backend.data.schemas import NormalizedOHLCV
        return [
            NormalizedOHLCV(
                symbol="TEST", asset_class="equity", venue="NYSE", source="test",
                timestamp=_BASE + timedelta(days=i),
                open=close, high=close + 1, low=close - 1, close=close,
                volume=1000.0, timeframe="1d",
            )
            for i in range(n)
        ]

    def test_empty_input_returns_three_empty_series(self) -> None:
        middle, upper, lower = compute_bollinger([], period=20)
        assert middle.points == []
        assert upper.points  == []
        assert lower.points  == []

    def test_default_name_prefix(self) -> None:
        middle, upper, lower = compute_bollinger([], period=20)
        assert "BB" in middle.name
        assert "BB" in upper.name
        assert "BB" in lower.name

    def test_custom_name_prefix(self) -> None:
        middle, upper, lower = compute_bollinger([], period=20, name="MyBB")
        assert "MyBB" in middle.name

    def test_all_panes_are_price(self) -> None:
        from backend.strategy_runtime.visualization import IndicatorPane
        middle, upper, lower = compute_bollinger([], period=20)
        assert middle.pane == IndicatorPane.price
        assert upper.pane  == IndicatorPane.price
        assert lower.pane  == IndicatorPane.price

    def test_all_kinds_are_line(self) -> None:
        from backend.strategy_runtime.visualization import IndicatorSeriesKind
        middle, upper, lower = compute_bollinger([], period=20)
        assert middle.kind == IndicatorSeriesKind.line
        assert upper.kind  == IndicatorSeriesKind.line
        assert lower.kind  == IndicatorSeriesKind.line

    def test_invalid_period_raises(self) -> None:
        with pytest.raises(ValueError, match="period must be >= 2"):
            compute_bollinger([], period=1)

    def test_invalid_std_dev_raises(self) -> None:
        with pytest.raises(ValueError, match="std_dev must be > 0"):
            compute_bollinger([], period=20, std_dev=0.0)

    def test_warmup_respected(self) -> None:
        candles = self._make_normalized(30)
        middle, upper, lower = compute_bollinger(candles, period=20)
        # warmup=19, first output at bar 19, so 30-19=11 points
        assert len(middle.points) == 11
        assert len(upper.points)  == 11
        assert len(lower.points)  == 11

    def test_flat_prices_zero_width(self) -> None:
        candles = self._make_normalized(30, close=100.0)
        middle, upper, lower = compute_bollinger(candles, period=20)
        for m, u, l in zip(middle.points, upper.points, lower.points):
            assert abs(m.value - 100.0) < 1e-12
            assert abs(u.value - 100.0) < 1e-12
            assert abs(l.value - 100.0) < 1e-12

    def test_all_three_series_equal_length(self) -> None:
        candles = self._make_normalized(40)
        middle, upper, lower = compute_bollinger(candles, period=20)
        assert len(middle.points) == len(upper.points) == len(lower.points)

    def test_deterministic(self) -> None:
        candles = self._make_normalized(40)
        m1, u1, l1 = compute_bollinger(candles, period=20)
        m2, u2, l2 = compute_bollinger(candles, period=20)
        for p1, p2 in zip(m1.points, m2.points):
            assert p1.value == p2.value
        for p1, p2 in zip(u1.points, u2.points):
            assert p1.value == p2.value

    def test_upper_always_gte_lower(self) -> None:
        candles = self._make_normalized(40)
        _, upper, lower = compute_bollinger(candles, period=20)
        for u, l in zip(upper.points, lower.points):
            assert u.value >= l.value


# ---------------------------------------------------------------------------
# Historical computation pipeline — Bollinger Bands
# ---------------------------------------------------------------------------

class TestBollingerHistoricalPipeline:
    def test_produces_three_series(self) -> None:
        bars = _flat_bars(30)
        result = _run_bb(bars, period=20)
        assert len(result.series) == 3

    def test_output_refs_correct(self) -> None:
        bars = _flat_bars(30)
        result = _run_bb(bars, period=20, instance_id="bb20")
        refs = {s.output_ref for s in result.series}
        assert refs == {"bb20.middle_band", "bb20.upper_band", "bb20.lower_band"}

    def test_warmup_respected(self) -> None:
        bars = _flat_bars(30)
        result = _run_bb(bars, period=20)
        for s in result.series:
            # warmup=19, 30-19=11 points
            assert len(s.points) == 11

    def test_flat_prices_zero_width_bands(self) -> None:
        bars = _flat_bars(30, price=100.0)
        result = _run_bb(bars, period=10)
        middle = next(s for s in result.series if s.output_name == "middle_band")
        upper  = next(s for s in result.series if s.output_name == "upper_band")
        lower  = next(s for s in result.series if s.output_name == "lower_band")
        for pt in middle.points:
            assert abs(pt.value - 100.0) < 1e-9
        for u, l in zip(upper.points, lower.points):
            assert abs(u.value - l.value) < 1e-9

    def test_middle_band_equals_sma(self) -> None:
        # Verify middle band matches hand-computed SMA for a small period
        bars = [_bar(i, float(i + 1)) for i in range(10)]  # closes: 1..10
        result = _run_bb(bars, period=3)
        middle = next(s for s in result.series if s.output_name == "middle_band")
        # First output at bar index 2: SMA(1,2,3)=2, SMA(2,3,4)=3, ...
        expected_middles = [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
        for pt, exp in zip(middle.points, expected_middles):
            assert abs(pt.value - exp) < 1e-9

    def test_bands_symmetric_around_middle(self) -> None:
        bars = _ramp_bars(30)
        result = _run_bb(bars, period=10)
        middle = next(s for s in result.series if s.output_name == "middle_band")
        upper  = next(s for s in result.series if s.output_name == "upper_band")
        lower  = next(s for s in result.series if s.output_name == "lower_band")
        for m, u, l in zip(middle.points, upper.points, lower.points):
            assert abs((u.value - m.value) - (m.value - l.value)) < 1e-9

    def test_missing_close_field_raises(self) -> None:
        bars = [
            ToolComputationBarInput(
                bar_index=i,
                timestamp=_BASE + timedelta(days=i),
                price_fields={"open": 100.0, "high": 101.0, "low": 99.0},
            )
            for i in range(25)
        ]
        toolset  = StrategyToolSet(toolset_id="ts", tools=(_bb_config(),))
        registry = ToolRegistry()
        registry.register(BOLLINGER_METADATA)
        with pytest.raises(ToolComputationError, match="missing 'close'"):
            compute_tool_outputs_for_history(toolset, bars, registry)

    def test_two_instances_isolated(self) -> None:
        bars = _ramp_bars(40)
        cfg_a = ToolConfiguration(instance_id="bb_fast", tool_id="bollinger_bands",
                                  parameters={"period": 5, "std_dev": 2.0})
        cfg_b = ToolConfiguration(instance_id="bb_slow", tool_id="bollinger_bands",
                                  parameters={"period": 20, "std_dev": 2.0})
        toolset  = StrategyToolSet(toolset_id="ts", tools=(cfg_a, cfg_b))
        registry = ToolRegistry()
        registry.register(BOLLINGER_METADATA)
        result = compute_tool_outputs_for_history(toolset, bars, registry)
        assert len(result.series) == 6   # 3 per instance
        fast_series = [s for s in result.series if s.instance_id == "bb_fast"]
        slow_series = [s for s in result.series if s.instance_id == "bb_slow"]
        assert len(fast_series) == 3
        assert len(slow_series) == 3
        # fast has more output points (smaller warmup)
        assert len(fast_series[0].points) > len(slow_series[0].points)

    def test_all_three_outputs_same_warmup(self) -> None:
        bars = _flat_bars(30)
        result = _run_bb(bars, period=10)
        warmups = {s.warmup_bar_count for s in result.series}
        assert len(warmups) == 1   # all three share the same warmup
        assert warmups.pop() == 9

    def test_std_dev_multiplier_2_vs_1(self) -> None:
        bars = _ramp_bars(30)
        result1 = _run_bb(bars, period=10, std_dev=1.0)
        result2 = _run_bb(bars, period=10, std_dev=2.0)
        u1 = next(s for s in result1.series if s.output_name == "upper_band")
        m1 = next(s for s in result1.series if s.output_name == "middle_band")
        u2 = next(s for s in result2.series if s.output_name == "upper_band")
        m2 = next(s for s in result2.series if s.output_name == "middle_band")
        # Band width with multiplier=2 should be double the width with multiplier=1
        for (p_u1, p_m1, p_u2, p_m2) in zip(u1.points, m1.points, u2.points, m2.points):
            w1 = p_u1.value - p_m1.value
            w2 = p_u2.value - p_m2.value
            assert abs(w2 - 2 * w1) < 1e-9

    def test_deterministic(self) -> None:
        bars = _ramp_bars(30)
        r1 = _run_bb(bars, period=10)
        r2 = _run_bb(bars, period=10)
        for s1, s2 in zip(r1.series, r2.series):
            for p1, p2 in zip(s1.points, s2.points):
                assert p1.value == p2.value

    def test_too_few_bars_no_output(self) -> None:
        bars = _flat_bars(5)  # period=20: need at least 20 bars
        result = _run_bb(bars, period=20)
        for s in result.series:
            assert s.points == ()

    def test_exactly_period_bars_gives_one_output(self) -> None:
        bars = _flat_bars(20, price=100.0)   # period=20: warmup=19, first output at bar 19
        result = _run_bb(bars, period=20)
        for s in result.series:
            assert len(s.points) == 1


# ---------------------------------------------------------------------------
# derive_warmup_bars_required — Bollinger
# ---------------------------------------------------------------------------

class TestBollingerWarmupDerivation:
    def test_warmup_equals_period_minus_one(self) -> None:
        cfg = _bb_config(period=20)
        assert derive_warmup_bars_required(cfg, BOLLINGER_METADATA) == 19

    def test_warmup_period_2(self) -> None:
        cfg = _bb_config(period=2)
        assert derive_warmup_bars_required(cfg, BOLLINGER_METADATA) == 1

    def test_warmup_period_5(self) -> None:
        cfg = _bb_config(period=5)
        assert derive_warmup_bars_required(cfg, BOLLINGER_METADATA) == 4

    def test_warmup_uses_default_20_when_no_period(self) -> None:
        cfg = ToolConfiguration(instance_id="bb1", tool_id="bollinger_bands", parameters={})
        assert derive_warmup_bars_required(cfg, BOLLINGER_METADATA) == 19
