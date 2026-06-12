"""
Phase 2R.1 — EMA Tool + Multi-Tool Computation Proof tests.

Coverage:
    EMA_METADATA — registry metadata contract
    compute_ema() — standalone IndicatorSeries path
    EMA registration in default registry
    _compute_ema_series() — historical pipeline dispatch
    EMA correctness — formula, seed, alpha, recursive progression
    EMA warmup — unavailable before seed, correct first value
    No-lookahead bias — bar N uses only closes 0..N
    Multi-instance EMA — independent state, independent outputs
    Multi-tool proof — SMA + EMA in same toolset, no collisions
    Semantic integration — ema_fast.ema > constant, ema_fast.ema crosses_above ema_slow.ema
    Negative / error cases — invalid period, missing close, unknown source in validation
    Architecture guards — no imports from backtesting/execution/forward_testing
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.services.historical_evaluation_service import evaluate_history_from_payload
from backend.api.schemas.historical_evaluation import HistoricalBarPayload
from backend.strategy_registry.semantics import StrategySemantics
from backend.tools import (
    EMA_METADATA,
    build_bar_tool_outputs,
    compute_ema,
    compute_tool_outputs_for_history,
    create_default_registry,
)
from backend.tools.configuration import ToolConfiguration
from backend.tools.historical_computation import (
    ToolComputationBarInput,
    ToolComputationError,
)
from backend.tools.models import (
    ToolCategory,
    ToolStatus,
    VisualizationCapability,
)
from backend.tools.toolset import StrategyToolSet

_CLIENT = TestClient(app)
_REGISTRY = create_default_registry()


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def _ema_config(
    instance_id: str,
    period: int,
    enabled: bool = True,
    source: str | None = None,
) -> ToolConfiguration:
    params: dict = {"period": period}
    if source is not None:
        params["source"] = source
    return ToolConfiguration(
        instance_id=instance_id,
        tool_id="ema",
        parameters=params,
        enabled=enabled,
    )


def _sma_config(instance_id: str, period: int) -> ToolConfiguration:
    return ToolConfiguration(
        instance_id=instance_id,
        tool_id="sma",
        parameters={"period": period},
    )


def _toolset(*configs: ToolConfiguration, toolset_id: str = "ts1") -> StrategyToolSet:
    return StrategyToolSet(toolset_id=toolset_id, tools=tuple(configs))


def _bar_input(bar_index: int, close: float) -> ToolComputationBarInput:
    return ToolComputationBarInput(bar_index=bar_index, price_fields={"close": close})


def _bar_payload(
    bar_index: int,
    close: float,
    tool_outputs: dict | None = None,
) -> HistoricalBarPayload:
    return HistoricalBarPayload(
        bar_index=bar_index,
        price_fields={"close": close},
        tool_outputs=tool_outputs or {},
    )


# ===========================================================================
# EMA_METADATA — registry contract
# ===========================================================================

class TestEmaMetadata:
    def test_tool_id(self):
        assert EMA_METADATA.tool_id == "ema"

    def test_name(self):
        assert "Exponential" in EMA_METADATA.name

    def test_category_is_indicator(self):
        assert EMA_METADATA.category == ToolCategory.indicator

    def test_status_is_stable(self):
        assert EMA_METADATA.status == ToolStatus.stable

    def test_output_feature_names(self):
        assert EMA_METADATA.output_feature_names == ("ema",)

    def test_stateful_flag_is_true(self):
        # EMA is recursive — stateful within a computation pass
        assert EMA_METADATA.stateful is True

    def test_min_warmup_bars_zero(self):
        # minimum when period=1; actual warmup = period - 1
        assert EMA_METADATA.min_warmup_bars == 0

    def test_period_param_required_int(self):
        spec = next(p for p in EMA_METADATA.parameters if p.name == "period")
        assert spec.required is True
        assert spec.type_label == "int"
        assert spec.min_value == 1

    def test_source_param_optional_str(self):
        spec = next(p for p in EMA_METADATA.parameters if p.name == "source")
        assert spec.required is False
        assert spec.type_label == "str"
        assert spec.default == "close"
        assert spec.options == ("close", "open", "high", "low", "hl2", "hlc3", "ohlc4")

    def test_visualization_line_overlay(self):
        assert VisualizationCapability.produces_line_overlay in EMA_METADATA.visualization_capabilities

    def test_registered_in_default_registry(self):
        registry = create_default_registry()
        assert "ema" in registry
        assert "sma" in registry
        assert "rsi" in registry
        assert "macd" in registry
        assert len(registry) == 10   # sma, ema, rsi, rsi_midline, rsi_smoothing, macd, atr, bollinger_bands, volume, volume_ma

    def test_registry_get_returns_ema_metadata(self):
        registry = create_default_registry()
        meta = registry.get("ema")
        assert meta.tool_id == "ema"
        assert meta.output_feature_names == ("ema",)


# ===========================================================================
# compute_ema() — standalone IndicatorSeries path
# ===========================================================================

class TestComputeEmaStandalone:
    """Tests for the NormalizedOHLCV → IndicatorSeries path (visualization layer)."""

    def _make_candles(self, closes: list[float]):
        from datetime import datetime, timezone
        from backend.data.schemas import NormalizedOHLCV

        candles = []
        for i, close in enumerate(closes):
            candles.append(NormalizedOHLCV(
                timestamp=datetime(2024, 1, i + 1, tzinfo=timezone.utc),
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1000.0,
                symbol="TEST",
                asset_class="equity",
                timeframe="1d",
                venue="test",
                source="yahoo",
            ))
        return candles

    def test_empty_candles_returns_empty_series(self):
        result = compute_ema([], period=10)
        assert result.points == []
        assert "EMA(10)" in result.name

    def test_invalid_period_raises(self):
        with pytest.raises(ValueError, match="period must be >= 1"):
            compute_ema([], period=0)

    def test_period_1_returns_each_close(self):
        candles = self._make_candles([10.0, 20.0, 30.0])
        result = compute_ema(candles, period=1)
        values = [p.value for p in result.points]
        assert values == pytest.approx([10.0, 20.0, 30.0])

    def test_period_3_seed_equals_sma_of_first_3(self):
        candles = self._make_candles([10.0, 20.0, 30.0, 40.0])
        result = compute_ema(candles, period=3)
        assert len(result.points) == 2  # warmup=2, bars 2 and 3
        # Seed at bar 2 = SMA(10,20,30) = 20.0
        assert result.points[0].value == pytest.approx(20.0)

    def test_period_3_recursive_step(self):
        # closes = [10, 20, 30, 40], period=3, alpha=0.5
        candles = self._make_candles([10.0, 20.0, 30.0, 40.0])
        result = compute_ema(candles, period=3)
        alpha = 2.0 / (3 + 1)  # = 0.5
        seed = (10 + 20 + 30) / 3  # = 20.0
        expected_bar3 = alpha * 40.0 + (1 - alpha) * seed  # = 0.5*40 + 0.5*20 = 30.0
        assert result.points[1].value == pytest.approx(expected_bar3)

    def test_custom_name(self):
        candles = self._make_candles([100.0])
        result = compute_ema(candles, period=1, name="My EMA")
        assert result.name == "My EMA"

    def test_default_name_format(self):
        candles = self._make_candles([100.0])
        result = compute_ema(candles, period=12)
        assert result.name == "EMA(12)"

    def test_deterministic(self):
        candles = self._make_candles([10.0, 20.0, 30.0, 40.0, 50.0])
        r1 = compute_ema(candles, period=3)
        r2 = compute_ema(candles, period=3)
        assert [p.value for p in r1.points] == [p.value for p in r2.points]


# ===========================================================================
# EMA computation correctness — pipeline path
# ===========================================================================

class TestEmaComputationCorrectness:
    """Verify EMA values computed via the historical pipeline dispatcher."""

    def _run_ema(self, period: int, closes: list[float]) -> list[float]:
        bars = [_bar_input(i, c) for i, c in enumerate(closes)]
        cfg = _ema_config("e1", period)
        toolset = _toolset(cfg)
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        assert len(result.series) == 1
        return [p.value for p in result.series[0].points]

    def test_period_1_equals_each_close(self):
        closes = [10.0, 20.0, 30.0]
        values = self._run_ema(1, closes)
        assert values == pytest.approx([10.0, 20.0, 30.0])

    def test_period_1_alpha_is_1_so_ema_tracks_close(self):
        closes = [100.0, 200.0, 50.0]
        values = self._run_ema(1, closes)
        assert values == pytest.approx(closes)

    def test_period_3_seed_is_sma(self):
        closes = [10.0, 20.0, 30.0, 40.0, 50.0]
        values = self._run_ema(3, closes)
        expected_seed = (10 + 20 + 30) / 3
        assert values[0] == pytest.approx(expected_seed)

    def test_period_3_recursive_progression(self):
        closes = [10.0, 20.0, 30.0, 40.0, 50.0]
        alpha = 2.0 / (3 + 1)
        seed = (10 + 20 + 30) / 3         # 20.0
        ema3 = alpha * 40 + (1 - alpha) * seed   # 0.5*40+0.5*20=30.0
        ema4 = alpha * 50 + (1 - alpha) * ema3   # 0.5*50+0.5*30=40.0
        values = self._run_ema(3, closes)
        assert values == pytest.approx([seed, ema3, ema4])

    def test_period_2_alpha_is_two_thirds(self):
        closes = [1.0, 2.0, 3.0, 4.0]
        alpha = 2.0 / (2 + 1)   # 2/3
        seed = (1 + 2) / 2       # 1.5
        ema2 = alpha * 3 + (1 - alpha) * seed   # (2/3)*3 + (1/3)*1.5 = 2.5
        ema3 = alpha * 4 + (1 - alpha) * ema2   # (2/3)*4 + (1/3)*2.5 ≈ 3.5
        values = self._run_ema(2, closes)
        assert values == pytest.approx([seed, ema2, ema3])

    def test_constant_series_ema_equals_constant(self):
        closes = [50.0] * 10
        values = self._run_ema(4, closes)
        assert all(v == pytest.approx(50.0) for v in values)

    def test_deterministic_identical_inputs_identical_outputs(self):
        closes = [10.0, 20.0, 15.0, 30.0, 25.0, 35.0]
        v1 = self._run_ema(3, closes)
        v2 = self._run_ema(3, closes)
        assert v1 == pytest.approx(v2)

    def test_output_ref_format(self):
        bars = [_bar_input(i, 100.0) for i in range(5)]
        cfg = _ema_config("ema_fast", 2)
        result = compute_tool_outputs_for_history(_toolset(cfg), bars, _REGISTRY)
        assert result.series[0].output_ref == "ema_fast.ema"


# ===========================================================================
# EMA warmup behavior
# ===========================================================================

class TestEmaWarmup:
    def test_warmup_count_is_period_minus_1(self):
        bars = [_bar_input(i, 100.0) for i in range(6)]
        result = compute_tool_outputs_for_history(
            _toolset(_ema_config("e", 4)), bars, _REGISTRY
        )
        assert result.series[0].warmup_bar_count == 3

    def test_warmup_bars_absent_from_build_output(self):
        bars = [_bar_input(i, 100.0) for i in range(6)]
        result = compute_tool_outputs_for_history(
            _toolset(_ema_config("e", 4)), bars, _REGISTRY
        )
        bar_outputs = build_bar_tool_outputs(result)
        # period=4 → warmup=3; bars 0,1,2 must be absent
        assert 0 not in bar_outputs
        assert 1 not in bar_outputs
        assert 2 not in bar_outputs
        # bars 3,4,5 must be present
        assert 3 in bar_outputs
        assert 4 in bar_outputs
        assert 5 in bar_outputs

    def test_period_1_has_zero_warmup(self):
        bars = [_bar_input(i, 100.0) for i in range(3)]
        result = compute_tool_outputs_for_history(
            _toolset(_ema_config("e", 1)), bars, _REGISTRY
        )
        assert result.series[0].warmup_bar_count == 0
        bar_outputs = build_bar_tool_outputs(result)
        assert 0 in bar_outputs

    def test_insufficient_bars_gives_empty_points(self):
        # period=5 but only 4 bars → all warmup, no output
        bars = [_bar_input(i, 100.0) for i in range(4)]
        result = compute_tool_outputs_for_history(
            _toolset(_ema_config("e", 5)), bars, _REGISTRY
        )
        bar_outputs = build_bar_tool_outputs(result)
        assert bar_outputs == {}

    def test_exactly_period_bars_gives_one_point(self):
        bars = [_bar_input(i, float(10 * (i + 1))) for i in range(4)]
        result = compute_tool_outputs_for_history(
            _toolset(_ema_config("e", 4)), bars, _REGISTRY
        )
        assert len(result.series[0].points) == 1
        # Seed = SMA(10,20,30,40) = 25.0
        assert result.series[0].points[0].value == pytest.approx(25.0)


# ===========================================================================
# No-lookahead bias
# ===========================================================================

class TestEmaNoLookahead:
    def test_bar_index_preserved_in_output(self):
        # Non-sequential bar indices to verify mapping is preserved
        bars = [
            ToolComputationBarInput(bar_index=10, price_fields={"close": 100.0}),
            ToolComputationBarInput(bar_index=11, price_fields={"close": 102.0}),
            ToolComputationBarInput(bar_index=12, price_fields={"close": 104.0}),
        ]
        result = compute_tool_outputs_for_history(
            _toolset(_ema_config("e", 2)), bars, _REGISTRY
        )
        bar_outputs = build_bar_tool_outputs(result)
        # warmup=1, so bar 10 absent, bars 11 and 12 present
        assert 10 not in bar_outputs
        # bar 11: seed = SMA(100, 102) = 101.0
        assert bar_outputs[11]["e.ema"] == pytest.approx(101.0)
        alpha = 2.0 / 3
        expected12 = alpha * 104.0 + (1 - alpha) * 101.0
        assert bar_outputs[12]["e.ema"] == pytest.approx(expected12)

    def test_unsorted_input_gives_same_result_as_sorted(self):
        closes = [10.0, 20.0, 30.0, 40.0]
        bars_sorted = [_bar_input(i, c) for i, c in enumerate(closes)]
        bars_reversed = list(reversed(bars_sorted))
        toolset = _toolset(_ema_config("e", 2))
        r1 = compute_tool_outputs_for_history(toolset, bars_sorted, _REGISTRY)
        r2 = compute_tool_outputs_for_history(toolset, bars_reversed, _REGISTRY)
        v1 = [p.value for p in r1.series[0].points]
        v2 = [p.value for p in r2.series[0].points]
        assert v1 == pytest.approx(v2)

    def test_each_bar_uses_only_current_and_prior_closes(self):
        # Add one extra bar; earlier bars' values must not change
        closes4 = [10.0, 20.0, 30.0, 40.0]
        closes5 = [10.0, 20.0, 30.0, 40.0, 50.0]
        bars4 = [_bar_input(i, c) for i, c in enumerate(closes4)]
        bars5 = [_bar_input(i, c) for i, c in enumerate(closes5)]
        toolset = _toolset(_ema_config("e", 2))
        r4 = compute_tool_outputs_for_history(toolset, bars4, _REGISTRY)
        r5 = compute_tool_outputs_for_history(toolset, bars5, _REGISTRY)
        v4 = [p.value for p in r4.series[0].points]
        v5 = [p.value for p in r5.series[0].points]
        # First len(v4) values of v5 must equal v4 exactly
        assert v5[:len(v4)] == pytest.approx(v4)


# ===========================================================================
# Multi-instance EMA — independent state
# ===========================================================================

class TestEmaMultiInstance:
    def test_two_ema_instances_produce_two_series(self):
        bars = [_bar_input(i, float(100 + i)) for i in range(10)]
        toolset = _toolset(_ema_config("ema_fast", 3), _ema_config("ema_slow", 6))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        assert len(result.series) == 2
        refs = {s.output_ref for s in result.series}
        assert "ema_fast.ema" in refs
        assert "ema_slow.ema" in refs

    def test_two_instances_have_independent_warmup(self):
        bars = [_bar_input(i, 100.0) for i in range(10)]
        toolset = _toolset(_ema_config("f", 3), _ema_config("s", 6))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        by_id = {s.instance_id: s for s in result.series}
        assert by_id["f"].warmup_bar_count == 2
        assert by_id["s"].warmup_bar_count == 5

    def test_two_instances_have_independent_state(self):
        # Same closes, different periods — state must not leak between instances
        closes = [float(10 * (i + 1)) for i in range(8)]
        bars = [_bar_input(i, c) for i, c in enumerate(closes)]
        toolset = _toolset(_ema_config("f", 2), _ema_config("s", 4))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        by_id = {s.instance_id: s for s in result.series}

        # Verify fast EMA independently
        alpha2 = 2.0 / 3
        seed2 = (10 + 20) / 2
        expected_fast = [seed2]
        for c in closes[2:]:
            expected_fast.append(alpha2 * c + (1 - alpha2) * expected_fast[-1])
        actual_fast = [p.value for p in by_id["f"].points]
        assert actual_fast == pytest.approx(expected_fast)

        # Verify slow EMA independently
        alpha4 = 2.0 / 5
        seed4 = (10 + 20 + 30 + 40) / 4
        expected_slow = [seed4]
        for c in closes[4:]:
            expected_slow.append(alpha4 * c + (1 - alpha4) * expected_slow[-1])
        actual_slow = [p.value for p in by_id["s"].points]
        assert actual_slow == pytest.approx(expected_slow)

    def test_disabled_ema_instance_excluded(self):
        bars = [_bar_input(i, 100.0) for i in range(5)]
        active = _ema_config("active", 2, enabled=True)
        inactive = _ema_config("inactive", 2, enabled=False)
        result = compute_tool_outputs_for_history(_toolset(active, inactive), bars, _REGISTRY)
        assert len(result.series) == 1
        assert result.series[0].instance_id == "active"


# ===========================================================================
# Multi-tool proof — SMA + EMA in same toolset
# ===========================================================================

class TestMultiToolProof:
    def test_sma_and_ema_produce_separate_series(self):
        bars = [_bar_input(i, float(100 + i)) for i in range(8)]
        toolset = _toolset(_sma_config("sma_fast", 3), _ema_config("ema_fast", 3))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        assert len(result.series) == 2
        refs = {s.output_ref for s in result.series}
        assert "sma_fast.sma" in refs
        assert "ema_fast.ema" in refs

    def test_sma_and_ema_ref_keys_do_not_collide(self):
        bars = [_bar_input(i, 100.0) for i in range(6)]
        toolset = _toolset(_sma_config("tool", 3), _ema_config("tool2", 3))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        bar_outputs = build_bar_tool_outputs(result)
        # Both present at bar 2 (warmup=2 for both period=3 tools)
        assert "tool.sma" in bar_outputs[2]
        assert "tool2.ema" in bar_outputs[2]

    def test_sma_and_ema_values_differ_after_price_spike(self):
        # After warmup, SMA and EMA diverge when price spikes (EMA reacts faster)
        # period=3, alpha=0.5; seed bar: SMA=EMA=(10+10+10)/3=10
        # after spike to 40: EMA=0.5*40+0.5*10=25, SMA=(10+10+40)/3=20
        closes = [10.0, 10.0, 10.0, 40.0, 40.0]
        bars = [_bar_input(i, c) for i, c in enumerate(closes)]
        toolset = _toolset(_sma_config("sma", 3), _ema_config("ema", 3))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        by_ref = {s.output_ref: s for s in result.series}
        sma_vals = [p.value for p in by_ref["sma.sma"].points]
        ema_vals = [p.value for p in by_ref["ema.ema"].points]
        # seed (bar 2): both equal SMA of first 3 bars
        assert sma_vals[0] == pytest.approx(ema_vals[0])
        # after spike (bar 3): EMA reacts faster → EMA > SMA
        assert ema_vals[1] > sma_vals[1]

    def test_three_tool_mixed_toolset(self):
        bars = [_bar_input(i, float(100 + i)) for i in range(12)]
        toolset = _toolset(
            _sma_config("sma_fast", 3),
            _ema_config("ema_fast", 3),
            _ema_config("ema_slow", 5),
        )
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        assert len(result.series) == 3
        refs = {s.output_ref for s in result.series}
        assert "sma_fast.sma" in refs
        assert "ema_fast.ema" in refs
        assert "ema_slow.ema" in refs

    def test_no_shared_state_between_sma_and_ema(self):
        # Running SMA+EMA together must equal running each independently
        closes = [10.0, 20.0, 30.0, 40.0, 50.0]
        bars = [_bar_input(i, c) for i, c in enumerate(closes)]

        combined_result = compute_tool_outputs_for_history(
            _toolset(_sma_config("s", 3), _ema_config("e", 3)), bars, _REGISTRY
        )
        sma_result = compute_tool_outputs_for_history(
            _toolset(_sma_config("s", 3)), bars, _REGISTRY
        )
        ema_result = compute_tool_outputs_for_history(
            _toolset(_ema_config("e", 3)), bars, _REGISTRY
        )

        combined_by_ref = {s.output_ref: s for s in combined_result.series}
        combined_sma = [p.value for p in combined_by_ref["s.sma"].points]
        combined_ema = [p.value for p in combined_by_ref["e.ema"].points]
        standalone_sma = [p.value for p in sma_result.series[0].points]
        standalone_ema = [p.value for p in ema_result.series[0].points]

        assert combined_sma == pytest.approx(standalone_sma)
        assert combined_ema == pytest.approx(standalone_ema)


# ===========================================================================
# Semantic integration — EMA outputs feed evaluator
# ===========================================================================

_EMA_ABOVE_SEMANTICS = {
    "entry_rules": [{
        "rule_id": "r1",
        "label": "EMA fast above 100",
        "condition_group": {
            "group_id": "g1",
            "operator": "AND",
            "conditions": [{
                "condition_id": "c1",
                "label": None,
                "left":  {"kind": "tool_output", "ref": "ema_fast.ema"},
                "operator": ">",
                "right": {"kind": "constant", "ref": "100"},
            }],
        },
    }],
    "exit_rules": [],
}

_EMA_CROSSOVER_SEMANTICS = {
    "entry_rules": [{
        "rule_id": "r1",
        "label": "EMA fast crosses above EMA slow",
        "condition_group": {
            "group_id": "g1",
            "operator": "AND",
            "conditions": [{
                "condition_id": "c1",
                "label": None,
                "left":  {"kind": "tool_output", "ref": "ema_fast.ema"},
                "operator": "crosses_above",
                "right": {"kind": "tool_output", "ref": "ema_slow.ema"},
            }],
        },
    }],
    "exit_rules": [],
}

_SMA_EMA_CROSS_SEMANTICS = {
    "entry_rules": [{
        "rule_id": "r1",
        "label": "EMA above SMA",
        "condition_group": {
            "group_id": "g1",
            "operator": "AND",
            "conditions": [{
                "condition_id": "c1",
                "label": None,
                "left":  {"kind": "tool_output", "ref": "ema_fast.ema"},
                "operator": ">",
                "right": {"kind": "tool_output", "ref": "sma_fast.sma"},
            }],
        },
    }],
    "exit_rules": [],
}


class TestSemanticIntegration:
    def test_ema_above_constant_triggers_when_true(self):
        sem = StrategySemantics.model_validate(_EMA_ABOVE_SEMANTICS)
        bars = [_bar_payload(i, 110.0) for i in range(5)]
        toolset = _toolset(_ema_config("ema_fast", 2))
        result = evaluate_history_from_payload(sem, bars, toolset=toolset)
        traces = {t.bar_index: t for t in result.bar_results}
        # warmup=1 → bar 0 is None; bar 1+ EMA(110,110)=110 > 100 → True
        assert traces[0].entry_triggered is None
        assert traces[1].entry_triggered is True
        assert traces[4].entry_triggered is True

    def test_ema_above_constant_not_triggered_when_below(self):
        sem = StrategySemantics.model_validate(_EMA_ABOVE_SEMANTICS)
        bars = [_bar_payload(i, 90.0) for i in range(5)]
        toolset = _toolset(_ema_config("ema_fast", 2))
        result = evaluate_history_from_payload(sem, bars, toolset=toolset)
        traces = {t.bar_index: t for t in result.bar_results}
        assert traces[1].entry_triggered is False
        assert traces[4].entry_triggered is False

    def test_ema_warmup_produces_none_outcome(self):
        sem = StrategySemantics.model_validate(_EMA_ABOVE_SEMANTICS)
        bars = [_bar_payload(i, 110.0) for i in range(6)]
        toolset = _toolset(_ema_config("ema_fast", 4))  # warmup=3
        result = evaluate_history_from_payload(sem, bars, toolset=toolset)
        traces = {t.bar_index: t for t in result.bar_results}
        assert traces[0].entry_triggered is None
        assert traces[1].entry_triggered is None
        assert traces[2].entry_triggered is None
        assert traces[3].entry_triggered is True  # first valid EMA

    def test_ema_crossover_evaluation_works(self):
        sem = StrategySemantics.model_validate(_EMA_CROSSOVER_SEMANTICS)
        # Rising series: ema_fast(2) will be above ema_slow(4) after warmup
        bars = [_bar_payload(i, float(100 + i * 5)) for i in range(10)]
        toolset = _toolset(_ema_config("ema_fast", 2), _ema_config("ema_slow", 4))
        result = evaluate_history_from_payload(sem, bars, toolset=toolset)
        assert result.bars_evaluated == 10
        traces = {t.bar_index: t for t in result.bar_results}
        # slow warmup=3 → bars 0-3 are None (ema_slow unavailable until bar 3)
        assert traces[0].entry_triggered is None
        assert traces[3].entry_triggered is None  # bar 3: first bar of slow, no "previous" for crossover
        # bar 4+ should have deterministic crossover results
        assert traces[4].entry_triggered is not None

    def test_ema_above_sma_mixed_toolset_semantics(self):
        sem = StrategySemantics.model_validate(_SMA_EMA_CROSS_SEMANTICS)
        # Step-change series: flat then spike. EMA reacts faster than SMA after spike.
        # period=3, alpha=0.5; seed=100; after spike to 130:
        #   EMA=0.5*130+0.5*100=115, SMA=(100+100+130)/3=110 → EMA > SMA
        closes = [100.0, 100.0, 100.0, 130.0, 130.0, 130.0, 130.0, 130.0]
        bars = [_bar_payload(i, c) for i, c in enumerate(closes)]
        toolset = _toolset(_sma_config("sma_fast", 3), _ema_config("ema_fast", 3))
        result = evaluate_history_from_payload(sem, bars, toolset=toolset)
        assert result.bars_evaluated == 8
        traces = {t.bar_index: t for t in result.bar_results}
        # warmup=2 for both tools
        assert traces[0].entry_triggered is None
        assert traces[1].entry_triggered is None
        # bar 2: both seeded from SMA(100,100,100)=100 → EMA == SMA → False
        assert traces[2].entry_triggered is False
        # bar 3: spike — EMA(115) > SMA(110) → True
        assert traces[3].entry_triggered is True

    def test_no_manual_tool_injection_required(self):
        # Confirm toolset path works with zero manual tool_outputs
        sem = StrategySemantics.model_validate(_EMA_ABOVE_SEMANTICS)
        bars = [_bar_payload(i, 110.0) for i in range(3)]
        # All bars have empty tool_outputs — server computes from toolset
        assert all(b.tool_outputs == {} for b in bars)
        toolset = _toolset(_ema_config("ema_fast", 2))
        result = evaluate_history_from_payload(sem, bars, toolset=toolset)
        assert result.bars_evaluated == 3


# ===========================================================================
# API integration — POST /semantics/evaluate-history with EMA toolset
# ===========================================================================

class TestApiEmaIntegration:
    def _ema_toolset_payload(self, instance_id: str, period: int) -> dict:
        return {
            "toolset_id": "ts1",
            "tools": [{
                "instance_id": instance_id,
                "tool_id": "ema",
                "parameters": {"period": period},
            }],
        }

    def _bars(self, n: int, close: float = 110.0) -> list[dict]:
        return [
            {"bar_index": i, "price_fields": {"close": close}, "tool_outputs": {}}
            for i in range(n)
        ]

    def test_ema_toolset_returns_200(self):
        payload = {
            "semantics": _EMA_ABOVE_SEMANTICS,
            "bars": self._bars(5),
            "toolset": self._ema_toolset_payload("ema_fast", 2),
        }
        resp = _CLIENT.post("/semantics/evaluate-history", json=payload)
        assert resp.status_code == 200

    def test_ema_warmup_bars_null_in_api_response(self):
        payload = {
            "semantics": _EMA_ABOVE_SEMANTICS,
            "bars": self._bars(6),
            "toolset": self._ema_toolset_payload("ema_fast", 4),  # warmup=3
        }
        resp = _CLIENT.post("/semantics/evaluate-history", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        by_index = {r["bar_index"]: r for r in data["bar_results"]}
        assert by_index[0]["entry_triggered"] is None
        assert by_index[1]["entry_triggered"] is None
        assert by_index[2]["entry_triggered"] is None
        assert by_index[3]["entry_triggered"] is True

    def test_sma_and_ema_mixed_toolset_api(self):
        payload = {
            "semantics": _SMA_EMA_CROSS_SEMANTICS,
            "bars": self._bars(10, close=float(100)),
            "toolset": {
                "toolset_id": "ts1",
                "tools": [
                    {"instance_id": "sma_fast", "tool_id": "sma", "parameters": {"period": 3}},
                    {"instance_id": "ema_fast", "tool_id": "ema", "parameters": {"period": 3}},
                ],
            },
        }
        resp = _CLIENT.post("/semantics/evaluate-history", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["bars_evaluated"] == 10

    def test_ema_invalid_period_rejected(self):
        payload = {
            "semantics": _EMA_ABOVE_SEMANTICS,
            "bars": self._bars(5),
            "toolset": {
                "toolset_id": "ts1",
                "tools": [{"instance_id": "e", "tool_id": "ema", "parameters": {"period": 0}}],
            },
        }
        resp = _CLIENT.post("/semantics/evaluate-history", json=payload)
        assert resp.status_code == 422


# ===========================================================================
# Validation — parameter validation via existing infrastructure
# ===========================================================================

class TestEmaValidation:
    def test_valid_config_passes(self):
        from backend.tools.validation import validate_tool_configuration
        cfg = _ema_config("e", 20)
        # Should not raise
        validate_tool_configuration(cfg, EMA_METADATA)

    def test_valid_config_with_source_passes(self):
        from backend.tools.validation import validate_tool_configuration
        cfg = _ema_config("e", 12, source="close")
        validate_tool_configuration(cfg, EMA_METADATA)

    def test_invalid_source_rejected_by_validation(self):
        from backend.tools.validation import validate_tool_configuration, ConfigurationValidationError
        cfg = _ema_config("e", 12, source="bogus")
        with pytest.raises(ConfigurationValidationError) as exc_info:
            validate_tool_configuration(cfg, EMA_METADATA)
        assert "source" in str(exc_info.value)
        assert "bogus" in str(exc_info.value)
        assert "allowed options" in str(exc_info.value)

    def test_missing_period_raises(self):
        from backend.tools.validation import validate_tool_configuration, ConfigurationValidationError
        cfg = ToolConfiguration(instance_id="e", tool_id="ema", parameters={})
        with pytest.raises(ConfigurationValidationError, match="period"):
            validate_tool_configuration(cfg, EMA_METADATA)

    def test_period_below_min_raises(self):
        from backend.tools.validation import validate_tool_configuration, ConfigurationValidationError
        cfg = ToolConfiguration(instance_id="e", tool_id="ema", parameters={"period": 0})
        with pytest.raises(ConfigurationValidationError, match="minimum"):
            validate_tool_configuration(cfg, EMA_METADATA)

    def test_unknown_parameter_raises(self):
        from backend.tools.validation import validate_tool_configuration, ConfigurationValidationError
        cfg = ToolConfiguration(instance_id="e", tool_id="ema", parameters={"period": 10, "bogus": 1})
        with pytest.raises(ConfigurationValidationError, match="unknown parameter"):
            validate_tool_configuration(cfg, EMA_METADATA)

    def test_ema_toolset_validates_cleanly(self):
        from backend.tools.validation import validate_strategy_toolset_against_registry
        toolset = _toolset(_ema_config("f", 12), _ema_config("s", 26))
        result = validate_strategy_toolset_against_registry(toolset, _REGISTRY)
        assert result.valid is True

    def test_mixed_sma_ema_toolset_validates(self):
        from backend.tools.validation import validate_strategy_toolset_against_registry
        toolset = _toolset(_sma_config("s", 20), _ema_config("e", 12))
        result = validate_strategy_toolset_against_registry(toolset, _REGISTRY)
        assert result.valid is True


# ===========================================================================
# Error cases
# ===========================================================================

class TestEmaErrorCases:
    def test_missing_close_field_raises(self):
        bars = [
            ToolComputationBarInput(bar_index=0, price_fields={"open": 100.0}),
            ToolComputationBarInput(bar_index=1, price_fields={"open": 101.0}),
        ]
        with pytest.raises(ToolComputationError, match="missing 'close'"):
            compute_tool_outputs_for_history(
                _toolset(_ema_config("e", 2)), bars, _REGISTRY
            )

    def test_duplicate_bar_index_raises(self):
        bars = [_bar_input(0, 100.0), _bar_input(0, 101.0)]
        with pytest.raises(ToolComputationError, match="duplicate bar_index"):
            compute_tool_outputs_for_history(
                _toolset(_ema_config("e", 2)), bars, _REGISTRY
            )

    def test_empty_bars_returns_empty_points(self):
        result = compute_tool_outputs_for_history(
            _toolset(_ema_config("e", 3)), [], _REGISTRY
        )
        assert result.total_bars == 0
        assert result.series[0].points == ()

    def test_unknown_tool_id_raises(self):
        bars = [_bar_input(i, 100.0) for i in range(5)]
        cfg = ToolConfiguration(
            instance_id="bad",
            tool_id="unknown_indicator_xyz",
            parameters={"period": 14},
        )
        with pytest.raises(ToolComputationError, match="not found in registry"):
            compute_tool_outputs_for_history(_toolset(cfg), bars, _REGISTRY)


# ===========================================================================
# Architecture guards
# ===========================================================================

class TestArchitectureGuards:
    def _has_import(self, code: str, module: str) -> bool:
        """Return True if code contains an actual import of the given module."""
        return (
            f"import {module}" in code
            or f"from {module}" in code
        )

    def test_ema_module_does_not_import_forbidden_layers(self):
        import backend.tools.ema as ema_mod
        with open(ema_mod.__file__) as f:
            code = f.read()
        assert not self._has_import(code, "backend.backtesting")
        assert not self._has_import(code, "backend.execution")
        assert not self._has_import(code, "backend.forward_testing")

    def test_historical_computation_does_not_import_forbidden_layers(self):
        import backend.tools.historical_computation as hc_mod
        with open(hc_mod.__file__) as f:
            code = f.read()
        assert not self._has_import(code, "backend.backtesting")
        assert not self._has_import(code, "backend.execution")
        assert not self._has_import(code, "backend.forward_testing")

    def test_historical_evaluator_does_not_compute_ema(self):
        import backend.strategy_registry.historical_evaluator as he_mod
        with open(he_mod.__file__) as f:
            code = f.read()
        assert "compute_ema" not in code
        assert "_compute_ema" not in code

    def test_scalar_evaluator_does_not_compute_ema(self):
        import backend.strategy_registry.scalar_evaluator as se_mod
        with open(se_mod.__file__) as f:
            code = f.read()
        assert "compute_ema" not in code
        assert "_compute_ema" not in code

    def test_ema_is_callable_primitive_not_strategy(self):
        # EMA produces outputs, not trade signals — output_feature_names contains data refs
        assert "ema" in EMA_METADATA.output_feature_names
        # No signal-generation or portfolio fields exist on ToolMetadata
        assert not hasattr(EMA_METADATA, "generates_signals")
        assert not hasattr(EMA_METADATA, "manages_portfolio")


# ===========================================================================
# Source-aware EMA computation — Tool-Backend-1A
# ===========================================================================

def _bar_full(
    bar_index: int,
    open_: float,
    high: float,
    low: float,
    close: float,
) -> ToolComputationBarInput:
    """Bar with all OHLCV price fields for source-aware computation tests."""
    return ToolComputationBarInput(
        bar_index=bar_index,
        price_fields={"open": open_, "high": high, "low": low, "close": close, "volume": 0.0},
    )


def _ema_source_bars() -> list[ToolComputationBarInput]:
    """
    5 bars with distinct OHLCV values, designed so each source field produces
    a unique series that can be verified against a known EMA computation.

    Bar | open  | high  | low   | close | hl2   | hlc3  | ohlc4
    ----|-------|-------|-------|-------|-------|-------|------
      0 | 10.0  | 15.0  |  8.0  | 12.0  | 11.5  | 11.67 | 11.25
      1 | 11.0  | 16.0  |  9.0  | 13.0  | 12.5  | 12.67 | 12.25
      2 | 12.0  | 17.0  | 10.0  | 14.0  | 13.5  | 13.67 | 13.25
      3 | 13.0  | 18.0  | 11.0  | 15.0  | 14.5  | 14.67 | 14.25
      4 | 14.0  | 19.0  | 12.0  | 16.0  | 15.5  | 15.67 | 15.25
    """
    data = [
        (10.0, 15.0,  8.0, 12.0),
        (11.0, 16.0,  9.0, 13.0),
        (12.0, 17.0, 10.0, 14.0),
        (13.0, 18.0, 11.0, 15.0),
        (14.0, 19.0, 12.0, 16.0),
    ]
    return [_bar_full(i, *row) for i, row in enumerate(data)]


def _compute_ema_from_values(values: list[float], period: int) -> list[float]:
    """Reference EMA: seed = SMA(values[:period]), alpha = 2/(period+1)."""
    assert period <= len(values)
    alpha  = 2.0 / (period + 1)
    warmup = period - 1
    result: list[float] = []
    ema: float | None = None
    for i, v in enumerate(values):
        if i < warmup:
            continue
        if ema is None:
            ema = sum(values[:period]) / period
        else:
            ema = alpha * v + (1.0 - alpha) * ema
        result.append(ema)
    return result


class TestEmaSourceAware:
    """Verify _compute_ema_series correctly dispatches to the selected source."""

    PERIOD = 3  # enough bars to have at least one output point from 5 bars

    def _run(self, source: str | None = None) -> tuple[list[float], ToolComputationBarInput]:
        bars   = _ema_source_bars()
        cfg    = _ema_config("e", self.PERIOD, source=source)
        result = compute_tool_outputs_for_history(_toolset(cfg), bars, _REGISTRY)
        pts    = [p.value for p in result.series[0].points]
        return pts, bars

    # ── Default / close ──────────────────────────────────────────────────────

    def test_default_source_matches_close(self):
        """Omitting source must give the same result as source='close'."""
        pts_default, bars = self._run(source=None)
        pts_close, _      = self._run(source="close")
        assert pts_default == pytest.approx(pts_close, rel=1e-9)

    def test_close_source_matches_reference(self):
        closes   = [12.0, 13.0, 14.0, 15.0, 16.0]
        expected = _compute_ema_from_values(closes, self.PERIOD)
        pts, _   = self._run(source="close")
        assert pts == pytest.approx(expected, rel=1e-9)

    # ── Simple named fields ──────────────────────────────────────────────────

    def test_open_source_matches_reference(self):
        opens    = [10.0, 11.0, 12.0, 13.0, 14.0]
        expected = _compute_ema_from_values(opens, self.PERIOD)
        pts, _   = self._run(source="open")
        assert pts == pytest.approx(expected, rel=1e-9)

    def test_high_source_matches_reference(self):
        highs    = [15.0, 16.0, 17.0, 18.0, 19.0]
        expected = _compute_ema_from_values(highs, self.PERIOD)
        pts, _   = self._run(source="high")
        assert pts == pytest.approx(expected, rel=1e-9)

    def test_low_source_matches_reference(self):
        lows     = [8.0, 9.0, 10.0, 11.0, 12.0]
        expected = _compute_ema_from_values(lows, self.PERIOD)
        pts, _   = self._run(source="low")
        assert pts == pytest.approx(expected, rel=1e-9)

    # ── Composite fields ─────────────────────────────────────────────────────

    def test_hl2_source_matches_reference(self):
        # hl2 = (high + low) / 2
        data = [(15.0, 8.0), (16.0, 9.0), (17.0, 10.0), (18.0, 11.0), (19.0, 12.0)]
        hl2  = [(h + l) / 2.0 for h, l in data]
        expected = _compute_ema_from_values(hl2, self.PERIOD)
        pts, _   = self._run(source="hl2")
        assert pts == pytest.approx(expected, rel=1e-9)

    def test_hlc3_source_matches_reference(self):
        # hlc3 = (high + low + close) / 3
        data = [
            (15.0,  8.0, 12.0),
            (16.0,  9.0, 13.0),
            (17.0, 10.0, 14.0),
            (18.0, 11.0, 15.0),
            (19.0, 12.0, 16.0),
        ]
        hlc3     = [(h + l + c) / 3.0 for h, l, c in data]
        expected = _compute_ema_from_values(hlc3, self.PERIOD)
        pts, _   = self._run(source="hlc3")
        assert pts == pytest.approx(expected, rel=1e-9)

    def test_ohlc4_source_matches_reference(self):
        # ohlc4 = (open + high + low + close) / 4
        data = [
            (10.0, 15.0,  8.0, 12.0),
            (11.0, 16.0,  9.0, 13.0),
            (12.0, 17.0, 10.0, 14.0),
            (13.0, 18.0, 11.0, 15.0),
            (14.0, 19.0, 12.0, 16.0),
        ]
        ohlc4    = [(o + h + l + c) / 4.0 for o, h, l, c in data]
        expected = _compute_ema_from_values(ohlc4, self.PERIOD)
        pts, _   = self._run(source="ohlc4")
        assert pts == pytest.approx(expected, rel=1e-9)

    # ── Sources differ from each other ───────────────────────────────────────

    def test_open_differs_from_close(self):
        """Different sources must produce different EMA values."""
        pts_close, _ = self._run(source="close")
        pts_open, _  = self._run(source="open")
        # All source values differ in the fixture so EMAs must differ
        assert pts_close != pytest.approx(pts_open, rel=1e-6)

    def test_hl2_differs_from_close(self):
        pts_close, _ = self._run(source="close")
        pts_hl2, _   = self._run(source="hl2")
        assert pts_close != pytest.approx(pts_hl2, rel=1e-6)

    # ── Invalid source ───────────────────────────────────────────────────────

    def test_invalid_source_raises(self):
        bars = _ema_source_bars()
        cfg  = _ema_config("e", 2, source="vwap")
        with pytest.raises(ToolComputationError, match="configuration invalid"):
            compute_tool_outputs_for_history(_toolset(cfg), bars, _REGISTRY)

    def test_invalid_source_error_names_the_bad_value(self):
        bars = _ema_source_bars()
        cfg  = _ema_config("e", 2, source="typical_price_typo")
        with pytest.raises(ToolComputationError, match="typical_price_typo"):
            compute_tool_outputs_for_history(_toolset(cfg), bars, _REGISTRY)

    # ── Missing required field for composite source ──────────────────────────

    def test_hl2_missing_high_raises(self):
        """hl2 requires 'high'; bar with only close should raise."""
        bars = [_bar_input(i, float(10 + i)) for i in range(4)]  # close-only bars
        cfg  = _ema_config("e", 2, source="hl2")
        with pytest.raises(ToolComputationError, match="missing 'high'"):
            compute_tool_outputs_for_history(_toolset(cfg), bars, _REGISTRY)

    def test_ohlc4_missing_open_raises(self):
        """ohlc4 requires 'open'; bar without open should raise."""
        bars = [
            ToolComputationBarInput(
                bar_index=i,
                price_fields={"high": float(15 + i), "low": float(8 + i), "close": float(12 + i)},
            )
            for i in range(4)
        ]
        cfg = _ema_config("e", 2, source="ohlc4")
        with pytest.raises(ToolComputationError, match="missing 'open'"):
            compute_tool_outputs_for_history(_toolset(cfg), bars, _REGISTRY)

    # ── Backward compatibility ───────────────────────────────────────────────

    def test_existing_close_only_bars_still_work(self):
        """Strategies using only close price_fields must still compute correctly."""
        closes = [100.0, 102.0, 104.0, 103.0, 105.0]
        bars   = [_bar_input(i, c) for i, c in enumerate(closes)]
        cfg    = _ema_config("e", 3)  # no source parameter → defaults to close
        result = compute_tool_outputs_for_history(_toolset(cfg), bars, _REGISTRY)
        expected = _compute_ema_from_values(closes, 3)
        pts = [p.value for p in result.series[0].points]
        assert pts == pytest.approx(expected, rel=1e-9)
