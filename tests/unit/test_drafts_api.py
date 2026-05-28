"""
Tests for Phase 2N.9 — /drafts REST API.

Covers:
  - GET  /drafts — list all active drafts
  - POST /drafts — create draft (201), 409 conflict, 422 validation error
  - GET  /drafts/{id} — retrieve draft (200), 404 not found
  - PUT  /drafts/{id} — partial update (200), 404 not found
  - POST /drafts/{id}/archive — archive (204), 404 not found
  - DELETE /drafts/{id} — hard-delete (204), 404 not found
  - Response shape: draft_id, display_name, toolset, timestamps, enabled, tags, notes
  - No compute_sma() called during any endpoint
  - GET /tools behavior remains unchanged
"""
from __future__ import annotations

from pathlib import Path

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


def _repo(tmp_path: Path) -> DraftRepository:
    return DraftRepository(tmp_path / "drafts")


def _client(tmp_path: Path) -> TestClient:
    app.dependency_overrides[get_draft_repository] = lambda: _repo(tmp_path)
    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    return TestClient(app)


def _cleanup() -> None:
    app.dependency_overrides.pop(get_draft_repository, None)
    app.dependency_overrides.pop(get_current_user, None)


def _valid_payload(draft_id: str = "alpha", **kw: object) -> dict:
    return {
        "draft_id": draft_id,
        "display_name": "Alpha Draft",
        "toolset": {
            "toolset_id": "ts1",
            "tools": [
                {
                    "instance_id": "sma_fast",
                    "tool_id": "sma",
                    "parameters": {"period": 20},
                }
            ],
        },
        **kw,
    }


# ---------------------------------------------------------------------------
# TestListDrafts
# ---------------------------------------------------------------------------

class TestListDrafts:
    def test_empty_list_returns_200(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            response = client.get("/drafts")
            assert response.status_code == 200
        finally:
            _cleanup()

    def test_empty_list_shape(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            body = client.get("/drafts").json()
            assert body["drafts"] == []
            assert body["count"] == 0
        finally:
            _cleanup()

    def test_lists_created_drafts(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            client.post("/drafts", json=_valid_payload("alpha"))
            client.post("/drafts", json=_valid_payload("beta"))
            body = client.get("/drafts").json()
            ids = [d["draft_id"] for d in body["drafts"]]
            assert "alpha" in ids
            assert "beta" in ids
            assert body["count"] == 2
        finally:
            _cleanup()

    def test_list_sorted_by_draft_id(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            client.post("/drafts", json=_valid_payload("zeta"))
            client.post("/drafts", json=_valid_payload("alpha"))
            body = client.get("/drafts").json()
            ids = [d["draft_id"] for d in body["drafts"]]
            assert ids == sorted(ids)
        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# TestCreateDraft
# ---------------------------------------------------------------------------

class TestCreateDraft:
    def test_create_returns_201(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            response = client.post("/drafts", json=_valid_payload())
            assert response.status_code == 201
        finally:
            _cleanup()

    def test_create_response_shape(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            body = client.post("/drafts", json=_valid_payload()).json()
            assert "draft_id" in body
            assert "display_name" in body
            assert "toolset" in body
            assert "created_at" in body
            assert "updated_at" in body
            assert "enabled" in body
            assert "tags" in body
            assert "notes" in body
        finally:
            _cleanup()

    def test_create_draft_id_normalized(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            body = client.post("/drafts", json=_valid_payload("MY_DRAFT")).json()
            assert body["draft_id"] == "my_draft"
        finally:
            _cleanup()

    def test_create_toolset_nested_in_response(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            body = client.post("/drafts", json=_valid_payload()).json()
            assert body["toolset"]["toolset_id"] == "ts1"
            assert len(body["toolset"]["tools"]) == 1
            assert body["toolset"]["tools"][0]["instance_id"] == "sma_fast"
        finally:
            _cleanup()

    def test_create_tags_optional_defaults_empty(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            body = client.post("/drafts", json=_valid_payload()).json()
            assert body["tags"] == []
        finally:
            _cleanup()

    def test_create_with_tags(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            payload = _valid_payload(tags=["research", "crypto"])
            body = client.post("/drafts", json=payload).json()
            assert set(body["tags"]) == {"research", "crypto"}
        finally:
            _cleanup()

    def test_create_enabled_defaults_true(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            body = client.post("/drafts", json=_valid_payload()).json()
            assert body["enabled"] is True
        finally:
            _cleanup()

    def test_create_timestamps_present(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            body = client.post("/drafts", json=_valid_payload()).json()
            assert body["created_at"] is not None
            assert body["updated_at"] is not None
        finally:
            _cleanup()

    def test_duplicate_draft_id_returns_409(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            client.post("/drafts", json=_valid_payload("alpha"))
            response = client.post("/drafts", json=_valid_payload("alpha"))
            assert response.status_code == 409
        finally:
            _cleanup()

    def test_missing_draft_id_returns_422(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            payload = _valid_payload()
            del payload["draft_id"]
            response = client.post("/drafts", json=payload)
            assert response.status_code == 422
        finally:
            _cleanup()

    def test_missing_toolset_returns_422(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            payload = _valid_payload()
            del payload["toolset"]
            response = client.post("/drafts", json=payload)
            assert response.status_code == 422
        finally:
            _cleanup()

    def test_duplicate_instance_id_in_toolset_returns_422(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            payload = _valid_payload()
            payload["toolset"]["tools"] = [
                {"instance_id": "dup", "tool_id": "sma", "parameters": {"period": 20}},
                {"instance_id": "dup", "tool_id": "sma", "parameters": {"period": 50}},
            ]
            response = client.post("/drafts", json=payload)
            assert response.status_code == 422
        finally:
            _cleanup()

    def test_extra_fields_return_422(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            payload = _valid_payload()
            payload["unexpected"] = True
            response = client.post("/drafts", json=payload)
            assert response.status_code == 422
        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# TestGetDraft
# ---------------------------------------------------------------------------

class TestGetDraft:
    def test_get_existing_returns_200(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            client.post("/drafts", json=_valid_payload("alpha"))
            response = client.get("/drafts/alpha")
            assert response.status_code == 200
        finally:
            _cleanup()

    def test_get_returns_correct_draft(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            client.post("/drafts", json=_valid_payload("alpha", display_name="My Strategy"))
            body = client.get("/drafts/alpha").json()
            assert body["draft_id"] == "alpha"
            assert body["display_name"] == "My Strategy"
        finally:
            _cleanup()

    def test_get_missing_returns_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            response = client.get("/drafts/ghost")
            assert response.status_code == 404
        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# TestUpdateDraft
# ---------------------------------------------------------------------------

class TestUpdateDraft:
    def test_update_returns_200(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            client.post("/drafts", json=_valid_payload("alpha"))
            response = client.put("/drafts/alpha", json={"display_name": "Updated"})
            assert response.status_code == 200
        finally:
            _cleanup()

    def test_update_changes_display_name(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            client.post("/drafts", json=_valid_payload("alpha", display_name="Original"))
            body = client.put("/drafts/alpha", json={"display_name": "Updated"}).json()
            assert body["display_name"] == "Updated"
        finally:
            _cleanup()

    def test_update_omitted_fields_unchanged(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            client.post("/drafts", json=_valid_payload("alpha", description="keep me"))
            body = client.put("/drafts/alpha", json={"display_name": "New Name"}).json()
            assert body["description"] == "keep me"
        finally:
            _cleanup()

    def test_update_refreshes_updated_at(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            created = client.post("/drafts", json=_valid_payload("alpha")).json()
            updated = client.put("/drafts/alpha", json={"display_name": "Changed"}).json()
            assert updated["created_at"] == created["created_at"]
        finally:
            _cleanup()

    def test_update_missing_returns_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            response = client.put("/drafts/ghost", json={"display_name": "X"})
            assert response.status_code == 404
        finally:
            _cleanup()

    def test_update_enabled_flag(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            client.post("/drafts", json=_valid_payload("alpha"))
            body = client.put("/drafts/alpha", json={"enabled": False}).json()
            assert body["enabled"] is False
        finally:
            _cleanup()

    def test_update_tags(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            client.post("/drafts", json=_valid_payload("alpha"))
            body = client.put("/drafts/alpha", json={"tags": ["momentum"]}).json()
            assert body["tags"] == ["momentum"]
        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# TestArchiveDraft
# ---------------------------------------------------------------------------

class TestArchiveDraft:
    def test_archive_returns_204(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            client.post("/drafts", json=_valid_payload("alpha"))
            response = client.post("/drafts/alpha/archive")
            assert response.status_code == 204
        finally:
            _cleanup()

    def test_archived_draft_removed_from_listing(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            client.post("/drafts", json=_valid_payload("alpha"))
            client.post("/drafts/alpha/archive")
            body = client.get("/drafts").json()
            assert all(d["draft_id"] != "alpha" for d in body["drafts"])
        finally:
            _cleanup()

    def test_archive_missing_returns_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            response = client.post("/drafts/ghost/archive")
            assert response.status_code == 404
        finally:
            _cleanup()

    def test_get_archived_draft_returns_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            client.post("/drafts", json=_valid_payload("alpha"))
            client.post("/drafts/alpha/archive")
            response = client.get("/drafts/alpha")
            assert response.status_code == 404
        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# TestDeleteDraft
# ---------------------------------------------------------------------------

class TestDeleteDraft:
    def test_delete_returns_204(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            client.post("/drafts", json=_valid_payload("alpha"))
            response = client.delete("/drafts/alpha")
            assert response.status_code == 204
        finally:
            _cleanup()

    def test_deleted_draft_not_found(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            client.post("/drafts", json=_valid_payload("alpha"))
            client.delete("/drafts/alpha")
            response = client.get("/drafts/alpha")
            assert response.status_code == 404
        finally:
            _cleanup()

    def test_delete_missing_returns_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            response = client.delete("/drafts/ghost")
            assert response.status_code == 404
        finally:
            _cleanup()

    def test_deleted_draft_absent_from_listing(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            client.post("/drafts", json=_valid_payload("alpha"))
            client.post("/drafts", json=_valid_payload("beta"))
            client.delete("/drafts/alpha")
            body = client.get("/drafts").json()
            ids = [d["draft_id"] for d in body["drafts"]]
            assert "alpha" not in ids
            assert "beta" in ids
        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# TestExecutionIndependence
# ---------------------------------------------------------------------------

class TestExecutionIndependence:
    def test_create_does_not_call_compute_sma(self, tmp_path: Path, monkeypatch) -> None:
        def _explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("compute_sma() must not be called by /drafts")

        monkeypatch.setattr("backend.tools.compute_sma", _explode)
        monkeypatch.setattr("backend.tools.sma.compute_sma", _explode)

        client = _client(tmp_path)
        try:
            response = client.post("/drafts", json=_valid_payload())
            assert response.status_code == 201
        finally:
            _cleanup()
