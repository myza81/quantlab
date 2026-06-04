"""
Exponential Moving Average (EMA) tool — Phase 2R.1.

Provides:
    EMA_METADATA — registry metadata for the EMA tool
    compute_ema  — standalone EMA computation over NormalizedOHLCV (visualization path)

The historical computation pipeline entry point is in historical_computation.py
(_compute_ema_series), which operates on ToolComputationBarInput and produces
ToolOutputSeries — the evaluator-compatible output format.

EMA formula:
    alpha = 2 / (period + 1)
    seed  = SMA(close[0..period-1])          # first valid EMA value
    EMA_t = alpha × close_t + (1 − alpha) × EMA_{t-1}

Warmup: first (period - 1) bars produce no output.
State:  recursive (depends on previous EMA value) but purely local to each
        computation pass — no shared mutable state between instances.
"""
from __future__ import annotations

from backend.data.schemas import NormalizedOHLCV
from backend.strategy_registry.models import RuntimeMode
from backend.strategy_runtime.visualization import (
    IndicatorPane,
    IndicatorPoint,
    IndicatorSeries,
    IndicatorSeriesKind,
)
from backend.tools.models import (
    ChartSeriesSpec,
    ParameterSpec,
    ToolCategory,
    ToolMetadata,
    ToolStatus,
    VisualizationCapability,
)

EMA_METADATA = ToolMetadata(
    tool_id="ema",
    name="Exponential Moving Average",
    version="1.0.0",
    category=ToolCategory.indicator,
    status=ToolStatus.stable,
    description=(
        "Computes an exponential moving average over close prices using a "
        "recursive multiplier alpha = 2 / (period + 1). "
        "Seed = SMA of the first `period` bars. "
        "Warmup = period - 1 bars. Stateful per computation pass; globally deterministic."
    ),
    input_data_family="ohlcv",
    output_feature_names=("ema",),
    parameters=(
        ParameterSpec(
            name="period",
            description="EMA window length. Must be >= 1.",
            type_label="int",
            required=True,
            min_value=1,
        ),
        ParameterSpec(
            name="source",
            description="Price field to compute EMA over. Currently only 'close' is supported.",
            type_label="str",
            required=False,
            default="close",
        ),
        ParameterSpec(
            name="name",
            description="Custom label for the output indicator series.",
            type_label="str",
            required=False,
            default=None,
        ),
        ParameterSpec(
            name="color",
            description="Hex color string for chart rendering (e.g. '#ff6b00').",
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
    visualization_capabilities=frozenset({
        VisualizationCapability.produces_line_overlay,
    }),
    min_warmup_bars=0,  # minimum when period=1; actual warmup = period - 1
    stateful=True,      # recursive: each bar depends on the previous EMA value
    visible_on_chart=True,
    chart_pane="price_overlay",
    chart_render_type="line",
    chart_series_kind="continuous",
    chart_category="Trend",
    chart_subcategory="Moving Averages",
    chart_search_keywords=(
        "exponential moving average", "ema", "moving average", "ma", "weighted",
    ),
    chart_display_order=20,
    chart_editable_parameters=("period", "source"),
    chart_output_series=(
        ChartSeriesSpec(
            series_id="ema",
            label="EMA",
            pane="price_overlay",
            render_type="line",
            default_color="#3b82f6",
        ),
    ),
)


def compute_ema(
    candles: list[NormalizedOHLCV],
    period: int,
    name: str | None = None,
    color: str | None = None,
) -> IndicatorSeries:
    """
    Compute Exponential Moving Average over the close prices of the given candles.

    Candles are sorted by timestamp internally; the caller need not pre-sort.
    The first valid EMA value is seeded from the SMA of the first `period` bars.
    Bars within the warmup window (index < period - 1) produce no output point.
    Output is deterministic: identical inputs always produce identical results.

    Args:
        candles: OHLCV records to compute over.
        period:  EMA window size. Must be >= 1.
        name:    Label for the output series. Defaults to "EMA(<period>)".
        color:   Optional hex color hint for visualization.

    Returns:
        IndicatorSeries with one IndicatorPoint per bar at or beyond warmup.

    Raises:
        ValueError: if period < 1.
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")

    series_name = name if name else f"EMA({period})"

    if not candles:
        return IndicatorSeries(
            name=series_name,
            kind=IndicatorSeriesKind.line,
            pane=IndicatorPane.price,
            color=color,
            points=[],
        )

    sorted_candles = sorted(candles, key=lambda c: c.timestamp)
    closes = [c.close for c in sorted_candles]
    timestamps = [c.timestamp for c in sorted_candles]

    alpha = 2.0 / (period + 1)
    warmup = period - 1
    points: list[IndicatorPoint] = []
    ema_value: float | None = None

    for i in range(len(closes)):
        if i < warmup:
            continue

        if ema_value is None:
            # Seed: SMA of first `period` bars
            ema_value = sum(closes[:period]) / period
        else:
            ema_value = alpha * closes[i] + (1.0 - alpha) * ema_value

        points.append(IndicatorPoint(timestamp=timestamps[i], value=ema_value))

    return IndicatorSeries(
        name=series_name,
        kind=IndicatorSeriesKind.line,
        pane=IndicatorPane.price,
        color=color,
        points=points,
    )
