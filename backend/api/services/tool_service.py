"""
Tool discovery and validation service.

Read-only metadata serialization layer between the tools API route and the
backend tool registry. No tool execution is allowed here.
"""
from backend.api.schemas.tools import (
    ToolListResponse,
    ToolMetadataResponse,
    ToolParameterResponse,
    ToolSetValidationResponse,
)
from backend.tools import (
    ToolMetadata,
    ToolRegistry,
    StrategyToolSet,
    validate_strategy_toolset_against_registry,
)


def list_tools(registry: ToolRegistry) -> ToolListResponse:
    """
    Return deterministic, JSON-serializable tool metadata for frontend discovery.
    """
    tools = [
        _serialize_tool_metadata(registry.get(tool_id))
        for tool_id in registry.list_tools()
    ]
    return ToolListResponse(tools=tools)


def validate_toolset(toolset: StrategyToolSet, registry: ToolRegistry) -> ToolSetValidationResponse:
    """Validate a StrategyToolSet against the registry; never raises."""
    result = validate_strategy_toolset_against_registry(toolset, registry)
    return ToolSetValidationResponse(valid=result.valid, errors=list(result.errors))


def _serialize_tool_metadata(metadata: ToolMetadata) -> ToolMetadataResponse:
    return ToolMetadataResponse(
        tool_id=metadata.tool_id,
        name=metadata.name,
        version=metadata.version,
        category=metadata.category.value,
        status=metadata.status.value,
        description=metadata.description,
        input_data_family=metadata.input_data_family,
        output_feature_names=list(metadata.output_feature_names),
        parameters=[
            ToolParameterResponse(
                name=parameter.name,
                type_label=parameter.type_label,
                required=parameter.required,
                default=parameter.default,
                min_value=parameter.min_value,
                max_value=parameter.max_value,
            )
            for parameter in metadata.parameters
        ],
        supported_runtime_modes=sorted(mode.value for mode in metadata.supported_runtime_modes),
        visualization_capabilities=sorted(
            capability.value for capability in metadata.visualization_capabilities
        ),
        min_warmup_bars=metadata.min_warmup_bars,
        stateful=metadata.stateful,
    )
