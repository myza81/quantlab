"""
Tests for POST /tools/validate-toolset — Phase 2N.7.

Covers:
  - Valid StrategyToolSet returns valid=true, errors=[]
  - Unknown tool_id returns valid=false with deterministic error
  - Invalid parameter returns valid=false with parameter error
  - Multiple errors are all collected (not fail-fast)
  - Malformed request body returns 422 (framework validation error)
  - Empty toolset is valid
  - Disabled tool is still validated
  - GET /tools behavior is unchanged after adding validate-toolset
  - Endpoint never calls compute_sma()
  - Response shape: valid (bool) + errors (list[str])
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.routes.tools import get_tool_registry
from backend.tools import ToolRegistry, create_default_registry


def _client() -> TestClient:
    return TestClient(app)


def _cleanup() -> None:
    app.dependency_overrides.pop(get_tool_registry, None)


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------

def _sma_tool(instance_id: str, period: int, **kw: object) -> dict:
    return {
        "instance_id": instance_id,
        "tool_id": "sma",
        "parameters": {"period": period},
        **kw,
    }


def _unknown_tool(instance_id: str) -> dict:
    return {
        "instance_id": instance_id,
        "tool_id": "ghost_tool",
        "parameters": {},
    }


def _toolset(*tools: dict, toolset_id: str = "test_set") -> dict:
    return {"toolset_id": toolset_id, "tools": list(tools)}


# ---------------------------------------------------------------------------
# TestHappyPath
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_valid_single_sma_returns_200(self) -> None:
        client = _client()
        payload = _toolset(_sma_tool("sma_fast", 20))
        response = client.post("/tools/validate-toolset", json=payload)
        assert response.status_code == 200

    def test_valid_single_sma_returns_valid_true(self) -> None:
        client = _client()
        payload = _toolset(_sma_tool("sma_fast", 20))
        response = client.post("/tools/validate-toolset", json=payload)
        body = response.json()
        assert body["valid"] is True
        assert body["errors"] == []

    def test_valid_multiple_smas_pass(self) -> None:
        client = _client()
        payload = _toolset(
            _sma_tool("a", 20),
            _sma_tool("b", 50),
            _sma_tool("c", 200),
        )
        response = client.post("/tools/validate-toolset", json=payload)
        assert response.status_code == 200
        assert response.json()["valid"] is True

    def test_empty_toolset_is_valid(self) -> None:
        client = _client()
        payload = _toolset()
        response = client.post("/tools/validate-toolset", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is True
        assert body["errors"] == []

    def test_disabled_tool_still_validated_and_passes(self) -> None:
        client = _client()
        payload = _toolset(_sma_tool("sma_off", 20, enabled=False))
        response = client.post("/tools/validate-toolset", json=payload)
        assert response.status_code == 200
        assert response.json()["valid"] is True

    def test_response_shape_has_valid_and_errors(self) -> None:
        client = _client()
        payload = _toolset(_sma_tool("sma_x", 10))
        body = client.post("/tools/validate-toolset", json=payload).json()
        assert "valid" in body
        assert "errors" in body
        assert isinstance(body["valid"], bool)
        assert isinstance(body["errors"], list)


# ---------------------------------------------------------------------------
# TestUnknownToolId
# ---------------------------------------------------------------------------

class TestUnknownToolId:
    def test_unknown_tool_id_returns_valid_false(self) -> None:
        client = _client()
        payload = _toolset(_unknown_tool("ghost_inst"))
        response = client.post("/tools/validate-toolset", json=payload)
        assert response.status_code == 200
        assert response.json()["valid"] is False

    def test_unknown_tool_id_returns_one_error(self) -> None:
        client = _client()
        payload = _toolset(_unknown_tool("ghost_inst"))
        body = client.post("/tools/validate-toolset", json=payload).json()
        assert len(body["errors"]) == 1

    def test_error_contains_instance_id(self) -> None:
        client = _client()
        payload = _toolset(_unknown_tool("my_ghost"))
        body = client.post("/tools/validate-toolset", json=payload).json()
        assert "my_ghost" in body["errors"][0]

    def test_error_contains_tool_id(self) -> None:
        client = _client()
        payload = _toolset(_unknown_tool("x"))
        body = client.post("/tools/validate-toolset", json=payload).json()
        assert "ghost_tool" in body["errors"][0]

    def test_error_says_not_found(self) -> None:
        client = _client()
        payload = _toolset(_unknown_tool("x"))
        body = client.post("/tools/validate-toolset", json=payload).json()
        assert "not found" in body["errors"][0]

    def test_empty_registry_flags_all_tools(self) -> None:
        app.dependency_overrides[get_tool_registry] = lambda: ToolRegistry()
        try:
            client = _client()
            payload = _toolset(_sma_tool("a", 20), _sma_tool("b", 50))
            body = client.post("/tools/validate-toolset", json=payload).json()
            assert body["valid"] is False
            assert len(body["errors"]) == 2
        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# TestParameterErrors
# ---------------------------------------------------------------------------

class TestParameterErrors:
    def test_missing_required_param_returns_valid_false(self) -> None:
        client = _client()
        payload = _toolset(
            {"instance_id": "sma_bad", "tool_id": "sma", "parameters": {}}
        )
        body = client.post("/tools/validate-toolset", json=payload).json()
        assert body["valid"] is False

    def test_missing_required_param_mentions_period(self) -> None:
        client = _client()
        payload = _toolset(
            {"instance_id": "sma_bad", "tool_id": "sma", "parameters": {}}
        )
        body = client.post("/tools/validate-toolset", json=payload).json()
        assert any("period" in e and "missing" in e for e in body["errors"])

    def test_error_prefixed_with_instance_id(self) -> None:
        client = _client()
        payload = _toolset(
            {"instance_id": "sma_broken", "tool_id": "sma", "parameters": {}}
        )
        body = client.post("/tools/validate-toolset", json=payload).json()
        assert all("sma_broken" in e for e in body["errors"])

    def test_period_below_min_fails(self) -> None:
        client = _client()
        payload = _toolset(
            {"instance_id": "sma_zero", "tool_id": "sma", "parameters": {"period": 0}}
        )
        body = client.post("/tools/validate-toolset", json=payload).json()
        assert body["valid"] is False
        assert any("below minimum" in e for e in body["errors"])

    def test_unknown_param_fails(self) -> None:
        client = _client()
        payload = _toolset(
            {
                "instance_id": "sma_ghost_param",
                "tool_id": "sma",
                "parameters": {"period": 20, "nonexistent": True},
            }
        )
        body = client.post("/tools/validate-toolset", json=payload).json()
        assert body["valid"] is False
        assert any("nonexistent" in e for e in body["errors"])

    def test_wrong_type_for_period_fails(self) -> None:
        client = _client()
        payload = _toolset(
            {
                "instance_id": "sma_wrong_type",
                "tool_id": "sma",
                "parameters": {"period": "twenty"},
            }
        )
        body = client.post("/tools/validate-toolset", json=payload).json()
        assert body["valid"] is False


# ---------------------------------------------------------------------------
# TestMultiErrorCollection
# ---------------------------------------------------------------------------

class TestMultiErrorCollection:
    def test_two_invalid_tools_both_reported(self) -> None:
        client = _client()
        payload = _toolset(
            {"instance_id": "bad_a", "tool_id": "sma", "parameters": {}},
            {"instance_id": "bad_b", "tool_id": "sma", "parameters": {}},
        )
        body = client.post("/tools/validate-toolset", json=payload).json()
        assert body["valid"] is False
        assert any("bad_a" in e for e in body["errors"])
        assert any("bad_b" in e for e in body["errors"])

    def test_unknown_and_bad_param_both_reported(self) -> None:
        client = _client()
        payload = _toolset(
            _unknown_tool("ghost_inst"),
            {"instance_id": "sma_bad", "tool_id": "sma", "parameters": {}},
        )
        body = client.post("/tools/validate-toolset", json=payload).json()
        assert body["valid"] is False
        assert any("ghost_inst" in e for e in body["errors"])
        assert any("sma_bad" in e for e in body["errors"])

    def test_error_count_matches_violation_count(self) -> None:
        client = _client()
        payload = _toolset(
            _unknown_tool("x"),
            _unknown_tool("y"),
            _unknown_tool("z"),
        )
        body = client.post("/tools/validate-toolset", json=payload).json()
        assert len(body["errors"]) == 3

    def test_mix_valid_and_invalid_only_reports_invalid(self) -> None:
        client = _client()
        payload = _toolset(
            _sma_tool("good_a", 20),
            {"instance_id": "bad_b", "tool_id": "sma", "parameters": {}},
            _sma_tool("good_c", 200),
        )
        body = client.post("/tools/validate-toolset", json=payload).json()
        assert body["valid"] is False
        assert any("bad_b" in e for e in body["errors"])
        assert not any("good_a" in e for e in body["errors"])
        assert not any("good_c" in e for e in body["errors"])


# ---------------------------------------------------------------------------
# TestMalformedRequest
# ---------------------------------------------------------------------------

class TestMalformedRequest:
    def test_missing_toolset_id_returns_422(self) -> None:
        client = _client()
        response = client.post("/tools/validate-toolset", json={"tools": []})
        assert response.status_code == 422

    def test_missing_tools_field_returns_422(self) -> None:
        client = _client()
        response = client.post("/tools/validate-toolset", json={"toolset_id": "x"})
        assert response.status_code == 422

    def test_empty_json_body_returns_422(self) -> None:
        client = _client()
        response = client.post("/tools/validate-toolset", json={})
        assert response.status_code == 422

    def test_non_json_body_returns_422(self) -> None:
        client = _client()
        response = client.post(
            "/tools/validate-toolset",
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422

    def test_duplicate_instance_id_returns_422(self) -> None:
        client = _client()
        payload = _toolset(
            _sma_tool("dup", 20),
            _sma_tool("dup", 50),
        )
        response = client.post("/tools/validate-toolset", json=payload)
        assert response.status_code == 422

    def test_extra_fields_on_toolset_returns_422(self) -> None:
        client = _client()
        payload = {
            "toolset_id": "x",
            "tools": [],
            "unexpected_field": True,
        }
        response = client.post("/tools/validate-toolset", json=payload)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# TestExecutionIndependence
# ---------------------------------------------------------------------------

class TestExecutionIndependence:
    def test_endpoint_does_not_call_compute_sma(self, monkeypatch) -> None:
        def _explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("compute_sma() must not be called during validation")

        monkeypatch.setattr("backend.tools.compute_sma", _explode)
        monkeypatch.setattr("backend.tools.sma.compute_sma", _explode)

        client = _client()
        payload = _toolset(_sma_tool("sma_fast", 20))
        response = client.post("/tools/validate-toolset", json=payload)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# TestGetToolsUnchanged
# ---------------------------------------------------------------------------

class TestGetToolsUnchanged:
    def test_get_tools_still_returns_200(self) -> None:
        client = _client()
        response = client.get("/tools")
        assert response.status_code == 200

    def test_get_tools_still_contains_sma(self) -> None:
        client = _client()
        response = client.get("/tools")
        tool_ids = {t["tool_id"] for t in response.json()["tools"]}
        assert "sma" in tool_ids
