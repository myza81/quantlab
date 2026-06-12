"""
RSI Midline tool — Phase RSI-1A.

Provides:
    RSI_MIDLINE_METADATA — registry metadata for the RSI Midline tool
    (no compute_rsi_midline function needed; computation is trivial)

The historical computation pipeline entry point is in historical_computation.py
(_compute_rsi_midline_series), which emits a constant value per bar.

RSI Midline is a reference level (typically 50) used in strategy rules such as:
    rsi.rsi > rsi_midline.rsi_midline

It follows the Volume architecture pattern: separate tool (not a multi-output extension
of the existing RSI tool).

Computation behavior:
    For every input bar, emit the configured value unchanged.
    No warmup; every bar produces one output.
    No internal state; deterministic.
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

RSI_MIDLINE_METADATA = ToolMetadata(
    tool_id="rsi_midline",
    name="RSI Midline",
    short_name="RSI_Midline",
    version="1.0.0",
    category=ToolCategory.indicator,
    status=ToolStatus.stable,
    description=(
        "Provides an editable constant reference level for RSI-based conditions.  "
        "Default value is 50 (the neutral point on the 0-100 RSI scale).  "
        "Use alongside RSI (rsi) to build conditions such as rsi.rsi > rsi_midline.rsi_midline.  "
        "Value must be between 0 and 100."
    ),
    input_data_family="ohlcv",
    output_feature_names=("rsi_midline",),
    parameters=(
        ParameterSpec(
            name="value",
            description=(
                "RSI reference level (0-100).  "
                "Default 50 (neutral point).  "
                "Must be numeric."
            ),
            type_label="float",
            required=True,
            default=50,
            min_value=0,
            max_value=100,
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
    min_warmup_bars=0,
    stateful=False,
    visible_on_chart=True,
    chart_pane="oscillator_pane",
    chart_render_type="line",
    chart_series_kind="continuous",
    chart_category="Momentum",
    chart_subcategory=None,
    chart_search_keywords=(
        "rsi", "midline", "rsi midline", "reference level", "threshold",
    ),
    chart_display_order=11,
    chart_editable_parameters=("value",),
    chart_output_series=(
        ChartSeriesSpec(
            series_id="rsi_midline",
            label="RSI Midline",
            pane="oscillator_pane",
            render_type="line",
            default_color="#64748b",
        ),
    ),
)
