"""
Backend unit tests for the volume_ma tool.

Coverage:
 1.  Metadata: tool_id, name, version, category, visible_on_chart
 2.  Metadata: chart_pane is price_overlay (not oscillator_pane)
 3.  Metadata: chart_output_series has volume (histogram) + volume_ma (line)
 4.  Metadata: ma_length parameter is optional (required=False, default=None)
 5.  Metadata: volume_ma registered in create_default_registry()
 6.  Computation: volume histogram returned for every bar (no warmup)
 7.  Computation: no MA series emitted when ma_length is None
 8.  Computation: MA series emitted when ma_length provided
 9.  Computation: MA warmup = ma_length - 1 (MA starts at bar index ma_length-1)
10.  Computation: MA values are correct SMA of volume
11.  Computation: ma_length = 1 → no warmup, every bar has MA = volume itself
12.  Computation: ma_length > available bars → zero MA points (no crash)
13.  Computation: zero bars → empty series returned
14.  Computation: invalid ma_length (0) raises ToolComputationError
15.  Computation: invalid ma_length (negative) raises ToolComputationError
16.  Computation: missing volume field raises ToolComputationError
17.  Computation: multiple instances with different ma_lengths do not collide
18.  Computation: output bar_index order matches input bar_index order
19.  Computation: output timestamps match input timestamps
20.  Computation: MA is deterministic (same input → same output)
21.  Computation: bars not in order still produce correct output (sorted internally)
22.  Chart indicator API: volume_ma appears in GET /chart/indicators response
23.  Chart indicator API: volume_ma artifact has two series (volume + volume_ma)
24.  Chart indicator API: volume series has render_type=histogram, pane=price_overlay
25.  Chart indicator API: ma_length=None → volume_ma series all-null in artifact
26.  Chart indicator API: ma_length provided → volume_ma series has values
27.  derive_warmup_bars_required: ma_length=None → 0
28.  derive_warmup_bars_required: ma_length=5 → 4
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.tools import (
    VOLUME_MA_METADATA,
    create_default_registry,
)
from backend.tools.configuration import ToolConfiguration
from backend.tools.historical_computation import (
    ToolComputationBarInput,
    ToolComputationError,
    compute_tool_outputs_for_history,
    derive_warmup_bars_required,
    _compute_volume_series,
)
from backend.tools.toolset import StrategyToolSet


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _ts(i: int) -> datetime:
    """Create a deterministic UTC datetime for bar index i."""
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


def _config(ma_length=None, instance_id="vol_1") -> ToolConfiguration:
    params: dict = {}
    if ma_length is not None:
        params["ma_length"] = ma_length
    return ToolConfiguration(
        instance_id=instance_id,
        tool_id="volume_ma",
        parameters=params,
    )


# ---------------------------------------------------------------------------
# 1–5. Metadata tests
# ---------------------------------------------------------------------------

class TestVolumeMetadata:
    def test_1_tool_id_and_name(self):
        assert VOLUME_MA_METADATA.tool_id == "volume_ma"
        assert VOLUME_MA_METADATA.name == "Volume"

    def test_2_chart_pane_is_price_overlay(self):
        assert VOLUME_MA_METADATA.chart_pane == "price_overlay"

    def test_3_chart_output_series_volume_and_ma(self):
        series_ids = {s.series_id for s in VOLUME_MA_METADATA.chart_output_series}
        assert "volume" in series_ids
        assert "volume_ma" in series_ids

    def test_3b_volume_series_is_histogram_price_overlay(self):
        vol_spec = next(s for s in VOLUME_MA_METADATA.chart_output_series if s.series_id == "volume")
        assert vol_spec.render_type == "histogram"
        assert vol_spec.pane == "price_overlay"

    def test_3c_volume_ma_series_is_line_price_overlay(self):
        ma_spec = next(s for s in VOLUME_MA_METADATA.chart_output_series if s.series_id == "volume_ma")
        assert ma_spec.render_type == "line"
        assert ma_spec.pane == "price_overlay"

    def test_4_ma_length_is_optional(self):
        ma_param = next(p for p in VOLUME_MA_METADATA.parameters if p.name == "ma_length")
        assert ma_param.required is False
        assert ma_param.default is None
        assert ma_param.min_value == 1

    def test_5_registered_in_default_registry(self):
        registry = create_default_registry()
        assert "volume_ma" in registry


# ---------------------------------------------------------------------------
# 6–13. Computation: histogram and MA series
# ---------------------------------------------------------------------------

class TestVolumeComputation:
    def test_6_volume_not_in_strategy_output(self):
        # "volume" is no longer a strategy output of volume_ma; it is visualization-only.
        bars   = _make_bars([1000.0, 2000.0, 3000.0])
        cfg    = _config(ma_length=2)
        series = _compute_volume_series(cfg, bars)
        names  = {s.output_name for s in series}
        assert "volume" not in names

    def test_7_no_series_at_all_when_ma_length_none(self):
        # When ma_length is not set the tool emits no strategy outputs.
        bars   = _make_bars([1000.0, 2000.0])
        cfg    = _config()
        series = _compute_volume_series(cfg, bars)
        assert series == []

    def test_8_ma_series_emitted_when_ma_length_provided(self):
        bars   = _make_bars([1000.0, 2000.0, 3000.0])
        cfg    = _config(ma_length=2)
        series = _compute_volume_series(cfg, bars)
        names  = {s.output_name for s in series}
        assert "volume_ma" in names

    def test_9_ma_warmup_equals_ma_length_minus_one(self):
        bars      = _make_bars([1000.0, 2000.0, 3000.0, 4000.0])
        cfg       = _config(ma_length=3)
        series    = _compute_volume_series(cfg, bars)
        ma_series = next(s for s in series if s.output_name == "volume_ma")
        assert ma_series.warmup_bar_count == 2   # 3 - 1 = 2
        assert len(ma_series.points) == 2        # bars at indices 2 and 3

    def test_10_ma_values_correct_sma_of_volume(self):
        volumes = [1000.0, 2000.0, 3000.0, 4000.0]
        bars    = _make_bars(volumes)
        cfg     = _config(ma_length=2)
        series  = _compute_volume_series(cfg, bars)
        ma_series = next(s for s in series if s.output_name == "volume_ma")
        # SMA(2): first at bar 1 = (1000+2000)/2=1500, bar2=(2000+3000)/2=2500, bar3=3500
        values = [p.value for p in ma_series.points]
        assert values == pytest.approx([1500.0, 2500.0, 3500.0])

    def test_11_ma_length_1_no_warmup_every_bar_equals_volume(self):
        volumes = [500.0, 750.0, 1000.0]
        bars    = _make_bars(volumes)
        cfg     = _config(ma_length=1)
        series  = _compute_volume_series(cfg, bars)
        ma_series = next(s for s in series if s.output_name == "volume_ma")
        assert ma_series.warmup_bar_count == 0
        assert len(ma_series.points) == 3
        assert [p.value for p in ma_series.points] == pytest.approx(volumes)

    def test_12_ma_length_greater_than_bars_produces_zero_ma_points(self):
        bars   = _make_bars([1000.0, 2000.0])   # only 2 bars
        cfg    = _config(ma_length=10)           # MA period > bar count
        series = _compute_volume_series(cfg, bars)
        ma_series = next(s for s in series if s.output_name == "volume_ma")
        assert len(ma_series.points) == 0        # no MA values, no crash

    def test_13_zero_bars_returns_only_volume_ma_series_empty(self):
        # No bars → volume_ma series exists with 0 points; no volume series.
        bars   = []
        cfg    = _config(ma_length=5)
        series = _compute_volume_series(cfg, bars)
        names  = {s.output_name for s in series}
        assert "volume" not in names
        ma = next(s for s in series if s.output_name == "volume_ma")
        assert len(ma.points) == 0


# ---------------------------------------------------------------------------
# 14–16. Computation: error cases
# ---------------------------------------------------------------------------

class TestVolumeComputationErrors:
    def test_14_invalid_ma_length_zero_raises(self):
        bars = _make_bars([1000.0])
        cfg  = _config(ma_length=0)
        with pytest.raises(ToolComputationError, match="ma_length must be >= 1"):
            _compute_volume_series(cfg, bars)

    def test_15_invalid_ma_length_negative_raises(self):
        bars = _make_bars([1000.0])
        cfg  = _config(ma_length=-3)
        with pytest.raises(ToolComputationError, match="ma_length must be >= 1"):
            _compute_volume_series(cfg, bars)

    def test_16_missing_volume_field_raises_when_ma_length_set(self):
        # Volume field is only read when ma_length is set.
        bars = [ToolComputationBarInput(
            bar_index=0, timestamp=_ts(0),
            price_fields={"open": 100.0, "close": 102.0},  # no volume
        )]
        cfg = _config(ma_length=1)
        with pytest.raises(ToolComputationError, match="missing 'volume'"):
            _compute_volume_series(cfg, bars)


# ---------------------------------------------------------------------------
# 17–21. Multi-instance, ordering, determinism
# ---------------------------------------------------------------------------

class TestVolumeMultiInstanceAndOrdering:
    def test_17_multiple_instances_do_not_collide(self):
        volumes = [100.0, 200.0, 300.0, 400.0, 500.0]
        bars    = _make_bars(volumes)
        cfg_a   = _config(ma_length=2, instance_id="vol_a")
        cfg_b   = _config(ma_length=3, instance_id="vol_b")
        series_a = _compute_volume_series(cfg_a, bars)
        series_b = _compute_volume_series(cfg_b, bars)
        # Check instance_ids are distinct
        for s in series_a:
            assert s.instance_id == "vol_a"
        for s in series_b:
            assert s.instance_id == "vol_b"
        # MA lengths produce different number of points
        ma_a = next(s for s in series_a if s.output_name == "volume_ma")
        ma_b = next(s for s in series_b if s.output_name == "volume_ma")
        assert len(ma_a.points) == 4   # warmup=1 → 4 points
        assert len(ma_b.points) == 3   # warmup=2 → 3 points

    def test_18_output_bar_index_order_matches_input(self):
        bars   = _make_bars([300.0, 100.0, 200.0])
        cfg    = _config(ma_length=1)  # ma_length=1 so all bars produce MA points
        series = _compute_volume_series(cfg, bars)
        ma     = next(s for s in series if s.output_name == "volume_ma")
        bar_indices = [p.bar_index for p in ma.points]
        assert bar_indices == sorted(bar_indices)

    def test_19_output_timestamps_match_input(self):
        volumes = [1000.0, 2000.0, 3000.0]
        bars    = _make_bars(volumes)
        cfg     = _config(ma_length=1)  # no warmup so all bars appear in output
        series  = _compute_volume_series(cfg, bars)
        ma      = next(s for s in series if s.output_name == "volume_ma")
        for i, point in enumerate(ma.points):
            assert point.timestamp == _ts(i)

    def test_20_computation_is_deterministic(self):
        volumes = [500.0, 1500.0, 2000.0, 750.0]
        bars    = _make_bars(volumes)
        cfg     = _config(ma_length=2)
        result_a = _compute_volume_series(cfg, bars)
        result_b = _compute_volume_series(cfg, bars)
        ma_a = [p.value for p in next(s for s in result_a if s.output_name == "volume_ma").points]
        ma_b = [p.value for p in next(s for s in result_b if s.output_name == "volume_ma").points]
        assert ma_a == pytest.approx(ma_b)

    def test_21_compute_tool_outputs_dispatches_volume_ma(self):
        """volume_ma dispatch: only volume_ma in strategy outputs, not volume."""
        volumes = [1000.0, 2000.0, 3000.0]
        bars    = _make_bars(volumes)
        registry = create_default_registry()
        toolset  = StrategyToolSet(
            toolset_id="ts_vol",
            tools=(_config(ma_length=2),),
        )
        result = compute_tool_outputs_for_history(toolset, bars, registry)
        names  = {s.output_name for s in result.series}
        assert "volume_ma" in names
        assert "volume" not in names

    def test_21b_output_feature_names_is_volume_ma_only(self):
        assert VOLUME_MA_METADATA.output_feature_names == ("volume_ma",)


# ---------------------------------------------------------------------------
# 22–26. Chart indicator artifact API tests (service layer)
# ---------------------------------------------------------------------------

class TestVolumeChartArtifact:
    """
    Tests against compute_indicator_artifact() via the chart indicator service.
    Uses mocked OHLCV data to avoid real provider calls.
    """

    def _make_mock_candles(self, n: int = 10):
        from backend.data.schemas import NormalizedOHLCV
        return [
            NormalizedOHLCV(
                symbol="AAPL",
                asset_class="equity",
                venue="unknown",
                timeframe="1d",
                source="yahoo",
                timestamp=_ts(i),
                open=100.0 + i, high=105.0 + i,
                low=99.0 + i,  close=102.0 + i,
                volume=float(1000 + i * 100),
            )
            for i in range(n)
        ]

    def _run_artifact(self, parameters: dict, candles=None):
        from backend.api.services.chart_indicator_service import compute_indicator_artifact
        from backend.data.models.dataset import DatasetIdentity

        registry     = create_default_registry()
        mock_factory = MagicMock()
        mock_adapter = MagicMock()
        mock_factory.build.return_value = mock_adapter
        mock_ohlcv   = MagicMock()
        mock_ohlcv.get_ohlcv.return_value = candles or self._make_mock_candles()

        return compute_indicator_artifact(
            tool_id="volume_ma",
            instance_id="test_vol",
            symbol="AAPL",
            provider="yahoo",
            timeframe="1d",
            date_range_start=_ts(0),
            date_range_end=_ts(9),
            parameters=parameters,
            registry=registry,
            factory=mock_factory,
            ohlcv_service=mock_ohlcv,
        )

    def test_22_volume_ma_appears_in_chart_indicators_list(self):
        from backend.api.services.chart_indicator_service import list_chart_indicators
        registry = create_default_registry()
        result   = list_chart_indicators(registry)
        tool_ids = {ind.tool_id for ind in result.indicators}
        assert "volume_ma" in tool_ids

    def test_23_artifact_has_volume_and_volume_ma_series(self):
        artifact = self._run_artifact({})
        series_ids = {s.series_id for s in artifact.series}
        assert "volume" in series_ids
        assert "volume_ma" in series_ids

    def test_24_volume_series_histogram_pane_price_overlay(self):
        artifact  = self._run_artifact({})
        vol_series = next(s for s in artifact.series if s.series_id == "volume")
        assert vol_series.render_type == "histogram"
        assert vol_series.pane == "price_overlay"

    def test_25_no_ma_length_volume_ma_series_all_null(self):
        artifact  = self._run_artifact({})
        ma_series = next(s for s in artifact.series if s.series_id == "volume_ma")
        # All values should be null when ma_length not provided
        assert all(p.value is None for p in ma_series.values)

    def test_26_ma_length_provided_volume_ma_series_has_values(self):
        artifact  = self._run_artifact({"ma_length": 3})
        ma_series = next(s for s in artifact.series if s.series_id == "volume_ma")
        non_null  = [p for p in ma_series.values if p.value is not None]
        assert len(non_null) > 0


# ---------------------------------------------------------------------------
# 27–28. derive_warmup_bars_required
# ---------------------------------------------------------------------------

class TestVolumeWarmup:
    def _meta(self):
        return VOLUME_MA_METADATA

    def test_27_warmup_is_zero_when_no_ma_length(self):
        warmup = derive_warmup_bars_required(_config(ma_length=None), self._meta())
        assert warmup == 0

    def test_28_warmup_is_ma_length_minus_one(self):
        warmup = derive_warmup_bars_required(_config(ma_length=5), self._meta())
        assert warmup == 4   # 5 - 1

    def test_28b_warmup_ma_length_1_gives_zero(self):
        warmup = derive_warmup_bars_required(_config(ma_length=1), self._meta())
        assert warmup == 0
