"""
Phase 2O.3 — Semantic Identity tests.

Covers:
- generate_id() format
- inject_ids() fills missing IDs across the full tree
- inject_ids() preserves existing IDs (idempotency)
- ID stability across repeated inject_ids() calls
- Reorder stability — IDs follow data, not array index
- Nested group injection
- Legacy semantics migration (no IDs → IDs injected)
- validate_semantic_identity_integrity() — unique IDs pass
- validate_semantic_identity_integrity() — duplicate condition_id caught
- validate_semantic_identity_integrity() — duplicate group_id caught
- validate_semantic_identity_integrity() — duplicate rule_id caught
- validate_semantic_identity_integrity() — cross-rule_type duplicate rule_id caught
- None IDs skipped (no false positives for un-injected legacy trees)
- Backward compatibility — semantics without IDs load and validate structurally
"""
import uuid

import pytest

from backend.strategy_registry.semantic_identity import generate_id, inject_ids
from backend.strategy_registry.semantic_validator import (
    validate_semantic_identity_integrity,
    validate_semantics_structure,
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
    StrategySemantics,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _price(ref: str = "close") -> OperandReference:
    return OperandReference(kind=OperandKind.PRICE, ref=ref)

def _const(ref: str = "30") -> OperandReference:
    return OperandReference(kind=OperandKind.CONSTANT, ref=ref)

def _tool(ref: str = "sma.value") -> OperandReference:
    return OperandReference(kind=OperandKind.TOOL_OUTPUT, ref=ref)


def _bare_condition(**kwargs) -> Condition:
    """Condition with no condition_id."""
    return Condition(left=_price(), operator=ConditionOperator.GT, right=_const(), **kwargs)


def _bare_group(*conditions, **kwargs) -> ConditionGroup:
    """ConditionGroup with no group_id."""
    conds = conditions or (_bare_condition(),)
    return ConditionGroup(operator=LogicalOperator.AND, conditions=tuple(conds), **kwargs)


def _bare_entry(*conditions, **kwargs) -> EntryRule:
    group = _bare_group(*conditions)
    return EntryRule(condition_group=group, **kwargs)


def _bare_exit(*conditions, **kwargs) -> ExitRule:
    group = _bare_group(*conditions)
    return ExitRule(condition_group=group, **kwargs)


def _bare_semantics(entry_count: int = 1, exit_count: int = 1) -> StrategySemantics:
    return StrategySemantics(
        entry_rules=tuple(_bare_entry() for _ in range(entry_count)),
        exit_rules=tuple(_bare_exit() for _ in range(exit_count)),
    )


# ---------------------------------------------------------------------------
# generate_id
# ---------------------------------------------------------------------------

class TestGenerateId:
    def test_returns_valid_uuid4(self):
        id_ = generate_id()
        parsed = uuid.UUID(id_, version=4)
        assert str(parsed) == id_

    def test_unique_on_each_call(self):
        ids = {generate_id() for _ in range(100)}
        assert len(ids) == 100


# ---------------------------------------------------------------------------
# inject_ids — basic injection
# ---------------------------------------------------------------------------

class TestInjectIds:
    def test_rule_ids_injected(self):
        s = _bare_semantics()
        result = inject_ids(s)
        assert result.entry_rules[0].rule_id is not None
        assert result.exit_rules[0].rule_id is not None

    def test_group_ids_injected(self):
        s = _bare_semantics()
        result = inject_ids(s)
        assert result.entry_rules[0].condition_group.group_id is not None

    def test_condition_ids_injected(self):
        s = _bare_semantics()
        result = inject_ids(s)
        cond = result.entry_rules[0].condition_group.conditions[0]
        assert isinstance(cond, Condition)
        assert cond.condition_id is not None

    def test_all_ids_are_valid_uuids(self):
        s = _bare_semantics(entry_count=2, exit_count=2)
        result = inject_ids(s)
        for rule in (*result.entry_rules, *result.exit_rules):
            uuid.UUID(rule.rule_id, version=4)
            grp = rule.condition_group
            uuid.UUID(grp.group_id, version=4)
            for node in grp.conditions:
                if isinstance(node, Condition):
                    uuid.UUID(node.condition_id, version=4)

    def test_multiple_rules_get_distinct_ids(self):
        s = _bare_semantics(entry_count=3, exit_count=2)
        result = inject_ids(s)
        rule_ids = [r.rule_id for r in (*result.entry_rules, *result.exit_rules)]
        assert len(rule_ids) == len(set(rule_ids))

    def test_multiple_conditions_get_distinct_ids(self):
        c1 = _bare_condition()
        c2 = _bare_condition()
        group = _bare_group(c1, c2)
        rule = EntryRule(condition_group=group)
        s = StrategySemantics(entry_rules=(rule,), exit_rules=())
        result = inject_ids(s)
        conds = result.entry_rules[0].condition_group.conditions
        ids = [c.condition_id for c in conds]
        assert ids[0] != ids[1]

    def test_empty_rules_are_fine(self):
        s = StrategySemantics(entry_rules=(), exit_rules=())
        result = inject_ids(s)
        assert result.entry_rules == ()
        assert result.exit_rules == ()


# ---------------------------------------------------------------------------
# inject_ids — ID preservation (idempotency)
# ---------------------------------------------------------------------------

class TestInjectIdsPreservation:
    def test_existing_rule_id_preserved(self):
        existing_id = generate_id()
        rule = EntryRule(rule_id=existing_id, condition_group=_bare_group())
        s = StrategySemantics(entry_rules=(rule,), exit_rules=())
        result = inject_ids(s)
        assert result.entry_rules[0].rule_id == existing_id

    def test_existing_group_id_preserved(self):
        existing_id = generate_id()
        group = ConditionGroup(
            group_id=existing_id,
            operator=LogicalOperator.AND,
            conditions=(_bare_condition(),),
        )
        rule = EntryRule(condition_group=group)
        s = StrategySemantics(entry_rules=(rule,), exit_rules=())
        result = inject_ids(s)
        assert result.entry_rules[0].condition_group.group_id == existing_id

    def test_existing_condition_id_preserved(self):
        existing_id = generate_id()
        cond = Condition(
            condition_id=existing_id,
            left=_price(),
            operator=ConditionOperator.GT,
            right=_const(),
        )
        s = StrategySemantics(
            entry_rules=(EntryRule(condition_group=_bare_group(cond)),),
            exit_rules=(),
        )
        result = inject_ids(s)
        assert result.entry_rules[0].condition_group.conditions[0].condition_id == existing_id

    def test_idempotent_on_fully_injected_semantics(self):
        s = inject_ids(_bare_semantics())
        s2 = inject_ids(s)
        assert s2 == s

    def test_partial_ids_respected(self):
        """One rule has ID, sibling does not — only missing IDs are filled."""
        fixed_id = generate_id()
        r1 = EntryRule(rule_id=fixed_id, condition_group=_bare_group())
        r2 = _bare_entry()
        s = StrategySemantics(entry_rules=(r1, r2), exit_rules=())
        result = inject_ids(s)
        assert result.entry_rules[0].rule_id == fixed_id
        assert result.entry_rules[1].rule_id is not None
        assert result.entry_rules[1].rule_id != fixed_id


# ---------------------------------------------------------------------------
# inject_ids — nested groups
# ---------------------------------------------------------------------------

class TestInjectIdsNested:
    def test_nested_group_ids_injected(self):
        inner = _bare_group(_bare_condition())
        outer = ConditionGroup(
            operator=LogicalOperator.OR,
            conditions=(inner, _bare_condition()),
        )
        rule = EntryRule(condition_group=outer)
        s = StrategySemantics(entry_rules=(rule,), exit_rules=())
        result = inject_ids(s)
        outer_r = result.entry_rules[0].condition_group
        assert outer_r.group_id is not None
        inner_node = outer_r.conditions[0]
        assert isinstance(inner_node, ConditionGroup)
        assert inner_node.group_id is not None
        assert outer_r.group_id != inner_node.group_id

    def test_deeply_nested_condition_ids_injected(self):
        inner = _bare_group(_bare_condition())
        outer = ConditionGroup(
            operator=LogicalOperator.AND,
            conditions=(inner,),
        )
        rule = EntryRule(condition_group=outer)
        s = StrategySemantics(entry_rules=(rule,), exit_rules=())
        result = inject_ids(s)
        inner_group = result.entry_rules[0].condition_group.conditions[0]
        assert isinstance(inner_group, ConditionGroup)
        inner_cond = inner_group.conditions[0]
        assert isinstance(inner_cond, Condition)
        assert inner_cond.condition_id is not None


# ---------------------------------------------------------------------------
# inject_ids — reorder stability
# ---------------------------------------------------------------------------

class TestReorderStability:
    def test_ids_follow_data_not_index(self):
        """After inject then reorder via model_dump manipulation, IDs stay with their data."""
        c1 = _bare_condition()
        c2 = Condition(left=_tool(), operator=ConditionOperator.LT, right=_const("50"))
        group = _bare_group(c1, c2)
        rule = EntryRule(condition_group=group)
        s = StrategySemantics(entry_rules=(rule,), exit_rules=())

        injected = inject_ids(s)
        cond_a = injected.entry_rules[0].condition_group.conditions[0]
        cond_b = injected.entry_rules[0].condition_group.conditions[1]
        id_a = cond_a.condition_id
        id_b = cond_b.condition_id

        # Simulate reorder: swap b, a
        data = injected.model_dump()
        data["entry_rules"][0]["condition_group"]["conditions"] = [
            injected.entry_rules[0].condition_group.conditions[1].model_dump(),
            injected.entry_rules[0].condition_group.conditions[0].model_dump(),
        ]
        reordered = StrategySemantics.model_validate(data)

        # IDs should stay with their respective conditions
        reordered_ids = [
            c.condition_id
            for c in reordered.entry_rules[0].condition_group.conditions
            if isinstance(c, Condition)
        ]
        assert reordered_ids[0] == id_b
        assert reordered_ids[1] == id_a


# ---------------------------------------------------------------------------
# validate_semantic_identity_integrity
# ---------------------------------------------------------------------------

class TestIdentityIntegrity:
    def test_passes_with_unique_ids(self):
        s = inject_ids(_bare_semantics())
        result = validate_semantic_identity_integrity(s)
        assert result.valid is True
        assert result.errors == []

    def test_passes_with_no_ids(self):
        s = _bare_semantics()
        result = validate_semantic_identity_integrity(s)
        assert result.valid is True

    def test_duplicate_condition_id_detected(self):
        shared_id = generate_id()
        c1 = Condition(condition_id=shared_id, left=_price(), operator=ConditionOperator.GT, right=_const())
        c2 = Condition(condition_id=shared_id, left=_price(), operator=ConditionOperator.LT, right=_const("70"))
        group = ConditionGroup(operator=LogicalOperator.AND, conditions=(c1, c2))
        rule = EntryRule(condition_group=group)
        s = StrategySemantics(entry_rules=(rule,), exit_rules=())
        result = validate_semantic_identity_integrity(s)
        assert result.valid is False
        assert any(shared_id in e for e in result.errors)

    def test_duplicate_group_id_detected(self):
        shared_id = generate_id()
        g1 = ConditionGroup(group_id=shared_id, operator=LogicalOperator.AND, conditions=(_bare_condition(),))
        g2 = ConditionGroup(group_id=shared_id, operator=LogicalOperator.OR,  conditions=(_bare_condition(),))
        outer = ConditionGroup(operator=LogicalOperator.AND, conditions=(g1, g2))
        rule = EntryRule(condition_group=outer)
        s = StrategySemantics(entry_rules=(rule,), exit_rules=())
        result = validate_semantic_identity_integrity(s)
        assert result.valid is False
        assert any(shared_id in e for e in result.errors)

    def test_duplicate_rule_id_detected(self):
        shared_id = generate_id()
        r1 = EntryRule(rule_id=shared_id, condition_group=_bare_group())
        r2 = EntryRule(rule_id=shared_id, condition_group=_bare_group())
        s = StrategySemantics(entry_rules=(r1, r2), exit_rules=())
        result = validate_semantic_identity_integrity(s)
        assert result.valid is False
        assert any(shared_id in e for e in result.errors)

    def test_rule_id_duplicate_across_entry_and_exit(self):
        shared_id = generate_id()
        entry = EntryRule(rule_id=shared_id, condition_group=_bare_group())
        exit_ = ExitRule(rule_id=shared_id, condition_group=_bare_group())
        s = StrategySemantics(entry_rules=(entry,), exit_rules=(exit_,))
        result = validate_semantic_identity_integrity(s)
        assert result.valid is False
        assert any(shared_id in e for e in result.errors)

    def test_unique_ids_across_multiple_rules_passes(self):
        s = inject_ids(_bare_semantics(entry_count=3, exit_count=3))
        result = validate_semantic_identity_integrity(s)
        assert result.valid is True

    def test_mixed_present_and_none_ids_no_false_positive(self):
        c1 = Condition(condition_id=None, left=_price(), operator=ConditionOperator.GT, right=_const())
        c2 = Condition(condition_id=None, left=_price(), operator=ConditionOperator.LT, right=_const("70"))
        group = ConditionGroup(operator=LogicalOperator.AND, conditions=(c1, c2))
        rule = EntryRule(condition_group=group)
        s = StrategySemantics(entry_rules=(rule,), exit_rules=())
        result = validate_semantic_identity_integrity(s)
        assert result.valid is True


# ---------------------------------------------------------------------------
# validate_semantics_structure integration — identity check included
# ---------------------------------------------------------------------------

class TestStructureValidatorIncludesIdentity:
    def test_structure_valid_after_inject(self):
        s = inject_ids(_bare_semantics())
        result = validate_semantics_structure(s)
        assert result.valid is True

    def test_duplicate_condition_id_propagates_to_structure_validator(self):
        shared_id = generate_id()
        c1 = Condition(condition_id=shared_id, left=_price(), operator=ConditionOperator.GT, right=_const())
        c2 = Condition(condition_id=shared_id, left=_price(), operator=ConditionOperator.LT, right=_const("50"))
        group = ConditionGroup(operator=LogicalOperator.AND, conditions=(c1, c2))
        rule = EntryRule(condition_group=group)
        s = StrategySemantics(entry_rules=(rule,), exit_rules=())
        result = validate_semantics_structure(s)
        assert result.valid is False
        assert any(shared_id in e for e in result.errors)


# ---------------------------------------------------------------------------
# Backward compatibility — legacy semantics (no IDs) still work
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_legacy_semantics_loads_without_ids(self):
        """Pydantic accepts semantics with no ID fields (all default to None)."""
        data = {
            "entry_rules": [{
                "condition_group": {
                    "operator": "AND",
                    "conditions": [{
                        "left":     {"kind": "price", "ref": "close"},
                        "operator": ">",
                        "right":    {"kind": "constant", "ref": "30"},
                    }],
                },
            }],
            "exit_rules": [],
        }
        s = StrategySemantics.model_validate(data)
        assert s.entry_rules[0].rule_id is None
        assert s.entry_rules[0].condition_group.group_id is None
        cond = s.entry_rules[0].condition_group.conditions[0]
        assert isinstance(cond, Condition)
        assert cond.condition_id is None

    def test_legacy_semantics_passes_structure_validation(self):
        s = _bare_semantics()
        result = validate_semantics_structure(s)
        assert result.valid is True

    def test_inject_ids_upgrades_legacy_semantics(self):
        data = {
            "entry_rules": [{
                "condition_group": {
                    "operator": "AND",
                    "conditions": [{
                        "left":     {"kind": "price", "ref": "close"},
                        "operator": ">",
                        "right":    {"kind": "constant", "ref": "30"},
                    }],
                },
            }],
            "exit_rules": [],
        }
        legacy = StrategySemantics.model_validate(data)
        upgraded = inject_ids(legacy)
        assert upgraded.entry_rules[0].rule_id is not None
        assert upgraded.entry_rules[0].condition_group.group_id is not None
        cond = upgraded.entry_rules[0].condition_group.conditions[0]
        assert isinstance(cond, Condition)
        assert cond.condition_id is not None
