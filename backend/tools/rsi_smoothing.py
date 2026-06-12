"""
RSI Smoothing tool — Phase RSI-1B.

Provides:
    RSI_SMOOTHING_METADATA — registry metadata for the RSI Smoothing tool

The historical computation pipeline entry point is in historical_computation.py
(_compute_rsi_smoothing_series), which computes RSI then applies SMA/EMA smoothing.

RSI Smoothing is used in rules such as:
    rsi.rsi > rsi_smoothing.rsi_smoothing

Computation:
    1. Compute RSI using Wilder's smoothing (same formula as rsi tool)
    2. Apply SMA or EMA smoothing to the RSI series
    3. Emit smoothed values starting at bar index (period + smoothing_length - 1)

Follows the Volume architecture pattern: separate tool (not a multi-output extension
of the existing RSI tool).
"""
from __future__ import annotations

from backend.strategy_registry.models import RuntimeMode
from backend.tools.models import (
    ChartSeriesSpec,
    ParameterSpec,
    ToolCategory,
    ToolMetadata,
    ToolStatus,
    VisualizationCapability,
)

RSI_SMOOTHING_METADATA = ToolMetadata(
    tool_id="rsi_smoothing",
    name="RSI Smoothing",
    short_name="RSI_Smoothing",
    version="1.0.0",
    category=ToolCategory.indicator,
    status=ToolStatus.stable,
    description=(
        "Computes RSI using Wilder's smoothing, then applies a moving average to smooth the result.  "
        "Default: SMA(14) of RSI(14).  "
        "Use alongside RSI (rsi) to build conditions such as rsi.rsi > rsi_smoothing.rsi_smoothing.  "
        "Supports both SMA and EMA smoothing types."
    ),
    input_data_family="ohlcv",
    output_feature_names=("rsi_smoothing",),
    parameters=(
        ParameterSpec(
            name="period",
            description=(
                "RSI lookback window. Must be >= 2.  "
                "Default 14."
            ),
            type_label="int",
            required=True,
            default=14,
            min_value=2,
        ),
        ParameterSpec(
            name="smoothing_type",
            description=(
                "Type of moving average applied to RSI. "
                "Allowed: 'SMA' or 'EMA'. "
                "Default 'SMA'."
            ),
            type_label="str",
            required=True,
            default="SMA",
            options=("SMA", "EMA"),
        ),
        ParameterSpec(
            name="smoothing_length",
            description=(
                "Length of the smoothing moving average applied to RSI. "
                "Must be >= 1. "
                "Default 14."
            ),
            type_label="int",
            required=True,
            default=14,
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
        VisualizationCapability.produces_oscillator_series,
    }),
    min_warmup_bars=2,  # minimum when period=2; actual warmup = period + smoothing_length - 2
    stateful=True,      # RSI is stateful (Wilder smoothing); smoothing is stateful (recursive EMA)
    visible_on_chart=True,
    chart_pane="oscillator_pane",
    chart_render_type="line",
    chart_series_kind="continuous",
    chart_category="Momentum",
    chart_subcategory=None,
    chart_search_keywords=(
        "rsi", "smoothing", "rsi smoothing", "rsi sma", "rsi ema", "smooth rsi",
    ),
    chart_display_order=12,
    chart_editable_parameters=("period", "smoothing_type", "smoothing_length"),
    chart_output_series=(
        ChartSeriesSpec(
            series_id="rsi_smoothing",
            label="RSI Smoothing",
            pane="oscillator_pane",
            render_type="line",
            default_color="#8b5cf6",
        ),
    ),
)
