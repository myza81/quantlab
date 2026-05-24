"""
Evaluation Readiness & Linting Layer — Phase 2O.9.

Statically checks whether a compiled EvaluationPlan is structurally ready
for future evaluation.

Answers: "Is this plan coherent, complete, and safe enough for a future evaluator?"

NOT evaluation. NOT market data. NOT indicator computation. NOT execution.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.backtesting
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.strategy_registry.semantic_binding_validator import BindingValidationResult
from backend.strategy_registry.semantic_plan import (
    ConditionGroupPlanNode,
    ConditionPlanNode,
    EvaluationPlan,
)


# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

DEFAULT_MAX_NESTING_DEPTH: int = 5

STANDARD_OPERATORS: frozenset[str] = frozenset({
    "<", ">", "<=", ">=", "==", "!=", "crosses_above", "crosses_below",
})


# ---------------------------------------------------------------------------
# Domain models (passive, frozen Pydantic v2)
# ---------------------------------------------------------------------------

ReadinessSeverity = Literal["blocking", "warning", "info"]
ReadinessStatus   = Literal["ready", "blocked", "degraded"]


class ReadinessIssue(BaseModel):
    """A single static lint issue found during readiness evaluation."""
    model_config = ConfigDict(frozen=True)

    code:       str                # machine-readable code, e.g. "no_rules"
    severity:   ReadinessSeverity  # "blocking" | "warning" | "info"
    message:    str
    path:       str | None = None  # plan path string, e.g. "rule[0].condition[1]"
    node_id:    str | None = None  # rule_id / condition_id / group_id
    suggestion: str | None = None  # actionable fix hint


class ReadinessSummary(BaseModel):
    """Counts of readiness issues by severity."""
    model_config = ConfigDict(frozen=True)

    blocking_count: int
    warning_count:  int
    info_count:     int


class EvaluationReadinessReport(BaseModel):
    """
    Deterministic, execution-free readiness assessment of an EvaluationPlan.

    ready=True   → no blocking issues; plan is structurally ready for evaluation
    ready=False  → at least one blocking issue prevents evaluation

    status:
        "ready"    → ready=True, no warnings present
        "degraded" → ready=True but non-blocking warnings present
        "blocked"  → ready=False (at least one blocking issue)
    """
    model_config = ConfigDict(frozen=True)

    ready:   bool
    status:  ReadinessStatus
    summary: ReadinessSummary
    issues:  tuple[ReadinessIssue, ...]


# ---------------------------------------------------------------------------
# Lint rule helpers — each appends ReadinessIssue objects to `issues`
# ---------------------------------------------------------------------------

def _check_compiled(
    compiled: bool,
    errors:   tuple[str, ...],
    issues:   list[ReadinessIssue],
) -> None:
    if not compiled:
        issues.append(ReadinessIssue(
            code="not_compiled",
            severity="blocking",
            message="Semantics did not compile into an EvaluationPlan.",
            suggestion=(
                "Ensure semantics are syntactically valid and non-empty before "
                "requesting readiness."
            ),
        ))
        for err in errors:
            issues.append(ReadinessIssue(
                code="compilation_error",
                severity="blocking",
                message=err,
                suggestion="Fix the reported compilation error in the semantic definition.",
            ))


def _check_compilation_diagnostics(
    plan:   EvaluationPlan,
    issues: list[ReadinessIssue],
) -> None:
    for diag in plan.diagnostics:
        if diag.severity == "error":
            issues.append(ReadinessIssue(
                code="compilation_diagnostic_error",
                severity="blocking",
                message=diag.message,
                path=diag.path,
                suggestion="Resolve the compilation error in the semantic definition.",
            ))
        elif diag.severity == "warning":
            issues.append(ReadinessIssue(
                code="compilation_diagnostic_warning",
                severity="warning",
                message=diag.message,
                path=diag.path,
            ))


def _check_has_rules(plan: EvaluationPlan, issues: list[ReadinessIssue]) -> None:
    if not plan.rule_nodes:
        issues.append(ReadinessIssue(
            code="no_rules",
            severity="blocking",
            message="EvaluationPlan has no rule nodes (no entry or exit rules).",
            suggestion=(
                "Add at least one entry or exit rule to the strategy semantics."
            ),
        ))


def _check_no_empty_rules(plan: EvaluationPlan, issues: list[ReadinessIssue]) -> None:
    for rule in plan.rule_nodes:
        if _count_conditions(rule.condition_group) == 0:
            issues.append(ReadinessIssue(
                code="empty_rule",
                severity="blocking",
                message=(
                    f"{rule.kind.capitalize()} rule[{rule.index}] has no conditions."
                ),
                path=f"rule[{rule.index}]",
                node_id=rule.rule_id,
                suggestion="Add at least one condition to the rule.",
            ))


def _count_conditions(group: ConditionGroupPlanNode) -> int:
    count = 0
    for node in group.nodes:
        if isinstance(node, ConditionPlanNode):
            count += 1
        else:
            count += _count_conditions(node)
    return count


def _check_semantic_ids(plan: EvaluationPlan, issues: list[ReadinessIssue]) -> None:
    for rule in plan.rule_nodes:
        if rule.rule_id is None:
            issues.append(ReadinessIssue(
                code="missing_rule_id",
                severity="warning",
                message=(
                    f"{rule.kind.capitalize()} rule[{rule.index}] has no rule_id. "
                    "Semantic identity injection may not have run."
                ),
                path=f"rule[{rule.index}]",
                suggestion=(
                    "Save semantics through PUT /drafts/{id}/semantics to trigger "
                    "automatic ID injection."
                ),
            ))
        _check_group_ids(rule.condition_group, f"rule[{rule.index}]", issues)


def _check_group_ids(
    group:  ConditionGroupPlanNode,
    path:   str,
    issues: list[ReadinessIssue],
) -> None:
    if group.group_id is None:
        issues.append(ReadinessIssue(
            code="missing_group_id",
            severity="warning",
            message=f"Condition group at {path} has no group_id.",
            path=path,
            suggestion=(
                "Save semantics through PUT /drafts/{id}/semantics to trigger "
                "automatic ID injection."
            ),
        ))
    for i, node in enumerate(group.nodes):
        if isinstance(node, ConditionPlanNode):
            if node.condition_id is None:
                issues.append(ReadinessIssue(
                    code="missing_condition_id",
                    severity="warning",
                    message=(
                        f"Condition at {path}.condition[{i}] has no condition_id."
                    ),
                    path=f"{path}.condition[{i}]",
                    suggestion=(
                        "Save semantics through PUT /drafts/{id}/semantics to trigger "
                        "automatic ID injection."
                    ),
                ))
        else:
            _check_group_ids(node, f"{path}.group[{i}]", issues)


def _check_operators(
    plan:                EvaluationPlan,
    supported_operators: frozenset[str],
    issues:              list[ReadinessIssue],
) -> None:
    unsupported: dict[str, str] = {}  # operator → first path seen

    def _scan_group(group: ConditionGroupPlanNode, path: str) -> None:
        for i, node in enumerate(group.nodes):
            if isinstance(node, ConditionPlanNode):
                op = node.operator
                if op not in supported_operators and op not in unsupported:
                    unsupported[op] = f"{path}.condition[{i}]"
            else:
                _scan_group(node, f"{path}.group[{i}]")

    for rule in plan.rule_nodes:
        _scan_group(rule.condition_group, f"rule[{rule.index}]")

    for op, first_path in sorted(unsupported.items()):
        issues.append(ReadinessIssue(
            code="unsupported_operator",
            severity="blocking",
            message=(
                f"Operator '{op}' is not in the standard supported operator set "
                f"{sorted(supported_operators)}."
            ),
            path=first_path,
            suggestion=(
                "Use a standard operator, or register a concrete evaluator that "
                "declares support for this operator."
            ),
        ))


def _check_nesting_depth(
    plan:      EvaluationPlan,
    threshold: int,
    issues:    list[ReadinessIssue],
) -> None:
    for rule in plan.rule_nodes:
        depth = _max_group_depth(rule.condition_group, 0)
        if depth > threshold:
            issues.append(ReadinessIssue(
                code="excessive_nesting_depth",
                severity="warning",
                message=(
                    f"{rule.kind.capitalize()} rule[{rule.index}] has nesting depth "
                    f"{depth}, exceeding threshold {threshold}."
                ),
                path=f"rule[{rule.index}]",
                node_id=rule.rule_id,
                suggestion=(
                    f"Flatten condition groups to nesting depth ≤ {threshold}."
                ),
            ))


def _max_group_depth(group: ConditionGroupPlanNode, current: int) -> int:
    max_depth = current
    for node in group.nodes:
        if not isinstance(node, ConditionPlanNode):
            max_depth = max(max_depth, _max_group_depth(node, current + 1))
    return max_depth


def _check_binding(
    binding_result: BindingValidationResult | None,
    issues:         list[ReadinessIssue],
) -> None:
    if binding_result is None:
        return
    if not binding_result.valid:
        for diag in binding_result.diagnostics:
            if diag.severity == "error":
                issues.append(ReadinessIssue(
                    code="binding_invalid",
                    severity="blocking",
                    message=f"Binding error [{diag.code}]: {diag.message}",
                    node_id=diag.reference,
                    suggestion=(
                        "Ensure all tool_output references match the draft's toolset "
                        "and tool registry."
                    ),
                ))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_readiness(
    *,
    compiled:                    bool,
    errors:                      tuple[str, ...] = (),
    plan:                        EvaluationPlan | None = None,
    binding_result:              BindingValidationResult | None = None,
    supported_operators:         frozenset[str] = STANDARD_OPERATORS,
    max_nesting_depth_threshold: int = DEFAULT_MAX_NESTING_DEPTH,
) -> EvaluationReadinessReport:
    """
    Check evaluation readiness of a compiled EvaluationPlan.

    Runs static lint rules and returns a deterministic readiness report.
    No evaluation. No market data. No indicators. No execution.

    Issues are returned in severity order (blocking → warning → info),
    stable within each severity by lint-rule registration order.

    Args:
        compiled:                    Whether compilation succeeded.
        errors:                      Compilation error strings (if not compiled).
        plan:                        Compiled EvaluationPlan, or None if compilation failed.
        binding_result:              Binding validation result; None = no binding check.
        supported_operators:         Set of operator strings the standard evaluator handles.
        max_nesting_depth_threshold: Maximum nesting depth before issuing a warning.

    Returns:
        EvaluationReadinessReport with ready flag, status, summary, and issues.
    """
    issues: list[ReadinessIssue] = []

    _check_compiled(compiled, errors, issues)

    if plan is not None:
        _check_compilation_diagnostics(plan, issues)
        _check_has_rules(plan, issues)
        _check_no_empty_rules(plan, issues)
        _check_semantic_ids(plan, issues)
        _check_operators(plan, supported_operators, issues)
        _check_nesting_depth(plan, max_nesting_depth_threshold, issues)

    _check_binding(binding_result, issues)

    # Stable sort: blocking first, then warning, then info; stable within each group
    _severity_order = {"blocking": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: _severity_order[i.severity])

    has_blocking = any(i.severity == "blocking" for i in issues)
    has_warning  = any(i.severity == "warning"  for i in issues)

    ready: bool = not has_blocking
    if has_blocking:
        status: ReadinessStatus = "blocked"
    elif has_warning:
        status = "degraded"
    else:
        status = "ready"

    return EvaluationReadinessReport(
        ready=ready,
        status=status,
        summary=ReadinessSummary(
            blocking_count=sum(1 for i in issues if i.severity == "blocking"),
            warning_count=sum(1 for i in issues if i.severity == "warning"),
            info_count=sum(1 for i in issues if i.severity == "info"),
        ),
        issues=tuple(issues),
    )
