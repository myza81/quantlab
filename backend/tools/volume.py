"""
Volume tools — raw Volume and Volume Moving Average.

Two separate tools are defined here:

    volume     — raw per-bar volume; no parameters; warmup = 0.
                 Source data exposure, not a derived feature.
                 Strategy output: "volume".

    volume_ma  — derived simple moving average of volume.
                 Strategy output: "volume_ma" only.
                 Chart visualization also includes a volume histogram (raw bars
                 for visual context), but raw volume is NOT a declared strategy
                 output of this tool.

Strategy output contract vs. visualization contract:
    These are intentionally different for volume_ma.

    Strategy output (output_feature_names):   ["volume_ma"]
    Chart visualization (chart_output_series): ["volume" histogram, "volume_ma" line]

    The histogram is rendered from raw bar data by the chart artifact service;
    it is not computed by _compute_volume_series and is not accessible in
    strategy rule evaluation.

Architecture boundary:
    No imports from strategy_runtime, execution, forward_testing, backtesting,
    api, or frontend layers.  Stays within tools/ boundary.
"""
from backend.strategy_registry.models import RuntimeMode
from backend.tools.models import (
    ChartSeriesSpec,
    ParameterSpec,
    ToolCategory,
    ToolMetadata,
    ToolStatus,
    VisualizationCapability,
)

VOLUME_METADATA = ToolMetadata(
    tool_id="volume",
    name="Volume",
    short_name="Volume",
    version="1.0.0",
    category=ToolCategory.indicator,
    status=ToolStatus.stable,
    description=(
        "Raw per-bar volume from OHLCV data.  "
        "Emits the bar's volume unchanged — no smoothing, no derived calculation.  "
        "Use alongside Volume MA (volume_ma) to build volume-based conditions "
        "such as volume > volume_ma."
    ),
    input_data_family="ohlcv",
    output_feature_names=("volume",),
    parameters=(),
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
    min_warmup_bars=0,
    stateful=False,
    visible_on_chart=True,
    chart_pane="price_overlay",
    chart_render_type="histogram",
    chart_series_kind="continuous",
    chart_category="Volume",
    chart_subcategory="Volume",
    chart_search_keywords=(
        "volume", "vol", "raw volume", "bar volume",
    ),
    chart_display_order=99,
    chart_editable_parameters=(),
    chart_output_series=(
        ChartSeriesSpec(
            series_id="volume",
            label="Volume",
            pane="price_overlay",
            render_type="histogram",
            default_color="#26a69a",
        ),
    ),
)

VOLUME_MA_METADATA = ToolMetadata(
    tool_id="volume_ma",
    name="Volume",
    short_name="Volume",
    version="1.0.0",
    category=ToolCategory.indicator,
    status=ToolStatus.stable,
    description=(
        "Volume histogram rendered in the price chart pane.  "
        "An optional simple moving average of volume can be shown by setting "
        "ma_length.  When ma_length is omitted the histogram is displayed alone."
    ),
    input_data_family="ohlcv",
    output_feature_names=("volume_ma",),
    parameters=(
        ParameterSpec(
            name="ma_length",
            description=(
                "Length of the volume simple moving average.  "
                "Leave empty (null) to show histogram only.  "
                "Must be a positive integer when provided."
            ),
            type_label="int",
            required=False,
            default=None,
            min_value=1,
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
    min_warmup_bars=0,
    stateful=False,
    visible_on_chart=True,
    chart_pane="price_overlay",
    chart_render_type="histogram",
    chart_series_kind="continuous",
    chart_category="Volume",
    chart_subcategory="Volume",
    chart_search_keywords=(
        "volume", "vol", "volume ma", "volume moving average",
        "volume histogram", "vol ma",
    ),
    chart_display_order=100,
    chart_editable_parameters=("ma_length",),
    chart_output_series=(
        ChartSeriesSpec(
            series_id="volume",
            label="Volume",
            # pane="price_overlay" + render_type="histogram" signals Chart.tsx
            # to create a HistogramSeries on the named 'volume' price scale
            pane="price_overlay",
            render_type="histogram",
            default_color="#26a69a",
        ),
        ChartSeriesSpec(
            series_id="volume_ma",
            label="Vol MA",
            pane="price_overlay",
            render_type="line",
            default_color="#ff9800",
        ),
    ),
)
