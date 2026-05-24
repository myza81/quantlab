"""
Semantic Validator — Phase 2O.1.

Structural-only validation for StrategySemantics objects.

Validates:
- operand reference format by kind
- non-empty condition groups
- nested group structure (recursive)
- overall entry/exit rule structure

CRITICAL — what this module does NOT do:
- evaluate conditions against market data
- compute indicator values
- generate trading signals
- interpret price action
- invoke any runtime execution

This is semantic STRUCTURE validation only.
"""
from __future__ import annotations

from backend.strategy_registry.semantics import (
    Condition,
    ConditionGroup,
    OperandKind,
    OperandReference,
    StrategySemantics,
)

# Recognised PRICE ref values
_VALID_PRICE_REFS: frozenset[str] = frozenset(
    {"open", "high", "low", "close", "volume"}
)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

class SemanticValidationResult:
    """Structural validation result. valid=True iff errors is empty."""

    def __init__(self, errors: list[str]) -> None:
        self.valid  = len(errors) == 0
        self.errors = errors

    def __repr__(self) -> str:
        return f"SemanticValidationResult(valid={self.valid}, errors={self.errors!r})"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_operand(ref: OperandReference, path: str, errors: list[str]) -> None:
    if ref.kind == OperandKind.PRICE:
        if ref.ref not in _VALID_PRICE_REFS:
            errors.append(
                f"{path}: price operand '{ref.ref}' is not a recognised price field "
                f"(expected one of: {sorted(_VALID_PRICE_REFS)})"
            )
    elif ref.kind == OperandKind.TOOL_OUTPUT:
        if "." not in ref.ref:
            errors.append(
                f"{path}: tool_output ref '{ref.ref}' must use dotted format "
                f"'instance_id.output_name' (e.g. 'sma_fast.value')"
            )
    elif ref.kind == OperandKind.CONSTANT:
        try:
            float(ref.ref)
        except ValueError:
            errors.append(
                f"{path}: constant ref '{ref.ref}' is not a valid numeric constant"
            )


def _validate_condition(cond: Condition, path: str, errors: list[str]) -> None:
    _validate_operand(cond.left,  f"{path}.left",  errors)
    _validate_operand(cond.right, f"{path}.right", errors)


def _validate_group(group: ConditionGroup, path: str, errors: list[str]) -> None:
    # ConditionGroup.model_validator already enforces non-empty, but guard here
    # to provide a clear path-aware error message if somehow bypassed.
    if len(group.conditions) == 0:
        errors.append(f"{path}: ConditionGroup must contain at least one condition")
        return
    for i, node in enumerate(group.conditions):
        node_path = f"{path}.conditions[{i}]"
        if isinstance(node, Condition):
            _validate_condition(node, node_path, errors)
        elif isinstance(node, ConditionGroup):
            _validate_group(node, node_path, errors)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_semantics_structure(semantics: StrategySemantics) -> SemanticValidationResult:
    """
    Validate the structural integrity of a StrategySemantics object.

    Checks operand reference formats, nested group consistency, logical
    composition validity, and stable ID uniqueness.
    Does NOT evaluate conditions against market data.

    Returns a SemanticValidationResult with valid=True and empty errors list
    on success, or valid=False with a non-empty errors list on failure.
    """
    errors: list[str] = []

    for i, rule in enumerate(semantics.entry_rules):
        _validate_group(
            rule.condition_group,
            f"entry_rules[{i}].condition_group",
            errors,
        )

    for i, rule in enumerate(semantics.exit_rules):
        _validate_group(
            rule.condition_group,
            f"exit_rules[{i}].condition_group",
            errors,
        )

    # Append identity integrity errors (IDs present but duplicate)
    id_result = validate_semantic_identity_integrity(semantics)
    errors.extend(id_result.errors)

    return SemanticValidationResult(errors)


# ---------------------------------------------------------------------------
# Identity integrity — duplicate ID detection
# ---------------------------------------------------------------------------

def _collect_group_ids(
    group: ConditionGroup,
    path: str,
    condition_ids: dict[str, str],
    group_ids: dict[str, str],
    errors: list[str],
) -> None:
    if group.group_id is not None:
        if group.group_id in group_ids:
            errors.append(
                f"{path}: duplicate group_id '{group.group_id}' "
                f"(first seen at {group_ids[group.group_id]})"
            )
        else:
            group_ids[group.group_id] = path

    for i, node in enumerate(group.conditions):
        node_path = f"{path}.conditions[{i}]"
        if isinstance(node, Condition):
            if node.condition_id is not None:
                if node.condition_id in condition_ids:
                    errors.append(
                        f"{node_path}: duplicate condition_id '{node.condition_id}' "
                        f"(first seen at {condition_ids[node.condition_id]})"
                    )
                else:
                    condition_ids[node.condition_id] = node_path
        elif isinstance(node, ConditionGroup):
            _collect_group_ids(node, node_path, condition_ids, group_ids, errors)


def validate_semantic_identity_integrity(
    semantics: StrategySemantics,
) -> SemanticValidationResult:
    """
    Verify that all stable IDs within the semantics tree are unique.

    Checks rule_ids, group_ids, and condition_ids independently.
    IDs that are None (legacy/pre-injection) are skipped — not an error.

    Returns SemanticValidationResult(valid=True) when all present IDs are unique.
    """
    errors: list[str] = []
    rule_ids:      dict[str, str] = {}
    group_ids:     dict[str, str] = {}
    condition_ids: dict[str, str] = {}

    for i, rule in enumerate(semantics.entry_rules):
        path = f"entry_rules[{i}]"
        if rule.rule_id is not None:
            if rule.rule_id in rule_ids:
                errors.append(
                    f"{path}: duplicate rule_id '{rule.rule_id}' "
                    f"(first seen at {rule_ids[rule.rule_id]})"
                )
            else:
                rule_ids[rule.rule_id] = path
        _collect_group_ids(
            rule.condition_group, f"{path}.condition_group",
            condition_ids, group_ids, errors,
        )

    for i, rule in enumerate(semantics.exit_rules):
        path = f"exit_rules[{i}]"
        if rule.rule_id is not None:
            if rule.rule_id in rule_ids:
                errors.append(
                    f"{path}: duplicate rule_id '{rule.rule_id}' "
                    f"(first seen at {rule_ids[rule.rule_id]})"
                )
            else:
                rule_ids[rule.rule_id] = path
        _collect_group_ids(
            rule.condition_group, f"{path}.condition_group",
            condition_ids, group_ids, errors,
        )

    return SemanticValidationResult(errors)
