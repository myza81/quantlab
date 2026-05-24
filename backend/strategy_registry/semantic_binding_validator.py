"""
Semantic Binding Validator — Phase 2O.5.

Validates that semantic tool_output references resolve against a StrategyToolSet
and, optionally, against a ToolRegistry.

This is STATIC validation only:
- No tool computation
- No indicator evaluation
- No runtime calls
- No market data

Resolves references like:
    "sma_fast.value" → toolset has instance_id="sma_fast" with tool_id that
                       declares "value" in output_feature_names

Architecture boundary:
    This module must NOT import from:
        backend.strategy_runtime
        backend.backtesting
        backend.execution
        backend.forward_testing
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.strategy_registry.semantics import (
    Condition,
    ConditionGroup,
    OperandKind,
    StrategySemantics,
)
from backend.tools.registry import ToolNotFoundError, ToolRegistry
from backend.tools.toolset import StrategyToolSet


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class BindingDiagnostic(BaseModel):
    """A single semantic binding diagnostic message."""
    model_config = ConfigDict(frozen=True)

    severity:  Literal["error", "warning", "info"]
    code:      str    # e.g. "missing_tool_instance", "unknown_output_name"
    reference: str    # full tool_output ref, e.g. "sma_fast.value"
    message:   str


class DependencySummary(BaseModel):
    """
    Static dependency summary produced by binding validation.

    All tuples are sorted for deterministic serialisation.
    No computation is performed — entries are reference strings only.
    """
    model_config = ConfigDict(frozen=True)

    resolved_tool_outputs:   tuple[str, ...]  # exist in toolset + registry
    unresolved_tool_outputs: tuple[str, ...]  # errors: missing or unknown
    warned_tool_outputs:     tuple[str, ...]  # warnings: instance found, registry inconclusive
    price_fields:            tuple[str, ...]
    constants:               tuple[str, ...]


class BindingValidationResult(BaseModel):
    """
    Result of semantic-to-toolset binding validation.

    valid=True   → all tool_output refs resolved with no errors
    valid=False  → at least one error diagnostic present
    Warnings and info do not set valid=False.
    """
    model_config = ConfigDict(frozen=True)

    valid:       bool
    diagnostics: tuple[BindingDiagnostic, ...]
    summary:     DependencySummary


# ---------------------------------------------------------------------------
# Internal extraction helper
# ---------------------------------------------------------------------------

def _collect_refs(
    semantics: StrategySemantics,
) -> tuple[list[str], list[str], list[str]]:
    """
    Walk the semantics tree and collect unique, sorted references.
    Returns (tool_output_refs, price_field_refs, constant_refs).
    """
    tool_outputs: set[str] = set()
    price_fields: set[str] = set()
    constants:    set[str] = set()

    def _visit(group: ConditionGroup) -> None:
        for node in group.conditions:
            if isinstance(node, Condition):
                for operand in (node.left, node.right):
                    if operand.kind == OperandKind.TOOL_OUTPUT:
                        tool_outputs.add(operand.ref)
                    elif operand.kind == OperandKind.PRICE:
                        price_fields.add(operand.ref)
                    elif operand.kind == OperandKind.CONSTANT:
                        constants.add(operand.ref)
            elif isinstance(node, ConditionGroup):
                _visit(node)

    for rule in (*semantics.entry_rules, *semantics.exit_rules):
        _visit(rule.condition_group)

    return sorted(tool_outputs), sorted(price_fields), sorted(constants)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_semantic_bindings(
    semantics: StrategySemantics,
    toolset: StrategyToolSet,
    registry: ToolRegistry | None = None,
) -> BindingValidationResult:
    """
    Validate that all tool_output references in semantics resolve in the toolset.

    For each dotted reference "instance_id.output_name":
      1. Checks instance_id exists in toolset.
      2. If registry provided, checks output_name in tool's declared outputs.
      3. If registry not provided, instance presence is verified but output
         name correctness yields an info diagnostic.

    Price fields and constants are always considered resolved.

    Returns BindingValidationResult with:
        valid=True  → no error-severity diagnostics
        valid=False → at least one error-severity diagnostic
    """
    tool_refs, price_fields, constants = _collect_refs(semantics)

    diagnostics: list[BindingDiagnostic] = []
    resolved:    list[str] = []
    unresolved:  list[str] = []
    warned:      list[str] = []

    for ref in tool_refs:
        if "." not in ref:
            diagnostics.append(BindingDiagnostic(
                severity="error",
                code="invalid_output_format",
                reference=ref,
                message=(
                    f"tool_output '{ref}' must use dotted format "
                    f"'instance_id.output_name' (e.g. 'sma_fast.value')"
                ),
            ))
            unresolved.append(ref)
            continue

        instance_id, output_name = ref.split(".", 1)
        tool_config = toolset.get_tool(instance_id)

        if tool_config is None:
            available = sorted(toolset.instance_ids())
            diagnostics.append(BindingDiagnostic(
                severity="error",
                code="missing_tool_instance",
                reference=ref,
                message=(
                    f"instance_id '{instance_id}' not found in toolset "
                    f"(available: {available})"
                ),
            ))
            unresolved.append(ref)
            continue

        if registry is None:
            diagnostics.append(BindingDiagnostic(
                severity="info",
                code="registry_unavailable",
                reference=ref,
                message=(
                    f"instance_id '{instance_id}' found in toolset; "
                    f"output '{output_name}' not verified (no registry provided)"
                ),
            ))
            warned.append(ref)
            continue

        try:
            metadata = registry.get(tool_config.tool_id)
            if output_name not in metadata.output_feature_names:
                known = sorted(metadata.output_feature_names)
                diagnostics.append(BindingDiagnostic(
                    severity="error",
                    code="unknown_output_name",
                    reference=ref,
                    message=(
                        f"output '{output_name}' not declared by tool "
                        f"'{tool_config.tool_id}'; known: {known}"
                    ),
                ))
                unresolved.append(ref)
            else:
                resolved.append(ref)
        except ToolNotFoundError:
            diagnostics.append(BindingDiagnostic(
                severity="warning",
                code="tool_not_in_registry",
                reference=ref,
                message=(
                    f"tool_id '{tool_config.tool_id}' not found in registry; "
                    f"cannot verify output '{output_name}'"
                ),
            ))
            warned.append(ref)

    has_errors = any(d.severity == "error" for d in diagnostics)

    return BindingValidationResult(
        valid=not has_errors,
        diagnostics=tuple(diagnostics),
        summary=DependencySummary(
            resolved_tool_outputs=tuple(sorted(resolved)),
            unresolved_tool_outputs=tuple(sorted(unresolved)),
            warned_tool_outputs=tuple(sorted(warned)),
            price_fields=tuple(sorted(price_fields)),
            constants=tuple(sorted(constants)),
        ),
    )
