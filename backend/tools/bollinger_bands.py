"""
Bollinger Bands tool — Phase 2U.

Provides:
    BOLLINGER_METADATA  — registry metadata for the Bollinger Bands tool
    compute_bollinger   — standalone Bollinger Bands computation over NormalizedOHLCV

The historical computation pipeline entry point is in historical_computation.py
(_compute_bollinger_series), which operates on ToolComputationBarInput and produces
three ToolOutputSeries — the evaluator-compatible output format.

Bollinger Bands formula:
    middle_band = SMA(close, period)
    std_dev     = population standard deviation of close over the same `period` window
    upper_band  = middle_band + multiplier * std_dev
    lower_band  = middle_band - multiplier * std_dev

Population std dev (divisor = period) is used, matching the standard Bollinger definition.

Outputs (three series per instance):
    middle_band — warmup = period - 1  (same as SMA)
    upper_band  — warmup = period - 1
    lower_band  — warmup = period - 1

All three outputs share an identical warmup window; the first valid bar for all is
bar index (period - 1) in the sorted input sequence.

Default configuration: period=20, std_dev=2.0.
"""
from __future__ import annotations

import math

from backend.data.schemas import NormalizedOHLCV
from backend.strategy_registry.models import RuntimeMode
from backend.strategy_runtime.visualization import (
    IndicatorPane,
    IndicatorPoint,
    IndicatorSeries,
    IndicatorSeriesKind,
)
from backend.tools.models import (
    ParameterSpec,
    ToolCategory,
    ToolMetadata,
    ToolStatus,
)

BOLLINGER_METADATA = ToolMetadata(
    tool_id="bollinger_bands",
    name="Bollinger Bands",
    version="1.0.0",
    category=ToolCategory.indicator,
    status=ToolStatus.stable,
    description=(
        "Computes Bollinger Bands using a rolling SMA and population standard deviation. "
        "middle_band = SMA(period); upper_band = middle + multiplier × σ; "
        "lower_band = middle - multiplier × σ. "
        "Warmup = period - 1 bars (first output at bar index period - 1). "
        "Three outputs: middle_band, upper_band, lower_band. Stateless and deterministic."
    ),
    input_data_family="ohlcv",
    output_feature_names=("middle_band", "upper_band", "lower_band"),
    parameters=(
        ParameterSpec(
            name="period",
            description="Rolling window length. Must be >= 2.",
            type_label="int",
            required=True,
            default=20,
            min_value=2,
        ),
        ParameterSpec(
            name="std_dev",
            description="Standard deviation multiplier for band width. Must be > 0.",
            type_label="float",
            required=False,
            default=2.0,
        ),
        ParameterSpec(
            name="name",
            description="Custom label prefix for output series names.",
            type_label="str",
            required=False,
            default=None,
        ),
        ParameterSpec(
            name="color",
            description="Hex color string for the middle band (e.g. '#2196f3').",
            type_label="str",
            required=False,
            default=None,
        ),
    ),
    supported_runtime_modes=frozenset({
        RuntimeMode.RESEARCH,
        RuntimeMode.BACKTESTING,
        RuntimeMode.FORWARD_TESTING,
        RuntimeMode.PAPER_TRADING,
        RuntimeMode.LIVE_TRADING,
    }),
    visualization_capabilities=frozenset(),  # all outputs are price-pane overlays
    min_warmup_bars=1,  # minimum when period=2; actual warmup = period - 1
    stateful=False,     # each bar's output depends only on the last `period` closes
)


def compute_bollinger(
    candles: list[NormalizedOHLCV],
    period: int,
    std_dev: float = 2.0,
    name: str | None = None,
    color: str | None = None,
) -> tuple[IndicatorSeries, IndicatorSeries, IndicatorSeries]:
    """
    Compute Bollinger Bands over close prices of the given candles (visualization path).

    Candles are sorted by timestamp internally. The first (period - 1) bars produce
    no output (warmup). First band values appear at the period-th bar (index period-1).

    Args:
        candles: OHLCV records to compute over.
        period:  Rolling window length. Must be >= 2.
        std_dev: Standard deviation multiplier. Must be > 0.
        name:    Label prefix. Defaults to "BB".
        color:   Optional hex color hint for the middle band.

    Returns:
        Tuple of (middle_band_series, upper_band_series, lower_band_series).

    Raises:
        ValueError: if period < 2 or std_dev <= 0.
    """
    if period < 2:
        raise ValueError(f"period must be >= 2, got {period}")
    if std_dev <= 0:
        raise ValueError(f"std_dev must be > 0, got {std_dev}")

    prefix = name if name else "BB"

    empty_middle = IndicatorSeries(name=f"{prefix} Middle", kind=IndicatorSeriesKind.line, pane=IndicatorPane.price, color=color,     points=[])
    empty_upper  = IndicatorSeries(name=f"{prefix} Upper",  kind=IndicatorSeriesKind.line, pane=IndicatorPane.price, color="#26a69a", points=[])
    empty_lower  = IndicatorSeries(name=f"{prefix} Lower",  kind=IndicatorSeriesKind.line, pane=IndicatorPane.price, color="#ef5350", points=[])

    if not candles:
        return empty_middle, empty_upper, empty_lower

    sorted_candles = sorted(candles, key=lambda c: c.timestamp)
    closes     = [c.close     for c in sorted_candles]
    timestamps = [c.timestamp for c in sorted_candles]

    middle_points: list[IndicatorPoint] = []
    upper_points:  list[IndicatorPoint] = []
    lower_points:  list[IndicatorPoint] = []

    for i in range(len(closes)):
        if i < period - 1:
            continue

        window = closes[i - period + 1 : i + 1]
        middle, upper, lower = _bollinger_values(window, std_dev)

        middle_points.append(IndicatorPoint(timestamp=timestamps[i], value=middle))
        upper_points.append( IndicatorPoint(timestamp=timestamps[i], value=upper))
        lower_points.append( IndicatorPoint(timestamp=timestamps[i], value=lower))

    return (
        IndicatorSeries(name=f"{prefix} Middle", kind=IndicatorSeriesKind.line, pane=IndicatorPane.price, color=color,     points=middle_points),
        IndicatorSeries(name=f"{prefix} Upper",  kind=IndicatorSeriesKind.line, pane=IndicatorPane.price, color="#26a69a", points=upper_points),
        IndicatorSeries(name=f"{prefix} Lower",  kind=IndicatorSeriesKind.line, pane=IndicatorPane.price, color="#ef5350", points=lower_points),
    )


def _bollinger_values(window: list[float], multiplier: float) -> tuple[float, float, float]:
    """
    Compute (middle, upper, lower) for a single fully-populated window.

    Uses population standard deviation (divisor = len(window)), matching the
    standard Bollinger Bands definition.
    """
    n    = len(window)
    mean = sum(window) / n
    variance = sum((x - mean) ** 2 for x in window) / n
    sigma = math.sqrt(variance)
    return mean, mean + multiplier * sigma, mean - multiplier * sigma
