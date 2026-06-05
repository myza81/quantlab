from backend.tools.atr import ATR_METADATA, compute_atr
from backend.tools.bollinger_bands import BOLLINGER_METADATA, compute_bollinger
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
    derive_warmup_bars_required,
)
from backend.tools.macd import MACD_METADATA, compute_macd
from backend.tools.models import (
    ChartSeriesSpec,
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
from backend.tools.rsi import RSI_METADATA, compute_rsi
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
    registry.register(RSI_METADATA)
    registry.register(MACD_METADATA)
    registry.register(ATR_METADATA)
    registry.register(BOLLINGER_METADATA)
    return registry


__all__ = [
    # models
    "ChartSeriesSpec",
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
    # rsi (Phase 2S)
    "RSI_METADATA",
    "compute_rsi",
    # macd (Phase 2S)
    "MACD_METADATA",
    "compute_macd",
    # atr (Phase 2U)
    "ATR_METADATA",
    "compute_atr",
    # bollinger bands (Phase 2U)
    "BOLLINGER_METADATA",
    "compute_bollinger",
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
    "derive_warmup_bars_required",
    # factory
    "create_default_registry",
]
