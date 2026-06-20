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


# ---------------------------------------------------------------------------
# POST /chart/market-structure — request and response (MS-1 / MS-2)
# ---------------------------------------------------------------------------

class OHLCVCandleInput(BaseModel):
    """Single OHLCV candle for market structure computation input."""
    model_config = ConfigDict(extra="forbid")
    timestamp: str   # ISO 8601 UTC
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketStructureRequest(BaseModel):
    """Request body for POST /chart/market-structure."""
    model_config = ConfigDict(extra="forbid")
    candles: list[OHLCVCandleInput]
    engine_id: str = "minor_structure_v1"


class StructurePointResponse(BaseModel):
    """One turning point in the market structure."""
    id: str
    level: str           # "minor" | "main"
    kind: str            # "H" | "L" | "HH" | "HL" | "LH" | "LL" | "unknown"
    timestamp: str       # ISO 8601 UTC
    bar_index: int       # 0-based index into the input candles array
    price: float
    source: str          # "price" | "minor" | "main"
    confirmed: bool


class StructureLegResponse(BaseModel):
    """One directional segment between two structure points."""
    id: str
    level: str           # "minor" | "main"
    from_point_id: str
    to_point_id: str
    direction: str       # "up" | "down"
    start_bar_index: int
    end_bar_index: int
    start_price: float
    end_price: float


class StructureDebugEventResponse(BaseModel):
    """Per-candle decision log for structure verification."""
    bar_index: int
    timestamp: str
    candle_relationship: str   # "higher_high" | "lower_low" | "inside_bar" | "outside_bar" | "ambiguous_startup"
    previous_direction: Optional[str] = None   # "up" | "down" | null
    new_direction: Optional[str] = None        # "up" | "down" | null
    action: str
    reason: str
    affected_level: str        # "minor" | "main"


class BosEventResponse(BaseModel):
    """One Break of Structure event for visual chart verification."""
    status:                        str            # "valid" | "pending" | "invalid"
    direction:                     str            # "bullish" | "bearish"
    structure_scope:               str            # "minor" | "main"
    break_level:                   float
    protected_level:               float
    break_candle_index:            int
    break_candle_timestamp:        str
    confirmation_level:            Optional[float] = None
    confirmation_candle_index:     Optional[int]   = None
    confirmation_candle_timestamp: Optional[str]   = None
    invalidation_candle_index:     Optional[int]   = None
    invalidation_candle_timestamp: Optional[str]   = None
    event_type:                    str = "bos"
    event_effect:                  str = "continuation"


class ChochEventResponse(BaseModel):
    """One Change of Character event for visual chart verification."""
    direction:                     str    # "bullish" | "bearish"
    structure_scope:               str    # "minor" | "main"
    protected_level:               float
    break_candle_index:            int
    break_candle_timestamp:        str
    structure_reference_index:     int
    structure_reference_timestamp: str
    reference_structure_type:      str    # "HL" | "LH"
    violated_trend:                str    # "uptrend" | "downtrend"
    event_type:                    str = "choch"
    status:                        str = "valid"
    event_effect:                  str = "transition"


class ToolLineageResponse(BaseModel):
    """
    Lineage metadata for a versioned research tool execution.

    Included in every POST /chart/market-structure response so callers can
    verify exactly which engine produced the output and never silently receive
    a different version than requested.
    """
    tool_domain:        str   # "market_structure" | "structure_event" | "indicator"
    tool_id:            str   # version-specific id, e.g. "minor_structure_v3"
    version_id:         str   # same as tool_id for engine-versioned tools
    human_name:         str   # "Container Breakout Minor Structure"
    lifecycle_status:   str   # "production" | "experimental" | "retired"
    implementation_ref: str   # "backend/tools/market_structure_v3.py::MinorStructureV3Engine"


class DerivedToolLineageResponse(BaseModel):
    """
    Lineage for a tool whose input is another tool's output (e.g. BoS, CHoCH).

    parent_engine_id and parent_tool_domain form a traceable link back to the
    exact structure engine that fed this derived tool.  Any mismatch between
    parent_engine_id and the structure_lineage.tool_id in the same response is
    a data-lineage error.
    """
    tool_domain:        str   # "structure_event"
    tool_id:            str   # "bos_detection" | "choch_detection"
    parent_tool_domain: str   # "market_structure"
    parent_engine_id:   str   # e.g. "minor_structure_v3" — must match structure_lineage.tool_id


class ExperimentalBosEventResponse(BaseModel):
    """One experimental bullish BoS event from the pivot-triplet detector."""
    direction:              str    # "bullish"
    p1_bar_index:           int
    p1_price:               float
    p1_timestamp:           str
    p2_bar_index:           int
    p2_price:               float
    p2_timestamp:           str
    p3_bar_index:           int
    p3_price:               float
    p3_timestamp:           str
    break_candle_index:     int
    break_candle_timestamp: str
    broken_level:           float


class MarketBiasResponse(BaseModel):
    """
    Market bias output from the experimental local bias engine.

    The engine field identifies the exact version that produced this result,
    preserving future versioning capability without API redesign.
    bias is always "BULLISH", "BEARISH", or "SIDEWAY".
    condition is the market state within that bias.
    """
    engine:        str                        # "market_bias_local_v1"
    bias:          str                        # "BULLISH" | "BEARISH" | "SIDEWAY"
    condition:     str                        # "CONTINUATION" | "REVERSAL" | "CONSOLIDATION" | "VOLATILE" | "INSUFFICIENT_DATA"
    reason:        str                        # machine-readable reason slug
    pivots_used:   list[float]               # [P4, P3, P2, P1, P0] or []
    current_close: float                     # informational/debug only
    boundaries:    dict[str, Optional[float]] # {"support": ..., "resistance": ...}


class MarketStructureResponse(BaseModel):
    """Full market structure result returned by POST /chart/market-structure."""
    minor_points:            list[StructurePointResponse]
    minor_legs:              list[StructureLegResponse]
    main_points:             list[StructurePointResponse]
    main_legs:               list[StructureLegResponse]
    debug_events:            list[StructureDebugEventResponse]
    bos_events:              list[BosEventResponse]                = []
    choch_events:            list[ChochEventResponse]              = []
    experimental_bos_events: list[ExperimentalBosEventResponse]   = []
    market_bias:             Optional[MarketBiasResponse]          = None
    structure_lineage:       Optional[ToolLineageResponse]         = None
    bos_lineage:             Optional[DerivedToolLineageResponse]  = None
    choch_lineage:           Optional[DerivedToolLineageResponse]  = None
