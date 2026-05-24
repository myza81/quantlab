"""
Phase 2O.5 — Semantic Binding Validator tests.

Covers:
- valid tool_output ref fully resolved (instance + output)
- invalid dotted format → error diagnostic
- missing instance_id in toolset → error diagnostic
- unknown output_name in registry → error diagnostic
- no registry provided → info diagnostic, not an error
- tool_id not found in registry → warning diagnostic, not an error
- valid=True when only warnings/info (no errors)
- valid=False when any error diagnostic present
- price fields collected in summary
- constants collected in summary
- multiple refs across entry + exit rules
- deduplication and sorting in summary tuples
- empty toolset and no tool_output refs → valid=True
- nested condition group refs collected
- architecture boundary: no runtime imports
"""
from __future__ import annotations

import importlib
import inspect

import pytest

from backend.strategy_registry.semantic_binding_validator import (
    BindingDiagnostic,
    BindingValidationResult,
    DependencySummary,
    validate_semantic_bindings,
)
from backend.strategy_registry.semantics import (
    Condition,
    ConditionGroup,
    ConditionOperator,
    EntryRule,
    ExitRule,
    LogicalOperator,
    OperandKind,
    OperandReference,
    SemanticsMetadata,
    StrategySemantics,
)
from backend.tools import create_default_registry
from backend.tools.configuration import ToolConfiguration
from backend.tools.toolset import StrategyToolSet

# ---------------------------------------------------------------------------
# Semantic builder helpers
# ---------------------------------------------------------------------------

def _tool(ref: str) -> OperandReference:
    return OperandReference(kind=OperandKind.TOOL_OUTPUT, ref=ref)

def _price(ref: str = "close") -> OperandReference:
    return OperandReference(kind=OperandKind.PRICE, ref=ref)

def _const(ref: str = "30") -> OperandReference:
    return OperandReference(kind=OperandKind.CONSTANT, ref=ref)

def _cond(left: OperandReference, right: OperandReference) -> Condition:
    return Condition(left=left, operator=ConditionOperator.GT, right=right)

def _group(*conds: Condition | ConditionGroup) -> ConditionGroup:
    return ConditionGroup(operator=LogicalOperator.AND, conditions=list(conds))

def _semantics(
    entry_groups: list[ConditionGroup] | None = None,
    exit_groups:  list[ConditionGroup] | None = None,
) -> StrategySemantics:
    entry_rules = [EntryRule(condition_group=g) for g in (entry_groups or [])]
    exit_rules  = [ExitRule(condition_group=g)  for g in (exit_groups  or [])]
    return StrategySemantics(
        entry_rules=entry_rules,
        exit_rules=exit_rules,
        metadata=SemanticsMetadata(version="1.0"),
    )

# ---------------------------------------------------------------------------
# Toolset builders
# ---------------------------------------------------------------------------

def _tool_config(instance_id: str, tool_id: str = "sma") -> ToolConfiguration:
    return ToolConfiguration(
        instance_id=instance_id,
        tool_id=tool_id,
        parameters={"period": 20},
    )

def _toolset(*configs: ToolConfiguration) -> StrategyToolSet:
    return StrategyToolSet(toolset_id="test", tools=configs)

# ---------------------------------------------------------------------------
# Tests — resolution paths
# ---------------------------------------------------------------------------

class TestResolutionPaths:
    def test_valid_ref_fully_resolved(self):
        registry = create_default_registry()
        toolset = _toolset(_tool_config("sma_fast", "sma"))
        sem = _semantics(entry_groups=[_group(_cond(_tool("sma_fast.sma"), _const()))])

        result = validate_semantic_bindings(sem, toolset, registry)

        assert result.valid is True
        assert result.summary.resolved_tool_outputs == ("sma_fast.sma",)
        assert result.summary.unresolved_tool_outputs == ()
        assert result.summary.warned_tool_outputs == ()

    def test_invalid_format_no_dot(self):
        toolset = _toolset()
        sem = _semantics(entry_groups=[_group(_cond(_tool("badref"), _const()))])

        result = validate_semantic_bindings(sem, toolset)

        assert result.valid is False
        assert any(d.code == "invalid_output_format" for d in result.diagnostics)
        assert "badref" in result.summary.unresolved_tool_outputs

    def test_missing_instance_id(self):
        toolset = _toolset()
        sem = _semantics(entry_groups=[_group(_cond(_tool("ghost.value"), _const()))])

        result = validate_semantic_bindings(sem, toolset)

        assert result.valid is False
        codes = [d.code for d in result.diagnostics]
        assert "missing_tool_instance" in codes
        assert "ghost.value" in result.summary.unresolved_tool_outputs

    def test_missing_instance_message_includes_available(self):
        toolset = _toolset(_tool_config("sma_fast"))
        sem = _semantics(entry_groups=[_group(_cond(_tool("ghost.value"), _const()))])

        result = validate_semantic_bindings(sem, toolset)

        diag = next(d for d in result.diagnostics if d.code == "missing_tool_instance")
        assert "sma_fast" in diag.message

    def test_unknown_output_name_error(self):
        registry = create_default_registry()
        toolset = _toolset(_tool_config("sma_fast", "sma"))
        sem = _semantics(entry_groups=[_group(_cond(_tool("sma_fast.nonexistent"), _const()))])

        result = validate_semantic_bindings(sem, toolset, registry)

        assert result.valid is False
        codes = [d.code for d in result.diagnostics]
        assert "unknown_output_name" in codes
        assert "sma_fast.nonexistent" in result.summary.unresolved_tool_outputs

    def test_unknown_output_message_includes_known(self):
        registry = create_default_registry()
        toolset = _toolset(_tool_config("sma_fast", "sma"))
        sem = _semantics(entry_groups=[_group(_cond(_tool("sma_fast.bad"), _const()))])

        result = validate_semantic_bindings(sem, toolset, registry)

        diag = next(d for d in result.diagnostics if d.code == "unknown_output_name")
        assert "sma" in diag.message

    def test_no_registry_yields_info_not_error(self):
        toolset = _toolset(_tool_config("sma_fast", "sma"))
        sem = _semantics(entry_groups=[_group(_cond(_tool("sma_fast.sma"), _const()))])

        result = validate_semantic_bindings(sem, toolset, registry=None)

        assert result.valid is True
        assert any(d.code == "registry_unavailable" for d in result.diagnostics)
        assert any(d.severity == "info" for d in result.diagnostics)
        assert "sma_fast.sma" in result.summary.warned_tool_outputs

    def test_tool_not_in_registry_yields_warning(self):
        from backend.tools.registry import ToolRegistry
        empty_registry = ToolRegistry()
        toolset = _toolset(_tool_config("sma_fast", "sma"))
        sem = _semantics(entry_groups=[_group(_cond(_tool("sma_fast.sma"), _const()))])

        result = validate_semantic_bindings(sem, toolset, empty_registry)

        assert result.valid is True
        assert any(d.code == "tool_not_in_registry" for d in result.diagnostics)
        assert any(d.severity == "warning" for d in result.diagnostics)
        assert "sma_fast.sma" in result.summary.warned_tool_outputs

# ---------------------------------------------------------------------------
# Tests — valid/invalid flag logic
# ---------------------------------------------------------------------------

class TestValidFlag:
    def test_valid_true_when_all_resolved(self):
        registry = create_default_registry()
        toolset = _toolset(_tool_config("sma_fast", "sma"))
        sem = _semantics(entry_groups=[_group(_cond(_tool("sma_fast.sma"), _const()))])
        result = validate_semantic_bindings(sem, toolset, registry)
        assert result.valid is True

    def test_valid_false_on_error(self):
        toolset = _toolset()
        sem = _semantics(entry_groups=[_group(_cond(_tool("missing.out"), _const()))])
        result = validate_semantic_bindings(sem, toolset)
        assert result.valid is False

    def test_valid_true_warnings_do_not_fail(self):
        from backend.tools.registry import ToolRegistry
        toolset = _toolset(_tool_config("sma_fast", "sma"))
        sem = _semantics(entry_groups=[_group(_cond(_tool("sma_fast.sma"), _const()))])
        result = validate_semantic_bindings(sem, toolset, ToolRegistry())
        assert result.valid is True

    def test_valid_true_info_does_not_fail(self):
        toolset = _toolset(_tool_config("sma_fast", "sma"))
        sem = _semantics(entry_groups=[_group(_cond(_tool("sma_fast.sma"), _const()))])
        result = validate_semantic_bindings(sem, toolset, registry=None)
        assert result.valid is True

    def test_valid_true_no_tool_output_refs(self):
        toolset = _toolset()
        sem = _semantics(entry_groups=[_group(_cond(_price(), _const()))])
        result = validate_semantic_bindings(sem, toolset)
        assert result.valid is True
        assert result.summary.resolved_tool_outputs == ()
        assert result.summary.unresolved_tool_outputs == ()

# ---------------------------------------------------------------------------
# Tests — dependency summary fields
# ---------------------------------------------------------------------------

class TestDependencySummary:
    def test_price_fields_collected(self):
        toolset = _toolset()
        sem = _semantics(entry_groups=[_group(_cond(_price("open"), _price("close")))])
        result = validate_semantic_bindings(sem, toolset)
        assert set(result.summary.price_fields) == {"open", "close"}

    def test_constants_collected(self):
        toolset = _toolset()
        sem = _semantics(entry_groups=[_group(_cond(_price(), _const("42")))])
        result = validate_semantic_bindings(sem, toolset)
        assert "42" in result.summary.constants

    def test_deduplication_tool_outputs(self):
        registry = create_default_registry()
        toolset = _toolset(_tool_config("sma_fast", "sma"))
        sem = _semantics(
            entry_groups=[_group(_cond(_tool("sma_fast.sma"), _tool("sma_fast.sma")))],
        )
        result = validate_semantic_bindings(sem, toolset, registry)
        assert result.summary.resolved_tool_outputs.count("sma_fast.sma") == 1

    def test_summary_tuples_sorted(self):
        toolset = _toolset()
        sem = _semantics(entry_groups=[_group(
            _cond(_price("close"), _const("50")),
            _cond(_price("open"), _const("10")),
        )])
        result = validate_semantic_bindings(sem, toolset)
        assert result.summary.price_fields == tuple(sorted(result.summary.price_fields))
        assert result.summary.constants == tuple(sorted(result.summary.constants))

    def test_mixed_refs_entry_and_exit(self):
        registry = create_default_registry()
        toolset = _toolset(_tool_config("sma_fast", "sma"), _tool_config("sma_slow", "sma"))
        sem = _semantics(
            entry_groups=[_group(_cond(_tool("sma_fast.sma"), _const()))],
            exit_groups=[_group(_cond(_tool("sma_slow.sma"), _price()))],
        )
        result = validate_semantic_bindings(sem, toolset, registry)
        assert result.valid is True
        assert set(result.summary.resolved_tool_outputs) == {"sma_fast.sma", "sma_slow.sma"}

# ---------------------------------------------------------------------------
# Tests — nested groups
# ---------------------------------------------------------------------------

class TestNestedGroups:
    def test_refs_in_nested_group_collected(self):
        registry = create_default_registry()
        toolset = _toolset(_tool_config("sma_fast", "sma"))
        nested = _group(_cond(_tool("sma_fast.sma"), _const()))
        outer  = ConditionGroup(
            operator=LogicalOperator.AND,
            conditions=[_cond(_price(), _const()), nested],
        )
        sem = _semantics(entry_groups=[outer])
        result = validate_semantic_bindings(sem, toolset, registry)
        assert "sma_fast.sma" in result.summary.resolved_tool_outputs

    def test_deep_nested_error_collected(self):
        toolset = _toolset()
        level3 = _group(_cond(_tool("ghost.value"), _const()))
        level2 = ConditionGroup(operator=LogicalOperator.OR, conditions=[level3])
        level1 = ConditionGroup(operator=LogicalOperator.AND, conditions=[level2])
        sem = _semantics(entry_groups=[level1])
        result = validate_semantic_bindings(sem, toolset)
        assert result.valid is False
        assert "ghost.value" in result.summary.unresolved_tool_outputs

# ---------------------------------------------------------------------------
# Tests — empty semantics
# ---------------------------------------------------------------------------

class TestEmptySemantics:
    def test_no_rules_valid(self):
        toolset = _toolset()
        sem = _semantics()
        result = validate_semantic_bindings(sem, toolset)
        assert result.valid is True
        assert result.diagnostics == ()
        assert result.summary.resolved_tool_outputs == ()
        assert result.summary.unresolved_tool_outputs == ()

# ---------------------------------------------------------------------------
# Tests — architecture boundary
# ---------------------------------------------------------------------------

class TestArchitectureBoundary:
    def _import_lines(self) -> list[str]:
        import backend.strategy_registry.semantic_binding_validator as mod
        return [
            line.strip()
            for line in inspect.getsource(mod).splitlines()
            if line.strip().startswith(("import ", "from "))
        ]

    def test_no_strategy_runtime_import(self):
        for line in self._import_lines():
            assert "strategy_runtime" not in line

    def test_no_backtesting_import(self):
        for line in self._import_lines():
            assert "backtesting" not in line

    def test_no_execution_import(self):
        for line in self._import_lines():
            assert "backend.execution" not in line

    def test_no_forward_testing_import(self):
        for line in self._import_lines():
            assert "forward_testing" not in line
