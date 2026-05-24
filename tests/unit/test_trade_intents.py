"""
Phase 2P.5 — Trade Intent Contract Layer unit tests.

Coverage:
    TradeIntentAction       — enum values, absent short-sell/leverage
    TradeIntentSource       — traceability fields, frozen
    TradeIntent             — frozen, no order/price/quantity fields
    TradeIntentSummary      — counts, first/last bar index
    TradeIntentBatch        — frozen, ignored_event_ids, plan_draft_id
    extract_trade_intents() — entry→open_long, exit→close_long,
                              diagnostic ignored, ordering, intent IDs,
                              summary counts, empty batch
    API endpoint            — POST /semantics/extract-trade-intents
    Architecture boundary   — no forbidden imports
"""
from __future__ import annotations

import importlib
import inspect
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
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
from backend.strategy_registry.trade_intent_extractor import extract_trade_intents
from backend.strategy_registry.trade_intents import (
    TradeIntent,
    TradeIntentAction,
    TradeIntentBatch,
    TradeIntentSource,
    TradeIntentSummary,
)

_CLIENT = TestClient(app)
_NOW    = datetime(2026, 5, 22, tzinfo=timezone.utc)
_T0     = datetime(2026, 1, 1, tzinfo=timezone.utc)
_T1     = datetime(2026, 1, 2, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Plan / bar helpers (mirrors test_signal_events.py)
# ---------------------------------------------------------------------------

def _condition(operator=">", right_ref="50", cid="c1") -> ConditionPlanNode:
    return ConditionPlanNode(
        condition_id=cid,
        left_kind="price", left_ref="close",
        operator=operator,
        right_kind="constant", right_ref=right_ref,
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
        bar_index=index, price_fields={"close": close}, timestamp=timestamp,
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


def _make_event_batch(*bars_and_plans) -> SignalEventBatch:
    """Evaluate and extract a signal event batch from plan + bars."""
    plan, *bars = bars_and_plans
    result = _evaluate(plan, *bars)
    return extract_signal_events(result)


def _empty_signal_batch(draft_id=None) -> SignalEventBatch:
    return SignalEventBatch(
        plan_draft_id=draft_id,
        events=(),
        summary=SignalEventSummary(
            total_events=0, entry_events=0, exit_events=0,
            diagnostic_events=0, bars_with_events=0,
            first_event_bar_index=None, last_event_bar_index=None,
        ),
    )


def _make_signal_event(
    event_id:   str = "0:entry:0:r1",
    kind:       SignalEventKind = SignalEventKind.ENTRY,
    bar_index:  int = 0,
    timestamp:  datetime | None = None,
    rule_id:    str | None = "r1",
    rule_kind:  str = "entry",
    rule_index: int = 0,
) -> SignalEvent:
    return SignalEvent(
        event_id=event_id,
        kind=kind,
        source=SignalEventSource(
            bar_index=bar_index, timestamp=timestamp,
            rule_id=rule_id, rule_kind=rule_kind, rule_index=rule_index,
        ),
        outcome=True,
    )


def _batch_from_events(*events: SignalEvent, draft_id=None) -> SignalEventBatch:
    entry_count = sum(1 for e in events if e.kind == SignalEventKind.ENTRY)
    exit_count  = sum(1 for e in events if e.kind == SignalEventKind.EXIT)
    diag_count  = sum(1 for e in events if e.kind == SignalEventKind.DIAGNOSTIC)
    bars        = {e.source.bar_index for e in events}
    first_bar   = min(e.source.bar_index for e in events) if events else None
    last_bar    = max(e.source.bar_index for e in events) if events else None
    return SignalEventBatch(
        plan_draft_id=draft_id,
        events=tuple(events),
        summary=SignalEventSummary(
            total_events=len(events),
            entry_events=entry_count,
            exit_events=exit_count,
            diagnostic_events=diag_count,
            bars_with_events=len(bars),
            first_event_bar_index=first_bar,
            last_event_bar_index=last_bar,
        ),
    )


# ---------------------------------------------------------------------------
# TestTradeIntentAction
# ---------------------------------------------------------------------------

class TestTradeIntentAction:
    def test_open_long_value(self):
        assert TradeIntentAction.OPEN_LONG == "open_long"

    def test_close_long_value(self):
        assert TradeIntentAction.CLOSE_LONG == "close_long"

    def test_no_short_sell_action(self):
        values = {a.value for a in TradeIntentAction}
        assert "short_sell" not in values
        assert "open_short" not in values

    def test_no_leverage_action(self):
        values = {a.value for a in TradeIntentAction}
        assert "leverage" not in values

    def test_no_margin_action(self):
        values = {a.value for a in TradeIntentAction}
        assert "margin" not in values

    def test_only_two_actions(self):
        assert len(TradeIntentAction) == 2


# ---------------------------------------------------------------------------
# TestTradeIntentSource
# ---------------------------------------------------------------------------

class TestTradeIntentSource:
    def _source(self, **kwargs):
        defaults = dict(
            signal_event_id="0:entry:0:r1",
            bar_index=0, timestamp=None,
            rule_id="r1", rule_kind="entry",
        )
        defaults.update(kwargs)
        return TradeIntentSource(**defaults)

    def test_signal_event_id_stored(self):
        assert self._source(signal_event_id="ev99").signal_event_id == "ev99"

    def test_bar_index_stored(self):
        assert self._source(bar_index=5).bar_index == 5

    def test_timestamp_stored(self):
        assert self._source(timestamp=_T0).timestamp == _T0

    def test_timestamp_none(self):
        assert self._source(timestamp=None).timestamp is None

    def test_rule_id_stored(self):
        assert self._source(rule_id="my_rule").rule_id == "my_rule"

    def test_rule_id_none(self):
        assert self._source(rule_id=None).rule_id is None

    def test_rule_kind_entry(self):
        assert self._source(rule_kind="entry").rule_kind == "entry"

    def test_rule_kind_exit(self):
        assert self._source(rule_kind="exit").rule_kind == "exit"

    def test_frozen(self):
        src = self._source()
        with pytest.raises(Exception):
            src.bar_index = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestTradeIntent
# ---------------------------------------------------------------------------

class TestTradeIntent:
    def _intent(self, **kwargs):
        defaults = dict(
            intent_id="intent:0:entry:0:r1",
            action=TradeIntentAction.OPEN_LONG,
            source=TradeIntentSource(
                signal_event_id="0:entry:0:r1",
                bar_index=0, timestamp=None,
                rule_id="r1", rule_kind="entry",
            ),
        )
        defaults.update(kwargs)
        return TradeIntent(**defaults)

    def test_frozen(self):
        i = self._intent()
        with pytest.raises(Exception):
            i.action = TradeIntentAction.CLOSE_LONG  # type: ignore[misc]

    def test_intent_id_stored(self):
        assert self._intent(intent_id="intent:test").intent_id == "intent:test"

    def test_action_open_long(self):
        assert self._intent(action=TradeIntentAction.OPEN_LONG).action == TradeIntentAction.OPEN_LONG

    def test_action_close_long(self):
        assert self._intent(action=TradeIntentAction.CLOSE_LONG).action == TradeIntentAction.CLOSE_LONG

    def test_no_order_field(self):
        assert not hasattr(self._intent(), "order")

    def test_no_trade_field(self):
        assert not hasattr(self._intent(), "trade")

    def test_no_position_field(self):
        assert not hasattr(self._intent(), "position")

    def test_no_pnl_field(self):
        assert not hasattr(self._intent(), "pnl")

    def test_no_quantity_field(self):
        assert not hasattr(self._intent(), "quantity")

    def test_no_price_field(self):
        assert not hasattr(self._intent(), "price")

    def test_no_fill_field(self):
        assert not hasattr(self._intent(), "fill")

    def test_no_broker_field(self):
        assert not hasattr(self._intent(), "broker")


# ---------------------------------------------------------------------------
# TestTradeIntentSummary
# ---------------------------------------------------------------------------

class TestTradeIntentSummary:
    def _summary(self, **kwargs):
        defaults = dict(
            total_intents=0, open_long_intents=0, close_long_intents=0,
            ignored_signal_events=0,
            first_intent_bar_index=None, last_intent_bar_index=None,
        )
        defaults.update(kwargs)
        return TradeIntentSummary(**defaults)

    def test_frozen(self):
        s = self._summary()
        with pytest.raises(Exception):
            s.total_intents = 99  # type: ignore[misc]

    def test_empty_summary(self):
        s = self._summary()
        assert s.total_intents == 0
        assert s.first_intent_bar_index is None
        assert s.last_intent_bar_index  is None

    def test_counts_stored(self):
        s = self._summary(
            total_intents=3, open_long_intents=2, close_long_intents=1,
            ignored_signal_events=1,
            first_intent_bar_index=0, last_intent_bar_index=10,
        )
        assert s.total_intents         == 3
        assert s.open_long_intents     == 2
        assert s.close_long_intents    == 1
        assert s.ignored_signal_events == 1

    def test_no_pnl_in_summary(self):
        s = self._summary()
        assert not hasattr(s, "pnl")
        assert not hasattr(s, "profit")


# ---------------------------------------------------------------------------
# TestTradeIntentBatch
# ---------------------------------------------------------------------------

class TestTradeIntentBatch:
    def _empty_batch(self, draft_id=None):
        return TradeIntentBatch(
            plan_draft_id=draft_id,
            intents=(),
            summary=TradeIntentSummary(
                total_intents=0, open_long_intents=0, close_long_intents=0,
                ignored_signal_events=0,
                first_intent_bar_index=None, last_intent_bar_index=None,
            ),
            ignored_event_ids=(),
        )

    def test_frozen(self):
        b = self._empty_batch()
        with pytest.raises(Exception):
            b.intents = ()  # type: ignore[misc]

    def test_plan_draft_id_preserved(self):
        assert self._empty_batch(draft_id="d1").plan_draft_id == "d1"

    def test_plan_draft_id_none(self):
        assert self._empty_batch().plan_draft_id is None

    def test_no_portfolio_field(self):
        b = self._empty_batch()
        assert not hasattr(b, "portfolio")
        assert not hasattr(b, "positions")
        assert not hasattr(b, "pnl")


# ---------------------------------------------------------------------------
# TestExtractTradeIntents — basic mapping
# ---------------------------------------------------------------------------

class TestExtractTradeIntentsMapping:
    def test_entry_signal_produces_open_long(self):
        batch  = _make_event_batch(_simple_entry_plan(), _bar(0, 100.0))
        result = extract_trade_intents(batch)
        assert len(result.intents) == 1
        assert result.intents[0].action == TradeIntentAction.OPEN_LONG

    def test_exit_signal_produces_close_long(self):
        batch  = _make_event_batch(_simple_exit_plan(), _bar(0, 100.0))
        result = extract_trade_intents(batch)
        assert len(result.intents) == 1
        assert result.intents[0].action == TradeIntentAction.CLOSE_LONG

    def test_no_signal_no_intent(self):
        batch  = _make_event_batch(_simple_entry_plan(), _bar(0, 10.0))
        result = extract_trade_intents(batch)
        assert len(result.intents) == 0

    def test_empty_signal_batch_empty_intents(self):
        result = extract_trade_intents(_empty_signal_batch())
        assert len(result.intents) == 0

    def test_diagnostic_event_ignored(self):
        diag_ev = _make_signal_event(
            event_id="0:diag:0:r1",
            kind=SignalEventKind.DIAGNOSTIC,
            bar_index=0,
        )
        batch  = _batch_from_events(diag_ev)
        result = extract_trade_intents(batch)
        assert len(result.intents) == 0
        assert len(result.ignored_event_ids) == 1
        assert "0:diag:0:r1" in result.ignored_event_ids

    def test_plan_draft_id_propagated(self):
        batch  = _make_event_batch(_simple_entry_plan(draft_id="d99"), _bar(0, 100.0))
        result = extract_trade_intents(batch)
        assert result.plan_draft_id == "d99"

    def test_plan_draft_id_none(self):
        batch  = _make_event_batch(_simple_entry_plan(), _bar(0, 100.0))
        result = extract_trade_intents(batch)
        assert result.plan_draft_id is None


# ---------------------------------------------------------------------------
# TestExtractTradeIntents — traceability
# ---------------------------------------------------------------------------

class TestExtractTradeIntentsTraceability:
    def test_signal_event_id_in_source(self):
        batch  = _make_event_batch(_simple_entry_plan(), _bar(0, 100.0))
        result = extract_trade_intents(batch)
        ev_id  = batch.events[0].event_id
        assert result.intents[0].source.signal_event_id == ev_id

    def test_bar_index_in_source(self):
        batch  = _make_event_batch(_simple_entry_plan(), _bar(7, 100.0))
        result = extract_trade_intents(batch)
        assert result.intents[0].source.bar_index == 7

    def test_timestamp_in_source(self):
        plan = _simple_entry_plan()
        bar  = HistoricalBarContext(
            bar_index=0, price_fields={"close": 100.0}, timestamp=_T0,
        )
        batch  = extract_signal_events(_evaluate(plan, bar))
        result = extract_trade_intents(batch)
        assert result.intents[0].source.timestamp == _T0

    def test_timestamp_none_in_source(self):
        batch  = _make_event_batch(_simple_entry_plan(), _bar(0, 100.0))
        result = extract_trade_intents(batch)
        assert result.intents[0].source.timestamp is None

    def test_rule_id_in_source(self):
        plan  = _plan(_rule(_group(_condition()), rid="my_entry"))
        batch = extract_signal_events(_evaluate(plan, _bar(0, 100.0)))
        result = extract_trade_intents(batch)
        assert result.intents[0].source.rule_id == "my_entry"

    def test_rule_kind_entry_in_source(self):
        batch  = _make_event_batch(_simple_entry_plan(), _bar(0, 100.0))
        result = extract_trade_intents(batch)
        assert result.intents[0].source.rule_kind == "entry"

    def test_rule_kind_exit_in_source(self):
        batch  = _make_event_batch(_simple_exit_plan(), _bar(0, 100.0))
        result = extract_trade_intents(batch)
        assert result.intents[0].source.rule_kind == "exit"


# ---------------------------------------------------------------------------
# TestExtractTradeIntents — intent IDs
# ---------------------------------------------------------------------------

class TestExtractTradeIntentsIds:
    def test_intent_id_starts_with_intent_prefix(self):
        batch  = _make_event_batch(_simple_entry_plan(), _bar(0, 100.0))
        result = extract_trade_intents(batch)
        assert result.intents[0].intent_id.startswith("intent:")

    def test_intent_id_contains_signal_event_id(self):
        batch  = _make_event_batch(_simple_entry_plan(), _bar(0, 100.0))
        result = extract_trade_intents(batch)
        ev_id  = batch.events[0].event_id
        assert ev_id in result.intents[0].intent_id

    def test_intent_id_deterministic(self):
        plan = _simple_entry_plan()
        b1   = extract_signal_events(_evaluate(plan, _bar(0, 100.0)))
        b2   = extract_signal_events(_evaluate(plan, _bar(0, 100.0)))
        r1   = extract_trade_intents(b1)
        r2   = extract_trade_intents(b2)
        assert r1.intents[0].intent_id == r2.intents[0].intent_id

    def test_intent_ids_unique_across_events(self):
        r_entry = _rule(_group(_condition()), kind="entry", index=0, rid="e")
        r_exit  = _rule(_group(_condition()), kind="exit",  index=1, rid="x")
        plan    = _plan(r_entry, r_exit)
        batch   = extract_signal_events(_evaluate(plan, _bar(0, 100.0)))
        result  = extract_trade_intents(batch)
        ids     = [i.intent_id for i in result.intents]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# TestExtractTradeIntents — ordering
# ---------------------------------------------------------------------------

class TestExtractTradeIntentsOrdering:
    def test_ordering_preserved_from_signal_batch(self):
        plan   = _simple_entry_plan()
        bars   = [_bar(i, 100.0) for i in range(3)]
        batch  = extract_signal_events(_evaluate(plan, *bars))
        result = extract_trade_intents(batch)
        indices = [i.source.bar_index for i in result.intents]
        assert indices == sorted(indices)

    def test_entry_before_exit_same_bar(self):
        r_exit  = _rule(_group(_condition()), kind="exit",  index=0, rid="x")
        r_entry = _rule(_group(_condition()), kind="entry", index=1, rid="e")
        plan    = _plan(r_exit, r_entry)
        batch   = extract_signal_events(_evaluate(plan, _bar(0, 100.0)))
        result  = extract_trade_intents(batch)
        assert result.intents[0].action == TradeIntentAction.OPEN_LONG
        assert result.intents[1].action == TradeIntentAction.CLOSE_LONG

    def test_deterministic_same_inputs(self):
        plan = _simple_entry_plan()
        b    = extract_signal_events(_evaluate(plan, _bar(0, 100.0), _bar(1, 10.0), _bar(2, 80.0)))
        r1   = extract_trade_intents(b)
        r2   = extract_trade_intents(b)
        assert [i.intent_id for i in r1.intents] == [i.intent_id for i in r2.intents]


# ---------------------------------------------------------------------------
# TestExtractTradeIntents — summary counts
# ---------------------------------------------------------------------------

class TestExtractTradeIntentsSummary:
    def test_total_intents_count(self):
        plan   = _simple_entry_plan()
        batch  = extract_signal_events(_evaluate(plan, _bar(0, 100.0), _bar(1, 10.0), _bar(2, 80.0)))
        result = extract_trade_intents(batch)
        assert result.summary.total_intents == 2

    def test_open_long_count(self):
        plan   = _simple_entry_plan()
        batch  = extract_signal_events(_evaluate(plan, _bar(0, 100.0), _bar(1, 100.0)))
        result = extract_trade_intents(batch)
        assert result.summary.open_long_intents == 2

    def test_close_long_count(self):
        plan   = _simple_exit_plan()
        batch  = extract_signal_events(_evaluate(plan, _bar(0, 100.0), _bar(1, 100.0)))
        result = extract_trade_intents(batch)
        assert result.summary.close_long_intents == 2
        assert result.summary.open_long_intents  == 0

    def test_ignored_signal_events_count(self):
        diag = _make_signal_event(
            event_id="0:diag:0:r1",
            kind=SignalEventKind.DIAGNOSTIC,
        )
        entry = _make_signal_event(event_id="0:entry:0:r1")
        batch  = _batch_from_events(entry, diag)
        result = extract_trade_intents(batch)
        assert result.summary.ignored_signal_events == 1
        assert result.summary.total_intents == 1

    def test_first_intent_bar_index(self):
        plan   = _simple_entry_plan()
        batch  = extract_signal_events(_evaluate(plan, _bar(0, 10.0), _bar(3, 100.0)))
        result = extract_trade_intents(batch)
        assert result.summary.first_intent_bar_index == 3

    def test_last_intent_bar_index(self):
        plan   = _simple_entry_plan()
        batch  = extract_signal_events(_evaluate(plan, _bar(0, 100.0), _bar(1, 100.0), _bar(2, 10.0)))
        result = extract_trade_intents(batch)
        assert result.summary.last_intent_bar_index == 1

    def test_first_last_none_when_empty(self):
        result = extract_trade_intents(_empty_signal_batch())
        assert result.summary.first_intent_bar_index is None
        assert result.summary.last_intent_bar_index  is None

    def test_both_action_types_counted(self):
        r_e = _rule(_group(_condition()), kind="entry", index=0, rid="e")
        r_x = _rule(_group(_condition()), kind="exit",  index=1, rid="x")
        plan   = _plan(r_e, r_x)
        batch  = extract_signal_events(_evaluate(plan, _bar(0, 100.0)))
        result = extract_trade_intents(batch)
        assert result.summary.open_long_intents  == 1
        assert result.summary.close_long_intents == 1
        assert result.summary.total_intents      == 2


# ---------------------------------------------------------------------------
# TestTradeIntentsAPI
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


def _build_signal_batch_payload(bars: list[dict], semantics=None) -> dict:
    """Build a SignalEventBatch JSON payload by hitting the evaluate+extract pipeline."""
    resp = _CLIENT.post(
        "/semantics/extract-signal-events",
        json={"semantics": semantics or _SEMANTICS, "bars": bars},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestTradeIntentsAPI:
    def test_returns_200(self):
        payload = _build_signal_batch_payload([_api_bar(0, 100.0)])
        resp    = _CLIENT.post("/semantics/extract-trade-intents", json=payload)
        assert resp.status_code == 200

    def test_open_long_intent_in_response(self):
        payload = _build_signal_batch_payload([_api_bar(0, 100.0)])
        resp    = _CLIENT.post("/semantics/extract-trade-intents", json=payload)
        data    = resp.json()
        assert data["summary"]["open_long_intents"] == 1
        assert data["summary"]["total_intents"]     == 1

    def test_no_intent_when_no_trigger(self):
        payload = _build_signal_batch_payload([_api_bar(0, 10.0)])
        resp    = _CLIENT.post("/semantics/extract-trade-intents", json=payload)
        data    = resp.json()
        assert data["summary"]["total_intents"] == 0
        assert data["intents"] == []

    def test_empty_signal_batch(self):
        payload = _build_signal_batch_payload([])
        resp    = _CLIENT.post("/semantics/extract-trade-intents", json=payload)
        data    = resp.json()
        assert data["summary"]["total_intents"] == 0

    def test_multiple_bars(self):
        payload = _build_signal_batch_payload(
            [_api_bar(0, 100.0), _api_bar(1, 10.0), _api_bar(2, 80.0)]
        )
        resp = _CLIENT.post("/semantics/extract-trade-intents", json=payload)
        data = resp.json()
        assert data["summary"]["total_intents"] == 2

    def test_intent_action_in_response(self):
        payload = _build_signal_batch_payload([_api_bar(0, 100.0)])
        resp    = _CLIENT.post("/semantics/extract-trade-intents", json=payload)
        intent  = resp.json()["intents"][0]
        assert intent["action"] == "open_long"

    def test_intent_id_in_response(self):
        payload = _build_signal_batch_payload([_api_bar(0, 100.0)])
        resp    = _CLIENT.post("/semantics/extract-trade-intents", json=payload)
        intent  = resp.json()["intents"][0]
        assert intent["intent_id"].startswith("intent:")

    def test_source_bar_index_in_response(self):
        payload = _build_signal_batch_payload([_api_bar(7, 100.0)])
        resp    = _CLIENT.post("/semantics/extract-trade-intents", json=payload)
        assert resp.json()["intents"][0]["source"]["bar_index"] == 7

    def test_plan_draft_id_null(self):
        payload = _build_signal_batch_payload([_api_bar(0, 100.0)])
        resp    = _CLIENT.post("/semantics/extract-trade-intents", json=payload)
        assert resp.json()["plan_draft_id"] is None

    def test_deterministic_same_inputs(self):
        payload = _build_signal_batch_payload([_api_bar(0, 100.0), _api_bar(1, 10.0)])
        r1 = _CLIENT.post("/semantics/extract-trade-intents", json=payload).json()
        r2 = _CLIENT.post("/semantics/extract-trade-intents", json=payload).json()
        assert r1["summary"]["total_intents"] == r2["summary"]["total_intents"]
        assert [i["intent_id"] for i in r1["intents"]] == [i["intent_id"] for i in r2["intents"]]

    def test_invalid_body_422(self):
        resp = _CLIENT.post("/semantics/extract-trade-intents", json={"bad": "data"})
        assert resp.status_code == 422


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
    "backend.strategy_registry.trade_intents",
    "backend.strategy_registry.trade_intent_extractor",
]


class TestArchitectureBoundary:
    @pytest.mark.parametrize("module_name", _BOUNDARY_MODULES)
    @pytest.mark.parametrize("forbidden", _FORBIDDEN)
    def test_no_forbidden_import(self, module_name: str, forbidden: str):
        mod   = importlib.import_module(module_name)
        src   = inspect.getsource(mod)
        lines = [
            ln for ln in src.splitlines()
            if ln.strip().startswith(("import ", "from ")) and forbidden in ln
        ]
        assert lines == [], f"{module_name} imports from '{forbidden}': {lines}"

    def test_no_short_sell_in_action_enum(self):
        values = {a.value for a in TradeIntentAction}
        assert "short_sell"  not in values
        assert "open_short"  not in values
        assert "close_short" not in values

    def test_trade_intent_has_no_execution_fields(self):
        from backend.strategy_registry.trade_intents import TradeIntent, TradeIntentSource
        intent = TradeIntent(
            intent_id="intent:test",
            action=TradeIntentAction.OPEN_LONG,
            source=TradeIntentSource(
                signal_event_id="ev1",
                bar_index=0, timestamp=None,
                rule_id="r1", rule_kind="entry",
            ),
        )
        for field in ("order", "trade", "fill", "position", "pnl", "quantity",
                      "price", "broker", "margin", "leverage"):
            assert not hasattr(intent, field), f"TradeIntent should not have field '{field}'"

    def test_trade_intent_batch_has_no_portfolio_fields(self):
        batch = TradeIntentBatch(
            plan_draft_id=None,
            intents=(),
            summary=TradeIntentSummary(
                total_intents=0, open_long_intents=0, close_long_intents=0,
                ignored_signal_events=0,
                first_intent_bar_index=None, last_intent_bar_index=None,
            ),
            ignored_event_ids=(),
        )
        for field in ("portfolio", "positions", "pnl", "capital"):
            assert not hasattr(batch, field), f"TradeIntentBatch should not have field '{field}'"
