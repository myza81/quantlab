"""
Phase 2P.4 — Signal Event Contracts unit tests.

Coverage:
    SignalEvent             — frozen, required fields, no execution fields
    SignalEventBatch        — frozen, events + summary
    SignalEventSummary      — counts, bar counts, first/last
    SignalEventKind         — enum values
    SignalEventSource       — traceability fields
    extract_signal_events() — entry/exit extraction, False/None skipped,
                              deterministic ordering, multi-rule, multi-bar,
                              empty result, summary counts, plan_draft_id
    API endpoint            — POST /semantics/extract-signal-events
    Architecture boundary   — no forbidden imports
"""
from __future__ import annotations

import importlib
import inspect
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.strategy_registry.evaluator_contracts import EvaluationDiagnostic
from backend.strategy_registry.historical_evaluator import (
    HistoricalBarContext,
    HistoricalEvaluationInput,
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
from backend.strategy_registry.signal_event_extractor import extract_signal_events
from backend.strategy_registry.signal_events import (
    SignalEvent,
    SignalEventBatch,
    SignalEventKind,
    SignalEventSource,
    SignalEventSummary,
)

_CLIENT = TestClient(app)
_NOW    = datetime(2026, 5, 22, tzinfo=timezone.utc)
_T0     = datetime(2026, 1, 1, tzinfo=timezone.utc)
_T1     = datetime(2026, 1, 2, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Plan / bar helpers
# ---------------------------------------------------------------------------

def _condition(
    left_kind:  str = "price",
    left_ref:   str = "close",
    operator:   str = ">",
    right_kind: str = "constant",
    right_ref:  str = "50",
    cid:        str = "c1",
) -> ConditionPlanNode:
    return ConditionPlanNode(
        condition_id=cid,
        left_kind=left_kind, left_ref=left_ref,
        operator=operator,
        right_kind=right_kind, right_ref=right_ref,
        label=None,
    )


def _group(*nodes, operator="AND", gid="g1") -> ConditionGroupPlanNode:
    return ConditionGroupPlanNode(
        group_id=gid, operator=operator, nodes=tuple(nodes), label=None,
    )


def _rule(group, kind="entry", index=0, rid="r1") -> RulePlanNode:
    return RulePlanNode(
        rule_id=rid, kind=kind, index=index, label=None, condition_group=group,
    )


def _plan(*rules, draft_id=None) -> EvaluationPlan:
    return EvaluationPlan(
        draft_id=draft_id,
        semantic_version="1.0",
        rule_nodes=tuple(rules),
        dependencies=DependencySet(tool_outputs=(), price_fields=(), constants=()),
        diagnostics=(),
        node_count=len(rules),
        compiled_at=_NOW,
    )


def _bar(index, close=100.0, timestamp=None) -> HistoricalBarContext:
    return HistoricalBarContext(
        bar_index=index,
        price_fields={"close": close},
        timestamp=timestamp,
    )


def _evaluate(plan, *bars):
    return evaluate_history(HistoricalEvaluationInput(plan=plan, bars=tuple(bars)))


def _simple_entry_plan(threshold=50.0, draft_id=None):
    return _plan(_rule(_group(_condition(right_ref=str(threshold)))), draft_id=draft_id)


def _simple_exit_plan(threshold=50.0, draft_id=None):
    return _plan(
        _rule(_group(_condition(right_ref=str(threshold))), kind="exit", rid="exit1"),
        draft_id=draft_id,
    )


# ---------------------------------------------------------------------------
# TestSignalEventKind
# ---------------------------------------------------------------------------

class TestSignalEventKind:
    def test_entry_value(self):
        assert SignalEventKind.ENTRY == "entry"

    def test_exit_value(self):
        assert SignalEventKind.EXIT == "exit"

    def test_diagnostic_value(self):
        assert SignalEventKind.DIAGNOSTIC == "diagnostic"


# ---------------------------------------------------------------------------
# TestSignalEventSource
# ---------------------------------------------------------------------------

class TestSignalEventSource:
    def _source(self, **kwargs):
        defaults = dict(
            bar_index=0, timestamp=None,
            rule_id="r1", rule_kind="entry", rule_index=0,
        )
        defaults.update(kwargs)
        return SignalEventSource(**defaults)

    def test_bar_index_stored(self):
        assert self._source(bar_index=5).bar_index == 5

    def test_timestamp_stored(self):
        assert self._source(timestamp=_T0).timestamp == _T0

    def test_timestamp_none(self):
        assert self._source(timestamp=None).timestamp is None

    def test_rule_id_stored(self):
        assert self._source(rule_id="my_rule").rule_id == "my_rule"

    def test_rule_id_none_allowed(self):
        assert self._source(rule_id=None).rule_id is None

    def test_rule_kind_entry(self):
        assert self._source(rule_kind="entry").rule_kind == "entry"

    def test_rule_kind_exit(self):
        assert self._source(rule_kind="exit").rule_kind == "exit"

    def test_rule_index_stored(self):
        assert self._source(rule_index=3).rule_index == 3

    def test_frozen(self):
        src = self._source()
        with pytest.raises(Exception):
            src.bar_index = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestSignalEvent
# ---------------------------------------------------------------------------

class TestSignalEvent:
    def _event(self, **kwargs):
        defaults = dict(
            event_id="0:entry:0:r1",
            kind=SignalEventKind.ENTRY,
            source=SignalEventSource(
                bar_index=0, timestamp=None,
                rule_id="r1", rule_kind="entry", rule_index=0,
            ),
            outcome=True,
        )
        defaults.update(kwargs)
        return SignalEvent(**defaults)

    def test_frozen(self):
        ev = self._event()
        with pytest.raises(Exception):
            ev.outcome = False  # type: ignore[misc]

    def test_event_id_stored(self):
        assert self._event(event_id="test-id").event_id == "test-id"

    def test_kind_stored(self):
        assert self._event(kind=SignalEventKind.EXIT).kind == SignalEventKind.EXIT

    def test_outcome_true(self):
        assert self._event().outcome is True

    def test_diagnostics_default_empty(self):
        assert self._event().diagnostics == ()

    def test_no_order_field(self):
        ev = self._event()
        assert not hasattr(ev, "order")

    def test_no_trade_field(self):
        ev = self._event()
        assert not hasattr(ev, "trade")

    def test_no_position_field(self):
        ev = self._event()
        assert not hasattr(ev, "position")

    def test_no_pnl_field(self):
        ev = self._event()
        assert not hasattr(ev, "pnl")

    def test_no_fill_field(self):
        ev = self._event()
        assert not hasattr(ev, "fill")


# ---------------------------------------------------------------------------
# TestSignalEventSummary
# ---------------------------------------------------------------------------

class TestSignalEventSummary:
    def _summary(self, **kwargs):
        defaults = dict(
            total_events=0, entry_events=0, exit_events=0,
            diagnostic_events=0, bars_with_events=0,
            first_event_bar_index=None, last_event_bar_index=None,
        )
        defaults.update(kwargs)
        return SignalEventSummary(**defaults)

    def test_frozen(self):
        s = self._summary()
        with pytest.raises(Exception):
            s.total_events = 99  # type: ignore[misc]

    def test_empty_summary(self):
        s = self._summary()
        assert s.total_events == 0
        assert s.first_event_bar_index is None
        assert s.last_event_bar_index  is None

    def test_populated_counts(self):
        s = self._summary(
            total_events=5, entry_events=3, exit_events=2,
            bars_with_events=3,
            first_event_bar_index=0, last_event_bar_index=10,
        )
        assert s.total_events  == 5
        assert s.entry_events  == 3
        assert s.exit_events   == 2
        assert s.bars_with_events == 3


# ---------------------------------------------------------------------------
# TestSignalEventBatch
# ---------------------------------------------------------------------------

class TestSignalEventBatch:
    def _empty_batch(self, draft_id=None):
        return SignalEventBatch(
            plan_draft_id=draft_id,
            events=(),
            summary=SignalEventSummary(
                total_events=0, entry_events=0, exit_events=0,
                diagnostic_events=0, bars_with_events=0,
                first_event_bar_index=None, last_event_bar_index=None,
            ),
        )

    def test_frozen(self):
        b = self._empty_batch()
        with pytest.raises(Exception):
            b.events = ()  # type: ignore[misc]

    def test_plan_draft_id_preserved(self):
        b = self._empty_batch(draft_id="d1")
        assert b.plan_draft_id == "d1"

    def test_plan_draft_id_none(self):
        b = self._empty_batch()
        assert b.plan_draft_id is None


# ---------------------------------------------------------------------------
# TestExtractSignalEvents — basic extraction
# ---------------------------------------------------------------------------

class TestExtractSignalEventsBasic:
    def test_entry_triggered_true_produces_event(self):
        plan   = _simple_entry_plan()
        result = _evaluate(plan, _bar(0, 100.0))
        batch  = extract_signal_events(result)
        assert len(batch.events) == 1
        assert batch.events[0].kind == SignalEventKind.ENTRY

    def test_entry_triggered_false_produces_no_event(self):
        plan   = _simple_entry_plan()
        result = _evaluate(plan, _bar(0, 10.0))
        batch  = extract_signal_events(result)
        assert len(batch.events) == 0

    def test_entry_triggered_none_produces_no_event(self):
        # Missing price → outcome=None → no event
        plan = _simple_entry_plan()
        bar  = HistoricalBarContext(bar_index=0, price_fields={})
        result = _evaluate(plan, bar)
        batch  = extract_signal_events(result)
        assert len(batch.events) == 0

    def test_exit_triggered_true_produces_exit_event(self):
        plan   = _simple_exit_plan()
        result = _evaluate(plan, _bar(0, 100.0))
        batch  = extract_signal_events(result)
        assert len(batch.events) == 1
        assert batch.events[0].kind == SignalEventKind.EXIT

    def test_empty_bars_empty_batch(self):
        plan   = _simple_entry_plan()
        result = _evaluate(plan)
        batch  = extract_signal_events(result)
        assert len(batch.events) == 0
        assert batch.summary.total_events == 0

    def test_plan_draft_id_preserved(self):
        plan   = _simple_entry_plan(draft_id="d42")
        result = _evaluate(plan, _bar(0, 100.0))
        batch  = extract_signal_events(result)
        assert batch.plan_draft_id == "d42"

    def test_plan_draft_id_none(self):
        plan   = _simple_entry_plan()
        result = _evaluate(plan, _bar(0, 100.0))
        batch  = extract_signal_events(result)
        assert batch.plan_draft_id is None


# ---------------------------------------------------------------------------
# TestExtractSignalEvents — traceability
# ---------------------------------------------------------------------------

class TestExtractSignalEventsTraceability:
    def test_bar_index_in_source(self):
        plan  = _simple_entry_plan()
        result = _evaluate(plan, _bar(7, 100.0))
        batch  = extract_signal_events(result)
        assert batch.events[0].source.bar_index == 7

    def test_timestamp_in_source(self):
        plan  = _simple_entry_plan()
        bar   = HistoricalBarContext(
            bar_index=0, price_fields={"close": 100.0}, timestamp=_T0,
        )
        result = _evaluate(plan, bar)
        batch  = extract_signal_events(result)
        assert batch.events[0].source.timestamp == _T0

    def test_timestamp_none_preserved(self):
        plan  = _simple_entry_plan()
        result = _evaluate(plan, _bar(0, 100.0))
        batch  = extract_signal_events(result)
        assert batch.events[0].source.timestamp is None

    def test_rule_id_in_source(self):
        plan   = _plan(_rule(_group(_condition()), rid="my_entry_rule"))
        result = _evaluate(plan, _bar(0, 100.0))
        batch  = extract_signal_events(result)
        assert batch.events[0].source.rule_id == "my_entry_rule"

    def test_rule_kind_entry_in_source(self):
        plan   = _simple_entry_plan()
        result = _evaluate(plan, _bar(0, 100.0))
        batch  = extract_signal_events(result)
        assert batch.events[0].source.rule_kind == "entry"

    def test_rule_kind_exit_in_source(self):
        plan   = _simple_exit_plan()
        result = _evaluate(plan, _bar(0, 100.0))
        batch  = extract_signal_events(result)
        assert batch.events[0].source.rule_kind == "exit"

    def test_rule_index_in_source(self):
        plan   = _plan(_rule(_group(_condition()), index=0))
        result = _evaluate(plan, _bar(0, 100.0))
        batch  = extract_signal_events(result)
        assert batch.events[0].source.rule_index == 0

    def test_event_id_format(self):
        plan   = _plan(_rule(_group(_condition()), rid="r1", index=0))
        result = _evaluate(plan, _bar(5, 100.0))
        batch  = extract_signal_events(result)
        eid    = batch.events[0].event_id
        assert "5" in eid
        assert "entry" in eid
        assert "r1" in eid

    def test_outcome_always_true_for_signal(self):
        plan   = _simple_entry_plan()
        result = _evaluate(plan, _bar(0, 100.0))
        batch  = extract_signal_events(result)
        assert batch.events[0].outcome is True


# ---------------------------------------------------------------------------
# TestExtractSignalEvents — ordering
# ---------------------------------------------------------------------------

class TestExtractSignalEventsOrdering:
    def test_entry_before_exit_same_bar(self):
        # Plan with exit rule first in list, entry rule second
        r_exit  = _rule(_group(_condition()), kind="exit",  index=0, rid="exit1")
        r_entry = _rule(_group(_condition()), kind="entry", index=1, rid="entry1")
        plan    = _plan(r_exit, r_entry)
        result  = _evaluate(plan, _bar(0, 100.0))
        batch   = extract_signal_events(result)
        kinds   = [e.kind for e in batch.events]
        assert kinds[0] == SignalEventKind.ENTRY
        assert kinds[1] == SignalEventKind.EXIT

    def test_bars_in_ascending_order(self):
        plan   = _simple_entry_plan()
        result = _evaluate(plan, _bar(0, 100.0), _bar(10, 100.0), _bar(20, 100.0))
        batch  = extract_signal_events(result)
        indices = [e.source.bar_index for e in batch.events]
        assert indices == sorted(indices)

    def test_multi_rule_ordering_by_index(self):
        r0 = _rule(_group(_condition()), kind="entry", index=0, rid="r0")
        r1 = _rule(_group(_condition()), kind="entry", index=1, rid="r1")
        r2 = _rule(_group(_condition()), kind="entry", index=2, rid="r2")
        plan   = _plan(r0, r1, r2)
        result = _evaluate(plan, _bar(0, 100.0))
        batch  = extract_signal_events(result)
        rule_ids = [e.source.rule_id for e in batch.events]
        assert rule_ids == ["r0", "r1", "r2"]

    def test_deterministic_same_inputs(self):
        plan = _simple_entry_plan()
        r1   = _evaluate(plan, _bar(0, 100.0), _bar(1, 10.0), _bar(2, 80.0))
        r2   = _evaluate(plan, _bar(0, 100.0), _bar(1, 10.0), _bar(2, 80.0))
        b1   = extract_signal_events(r1)
        b2   = extract_signal_events(r2)
        assert [e.event_id for e in b1.events] == [e.event_id for e in b2.events]


# ---------------------------------------------------------------------------
# TestExtractSignalEvents — summary counts
# ---------------------------------------------------------------------------

class TestExtractSignalEventsSummary:
    def test_total_events_count(self):
        plan   = _simple_entry_plan()
        result = _evaluate(plan, _bar(0, 100.0), _bar(1, 10.0), _bar(2, 80.0))
        batch  = extract_signal_events(result)
        assert batch.summary.total_events == 2  # bars 0 and 2

    def test_entry_events_count(self):
        plan   = _simple_entry_plan()
        result = _evaluate(plan, _bar(0, 100.0), _bar(1, 100.0), _bar(2, 10.0))
        batch  = extract_signal_events(result)
        assert batch.summary.entry_events == 2

    def test_exit_events_count(self):
        plan   = _simple_exit_plan()
        result = _evaluate(plan, _bar(0, 100.0), _bar(1, 100.0))
        batch  = extract_signal_events(result)
        assert batch.summary.exit_events == 2
        assert batch.summary.entry_events == 0

    def test_diagnostic_events_zero_by_default(self):
        plan  = _simple_entry_plan()
        result = _evaluate(plan, _bar(0, 100.0))
        batch  = extract_signal_events(result)
        assert batch.summary.diagnostic_events == 0

    def test_bars_with_events_single(self):
        plan   = _simple_entry_plan()
        result = _evaluate(plan, _bar(5, 100.0))
        batch  = extract_signal_events(result)
        assert batch.summary.bars_with_events == 1

    def test_bars_with_events_multi(self):
        plan   = _simple_entry_plan()
        result = _evaluate(plan, _bar(0, 100.0), _bar(1, 10.0), _bar(2, 80.0))
        batch  = extract_signal_events(result)
        assert batch.summary.bars_with_events == 2  # bars 0 and 2

    def test_first_event_bar_index(self):
        plan   = _simple_entry_plan()
        result = _evaluate(plan, _bar(0, 10.0), _bar(1, 10.0), _bar(3, 100.0))
        batch  = extract_signal_events(result)
        assert batch.summary.first_event_bar_index == 3

    def test_last_event_bar_index(self):
        plan   = _simple_entry_plan()
        result = _evaluate(plan, _bar(0, 100.0), _bar(1, 100.0), _bar(2, 10.0))
        batch  = extract_signal_events(result)
        assert batch.summary.last_event_bar_index == 1

    def test_first_last_none_when_empty(self):
        plan   = _simple_entry_plan()
        result = _evaluate(plan, _bar(0, 10.0))
        batch  = extract_signal_events(result)
        assert batch.summary.first_event_bar_index is None
        assert batch.summary.last_event_bar_index  is None

    def test_both_entry_and_exit_counted(self):
        r_entry = _rule(_group(_condition()), kind="entry", index=0, rid="e")
        r_exit  = _rule(_group(_condition()), kind="exit",  index=1, rid="x")
        plan    = _plan(r_entry, r_exit)
        result  = _evaluate(plan, _bar(0, 100.0))
        batch   = extract_signal_events(result)
        assert batch.summary.entry_events == 1
        assert batch.summary.exit_events  == 1
        assert batch.summary.total_events == 2
        assert batch.summary.bars_with_events == 1

    def test_no_pnl_in_summary(self):
        batch = extract_signal_events(_evaluate(_simple_entry_plan(), _bar(0, 100.0)))
        assert not hasattr(batch.summary, "pnl")
        assert not hasattr(batch.summary, "profit")


# ---------------------------------------------------------------------------
# TestExtractSignalEvents — multi-bar, multi-rule scenarios
# ---------------------------------------------------------------------------

class TestExtractSignalEventsScenarios:
    def test_multiple_bars_multiple_events(self):
        plan   = _simple_entry_plan()
        bars   = [_bar(i, 100.0 if i % 2 == 0 else 10.0) for i in range(6)]
        result = _evaluate(plan, *bars)
        batch  = extract_signal_events(result)
        assert batch.summary.total_events == 3
        triggered_bars = [e.source.bar_index for e in batch.events]
        assert triggered_bars == [0, 2, 4]

    def test_none_outcome_bars_not_counted(self):
        # bars with missing price → outcome=None
        plan = _simple_entry_plan()
        good = _bar(0, 100.0)
        bad  = HistoricalBarContext(bar_index=1, price_fields={})
        result = _evaluate(plan, good, bad)
        batch  = extract_signal_events(result)
        assert batch.summary.total_events == 1
        assert batch.events[0].source.bar_index == 0

    def test_multi_rule_same_bar(self):
        r1 = _rule(_group(_condition()), kind="entry", index=0, rid="r1")
        r2 = _rule(_group(_condition()), kind="entry", index=1, rid="r2")
        plan   = _plan(r1, r2)
        result = _evaluate(plan, _bar(0, 100.0))
        batch  = extract_signal_events(result)
        assert len(batch.events) == 2

    def test_events_tuple_is_immutable(self):
        plan   = _simple_entry_plan()
        result = _evaluate(plan, _bar(0, 100.0))
        batch  = extract_signal_events(result)
        assert isinstance(batch.events, tuple)

    def test_event_id_unique_per_event(self):
        r1 = _rule(_group(_condition()), kind="entry", index=0, rid="r1")
        r2 = _rule(_group(_condition()), kind="entry", index=1, rid="r2")
        plan   = _plan(r1, r2)
        result = _evaluate(plan, _bar(0, 100.0), _bar(1, 100.0))
        batch  = extract_signal_events(result)
        ids    = [e.event_id for e in batch.events]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# TestSignalEventsAPI
# ---------------------------------------------------------------------------

_SEMANTICS = {
    "entry_rules": [{
        "rule_id": "r1", "label": "Entry",
        "condition_group": {
            "group_id": "g1", "operator": "AND",
            "conditions": [{
                "condition_id": "c1", "label": None,
                "left":  {"kind": "price",    "ref": "close"},
                "operator": ">",
                "right": {"kind": "constant", "ref": "50"},
            }],
        },
    }],
    "exit_rules": [],
}


def _api_bar(index: int, close: float) -> dict:
    return {"bar_index": index, "price_fields": {"close": close}, "tool_outputs": {}}


def _api_payload(bars: list[dict], semantics=None) -> dict:
    return {
        "semantics": semantics or _SEMANTICS,
        "bars": bars,
    }


class TestSignalEventsAPI:
    def test_returns_200(self):
        resp = _CLIENT.post(
            "/semantics/extract-signal-events",
            json=_api_payload([_api_bar(0, 100.0)]),
        )
        assert resp.status_code == 200

    def test_entry_event_in_response(self):
        resp = _CLIENT.post(
            "/semantics/extract-signal-events",
            json=_api_payload([_api_bar(0, 100.0)]),
        )
        data = resp.json()
        assert data["summary"]["entry_events"] == 1

    def test_no_entry_event_below_threshold(self):
        resp = _CLIENT.post(
            "/semantics/extract-signal-events",
            json=_api_payload([_api_bar(0, 10.0)]),
        )
        data = resp.json()
        assert data["summary"]["total_events"] == 0
        assert data["events"] == []

    def test_multiple_bars(self):
        resp = _CLIENT.post(
            "/semantics/extract-signal-events",
            json=_api_payload([_api_bar(0, 100.0), _api_bar(1, 20.0), _api_bar(2, 80.0)]),
        )
        data = resp.json()
        assert data["summary"]["total_events"] == 2

    def test_empty_bars(self):
        resp = _CLIENT.post(
            "/semantics/extract-signal-events",
            json=_api_payload([]),
        )
        data = resp.json()
        assert data["summary"]["total_events"] == 0

    def test_plan_draft_id_null(self):
        resp = _CLIENT.post(
            "/semantics/extract-signal-events",
            json=_api_payload([_api_bar(0, 100.0)]),
        )
        assert resp.json()["plan_draft_id"] is None

    def test_event_kind_in_response(self):
        resp = _CLIENT.post(
            "/semantics/extract-signal-events",
            json=_api_payload([_api_bar(0, 100.0)]),
        )
        ev = resp.json()["events"][0]
        assert ev["kind"] == "entry"

    def test_event_source_bar_index(self):
        resp = _CLIENT.post(
            "/semantics/extract-signal-events",
            json=_api_payload([_api_bar(7, 100.0)]),
        )
        ev = resp.json()["events"][0]
        assert ev["source"]["bar_index"] == 7

    def test_missing_semantics_422(self):
        resp = _CLIENT.post(
            "/semantics/extract-signal-events",
            json={"bars": []},
        )
        assert resp.status_code == 422

    def test_invalid_body_422(self):
        resp = _CLIENT.post(
            "/semantics/extract-signal-events",
            json={"bad": "data"},
        )
        assert resp.status_code == 422

    def test_invalid_semantics_422(self):
        resp = _CLIENT.post(
            "/semantics/extract-signal-events",
            json={"semantics": {"entry_rules": "not_a_list", "exit_rules": []}, "bars": []},
        )
        assert resp.status_code == 422

    def test_extra_field_rejected(self):
        body = _api_payload([])
        body["unexpected"] = "value"
        resp = _CLIENT.post("/semantics/extract-signal-events", json=body)
        assert resp.status_code == 422

    def test_deterministic_same_inputs(self):
        p  = _api_payload([_api_bar(0, 100.0), _api_bar(1, 20.0)])
        r1 = _CLIENT.post("/semantics/extract-signal-events", json=p).json()
        r2 = _CLIENT.post("/semantics/extract-signal-events", json=p).json()
        assert r1["summary"]["total_events"] == r2["summary"]["total_events"]
        assert [e["event_id"] for e in r1["events"]] == [e["event_id"] for e in r2["events"]]

    def test_bars_with_events_in_summary(self):
        resp = _CLIENT.post(
            "/semantics/extract-signal-events",
            json=_api_payload([_api_bar(0, 100.0), _api_bar(1, 10.0)]),
        )
        assert resp.json()["summary"]["bars_with_events"] == 1


# ---------------------------------------------------------------------------
# Architecture boundary
# ---------------------------------------------------------------------------

_FORBIDDEN = (
    "strategy_runtime",
    "backtesting",
    "backend.execution",
    "forward_testing",
)

_BOUNDARY_MODULES = [
    "backend.strategy_registry.signal_events",
    "backend.strategy_registry.signal_event_extractor",
]


class TestArchitectureBoundary:
    @pytest.mark.parametrize("module_name", _BOUNDARY_MODULES)
    @pytest.mark.parametrize("forbidden", _FORBIDDEN)
    def test_no_forbidden_import(self, module_name: str, forbidden: str):
        mod  = importlib.import_module(module_name)
        src  = inspect.getsource(mod)
        lines = [
            ln for ln in src.splitlines()
            if ln.strip().startswith(("import ", "from ")) and forbidden in ln
        ]
        assert lines == [], f"{module_name} imports from '{forbidden}': {lines}"

    def test_signal_event_has_no_order_attr(self):
        ev = SignalEvent(
            event_id="0:entry:0:r1",
            kind=SignalEventKind.ENTRY,
            source=SignalEventSource(
                bar_index=0, timestamp=None,
                rule_id="r1", rule_kind="entry", rule_index=0,
            ),
            outcome=True,
        )
        assert not hasattr(ev, "order")
        assert not hasattr(ev, "trade")
        assert not hasattr(ev, "broker")
        assert not hasattr(ev, "position")

    def test_signal_event_batch_has_no_portfolio(self):
        batch = SignalEventBatch(
            plan_draft_id=None,
            events=(),
            summary=SignalEventSummary(
                total_events=0, entry_events=0, exit_events=0,
                diagnostic_events=0, bars_with_events=0,
                first_event_bar_index=None, last_event_bar_index=None,
            ),
        )
        assert not hasattr(batch, "portfolio")
        assert not hasattr(batch, "positions")
        assert not hasattr(batch, "pnl")
