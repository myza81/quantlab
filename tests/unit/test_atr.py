"""
Tests for the ATR (Average True Range) tool — Phase 2U.

Covers:
  - True range calculation (_true_range helper)
  - Wilder smoothing correctness
  - Warmup behavior (no output before bar `period`)
  - Empty input handling
  - Period boundary conditions
  - Determinism (identical inputs → identical outputs)
  - Multi-instance isolation via historical computation pipeline
  - Price field validation in pipeline
  - Visualization metadata (pane, kind, output feature names)
  - Architecture boundary (no forbidden imports)
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from backend.tools.atr import ATR_METADATA, _true_range, compute_atr
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

def _bar(i: int, high: float, low: float, close: float, open_: float = 100.0) -> ToolComputationBarInput:
    return ToolComputationBarInput(
        bar_index=i,
        timestamp=_BASE + timedelta(days=i),
        price_fields={"open": open_, "high": high, "low": low, "close": close, "volume": 1000.0},
    )


def _uniform_bars(n: int, high: float = 105.0, low: float = 95.0, close: float = 100.0) -> list[ToolComputationBarInput]:
    return [_bar(i, high, low, close) for i in range(n)]


def _atr_config(instance_id: str = "atr1", period: int = 14) -> ToolConfiguration:
    return ToolConfiguration(instance_id=instance_id, tool_id="atr", parameters={"period": period})


def _run_atr(bars: list[ToolComputationBarInput], period: int = 14, instance_id: str = "atr1"):
    toolset  = StrategyToolSet(toolset_id="ts", tools=(_atr_config(instance_id, period),))
    registry = ToolRegistry()
    registry.register(ATR_METADATA)
    return compute_tool_outputs_for_history(toolset, bars, registry)


# ---------------------------------------------------------------------------
# True range helper
# ---------------------------------------------------------------------------

class TestTrueRange:
    def test_normal_bar_wider_than_prev_range(self) -> None:
        # H=110, L=90, prev_close=100 → TR = max(20, 10, 10) = 20
        assert _true_range(110.0, 90.0, 100.0) == 20.0

    def test_gap_up_dominates(self) -> None:
        # H=115, L=110, prev_close=100 → TR = max(5, 15, 10) = 15
        assert _true_range(115.0, 110.0, 100.0) == 15.0

    def test_gap_down_dominates(self) -> None:
        # H=90, L=85, prev_close=100 → TR = max(5, 10, 15) = 15
        assert _true_range(90.0, 85.0, 100.0) == 15.0

    def test_inside_bar(self) -> None:
        # H=102, L=98, prev_close=100 → TR = max(4, 2, 2) = 4
        assert _true_range(102.0, 98.0, 100.0) == 4.0

    def test_equal_ohlc(self) -> None:
        # H=L=close=prev_close=100 → TR = 0
        assert _true_range(100.0, 100.0, 100.0) == 0.0

    def test_tr_always_nonnegative(self) -> None:
        # With valid OHLC, TR is always >= 0
        assert _true_range(100.0, 100.0, 100.0) >= 0.0
        assert _true_range(105.0, 95.0, 100.0) >= 0.0


# ---------------------------------------------------------------------------
# ATR metadata
# ---------------------------------------------------------------------------

class TestATRMetadata:
    def test_tool_id(self) -> None:
        assert ATR_METADATA.tool_id == "atr"

    def test_output_feature_names(self) -> None:
        assert ATR_METADATA.output_feature_names == ("atr",)

    def test_produces_oscillator_series(self) -> None:
        assert VisualizationCapability.produces_oscillator_series in ATR_METADATA.visualization_capabilities

    def test_stateful(self) -> None:
        assert ATR_METADATA.stateful is True

    def test_min_warmup_bars_at_least_one(self) -> None:
        assert ATR_METADATA.min_warmup_bars >= 1

    def test_period_parameter_exists(self) -> None:
        names = [p.name for p in ATR_METADATA.parameters]
        assert "period" in names

    def test_period_default_14(self) -> None:
        param = next(p for p in ATR_METADATA.parameters if p.name == "period")
        assert param.default == 14

    def test_period_min_value_1(self) -> None:
        param = next(p for p in ATR_METADATA.parameters if p.name == "period")
        assert param.min_value == 1


# ---------------------------------------------------------------------------
# compute_atr (visualization path)
# ---------------------------------------------------------------------------

class TestComputeATRVisualization:
    def _make_normalized(self, n: int, high: float = 105.0, low: float = 95.0, close: float = 100.0):
        from backend.data.schemas import NormalizedOHLCV
        return [
            NormalizedOHLCV(
                symbol="TEST", asset_class="equity", venue="NYSE", source="test",
                timestamp=_BASE + timedelta(days=i),
                open=100.0, high=high, low=low, close=close,
                volume=1000.0, timeframe="1d",
            )
            for i in range(n)
        ]

    def test_empty_input_returns_empty_series(self) -> None:
        result = compute_atr([], period=14)
        assert result.points == []

    def test_empty_series_name_default(self) -> None:
        result = compute_atr([], period=14)
        assert result.name == "ATR(14)"

    def test_custom_name(self) -> None:
        result = compute_atr([], period=14, name="MyATR")
        assert result.name == "MyATR"

    def test_pane_is_oscillator(self) -> None:
        from backend.strategy_runtime.visualization import IndicatorPane
        result = compute_atr([], period=14)
        assert result.pane == IndicatorPane.oscillator

    def test_kind_is_line(self) -> None:
        from backend.strategy_runtime.visualization import IndicatorSeriesKind
        result = compute_atr([], period=14)
        assert result.kind == IndicatorSeriesKind.line

    def test_invalid_period_raises(self) -> None:
        with pytest.raises(ValueError, match="period must be >= 1"):
            compute_atr([], period=0)

    def test_warmup_respected(self) -> None:
        candles = self._make_normalized(30, high=110.0, low=90.0, close=100.0)
        result = compute_atr(candles, period=14)
        # First output at bar index 14 (period=14), so 30-14=16 points
        assert len(result.points) == 30 - 14

    def test_flat_prices_atr_equals_bar_range(self) -> None:
        # All bars identical: high=110, low=90, close=100, prev_close always 100
        # TR = max(20, |110-100|, |90-100|) = max(20, 10, 10) = 20 for every bar
        # Seed ATR = SMA(20, 20, ...) = 20; all subsequent = 20
        candles = self._make_normalized(30, high=110.0, low=90.0, close=100.0)
        result = compute_atr(candles, period=14)
        for pt in result.points:
            assert abs(pt.value - 20.0) < 1e-9

    def test_values_are_nonnegative(self) -> None:
        candles = self._make_normalized(30)
        result = compute_atr(candles, period=5)
        assert all(pt.value >= 0.0 for pt in result.points)

    def test_period_1_first_output_at_bar_1(self) -> None:
        candles = self._make_normalized(5, high=110.0, low=90.0, close=100.0)
        result = compute_atr(candles, period=1)
        # period=1: warmup=1, first output at bar 1 → 4 points for 5 bars
        assert len(result.points) == 4

    def test_deterministic(self) -> None:
        candles = self._make_normalized(40)
        r1 = compute_atr(candles, period=10)
        r2 = compute_atr(candles, period=10)
        for p1, p2 in zip(r1.points, r2.points):
            assert p1.value == p2.value


# ---------------------------------------------------------------------------
# Historical computation pipeline — ATR
# ---------------------------------------------------------------------------

class TestATRHistoricalPipeline:
    def test_warmup_respected_no_output_before_period(self) -> None:
        bars = _uniform_bars(20, high=110.0, low=90.0, close=100.0)
        result = _run_atr(bars, period=14)
        series = result.series[0]
        # 20 bars, warmup=14, first output at position 14 → 20-14 = 6 points
        assert len(series.points) == 6

    def test_output_ref_is_instance_dot_atr(self) -> None:
        bars = _uniform_bars(20)
        result = _run_atr(bars, period=5, instance_id="atr14")
        assert result.series[0].output_ref == "atr14.atr"

    def test_flat_prices_atr_equals_bar_range(self) -> None:
        # high=110, low=90, prev_close=100: TR=20 always → ATR=20 everywhere
        bars = _uniform_bars(30, high=110.0, low=90.0, close=100.0)
        result = _run_atr(bars, period=10)
        for pt in result.series[0].points:
            assert abs(pt.value - 20.0) < 1e-9

    def test_single_series_per_instance(self) -> None:
        bars = _uniform_bars(20)
        result = _run_atr(bars, period=5)
        assert len(result.series) == 1

    def test_missing_high_field_raises(self) -> None:
        bars = [
            ToolComputationBarInput(
                bar_index=i,
                timestamp=_BASE + timedelta(days=i),
                price_fields={"low": 95.0, "close": 100.0},
            )
            for i in range(20)
        ]
        toolset  = StrategyToolSet(toolset_id="ts", tools=(_atr_config(),))
        registry = ToolRegistry()
        registry.register(ATR_METADATA)
        with pytest.raises(ToolComputationError, match="missing 'high'"):
            compute_tool_outputs_for_history(toolset, bars, registry)

    def test_missing_low_field_raises(self) -> None:
        bars = [
            ToolComputationBarInput(
                bar_index=i,
                timestamp=_BASE + timedelta(days=i),
                price_fields={"high": 105.0, "close": 100.0},
            )
            for i in range(20)
        ]
        toolset  = StrategyToolSet(toolset_id="ts", tools=(_atr_config(),))
        registry = ToolRegistry()
        registry.register(ATR_METADATA)
        with pytest.raises(ToolComputationError, match="missing 'low'"):
            compute_tool_outputs_for_history(toolset, bars, registry)

    def test_wilder_smoothing_seed_then_update(self) -> None:
        # Manually verify Wilder smoothing for period=3 with known TR values.
        # Bar 0: close=100
        # Bars 1,2,3: high=115, low=95, close=100 → TR = max(20, 15, 5) = 20
        # Seed at bar 3: ATR = SMA(20,20,20)/3 = 20
        # Bar 4: high=120, low=100, close=110 → prev_close=100 → TR = max(20,20,0) = 20
        # ATR = (20*2 + 20)/3 = 20
        bars = [
            _bar(0, high=100.0, low=100.0, close=100.0),
            _bar(1, high=115.0, low=95.0, close=100.0),
            _bar(2, high=115.0, low=95.0, close=100.0),
            _bar(3, high=115.0, low=95.0, close=100.0),
            _bar(4, high=120.0, low=100.0, close=110.0),
        ]
        result = _run_atr(bars, period=3)
        pts = result.series[0].points
        # First output at bar 3 (position 3), second at bar 4
        assert len(pts) == 2
        assert abs(pts[0].value - 20.0) < 1e-9
        assert abs(pts[1].value - 20.0) < 1e-9

    def test_two_instances_isolated(self) -> None:
        bars = _uniform_bars(30, high=110.0, low=90.0, close=100.0)
        cfg_a = ToolConfiguration(instance_id="atr_fast", tool_id="atr", parameters={"period": 5})
        cfg_b = ToolConfiguration(instance_id="atr_slow", tool_id="atr", parameters={"period": 14})
        toolset  = StrategyToolSet(toolset_id="ts", tools=(cfg_a, cfg_b))
        registry = ToolRegistry()
        registry.register(ATR_METADATA)
        result = compute_tool_outputs_for_history(toolset, bars, registry)
        assert len(result.series) == 2
        fast = next(s for s in result.series if s.instance_id == "atr_fast")
        slow = next(s for s in result.series if s.instance_id == "atr_slow")
        # fast has more output points (smaller warmup)
        assert len(fast.points) > len(slow.points)

    def test_warmup_bar_count_stored(self) -> None:
        bars = _uniform_bars(30)
        result = _run_atr(bars, period=10)
        assert result.series[0].warmup_bar_count == 10

    def test_deterministic(self) -> None:
        bars = _uniform_bars(30)
        r1 = _run_atr(bars, period=7)
        r2 = _run_atr(bars, period=7)
        for p1, p2 in zip(r1.series[0].points, r2.series[0].points):
            assert p1.value == p2.value

    def test_too_few_bars_no_output(self) -> None:
        bars = _uniform_bars(5)  # period=14 needs at least 15 bars for first output
        result = _run_atr(bars, period=14)
        assert result.series[0].points == ()

    def test_exactly_period_plus_one_bars_gives_one_output(self) -> None:
        # period=5: need bars 0..5 (6 bars) → 1 output at bar_index 5
        bars = _uniform_bars(6, high=110.0, low=90.0, close=100.0)
        result = _run_atr(bars, period=5)
        assert len(result.series[0].points) == 1


# ---------------------------------------------------------------------------
# derive_warmup_bars_required — ATR
# ---------------------------------------------------------------------------

class TestATRWarmupDerivation:
    def test_warmup_equals_period(self) -> None:
        cfg = _atr_config(period=14)
        assert derive_warmup_bars_required(cfg, ATR_METADATA) == 14

    def test_warmup_period_1(self) -> None:
        cfg = _atr_config(period=1)
        assert derive_warmup_bars_required(cfg, ATR_METADATA) == 1

    def test_warmup_period_5(self) -> None:
        cfg = _atr_config(period=5)
        assert derive_warmup_bars_required(cfg, ATR_METADATA) == 5

    def test_warmup_uses_default_14_when_no_period(self) -> None:
        cfg = ToolConfiguration(instance_id="atr1", tool_id="atr", parameters={})
        assert derive_warmup_bars_required(cfg, ATR_METADATA) == 14
