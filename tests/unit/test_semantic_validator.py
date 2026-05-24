"""
Unit tests for SemanticValidator — Phase 2O.1.

Covers:
- Valid semantics → valid=True, empty errors
- Invalid constant operand (non-numeric)
- Invalid price operand (unrecognised field)
- Invalid tool_output operand (no dot)
- Empty condition group (structural guard)
- Nested group validation (errors surfaced from inner groups)
- Mixed valid/invalid operands
- Empty entry/exit rules → valid
- Validation result repr
- Confirm: NO runtime evaluation in validator
"""
from __future__ import annotations

import pytest

from backend.strategy_registry.semantic_validator import (
    SemanticValidationResult,
    validate_semantics_structure,
)
from backend.strategy_registry.semantics import (
    Condition,
    ConditionGroup,
    EntryRule,
    ExitRule,
    OperandReference,
    StrategySemantics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _op(kind: str, ref: str) -> OperandReference:
    return OperandReference(kind=kind, ref=ref)


def _cond(left: OperandReference, right: OperandReference, op: str = ">") -> Condition:
    return Condition(left=left, operator=op, right=right)


def _group(*conditions, logical_op: str = "AND") -> ConditionGroup:
    return ConditionGroup(operator=logical_op, conditions=tuple(conditions))


def _entry(group: ConditionGroup) -> EntryRule:
    return EntryRule(condition_group=group)


def _exit(group: ConditionGroup) -> ExitRule:
    return ExitRule(condition_group=group)


def _semantics(entry_groups=(), exit_groups=()) -> StrategySemantics:
    return StrategySemantics(
        entry_rules=tuple(_entry(g) for g in entry_groups),
        exit_rules=tuple(_exit(g) for g in exit_groups),
    )


# ---------------------------------------------------------------------------
# Valid cases
# ---------------------------------------------------------------------------

class TestValidSemantics:
    def test_valid_tool_output_comparison(self):
        group = _group(
            _cond(_op("tool_output", "sma_fast.value"), _op("tool_output", "sma_slow.value"))
        )
        result = validate_semantics_structure(_semantics([group]))
        assert result.valid is True
        assert result.errors == []

    def test_valid_constant_comparison(self):
        group = _group(
            _cond(_op("tool_output", "rsi_14.value"), _op("constant", "30"), op="<")
        )
        result = validate_semantics_structure(_semantics([group]))
        assert result.valid is True

    def test_valid_price_close(self):
        group = _group(
            _cond(_op("price", "close"), _op("constant", "100"))
        )
        result = validate_semantics_structure(_semantics([group]))
        assert result.valid is True

    def test_valid_all_price_fields(self):
        for field in ("open", "high", "low", "close", "volume"):
            group = _group(_cond(_op("price", field), _op("constant", "1")))
            result = validate_semantics_structure(_semantics([group]))
            assert result.valid is True, f"Expected valid for price ref '{field}'"

    def test_valid_float_constant(self):
        group = _group(_cond(_op("constant", "1.5"), _op("constant", "2.0")))
        result = validate_semantics_structure(_semantics([group]))
        assert result.valid is True

    def test_valid_negative_constant(self):
        group = _group(_cond(_op("constant", "-5"), _op("constant", "0")))
        result = validate_semantics_structure(_semantics([group]))
        assert result.valid is True

    def test_empty_rules_valid(self):
        result = validate_semantics_structure(_semantics())
        assert result.valid is True
        assert result.errors == []

    def test_valid_nested_group(self):
        inner = _group(
            _cond(_op("tool_output", "sma_fast.value"), _op("tool_output", "sma_slow.value"))
        )
        outer = _group(
            inner,
            _cond(_op("price", "close"), _op("constant", "50")),
            logical_op="OR",
        )
        result = validate_semantics_structure(_semantics([outer]))
        assert result.valid is True

    def test_multiple_entry_exit_rules_all_valid(self):
        group = _group(
            _cond(_op("tool_output", "sma_fast.value"), _op("tool_output", "sma_slow.value"))
        )
        s = StrategySemantics(
            entry_rules=(EntryRule(condition_group=group), EntryRule(condition_group=group)),
            exit_rules=(ExitRule(condition_group=group), ExitRule(condition_group=group)),
        )
        result = validate_semantics_structure(s)
        assert result.valid is True


# ---------------------------------------------------------------------------
# Invalid operand — constant
# ---------------------------------------------------------------------------

class TestInvalidConstantOperand:
    def test_non_numeric_constant_left(self):
        group = _group(_cond(_op("constant", "abc"), _op("constant", "30")))
        result = validate_semantics_structure(_semantics([group]))
        assert result.valid is False
        assert any("abc" in e for e in result.errors)

    def test_non_numeric_constant_right(self):
        group = _group(_cond(_op("tool_output", "sma.value"), _op("constant", "not_a_number")))
        result = validate_semantics_structure(_semantics([group]))
        assert result.valid is False
        assert any("not_a_number" in e for e in result.errors)

    def test_empty_string_constant_is_rejected_by_model(self):
        with pytest.raises(Exception):
            OperandReference(kind="constant", ref="")


# ---------------------------------------------------------------------------
# Invalid operand — price
# ---------------------------------------------------------------------------

class TestInvalidPriceOperand:
    def test_unknown_price_ref(self):
        group = _group(_cond(_op("price", "bid"), _op("constant", "100")))
        result = validate_semantics_structure(_semantics([group]))
        assert result.valid is False
        assert any("bid" in e for e in result.errors)

    def test_uppercase_price_ref_not_recognised(self):
        group = _group(_cond(_op("price", "Close"), _op("constant", "100")))
        result = validate_semantics_structure(_semantics([group]))
        assert result.valid is False


# ---------------------------------------------------------------------------
# Invalid operand — tool_output
# ---------------------------------------------------------------------------

class TestInvalidToolOutputOperand:
    def test_missing_dot(self):
        group = _group(_cond(_op("tool_output", "sma_fast"), _op("constant", "1")))
        result = validate_semantics_structure(_semantics([group]))
        assert result.valid is False
        assert any("sma_fast" in e for e in result.errors)

    def test_valid_dotted_ref(self):
        group = _group(_cond(_op("tool_output", "sma_fast.value"), _op("constant", "1")))
        result = validate_semantics_structure(_semantics([group]))
        assert result.valid is True


# ---------------------------------------------------------------------------
# Nested group errors surfaced
# ---------------------------------------------------------------------------

class TestNestedGroupValidation:
    def test_error_in_inner_group_surfaced(self):
        bad_cond = _cond(_op("constant", "abc"), _op("constant", "1"))
        inner = _group(bad_cond)
        outer = _group(inner, logical_op="OR")
        result = validate_semantics_structure(_semantics([outer]))
        assert result.valid is False
        assert any("abc" in e for e in result.errors)

    def test_error_path_includes_nesting(self):
        bad_cond = _cond(_op("constant", "xyz"), _op("constant", "1"))
        inner = _group(bad_cond)
        outer = _group(inner)
        result = validate_semantics_structure(_semantics([outer]))
        assert result.valid is False
        # Path should reference the nested conditions position
        assert any("conditions[0]" in e for e in result.errors)

    def test_multiple_errors_collected(self):
        bad1 = _cond(_op("constant", "abc"), _op("constant", "1"))
        bad2 = _cond(_op("price", "bid"), _op("constant", "1"))
        group = _group(bad1, bad2)
        result = validate_semantics_structure(_semantics([group]))
        assert result.valid is False
        assert len(result.errors) >= 2


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

class TestSemanticValidationResult:
    def test_valid_result(self):
        r = SemanticValidationResult([])
        assert r.valid is True
        assert r.errors == []

    def test_invalid_result(self):
        r = SemanticValidationResult(["some error"])
        assert r.valid is False
        assert len(r.errors) == 1

    def test_repr(self):
        r = SemanticValidationResult([])
        assert "valid=True" in repr(r)

    def test_multiple_errors(self):
        r = SemanticValidationResult(["err1", "err2", "err3"])
        assert r.valid is False
        assert len(r.errors) == 3

    def test_no_runtime_evaluation(self):
        """Validator must not import from runtime, backtesting, or execution modules."""
        import inspect
        import backend.strategy_registry.semantic_validator as mod
        source = inspect.getsource(mod)
        # Check that forbidden modules are NOT imported (not merely mentioned in comments)
        forbidden_imports = [
            "import strategy_runtime",
            "from backend.strategy_runtime",
            "import backtesting",
            "from backend.backtesting",
            "import execution",
            "from backend.execution",
            "compute_sma",
            "compute_ema",
            "compute_rsi",
            "OHLCVService",
            "YahooFinanceAdapter",
        ]
        for term in forbidden_imports:
            assert term not in source, (
                f"semantic_validator must not import or reference '{term}' — "
                "it must remain structural-only"
            )
