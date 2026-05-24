from backend.tools.computation_models import (
    ToolComputationResult,
    ToolOutputPoint,
    ToolOutputSeries,
)
from backend.tools.configuration import ToolConfiguration
from backend.tools.ema import EMA_METADATA, compute_ema
from backend.tools.historical_computation import (
    ToolComputationBarInput,
    ToolComputationError,
    build_bar_tool_outputs,
    compute_tool_outputs_for_history,
)
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
    registry.register(EMA_METADATA)
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
    # ema (Phase 2R.1)
    "EMA_METADATA",
    "compute_ema",
    # configuration
    "ToolConfiguration",
    # toolset
    "StrategyToolSet",
    # validation
    "ConfigurationValidationError",
    "ToolSetValidationResult",
    "validate_strategy_toolset_against_registry",
    "validate_tool_configuration",
    # computation models (Phase 2R.0)
    "ToolOutputPoint",
    "ToolOutputSeries",
    "ToolComputationResult",
    # historical computation pipeline (Phase 2R.0)
    "ToolComputationBarInput",
    "ToolComputationError",
    "compute_tool_outputs_for_history",
    "build_bar_tool_outputs",
    # factory
    "create_default_registry",
]
