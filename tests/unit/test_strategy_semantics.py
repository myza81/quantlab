"""
Unit tests for Strategy Semantic domain models — Phase 2O.1.

Covers:
- OperandReference validation
- Condition construction and immutability
- ConditionGroup construction, nesting, empty-guard
- EntryRule / ExitRule construction
- StrategySemantics construction
- Frozen immutability across all models
- Deterministic serialisation (model_dump / model_dump_json)
- Round-trip: model_dump → model_validate
- Invalid operator / operand values rejected
"""
from __future__ import annotations

import json

import pytest

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _op(kind: str, ref: str) -> OperandReference:
    return OperandReference(kind=kind, ref=ref)


def _cond(left: OperandReference, op: str, right: OperandReference) -> Condition:
    return Condition(left=left, operator=op, right=right)


def _simple_group(op: str = "AND") -> ConditionGroup:
    return ConditionGroup(
        operator=op,
        conditions=(
            _cond(_op("tool_output", "sma_fast.value"), ">", _op("tool_output", "sma_slow.value")),
        ),
    )


def _simple_semantics() -> StrategySemantics:
    group = _simple_group("AND")
    return StrategySemantics(
        entry_rules=(EntryRule(condition_group=group),),
        exit_rules=(ExitRule(condition_group=group),),
    )


# ---------------------------------------------------------------------------
# OperandReference
# ---------------------------------------------------------------------------

class TestOperandReference:
    def test_tool_output(self):
        ref = _op("tool_output", "sma_fast.value")
        assert ref.kind == OperandKind.TOOL_OUTPUT
        assert ref.ref == "sma_fast.value"

    def test_constant(self):
        ref = _op("constant", "30")
        assert ref.kind == OperandKind.CONSTANT
        assert ref.ref == "30"

    def test_price(self):
        ref = _op("price", "close")
        assert ref.kind == OperandKind.PRICE
        assert ref.ref == "close"

    def test_ref_stripped(self):
        ref = OperandReference(kind="constant", ref="  42  ")
        assert ref.ref == "42"

    def test_empty_ref_rejected(self):
        with pytest.raises(Exception):
            OperandReference(kind="constant", ref="   ")

    def test_invalid_kind_rejected(self):
        with pytest.raises(Exception):
            OperandReference(kind="unknown_kind", ref="x")

    def test_extra_fields_forbidden(self):
        with pytest.raises(Exception):
            OperandReference(kind="constant", ref="1", extra_field="oops")

    def test_frozen(self):
        ref = _op("constant", "30")
        with pytest.raises(Exception):
            ref.ref = "99"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Condition
# ---------------------------------------------------------------------------

class TestCondition:
    def test_basic_condition(self):
        cond = _cond(
            _op("tool_output", "sma_fast.value"),
            ">",
            _op("tool_output", "sma_slow.value"),
        )
        assert cond.operator == ConditionOperator.GT
        assert cond.left.ref == "sma_fast.value"
        assert cond.right.ref == "sma_slow.value"

    def test_all_operators(self):
        ops = [">", "<", ">=", "<=", "==", "!=", "crosses_above", "crosses_below"]
        left = _op("constant", "1")
        right = _op("constant", "2")
        for op in ops:
            cond = _cond(left, op, right)
            assert cond.operator == op

    def test_invalid_operator_rejected(self):
        with pytest.raises(Exception):
            _cond(_op("constant", "1"), "INVALID_OP", _op("constant", "2"))

    def test_label_optional(self):
        cond = _cond(_op("constant", "1"), ">", _op("constant", "2"))
        assert cond.label is None

    def test_label_set(self):
        cond = Condition(
            left=_op("constant", "1"),
            operator=">",
            right=_op("constant", "2"),
            label="price above threshold",
        )
        assert cond.label == "price above threshold"

    def test_extra_fields_forbidden(self):
        with pytest.raises(Exception):
            Condition(
                left=_op("constant", "1"),
                operator=">",
                right=_op("constant", "2"),
                extra="oops",
            )

    def test_frozen(self):
        cond = _cond(_op("constant", "1"), ">", _op("constant", "2"))
        with pytest.raises(Exception):
            cond.label = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ConditionGroup
# ---------------------------------------------------------------------------

class TestConditionGroup:
    def test_and_group(self):
        g = _simple_group("AND")
        assert g.operator == LogicalOperator.AND
        assert len(g.conditions) == 1

    def test_or_group(self):
        g = _simple_group("OR")
        assert g.operator == LogicalOperator.OR

    def test_multiple_conditions(self):
        cond1 = _cond(_op("tool_output", "sma_fast.value"), ">", _op("tool_output", "sma_slow.value"))
        cond2 = _cond(_op("tool_output", "rsi_14.value"), "<", _op("constant", "30"))
        g = ConditionGroup(operator="AND", conditions=(cond1, cond2))
        assert len(g.conditions) == 2

    def test_empty_conditions_rejected(self):
        with pytest.raises(Exception):
            ConditionGroup(operator="AND", conditions=())

    def test_nested_group(self):
        inner = _simple_group("AND")
        outer = ConditionGroup(
            operator="OR",
            conditions=(
                _cond(_op("price", "close"), ">", _op("constant", "100")),
                inner,
            ),
        )
        assert len(outer.conditions) == 2
        assert isinstance(outer.conditions[1], ConditionGroup)

    def test_deeply_nested_group(self):
        level3 = _simple_group("AND")
        level2 = ConditionGroup(
            operator="OR",
            conditions=(level3, _cond(_op("constant", "1"), "==", _op("constant", "1"))),
        )
        level1 = ConditionGroup(operator="AND", conditions=(level2,))
        assert isinstance(level1.conditions[0], ConditionGroup)
        assert isinstance(level1.conditions[0].conditions[0], ConditionGroup)

    def test_label_optional(self):
        g = _simple_group("AND")
        assert g.label is None

    def test_label_set(self):
        g = ConditionGroup(operator="AND", conditions=(_simple_group("AND"),), label="main entry")
        assert g.label == "main entry"

    def test_invalid_operator_rejected(self):
        with pytest.raises(Exception):
            ConditionGroup(operator="XOR", conditions=(_simple_group("AND"),))

    def test_frozen(self):
        g = _simple_group("AND")
        with pytest.raises(Exception):
            g.operator = LogicalOperator.OR  # type: ignore[misc]

    def test_extra_fields_forbidden(self):
        with pytest.raises(Exception):
            ConditionGroup(operator="AND", conditions=(_simple_group("AND"),), extra="oops")


# ---------------------------------------------------------------------------
# EntryRule / ExitRule
# ---------------------------------------------------------------------------

class TestEntryExitRules:
    def test_entry_rule(self):
        group = _simple_group("AND")
        rule = EntryRule(condition_group=group)
        assert rule.condition_group is group
        assert rule.label is None
        assert rule.notes is None

    def test_exit_rule(self):
        group = _simple_group("OR")
        rule = ExitRule(condition_group=group, label="stop loss", notes="2% below entry")
        assert rule.label == "stop loss"
        assert rule.notes == "2% below entry"

    def test_entry_rule_frozen(self):
        rule = EntryRule(condition_group=_simple_group("AND"))
        with pytest.raises(Exception):
            rule.label = "mutated"  # type: ignore[misc]

    def test_exit_rule_frozen(self):
        rule = ExitRule(condition_group=_simple_group("AND"))
        with pytest.raises(Exception):
            rule.notes = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# StrategySemantics
# ---------------------------------------------------------------------------

class TestStrategySemantics:
    def test_basic_semantics(self):
        s = _simple_semantics()
        assert len(s.entry_rules) == 1
        assert len(s.exit_rules) == 1
        assert s.metadata.version == "1.0"

    def test_empty_rules_allowed(self):
        s = StrategySemantics(entry_rules=(), exit_rules=())
        assert len(s.entry_rules) == 0
        assert len(s.exit_rules) == 0

    def test_multiple_rules(self):
        group = _simple_group("AND")
        s = StrategySemantics(
            entry_rules=(EntryRule(condition_group=group), EntryRule(condition_group=group)),
            exit_rules=(ExitRule(condition_group=group),),
        )
        assert len(s.entry_rules) == 2

    def test_metadata_defaults(self):
        s = _simple_semantics()
        assert s.metadata.version == "1.0"
        assert s.metadata.author is None
        assert s.metadata.description is None

    def test_custom_metadata(self):
        s = StrategySemantics(
            entry_rules=(),
            exit_rules=(),
            metadata=SemanticsMetadata(version="2.0", author="test", description="desc"),
        )
        assert s.metadata.version == "2.0"
        assert s.metadata.author == "test"

    def test_frozen(self):
        s = _simple_semantics()
        with pytest.raises(Exception):
            s.entry_rules = ()  # type: ignore[misc]

    def test_extra_fields_forbidden(self):
        with pytest.raises(Exception):
            StrategySemantics(entry_rules=(), exit_rules=(), extra="oops")


# ---------------------------------------------------------------------------
# Serialisation & round-trip
# ---------------------------------------------------------------------------

class TestSerialisation:
    def test_model_dump_is_dict(self):
        s = _simple_semantics()
        d = s.model_dump()
        assert isinstance(d, dict)
        assert "entry_rules" in d
        assert "exit_rules" in d
        assert "metadata" in d

    def test_model_dump_json_is_valid_json(self):
        s = _simple_semantics()
        raw = s.model_dump_json()
        parsed = json.loads(raw)
        assert "entry_rules" in parsed

    def test_round_trip(self):
        s = _simple_semantics()
        rebuilt = StrategySemantics.model_validate(s.model_dump())
        assert rebuilt.model_dump_json() == s.model_dump_json()

    def test_deterministic_serialisation(self):
        """Same semantic structure always produces identical JSON."""
        group = _simple_group("AND")
        s1 = StrategySemantics(entry_rules=(EntryRule(condition_group=group),), exit_rules=())
        s2 = StrategySemantics(entry_rules=(EntryRule(condition_group=group),), exit_rules=())
        assert s1.model_dump_json() == s2.model_dump_json()

    def test_nested_group_round_trip(self):
        inner = _simple_group("AND")
        outer = ConditionGroup(
            operator="OR",
            conditions=(inner, _cond(_op("price", "close"), ">", _op("constant", "50"))),
        )
        group_dict = outer.model_dump()
        rebuilt = ConditionGroup.model_validate(group_dict)
        assert rebuilt.model_dump_json() == outer.model_dump_json()

    def test_operator_values_in_json(self):
        s = _simple_semantics()
        d = s.model_dump()
        entry_group = d["entry_rules"][0]["condition_group"]
        assert entry_group["operator"] == "AND"
        condition = entry_group["conditions"][0]
        assert condition["operator"] == ">"
