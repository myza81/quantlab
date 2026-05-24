"""
Phase 2O.7 — Plan Inspection API tests.

Covers:
- GET /drafts/{draft_id}/semantics/plan — draft with semantics
- GET /drafts/{draft_id}/semantics/plan — draft without semantics (compiled=False)
- GET /drafts/{draft_id}/semantics/plan — draft not found (404)
- POST /semantics/plan — payload inspection
- POST /semantics/plan — invalid body (422)
- Response shape: compiled, evaluation_plan, summary, binding_valid
- summary fields: topology, dependencies, diagnostics, rules
- topology: condition/group/rule counts
- topology: operator_usage
- dependency: price_fields, constants surfaced
- binding_valid populated for draft endpoint
- binding_dependency_summary populated for draft endpoint
- payload endpoint: binding_valid is None (no draft context)
- deterministic responses: same draft → same summary structure
"""
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.routes.drafts import get_draft_repository
from backend.strategy_registry.draft_repository import DraftRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path):
    return DraftRepository(tmp_path)

@pytest.fixture
def client(repo):
    app.dependency_overrides[get_draft_repository] = lambda: repo
    yield TestClient(app)
    app.dependency_overrides.clear()


def _create_draft(client: TestClient, draft_id: str = "draft-1") -> None:
    client.post("/drafts", json={
        "draft_id": draft_id,
        "display_name": "Test Draft",
        "toolset": {"toolset_id": draft_id, "tools": []},
    })


_PRICE_CLOSE = {"kind": "price", "ref": "close"}
_CONST_30    = {"kind": "constant", "ref": "30"}
_TOOL_SMA    = {"kind": "tool_output", "ref": "sma_fast.sma"}


def _simple_semantics():
    return {
        "entry_rules": [{
            "condition_group": {
                "operator": "AND",
                "conditions": [{
                    "left":     _PRICE_CLOSE,
                    "operator": ">",
                    "right":    _CONST_30,
                }],
            },
        }],
        "exit_rules": [{
            "condition_group": {
                "operator": "AND",
                "conditions": [{
                    "left":     _PRICE_CLOSE,
                    "operator": "<",
                    "right":    _CONST_30,
                }],
            },
        }],
    }


def _draft_with_semantics(
    client: TestClient,
    draft_id: str = "draft-1",
    semantics: dict | None = None,
) -> None:
    _create_draft(client, draft_id)
    client.put(
        f"/drafts/{draft_id}/semantics",
        json={"semantics": semantics or _simple_semantics()},
    )


# ---------------------------------------------------------------------------
# GET /drafts/{draft_id}/semantics/plan
# ---------------------------------------------------------------------------

class TestDraftPlanInspectionEndpoint:
    def test_returns_200_with_semantics(self, client):
        _draft_with_semantics(client)
        resp = client.get("/drafts/draft-1/semantics/plan")
        assert resp.status_code == 200

    def test_returns_404_unknown_draft(self, client):
        resp = client.get("/drafts/nonexistent/semantics/plan")
        assert resp.status_code == 404

    def test_compiled_true(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        assert data["compiled"] is True

    def test_errors_empty_on_success(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        assert data["errors"] == []

    def test_evaluation_plan_present(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        assert data["evaluation_plan"] is not None

    def test_summary_present(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        assert data["summary"] is not None

    def test_summary_has_topology(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        assert "topology" in data["summary"]

    def test_topology_entry_rule_count(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        assert data["summary"]["topology"]["entry_rule_count"] == 1

    def test_topology_exit_rule_count(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        assert data["summary"]["topology"]["exit_rule_count"] == 1

    def test_topology_total_condition_nodes(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        # 1 entry condition + 1 exit condition = 2
        assert data["summary"]["topology"]["total_condition_nodes"] == 2

    def test_topology_total_group_nodes(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        # 1 entry group + 1 exit group = 2
        assert data["summary"]["topology"]["total_group_nodes"] == 2

    def test_topology_max_nesting_depth_flat(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        assert data["summary"]["topology"]["max_nesting_depth"] == 0

    def test_topology_operator_usage(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        op_usage = data["summary"]["topology"]["operator_usage"]
        assert ">" in op_usage
        assert "<" in op_usage

    def test_dependencies_price_fields(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        assert "close" in data["summary"]["dependencies"]["price_fields"]

    def test_dependencies_constants(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        assert "30" in data["summary"]["dependencies"]["constants"]

    def test_rules_list_length(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        assert len(data["summary"]["rules"]) == 2

    def test_rules_kinds(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        kinds = {r["kind"] for r in data["summary"]["rules"]}
        assert kinds == {"entry", "exit"}

    def test_binding_valid_populated(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        assert "binding_valid" in data
        assert data["binding_valid"] is not None

    def test_binding_valid_true_no_tool_refs(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        assert data["binding_valid"] is True

    def test_binding_dependency_summary_populated(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        assert data["binding_dependency_summary"] is not None

    def test_diagnostics_in_summary(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        diag = data["summary"]["diagnostics"]
        assert "error_count" in diag
        assert "warning_count" in diag
        assert "info_count" in diag

    def test_total_rules_in_summary(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/plan").json()
        assert data["summary"]["total_rules"] == 2


class TestDraftPlanNoSemantics:
    def test_no_semantics_returns_200(self, client):
        _create_draft(client, "draft-empty")
        resp = client.get("/drafts/draft-empty/semantics/plan")
        assert resp.status_code == 200

    def test_no_semantics_compiled_false(self, client):
        _create_draft(client, "draft-empty")
        data = client.get("/drafts/draft-empty/semantics/plan").json()
        assert data["compiled"] is False

    def test_no_semantics_errors_populated(self, client):
        _create_draft(client, "draft-empty")
        data = client.get("/drafts/draft-empty/semantics/plan").json()
        assert len(data["errors"]) > 0

    def test_no_semantics_evaluation_plan_null(self, client):
        _create_draft(client, "draft-empty")
        data = client.get("/drafts/draft-empty/semantics/plan").json()
        assert data["evaluation_plan"] is None

    def test_no_semantics_summary_null(self, client):
        _create_draft(client, "draft-empty")
        data = client.get("/drafts/draft-empty/semantics/plan").json()
        assert data["summary"] is None


# ---------------------------------------------------------------------------
# POST /semantics/plan
# ---------------------------------------------------------------------------

class TestPayloadPlanInspectionEndpoint:
    def test_returns_200(self, client):
        resp = client.post("/semantics/plan", json={"semantics": _simple_semantics()})
        assert resp.status_code == 200

    def test_compiled_true(self, client):
        data = client.post("/semantics/plan", json={"semantics": _simple_semantics()}).json()
        assert data["compiled"] is True

    def test_summary_present(self, client):
        data = client.post("/semantics/plan", json={"semantics": _simple_semantics()}).json()
        assert data["summary"] is not None

    def test_binding_valid_none_no_draft_context(self, client):
        data = client.post("/semantics/plan", json={"semantics": _simple_semantics()}).json()
        assert data["binding_valid"] is None

    def test_binding_diagnostics_empty_no_draft_context(self, client):
        data = client.post("/semantics/plan", json={"semantics": _simple_semantics()}).json()
        assert data["binding_diagnostics"] == []

    def test_draft_id_null(self, client):
        data = client.post("/semantics/plan", json={"semantics": _simple_semantics()}).json()
        assert data["draft_id"] is None

    def test_topology_condition_count(self, client):
        data = client.post("/semantics/plan", json={"semantics": _simple_semantics()}).json()
        assert data["summary"]["topology"]["total_condition_nodes"] == 2

    def test_invalid_body_422(self, client):
        resp = client.post("/semantics/plan", json={"bad": "payload"})
        assert resp.status_code == 422

    def test_deterministic_two_calls(self, client):
        payload = {"semantics": _simple_semantics()}
        d1 = client.post("/semantics/plan", json=payload).json()
        d2 = client.post("/semantics/plan", json=payload).json()
        assert d1["summary"]["topology"]["total_condition_nodes"] == \
               d2["summary"]["topology"]["total_condition_nodes"]
        assert d1["summary"]["topology"]["operator_usage"] == \
               d2["summary"]["topology"]["operator_usage"]
