"""
Phase 2P.2 — Historical Evaluation API tests.

Covers:
    POST /semantics/evaluate-history
    - valid semantics + bars → result returned
    - bars_evaluated count matches input
    - entry_triggered_count / exit_triggered_count correct
    - per-bar entry_triggered populated
    - empty bars → 0 evaluated
    - missing price value in bar → outcome=None for that bar
    - crosses_above → outcome=None for that bar
    - plan_draft_id=None (payload endpoint)
    - evaluation_id present per bar trace
    - deterministic same inputs
    - invalid semantics → 422
    - missing semantics field → 422
    - extra fields rejected → 422
    - compilation failure → 422
"""
from fastapi.testclient import TestClient

from backend.api.main import app

_CLIENT = TestClient(app)

_SEMANTICS = {
    "entry_rules": [{
        "rule_id": "r1",
        "label":   "Entry",
        "condition_group": {
            "group_id":  "g1",
            "operator":  "AND",
            "conditions": [{
                "condition_id": "c1",
                "label":        None,
                "left":         {"kind": "price",    "ref": "close"},
                "operator":     ">",
                "right":        {"kind": "constant", "ref": "50"},
            }],
        },
    }],
    "exit_rules": [],
}


def _bar(index: int, close: float, timestamp: str | None = None) -> dict:
    b: dict = {"bar_index": index, "price_fields": {"close": close}, "tool_outputs": {}}
    if timestamp is not None:
        b["timestamp"] = timestamp
    return b


def _payload(bars: list[dict], semantics: dict | None = None) -> dict:
    return {
        "semantics": semantics or _SEMANTICS,
        "bars":      bars,
    }


class TestHistoricalEvaluationEndpoint:
    def test_returns_200(self):
        resp = _CLIENT.post("/semantics/evaluate-history", json=_payload([_bar(0, 100.0)]))
        assert resp.status_code == 200

    def test_bars_evaluated_matches_input(self):
        resp = _CLIENT.post("/semantics/evaluate-history",
                            json=_payload([_bar(0, 100.0), _bar(1, 40.0), _bar(2, 80.0)]))
        assert resp.json()["bars_evaluated"] == 3

    def test_entry_triggered_count(self):
        # 100 > 50 (True), 30 > 50 (False), 70 > 50 (True)
        resp = _CLIENT.post("/semantics/evaluate-history",
                            json=_payload([_bar(0, 100.0), _bar(1, 30.0), _bar(2, 70.0)]))
        assert resp.json()["entry_triggered_count"] == 2

    def test_exit_triggered_count_zero_no_exit_rules(self):
        resp = _CLIENT.post("/semantics/evaluate-history", json=_payload([_bar(0, 100.0)]))
        assert resp.json()["exit_triggered_count"] == 0

    def test_bar_results_count(self):
        resp = _CLIENT.post("/semantics/evaluate-history",
                            json=_payload([_bar(i, 100.0) for i in range(5)]))
        assert len(resp.json()["bar_results"]) == 5

    def test_bar_entry_triggered_true(self):
        resp = _CLIENT.post("/semantics/evaluate-history", json=_payload([_bar(0, 100.0)]))
        assert resp.json()["bar_results"][0]["entry_triggered"] is True

    def test_bar_entry_triggered_false(self):
        resp = _CLIENT.post("/semantics/evaluate-history", json=_payload([_bar(0, 20.0)]))
        assert resp.json()["bar_results"][0]["entry_triggered"] is False

    def test_empty_bars_returns_zero(self):
        resp = _CLIENT.post("/semantics/evaluate-history", json=_payload([]))
        data = resp.json()
        assert data["bars_evaluated"] == 0
        assert data["bar_results"] == []

    def test_plan_draft_id_null(self):
        resp = _CLIENT.post("/semantics/evaluate-history", json=_payload([_bar(0, 100.0)]))
        assert resp.json()["plan_draft_id"] is None

    def test_evaluation_id_in_trace(self):
        resp = _CLIENT.post("/semantics/evaluate-history", json=_payload([_bar(0, 100.0)]))
        trace = resp.json()["bar_results"][0]["trace"]
        assert isinstance(trace["evaluation_id"], str)
        assert len(trace["evaluation_id"]) > 0

    def test_bar_index_preserved(self):
        resp = _CLIENT.post("/semantics/evaluate-history",
                            json=_payload([_bar(10, 100.0), _bar(20, 100.0)]))
        indices = [r["bar_index"] for r in resp.json()["bar_results"]]
        assert indices == [10, 20]

    def test_missing_price_produces_none_trigger(self):
        bar = {"bar_index": 0, "price_fields": {}, "tool_outputs": {}}
        resp = _CLIENT.post("/semantics/evaluate-history", json=_payload([bar]))
        assert resp.json()["bar_results"][0]["entry_triggered"] is None
        assert resp.json()["entry_triggered_count"] == 0

    def test_deterministic_same_inputs(self):
        p  = _payload([_bar(0, 100.0), _bar(1, 30.0)])
        r1 = _CLIENT.post("/semantics/evaluate-history", json=p).json()
        r2 = _CLIENT.post("/semantics/evaluate-history", json=p).json()
        assert r1["entry_triggered_count"] == r2["entry_triggered_count"]
        assert [x["entry_triggered"] for x in r1["bar_results"]] == \
               [x["entry_triggered"] for x in r2["bar_results"]]

    def test_tool_output_operand_resolved(self):
        semantics = {
            "entry_rules": [{
                "rule_id": "r1", "label": None,
                "condition_group": {
                    "group_id": "g1", "operator": "AND",
                    "conditions": [{
                        "condition_id": "c1", "label": None,
                        "left":  {"kind": "tool_output", "ref": "sma.value"},
                        "operator": ">",
                        "right": {"kind": "constant",    "ref": "50"},
                    }],
                },
            }],
            "exit_rules": [],
        }
        bar = {"bar_index": 0, "price_fields": {"close": 100.0}, "tool_outputs": {"sma.value": 80.0}}
        resp = _CLIENT.post("/semantics/evaluate-history", json={"semantics": semantics, "bars": [bar]})
        assert resp.status_code == 200
        assert resp.json()["bar_results"][0]["entry_triggered"] is True

    def test_missing_semantics_422(self):
        resp = _CLIENT.post("/semantics/evaluate-history", json={"bars": []})
        assert resp.status_code == 422

    def test_invalid_body_422(self):
        resp = _CLIENT.post("/semantics/evaluate-history", json={"bad": "data"})
        assert resp.status_code == 422

    def test_extra_field_rejected(self):
        body = _payload([_bar(0, 100.0)])
        body["unexpected_field"] = "value"
        resp = _CLIENT.post("/semantics/evaluate-history", json=body)
        assert resp.status_code == 422

    def test_compilation_failure_422(self):
        bad = {"entry_rules": "not_a_list", "exit_rules": []}
        resp = _CLIENT.post("/semantics/evaluate-history", json={"semantics": bad, "bars": []})
        assert resp.status_code == 422

    def test_timestamp_accepted(self):
        bar = {"bar_index": 0, "price_fields": {"close": 100.0},
               "tool_outputs": {}, "timestamp": "2026-01-01T00:00:00Z"}
        resp = _CLIENT.post("/semantics/evaluate-history", json=_payload([bar]))
        assert resp.status_code == 200
        assert resp.json()["bar_results"][0]["timestamp"] is not None
