"""
Tests for GET /tools.

Covers:
- Happy path: returns 200 with registered tool metadata
- SMA tool exists in response
- Required metadata and parameter fields exist
- Response payload is JSON serializable
- Response ordering is deterministic/stable
- Endpoint does not execute compute_sma()
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.routes.tools import get_tool_registry
from backend.tools import (
    ParameterSpec,
    ToolCategory,
    ToolMetadata,
    ToolRegistry,
    ToolStatus,
    VisualizationCapability,
)
from backend.strategy_registry.models import RuntimeMode


def _client() -> TestClient:
    return TestClient(app)


def _cleanup() -> None:
    app.dependency_overrides.pop(get_tool_registry, None)


def _metadata(tool_id: str, name: str) -> ToolMetadata:
    return ToolMetadata(
        tool_id=tool_id,
        name=name,
        version="1.0.0",
        category=ToolCategory.indicator,
        status=ToolStatus.stable,
        description=f"{name} description",
        input_data_family="ohlcv",
        output_feature_names=("value",),
        parameters=(
            ParameterSpec(
                name="period",
                description="Window size",
                type_label="int",
                required=True,
                min_value=1,
            ),
        ),
        supported_runtime_modes=frozenset({
            RuntimeMode.RESEARCH,
            RuntimeMode.BACKTESTING,
        }),
        visualization_capabilities=frozenset({
            VisualizationCapability.produces_line_overlay,
        }),
        min_warmup_bars=0,
        stateful=False,
    )


class TestGetTools:
    def test_returns_200(self) -> None:
        client = _client()
        response = client.get("/tools")

        assert response.status_code == 200

    def test_sma_tool_exists_in_response(self) -> None:
        client = _client()
        response = client.get("/tools")

        tool_ids = {tool["tool_id"] for tool in response.json()["tools"]}
        assert "sma" in tool_ids

    def test_required_metadata_fields_exist(self) -> None:
        client = _client()
        response = client.get("/tools")

        sma = next(tool for tool in response.json()["tools"] if tool["tool_id"] == "sma")
        assert sma["name"] == "Simple Moving Average"
        assert sma["version"] == "1.0.0"
        assert sma["category"] == "indicator"
        assert sma["status"] == "stable"
        assert sma["input_data_family"] == "ohlcv"
        assert sma["output_feature_names"] == ["sma"]
        assert "supported_runtime_modes" in sma
        assert "visualization_capabilities" in sma
        assert "min_warmup_bars" in sma
        assert sma["stateful"] is False

    def test_parameter_schema_exists(self) -> None:
        client = _client()
        response = client.get("/tools")

        sma = next(tool for tool in response.json()["tools"] if tool["tool_id"] == "sma")
        period = next(parameter for parameter in sma["parameters"] if parameter["name"] == "period")
        assert period["type_label"] == "int"
        assert period["required"] is True
        assert period["default"] is None
        assert period["min_value"] == 1
        assert "max_value" in period

    def test_response_is_json_serializable(self) -> None:
        client = _client()
        response = client.get("/tools")

        payload = response.json()
        encoded = json.dumps(payload, sort_keys=True)
        assert '"tool_id": "sma"' in encoded

    def test_response_shape_is_deterministic_and_sorted(self) -> None:
        registry = ToolRegistry()
        registry.register(_metadata("zeta", "Zeta"))
        registry.register(_metadata("alpha", "Alpha"))
        app.dependency_overrides[get_tool_registry] = lambda: registry

        client = _client()
        first = client.get("/tools")
        second = client.get("/tools")
        _cleanup()

        first_payload = first.json()
        second_payload = second.json()
        assert first_payload == second_payload
        assert [tool["tool_id"] for tool in first_payload["tools"]] == ["alpha", "zeta"]
        assert first_payload["tools"][0]["supported_runtime_modes"] == [
            "backtesting",
            "research",
        ]

    def test_endpoint_does_not_execute_compute_sma(self, monkeypatch) -> None:
        def _explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("compute_sma() should not be called by GET /tools")

        monkeypatch.setattr("backend.tools.compute_sma", _explode)
        monkeypatch.setattr("backend.tools.sma.compute_sma", _explode)

        client = _client()
        response = client.get("/tools")

        assert response.status_code == 200
