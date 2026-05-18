from backend.tools.configuration import ToolConfiguration
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
from backend.tools.toolset import StrategyToolSet
from backend.tools.validation import (
    ConfigurationValidationError,
    ToolSetValidationResult,
    validate_strategy_toolset_against_registry,
    validate_tool_configuration,
)


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
    # configuration
    "ToolConfiguration",
    # toolset
    "StrategyToolSet",
    # validation
    "ConfigurationValidationError",
    "ToolSetValidationResult",
    "validate_strategy_toolset_against_registry",
    "validate_tool_configuration",
    # factory
    "create_default_registry",
]
