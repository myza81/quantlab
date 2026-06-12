from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from backend.strategy_registry.models import RuntimeMode


class ToolCategory(str, Enum):
    indicator = "indicator"
    feature_generator = "feature_generator"
    filter = "filter"
    confirmation = "confirmation"
    risk_analysis = "risk_analysis"
    transformation = "transformation"
    aggregation = "aggregation"
    experimental_research = "experimental_research"


class ToolStatus(str, Enum):
    experimental = "experimental"
    prototype = "prototype"
    validated = "validated"
    stable = "stable"
    deprecated = "deprecated"
    retired = "retired"


class VisualizationCapability(str, Enum):
    produces_line_overlay = "produces_line_overlay"
    produces_oscillator_series = "produces_oscillator_series"
    produces_marker_annotations = "produces_marker_annotations"
    produces_regime_overlay = "produces_regime_overlay"
    produces_zone_overlay = "produces_zone_overlay"
    produces_heatmap = "produces_heatmap"
    no_visualization = "no_visualization"


class ParameterSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    description: str
    type_label: str  # "int", "float", "str", "bool"
    required: bool = True
    default: Any = None
    min_value: float | None = None
    max_value: float | None = None
    # Ordered allowed values. When set, the frontend must render a <select>
    # instead of a free-text or numeric input.  None means no restriction.
    options: tuple[str, ...] | None = None

    @field_validator("name", "description", "type_label")
    @classmethod
    def must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field must not be empty or whitespace")
        return v


class ChartSeriesSpec(BaseModel):
    """
    Specification for one named output series within a chart-visible tool.

    series_id must match a value in the tool's output_feature_names so the
    chart service can align computation output with rendering metadata.

    Chart-UX-3B.1: migrated from the static _CHART_DISPLAY_METADATA dict
    into ToolMetadata so the chart ecosystem is fully registry-driven.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    series_id: str     # matches output_feature_names (e.g. "sma", "macd_line")
    label: str         # human-readable legend label
    pane: str          # "price_overlay" or "oscillator_pane"
    render_type: str   # "line", "histogram", "area", "band_fill"
    default_color: str # hex color string, e.g. "#f59e0b"


class ToolMetadata(BaseModel):
    """
    Metadata contract for a registered analytical tool.

    Declares identity, categorization, parameter schema, runtime compatibility,
    visualization capabilities, and (when visible_on_chart=True) full chart
    indicator rendering and discovery metadata.

    Does not contain executable logic.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_id: str
    name: str
    version: str
    category: ToolCategory
    status: ToolStatus
    description: str
    # Compact UI label (Strategy-UX-1E). When set, drives short labels such as
    # "EMA(21)" in rule builders and indicator chips. Falls back to `name` if None.
    short_name: str | None = None

    # Input/output declarations
    input_data_family: str  # e.g. "ohlcv", "close_series", "any_numeric_series"
    output_feature_names: tuple[str, ...]

    # Parameter schema
    parameters: tuple[ParameterSpec, ...]

    # Runtime compatibility
    supported_runtime_modes: frozenset[RuntimeMode]

    # Visualization capabilities declared by this tool (legacy field; preserved)
    visualization_capabilities: frozenset[VisualizationCapability]

    # Minimum bars required before first valid output (actual warmup may depend on parameters)
    min_warmup_bars: int = 0

    # Whether the tool maintains internal state across bars
    stateful: bool = False

    # -----------------------------------------------------------------------
    # Chart indicator metadata (Chart-UX-3B / Chart-UX-3B.1)
    # -----------------------------------------------------------------------
    # visible_on_chart=True requires category=indicator and all chart_* fields.
    # Validated at model construction time by _validate_chart_metadata.
    # Non-chart tools leave these as defaults and are never validated further.

    visible_on_chart: bool = False

    chart_pane: str | None = None          # "price_overlay" or "oscillator_pane"
    chart_render_type: str | None = None   # "line", "band", "histogram", "area"
    chart_series_kind: str | None = None   # "continuous" or "event"

    # Discovery metadata for the indicator picker
    chart_category: str | None = None      # "Trend", "Momentum", "Volatility", etc.
    chart_subcategory: str | None = None   # optional refinement (e.g. "Moving Averages")
    chart_search_keywords: tuple[str, ...] = ()
    chart_display_order: int = 0

    # Chart rendering contract
    chart_editable_parameters: tuple[str, ...] = ()   # subset of parameters
    chart_output_series: tuple[ChartSeriesSpec, ...] = ()  # one entry per output series

    # -----------------------------------------------------------------------
    # Field validators
    # -----------------------------------------------------------------------

    @field_validator("tool_id")
    @classmethod
    def tool_id_must_be_valid(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("tool_id must not be empty or whitespace")
        return v.strip().lower()

    @field_validator("name", "description", "input_data_family")
    @classmethod
    def must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field must not be empty or whitespace")
        return v

    @field_validator("version")
    @classmethod
    def version_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("version must not be empty")
        return v.strip()

    @field_validator("min_warmup_bars")
    @classmethod
    def warmup_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("min_warmup_bars must be >= 0")
        return v

    # -----------------------------------------------------------------------
    # Cross-field validation for chart metadata
    # -----------------------------------------------------------------------

    @model_validator(mode="after")
    def _validate_chart_metadata(self) -> "ToolMetadata":
        """
        Enforce that any tool declaring visible_on_chart=True also:
          - has category=indicator (non-indicator types must not be chart-visible)
          - declares all required chart metadata fields

        Tools with visible_on_chart=False (the default) are not validated
        against chart metadata requirements.
        """
        if not self.visible_on_chart:
            return self

        if self.category != ToolCategory.indicator:
            raise ValueError(
                f"Tool '{self.tool_id}' sets visible_on_chart=True but "
                f"category={self.category.value!r}. Only tools with "
                f"category='indicator' may be chart-visible."
            )

        missing: list[str] = []
        if self.chart_pane is None:
            missing.append("chart_pane")
        if self.chart_render_type is None:
            missing.append("chart_render_type")
        if self.chart_series_kind is None:
            missing.append("chart_series_kind")
        if self.chart_category is None:
            missing.append("chart_category")
        if not self.chart_output_series:
            missing.append("chart_output_series")

        if missing:
            raise ValueError(
                f"Tool '{self.tool_id}' sets visible_on_chart=True but is missing "
                f"required chart metadata: {', '.join(missing)}"
            )

        return self
