from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class ToolConfiguration(BaseModel):
    """
    A configured instance of a registered tool.

    Represents a named, parameterized binding of a tool definition.
    The same tool_id can produce multiple independent configurations,
    e.g. SMA(period=20) and SMA(period=50) both reference tool_id="sma".

    instance_id uniqueness is enforced at the collection level (e.g., within
    a strategy definition). It is not globally unique across the system.

    Parameters are stored as-is; validation against ToolMetadata is performed
    separately via validate_tool_configuration().
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    instance_id: str  # human-readable label, e.g. "sma_fast" or "sma_20"
    tool_id: str  # references ToolMetadata.tool_id in the registry
    parameters: dict[str, Any]  # keyed by ParameterSpec.name; values are primitives
    enabled: bool = True
    display_name: str | None = None  # optional UI label override
    color: str | None = None  # optional hex color string, e.g. "#2196f3"

    @field_validator("instance_id")
    @classmethod
    def instance_id_must_be_valid(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("instance_id must not be empty or whitespace")
        return v.strip().lower()

    @field_validator("tool_id")
    @classmethod
    def tool_id_must_be_valid(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("tool_id must not be empty or whitespace")
        return v.strip().lower()
