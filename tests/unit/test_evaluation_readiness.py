"""
Phase 2O.9 — Evaluation Readiness domain tests.

Covers:
- Ready plan → status="ready", ready=True, no blocking issues
- No compilation (not compiled) → status="blocked"
- Compilation error strings → blocking issues
- Compilation diagnostic errors → blocking
- Compilation diagnostic warnings → warning
- Binding invalid → blocking issues
- Empty plan (no rules) → blocked
- Empty rule (0 conditions) → blocked
- Missing rule_id → warning
- Missing group_id → warning
- Missing condition_id → warning
- Unsupported operator → blocked
- Excessive nesting depth → warning (degraded)
- Degraded status (ready=True but warnings present)
- Deterministic issue ordering (blocking before warning)
- Summary counts correct
- Architecture boundary: no imports from runtime/backtesting/execution/forward_testing
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.strategy_registry.evaluation_readiness import (
    DEFAULT_MAX_NESTING_DEPTH,
    STANDARD_OPERATORS,
    EvaluationReadinessReport,
    ReadinessSummary,
    check_readiness,
)
from backend.strategy_registry.semantic_binding_validator import (
    BindingDiagnostic,
    BindingValidationResult,
    DependencySummary,
)
from backend.strategy_registry.semantic_plan import (
    ConditionGroupPlanNode,
    ConditionPlanNode,
    DependencySet,
    EvaluationPlan,
    RulePlanNode,
)

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cond(
    operator: str = ">",
    condition_id: str | None = "cond-1",
) -> ConditionPlanNode:
    return ConditionPlanNode(
        condition_id=condition_id,
        left_kind="price",
        left_ref="close",
        operator=operator,
        right_kind="constant",
        right_ref="30",
        label=None,
    )


def _group(
    *nodes: ConditionPlanNode | ConditionGroupPlanNode,
    group_id: str | None = "group-1",
) -> ConditionGroupPlanNode:
    return ConditionGroupPlanNode(
        group_id=group_id,
        operator="AND",
        nodes=nodes,
        label=None,
    )


def _rule(
    kind: str = "entry",
    index: int = 0,
    group: ConditionGroupPlanNode | None = None,
    rule_id: str | None = "rule-1",
) -> RulePlanNode:
    return RulePlanNode(
        rule_id=rule_id,
        kind=kind,
        index=index,
        label=None,
        condition_group=group or _group(_cond()),
    )


def _plan(*rules: RulePlanNode) -> EvaluationPlan:
    return EvaluationPlan(
        draft_id=None,
        semantic_version="1.0",
        rule_nodes=rules,
        dependencies=DependencySet(
            tool_outputs=(),
            price_fields=("close",),
            constants=("30",),
        ),
        diagnostics=(),
        node_count=len(rules) * 2,
        compiled_at=datetime.now(UTC),
    )


def _simple_plan() -> EvaluationPlan:
    return _plan(
        _rule("entry", 0, rule_id="rule-entry"),
        _rule("exit",  1, rule_id="rule-exit"),
    )


def _invalid_binding() -> BindingValidationResult:
    return BindingValidationResult(
        valid=False,
        diagnostics=(BindingDiagnostic(
            severity="error",
            code="missing_tool_instance",
            reference="sma_fast.sma",
            message="instance_id 'sma_fast' not found in toolset",
        ),),
        summary=DependencySummary(
            resolved_tool_outputs=(),
            unresolved_tool_outputs=("sma_fast.sma",),
            warned_tool_outputs=(),
            price_fields=(),
            constants=(),
        ),
    )


def _valid_binding() -> BindingValidationResult:
    return BindingValidationResult(
        valid=True,
        diagnostics=(),
        summary=DependencySummary(
            resolved_tool_outputs=(),
            unresolved_tool_outputs=(),
            warned_tool_outputs=(),
            price_fields=("close",),
            constants=("30",),
        ),
    )


# ---------------------------------------------------------------------------
# Ready plan
# ---------------------------------------------------------------------------

class TestReadyPlan:
    def test_ready_true(self):
        r = check_readiness(compiled=True, plan=_simple_plan())
        assert r.ready is True

    def test_status_ready(self):
        r = check_readiness(compiled=True, plan=_simple_plan())
        assert r.status == "ready"

    def test_no_issues(self):
        r = check_readiness(compiled=True, plan=_simple_plan())
        assert r.issues == ()

    def test_summary_all_zero(self):
        r = check_readiness(compiled=True, plan=_simple_plan())
        assert r.summary.blocking_count == 0
        assert r.summary.warning_count  == 0
        assert r.summary.info_count     == 0

    def test_returns_report_instance(self):
        r = check_readiness(compiled=True, plan=_simple_plan())
        assert isinstance(r, EvaluationReadinessReport)

    def test_issues_is_tuple(self):
        r = check_readiness(compiled=True, plan=_simple_plan())
        assert isinstance(r.issues, tuple)

    def test_summary_is_frozen(self):
        r = check_readiness(compiled=True, plan=_simple_plan())
        assert isinstance(r.summary, ReadinessSummary)


# ---------------------------------------------------------------------------
# Not compiled
# ---------------------------------------------------------------------------

class TestNotCompiled:
    def test_ready_false(self):
        r = check_readiness(compiled=False)
        assert r.ready is False

    def test_status_blocked(self):
        r = check_readiness(compiled=False)
        assert r.status == "blocked"

    def test_not_compiled_issue_present(self):
        r = check_readiness(compiled=False)
        codes = {i.code for i in r.issues}
        assert "not_compiled" in codes

    def test_not_compiled_severity_blocking(self):
        r = check_readiness(compiled=False)
        issue = next(i for i in r.issues if i.code == "not_compiled")
        assert issue.severity == "blocking"

    def test_compilation_error_strings_become_issues(self):
        r = check_readiness(compiled=False, errors=("missing condition group",))
        codes = {i.code for i in r.issues}
        assert "compilation_error" in codes

    def test_compilation_error_message_preserved(self):
        r = check_readiness(compiled=False, errors=("missing condition group",))
        error_issues = [i for i in r.issues if i.code == "compilation_error"]
        assert any("missing condition group" in i.message for i in error_issues)

    def test_blocking_count_includes_error_strings(self):
        r = check_readiness(
            compiled=False,
            errors=("error one", "error two"),
        )
        # not_compiled + 2 compilation_error = 3
        assert r.summary.blocking_count == 3


# ---------------------------------------------------------------------------
# Compilation diagnostics
# ---------------------------------------------------------------------------

class TestCompilationDiagnostics:
    def _plan_with_error_diag(self) -> EvaluationPlan:
        from backend.strategy_registry.semantic_plan import CompilationDiagnostic
        plan = _simple_plan()
        return EvaluationPlan(
            **{
                **plan.model_dump(),
                "diagnostics": (CompilationDiagnostic(
                    severity="error",
                    message="structural error in group",
                    path="rule[0].group",
                ),),
            }
        )

    def _plan_with_warning_diag(self) -> EvaluationPlan:
        from backend.strategy_registry.semantic_plan import CompilationDiagnostic
        plan = _simple_plan()
        return EvaluationPlan(
            **{
                **plan.model_dump(),
                "diagnostics": (CompilationDiagnostic(
                    severity="warning",
                    message="advisory: nested group depth high",
                    path="rule[0]",
                ),),
            }
        )

    def test_error_diag_creates_blocking_issue(self):
        r = check_readiness(compiled=True, plan=self._plan_with_error_diag())
        assert any(i.code == "compilation_diagnostic_error" for i in r.issues)

    def test_error_diag_makes_blocked(self):
        r = check_readiness(compiled=True, plan=self._plan_with_error_diag())
        assert r.status == "blocked"
        assert r.ready is False

    def test_warning_diag_creates_warning_issue(self):
        r = check_readiness(compiled=True, plan=self._plan_with_warning_diag())
        assert any(i.code == "compilation_diagnostic_warning" for i in r.issues)

    def test_warning_diag_does_not_block(self):
        r = check_readiness(compiled=True, plan=self._plan_with_warning_diag())
        assert r.ready is True
        assert r.status == "degraded"


# ---------------------------------------------------------------------------
# Binding validation
# ---------------------------------------------------------------------------

class TestBindingValidation:
    def test_binding_invalid_makes_blocked(self):
        r = check_readiness(
            compiled=True,
            plan=_simple_plan(),
            binding_result=_invalid_binding(),
        )
        assert r.ready is False
        assert r.status == "blocked"

    def test_binding_invalid_creates_blocking_issue(self):
        r = check_readiness(
            compiled=True,
            plan=_simple_plan(),
            binding_result=_invalid_binding(),
        )
        assert any(i.code == "binding_invalid" for i in r.issues)

    def test_binding_invalid_issue_contains_reference(self):
        r = check_readiness(
            compiled=True,
            plan=_simple_plan(),
            binding_result=_invalid_binding(),
        )
        issues = [i for i in r.issues if i.code == "binding_invalid"]
        assert any("sma_fast" in (i.node_id or "") for i in issues)

    def test_binding_valid_no_binding_issues(self):
        r = check_readiness(
            compiled=True,
            plan=_simple_plan(),
            binding_result=_valid_binding(),
        )
        assert not any(i.code == "binding_invalid" for i in r.issues)

    def test_no_binding_result_no_binding_issues(self):
        r = check_readiness(compiled=True, plan=_simple_plan(), binding_result=None)
        assert not any(i.code == "binding_invalid" for i in r.issues)


# ---------------------------------------------------------------------------
# No rules
# ---------------------------------------------------------------------------

class TestNoRules:
    def _empty_plan(self) -> EvaluationPlan:
        return EvaluationPlan(
            draft_id=None,
            semantic_version="1.0",
            rule_nodes=(),
            dependencies=DependencySet(tool_outputs=(), price_fields=(), constants=()),
            diagnostics=(),
            node_count=0,
            compiled_at=datetime.now(UTC),
        )

    def test_no_rules_blocked(self):
        r = check_readiness(compiled=True, plan=self._empty_plan())
        assert r.ready is False
        assert r.status == "blocked"

    def test_no_rules_issue_code(self):
        r = check_readiness(compiled=True, plan=self._empty_plan())
        assert any(i.code == "no_rules" for i in r.issues)

    def test_no_rules_is_blocking(self):
        r = check_readiness(compiled=True, plan=self._empty_plan())
        issue = next(i for i in r.issues if i.code == "no_rules")
        assert issue.severity == "blocking"


# ---------------------------------------------------------------------------
# Empty rule (0 conditions)
# ---------------------------------------------------------------------------

class TestEmptyRule:
    def _plan_with_empty_rule(self) -> EvaluationPlan:
        empty_group = ConditionGroupPlanNode(
            group_id="group-empty",
            operator="AND",
            nodes=(),
            label=None,
        )
        return _plan(_rule("entry", 0, group=empty_group))

    def test_empty_rule_blocked(self):
        r = check_readiness(compiled=True, plan=self._plan_with_empty_rule())
        assert r.ready is False

    def test_empty_rule_issue_code(self):
        r = check_readiness(compiled=True, plan=self._plan_with_empty_rule())
        assert any(i.code == "empty_rule" for i in r.issues)

    def test_empty_rule_path_present(self):
        r = check_readiness(compiled=True, plan=self._plan_with_empty_rule())
        issue = next(i for i in r.issues if i.code == "empty_rule")
        assert issue.path == "rule[0]"


# ---------------------------------------------------------------------------
# Semantic ID checks
# ---------------------------------------------------------------------------

class TestSemanticIds:
    def _plan_missing_rule_id(self) -> EvaluationPlan:
        return _plan(_rule("entry", 0, rule_id=None))

    def _plan_missing_group_id(self) -> EvaluationPlan:
        return _plan(_rule("entry", 0, group=_group(_cond(), group_id=None)))

    def _plan_missing_condition_id(self) -> EvaluationPlan:
        return _plan(_rule("entry", 0, group=_group(_cond(condition_id=None))))

    def test_missing_rule_id_is_warning(self):
        r = check_readiness(compiled=True, plan=self._plan_missing_rule_id())
        issue = next(i for i in r.issues if i.code == "missing_rule_id")
        assert issue.severity == "warning"

    def test_missing_rule_id_does_not_block(self):
        r = check_readiness(compiled=True, plan=self._plan_missing_rule_id())
        assert r.ready is True
        assert r.status == "degraded"

    def test_missing_group_id_is_warning(self):
        r = check_readiness(compiled=True, plan=self._plan_missing_group_id())
        assert any(i.code == "missing_group_id" for i in r.issues)

    def test_missing_condition_id_is_warning(self):
        r = check_readiness(compiled=True, plan=self._plan_missing_condition_id())
        assert any(i.code == "missing_condition_id" for i in r.issues)

    def test_all_ids_present_no_id_warnings(self):
        r = check_readiness(compiled=True, plan=_simple_plan())
        id_codes = {"missing_rule_id", "missing_group_id", "missing_condition_id"}
        assert not any(i.code in id_codes for i in r.issues)


# ---------------------------------------------------------------------------
# Unsupported operator
# ---------------------------------------------------------------------------

class TestUnsupportedOperator:
    def _plan_custom_op(self, op: str = "CUSTOM") -> EvaluationPlan:
        return _plan(_rule("entry", 0, group=_group(_cond(operator=op))))

    def test_unsupported_operator_blocks(self):
        r = check_readiness(compiled=True, plan=self._plan_custom_op())
        assert r.ready is False
        assert r.status == "blocked"

    def test_unsupported_operator_issue_code(self):
        r = check_readiness(compiled=True, plan=self._plan_custom_op())
        assert any(i.code == "unsupported_operator" for i in r.issues)

    def test_unsupported_operator_message_contains_op(self):
        r = check_readiness(compiled=True, plan=self._plan_custom_op("MY_OP"))
        issue = next(i for i in r.issues if i.code == "unsupported_operator")
        assert "MY_OP" in issue.message

    def test_standard_operators_all_accepted(self):
        for op in STANDARD_OPERATORS:
            r = check_readiness(compiled=True, plan=self._plan_custom_op(op))
            assert not any(i.code == "unsupported_operator" for i in r.issues), (
                f"Standard operator '{op}' was incorrectly flagged"
            )

    def test_custom_supported_operators_parameter(self):
        custom_ops = frozenset({"MY_OP", ">"})
        r = check_readiness(
            compiled=True,
            plan=self._plan_custom_op("MY_OP"),
            supported_operators=custom_ops,
        )
        assert not any(i.code == "unsupported_operator" for i in r.issues)

    def test_each_unsupported_op_one_issue_per_op(self):
        group = _group(_cond("ALPHA"), _cond("BETA"))
        plan = _plan(_rule("entry", 0, group=group))
        r = check_readiness(compiled=True, plan=plan)
        op_issues = [i for i in r.issues if i.code == "unsupported_operator"]
        op_names = {i.message.split("'")[1] for i in op_issues}
        assert "ALPHA" in op_names
        assert "BETA" in op_names


# ---------------------------------------------------------------------------
# Excessive nesting depth
# ---------------------------------------------------------------------------

class TestNestingDepth:
    def _deep_plan(self, depth: int) -> EvaluationPlan:
        """Build a plan with `depth` levels of nested groups."""
        inner: ConditionGroupPlanNode = _group(_cond(), group_id=f"group-{depth}")
        for d in range(depth - 1, 0, -1):
            inner = ConditionGroupPlanNode(
                group_id=f"group-{d}",
                operator="AND",
                nodes=(inner,),
                label=None,
            )
        return _plan(_rule("entry", 0, group=inner))

    def test_depth_within_threshold_no_issue(self):
        # _deep_plan(N) → max nesting depth N-1; N=6 → depth 5 = threshold → no warning
        r = check_readiness(
            compiled=True,
            plan=self._deep_plan(DEFAULT_MAX_NESTING_DEPTH + 1),
        )
        assert not any(i.code == "excessive_nesting_depth" for i in r.issues)

    def test_depth_exceeds_threshold_warning(self):
        # _deep_plan(N) → max nesting depth N-1; N=7 → depth 6 > threshold 5 → warning
        r = check_readiness(
            compiled=True,
            plan=self._deep_plan(DEFAULT_MAX_NESTING_DEPTH + 2),
        )
        assert any(i.code == "excessive_nesting_depth" for i in r.issues)

    def test_excessive_depth_is_warning_not_blocking(self):
        r = check_readiness(
            compiled=True,
            plan=self._deep_plan(DEFAULT_MAX_NESTING_DEPTH + 2),
        )
        issue = next(i for i in r.issues if i.code == "excessive_nesting_depth")
        assert issue.severity == "warning"

    def test_excessive_depth_gives_degraded_not_blocked(self):
        r = check_readiness(
            compiled=True,
            plan=self._deep_plan(DEFAULT_MAX_NESTING_DEPTH + 2),
        )
        assert r.ready is True
        assert r.status == "degraded"

    def test_custom_threshold_parameter(self):
        # _deep_plan(4) → max depth 3 > threshold 2
        r = check_readiness(
            compiled=True,
            plan=self._deep_plan(4),
            max_nesting_depth_threshold=2,
        )
        assert any(i.code == "excessive_nesting_depth" for i in r.issues)


# ---------------------------------------------------------------------------
# Issue ordering — blocking before warning
# ---------------------------------------------------------------------------

class TestIssueOrdering:
    def test_blocking_before_warning(self):
        plan = _plan(_rule("entry", 0, rule_id=None))  # missing rule_id → warning
        # unsupported operator → blocking
        bad_op_plan = _plan(_rule("entry", 0, group=_group(_cond("BAD")), rule_id=None))
        r = check_readiness(compiled=True, plan=bad_op_plan)
        severities = [i.severity for i in r.issues]
        # All blocking issues must appear before any warning issue
        last_blocking = max(
            (idx for idx, s in enumerate(severities) if s == "blocking"),
            default=-1,
        )
        first_warning = min(
            (idx for idx, s in enumerate(severities) if s == "warning"),
            default=len(severities),
        )
        assert last_blocking < first_warning

    def test_deterministic_same_plan_same_issues(self):
        plan = _simple_plan()
        r1 = check_readiness(compiled=True, plan=plan)
        r2 = check_readiness(compiled=True, plan=plan)
        assert r1.issues == r2.issues
        assert r1.status == r2.status

    def test_report_is_frozen(self):
        r = check_readiness(compiled=True, plan=_simple_plan())
        with pytest.raises(Exception):
            r.ready = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Summary correctness
# ---------------------------------------------------------------------------

class TestSummaryCounts:
    def test_blocking_count_correct(self):
        r = check_readiness(compiled=False, errors=("err1", "err2"))
        # not_compiled + 2 errors = 3 blocking
        assert r.summary.blocking_count == 3

    def test_warning_count_correct(self):
        plan = _plan(_rule("entry", 0, rule_id=None))  # 1 missing_rule_id warning
        r = check_readiness(compiled=True, plan=plan)
        assert r.summary.warning_count >= 1

    def test_info_count_zero_in_standard_checks(self):
        r = check_readiness(compiled=True, plan=_simple_plan())
        assert r.summary.info_count == 0


# ---------------------------------------------------------------------------
# Architecture boundary
# ---------------------------------------------------------------------------

class TestArchitectureBoundary:
    def _import_lines(self, module_name: str) -> list[str]:
        import importlib
        import inspect
        mod = importlib.import_module(module_name)
        return [
            line.strip()
            for line in inspect.getsource(mod).splitlines()
            if line.strip().startswith(("import ", "from "))
        ]

    def _assert_no_forbidden(self, module_name: str, forbidden: str) -> None:
        for line in self._import_lines(module_name):
            assert forbidden not in line, (
                f"Architecture violation in {module_name}: "
                f"'{forbidden}' found in import: {line!r}"
            )

    MODULES = [
        "backend.strategy_registry.evaluation_readiness",
        "backend.api.services.evaluation_readiness_service",
        "backend.api.routes.evaluation_readiness",
    ]

    def test_no_strategy_runtime_import(self):
        for mod in self.MODULES:
            self._assert_no_forbidden(mod, "strategy_runtime")

    def test_no_backtesting_import(self):
        for mod in self.MODULES:
            self._assert_no_forbidden(mod, "backtesting")

    def test_no_execution_import(self):
        for mod in self.MODULES:
            self._assert_no_forbidden(mod, "backend.execution")

    def test_no_forward_testing_import(self):
        for mod in self.MODULES:
            self._assert_no_forbidden(mod, "forward_testing")
