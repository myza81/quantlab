"""
Phase 2O.9 — Evaluation Readiness API tests.

Covers:
- GET /drafts/{draft_id}/semantics/readiness — draft with semantics
- GET /drafts/{draft_id}/semantics/readiness — draft without semantics (blocked)
- GET /drafts/{draft_id}/semantics/readiness — unknown draft (404)
- POST /semantics/readiness — payload inspection
- POST /semantics/readiness — invalid body (422)
- Response shape: ready, status, summary, issues
- summary fields: blocking_count, warning_count, info_count
- issues items: code, severity, message
- Ready plan → ready=True, status="ready"
- No semantics → ready=False, status="blocked"
- Payload endpoint: draft_id=null
- Deterministic: same payload → same response
"""
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.routes.drafts import get_draft_repository
from backend.strategy_registry.draft_repository import DraftRepository


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


_PRICE_CLOSE = {"kind": "price",    "ref": "close"}
_CONST_30    = {"kind": "constant", "ref": "30"}


def _simple_semantics() -> dict:
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
    _create_draft(client, draft_id)
    client.put(
        f"/drafts/{draft_id}/semantics",
        json={"semantics": _simple_semantics()},
    )


# ---------------------------------------------------------------------------
# GET /drafts/{draft_id}/semantics/readiness
# ---------------------------------------------------------------------------

class TestDraftReadinessEndpoint:
    def test_returns_200_with_semantics(self, client):
        _draft_with_semantics(client)
        resp = client.get("/drafts/draft-1/semantics/readiness")
        assert resp.status_code == 200

    def test_returns_404_unknown_draft(self, client):
        resp = client.get("/drafts/nonexistent/semantics/readiness")
        assert resp.status_code == 404

    def test_ready_true_for_valid_semantics(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/readiness").json()
        assert data["ready"] is True

    def test_status_ready_for_valid_semantics(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/readiness").json()
        assert data["status"] == "ready"

    def test_response_has_draft_id(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/readiness").json()
        assert data["draft_id"] == "draft-1"

    def test_response_has_summary(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/readiness").json()
        assert "summary" in data

    def test_summary_has_blocking_count(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/readiness").json()
        assert "blocking_count" in data["summary"]

    def test_summary_has_warning_count(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/readiness").json()
        assert "warning_count" in data["summary"]

    def test_summary_has_info_count(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/readiness").json()
        assert "info_count" in data["summary"]

    def test_response_has_issues(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/readiness").json()
        assert "issues" in data
        assert isinstance(data["issues"], list)

    def test_no_blocking_issues_for_valid_semantics(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/readiness").json()
        assert data["summary"]["blocking_count"] == 0

    def test_blocking_count_zero_means_ready(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/readiness").json()
        assert data["ready"] is (data["summary"]["blocking_count"] == 0)

    def test_issues_items_have_code(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/readiness").json()
        for issue in data["issues"]:
            assert "code" in issue

    def test_issues_items_have_severity(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/readiness").json()
        for issue in data["issues"]:
            assert "severity" in issue

    def test_issues_items_have_message(self, client):
        _draft_with_semantics(client)
        data = client.get("/drafts/draft-1/semantics/readiness").json()
        for issue in data["issues"]:
            assert "message" in issue

    def test_deterministic_two_calls(self, client):
        _draft_with_semantics(client)
        d1 = client.get("/drafts/draft-1/semantics/readiness").json()
        d2 = client.get("/drafts/draft-1/semantics/readiness").json()
        assert d1["ready"]  == d2["ready"]
        assert d1["status"] == d2["status"]
        assert d1["issues"] == d2["issues"]


# ---------------------------------------------------------------------------
# GET /drafts/{draft_id}/semantics/readiness — no semantics
# ---------------------------------------------------------------------------

class TestDraftReadinessNoSemantics:
    def test_no_semantics_returns_200(self, client):
        _create_draft(client, "draft-empty")
        resp = client.get("/drafts/draft-empty/semantics/readiness")
        assert resp.status_code == 200

    def test_no_semantics_ready_false(self, client):
        _create_draft(client, "draft-empty")
        data = client.get("/drafts/draft-empty/semantics/readiness").json()
        assert data["ready"] is False

    def test_no_semantics_status_blocked(self, client):
        _create_draft(client, "draft-empty")
        data = client.get("/drafts/draft-empty/semantics/readiness").json()
        assert data["status"] == "blocked"

    def test_no_semantics_has_blocking_issues(self, client):
        _create_draft(client, "draft-empty")
        data = client.get("/drafts/draft-empty/semantics/readiness").json()
        assert data["summary"]["blocking_count"] > 0


# ---------------------------------------------------------------------------
# POST /semantics/readiness
# ---------------------------------------------------------------------------

class TestPayloadReadinessEndpoint:
    def test_returns_200(self, client):
        resp = client.post(
            "/semantics/readiness",
            json={"semantics": _simple_semantics()},
        )
        assert resp.status_code == 200

    def test_ready_true(self, client):
        data = client.post(
            "/semantics/readiness",
            json={"semantics": _simple_semantics()},
        ).json()
        assert data["ready"] is True

    def test_draft_id_null(self, client):
        data = client.post(
            "/semantics/readiness",
            json={"semantics": _simple_semantics()},
        ).json()
        assert data["draft_id"] is None

    def test_summary_present(self, client):
        data = client.post(
            "/semantics/readiness",
            json={"semantics": _simple_semantics()},
        ).json()
        assert "summary" in data

    def test_issues_present(self, client):
        data = client.post(
            "/semantics/readiness",
            json={"semantics": _simple_semantics()},
        ).json()
        assert "issues" in data

    def test_invalid_body_422(self, client):
        resp = client.post("/semantics/readiness", json={"bad": "payload"})
        assert resp.status_code == 422

    def test_deterministic_two_calls(self, client):
        payload = {"semantics": _simple_semantics()}
        d1 = client.post("/semantics/readiness", json=payload).json()
        d2 = client.post("/semantics/readiness", json=payload).json()
        assert d1["ready"]  == d2["ready"]
        assert d1["status"] == d2["status"]
        assert d1["issues"] == d2["issues"]

    def test_no_binding_issues_no_toolset_context(self, client):
        data = client.post(
            "/semantics/readiness",
            json={"semantics": _simple_semantics()},
        ).json()
        binding_issues = [i for i in data["issues"] if i["code"] == "binding_invalid"]
        assert binding_issues == []
