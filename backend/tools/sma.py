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
    VisualizationCapability,
)

SMA_METADATA = ToolMetadata(
    tool_id="sma",
    name="Simple Moving Average",
    version="1.0.0",
    category=ToolCategory.indicator,
    status=ToolStatus.stable,
    description=(
        "Computes a simple arithmetic moving average over close prices. "
        "Actual warmup = period - 1 bars. Stateless and deterministic."
    ),
    input_data_family="ohlcv",
    output_feature_names=("sma",),
    parameters=(
        ParameterSpec(
            name="period",
            description="Number of bars in the averaging window. Must be >= 1.",
            type_label="int",
            required=True,
            min_value=1,
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
            description="Hex color string for chart rendering (e.g. '#2196f3').",
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
    stateful=False,
)


def compute_sma(
    candles: list[NormalizedOHLCV],
    period: int,
    name: str | None = None,
    color: str | None = None,
) -> IndicatorSeries:
    """
    Compute Simple Moving Average over the close prices of the given candles.

    Candles are sorted by timestamp internally; the caller need not pre-sort.
    Bars within the warmup window (index < period - 1) produce no output point.
    Output is deterministic: identical inputs always produce identical results.

    Args:
        candles: OHLCV records to compute over.
        period: Averaging window size. Must be >= 1.
        name: Label for the output series. Defaults to "SMA(<period>)".
        color: Optional hex color hint for visualization.

    Returns:
        IndicatorSeries with one IndicatorPoint per bar at or beyond warmup.
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")

    series_name = name if name else f"SMA({period})"

    if not candles:
        return IndicatorSeries(
            name=series_name,
            kind=IndicatorSeriesKind.line,
            pane=IndicatorPane.price,
            color=color,
            points=[],
        )

    # Sort by timestamp to guarantee bar ordering regardless of input order
    sorted_candles = sorted(candles, key=lambda c: c.timestamp)

    closes = [c.close for c in sorted_candles]
    timestamps = [c.timestamp for c in sorted_candles]

    points: list[IndicatorPoint] = []
    for i in range(len(closes)):
        if i < period - 1:
            continue
        window_sum = sum(closes[i - period + 1 : i + 1])
        points.append(
            IndicatorPoint(timestamp=timestamps[i], value=window_sum / period)
        )

    return IndicatorSeries(
        name=series_name,
        kind=IndicatorSeriesKind.line,
        pane=IndicatorPane.price,
        color=color,
        points=points,
    )
