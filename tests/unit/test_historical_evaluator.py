"""
Phase 2P.2 — Historical Evaluation Iterator unit tests.

Coverage:
    HistoricalBarContext        — construction, defaults, field storage
    HistoricalEvaluationInput   — construction, empty bars
    _build_scalar_context       — price field mapping, tool output mapping
    evaluate_history()          — iteration, counts, traces, determinism
    BarEvaluationResult         — construction, field propagation
    HistoricalEvaluationResult  — aggregated counts, plan_draft_id
    Deferred operators          — crosses_above/crosses_below → None outcome
    Architecture boundary       — no forbidden imports
"""
from __future__ import annotations

import importlib
import inspect
from datetime import datetime, timezone

import pytest

from backend.strategy_registry.evaluator_contracts import EvaluationTrace
from backend.strategy_registry.historical_evaluator import (
    BarEvaluationResult,
    HistoricalBarContext,
    HistoricalEvaluationInput,
    HistoricalEvaluationResult,
    _build_scalar_context,
    evaluate_history,
)
from backend.strategy_registry.semantic_plan import (
    CompilationDiagnostic,
    ConditionGroupPlanNode,
    ConditionPlanNode,
    DependencySet,
    EvaluationPlan,
    RulePlanNode,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 5, 21, tzinfo=timezone.utc)
_T0  = datetime(2026, 1, 1, tzinfo=timezone.utc)
_T1  = datetime(2026, 1, 2, tzinfo=timezone.utc)
_T2  = datetime(2026, 1, 3, tzinfo=timezone.utc)


def _condition(
    left_kind:  str = "price",
    left_ref:   str = "close",
    operator:   str = ">",
    right_kind: str = "constant",
    right_ref:  str = "50",
    cid:        str | None = "c1",
) -> ConditionPlanNode:
    return ConditionPlanNode(
        condition_id=cid,
        left_kind=left_kind,
        left_ref=left_ref,
        operator=operator,
        right_kind=right_kind,
        right_ref=right_ref,
        label=None,
    )


def _group(
    *nodes: ConditionPlanNode | ConditionGroupPlanNode,
    operator: str = "AND",
    gid: str | None = "g1",
) -> ConditionGroupPlanNode:
    return ConditionGroupPlanNode(
        group_id=gid,
        operator=operator,
        nodes=tuple(nodes),
        label=None,
    )


def _rule(
    group:  ConditionGroupPlanNode,
    kind:   str = "entry",
    index:  int = 0,
    rid:    str | None = "r1",
) -> RulePlanNode:
    return RulePlanNode(
        rule_id=rid,
        kind=kind,  # type: ignore[arg-type]
        index=index,
        label=None,
        condition_group=group,
    )


def _plan(*rules: RulePlanNode, draft_id: str | None = None) -> EvaluationPlan:
    return EvaluationPlan(
        draft_id=draft_id,
        semantic_version="1.0",
        rule_nodes=tuple(rules),
        dependencies=DependencySet(tool_outputs=(), price_fields=(), constants=()),
        diagnostics=(),
        node_count=len(rules),
        compiled_at=_NOW,
    )


def _simple_entry_plan(threshold: float = 50.0) -> EvaluationPlan:
    """close > threshold → entry triggered."""
    c = _condition("price", "close", ">", "constant", str(threshold))
    return _plan(_rule(_group(c)))


def _simple_exit_plan(threshold: float = 150.0) -> EvaluationPlan:
    """close > threshold → exit triggered."""
    c = _condition("price", "close", ">", "constant", str(threshold))
    return _plan(_rule(_group(c), kind="exit", rid="exit1"))


def _bar(
    index:        int,
    close:        float = 100.0,
    tool_outputs: dict | None = None,
    timestamp:    datetime | None = None,
    extra_prices: dict | None = None,
) -> HistoricalBarContext:
    prices = {"close": close}
    if extra_prices:
        prices.update(extra_prices)
    return HistoricalBarContext(
        bar_index=index,
        timestamp=timestamp,
        price_fields=prices,
        tool_outputs=tool_outputs or {},
    )


def _input(plan: EvaluationPlan, *bars: HistoricalBarContext) -> HistoricalEvaluationInput:
    return HistoricalEvaluationInput(plan=plan, bars=tuple(bars))


# ---------------------------------------------------------------------------
# TestHistoricalBarContext
# ---------------------------------------------------------------------------

class TestHistoricalBarContext:
    def test_bar_index_stored(self):
        b = _bar(5)
        assert b.bar_index == 5

    def test_price_fields_stored(self):
        b = HistoricalBarContext(bar_index=0, price_fields={"close": 100.0, "open": 99.0})
        assert b.price_fields["close"] == 100.0
        assert b.price_fields["open"]  == 99.0

    def test_tool_outputs_default_empty(self):
        b = HistoricalBarContext(bar_index=0, price_fields={"close": 100.0})
        assert b.tool_outputs == {}

    def test_tool_outputs_stored(self):
        b = HistoricalBarContext(
            bar_index=0,
            price_fields={"close": 100.0},
            tool_outputs={"sma_fast.value": 98.0},
        )
        assert b.tool_outputs["sma_fast.value"] == 98.0

    def test_timestamp_default_none(self):
        b = _bar(0)
        assert b.timestamp is None

    def test_timestamp_stored(self):
        b = HistoricalBarContext(bar_index=0, price_fields={}, timestamp=_T0)
        assert b.timestamp == _T0

    def test_multiple_price_fields(self):
        b = HistoricalBarContext(
            bar_index=0,
            price_fields={"open": 99.0, "high": 102.0, "low": 98.0, "close": 101.0, "volume": 1000.0},
        )
        assert len(b.price_fields) == 5

    def test_multiple_tool_outputs(self):
        b = HistoricalBarContext(
            bar_index=0,
            price_fields={"close": 100.0},
            tool_outputs={"sma_fast.value": 98.0, "sma_slow.value": 95.0, "rsi.value": 60.0},
        )
        assert len(b.tool_outputs) == 3


# ---------------------------------------------------------------------------
# TestHistoricalEvaluationInput
# ---------------------------------------------------------------------------

class TestHistoricalEvaluationInput:
    def test_plan_stored(self):
        plan = _simple_entry_plan()
        inp  = _input(plan, _bar(0))
        assert inp.plan is plan

    def test_bars_stored_as_tuple(self):
        inp = _input(_simple_entry_plan(), _bar(0), _bar(1))
        assert isinstance(inp.bars, tuple)
        assert len(inp.bars) == 2

    def test_empty_bars_allowed(self):
        inp = _input(_simple_entry_plan())
        assert inp.bars == ()


# ---------------------------------------------------------------------------
# TestBuildScalarContext
# ---------------------------------------------------------------------------

class TestBuildScalarContext:
    def test_price_field_mapped(self):
        bar = _bar(0, close=105.0)
        ctx = _build_scalar_context(bar, None)
        assert ctx.resolve_price_field("close") == 105.0

    def test_multiple_price_fields_mapped(self):
        bar = HistoricalBarContext(
            bar_index=0,
            price_fields={"close": 101.0, "open": 99.0, "high": 103.0},
        )
        ctx = _build_scalar_context(bar, None)
        assert ctx.resolve_price_field("close") == 101.0
        assert ctx.resolve_price_field("open")  == 99.0
        assert ctx.resolve_price_field("high")  == 103.0

    def test_tool_output_mapped(self):
        bar = _bar(0, tool_outputs={"sma_fast.value": 98.5})
        ctx = _build_scalar_context(bar, None)
        assert ctx.resolve_tool_output("sma_fast", "value") == 98.5

    def test_multiple_tool_outputs_mapped(self):
        bar = _bar(0, tool_outputs={"sma_fast.value": 98.0, "rsi.value": 55.0})
        ctx = _build_scalar_context(bar, None)
        assert ctx.resolve_tool_output("sma_fast", "value") == 98.0
        assert ctx.resolve_tool_output("rsi", "value") == 55.0

    def test_evaluation_id_includes_bar_index(self):
        bar = _bar(7)
        ctx = _build_scalar_context(bar, None)
        assert "7" in ctx.evaluation_id

    def test_evaluation_id_includes_plan_draft_id(self):
        bar = _bar(0)
        ctx = _build_scalar_context(bar, "draft-xyz")
        assert "draft-xyz" in ctx.evaluation_id

    def test_empty_tool_outputs_no_error(self):
        bar = _bar(0)
        ctx = _build_scalar_context(bar, None)
        assert ctx.available_tool_instances == ()

    def test_plan_draft_id_none_uses_fallback(self):
        bar = _bar(0)
        ctx = _build_scalar_context(bar, None)
        assert "plan" in ctx.evaluation_id


# ---------------------------------------------------------------------------
# TestEvaluateHistory — iteration
# ---------------------------------------------------------------------------

class TestEvaluateHistoryIteration:
    def test_empty_bars_returns_zero_evaluated(self):
        result = evaluate_history(_input(_simple_entry_plan()))
        assert result.bars_evaluated == 0
        assert result.bar_results == ()

    def test_single_bar_triggered(self):
        plan   = _simple_entry_plan(threshold=50.0)
        result = evaluate_history(_input(plan, _bar(0, close=100.0)))
        assert result.bars_evaluated == 1
        assert result.bar_results[0].entry_triggered is True

    def test_single_bar_not_triggered(self):
        plan   = _simple_entry_plan(threshold=50.0)
        result = evaluate_history(_input(plan, _bar(0, close=30.0)))
        assert result.bars_evaluated == 1
        assert result.bar_results[0].entry_triggered is False

    def test_multiple_bars_evaluated(self):
        plan   = _simple_entry_plan(50.0)
        result = evaluate_history(_input(plan, _bar(0, 100.0), _bar(1, 40.0), _bar(2, 80.0)))
        assert result.bars_evaluated == 3
        assert len(result.bar_results) == 3

    def test_bar_index_preserved_in_results(self):
        plan   = _simple_entry_plan()
        result = evaluate_history(_input(plan, _bar(10), _bar(20), _bar(30)))
        assert [r.bar_index for r in result.bar_results] == [10, 20, 30]

    def test_timestamp_preserved_in_results(self):
        plan   = _simple_entry_plan()
        b0 = HistoricalBarContext(bar_index=0, price_fields={"close": 100.0}, timestamp=_T0)
        b1 = HistoricalBarContext(bar_index=1, price_fields={"close": 100.0}, timestamp=_T1)
        result = evaluate_history(_input(plan, b0, b1))
        assert result.bar_results[0].timestamp == _T0
        assert result.bar_results[1].timestamp == _T1

    def test_timestamp_none_preserved(self):
        plan   = _simple_entry_plan()
        result = evaluate_history(_input(plan, _bar(0, timestamp=None)))
        assert result.bar_results[0].timestamp is None

    def test_deterministic_same_input(self):
        plan = _simple_entry_plan()
        bars = (_bar(0, 100.0), _bar(1, 40.0))
        r1 = evaluate_history(HistoricalEvaluationInput(plan=plan, bars=bars))
        r2 = evaluate_history(HistoricalEvaluationInput(plan=plan, bars=bars))
        assert r1.entry_triggered_count == r2.entry_triggered_count
        assert [x.entry_triggered for x in r1.bar_results] == \
               [x.entry_triggered for x in r2.bar_results]

    def test_iteration_order_preserved(self):
        plan = _simple_entry_plan(50.0)
        # alternating above/below threshold
        bars = tuple(_bar(i, close=(100.0 if i % 2 == 0 else 20.0)) for i in range(6))
        result = evaluate_history(HistoricalEvaluationInput(plan=plan, bars=bars))
        triggered = [r.entry_triggered for r in result.bar_results]
        assert triggered == [True, False, True, False, True, False]


# ---------------------------------------------------------------------------
# TestEvaluateHistory — aggregated counts
# ---------------------------------------------------------------------------

class TestEvaluateHistoryAggregation:
    def test_entry_triggered_count_true_only(self):
        plan   = _simple_entry_plan(50.0)
        result = evaluate_history(_input(plan, _bar(0, 100.0), _bar(1, 30.0), _bar(2, 80.0)))
        assert result.entry_triggered_count == 2  # bars 0 and 2

    def test_entry_triggered_count_none_not_counted(self):
        # missing price.close → outcome=None → not counted
        plan = _simple_entry_plan(50.0)
        no_price = HistoricalBarContext(bar_index=0, price_fields={})
        result = evaluate_history(_input(plan, no_price))
        assert result.entry_triggered_count == 0

    def test_exit_triggered_count(self):
        plan   = _simple_exit_plan(50.0)
        result = evaluate_history(_input(plan, _bar(0, 100.0), _bar(1, 30.0)))
        assert result.exit_triggered_count == 1  # only bar 0

    def test_all_triggered(self):
        plan = _simple_entry_plan(50.0)
        bars = tuple(_bar(i, 100.0) for i in range(5))
        result = evaluate_history(HistoricalEvaluationInput(plan=plan, bars=bars))
        assert result.entry_triggered_count == 5

    def test_none_triggered(self):
        plan = _simple_entry_plan(50.0)
        bars = tuple(_bar(i, 10.0) for i in range(5))
        result = evaluate_history(HistoricalEvaluationInput(plan=plan, bars=bars))
        assert result.entry_triggered_count == 0

    def test_plan_draft_id_in_result(self):
        plan   = _plan(_rule(_group(_condition())), draft_id="draft-999")
        result = evaluate_history(_input(plan, _bar(0, 100.0)))
        assert result.plan_draft_id == "draft-999"

    def test_plan_draft_id_none(self):
        plan   = _plan(_rule(_group(_condition())))
        result = evaluate_history(_input(plan))
        assert result.plan_draft_id is None

    def test_zero_count_exit_when_no_exit_rules(self):
        plan   = _simple_entry_plan()
        result = evaluate_history(_input(plan, _bar(0, 100.0)))
        assert result.exit_triggered_count == 0

    def test_bars_evaluated_matches_input(self):
        plan = _simple_entry_plan()
        bars = tuple(_bar(i) for i in range(10))
        result = evaluate_history(HistoricalEvaluationInput(plan=plan, bars=bars))
        assert result.bars_evaluated == 10


# ---------------------------------------------------------------------------
# TestEvaluateHistory — traces
# ---------------------------------------------------------------------------

class TestEvaluateHistoryTraces:
    def test_trace_in_each_bar_result(self):
        plan   = _simple_entry_plan()
        result = evaluate_history(_input(plan, _bar(0), _bar(1)))
        for r in result.bar_results:
            assert isinstance(r.trace, EvaluationTrace)

    def test_trace_entry_triggered_matches_bar_result(self):
        plan   = _simple_entry_plan(50.0)
        result = evaluate_history(_input(plan, _bar(0, 100.0)))
        r = result.bar_results[0]
        assert r.entry_triggered == r.trace.entry_triggered

    def test_trace_exit_triggered_matches_bar_result(self):
        plan   = _simple_exit_plan(50.0)
        result = evaluate_history(_input(plan, _bar(0, 100.0)))
        r = result.bar_results[0]
        assert r.exit_triggered == r.trace.exit_triggered

    def test_trace_has_rule_results(self):
        plan   = _simple_entry_plan()
        result = evaluate_history(_input(plan, _bar(0, 100.0)))
        assert len(result.bar_results[0].trace.rule_results) == 1

    def test_trace_evaluation_id_contains_bar_index(self):
        plan   = _simple_entry_plan()
        result = evaluate_history(_input(plan, _bar(42, 100.0)))
        assert "42" in result.bar_results[0].trace.evaluation_id

    def test_trace_preserves_condition_outcome(self):
        plan   = _simple_entry_plan(50.0)
        result = evaluate_history(_input(plan, _bar(0, 100.0)))
        rule_result  = result.bar_results[0].trace.rule_results[0]
        group_result = rule_result.group_result
        assert len(group_result.child_results) == 1
        assert group_result.child_results[0].outcome is True

    def test_nested_group_trace_preserved(self):
        # (close > 50 AND close < 200) → both True
        c1 = _condition("price", "close", ">",  "constant", "50",  cid="c1")
        c2 = _condition("price", "close", "<",  "constant", "200", cid="c2")
        g  = _group(c1, c2, operator="AND")
        plan   = _plan(_rule(g))
        result = evaluate_history(_input(plan, _bar(0, 100.0)))
        rule   = result.bar_results[0].trace.rule_results[0]
        assert len(rule.group_result.child_results) == 2

    def test_diagnostics_in_trace_when_operand_missing(self):
        # missing price.close → diagnostic in condition result
        plan   = _simple_entry_plan(50.0)
        no_price = HistoricalBarContext(bar_index=0, price_fields={})
        result = evaluate_history(_input(plan, no_price))
        rule   = result.bar_results[0].trace.rule_results[0]
        cond   = rule.group_result.child_results[0]
        assert cond.outcome is None
        assert len(cond.diagnostics) == 1


# ---------------------------------------------------------------------------
# TestEvaluateHistory — missing values
# ---------------------------------------------------------------------------

class TestEvaluateHistoryMissingValues:
    def test_missing_price_produces_none(self):
        plan     = _simple_entry_plan(50.0)
        no_price = HistoricalBarContext(bar_index=0, price_fields={})
        result   = evaluate_history(_input(plan, no_price))
        assert result.bar_results[0].entry_triggered is None

    def test_missing_tool_output_produces_none(self):
        c    = _condition("tool_output", "sma.value", ">", "constant", "50")
        plan = _plan(_rule(_group(c)))
        bar  = _bar(0, 100.0)  # no tool_outputs
        result = evaluate_history(_input(plan, bar))
        assert result.bar_results[0].entry_triggered is None

    def test_partial_bars_have_correct_outcomes(self):
        # bar 0 has price, bar 1 does not
        plan = _simple_entry_plan(50.0)
        b0   = _bar(0, close=100.0)
        b1   = HistoricalBarContext(bar_index=1, price_fields={})
        result = evaluate_history(_input(plan, b0, b1))
        assert result.bar_results[0].entry_triggered is True
        assert result.bar_results[1].entry_triggered is None
        assert result.entry_triggered_count == 1  # only bar 0

    def test_tool_output_resolved_when_present(self):
        c    = _condition("tool_output", "sma.value", ">", "constant", "50")
        plan = _plan(_rule(_group(c)))
        bar  = _bar(0, tool_outputs={"sma.value": 80.0})
        result = evaluate_history(_input(plan, bar))
        assert result.bar_results[0].entry_triggered is True

    def test_entry_count_excludes_none_outcomes(self):
        plan = _simple_entry_plan(50.0)
        good = _bar(0, close=100.0)
        bad  = HistoricalBarContext(bar_index=1, price_fields={})
        result = evaluate_history(_input(plan, good, bad))
        assert result.entry_triggered_count == 1


# ---------------------------------------------------------------------------
# TestDeferredOperators — crosses_above/crosses_below produce None
# ---------------------------------------------------------------------------

class TestDeferredOperatorsHistorical:
    def test_crosses_above_produces_none_outcome(self):
        c    = _condition("price", "close", "crosses_above", "tool_output", "sma.value")
        plan = _plan(_rule(_group(c)))
        bar  = _bar(0, close=100.0, tool_outputs={"sma.value": 99.0})
        result = evaluate_history(_input(plan, bar))
        assert result.bar_results[0].entry_triggered is None

    def test_crosses_below_produces_none_outcome(self):
        c    = _condition("price", "close", "crosses_below", "tool_output", "sma.value")
        plan = _plan(_rule(_group(c)))
        bar  = _bar(0, close=98.0, tool_outputs={"sma.value": 99.0})
        result = evaluate_history(_input(plan, bar))
        assert result.bar_results[0].entry_triggered is None

    def test_crosses_above_not_counted(self):
        c    = _condition("price", "close", "crosses_above", "tool_output", "sma.value")
        plan = _plan(_rule(_group(c)))
        bars = tuple(_bar(i, close=100.0, tool_outputs={"sma.value": 99.0}) for i in range(5))
        result = evaluate_history(HistoricalEvaluationInput(plan=plan, bars=bars))
        assert result.entry_triggered_count == 0  # all None, not True

    def test_crosses_above_diagnostic_present(self):
        # First bar has no previous bar, so diagnostic code is "no_previous_bar"
        c    = _condition("price", "close", "crosses_above", "tool_output", "sma.value")
        plan = _plan(_rule(_group(c)))
        bar  = _bar(0, close=100.0, tool_outputs={"sma.value": 99.0})
        result  = evaluate_history(_input(plan, bar))
        cond    = result.bar_results[0].trace.rule_results[0].group_result.child_results[0]
        assert any(d.code == "no_previous_bar" for d in cond.diagnostics)


# ---------------------------------------------------------------------------
# TestBarEvaluationResult
# ---------------------------------------------------------------------------

class TestBarEvaluationResult:
    def test_entry_triggered_is_true(self):
        plan   = _simple_entry_plan(50.0)
        result = evaluate_history(_input(plan, _bar(0, 100.0)))
        assert result.bar_results[0].entry_triggered is True

    def test_entry_triggered_is_false(self):
        plan   = _simple_entry_plan(50.0)
        result = evaluate_history(_input(plan, _bar(0, 10.0)))
        assert result.bar_results[0].entry_triggered is False

    def test_returns_bar_evaluation_result(self):
        plan   = _simple_entry_plan()
        result = evaluate_history(_input(plan, _bar(0, 100.0)))
        assert isinstance(result.bar_results[0], BarEvaluationResult)


# ---------------------------------------------------------------------------
# TestHistoricalEvaluationResult
# ---------------------------------------------------------------------------

class TestHistoricalEvaluationResultModel:
    def test_returns_historical_evaluation_result(self):
        result = evaluate_history(_input(_simple_entry_plan()))
        assert isinstance(result, HistoricalEvaluationResult)

    def test_bar_results_is_tuple(self):
        plan   = _simple_entry_plan()
        result = evaluate_history(_input(plan, _bar(0)))
        assert isinstance(result.bar_results, tuple)

    def test_entry_and_exit_counts_independent(self):
        # Plan with both entry and exit rules
        entry_c = _condition("price", "close", ">", "constant", "50",  cid="c1")
        exit_c  = _condition("price", "close", ">", "constant", "150", cid="c2")
        entry_r = _rule(_group(entry_c), kind="entry", index=0, rid="r1")
        exit_r  = _rule(_group(exit_c), kind="exit",  index=0, rid="r2")
        plan = _plan(entry_r, exit_r)
        # close=100 → entry triggered, exit not triggered
        result = evaluate_history(_input(plan, _bar(0, close=100.0)))
        assert result.entry_triggered_count == 1
        assert result.exit_triggered_count  == 0


# ---------------------------------------------------------------------------
# Architecture boundary tests
# ---------------------------------------------------------------------------

class TestArchitectureBoundary:
    _FORBIDDEN = ("strategy_runtime", "backtesting", "execution", "forward_testing")

    def _import_lines(self, module_name: str) -> list[str]:
        mod = importlib.import_module(module_name)
        src = inspect.getsource(mod)
        return [
            line.strip()
            for line in src.splitlines()
            if line.strip().startswith("import ") or line.strip().startswith("from ")
        ]

    def _check(self, module_name: str) -> None:
        for line in self._import_lines(module_name):
            for forbidden in self._FORBIDDEN:
                assert forbidden not in line, (
                    f"Forbidden import in {module_name}: '{line}' references '{forbidden}'"
                )

    def test_historical_evaluator_boundary(self):
        self._check("backend.strategy_registry.historical_evaluator")

    def test_historical_evaluation_service_boundary(self):
        self._check("backend.api.services.historical_evaluation_service")
