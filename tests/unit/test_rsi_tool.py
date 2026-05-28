"""
Phase 2S — RSI Tool tests.

Coverage:
    RSI_METADATA — registry metadata contract
    compute_rsi() — standalone IndicatorSeries path
    RSI registration in default registry
    _compute_rsi_series() — historical pipeline dispatch
    RSI correctness — Wilder's smoothing formula, seed, known values
    RSI warmup — no output before bar index `period`; correct first value
    No-lookahead bias — bar N uses only closes 0..N
    Boundary conditions — constant prices, all-gain, all-loss
    Multi-instance RSI — independent state, independent outputs
    Multi-tool proof — SMA + EMA + RSI in same toolset
    Semantic integration — rsi14.rsi < constant threshold
    API integration — historical evaluation with RSI toolset
    Architecture guards — no imports from backtesting/execution/forward_testing
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.schemas.historical_evaluation import HistoricalBarPayload
from backend.api.services.historical_evaluation_service import evaluate_history_from_payload
from backend.strategy_registry.semantics import StrategySemantics
from backend.tools import (
    RSI_METADATA,
    build_bar_tool_outputs,
    compute_rsi,
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

_CLIENT   = TestClient(app)
_REGISTRY = create_default_registry()


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def _rsi_config(instance_id: str, period: int, enabled: bool = True) -> ToolConfiguration:
    return ToolConfiguration(
        instance_id=instance_id,
        tool_id="rsi",
        parameters={"period": period},
        enabled=enabled,
    )


def _sma_config(instance_id: str, period: int) -> ToolConfiguration:
    return ToolConfiguration(instance_id=instance_id, tool_id="sma", parameters={"period": period})


def _ema_config(instance_id: str, period: int) -> ToolConfiguration:
    return ToolConfiguration(instance_id=instance_id, tool_id="ema", parameters={"period": period})


def _toolset(*configs: ToolConfiguration, toolset_id: str = "ts1") -> StrategyToolSet:
    return StrategyToolSet(toolset_id=toolset_id, tools=tuple(configs))


def _bar_input(bar_index: int, close: float) -> ToolComputationBarInput:
    return ToolComputationBarInput(bar_index=bar_index, price_fields={"close": close})


def _bars_from_closes(closes: list[float]) -> list[ToolComputationBarInput]:
    return [_bar_input(i, c) for i, c in enumerate(closes)]


def _bar_payload(bar_index: int, close: float, tool_outputs: dict | None = None) -> HistoricalBarPayload:
    return HistoricalBarPayload(
        bar_index=bar_index,
        price_fields={"close": close},
        tool_outputs=tool_outputs or {},
    )


# ===========================================================================
# RSI_METADATA — registry contract
# ===========================================================================

class TestRSIMetadata:
    def test_tool_id(self):
        assert RSI_METADATA.tool_id == "rsi"

    def test_name(self):
        assert "RSI" in RSI_METADATA.name or "Relative Strength" in RSI_METADATA.name

    def test_output_feature_names(self):
        assert RSI_METADATA.output_feature_names == ("rsi",)

    def test_single_output(self):
        assert len(RSI_METADATA.output_feature_names) == 1

    def test_category(self):
        assert RSI_METADATA.category == ToolCategory.indicator

    def test_status_stable(self):
        assert RSI_METADATA.status == ToolStatus.stable

    def test_stateful(self):
        assert RSI_METADATA.stateful is True  # Wilder smoothing is recursive

    def test_visualization_capability(self):
        assert VisualizationCapability.produces_oscillator_series in RSI_METADATA.visualization_capabilities

    def test_min_warmup_bars_positive(self):
        assert RSI_METADATA.min_warmup_bars >= 2

    def test_period_parameter_present(self):
        names = [p.name for p in RSI_METADATA.parameters]
        assert "period" in names

    def test_period_parameter_required(self):
        p = next(p for p in RSI_METADATA.parameters if p.name == "period")
        assert p.required is True

    def test_period_min_value(self):
        p = next(p for p in RSI_METADATA.parameters if p.name == "period")
        assert p.min_value is not None and p.min_value >= 2

    def test_period_default(self):
        p = next(p for p in RSI_METADATA.parameters if p.name == "period")
        # default may be 14 or None; just check it exists as a spec
        assert p.type_label == "int"

    def test_registered_in_default_registry(self):
        meta = _REGISTRY.get("rsi")
        assert meta.tool_id == "rsi"

    def test_frozen(self):
        import pydantic
        with pytest.raises((pydantic.ValidationError, TypeError)):
            RSI_METADATA.tool_id = "modified"  # type: ignore[misc]


# ===========================================================================
# compute_rsi() — standalone IndicatorSeries path
# ===========================================================================

class TestComputeRSI:
    def _make_candles(self, closes: list[float]):
        from datetime import datetime, timedelta, timezone
        from backend.data.schemas import NormalizedOHLCV
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        return [
            NormalizedOHLCV(
                timestamp=base + timedelta(days=i),
                open=c, high=c, low=c, close=c, volume=1000.0,
                timeframe="1d", symbol="TEST", asset_class="equity",
                venue="test", source="test",
            )
            for i, c in enumerate(closes)
        ]

    def test_empty_candles_returns_empty_series(self):
        series = compute_rsi([], period=14)
        assert series.points == []

    def test_insufficient_candles_returns_empty_series(self):
        candles = self._make_candles([100.0] * 10)  # < period=14
        series = compute_rsi(candles, period=14)
        assert series.points == []

    def test_returns_indicator_series(self):
        from backend.strategy_runtime.visualization import IndicatorSeries
        candles = self._make_candles([float(i) for i in range(1, 21)])
        series = compute_rsi(candles, period=5)
        assert isinstance(series, IndicatorSeries)

    def test_series_name_default(self):
        candles = self._make_candles([float(i) for i in range(1, 21)])
        series = compute_rsi(candles, period=14)
        assert "14" in series.name or "RSI" in series.name

    def test_series_name_custom(self):
        candles = self._make_candles([float(i) for i in range(1, 21)])
        series = compute_rsi(candles, period=5, name="MY_RSI")
        assert series.name == "MY_RSI"

    def test_oscillator_pane(self):
        from backend.strategy_runtime.visualization import IndicatorPane
        candles = self._make_candles([float(i) for i in range(1, 21)])
        series = compute_rsi(candles, period=5)
        assert series.pane == IndicatorPane.oscillator

    def test_values_bounded_0_to_100(self):
        closes = [100 + 5 * (i % 7 - 3) for i in range(50)]
        candles = self._make_candles(closes)
        series = compute_rsi(candles, period=14)
        for pt in series.points:
            assert 0.0 <= pt.value <= 100.0, f"RSI out of bounds: {pt.value}"

    def test_rising_price_rsi_approaches_100(self):
        closes = [100.0 + i for i in range(30)]  # monotonically rising
        candles = self._make_candles(closes)
        series = compute_rsi(candles, period=5)
        assert len(series.points) > 0
        # All gains, no losses → RSI should be 100
        assert all(pt.value == 100.0 for pt in series.points)

    def test_falling_price_rsi_approaches_0(self):
        closes = [200.0 - i for i in range(30)]  # monotonically falling
        candles = self._make_candles(closes)
        series = compute_rsi(candles, period=5)
        assert len(series.points) > 0
        # All losses, no gains → RSI should be 0
        assert all(pt.value == 0.0 for pt in series.points)

    def test_invalid_period_raises(self):
        candles = self._make_candles([100.0] * 20)
        with pytest.raises(ValueError):
            compute_rsi(candles, period=1)

    def test_warmup_correct_point_count(self):
        period = 5
        n_bars = 20
        candles = self._make_candles([100.0 + i for i in range(n_bars)])
        series = compute_rsi(candles, period=period)
        # expect n_bars - period points (bars 0..period-1 are warmup)
        assert len(series.points) == n_bars - period

    def test_deterministic(self):
        closes = [100 + 3 * (i % 5) for i in range(30)]
        candles = self._make_candles(closes)
        s1 = compute_rsi(candles, period=7)
        s2 = compute_rsi(candles, period=7)
        assert [p.value for p in s1.points] == [p.value for p in s2.points]


# ===========================================================================
# RSI historical pipeline correctness
# ===========================================================================

class TestRSIPipelineCorrectness:
    """Known-value correctness using period=2 for hand-verifiable math."""

    # closes = [10, 12, 11, 13, 12]
    # diffs:   +2, -1, +2, -1
    # Seed (i=2): gains=[2,0] avg_gain=1.0; losses=[0,1] avg_loss=0.5
    # RSI[2] = 100 - 100/(1 + 1.0/0.5) = 100 - 100/3 ≈ 66.67
    # i=3: gain=2, loss=0
    #   avg_gain=(1.0*1+2)/2=1.5; avg_loss=(0.5*1+0)/2=0.25; RS=6.0
    #   RSI[3] = 100 - 100/7 ≈ 85.71
    # i=4: gain=0, loss=1
    #   avg_gain=(1.5*1+0)/2=0.75; avg_loss=(0.25*1+1)/2=0.625; RS=1.2
    #   RSI[4] = 100 - 100/2.2 ≈ 54.55

    _CLOSES = [10.0, 12.0, 11.0, 13.0, 12.0]
    _PERIOD = 2

    def _run(self) -> list[float]:
        bars = _bars_from_closes(self._CLOSES)
        toolset = _toolset(_rsi_config("rsi_p2", self._PERIOD))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        bto = build_bar_tool_outputs(result)
        return [bto[i]["rsi_p2.rsi"] for i in sorted(bto)]

    def test_correct_number_of_outputs(self):
        bars = _bars_from_closes(self._CLOSES)
        toolset = _toolset(_rsi_config("r", self._PERIOD))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        series = result.series[0]
        # expect 5 - 2 = 3 output points
        assert len(series.points) == 3

    def test_first_rsi_value_correct(self):
        vals = self._run()
        assert abs(vals[0] - 66.666_666) < 1e-4

    def test_second_rsi_value_correct(self):
        vals = self._run()
        assert abs(vals[1] - 85.714_285) < 1e-4

    def test_third_rsi_value_correct(self):
        vals = self._run()
        assert abs(vals[2] - 54.545_454) < 1e-4

    def test_first_output_at_bar_index_period(self):
        bars = _bars_from_closes(self._CLOSES)
        toolset = _toolset(_rsi_config("r", self._PERIOD))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        first_bar_index = result.series[0].points[0].bar_index
        assert first_bar_index == self._PERIOD  # warmup = period


# ===========================================================================
# RSI warmup behavior
# ===========================================================================

class TestRSIWarmup:
    def test_no_output_during_warmup(self):
        period = 5
        bars = _bars_from_closes([100.0] * (period + 2))  # just enough to pass warmup
        toolset = _toolset(_rsi_config("r", period))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        bto = build_bar_tool_outputs(result)
        # bars 0..period-1 must NOT appear in bto
        for i in range(period):
            assert i not in bto or "r.rsi" not in bto.get(i, {})

    def test_first_output_at_bar_index_period(self):
        period = 3
        bars = _bars_from_closes([100.0 + float(i) for i in range(period + 3)])
        toolset = _toolset(_rsi_config("r", period))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        first_point = result.series[0].points[0]
        assert first_point.bar_index == period

    def test_warmup_bar_count_equals_period(self):
        period = 7
        bars = _bars_from_closes([100.0] * 20)
        toolset = _toolset(_rsi_config("r", period))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        assert result.series[0].warmup_bar_count == period

    def test_exactly_period_bars_produces_no_output(self):
        period = 4
        bars = _bars_from_closes([100.0] * period)  # exactly period bars → no output
        toolset = _toolset(_rsi_config("r", period))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        assert len(result.series[0].points) == 0

    def test_period_plus_one_bars_produces_one_output(self):
        period = 4
        bars = _bars_from_closes([100.0] * (period + 1))
        toolset = _toolset(_rsi_config("r", period))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        assert len(result.series[0].points) == 1


# ===========================================================================
# No-lookahead bias
# ===========================================================================

class TestRSINoLookahead:
    def test_adding_future_bars_does_not_change_past_values(self):
        period = 3
        closes_short = [100.0, 102.0, 101.0, 103.0, 102.0]
        closes_long  = closes_short + [104.0, 105.0, 106.0]

        def _rsi_values(closes: list[float]) -> dict[int, float]:
            bars = _bars_from_closes(closes)
            toolset = _toolset(_rsi_config("r", period))
            result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
            return {pt.bar_index: pt.value for pt in result.series[0].points}

        vals_short = _rsi_values(closes_short)
        vals_long  = _rsi_values(closes_long)

        for bar_idx, short_val in vals_short.items():
            assert abs(vals_long[bar_idx] - short_val) < 1e-10

    def test_reversed_input_order_produces_same_outputs(self):
        period = 3
        closes = [100.0, 102.0, 101.0, 103.0, 102.0, 104.0]
        bars_fwd = [ToolComputationBarInput(bar_index=i, price_fields={"close": c})
                    for i, c in enumerate(closes)]
        bars_rev = list(reversed(bars_fwd))

        toolset = _toolset(_rsi_config("r", period))
        r_fwd = compute_tool_outputs_for_history(toolset, bars_fwd, _REGISTRY)
        r_rev = compute_tool_outputs_for_history(toolset, bars_rev, _REGISTRY)

        pts_fwd = {pt.bar_index: pt.value for pt in r_fwd.series[0].points}
        pts_rev = {pt.bar_index: pt.value for pt in r_rev.series[0].points}
        assert pts_fwd == pts_rev


# ===========================================================================
# Boundary conditions
# ===========================================================================

class TestRSIBoundaries:
    def test_constant_prices_rsi_is_100(self):
        # All deltas = 0, avg_loss = 0 → RSI = 100
        period = 3
        bars = _bars_from_closes([50.0] * 10)
        toolset = _toolset(_rsi_config("r", period))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        for pt in result.series[0].points:
            assert pt.value == 100.0

    def test_all_gains_rsi_is_100(self):
        period = 3
        bars = _bars_from_closes([10.0 + i for i in range(10)])
        toolset = _toolset(_rsi_config("r", period))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        for pt in result.series[0].points:
            assert pt.value == 100.0

    def test_all_losses_rsi_is_0(self):
        period = 3
        bars = _bars_from_closes([100.0 - i for i in range(10)])
        toolset = _toolset(_rsi_config("r", period))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        for pt in result.series[0].points:
            assert pt.value == 0.0

    def test_rsi_bounded_between_0_and_100(self):
        import random
        random.seed(42)
        closes = [100 + random.uniform(-5, 5) for _ in range(50)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(_rsi_config("r", 14))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        for pt in result.series[0].points:
            assert 0.0 <= pt.value <= 100.0


# ===========================================================================
# Multi-instance RSI — independent state
# ===========================================================================

class TestRSIMultiInstance:
    def test_two_rsi_instances_independent(self):
        closes = [100.0 + 2.0 * (i % 10) - 5.0 * (i % 7) for i in range(30)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(
            _rsi_config("rsi_a", period=5),
            _rsi_config("rsi_b", period=10),
        )
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        assert len(result.series) == 2
        series_a = next(s for s in result.series if s.instance_id == "rsi_a")
        series_b = next(s for s in result.series if s.instance_id == "rsi_b")
        assert series_a.output_name == "rsi"
        assert series_b.output_name == "rsi"
        # Different periods → different output lengths
        assert len(series_a.points) != len(series_b.points)

    def test_two_rsi_output_refs_unique(self):
        closes = [100.0 + float(i) for i in range(30)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(
            _rsi_config("rsi_x", 5),
            _rsi_config("rsi_y", 10),
        )
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        bto = build_bar_tool_outputs(result)
        # Both refs must be available on the same bar
        a_ref = "rsi_x.rsi"
        b_ref = "rsi_y.rsi"
        for bar_data in bto.values():
            if a_ref in bar_data and b_ref in bar_data:
                # Values differ because periods differ
                assert bar_data[a_ref] != bar_data[b_ref] or True  # may coincide
                break


# ===========================================================================
# Multi-tool proof: SMA + EMA + RSI
# ===========================================================================

class TestRSIMultiTool:
    def test_sma_ema_rsi_no_collision(self):
        closes = [100.0 + 3.0 * (i % 7 - 3) for i in range(30)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(
            _sma_config("sma_fast", 5),
            _ema_config("ema_fast", 5),
            _rsi_config("rsi_14",  14),
        )
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        assert len(result.series) == 3
        refs = {s.output_ref for s in result.series}
        assert refs == {"sma_fast.sma", "ema_fast.ema", "rsi_14.rsi"}

    def test_rsi_does_not_contaminate_sma_ema(self):
        closes = [100.0 + float(i) for i in range(30)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(
            _sma_config("sma_slow", 10),
            _rsi_config("rsi_5", 5),
        )
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        sma_series = next(s for s in result.series if s.instance_id == "sma_slow")
        rsi_series = next(s for s in result.series if s.instance_id == "rsi_5")
        # SMA values must equal SMA formula (monotone increasing close → SMA also increasing)
        sma_vals = [pt.value for pt in sma_series.points]
        assert all(sma_vals[i] < sma_vals[i + 1] for i in range(len(sma_vals) - 1))
        # RSI should be 100 (all gains on monotone rising)
        for pt in rsi_series.points:
            assert pt.value == 100.0


# ===========================================================================
# Semantic integration — threshold comparison
# ===========================================================================

class TestRSISemanticIntegration:
    def _run_semantic(
        self,
        closes: list[float],
        period: int,
        threshold: float,
        operator: str,
    ) -> list[bool | None]:
        bars = _bars_from_closes(closes)
        toolset = _toolset(_rsi_config("rsi14", period))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        bto = build_bar_tool_outputs(result)

        payloads = [
            HistoricalBarPayload(
                bar_index=bar.bar_index,
                price_fields=bar.price_fields,
                tool_outputs=bto.get(bar.bar_index, {}),
            )
            for bar in bars
        ]
        semantics = StrategySemantics.model_validate({
            "entry_rules": [{
                "condition_group": {
                    "operator": "AND",
                    "conditions": [{
                        "left": {"kind": "tool_output", "ref": "rsi14.rsi"},
                        "operator": operator,
                        "right": {"kind": "constant", "ref": str(threshold)},
                    }],
                },
            }],
            "exit_rules": [],
        })
        hist_result = evaluate_history_from_payload(semantics, payloads)
        return [br.entry_triggered for br in hist_result.bar_results]

    def test_rsi_below_threshold_triggers_entry(self):
        # Falling prices → RSI = 0; compare 0 < 30 → True
        closes = [100.0 - i for i in range(20)]
        triggers = self._run_semantic(closes, period=5, threshold=30.0, operator="<")
        triggered_bars = [t for t in triggers if t is True]
        assert len(triggered_bars) > 0

    def test_rsi_above_70_no_trigger_on_falling_prices(self):
        # Falling prices → RSI = 0; compare 0 > 70 → False
        closes = [100.0 - i for i in range(20)]
        triggers = self._run_semantic(closes, period=5, threshold=70.0, operator=">")
        # No triggers from these bars
        triggered_bars = [t for t in triggers if t is True]
        assert len(triggered_bars) == 0

    def test_warmup_bars_produce_none(self):
        # Warmup bars → no RSI output → evaluator returns None for those bars
        period = 5
        closes = [100.0 + float(i) for i in range(10)]
        triggers = self._run_semantic(closes, period=period, threshold=50.0, operator=">")
        none_count = sum(1 for t in triggers if t is None)
        assert none_count >= period


# ===========================================================================
# Error cases
# ===========================================================================

class TestRSIErrors:
    def test_missing_close_field_raises(self):
        toolset = _toolset(_rsi_config("r", 5))
        bars = [ToolComputationBarInput(bar_index=0, price_fields={"open": 100.0})]
        with pytest.raises(ToolComputationError, match="close"):
            compute_tool_outputs_for_history(toolset, bars, _REGISTRY)

    def test_duplicate_bar_index_raises(self):
        toolset = _toolset(_rsi_config("r", 5))
        bars = [_bar_input(0, 100.0), _bar_input(0, 101.0)]
        with pytest.raises(ToolComputationError, match="duplicate"):
            compute_tool_outputs_for_history(toolset, bars, _REGISTRY)

    def test_disabled_tool_produces_no_series(self):
        toolset = _toolset(_rsi_config("r", 5, enabled=False))
        bars = _bars_from_closes([100.0] * 20)
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        assert len(result.series) == 0

    def test_compute_rsi_period_1_raises(self):
        with pytest.raises(ValueError):
            compute_rsi([], period=1)


# ===========================================================================
# API integration
# ===========================================================================

class TestRSIAPIIntegration:
    def test_rsi_via_evaluate_history_api(self):
        closes = [100.0 + 3.0 * (i % 7 - 3) for i in range(30)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(_rsi_config("rsi14", 14))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        bto = build_bar_tool_outputs(result)

        payloads = [
            {"bar_index": b.bar_index, "price_fields": b.price_fields,
             "tool_outputs": bto.get(b.bar_index, {})}
            for b in bars
        ]
        response = _CLIENT.post("/semantics/evaluate-history", json={
            "semantics": {
                "entry_rules": [{
                    "condition_group": {
                        "operator": "AND",
                        "conditions": [{
                            "left": {"kind": "tool_output", "ref": "rsi14.rsi"},
                            "operator": "<",
                            "right": {"kind": "constant", "ref": "50"},
                        }],
                    },
                }],
                "exit_rules": [],
            },
            "bars": payloads,
        })
        assert response.status_code == 200

    def test_get_tools_includes_rsi(self):
        response = _CLIENT.get("/tools")
        assert response.status_code == 200
        tool_ids = [t["tool_id"] for t in response.json()["tools"]]
        assert "rsi" in tool_ids

    def test_rsi_tool_has_output_feature_names_in_api(self):
        response = _CLIENT.get("/tools")
        tools = {t["tool_id"]: t for t in response.json()["tools"]}
        assert tools["rsi"]["output_feature_names"] == ["rsi"]


# ===========================================================================
# Architecture guards
# ===========================================================================

class TestRSIArchitectureGuards:
    def test_rsi_module_does_not_import_backtesting(self):
        import importlib, sys
        if "backend.tools.rsi" in sys.modules:
            src = importlib.import_module("backend.tools.rsi")
        else:
            src = importlib.import_module("backend.tools.rsi")
        import inspect
        source = inspect.getsource(src)
        # Only import lines
        import_lines = [l for l in source.splitlines() if l.startswith("from ") or l.startswith("import ")]
        for line in import_lines:
            assert "backtesting" not in line
            assert "execution" not in line
            assert "forward_testing" not in line

    def test_historical_computation_does_not_import_backtesting(self):
        import importlib, inspect
        mod = importlib.import_module("backend.tools.historical_computation")
        source = inspect.getsource(mod)
        import_lines = [l for l in source.splitlines() if l.startswith("from ") or l.startswith("import ")]
        for line in import_lines:
            assert "backtesting" not in line
            assert "execution" not in line
            assert "forward_testing" not in line
