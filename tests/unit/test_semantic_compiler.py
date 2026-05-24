"""
Phase 2O.4 — Semantic Compiler tests.

Covers:
- compile_semantics() basic output shape
- simple condition compilation
- nested condition group compilation
- semantic ID preservation (condition_id, group_id, rule_id)
- entry and exit rule kind assignment
- rule index assignment
- tool_output dependency extraction
- price field dependency extraction
- constant dependency extraction
- mixed dependency extraction across multiple rules
- deduplication and sorting of dependencies
- empty semantics → warning diagnostic, compiled=True
- no entry rules → compiled=True, zero entry rule_nodes
- compilation of semantics with no IDs (legacy)
- deterministic serialization (same input → same output structure)
- node_count accuracy
- no runtime imports in compiler module
- CompilationResult structure: compiled, errors, evaluation_plan
- EvaluationPlan draft_id preserved
- EvaluationPlan semantic_version preserved
- nested group depth preservation
- label propagation
"""
import inspect
import importlib

import pytest

from backend.strategy_registry.semantic_compiler import compile_semantics
from backend.strategy_registry.semantic_identity import inject_ids
from backend.strategy_registry.semantic_plan import (
    CompilationResult,
    ConditionGroupPlanNode,
    ConditionPlanNode,
    DependencySet,
    EvaluationPlan,
    RulePlanNode,
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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _price(ref: str = "close") -> OperandReference:
    return OperandReference(kind=OperandKind.PRICE, ref=ref)

def _const(ref: str = "30") -> OperandReference:
    return OperandReference(kind=OperandKind.CONSTANT, ref=ref)

def _tool(ref: str = "sma_fast.value") -> OperandReference:
    return OperandReference(kind=OperandKind.TOOL_OUTPUT, ref=ref)


def _cond(left=None, op=ConditionOperator.GT, right=None, **kw) -> Condition:
    return Condition(
        left=left or _price(),
        operator=op,
        right=right or _const(),
        **kw,
    )


def _group(*conds, op=LogicalOperator.AND, **kw) -> ConditionGroup:
    nodes = conds or (_cond(),)
    return ConditionGroup(operator=op, conditions=tuple(nodes), **kw)


def _entry(*conds, **kw) -> EntryRule:
    return EntryRule(condition_group=_group(*conds), **kw)


def _exit(*conds, **kw) -> ExitRule:
    return ExitRule(condition_group=_group(*conds), **kw)


def _simple() -> StrategySemantics:
    """One entry rule, one exit rule, simple conditions."""
    return StrategySemantics(
        entry_rules=(_entry(_cond(_price("close"), ConditionOperator.GT, _const("50"))),),
        exit_rules=(_exit(_cond(_price("close"), ConditionOperator.LT, _const("20"))),),
    )


# ---------------------------------------------------------------------------
# CompilationResult structure
# ---------------------------------------------------------------------------

class TestCompilationResultStructure:
    def test_returns_compilation_result(self):
        result = compile_semantics(_simple())
        assert isinstance(result, CompilationResult)

    def test_compiled_true_on_success(self):
        result = compile_semantics(_simple())
        assert result.compiled is True

    def test_errors_empty_on_success(self):
        result = compile_semantics(_simple())
        assert result.errors == ()

    def test_evaluation_plan_present_on_success(self):
        result = compile_semantics(_simple())
        assert result.evaluation_plan is not None
        assert isinstance(result.evaluation_plan, EvaluationPlan)

    def test_draft_id_preserved(self):
        result = compile_semantics(_simple(), draft_id="my-draft")
        assert result.evaluation_plan.draft_id == "my-draft"

    def test_draft_id_none_for_payload(self):
        result = compile_semantics(_simple())
        assert result.evaluation_plan.draft_id is None

    def test_semantic_version_preserved(self):
        sem = StrategySemantics(
            entry_rules=(_entry(),),
            exit_rules=(),
            metadata=SemanticsMetadata(version="2.5"),
        )
        result = compile_semantics(sem)
        assert result.evaluation_plan.semantic_version == "2.5"

    def test_compiled_at_is_datetime(self):
        from datetime import datetime
        result = compile_semantics(_simple())
        assert isinstance(result.evaluation_plan.compiled_at, datetime)


# ---------------------------------------------------------------------------
# Rule node compilation
# ---------------------------------------------------------------------------

class TestRuleNodes:
    def test_entry_rule_kind(self):
        result = compile_semantics(_simple())
        plan = result.evaluation_plan
        entry_nodes = [n for n in plan.rule_nodes if n.kind == "entry"]
        assert len(entry_nodes) == 1

    def test_exit_rule_kind(self):
        result = compile_semantics(_simple())
        plan = result.evaluation_plan
        exit_nodes = [n for n in plan.rule_nodes if n.kind == "exit"]
        assert len(exit_nodes) == 1

    def test_rule_index_assignment(self):
        sem = StrategySemantics(
            entry_rules=(_entry(), _entry(), _entry()),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        entry_nodes = [n for n in result.evaluation_plan.rule_nodes if n.kind == "entry"]
        indices = [n.index for n in entry_nodes]
        assert indices == [0, 1, 2]

    def test_exit_rule_index_assignment(self):
        sem = StrategySemantics(
            entry_rules=(),
            exit_rules=(_exit(), _exit()),
        )
        result = compile_semantics(sem)
        exit_nodes = [n for n in result.evaluation_plan.rule_nodes if n.kind == "exit"]
        assert [n.index for n in exit_nodes] == [0, 1]

    def test_rule_label_preserved(self):
        sem = StrategySemantics(
            entry_rules=(EntryRule(condition_group=_group(), label="my entry"),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        node = result.evaluation_plan.rule_nodes[0]
        assert node.label == "my entry"

    def test_rule_without_label_is_none(self):
        result = compile_semantics(_simple())
        node = result.evaluation_plan.rule_nodes[0]
        assert node.label is None

    def test_rule_nodes_count(self):
        sem = StrategySemantics(
            entry_rules=(_entry(), _entry()),
            exit_rules=(_exit(),),
        )
        result = compile_semantics(sem)
        assert len(result.evaluation_plan.rule_nodes) == 3


# ---------------------------------------------------------------------------
# Condition compilation
# ---------------------------------------------------------------------------

class TestConditionCompilation:
    def test_condition_operator_preserved(self):
        sem = StrategySemantics(
            entry_rules=(_entry(_cond(op=ConditionOperator.CROSSES_ABOVE)),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        group_node = result.evaluation_plan.rule_nodes[0].condition_group
        cond_node = group_node.nodes[0]
        assert isinstance(cond_node, ConditionPlanNode)
        assert cond_node.operator == "crosses_above"

    def test_left_operand_kind_and_ref(self):
        sem = StrategySemantics(
            entry_rules=(_entry(_cond(left=_price("high"))),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        cond_node = result.evaluation_plan.rule_nodes[0].condition_group.nodes[0]
        assert isinstance(cond_node, ConditionPlanNode)
        assert cond_node.left_kind == "price"
        assert cond_node.left_ref == "high"

    def test_right_operand_kind_and_ref(self):
        sem = StrategySemantics(
            entry_rules=(_entry(_cond(right=_tool("rsi.value"))),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        cond_node = result.evaluation_plan.rule_nodes[0].condition_group.nodes[0]
        assert isinstance(cond_node, ConditionPlanNode)
        assert cond_node.right_kind == "tool_output"
        assert cond_node.right_ref == "rsi.value"

    def test_constant_operand(self):
        sem = StrategySemantics(
            entry_rules=(_entry(_cond(right=_const("70"))),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        cond_node = result.evaluation_plan.rule_nodes[0].condition_group.nodes[0]
        assert isinstance(cond_node, ConditionPlanNode)
        assert cond_node.right_kind == "constant"
        assert cond_node.right_ref == "70"

    def test_condition_label_preserved(self):
        cond = Condition(
            left=_price(),
            operator=ConditionOperator.GT,
            right=_const(),
            label="price above threshold",
        )
        sem = StrategySemantics(entry_rules=(_entry(cond),), exit_rules=())
        result = compile_semantics(sem)
        cond_node = result.evaluation_plan.rule_nodes[0].condition_group.nodes[0]
        assert isinstance(cond_node, ConditionPlanNode)
        assert cond_node.label == "price above threshold"


# ---------------------------------------------------------------------------
# Condition group compilation
# ---------------------------------------------------------------------------

class TestGroupCompilation:
    def test_group_operator_preserved(self):
        group = _group(_cond(), _cond(), op=LogicalOperator.OR)
        sem = StrategySemantics(
            entry_rules=(EntryRule(condition_group=group),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        group_node = result.evaluation_plan.rule_nodes[0].condition_group
        assert isinstance(group_node, ConditionGroupPlanNode)
        assert group_node.operator == "OR"

    def test_multiple_conditions_in_group(self):
        group = _group(_cond(), _cond(), _cond())
        sem = StrategySemantics(
            entry_rules=(EntryRule(condition_group=group),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        group_node = result.evaluation_plan.rule_nodes[0].condition_group
        assert len(group_node.nodes) == 3
        assert all(isinstance(n, ConditionPlanNode) for n in group_node.nodes)

    def test_group_label_preserved(self):
        group = ConditionGroup(
            operator=LogicalOperator.AND,
            conditions=(_cond(),),
            label="primary signal",
        )
        sem = StrategySemantics(
            entry_rules=(EntryRule(condition_group=group),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        group_node = result.evaluation_plan.rule_nodes[0].condition_group
        assert group_node.label == "primary signal"

    def test_nested_group_compilation(self):
        inner = _group(_cond(_price("high"), ConditionOperator.GT, _tool("atr.value")))
        outer = ConditionGroup(
            operator=LogicalOperator.AND,
            conditions=(inner, _cond()),
        )
        sem = StrategySemantics(
            entry_rules=(EntryRule(condition_group=outer),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        outer_node = result.evaluation_plan.rule_nodes[0].condition_group
        assert len(outer_node.nodes) == 2
        inner_node = outer_node.nodes[0]
        assert isinstance(inner_node, ConditionGroupPlanNode)
        leaf = inner_node.nodes[0]
        assert isinstance(leaf, ConditionPlanNode)
        assert leaf.left_kind == "price"
        assert leaf.left_ref == "high"

    def test_deeply_nested_groups(self):
        level3 = _group(_cond())
        level2 = ConditionGroup(operator=LogicalOperator.OR, conditions=(level3,))
        level1 = ConditionGroup(operator=LogicalOperator.AND, conditions=(level2,))
        sem = StrategySemantics(
            entry_rules=(EntryRule(condition_group=level1),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        assert result.compiled is True
        l1 = result.evaluation_plan.rule_nodes[0].condition_group
        l2 = l1.nodes[0]
        assert isinstance(l2, ConditionGroupPlanNode)
        l3 = l2.nodes[0]
        assert isinstance(l3, ConditionGroupPlanNode)
        assert isinstance(l3.nodes[0], ConditionPlanNode)


# ---------------------------------------------------------------------------
# Semantic ID preservation
# ---------------------------------------------------------------------------

class TestSemanticIdPreservation:
    def test_condition_id_preserved(self):
        sem = inject_ids(_simple())
        result = compile_semantics(sem)
        plan_cond = result.evaluation_plan.rule_nodes[0].condition_group.nodes[0]
        assert isinstance(plan_cond, ConditionPlanNode)
        src_cond = sem.entry_rules[0].condition_group.conditions[0]
        assert isinstance(src_cond, Condition)
        assert plan_cond.condition_id == src_cond.condition_id

    def test_group_id_preserved(self):
        sem = inject_ids(_simple())
        result = compile_semantics(sem)
        plan_group = result.evaluation_plan.rule_nodes[0].condition_group
        src_group = sem.entry_rules[0].condition_group
        assert plan_group.group_id == src_group.group_id

    def test_rule_id_preserved(self):
        sem = inject_ids(_simple())
        result = compile_semantics(sem)
        plan_rule = result.evaluation_plan.rule_nodes[0]
        src_rule = sem.entry_rules[0]
        assert plan_rule.rule_id == src_rule.rule_id

    def test_none_ids_propagate(self):
        """Legacy semantics (no IDs) compile correctly with None IDs in plan."""
        sem = _simple()  # no inject_ids
        result = compile_semantics(sem)
        plan_rule = result.evaluation_plan.rule_nodes[0]
        assert plan_rule.rule_id is None
        plan_group = plan_rule.condition_group
        assert plan_group.group_id is None
        plan_cond = plan_group.nodes[0]
        assert isinstance(plan_cond, ConditionPlanNode)
        assert plan_cond.condition_id is None

    def test_all_ids_preserved_after_inject(self):
        sem = inject_ids(StrategySemantics(
            entry_rules=(_entry(_cond(), _cond()), _entry()),
            exit_rules=(_exit(),),
        ))
        result = compile_semantics(sem, draft_id="test")
        plan_rule_ids = [n.rule_id for n in result.evaluation_plan.rule_nodes]
        src_entry_ids = [r.rule_id for r in sem.entry_rules]
        src_exit_ids  = [r.rule_id for r in sem.exit_rules]
        assert plan_rule_ids == src_entry_ids + src_exit_ids


# ---------------------------------------------------------------------------
# Dependency extraction
# ---------------------------------------------------------------------------

class TestDependencyExtraction:
    def test_price_field_extracted(self):
        sem = StrategySemantics(
            entry_rules=(_entry(_cond(left=_price("high"))),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        assert "high" in result.evaluation_plan.dependencies.price_fields

    def test_tool_output_extracted(self):
        sem = StrategySemantics(
            entry_rules=(_entry(_cond(left=_tool("sma_fast.value"))),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        assert "sma_fast.value" in result.evaluation_plan.dependencies.tool_outputs

    def test_constant_extracted(self):
        sem = StrategySemantics(
            entry_rules=(_entry(_cond(right=_const("30"))),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        assert "30" in result.evaluation_plan.dependencies.constants

    def test_multiple_dependencies_extracted(self):
        c1 = _cond(left=_tool("sma_fast.value"), right=_tool("sma_slow.value"))
        c2 = _cond(left=_price("close"), right=_const("0"))
        sem = StrategySemantics(
            entry_rules=(_entry(c1, c2),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        deps = result.evaluation_plan.dependencies
        assert "sma_fast.value" in deps.tool_outputs
        assert "sma_slow.value" in deps.tool_outputs
        assert "close" in deps.price_fields
        assert "0" in deps.constants

    def test_dependencies_deduped(self):
        c1 = _cond(left=_price("close"), right=_const("30"))
        c2 = _cond(left=_price("close"), right=_const("30"))
        sem = StrategySemantics(
            entry_rules=(_entry(c1, c2),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        deps = result.evaluation_plan.dependencies
        assert deps.price_fields.count("close") == 1
        assert deps.constants.count("30") == 1

    def test_dependencies_sorted(self):
        c1 = _cond(left=_tool("sma_slow.value"), right=_const("50"))
        c2 = _cond(left=_tool("rsi.value"),      right=_const("30"))
        sem = StrategySemantics(
            entry_rules=(_entry(c1, c2),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        deps = result.evaluation_plan.dependencies
        assert list(deps.tool_outputs) == sorted(deps.tool_outputs)
        assert list(deps.constants)    == sorted(deps.constants)

    def test_cross_rule_dependency_extraction(self):
        entry = _entry(_cond(left=_price("open")))
        exit_ = _exit(_cond(left=_price("close")))
        sem = StrategySemantics(entry_rules=(entry,), exit_rules=(exit_,))
        result = compile_semantics(sem)
        deps = result.evaluation_plan.dependencies
        assert "open"  in deps.price_fields
        assert "close" in deps.price_fields

    def test_nested_group_dependencies_extracted(self):
        inner = _group(_cond(left=_tool("macd.signal")))
        outer = ConditionGroup(operator=LogicalOperator.AND, conditions=(inner,))
        sem = StrategySemantics(
            entry_rules=(EntryRule(condition_group=outer),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        assert "macd.signal" in result.evaluation_plan.dependencies.tool_outputs

    def test_empty_semantics_has_empty_deps(self):
        sem = StrategySemantics(entry_rules=(), exit_rules=())
        result = compile_semantics(sem)
        deps = result.evaluation_plan.dependencies
        assert deps.tool_outputs == ()
        assert deps.price_fields == ()
        assert deps.constants == ()

    def test_no_tool_computation_performed(self):
        """Confirm extraction is reference-only — no tool functions called."""
        sem = StrategySemantics(
            entry_rules=(_entry(_cond(left=_tool("hypothetical.compute"))),),
            exit_rules=(),
        )
        # If a compute call were attempted, an error would be raised here.
        result = compile_semantics(sem)
        assert result.compiled is True
        assert "hypothetical.compute" in result.evaluation_plan.dependencies.tool_outputs


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

class TestDiagnostics:
    def test_empty_semantics_warning(self):
        sem = StrategySemantics(entry_rules=(), exit_rules=())
        result = compile_semantics(sem)
        assert result.compiled is True
        assert len(result.evaluation_plan.diagnostics) == 1
        diag = result.evaluation_plan.diagnostics[0]
        assert diag.severity == "warning"
        assert "no entry or exit rules" in diag.message

    def test_non_empty_semantics_no_warning(self):
        result = compile_semantics(_simple())
        assert result.evaluation_plan.diagnostics == ()


# ---------------------------------------------------------------------------
# Node count
# ---------------------------------------------------------------------------

class TestNodeCount:
    def test_single_condition_node_count(self):
        sem = StrategySemantics(
            entry_rules=(_entry(_cond()),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        # 1 rule + 1 condition = 2; but node_count counts within rules
        # _compile_rule returns count = condition_count (1), node_count = count + 1 (rule) = 2
        assert result.evaluation_plan.node_count == 2

    def test_multiple_conditions_node_count(self):
        sem = StrategySemantics(
            entry_rules=(_entry(_cond(), _cond(), _cond()),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        # 1 rule + 3 conditions = 4
        assert result.evaluation_plan.node_count == 4

    def test_nested_group_node_count(self):
        inner = _group(_cond())  # 1 cond
        outer = ConditionGroup(operator=LogicalOperator.AND, conditions=(inner, _cond()))
        sem = StrategySemantics(
            entry_rules=(EntryRule(condition_group=outer),),
            exit_rules=(),
        )
        result = compile_semantics(sem)
        # 1 rule + outer group (2 nodes: inner_group + cond) + inner group (1 node: cond)
        # _compile_group(outer) → count = inner_count+1+1 = 3 (inner:1cond+1grp=2, +1 outer_cond)
        # _compile_rule count = 3, total = 3+1 = 4
        assert result.evaluation_plan.node_count == 4

    def test_empty_semantics_node_count_zero(self):
        sem = StrategySemantics(entry_rules=(), exit_rules=())
        result = compile_semantics(sem)
        assert result.evaluation_plan.node_count == 0


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_input_same_output_shape(self):
        sem = inject_ids(_simple())
        r1 = compile_semantics(sem, draft_id="x")
        r2 = compile_semantics(sem, draft_id="x")
        assert r1.compiled == r2.compiled
        assert r1.errors == r2.errors
        assert r1.evaluation_plan.rule_nodes == r2.evaluation_plan.rule_nodes
        assert r1.evaluation_plan.dependencies == r2.evaluation_plan.dependencies

    def test_serialization_round_trip(self):
        result = compile_semantics(inject_ids(_simple()), draft_id="draft-1")
        plan = result.evaluation_plan
        # Serialize to dict and re-validate through the domain model
        from backend.strategy_registry.semantic_plan import EvaluationPlan
        data = plan.model_dump()
        restored = EvaluationPlan.model_validate(data)
        assert restored.draft_id == plan.draft_id
        assert restored.node_count == plan.node_count
        assert restored.dependencies.tool_outputs == plan.dependencies.tool_outputs


# ---------------------------------------------------------------------------
# Architecture guard — no forbidden imports
# ---------------------------------------------------------------------------

class TestArchitectureBoundary:
    _FORBIDDEN = [
        "strategy_runtime",
        "backtesting",
        "execution",
        "forward_testing",
    ]

    def _import_lines(self, mod) -> list[str]:
        return [
            line.strip()
            for line in inspect.getsource(mod).splitlines()
            if line.strip().startswith(("import ", "from "))
        ]

    def test_compiler_does_not_import_strategy_runtime(self):
        import backend.strategy_registry.semantic_compiler as mod
        lines = self._import_lines(mod)
        assert not any("strategy_runtime" in l for l in lines)

    def test_compiler_does_not_import_backtesting(self):
        import backend.strategy_registry.semantic_compiler as mod
        lines = self._import_lines(mod)
        assert not any("backtesting" in l for l in lines)

    def test_compiler_does_not_import_execution(self):
        import backend.strategy_registry.semantic_compiler as mod
        lines = self._import_lines(mod)
        assert not any(".execution" in l for l in lines)

    def test_compiler_does_not_import_forward_testing(self):
        import backend.strategy_registry.semantic_compiler as mod
        lines = self._import_lines(mod)
        assert not any("forward_testing" in l for l in lines)

    def test_plan_module_does_not_import_strategy_runtime(self):
        import backend.strategy_registry.semantic_plan as mod
        lines = self._import_lines(mod)
        assert not any("strategy_runtime" in l for l in lines)
