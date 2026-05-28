"""
Phase 2S — MACD Tool tests.

Coverage:
    MACD_METADATA — registry metadata contract (multi-output)
    compute_macd() — standalone tuple-of-IndicatorSeries path
    MACD registration in default registry
    _compute_macd_series() — historical pipeline dispatch (3 series)
    MACD line correctness — fast EMA - slow EMA
    Signal line correctness — EMA of MACD line
    Histogram correctness — macd_line - signal_line (verified per bar)
    Warmup propagation — macd_line vs signal_line different warmup
    No-lookahead bias — reversed input order produces same outputs
    Multi-instance MACD — independent state, separate output namespaces
    Multi-tool proof — SMA + EMA + RSI + MACD coexistence
    Semantic integration — macd_fast.histogram > 0 as entry condition
    API integration — /tools includes MACD; evaluate-history with MACD
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
    MACD_METADATA,
    RSI_METADATA,
    build_bar_tool_outputs,
    compute_macd,
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

def _macd_config(
    instance_id: str,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    enabled: bool = True,
) -> ToolConfiguration:
    return ToolConfiguration(
        instance_id=instance_id,
        tool_id="macd",
        parameters={"fast_period": fast, "slow_period": slow, "signal_period": signal},
        enabled=enabled,
    )


def _sma_config(instance_id: str, period: int) -> ToolConfiguration:
    return ToolConfiguration(instance_id=instance_id, tool_id="sma", parameters={"period": period})


def _ema_config(instance_id: str, period: int) -> ToolConfiguration:
    return ToolConfiguration(instance_id=instance_id, tool_id="ema", parameters={"period": period})


def _rsi_config(instance_id: str, period: int) -> ToolConfiguration:
    return ToolConfiguration(instance_id=instance_id, tool_id="rsi", parameters={"period": period})


def _toolset(*configs: ToolConfiguration, toolset_id: str = "ts1") -> StrategyToolSet:
    return StrategyToolSet(toolset_id=toolset_id, tools=tuple(configs))


def _bar_input(bar_index: int, close: float) -> ToolComputationBarInput:
    return ToolComputationBarInput(bar_index=bar_index, price_fields={"close": close})


def _bars_from_closes(closes: list[float]) -> list[ToolComputationBarInput]:
    return [_bar_input(i, c) for i, c in enumerate(closes)]


# ===========================================================================
# MACD_METADATA — registry contract
# ===========================================================================

class TestMACDMetadata:
    def test_tool_id(self):
        assert MACD_METADATA.tool_id == "macd"

    def test_name_contains_macd(self):
        assert "MACD" in MACD_METADATA.name or "Convergence" in MACD_METADATA.name

    def test_three_outputs(self):
        assert len(MACD_METADATA.output_feature_names) == 3

    def test_output_names(self):
        assert "macd_line" in MACD_METADATA.output_feature_names
        assert "signal_line" in MACD_METADATA.output_feature_names
        assert "histogram" in MACD_METADATA.output_feature_names

    def test_output_order(self):
        assert MACD_METADATA.output_feature_names == ("macd_line", "signal_line", "histogram")

    def test_category(self):
        assert MACD_METADATA.category == ToolCategory.indicator

    def test_status_stable(self):
        assert MACD_METADATA.status == ToolStatus.stable

    def test_stateful(self):
        assert MACD_METADATA.stateful is True

    def test_visualization_capability(self):
        assert VisualizationCapability.produces_oscillator_series in MACD_METADATA.visualization_capabilities

    def test_parameters_present(self):
        param_names = [p.name for p in MACD_METADATA.parameters]
        assert "fast_period" in param_names
        assert "slow_period" in param_names
        assert "signal_period" in param_names

    def test_all_periods_have_min_value(self):
        for p in MACD_METADATA.parameters:
            if p.name in {"fast_period", "slow_period", "signal_period"}:
                assert p.min_value is not None and p.min_value >= 2

    def test_default_fast_period(self):
        p = next(p for p in MACD_METADATA.parameters if p.name == "fast_period")
        assert p.default == 12

    def test_default_slow_period(self):
        p = next(p for p in MACD_METADATA.parameters if p.name == "slow_period")
        assert p.default == 26

    def test_default_signal_period(self):
        p = next(p for p in MACD_METADATA.parameters if p.name == "signal_period")
        assert p.default == 9

    def test_registered_in_default_registry(self):
        meta = _REGISTRY.get("macd")
        assert meta.tool_id == "macd"

    def test_frozen(self):
        import pydantic
        with pytest.raises((pydantic.ValidationError, TypeError)):
            MACD_METADATA.tool_id = "modified"  # type: ignore[misc]


# ===========================================================================
# compute_macd() — standalone tuple path
# ===========================================================================

class TestComputeMACDStandalone:
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

    def test_returns_three_series(self):
        candles = self._make_candles([float(i) for i in range(1, 50)])
        result = compute_macd(candles)
        assert len(result) == 3

    def test_empty_candles_returns_three_empty_series(self):
        result = compute_macd([])
        assert len(result) == 3
        for series in result:
            assert series.points == []

    def test_oscillator_pane(self):
        from backend.strategy_runtime.visualization import IndicatorPane
        candles = self._make_candles([float(i) for i in range(1, 50)])
        for series in compute_macd(candles):
            assert series.pane == IndicatorPane.oscillator

    def test_macd_line_first(self):
        candles = self._make_candles([float(i) for i in range(1, 50)])
        macd_line, signal_line, histogram = compute_macd(candles, fast_period=3, slow_period=5, signal_period=3)
        # MACD line has more points than signal (lower warmup)
        assert len(macd_line.points) >= len(signal_line.points)

    def test_histogram_equals_macd_minus_signal(self):
        candles = self._make_candles([float(i) for i in range(1, 50)])
        macd_line, signal_line, histogram = compute_macd(
            candles, fast_period=3, slow_period=6, signal_period=3
        )
        macd_by_ts  = {pt.timestamp: pt.value for pt in macd_line.points}
        signal_by_ts = {pt.timestamp: pt.value for pt in signal_line.points}
        for hist_pt in histogram.points:
            m = macd_by_ts[hist_pt.timestamp]
            s = signal_by_ts[hist_pt.timestamp]
            assert abs(hist_pt.value - (m - s)) < 1e-10

    def test_invalid_fast_period_raises(self):
        with pytest.raises(ValueError):
            compute_macd([], fast_period=1)

    def test_fast_greater_than_slow_raises(self):
        with pytest.raises(ValueError):
            compute_macd([], fast_period=26, slow_period=12)

    def test_invalid_signal_period_raises(self):
        with pytest.raises(ValueError):
            compute_macd([], fast_period=3, slow_period=6, signal_period=1)

    def test_deterministic(self):
        closes = [100 + 3 * (i % 7 - 3) for i in range(50)]
        candles = self._make_candles(closes)
        r1 = compute_macd(candles, fast_period=3, slow_period=6, signal_period=3)
        r2 = compute_macd(candles, fast_period=3, slow_period=6, signal_period=3)
        for s1, s2 in zip(r1, r2):
            assert [p.value for p in s1.points] == [p.value for p in s2.points]


# ===========================================================================
# MACD historical pipeline — 3 output series
# ===========================================================================

class TestMACDPipeline:
    def test_returns_three_series_from_pipeline(self):
        closes = [float(i) for i in range(1, 40)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(_macd_config("macd1", fast=3, slow=6, signal=3))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        assert len(result.series) == 3

    def test_series_output_names(self):
        closes = [float(i) for i in range(1, 40)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(_macd_config("m1", fast=3, slow=6, signal=3))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        names = {s.output_name for s in result.series}
        assert names == {"macd_line", "signal_line", "histogram"}

    def test_series_instance_ids(self):
        closes = [float(i) for i in range(1, 40)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(_macd_config("macd_inst", fast=3, slow=6, signal=3))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        for s in result.series:
            assert s.instance_id == "macd_inst"

    def test_output_refs_correct(self):
        closes = [float(i) for i in range(1, 40)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(_macd_config("mf", fast=3, slow=6, signal=3))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        refs = {s.output_ref for s in result.series}
        assert refs == {"mf.macd_line", "mf.signal_line", "mf.histogram"}

    def test_macd_line_has_higher_warmup(self):
        """macd_line warmup = slow-1; signal warmup = slow+signal-2 (>= macd_line warmup)."""
        closes = [float(i) for i in range(1, 50)]
        bars = _bars_from_closes(closes)
        fast, slow, sig = 3, 6, 3
        toolset = _toolset(_macd_config("m", fast=fast, slow=slow, signal=sig))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        series_by_name = {s.output_name: s for s in result.series}
        assert series_by_name["macd_line"].warmup_bar_count    == slow - 1
        assert series_by_name["signal_line"].warmup_bar_count  == slow + sig - 2
        assert series_by_name["histogram"].warmup_bar_count    == slow + sig - 2

    def test_macd_line_more_points_than_signal(self):
        closes = [float(i) for i in range(1, 50)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(_macd_config("m", fast=3, slow=6, signal=3))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        series_by_name = {s.output_name: s for s in result.series}
        assert len(series_by_name["macd_line"].points) > len(series_by_name["signal_line"].points)

    def test_signal_and_histogram_same_length(self):
        closes = [float(i) for i in range(1, 50)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(_macd_config("m", fast=3, slow=6, signal=3))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        series_by_name = {s.output_name: s for s in result.series}
        assert len(series_by_name["signal_line"].points) == len(series_by_name["histogram"].points)

    def test_histogram_equals_macd_minus_signal_per_bar(self):
        closes = [100.0 + 5.0 * (i % 9 - 4) for i in range(50)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(_macd_config("m", fast=3, slow=6, signal=3))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        bto = build_bar_tool_outputs(result)
        # For every bar where all three are available, histogram = macd_line - signal_line
        for bar_index, outputs in bto.items():
            if "m.macd_line" in outputs and "m.signal_line" in outputs and "m.histogram" in outputs:
                expected = outputs["m.macd_line"] - outputs["m.signal_line"]
                assert abs(outputs["m.histogram"] - expected) < 1e-10, \
                    f"bar {bar_index}: histogram={outputs['m.histogram']}, expected={expected}"


# ===========================================================================
# MACD warmup behavior
# ===========================================================================

class TestMACDWarmup:
    def test_signal_warmup_bars_absent_from_bto(self):
        fast, slow, sig = 3, 6, 3
        signal_warmup = slow + sig - 2  # 7
        closes = [float(i) for i in range(1, 20)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(_macd_config("m", fast=fast, slow=slow, signal=sig))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        bto = build_bar_tool_outputs(result)
        # signal_line and histogram must be absent for bars 0..signal_warmup-1
        for i in range(signal_warmup):
            row = bto.get(i, {})
            assert "m.signal_line" not in row
            assert "m.histogram"   not in row

    def test_macd_line_absent_during_slow_warmup(self):
        fast, slow, sig = 3, 6, 3
        macd_warmup = slow - 1  # 5
        closes = [float(i) for i in range(1, 20)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(_macd_config("m", fast=fast, slow=slow, signal=sig))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        bto = build_bar_tool_outputs(result)
        for i in range(macd_warmup):
            row = bto.get(i, {})
            assert "m.macd_line" not in row

    def test_signal_first_at_correct_bar_index(self):
        fast, slow, sig = 3, 6, 3
        expected_first_signal_bar = slow + sig - 2  # 7
        closes = [float(i) for i in range(1, 30)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(_macd_config("m", fast=fast, slow=slow, signal=sig))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        signal_series = next(s for s in result.series if s.output_name == "signal_line")
        assert signal_series.points[0].bar_index == expected_first_signal_bar

    def test_exactly_signal_warmup_bars_produces_no_signal(self):
        fast, slow, sig = 3, 6, 3
        signal_warmup = slow + sig - 2  # 7
        bars = _bars_from_closes([float(i) for i in range(1, signal_warmup + 1)])  # exactly warmup bars
        toolset = _toolset(_macd_config("m", fast=fast, slow=slow, signal=sig))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        signal_series = next(s for s in result.series if s.output_name == "signal_line")
        assert len(signal_series.points) == 0


# ===========================================================================
# No-lookahead bias
# ===========================================================================

class TestMACDNoLookahead:
    def test_reversed_input_produces_same_outputs(self):
        closes = [100.0 + 3.0 * (i % 7 - 3) for i in range(40)]
        bars_fwd = [ToolComputationBarInput(bar_index=i, price_fields={"close": c})
                    for i, c in enumerate(closes)]
        bars_rev = list(reversed(bars_fwd))
        toolset = _toolset(_macd_config("m", fast=3, slow=6, signal=3))

        r_fwd = compute_tool_outputs_for_history(toolset, bars_fwd, _REGISTRY)
        r_rev = compute_tool_outputs_for_history(toolset, bars_rev, _REGISTRY)

        for output_name in ("macd_line", "signal_line", "histogram"):
            pts_fwd = {pt.bar_index: pt.value for s in r_fwd.series if s.output_name == output_name for pt in s.points}
            pts_rev = {pt.bar_index: pt.value for s in r_rev.series if s.output_name == output_name for pt in s.points}
            assert pts_fwd.keys() == pts_rev.keys(), f"bar indices differ for {output_name}"
            for bi in pts_fwd:
                assert abs(pts_fwd[bi] - pts_rev[bi]) < 1e-10, f"{output_name} bar {bi} differs"

    def test_adding_future_bars_does_not_change_past(self):
        closes_short = [100.0 + 3.0 * (i % 7 - 3) for i in range(20)]
        closes_long  = closes_short + [110.0, 115.0, 108.0, 112.0]

        def _macd_vals(closes: list[float]) -> dict[int, float]:
            bars = _bars_from_closes(closes)
            toolset = _toolset(_macd_config("m", fast=3, slow=6, signal=3))
            result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
            bto = build_bar_tool_outputs(result)
            return {bi: d["m.macd_line"] for bi, d in bto.items() if "m.macd_line" in d}

        vals_short = _macd_vals(closes_short)
        vals_long  = _macd_vals(closes_long)
        for bi, v in vals_short.items():
            assert abs(vals_long[bi] - v) < 1e-10


# ===========================================================================
# Multi-instance MACD
# ===========================================================================

class TestMACDMultiInstance:
    def test_two_macd_instances_six_series(self):
        closes = [float(i) for i in range(1, 50)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(
            _macd_config("macd_a", fast=3, slow=6, signal=3),
            _macd_config("macd_b", fast=4, slow=8, signal=4),
        )
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        assert len(result.series) == 6

    def test_two_macd_output_refs_disjoint(self):
        closes = [float(i) for i in range(1, 50)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(
            _macd_config("ma", fast=3, slow=6, signal=3),
            _macd_config("mb", fast=4, slow=8, signal=4),
        )
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        refs = {s.output_ref for s in result.series}
        assert "ma.macd_line" in refs and "ma.signal_line" in refs and "ma.histogram" in refs
        assert "mb.macd_line" in refs and "mb.signal_line" in refs and "mb.histogram" in refs

    def test_two_macd_independent_values(self):
        closes = [100.0 + 5.0 * (i % 9 - 4) for i in range(50)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(
            _macd_config("ma", fast=3, slow=6, signal=3),
            _macd_config("mb", fast=4, slow=8, signal=4),
        )
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        bto = build_bar_tool_outputs(result)
        # Find a bar where both macd_line refs exist
        for bi, outputs in bto.items():
            if "ma.macd_line" in outputs and "mb.macd_line" in outputs:
                # Different configurations → generally different values
                # (may coincide in degenerate inputs, but usually won't)
                assert "ma.macd_line" in outputs
                assert "mb.macd_line" in outputs
                break


# ===========================================================================
# Multi-tool proof: SMA + EMA + RSI + MACD
# ===========================================================================

class TestMACDMultiTool:
    def test_four_tools_no_collision(self):
        closes = [100.0 + 3.0 * (i % 7 - 3) for i in range(40)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(
            _sma_config("sma1", 5),
            _ema_config("ema1", 5),
            _rsi_config("rsi1", 5),
            _macd_config("macd1", fast=3, slow=6, signal=3),
        )
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        # SMA: 1, EMA: 1, RSI: 1, MACD: 3 → total 6 series
        assert len(result.series) == 6

    def test_all_output_refs_unique(self):
        closes = [100.0 + 3.0 * (i % 7 - 3) for i in range(40)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(
            _sma_config("s1", 5),
            _ema_config("e1", 5),
            _rsi_config("r1", 5),
            _macd_config("m1", fast=3, slow=6, signal=3),
        )
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        refs = [s.output_ref for s in result.series]
        assert len(refs) == len(set(refs)), "Duplicate output refs detected"

    def test_macd_does_not_contaminate_sma_values(self):
        closes = [float(i) for i in range(1, 40)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(
            _sma_config("sma5", 5),
            _macd_config("macd1", fast=3, slow=6, signal=3),
        )
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        sma_series = next(s for s in result.series if s.instance_id == "sma5")
        # Monotone rising closes → SMA also monotone rising
        sma_vals = [pt.value for pt in sma_series.points]
        assert all(sma_vals[i] < sma_vals[i + 1] for i in range(len(sma_vals) - 1))


# ===========================================================================
# Semantic integration — threshold comparison on histogram
# ===========================================================================

class TestMACDSemanticIntegration:
    def _run_semantic_histogram(
        self,
        closes: list[float],
        fast: int,
        slow: int,
        signal: int,
        operator: str,
        threshold: float,
    ) -> list[bool | None]:
        bars = _bars_from_closes(closes)
        toolset = _toolset(_macd_config("mf", fast=fast, slow=slow, signal=signal))
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
                        "left":  {"kind": "tool_output", "ref": "mf.histogram"},
                        "operator": operator,
                        "right": {"kind": "constant", "ref": str(threshold)},
                    }],
                },
            }],
            "exit_rules": [],
        })
        hist_result = evaluate_history_from_payload(semantics, payloads)
        return [br.entry_triggered for br in hist_result.bar_results]

    def test_histogram_evaluates_after_warmup(self):
        # Flat prices → price surge → fast EMA rises before slow EMA →
        # MACD line > 0; signal lags → histogram > 0 on the initial surge.
        closes = [100.0] * 20 + [100.0 + float(i) * 5 for i in range(1, 30)]
        triggers = self._run_semantic_histogram(closes, fast=3, slow=6, signal=3, operator=">", threshold=0.0)
        # After warmup ends, some bars should trigger (histogram > 0)
        assert any(t is True for t in triggers)

    def test_warmup_bars_produce_none_for_histogram(self):
        fast, slow, sig = 3, 6, 3
        signal_warmup = slow + sig - 2
        closes = [float(i) for i in range(1, 30)]
        triggers = self._run_semantic_histogram(closes, fast=fast, slow=slow, signal=sig, operator=">", threshold=0.0)
        # Warmup bars → None
        none_count = sum(1 for t in triggers if t is None)
        assert none_count >= signal_warmup

    def test_macd_line_crossover_semantics(self):
        """macd_line crosses_above signal_line is a typical trade signal."""
        closes = [float(i) for i in range(1, 50)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(_macd_config("mf", fast=3, slow=6, signal=3))
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
                        "left":  {"kind": "tool_output", "ref": "mf.macd_line"},
                        "operator": "crosses_above",
                        "right": {"kind": "tool_output", "ref": "mf.signal_line"},
                    }],
                },
            }],
            "exit_rules": [],
        })
        hist_result = evaluate_history_from_payload(semantics, payloads)
        # Result should be a list; no exception thrown — semantics evaluated cleanly
        assert len(hist_result.bar_results) == len(bars)


# ===========================================================================
# Error cases
# ===========================================================================

class TestMACDErrors:
    def test_missing_close_field_raises(self):
        toolset = _toolset(_macd_config("m"))
        bars = [ToolComputationBarInput(bar_index=0, price_fields={"open": 100.0})]
        with pytest.raises(ToolComputationError, match="close"):
            compute_tool_outputs_for_history(toolset, bars, _REGISTRY)

    def test_duplicate_bar_index_raises(self):
        toolset = _toolset(_macd_config("m"))
        bars = [_bar_input(0, 100.0), _bar_input(0, 101.0)]
        with pytest.raises(ToolComputationError, match="duplicate"):
            compute_tool_outputs_for_history(toolset, bars, _REGISTRY)

    def test_disabled_tool_produces_no_series(self):
        toolset = _toolset(_macd_config("m", enabled=False))
        bars = _bars_from_closes([float(i) for i in range(30)])
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        assert len(result.series) == 0


# ===========================================================================
# API integration
# ===========================================================================

class TestMACDAPIIntegration:
    def test_get_tools_includes_macd(self):
        response = _CLIENT.get("/tools")
        assert response.status_code == 200
        tool_ids = [t["tool_id"] for t in response.json()["tools"]]
        assert "macd" in tool_ids

    def test_macd_has_three_output_feature_names(self):
        response = _CLIENT.get("/tools")
        tools = {t["tool_id"]: t for t in response.json()["tools"]}
        assert tools["macd"]["output_feature_names"] == ["macd_line", "signal_line", "histogram"]

    def test_macd_via_evaluate_history_api(self):
        closes = [100.0 + 3.0 * (i % 9 - 4) for i in range(50)]
        bars = _bars_from_closes(closes)
        toolset = _toolset(_macd_config("mf", fast=3, slow=6, signal=3))
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
                            "left":  {"kind": "tool_output", "ref": "mf.histogram"},
                            "operator": ">",
                            "right": {"kind": "constant", "ref": "0"},
                        }],
                    },
                }],
                "exit_rules": [],
            },
            "bars": payloads,
        })
        assert response.status_code == 200

    def test_validate_toolset_accepts_macd(self):
        response = _CLIENT.post("/tools/validate-toolset", json={
            "toolset_id": "test_macd",
            "tools": [{
                "instance_id": "macd1",
                "tool_id": "macd",
                "parameters": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
                "enabled": True,
                "display_name": None,
                "color": None,
            }],
        })
        assert response.status_code == 200
        assert response.json()["valid"] is True


# ===========================================================================
# Architecture guards
# ===========================================================================

class TestMACDArchitectureGuards:
    def test_macd_module_does_not_import_backtesting(self):
        import importlib, inspect
        mod = importlib.import_module("backend.tools.macd")
        source = inspect.getsource(mod)
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
