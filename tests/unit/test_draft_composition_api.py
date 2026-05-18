"""
Tests for Phase 2N.10 — /drafts composition REST API.

Covers:
  - POST   /drafts/{draft_id}/tools        — add tool (200, 404, 409, 422)
  - DELETE /drafts/{draft_id}/tools/{id}   — remove tool (200, 404)
  - POST   /drafts/{draft_id}/tools/reorder — reorder (200, 404, 422)
  - PATCH  /drafts/{draft_id}/tools/{id}   — patch tool (200, 404, 422)
  - POST   /drafts/{draft_id}/validate     — validate (200, 404)
  - No compute_sma() called during any composition endpoint
  - Existing /drafts CRUD endpoints not regressed
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.routes.drafts import get_draft_repository
from backend.strategy_registry.draft_repository import DraftRepository
from backend.strategy_registry.drafts import StrategyDraft
from backend.tools.configuration import ToolConfiguration
from backend.tools.toolset import StrategyToolSet

_UTC = timezone.utc
_NOW = datetime(2026, 5, 18, 12, 0, 0, tzinfo=_UTC)


# ---------------------------------------------------------------------------
# Client / fixtures
# ---------------------------------------------------------------------------

def _repo(tmp_path: Path) -> DraftRepository:
    return DraftRepository(tmp_path / "drafts")


def _client(tmp_path: Path) -> TestClient:
    app.dependency_overrides[get_draft_repository] = lambda: _repo(tmp_path)
    return TestClient(app)


def _cleanup() -> None:
    app.dependency_overrides.pop(get_draft_repository, None)


def _valid_draft_payload(draft_id: str = "alpha", **kw: object) -> dict:
    return {
        "draft_id": draft_id,
        "display_name": "Alpha Draft",
        "toolset": {
            "toolset_id": "ts1",
            "tools": [
                {"instance_id": "sma_fast", "tool_id": "sma", "parameters": {"period": 20}}
            ],
        },
        **kw,
    }


def _seed_draft(
    client: TestClient,
    draft_id: str = "alpha",
    tools: list[dict] | None = None,
) -> None:
    payload = _valid_draft_payload(draft_id)
    if tools is not None:
        payload["toolset"]["tools"] = tools
    client.post("/drafts", json=payload)


def _sma_payload(instance_id: str, period: int) -> dict:
    return {"instance_id": instance_id, "tool_id": "sma", "parameters": {"period": period}}


# ---------------------------------------------------------------------------
# TestAddToolAPI
# ---------------------------------------------------------------------------

class TestAddToolAPI:
    def test_add_returns_200(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            response = client.post(
                "/drafts/alpha/tools",
                json={"tool": _sma_payload("sma_slow", 50)},
            )
            assert response.status_code == 200
        finally:
            _cleanup()

    def test_add_response_has_correct_tool_count(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            body = client.post(
                "/drafts/alpha/tools",
                json={"tool": _sma_payload("sma_slow", 50)},
            ).json()
            assert len(body["toolset"]["tools"]) == 2
        finally:
            _cleanup()

    def test_add_tool_appears_in_response(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            body = client.post(
                "/drafts/alpha/tools",
                json={"tool": _sma_payload("sma_slow", 50)},
            ).json()
            ids = [t["instance_id"] for t in body["toolset"]["tools"]]
            assert "sma_slow" in ids
        finally:
            _cleanup()

    def test_add_at_index_zero(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            body = client.post(
                "/drafts/alpha/tools",
                json={"tool": _sma_payload("sma_slow", 50), "index": 0},
            ).json()
            assert body["toolset"]["tools"][0]["instance_id"] == "sma_slow"
        finally:
            _cleanup()

    def test_add_duplicate_instance_id_returns_409(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            response = client.post(
                "/drafts/alpha/tools",
                json={"tool": _sma_payload("sma_fast", 50)},
            )
            assert response.status_code == 409
        finally:
            _cleanup()

    def test_add_unknown_tool_id_returns_422(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            response = client.post(
                "/drafts/alpha/tools",
                json={"tool": {"instance_id": "x", "tool_id": "nonexistent", "parameters": {}}},
            )
            assert response.status_code == 422
        finally:
            _cleanup()

    def test_add_invalid_params_returns_422(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            response = client.post(
                "/drafts/alpha/tools",
                json={"tool": _sma_payload("sma_new", -1)},
            )
            assert response.status_code == 422
        finally:
            _cleanup()

    def test_add_missing_draft_returns_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            response = client.post(
                "/drafts/ghost/tools",
                json={"tool": _sma_payload("sma_fast", 20)},
            )
            assert response.status_code == 404
        finally:
            _cleanup()

    def test_add_index_out_of_range_returns_422(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            response = client.post(
                "/drafts/alpha/tools",
                json={"tool": _sma_payload("sma_slow", 50), "index": 99},
            )
            assert response.status_code == 422
        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# TestRemoveToolAPI
# ---------------------------------------------------------------------------

class TestRemoveToolAPI:
    def test_remove_returns_200(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client, tools=[_sma_payload("a", 10), _sma_payload("b", 20)])
            response = client.delete("/drafts/alpha/tools/a")
            assert response.status_code == 200
        finally:
            _cleanup()

    def test_remove_tool_absent_from_response(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client, tools=[_sma_payload("a", 10), _sma_payload("b", 20)])
            body = client.delete("/drafts/alpha/tools/a").json()
            ids = [t["instance_id"] for t in body["toolset"]["tools"]]
            assert "a" not in ids
            assert "b" in ids
        finally:
            _cleanup()

    def test_remove_missing_instance_returns_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            response = client.delete("/drafts/alpha/tools/ghost")
            assert response.status_code == 404
        finally:
            _cleanup()

    def test_remove_missing_draft_returns_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            response = client.delete("/drafts/ghost/tools/sma_fast")
            assert response.status_code == 404
        finally:
            _cleanup()

    def test_remove_remaining_count_correct(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client, tools=[_sma_payload("a", 10), _sma_payload("b", 20), _sma_payload("c", 30)])
            body = client.delete("/drafts/alpha/tools/b").json()
            assert len(body["toolset"]["tools"]) == 2
        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# TestReorderToolsAPI
# ---------------------------------------------------------------------------

class TestReorderToolsAPI:
    def test_reorder_returns_200(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client, tools=[_sma_payload("a", 10), _sma_payload("b", 20)])
            response = client.post(
                "/drafts/alpha/tools/reorder",
                json={"ordered_instance_ids": ["b", "a"]},
            )
            assert response.status_code == 200
        finally:
            _cleanup()

    def test_reorder_applies_new_order(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client, tools=[_sma_payload("a", 10), _sma_payload("b", 20), _sma_payload("c", 30)])
            body = client.post(
                "/drafts/alpha/tools/reorder",
                json={"ordered_instance_ids": ["c", "a", "b"]},
            ).json()
            ids = [t["instance_id"] for t in body["toolset"]["tools"]]
            assert ids == ["c", "a", "b"]
        finally:
            _cleanup()

    def test_reorder_missing_id_returns_422(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client, tools=[_sma_payload("a", 10), _sma_payload("b", 20)])
            response = client.post(
                "/drafts/alpha/tools/reorder",
                json={"ordered_instance_ids": ["a"]},
            )
            assert response.status_code == 422
        finally:
            _cleanup()

    def test_reorder_extra_id_returns_422(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client, tools=[_sma_payload("a", 10), _sma_payload("b", 20)])
            response = client.post(
                "/drafts/alpha/tools/reorder",
                json={"ordered_instance_ids": ["a", "b", "ghost"]},
            )
            assert response.status_code == 422
        finally:
            _cleanup()

    def test_reorder_missing_draft_returns_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            response = client.post(
                "/drafts/ghost/tools/reorder",
                json={"ordered_instance_ids": ["a"]},
            )
            assert response.status_code == 404
        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# TestPatchToolAPI
# ---------------------------------------------------------------------------

class TestPatchToolAPI:
    def test_patch_returns_200(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            response = client.patch(
                "/drafts/alpha/tools/sma_fast",
                json={"enabled": False},
            )
            assert response.status_code == 200
        finally:
            _cleanup()

    def test_patch_updates_enabled(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            body = client.patch(
                "/drafts/alpha/tools/sma_fast",
                json={"enabled": False},
            ).json()
            tool = next(t for t in body["toolset"]["tools"] if t["instance_id"] == "sma_fast")
            assert tool["enabled"] is False
        finally:
            _cleanup()

    def test_patch_updates_parameters(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            body = client.patch(
                "/drafts/alpha/tools/sma_fast",
                json={"parameters": {"period": 100}},
            ).json()
            tool = next(t for t in body["toolset"]["tools"] if t["instance_id"] == "sma_fast")
            assert tool["parameters"]["period"] == 100
        finally:
            _cleanup()

    def test_patch_invalid_params_returns_422(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            response = client.patch(
                "/drafts/alpha/tools/sma_fast",
                json={"parameters": {"period": -1}},
            )
            assert response.status_code == 422
        finally:
            _cleanup()

    def test_patch_missing_instance_returns_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            response = client.patch(
                "/drafts/alpha/tools/ghost",
                json={"enabled": False},
            )
            assert response.status_code == 404
        finally:
            _cleanup()

    def test_patch_missing_draft_returns_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            response = client.patch(
                "/drafts/ghost/tools/sma_fast",
                json={"enabled": False},
            )
            assert response.status_code == 404
        finally:
            _cleanup()

    def test_patch_display_name(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            body = client.patch(
                "/drafts/alpha/tools/sma_fast",
                json={"display_name": "Fast Moving Average"},
            ).json()
            tool = next(t for t in body["toolset"]["tools"] if t["instance_id"] == "sma_fast")
            assert tool["display_name"] == "Fast Moving Average"
        finally:
            _cleanup()

    def test_patch_color(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            body = client.patch(
                "/drafts/alpha/tools/sma_fast",
                json={"color": "#ff0000"},
            ).json()
            tool = next(t for t in body["toolset"]["tools"] if t["instance_id"] == "sma_fast")
            assert tool["color"] == "#ff0000"
        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# TestValidateDraftAPI
# ---------------------------------------------------------------------------

class TestValidateDraftAPI:
    def test_validate_returns_200(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            response = client.post("/drafts/alpha/validate")
            assert response.status_code == 200
        finally:
            _cleanup()

    def test_validate_valid_draft(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            body = client.post("/drafts/alpha/validate").json()
            assert body["valid"] is True
            assert body["errors"] == []
        finally:
            _cleanup()

    def test_validate_missing_draft_returns_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            response = client.post("/drafts/ghost/validate")
            assert response.status_code == 404
        finally:
            _cleanup()

    def test_validate_response_shape(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            body = client.post("/drafts/alpha/validate").json()
            assert "valid" in body
            assert "errors" in body
            assert isinstance(body["errors"], list)
        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# TestExecutionIndependence
# ---------------------------------------------------------------------------

class TestExecutionIndependence:
    def test_add_tool_does_not_call_compute_sma(self, tmp_path: Path, monkeypatch) -> None:
        def _explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("compute_sma() must not be called by composition endpoints")

        monkeypatch.setattr("backend.tools.compute_sma", _explode)
        monkeypatch.setattr("backend.tools.sma.compute_sma", _explode)

        client = _client(tmp_path)
        try:
            _seed_draft(client)
            response = client.post(
                "/drafts/alpha/tools",
                json={"tool": _sma_payload("sma_slow", 50)},
            )
            assert response.status_code == 200
        finally:
            _cleanup()

    def test_validate_does_not_call_compute_sma(self, tmp_path: Path, monkeypatch) -> None:
        def _explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("compute_sma() must not be called during validation")

        monkeypatch.setattr("backend.tools.compute_sma", _explode)
        monkeypatch.setattr("backend.tools.sma.compute_sma", _explode)

        client = _client(tmp_path)
        try:
            _seed_draft(client)
            response = client.post("/drafts/alpha/validate")
            assert response.status_code == 200
        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# TestRegressionExistingDraftsAPI
# ---------------------------------------------------------------------------

class TestRegressionExistingDraftsAPI:
    def test_list_drafts_still_works(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            response = client.get("/drafts")
            assert response.status_code == 200
            assert response.json()["count"] == 1
        finally:
            _cleanup()

    def test_get_draft_still_works(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            response = client.get("/drafts/alpha")
            assert response.status_code == 200
        finally:
            _cleanup()

    def test_archive_draft_still_works(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            response = client.post("/drafts/alpha/archive")
            assert response.status_code == 204
        finally:
            _cleanup()

    def test_delete_draft_still_works(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _seed_draft(client)
            response = client.delete("/drafts/alpha")
            assert response.status_code == 204
        finally:
            _cleanup()
