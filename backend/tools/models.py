from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

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

    @field_validator("name", "description", "type_label")
    @classmethod
    def must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field must not be empty or whitespace")
        return v


class ToolMetadata(BaseModel):
    """
    Metadata contract for a registered analytical tool.

    Declares identity, categorization, parameter schema, runtime compatibility,
    and visualization capabilities. Does not contain executable logic.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_id: str
    name: str
    version: str
    category: ToolCategory
    status: ToolStatus
    description: str

    # Input/output declarations
    input_data_family: str  # e.g. "ohlcv", "close_series", "any_numeric_series"
    output_feature_names: tuple[str, ...]

    # Parameter schema
    parameters: tuple[ParameterSpec, ...]

    # Runtime compatibility
    supported_runtime_modes: frozenset[RuntimeMode]

    # Visualization capabilities declared by this tool
    visualization_capabilities: frozenset[VisualizationCapability]

    # Minimum bars required before first valid output (actual warmup may depend on parameters)
    min_warmup_bars: int = 0

    # Whether the tool maintains internal state across bars
    stateful: bool = False

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
