"""
Chart indicator API schemas — Chart-UX-3B.

Covers:
    IndicatorArtifactRequest  — POST /chart/indicator-artifact request body
    IndicatorArtifactResponse — artifact returned for a single tool instance
    ChartIndicatorsListResponse — GET /chart/indicators metadata response

Design notes:
    - IndicatorSeriesPoint.value is Optional[float]: null means warmup bar (no output).
    - All timestamps in responses are ISO 8601 UTC strings.
    - instance_id is always echoed back in IndicatorArtifactResponse so the frontend
      can route each response to the correct chart indicator instance.
    - warmup_bars in the response is the max warmup across all output series.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# POST /chart/indicator-artifact — request
# ---------------------------------------------------------------------------

class IndicatorArtifactRequest(BaseModel):
    """
    Request body for POST /chart/indicator-artifact.

    Identifies the tool, the chart-level instance, the data context, and
    the parameters to compute with.  No strategy draft or composition
    context is required — this is a direct indicator computation.
    """
    model_config = ConfigDict(extra="forbid")

    tool_id: str
    instance_id: str
    symbol: str
    provider: str
    timeframe: str
    date_range_start: datetime
    date_range_end: datetime
    parameters: dict[str, Any]

    # Data context — optional fields that resolve provider and instrument identity
    asset_class: str = "equity"
    exchange: str = ""
    credential_id: Optional[str] = None


# ---------------------------------------------------------------------------
# POST /chart/indicator-artifact — response
# ---------------------------------------------------------------------------

class IndicatorSeriesPoint(BaseModel):
    """Single bar's output for one indicator series."""
    timestamp: str          # ISO 8601 UTC — e.g. "2023-01-03T00:00:00+00:00"
    value: Optional[float]  # null for warmup bars; float for computed bars


class IndicatorArtifactSeries(BaseModel):
    """One named output series within an indicator artifact."""
    series_id: str        # stable id matching tool output_feature_names (e.g. "sma", "macd_line")
    label: str            # human-readable label for chart legend
    pane: str             # "price_overlay" or "oscillator_pane"
    render_type: str      # "line", "histogram", "area", "band_fill"
    default_color: str    # hex color hint, e.g. "#f59e0b"
    values: list[IndicatorSeriesPoint]


class IndicatorArtifactResponse(BaseModel):
    """
    Normalized indicator artifact returned by POST /chart/indicator-artifact.

    Contains all output series with timestamp-aligned values (null for warmup bars)
    and echoes the instance_id so the frontend can route the response to the correct
    chart indicator instance.
    """
    tool_id: str
    instance_id: str          # echoed from request — identifies the chart instance
    display_name: str         # human-readable tool name
    pane: str                 # primary pane: "price_overlay" or "oscillator_pane"
    render_type: str          # primary render type for the tool
    parameters: dict[str, Any]  # echoed from request (validated)
    series: list[IndicatorArtifactSeries]
    warmup_bars: int          # max warmup across all series; leading nulls to expect
    diagnostics: Optional[str] = None


# ---------------------------------------------------------------------------
# GET /chart/indicators — response
# ---------------------------------------------------------------------------

class ChartIndicatorParameterSpec(BaseModel):
    """Parameter spec exposed in the indicator picker for a chart-visible tool."""
    name: str
    description: str
    type_label: str
    required: bool
    default: Any = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    options: Optional[list[str]] = None


class ChartIndicatorSeriesSpec(BaseModel):
    """One output series spec for the indicator picker."""
    series_id: str
    label: str
    pane: str
    render_type: str
    default_color: str


class ChartIndicatorMetadata(BaseModel):
    """
    Full chart indicator metadata for one tool.

    Returned by GET /chart/indicators and used by the frontend indicator picker
    to render the tool list, parameter editor, and chart rendering configuration.

    The display-specific fields (chart_pane, render_type, output_series, etc.) are
    sourced from the static _CHART_DISPLAY_METADATA dict in chart_indicator_service.py
    until Chart-UX-3D migrates them into ToolMetadata.
    """
    tool_id: str
    display_name: str
    description: str
    category: str             # "Trend", "Momentum", "Volatility", etc.
    chart_pane: str           # primary pane
    render_type: str          # primary render type
    series_kind: str          # "continuous" or "event"
    output_series: list[ChartIndicatorSeriesSpec]
    editable_parameters: list[str]
    parameters: list[ChartIndicatorParameterSpec]
    visible_on_chart: bool
    short_name: str | None = None


class ChartIndicatorsListResponse(BaseModel):
    """Response for GET /chart/indicators."""
    indicators: list[ChartIndicatorMetadata]
