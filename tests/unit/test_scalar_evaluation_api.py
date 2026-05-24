"""
Phase 2P.1 — Scalar Evaluation API tests.

Covers:
    POST /semantics/evaluate-scalar
    - valid semantics + sufficient context → trace returned
    - entry_triggered / exit_triggered populated
    - condition true/false from real scalar values
    - empty scalar context → unresolved operand diagnostics, outcome=None
    - compilation failure → 422
    - missing semantics field → 422 validation error
    - evaluation_id respected when supplied
    - evaluation_id auto-generated when not supplied
    - draft_id=None (payload endpoint, no draft)
    - rule_results count matches rule count
"""
from fastapi.testclient import TestClient

from backend.api.main import app

_CLIENT = TestClient(app)


def _simple_semantics(operator: str = ">") -> dict:
    return {
        "entry_rules": [{
            "rule_id": "entry_rule_1",
            "label":   "Entry",
            "condition_group": {
                "group_id": "g1",
                "operator": "AND",
                "conditions": [{
                    "condition_id": "c1",
                    "label":        None,
                    "left":  {"kind": "price",    "ref": "close"},
                    "operator": operator,
                    "right": {"kind": "constant", "ref": "50"},
                }],
            },
        }],
        "exit_rules": [],
    }


def _payload(
    operator: str = ">",
    scalar_context: dict | None = None,
    evaluation_id: str | None = None,
) -> dict:
    body: dict = {
        "semantics": _simple_semantics(operator),
        "scalar_context": {"price.close": 100.0} if scalar_context is None else scalar_context,
    }
    if evaluation_id is not None:
        body["evaluation_id"] = evaluation_id
    return body


class TestScalarEvaluationEndpoint:
    def test_returns_200(self):
        resp = _CLIENT.post("/semantics/evaluate-scalar", json=_payload())
        assert resp.status_code == 200

    def test_entry_triggered_true(self):
        # close (100.0) > 50 → True
        resp = _CLIENT.post("/semantics/evaluate-scalar", json=_payload(">", {"price.close": 100.0}))
        data = resp.json()
        assert data["entry_triggered"] is True

    def test_entry_triggered_false(self):
        # close (30.0) > 50 → False
        resp = _CLIENT.post("/semantics/evaluate-scalar", json=_payload(">", {"price.close": 30.0}))
        data = resp.json()
        assert data["entry_triggered"] is False

    def test_exit_triggered_null_when_no_exit_rules(self):
        resp = _CLIENT.post("/semantics/evaluate-scalar", json=_payload())
        data = resp.json()
        assert data["exit_triggered"] is None

    def test_rule_results_present(self):
        resp = _CLIENT.post("/semantics/evaluate-scalar", json=_payload())
        data = resp.json()
        assert len(data["rule_results"]) == 1

    def test_rule_kind_entry(self):
        resp = _CLIENT.post("/semantics/evaluate-scalar", json=_payload())
        data = resp.json()
        assert data["rule_results"][0]["kind"] == "entry"

    def test_evaluation_id_respected(self):
        resp = _CLIENT.post("/semantics/evaluate-scalar", json=_payload(evaluation_id="my-eval-123"))
        data = resp.json()
        assert data["evaluation_id"] == "my-eval-123"

    def test_evaluation_id_auto_generated_when_omitted(self):
        resp = _CLIENT.post("/semantics/evaluate-scalar", json=_payload())
        data = resp.json()
        assert isinstance(data["evaluation_id"], str)
        assert len(data["evaluation_id"]) > 0

    def test_draft_id_null(self):
        resp = _CLIENT.post("/semantics/evaluate-scalar", json=_payload())
        data = resp.json()
        assert data["plan_draft_id"] is None

    def test_empty_context_produces_none_trigger(self):
        # No price.close in context → unresolved operand → outcome=None
        resp = _CLIENT.post("/semantics/evaluate-scalar", json=_payload(scalar_context={}))
        data = resp.json()
        assert data["entry_triggered"] is None

    def test_eq_operator(self):
        resp = _CLIENT.post("/semantics/evaluate-scalar", json=_payload("==", {"price.close": 50.0}))
        data = resp.json()
        assert data["entry_triggered"] is True

    def test_neq_operator(self):
        resp = _CLIENT.post("/semantics/evaluate-scalar", json=_payload("!=", {"price.close": 100.0}))
        data = resp.json()
        assert data["entry_triggered"] is True

    def test_gte_operator(self):
        resp = _CLIENT.post("/semantics/evaluate-scalar", json=_payload(">=", {"price.close": 50.0}))
        data = resp.json()
        assert data["entry_triggered"] is True

    def test_lte_operator(self):
        resp = _CLIENT.post("/semantics/evaluate-scalar", json=_payload("<=", {"price.close": 50.0}))
        data = resp.json()
        assert data["entry_triggered"] is True

    def test_deterministic_same_inputs(self):
        p = _payload(">", {"price.close": 100.0}, "eval-det")
        r1 = _CLIENT.post("/semantics/evaluate-scalar", json=p)
        r2 = _CLIENT.post("/semantics/evaluate-scalar", json=p)
        assert r1.json()["entry_triggered"] == r2.json()["entry_triggered"]

    def test_missing_semantics_422(self):
        resp = _CLIENT.post("/semantics/evaluate-scalar", json={"scalar_context": {}})
        assert resp.status_code == 422

    def test_invalid_body_422(self):
        resp = _CLIENT.post("/semantics/evaluate-scalar", json={"bad": "data"})
        assert resp.status_code == 422

    def test_extra_fields_rejected(self):
        body = _payload()
        body["unexpected_field"] = "value"
        resp = _CLIENT.post("/semantics/evaluate-scalar", json=body)
        assert resp.status_code == 422

    def test_compilation_failure_returns_422(self):
        bad_body = {
            "semantics": {
                "entry_rules": "not_a_list",
                "exit_rules": [],
            },
            "scalar_context": {},
        }
        resp = _CLIENT.post("/semantics/evaluate-scalar", json=bad_body)
        assert resp.status_code == 422

    def test_tool_output_operand_resolved(self):
        semantics = {
            "entry_rules": [{
                "rule_id": "r1",
                "label":   None,
                "condition_group": {
                    "group_id": "g1",
                    "operator": "AND",
                    "conditions": [{
                        "condition_id": "c1",
                        "label": None,
                        "left":  {"kind": "tool_output", "ref": "sma_fast.value"},
                        "operator": ">",
                        "right": {"kind": "tool_output", "ref": "sma_slow.value"},
                    }],
                },
            }],
            "exit_rules": [],
        }
        body = {
            "semantics": semantics,
            "scalar_context": {
                "tool.sma_fast.value": 102.0,
                "tool.sma_slow.value": 99.0,
            },
        }
        resp = _CLIENT.post("/semantics/evaluate-scalar", json=body)
        assert resp.status_code == 200
        assert resp.json()["entry_triggered"] is True
