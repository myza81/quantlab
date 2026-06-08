"""
Backend unit tests for the raw Volume tool (tool_id="volume").

Coverage:
 1.  Metadata: VOLUME_METADATA exists with tool_id="volume"
 2.  Metadata: no editable parameters (parameters tuple is empty)
 3.  Metadata: min_warmup_bars == 0
 4.  Metadata: output_feature_names contains exactly one entry: "volume"
 5.  Computation: emits raw volume value for every bar
 6.  Computation: output bar_index order and timestamps match input
 7.  Computation: missing volume field raises ToolComputationError
 8.  Computation: multiple instances do not collide
 9.  Computation: volume and volume_ma can be computed together in one toolset
10.  Computation: derive_warmup_bars_required returns 0 for tool_id="volume"
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.tools import (
    VOLUME_METADATA,
    create_default_registry,
)
from backend.tools.configuration import ToolConfiguration
from backend.tools.historical_computation import (
    ToolComputationBarInput,
    ToolComputationError,
    _compute_raw_volume_series,
    compute_tool_outputs_for_history,
    derive_warmup_bars_required,
)
from backend.tools.toolset import StrategyToolSet


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _ts(i: int) -> datetime:
    return datetime(2024, 1, i + 1, tzinfo=timezone.utc)


def _make_bars(
    volumes: list[float],
    start_index: int = 0,
) -> list[ToolComputationBarInput]:
    return [
        ToolComputationBarInput(
            bar_index=start_index + i,
            timestamp=_ts(start_index + i),
            price_fields={
                "open":   100.0 + i,
                "high":   105.0 + i,
                "low":     99.0 + i,
                "close":  102.0 + i,
                "volume": float(vol),
            },
        )
        for i, vol in enumerate(volumes)
    ]


def _config(instance_id: str = "vol_raw") -> ToolConfiguration:
    return ToolConfiguration(
        instance_id=instance_id,
        tool_id="volume",
        parameters={},
    )


def _config_volume_ma(ma_length: int, instance_id: str = "vol_ma") -> ToolConfiguration:
    return ToolConfiguration(
        instance_id=instance_id,
        tool_id="volume_ma",
        parameters={"ma_length": ma_length},
    )


# ---------------------------------------------------------------------------
# 1–4. Metadata tests
# ---------------------------------------------------------------------------

class TestVolumeRawMetadata:
    def test_1_metadata_exists_with_correct_tool_id(self):
        assert VOLUME_METADATA.tool_id == "volume"

    def test_2_no_editable_parameters(self):
        assert VOLUME_METADATA.parameters == ()
        assert VOLUME_METADATA.chart_editable_parameters == ()

    def test_3_warmup_is_zero(self):
        assert VOLUME_METADATA.min_warmup_bars == 0

    def test_4_single_output_named_volume(self):
        assert VOLUME_METADATA.output_feature_names == ("volume",)

    def test_registered_in_default_registry(self):
        registry = create_default_registry()
        assert "volume" in registry

    def test_chart_pane_is_price_overlay(self):
        assert VOLUME_METADATA.chart_pane == "price_overlay"

    def test_chart_output_series_is_histogram(self):
        assert len(VOLUME_METADATA.chart_output_series) == 1
        spec = VOLUME_METADATA.chart_output_series[0]
        assert spec.series_id == "volume"
        assert spec.render_type == "histogram"
        assert spec.pane == "price_overlay"


# ---------------------------------------------------------------------------
# 5–6. Computation: values, order, timestamps
# ---------------------------------------------------------------------------

class TestVolumeRawComputation:
    def test_5_emits_raw_volume_for_every_bar(self):
        volumes = [1000.0, 2500.0, 750.0, 3300.0]
        bars = _make_bars(volumes)
        series = _compute_raw_volume_series(_config(), bars)
        assert len(series) == 1
        vol_series = series[0]
        assert vol_series.output_name == "volume"
        assert vol_series.warmup_bar_count == 0
        assert len(vol_series.points) == len(volumes)
        emitted = [p.value for p in vol_series.points]
        assert emitted == pytest.approx(volumes)

    def test_6a_output_bar_index_order_matches_input(self):
        bars = _make_bars([500.0, 1500.0, 800.0])
        series = _compute_raw_volume_series(_config(), bars)
        indices = [p.bar_index for p in series[0].points]
        assert indices == sorted(indices)

    def test_6b_output_timestamps_match_input(self):
        volumes = [100.0, 200.0, 300.0]
        bars = _make_bars(volumes)
        series = _compute_raw_volume_series(_config(), bars)
        for i, point in enumerate(series[0].points):
            assert point.timestamp == _ts(i)

    def test_6c_non_sequential_input_bars_sorted_by_bar_index(self):
        # Bars provided out of order — dispatcher sorts them; we verify output is in order
        registry = create_default_registry()
        shuffled = [
            ToolComputationBarInput(
                bar_index=2, timestamp=_ts(2),
                price_fields={"open":100.0,"high":105.0,"low":99.0,"close":102.0,"volume":300.0},
            ),
            ToolComputationBarInput(
                bar_index=0, timestamp=_ts(0),
                price_fields={"open":100.0,"high":105.0,"low":99.0,"close":102.0,"volume":100.0},
            ),
            ToolComputationBarInput(
                bar_index=1, timestamp=_ts(1),
                price_fields={"open":100.0,"high":105.0,"low":99.0,"close":102.0,"volume":200.0},
            ),
        ]
        toolset = StrategyToolSet(toolset_id="ts_sort", tools=(_config(),))
        result = compute_tool_outputs_for_history(toolset, shuffled, registry)
        vol_series = next(s for s in result.series if s.output_name == "volume")
        indices = [p.bar_index for p in vol_series.points]
        values  = [p.value    for p in vol_series.points]
        assert indices == [0, 1, 2]
        assert values  == pytest.approx([100.0, 200.0, 300.0])

    def test_5b_zero_bars_returns_empty_series(self):
        series = _compute_raw_volume_series(_config(), [])
        assert len(series) == 1
        assert len(series[0].points) == 0
        assert series[0].warmup_bar_count == 0

    def test_computation_is_deterministic(self):
        volumes = [400.0, 1200.0, 800.0]
        bars = _make_bars(volumes)
        result_a = _compute_raw_volume_series(_config(), bars)
        result_b = _compute_raw_volume_series(_config(), bars)
        vals_a = [p.value for p in result_a[0].points]
        vals_b = [p.value for p in result_b[0].points]
        assert vals_a == pytest.approx(vals_b)


# ---------------------------------------------------------------------------
# 7. Missing volume field raises ToolComputationError
# ---------------------------------------------------------------------------

class TestVolumeRawErrors:
    def test_7_missing_volume_field_raises(self):
        bars = [ToolComputationBarInput(
            bar_index=0,
            timestamp=_ts(0),
            price_fields={"open": 100.0, "close": 102.0},  # no volume
        )]
        with pytest.raises(ToolComputationError, match="missing 'volume'"):
            _compute_raw_volume_series(_config(), bars)

    def test_7b_missing_volume_on_later_bar_raises(self):
        bars = [
            ToolComputationBarInput(
                bar_index=0, timestamp=_ts(0),
                price_fields={"open":100.0,"high":105.0,"low":99.0,"close":102.0,"volume":1000.0},
            ),
            ToolComputationBarInput(
                bar_index=1, timestamp=_ts(1),
                price_fields={"open":100.0,"high":105.0,"low":99.0,"close":102.0},  # no volume
            ),
        ]
        with pytest.raises(ToolComputationError, match="missing 'volume'"):
            _compute_raw_volume_series(_config(), bars)


# ---------------------------------------------------------------------------
# 8. Multiple instances do not collide
# ---------------------------------------------------------------------------

class TestVolumeRawMultiInstance:
    def test_8_multiple_instances_have_distinct_instance_ids(self):
        volumes = [100.0, 200.0, 300.0]
        bars = _make_bars(volumes)
        cfg_a = _config(instance_id="vol_a")
        cfg_b = _config(instance_id="vol_b")
        series_a = _compute_raw_volume_series(cfg_a, bars)
        series_b = _compute_raw_volume_series(cfg_b, bars)
        assert series_a[0].instance_id == "vol_a"
        assert series_b[0].instance_id == "vol_b"
        # Values are identical (same bars), but metadata is distinct
        assert [p.value for p in series_a[0].points] == pytest.approx(
            [p.value for p in series_b[0].points]
        )

    def test_8b_build_bar_tool_outputs_separates_by_output_ref(self):
        from backend.tools.historical_computation import build_bar_tool_outputs
        from backend.tools.computation_models import ToolComputationResult, ToolOutputSeries, ToolOutputPoint
        # Two volume instances: refs are "vol_a.volume" and "vol_b.volume"
        point = ToolOutputPoint(bar_index=0, timestamp=_ts(0), value=500.0)
        series_a = ToolOutputSeries(
            instance_id="vol_a", tool_id="volume",
            output_name="volume", warmup_bar_count=0, points=(point,),
        )
        series_b = ToolOutputSeries(
            instance_id="vol_b", tool_id="volume",
            output_name="volume", warmup_bar_count=0, points=(point,),
        )
        result = ToolComputationResult(
            toolset_id="ts_test", total_bars=1,
            series=(series_a, series_b),
        )
        bar_outputs = build_bar_tool_outputs(result)
        assert "vol_a.volume" in bar_outputs[0]
        assert "vol_b.volume" in bar_outputs[0]


# ---------------------------------------------------------------------------
# 9. volume and volume_ma can coexist in the same toolset
# ---------------------------------------------------------------------------

class TestVolumeAndVolumeMaTogether:
    def test_9_both_tools_compute_in_same_toolset(self):
        volumes = [1000.0, 2000.0, 3000.0, 4000.0, 5000.0]
        bars = _make_bars(volumes)
        registry = create_default_registry()
        toolset = StrategyToolSet(
            toolset_id="ts_combo",
            tools=(
                _config(instance_id="raw_vol"),
                _config_volume_ma(ma_length=3, instance_id="vol_ma"),
            ),
        )
        result = compute_tool_outputs_for_history(toolset, bars, registry)
        output_refs = {f"{s.instance_id}.{s.output_name}" for s in result.series}
        assert "raw_vol.volume"   in output_refs
        assert "vol_ma.volume_ma" in output_refs
        # vol_ma.volume is no longer a strategy output of volume_ma (visualization-only)
        assert "vol_ma.volume" not in output_refs

    def test_9b_build_bar_outputs_contains_both_refs(self):
        from backend.tools.historical_computation import build_bar_tool_outputs
        volumes = [1000.0, 2000.0, 3000.0]
        bars = _make_bars(volumes)
        registry = create_default_registry()
        toolset = StrategyToolSet(
            toolset_id="ts_bar",
            tools=(
                _config(instance_id="raw_vol"),
                _config_volume_ma(ma_length=2, instance_id="vol_ma"),
            ),
        )
        result = compute_tool_outputs_for_history(toolset, bars, registry)
        bar_outputs = build_bar_tool_outputs(result)

        # raw_vol.volume is available from bar 0 (no warmup)
        assert "raw_vol.volume" in bar_outputs[0]
        assert bar_outputs[0]["raw_vol.volume"] == pytest.approx(1000.0)

        # vol_ma.volume_ma is available from bar 1 (warmup = ma_length - 1 = 1)
        assert "vol_ma.volume_ma" in bar_outputs[1]
        assert bar_outputs[1]["vol_ma.volume_ma"] == pytest.approx(1500.0)  # (1000+2000)/2

    def test_9c_rule_condition_refs_both_outputs(self):
        """Simulate the kind of operand refs a strategy rule would use."""
        from backend.tools.historical_computation import build_bar_tool_outputs
        volumes = [2000.0, 3000.0, 1500.0]
        bars = _make_bars(volumes)
        registry = create_default_registry()
        toolset = StrategyToolSet(
            toolset_id="ts_rule",
            tools=(
                _config(instance_id="raw_vol"),
                _config_volume_ma(ma_length=2, instance_id="vol_ma"),
            ),
        )
        result = compute_tool_outputs_for_history(toolset, bars, registry)
        bar_outputs = build_bar_tool_outputs(result)

        # At bar 1: raw_vol.volume = 3000, vol_ma.volume_ma = (2000+3000)/2 = 2500
        # Condition "volume > volume_ma" → 3000 > 2500 → True
        raw_vol_bar1 = bar_outputs[1]["raw_vol.volume"]
        ma_vol_bar1  = bar_outputs[1]["vol_ma.volume_ma"]
        assert raw_vol_bar1 > ma_vol_bar1

        # At bar 2: raw_vol.volume = 1500, vol_ma.volume_ma = (3000+1500)/2 = 2250
        # Condition "volume > volume_ma" → 1500 > 2250 → False
        raw_vol_bar2 = bar_outputs[2]["raw_vol.volume"]
        ma_vol_bar2  = bar_outputs[2]["vol_ma.volume_ma"]
        assert raw_vol_bar2 < ma_vol_bar2


# ---------------------------------------------------------------------------
# 10. derive_warmup_bars_required returns 0 for "volume"
# ---------------------------------------------------------------------------

class TestVolumeRawWarmup:
    def test_10_derive_warmup_returns_zero(self):
        warmup = derive_warmup_bars_required(_config(), VOLUME_METADATA)
        assert warmup == 0

    def test_10b_dispatch_via_compute_tool_outputs_produces_all_bars(self):
        """Warmup=0 means every bar appears in the output."""
        volumes = [100.0, 200.0, 300.0]
        bars = _make_bars(volumes)
        registry = create_default_registry()
        toolset = StrategyToolSet(toolset_id="ts_warmup", tools=(_config(),))
        result = compute_tool_outputs_for_history(toolset, bars, registry)
        vol_series = next(s for s in result.series if s.output_name == "volume")
        assert len(vol_series.points) == len(volumes)
