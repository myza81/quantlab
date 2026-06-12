from dataclasses import dataclass

from backend.tools.configuration import ToolConfiguration
from backend.tools.models import ParameterSpec, ToolMetadata
from backend.tools.registry import ToolNotFoundError, ToolRegistry
from backend.tools.toolset import StrategyToolSet


class ConfigurationValidationError(Exception):
    """Raised when a ToolConfiguration fails validation against ToolMetadata."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        detail = "\n".join(f"  - {e}" for e in errors)
        super().__init__(
            f"Tool configuration validation failed ({len(errors)} error(s)):\n{detail}"
        )


@dataclass(frozen=True)
class ToolSetValidationResult:
    """
    Deterministic, immutable result of validating a StrategyToolSet against a registry.

    valid is True iff errors is empty. Errors are ordered by tool position in the toolset.
    Callers must check valid before treating the toolset as registry-confirmed.
    """

    valid: bool
    errors: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.valid and self.errors:
            raise ValueError("ToolSetValidationResult: valid=True but errors is non-empty")
        if not self.valid and not self.errors:
            raise ValueError("ToolSetValidationResult: valid=False but errors is empty")


def validate_tool_configuration(
    config: ToolConfiguration,
    metadata: ToolMetadata,
) -> None:
    """
    Validate a ToolConfiguration against the referenced ToolMetadata.

    Checks performed:
    - tool_id must match metadata.tool_id
    - all required parameters must be present
    - no unknown parameters (not declared in metadata)
    - parameter values must be type-compatible with ParameterSpec.type_label
    - parameter values must be members of ParameterSpec.options when declared
    - numeric values must satisfy ParameterSpec.min_value / max_value

    All violations are collected before raising so callers receive the full error list.

    Raises:
        ConfigurationValidationError: if any check fails; .errors contains
            the full list of violation messages.
    """
    errors: list[str] = []

    if config.tool_id != metadata.tool_id:
        errors.append(
            f"config tool_id '{config.tool_id}' does not match "
            f"metadata tool_id '{metadata.tool_id}'"
        )

    param_index: dict[str, ParameterSpec] = {p.name: p for p in metadata.parameters}

    for spec in metadata.parameters:
        if spec.required and spec.name not in config.parameters:
            errors.append(f"required parameter '{spec.name}' is missing")

    for param_name, value in config.parameters.items():
        if param_name not in param_index:
            errors.append(
                f"unknown parameter '{param_name}' (not declared in tool metadata)"
            )
            continue

        spec = param_index[param_name]

        type_error = _check_type_compatibility(param_name, value, spec.type_label)
        if type_error:
            errors.append(type_error)
            continue

        if spec.options is not None and value not in spec.options:
            allowed = ", ".join(repr(option) for option in spec.options)
            errors.append(
                f"parameter '{param_name}' value {value!r} is not one of "
                f"allowed options: {allowed}"
            )
            continue

        if spec.type_label in ("int", "float") and isinstance(value, (int, float)) and not isinstance(value, bool):
            if spec.min_value is not None and value < spec.min_value:
                errors.append(
                    f"parameter '{param_name}' value {value} is below "
                    f"minimum {spec.min_value}"
                )
            if spec.max_value is not None and value > spec.max_value:
                errors.append(
                    f"parameter '{param_name}' value {value} is above "
                    f"maximum {spec.max_value}"
                )

    if errors:
        raise ConfigurationValidationError(errors)


def validate_strategy_toolset_against_registry(
    toolset: StrategyToolSet,
    registry: ToolRegistry,
) -> ToolSetValidationResult:
    """
    Validate all configured tools in a StrategyToolSet against an active ToolRegistry.

    For each ToolConfiguration in toolset.tools (in insertion order):
      1. Resolves tool_id in the registry; records an error if not found.
      2. If found, runs validate_tool_configuration() against the ToolMetadata
         and collects any parameter errors, each prefixed with the instance_id.

    All errors across all tools are collected before returning. The result is a
    deterministic, ordered tuple of error strings — one pass, full picture.

    This function never raises — errors are surfaced in the returned result only.
    Execution-independent: no tool logic is invoked, no indicators computed.

    Args:
        toolset: The StrategyToolSet to validate.
        registry: The ToolRegistry providing authoritative ToolMetadata.

    Returns:
        ToolSetValidationResult(valid=True, errors=()) if all tools pass,
        or ToolSetValidationResult(valid=False, errors=(...)) listing all issues.
    """
    errors: list[str] = []

    for tool in toolset.tools:
        try:
            metadata = registry.get(tool.tool_id)
        except ToolNotFoundError:
            errors.append(
                f"instance '{tool.instance_id}': "
                f"tool_id '{tool.tool_id}' not found in registry"
            )
            continue

        try:
            validate_tool_configuration(tool, metadata)
        except ConfigurationValidationError as exc:
            for detail in exc.errors:
                errors.append(f"instance '{tool.instance_id}': {detail}")

    if errors:
        return ToolSetValidationResult(valid=False, errors=tuple(errors))
    return ToolSetValidationResult(valid=True, errors=())


def _check_type_compatibility(
    name: str, value: object, type_label: str
) -> str | None:
    """Return an error string if value is incompatible with type_label, else None."""
    if type_label == "bool":
        if not isinstance(value, bool):
            return f"parameter '{name}' expects bool, got {type(value).__name__}"
    elif type_label == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            return f"parameter '{name}' expects int, got {type(value).__name__}"
    elif type_label == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"parameter '{name}' expects float or int, got {type(value).__name__}"
    elif type_label == "str":
        if not isinstance(value, str):
            return f"parameter '{name}' expects str, got {type(value).__name__}"
    return None
