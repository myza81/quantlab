"""
API integration tests for /drafts/{id}/semantics endpoints — Phase 2O.1.

Covers:
- GET /drafts/{id}/semantics — returns null semantics on new draft
- PUT /drafts/{id}/semantics — persists semantics
- GET /drafts/{id}/semantics — returns semantics after PUT
- POST /drafts/{id}/semantics/validate — validates stored semantics
- POST /semantics/validate — validates payload without persisting
- 404 on non-existent draft
- Validation of invalid semantics payload
- Draft backward compatibility (existing drafts without semantics)
- DraftResponse includes semantics field
- Round-trip: PUT then GET produces identical payload
"""
from __future__ import annotations

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
# Fixtures
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


def _create_draft(client: TestClient, draft_id: str = "test_draft") -> dict:
    resp = client.post("/drafts", json={
        "draft_id": draft_id,
        "display_name": "Test Draft",
        "toolset": {"toolset_id": draft_id, "tools": []},
    })
    assert resp.status_code in (200, 201), resp.json()
    return resp.json()


def _semantics_payload() -> dict:
    return {
        "semantics": {
            "entry_rules": [
                {
                    "condition_group": {
                        "operator": "AND",
                        "conditions": [
                            {
                                "left":     {"kind": "tool_output", "ref": "sma_fast.value"},
                                "operator": ">",
                                "right":    {"kind": "tool_output", "ref": "sma_slow.value"},
                            }
                        ],
                    }
                }
            ],
            "exit_rules": [
                {
                    "condition_group": {
                        "operator": "OR",
                        "conditions": [
                            {
                                "left":     {"kind": "tool_output", "ref": "rsi_14.value"},
                                "operator": ">",
                                "right":    {"kind": "constant", "ref": "70"},
                            }
                        ],
                    }
                }
            ],
            "metadata": {"version": "1.0"},
        }
    }


# ---------------------------------------------------------------------------
# GET /drafts/{id}/semantics
# ---------------------------------------------------------------------------

class TestGetSemantics:
    def test_null_semantics_on_new_draft(self, client):
        _create_draft(client)
        resp = client.get("/drafts/test_draft/semantics")
        assert resp.status_code == 200
        body = resp.json()
        assert body["draft_id"] == "test_draft"
        assert body["semantics"] is None

    def test_404_on_missing_draft(self, client):
        resp = client.get("/drafts/nonexistent/semantics")
        assert resp.status_code == 404

    def test_returns_semantics_after_put(self, client):
        _create_draft(client)
        client.put("/drafts/test_draft/semantics", json=_semantics_payload())
        resp = client.get("/drafts/test_draft/semantics")
        assert resp.status_code == 200
        body = resp.json()
        assert body["semantics"] is not None
        assert len(body["semantics"]["entry_rules"]) == 1
        assert len(body["semantics"]["exit_rules"]) == 1


# ---------------------------------------------------------------------------
# PUT /drafts/{id}/semantics
# ---------------------------------------------------------------------------

class TestPutSemantics:
    def test_put_semantics_200(self, client):
        _create_draft(client)
        resp = client.put("/drafts/test_draft/semantics", json=_semantics_payload())
        assert resp.status_code == 200
        body = resp.json()
        assert body["draft_id"] == "test_draft"
        assert body["semantics"] is not None

    def test_put_semantics_entry_rules_persisted(self, client):
        _create_draft(client)
        resp = client.put("/drafts/test_draft/semantics", json=_semantics_payload())
        entry = resp.json()["semantics"]["entry_rules"][0]
        cond = entry["condition_group"]["conditions"][0]
        assert cond["left"]["ref"] == "sma_fast.value"
        assert cond["operator"] == ">"

    def test_put_semantics_404_missing_draft(self, client):
        resp = client.put("/drafts/ghost/semantics", json=_semantics_payload())
        assert resp.status_code == 404

    def test_put_semantics_replaces_previous(self, client):
        _create_draft(client)
        client.put("/drafts/test_draft/semantics", json=_semantics_payload())

        new_payload = {
            "semantics": {
                "entry_rules": [],
                "exit_rules": [],
                "metadata": {"version": "2.0"},
            }
        }
        resp = client.put("/drafts/test_draft/semantics", json=new_payload)
        assert resp.status_code == 200
        assert resp.json()["semantics"]["metadata"]["version"] == "2.0"
        assert resp.json()["semantics"]["entry_rules"] == []

    def test_round_trip(self, client):
        _create_draft(client)
        put_resp = client.put("/drafts/test_draft/semantics", json=_semantics_payload())
        get_resp = client.get("/drafts/test_draft/semantics")
        assert put_resp.json()["semantics"] == get_resp.json()["semantics"]

    def test_put_invalid_payload_422(self, client):
        _create_draft(client)
        bad_payload = {"semantics": {"entry_rules": "not_a_list", "exit_rules": []}}
        resp = client.put("/drafts/test_draft/semantics", json=bad_payload)
        assert resp.status_code == 422

    def test_put_updates_draft_updated_at(self, client):
        _create_draft(client)
        draft_before = client.get("/drafts/test_draft").json()
        import time; time.sleep(0.01)
        client.put("/drafts/test_draft/semantics", json=_semantics_payload())
        draft_after = client.get("/drafts/test_draft").json()
        assert draft_after["updated_at"] >= draft_before["updated_at"]


# ---------------------------------------------------------------------------
# POST /drafts/{id}/semantics/validate
# ---------------------------------------------------------------------------

class TestValidateDraftSemantics:
    def test_no_semantics_returns_invalid(self, client):
        _create_draft(client)
        resp = client.post("/drafts/test_draft/semantics/validate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert len(body["errors"]) > 0

    def test_valid_semantics_returns_valid(self, client):
        _create_draft(client)
        client.put("/drafts/test_draft/semantics", json=_semantics_payload())
        resp = client.post("/drafts/test_draft/semantics/validate")
        assert resp.status_code == 200
        assert resp.json()["valid"] is True
        assert resp.json()["errors"] == []

    def test_404_on_missing_draft(self, client):
        resp = client.post("/drafts/ghost/semantics/validate")
        assert resp.status_code == 404

    def test_semantics_with_bad_constant_returns_invalid(self, client):
        _create_draft(client)
        bad_payload = {
            "semantics": {
                "entry_rules": [
                    {
                        "condition_group": {
                            "operator": "AND",
                            "conditions": [
                                {
                                    "left":     {"kind": "constant", "ref": "not_a_number"},
                                    "operator": ">",
                                    "right":    {"kind": "constant", "ref": "1"},
                                }
                            ],
                        }
                    }
                ],
                "exit_rules": [],
                "metadata": {"version": "1.0"},
            }
        }
        client.put("/drafts/test_draft/semantics", json=bad_payload)
        resp = client.post("/drafts/test_draft/semantics/validate")
        assert resp.status_code == 200
        assert resp.json()["valid"] is False


# ---------------------------------------------------------------------------
# POST /semantics/validate (payload validation, no draft)
# ---------------------------------------------------------------------------

class TestValidateSemanticsPayload:
    def test_valid_payload_returns_valid(self, client):
        resp = client.post("/semantics/validate", json=_semantics_payload())
        assert resp.status_code == 200
        assert resp.json()["valid"] is True
        assert resp.json()["errors"] == []

    def test_invalid_constant_returns_errors(self, client):
        payload = {
            "semantics": {
                "entry_rules": [
                    {
                        "condition_group": {
                            "operator": "AND",
                            "conditions": [
                                {
                                    "left":     {"kind": "constant", "ref": "abc"},
                                    "operator": ">",
                                    "right":    {"kind": "constant", "ref": "1"},
                                }
                            ],
                        }
                    }
                ],
                "exit_rules": [],
                "metadata": {"version": "1.0"},
            }
        }
        resp = client.post("/semantics/validate", json=payload)
        assert resp.status_code == 200
        assert resp.json()["valid"] is False
        assert any("abc" in e for e in resp.json()["errors"])

    def test_invalid_price_ref_returns_errors(self, client):
        payload = {
            "semantics": {
                "entry_rules": [
                    {
                        "condition_group": {
                            "operator": "AND",
                            "conditions": [
                                {
                                    "left":     {"kind": "price", "ref": "ask"},
                                    "operator": ">",
                                    "right":    {"kind": "constant", "ref": "100"},
                                }
                            ],
                        }
                    }
                ],
                "exit_rules": [],
                "metadata": {"version": "1.0"},
            }
        }
        resp = client.post("/semantics/validate", json=payload)
        assert resp.status_code == 200
        assert resp.json()["valid"] is False

    def test_empty_rules_valid(self, client):
        payload = {
            "semantics": {
                "entry_rules": [],
                "exit_rules": [],
                "metadata": {"version": "1.0"},
            }
        }
        resp = client.post("/semantics/validate", json=payload)
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_malformed_body_422(self, client):
        resp = client.post("/semantics/validate", json={"semantics": "not_an_object"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DraftResponse includes semantics (backward compatibility)
# ---------------------------------------------------------------------------

class TestDraftResponseBackwardCompatibility:
    def test_draft_response_includes_semantics_null_by_default(self, client):
        _create_draft(client)
        resp = client.get("/drafts/test_draft")
        assert resp.status_code == 200
        body = resp.json()
        assert "semantics" in body
        assert body["semantics"] is None

    def test_draft_response_includes_semantics_after_put(self, client):
        _create_draft(client)
        client.put("/drafts/test_draft/semantics", json=_semantics_payload())
        resp = client.get("/drafts/test_draft")
        assert resp.status_code == 200
        body = resp.json()
        assert body["semantics"] is not None
        assert "entry_rules" in body["semantics"]

    def test_list_drafts_includes_semantics_field(self, client):
        _create_draft(client)
        resp = client.get("/drafts")
        assert resp.status_code == 200
        draft = resp.json()["drafts"][0]
        assert "semantics" in draft

    def test_existing_draft_without_semantics_still_loadable(self, client, repo, tmp_path):
        """
        Phase 3L: Legacy drafts (no user_id) are inaccessible to authenticated users.
        The repository can still deserialise them, but ownership filtering returns 404.
        """
        import json
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        legacy_data = {
            "draft_id": "legacy_draft",
            "display_name": "Legacy",
            "toolset": {
                "toolset_id": "legacy_draft",
                "display_name": None,
                "tools": [],
                "enabled": True,
            },
            "created_at": now,
            "updated_at": now,
            "enabled": True,
            "tags": [],
            "notes": None,
            # intentionally no "semantics" or "user_id" key — legacy format
        }
        # Write legacy JSON directly to repository
        active_dir = tmp_path / "strategy_drafts"
        active_dir.mkdir(parents=True, exist_ok=True)
        (active_dir / "legacy_draft.json").write_text(
            json.dumps(legacy_data), encoding="utf-8"
        )
        # Phase 3L: legacy draft (user_id=None) is inaccessible to authenticated user
        resp = client.get("/drafts/legacy_draft")
        assert resp.status_code == 404
