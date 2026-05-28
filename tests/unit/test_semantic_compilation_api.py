"""
Phase 2O.4 — Semantic Compilation API tests.

Covers:
- POST /drafts/{draft_id}/semantics/compile — draft with semantics
- POST /drafts/{draft_id}/semantics/compile — draft without semantics
- POST /drafts/{draft_id}/semantics/compile — draft not found (404)
- POST /semantics/compile — payload endpoint
- POST /semantics/compile — empty semantics
- POST /semantics/compile — invalid request body (422)
- Response shape: compiled, errors, diagnostics, evaluation_plan
- evaluation_plan includes dependencies, rule_nodes, node_count, compiled_at
- No execution side effects: compiled_at changes but plan is structurally stable
"""
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.routes.drafts import get_draft_repository
from backend.auth.dependencies import get_current_user
from backend.auth.models import User
from backend.strategy_registry.draft_repository import DraftRepository

_TEST_USER = User(
    user_id="test-user-id",
    username="testuser",
    email="test@example.com",
    password_hash="hash",
    created_at="2026-01-01T00:00:00+00:00",
    subscription_status="active",
)

# ---------------------------------------------------------------------------
# Test client + repository fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path):
    return DraftRepository(tmp_path)

@pytest.fixture
def client(repo):
    app.dependency_overrides[get_draft_repository] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    yield TestClient(app)
    app.dependency_overrides.clear()


def _create_draft(client: TestClient, draft_id: str = "draft-1") -> None:
    client.post("/drafts", json={
        "draft_id": draft_id,
        "display_name": "Test Draft",
        "toolset": {"toolset_id": draft_id, "tools": []},
    })


# ---------------------------------------------------------------------------
# Semantic payload helpers
# ---------------------------------------------------------------------------

_PRICE_CLOSE = {"kind": "price", "ref": "close"}
_CONST_30    = {"kind": "constant", "ref": "30"}
_TOOL_SMA    = {"kind": "tool_output", "ref": "sma_fast.value"}

def _simple_semantics_dict():
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


def _draft_with_semantics(client: TestClient, draft_id: str = "draft-1") -> None:
    """Create a draft via API and PUT semantics onto it."""
    _create_draft(client, draft_id)
    client.put(f"/drafts/{draft_id}/semantics", json={"semantics": _simple_semantics_dict()})


def _draft_without_semantics(client: TestClient, draft_id: str = "draft-empty") -> None:
    """Create a draft via API with no semantics."""
    _create_draft(client, draft_id)


# ---------------------------------------------------------------------------
# POST /drafts/{draft_id}/semantics/compile
# ---------------------------------------------------------------------------

class TestDraftCompileEndpoint:
    def test_compile_draft_with_semantics_returns_200(self, client):
        _draft_with_semantics(client)
        resp = client.post("/drafts/draft-1/semantics/compile")
        assert resp.status_code == 200

    def test_compile_draft_compiled_true(self, client):
        _draft_with_semantics(client)
        resp = client.post("/drafts/draft-1/semantics/compile")
        data = resp.json()
        assert data["compiled"] is True

    def test_compile_draft_errors_empty(self, client):
        _draft_with_semantics(client)
        resp = client.post("/drafts/draft-1/semantics/compile")
        assert resp.json()["errors"] == []

    def test_compile_draft_evaluation_plan_present(self, client):
        _draft_with_semantics(client)
        resp = client.post("/drafts/draft-1/semantics/compile")
        plan = resp.json()["evaluation_plan"]
        assert plan is not None

    def test_compile_draft_plan_has_draft_id(self, client):
        _draft_with_semantics(client, "my-draft")
        resp = client.post("/drafts/my-draft/semantics/compile")
        plan = resp.json()["evaluation_plan"]
        assert plan["draft_id"] == "my-draft"

    def test_compile_draft_plan_has_rule_nodes(self, client):
        _draft_with_semantics(client)
        resp = client.post("/drafts/draft-1/semantics/compile")
        plan = resp.json()["evaluation_plan"]
        assert len(plan["rule_nodes"]) == 2  # 1 entry + 1 exit

    def test_compile_draft_rule_kinds(self, client):
        _draft_with_semantics(client)
        resp = client.post("/drafts/draft-1/semantics/compile")
        kinds = [n["kind"] for n in resp.json()["evaluation_plan"]["rule_nodes"]]
        assert "entry" in kinds
        assert "exit" in kinds

    def test_compile_draft_dependencies_present(self, client):
        _draft_with_semantics(client)
        resp = client.post("/drafts/draft-1/semantics/compile")
        deps = resp.json()["evaluation_plan"]["dependencies"]
        assert "price_fields" in deps
        assert "tool_outputs" in deps
        assert "constants"    in deps

    def test_compile_draft_price_field_extracted(self, client):
        _draft_with_semantics(client)
        resp = client.post("/drafts/draft-1/semantics/compile")
        deps = resp.json()["evaluation_plan"]["dependencies"]
        assert "close" in deps["price_fields"]

    def test_compile_draft_constant_extracted(self, client):
        _draft_with_semantics(client)
        resp = client.post("/drafts/draft-1/semantics/compile")
        deps = resp.json()["evaluation_plan"]["dependencies"]
        assert "30" in deps["constants"]

    def test_compile_draft_node_count_positive(self, client):
        _draft_with_semantics(client)
        resp = client.post("/drafts/draft-1/semantics/compile")
        assert resp.json()["evaluation_plan"]["node_count"] > 0

    def test_compile_draft_has_compiled_at(self, client):
        _draft_with_semantics(client)
        resp = client.post("/drafts/draft-1/semantics/compile")
        assert resp.json()["evaluation_plan"]["compiled_at"] is not None

    def test_compile_draft_no_semantics_returns_200(self, client):
        _draft_without_semantics(client)
        resp = client.post("/drafts/draft-empty/semantics/compile")
        assert resp.status_code == 200

    def test_compile_draft_no_semantics_compiled_false(self, client):
        _draft_without_semantics(client)
        resp = client.post("/drafts/draft-empty/semantics/compile")
        data = resp.json()
        assert data["compiled"] is False

    def test_compile_draft_no_semantics_has_error(self, client):
        _draft_without_semantics(client)
        resp = client.post("/drafts/draft-empty/semantics/compile")
        assert len(resp.json()["errors"]) > 0

    def test_compile_draft_no_semantics_plan_null(self, client):
        _draft_without_semantics(client)
        resp = client.post("/drafts/draft-empty/semantics/compile")
        assert resp.json()["evaluation_plan"] is None

    def test_compile_draft_not_found_returns_404(self, client):
        resp = client.post("/drafts/nonexistent/semantics/compile")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /semantics/compile (payload endpoint)
# ---------------------------------------------------------------------------

class TestPayloadCompileEndpoint:
    def test_compile_payload_returns_200(self, client):
        resp = client.post("/semantics/compile", json={"semantics": _simple_semantics_dict()})
        assert resp.status_code == 200

    def test_compile_payload_compiled_true(self, client):
        resp = client.post("/semantics/compile", json={"semantics": _simple_semantics_dict()})
        assert resp.json()["compiled"] is True

    def test_compile_payload_errors_empty(self, client):
        resp = client.post("/semantics/compile", json={"semantics": _simple_semantics_dict()})
        assert resp.json()["errors"] == []

    def test_compile_payload_plan_present(self, client):
        resp = client.post("/semantics/compile", json={"semantics": _simple_semantics_dict()})
        assert resp.json()["evaluation_plan"] is not None

    def test_compile_payload_draft_id_null(self, client):
        resp = client.post("/semantics/compile", json={"semantics": _simple_semantics_dict()})
        assert resp.json()["evaluation_plan"]["draft_id"] is None

    def test_compile_payload_has_dependencies(self, client):
        resp = client.post("/semantics/compile", json={"semantics": _simple_semantics_dict()})
        plan = resp.json()["evaluation_plan"]
        assert "dependencies" in plan

    def test_compile_empty_semantics_compiled_true(self, client):
        """Empty semantics compiles successfully with a warning."""
        empty = {"entry_rules": [], "exit_rules": []}
        resp = client.post("/semantics/compile", json={"semantics": empty})
        data = resp.json()
        assert resp.status_code == 200
        assert data["compiled"] is True
        assert data["evaluation_plan"]["rule_nodes"] == []

    def test_compile_empty_semantics_has_warning(self, client):
        empty = {"entry_rules": [], "exit_rules": []}
        resp = client.post("/semantics/compile", json={"semantics": empty})
        diags = resp.json()["diagnostics"]
        assert len(diags) == 1
        assert diags[0]["severity"] == "warning"

    def test_compile_payload_invalid_body_422(self, client):
        resp = client.post("/semantics/compile", json={"semantics": "not-a-dict"})
        assert resp.status_code == 422

    def test_compile_payload_missing_body_422(self, client):
        resp = client.post("/semantics/compile", json={})
        assert resp.status_code == 422

    def test_compile_payload_tool_output_extracted(self, client):
        sem = {
            "entry_rules": [{
                "condition_group": {
                    "operator": "AND",
                    "conditions": [{
                        "left":     _TOOL_SMA,
                        "operator": ">",
                        "right":    _CONST_30,
                    }],
                },
            }],
            "exit_rules": [],
        }
        resp = client.post("/semantics/compile", json={"semantics": sem})
        deps = resp.json()["evaluation_plan"]["dependencies"]
        assert "sma_fast.value" in deps["tool_outputs"]

    def test_compile_payload_no_execution_side_effects(self, client):
        """Two identical compilations produce structurally identical plans."""
        body = {"semantics": _simple_semantics_dict()}
        r1 = client.post("/semantics/compile", json=body).json()
        r2 = client.post("/semantics/compile", json=body).json()
        # Plan shape must be identical (compiled_at will differ — that's fine)
        assert r1["compiled"]  == r2["compiled"]
        assert r1["errors"]    == r2["errors"]
        assert r1["evaluation_plan"]["rule_nodes"]    == r2["evaluation_plan"]["rule_nodes"]
        assert r1["evaluation_plan"]["dependencies"]  == r2["evaluation_plan"]["dependencies"]
        assert r1["evaluation_plan"]["node_count"]    == r2["evaluation_plan"]["node_count"]
