"""
Phase 2O.5 — Semantic Binding API tests.

Covers:
- POST /drafts/{draft_id}/semantics/validate-bindings — draft with semantics
- POST /drafts/{draft_id}/semantics/validate-bindings — draft without semantics (valid=False)
- POST /drafts/{draft_id}/semantics/validate-bindings — draft not found (404)
- Response shape: valid, binding_diagnostics, dependency_summary
- dependency_summary fields: resolved/unresolved/warned/price_fields/constants
- no_semantics code present when draft has no semantics
- binding_valid/binding_diagnostics in compile response (Phase 2O.5 integration)
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
        "exit_rules": [],
    }

def _semantics_with_tool_output():
    return {
        "entry_rules": [{
            "condition_group": {
                "operator": "AND",
                "conditions": [{
                    "left":     {"kind": "tool_output", "ref": "sma_fast.sma"},
                    "operator": ">",
                    "right":    _CONST_30,
                }],
            },
        }],
        "exit_rules": [],
    }

def _draft_with_semantics(
    client: TestClient,
    draft_id: str = "draft-1",
    semantics: dict | None = None,
) -> None:
    _create_draft(client, draft_id)
    payload = semantics or _simple_semantics_dict()
    client.put(f"/drafts/{draft_id}/semantics", json={"semantics": payload})


# ---------------------------------------------------------------------------
# POST /drafts/{draft_id}/semantics/validate-bindings
# ---------------------------------------------------------------------------

class TestValidateBindingsEndpoint:
    def test_returns_200_with_semantics(self, client):
        _draft_with_semantics(client)
        resp = client.post("/drafts/draft-1/semantics/validate-bindings")
        assert resp.status_code == 200

    def test_returns_404_unknown_draft(self, client):
        resp = client.post("/drafts/nonexistent/semantics/validate-bindings")
        assert resp.status_code == 404

    def test_response_has_valid_field(self, client):
        _draft_with_semantics(client)
        data = client.post("/drafts/draft-1/semantics/validate-bindings").json()
        assert "valid" in data

    def test_response_has_binding_diagnostics_list(self, client):
        _draft_with_semantics(client)
        data = client.post("/drafts/draft-1/semantics/validate-bindings").json()
        assert isinstance(data["binding_diagnostics"], list)

    def test_response_has_dependency_summary(self, client):
        _draft_with_semantics(client)
        data = client.post("/drafts/draft-1/semantics/validate-bindings").json()
        assert "dependency_summary" in data

    def test_dependency_summary_has_required_keys(self, client):
        _draft_with_semantics(client)
        data = client.post("/drafts/draft-1/semantics/validate-bindings").json()
        summary = data["dependency_summary"]
        for key in (
            "resolved_tool_outputs",
            "unresolved_tool_outputs",
            "warned_tool_outputs",
            "price_fields",
            "constants",
        ):
            assert key in summary, f"missing key: {key}"

    def test_price_fields_in_summary(self, client):
        _draft_with_semantics(client)
        data = client.post("/drafts/draft-1/semantics/validate-bindings").json()
        assert "close" in data["dependency_summary"]["price_fields"]

    def test_constants_in_summary(self, client):
        _draft_with_semantics(client)
        data = client.post("/drafts/draft-1/semantics/validate-bindings").json()
        assert "30" in data["dependency_summary"]["constants"]

    def test_no_tool_output_refs_valid_true(self, client):
        _draft_with_semantics(client)
        data = client.post("/drafts/draft-1/semantics/validate-bindings").json()
        assert data["valid"] is True
        assert data["dependency_summary"]["resolved_tool_outputs"] == []
        assert data["dependency_summary"]["unresolved_tool_outputs"] == []

    def test_missing_tool_instance_valid_false(self, client):
        _draft_with_semantics(client, semantics=_semantics_with_tool_output())
        data = client.post("/drafts/draft-1/semantics/validate-bindings").json()
        assert data["valid"] is False

    def test_missing_tool_instance_diagnostic_code(self, client):
        _draft_with_semantics(client, semantics=_semantics_with_tool_output())
        data = client.post("/drafts/draft-1/semantics/validate-bindings").json()
        codes = [d["code"] for d in data["binding_diagnostics"]]
        assert "missing_tool_instance" in codes

    def test_unresolved_in_summary_on_missing_instance(self, client):
        _draft_with_semantics(client, semantics=_semantics_with_tool_output())
        data = client.post("/drafts/draft-1/semantics/validate-bindings").json()
        assert "sma_fast.sma" in data["dependency_summary"]["unresolved_tool_outputs"]


class TestValidateBindingsNoSemantics:
    def test_draft_without_semantics_returns_200(self, client):
        _create_draft(client, "draft-empty")
        resp = client.post("/drafts/draft-empty/semantics/validate-bindings")
        assert resp.status_code == 200

    def test_draft_without_semantics_valid_false(self, client):
        _create_draft(client, "draft-empty")
        data = client.post("/drafts/draft-empty/semantics/validate-bindings").json()
        assert data["valid"] is False

    def test_draft_without_semantics_no_semantics_code(self, client):
        _create_draft(client, "draft-empty")
        data = client.post("/drafts/draft-empty/semantics/validate-bindings").json()
        codes = [d["code"] for d in data["binding_diagnostics"]]
        assert "no_semantics" in codes

    def test_draft_without_semantics_error_severity(self, client):
        _create_draft(client, "draft-empty")
        data = client.post("/drafts/draft-empty/semantics/validate-bindings").json()
        severities = [d["severity"] for d in data["binding_diagnostics"]]
        assert "error" in severities


# ---------------------------------------------------------------------------
# Phase 2O.5 integration — compile endpoint populates binding fields
# ---------------------------------------------------------------------------

class TestCompileEndpointBindingIntegration:
    def test_compile_response_has_binding_valid(self, client):
        _draft_with_semantics(client)
        data = client.post("/drafts/draft-1/semantics/compile").json()
        assert "binding_valid" in data

    def test_compile_response_has_binding_diagnostics(self, client):
        _draft_with_semantics(client)
        data = client.post("/drafts/draft-1/semantics/compile").json()
        assert "binding_diagnostics" in data
        assert isinstance(data["binding_diagnostics"], list)

    def test_compile_response_has_dependency_summary(self, client):
        _draft_with_semantics(client)
        data = client.post("/drafts/draft-1/semantics/compile").json()
        assert "dependency_summary" in data

    def test_compile_binding_valid_true_no_tool_refs(self, client):
        _draft_with_semantics(client)
        data = client.post("/drafts/draft-1/semantics/compile").json()
        assert data["binding_valid"] is True

    def test_compile_price_fields_in_dependency_summary(self, client):
        _draft_with_semantics(client)
        data = client.post("/drafts/draft-1/semantics/compile").json()
        assert "close" in data["dependency_summary"]["price_fields"]
