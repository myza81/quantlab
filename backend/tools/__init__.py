from backend.tools.models import (
    ParameterSpec,
    ToolCategory,
    ToolMetadata,
    ToolStatus,
    VisualizationCapability,
)
from backend.tools.registry import (
    DuplicateToolError,
    ToolNotFoundError,
    ToolRegistry,
    ToolRegistryError,
)
from backend.tools.sma import SMA_METADATA, compute_sma


def create_default_registry() -> ToolRegistry:
    """Return a ToolRegistry pre-populated with all built-in stable tools."""
    registry = ToolRegistry()
    registry.register(SMA_METADATA)
    return registry


__all__ = [
    # models
    "ParameterSpec",
    "ToolCategory",
    "ToolMetadata",
    "ToolStatus",
    "VisualizationCapability",
    # registry
    "DuplicateToolError",
    "ToolNotFoundError",
    "ToolRegistry",
    "ToolRegistryError",
    # sma
    "SMA_METADATA",
    "compute_sma",
    # factory
    "create_default_registry",
]
