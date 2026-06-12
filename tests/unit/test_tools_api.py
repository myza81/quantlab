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


# ---------------------------------------------------------------------------
# short_name — Strategy-UX-1E (metadata-driven compact labels)
# ---------------------------------------------------------------------------

class TestToolShortName:
    """short_name is metadata-driven and exposed via the /tools API response."""

    def test_ema_has_short_name(self) -> None:
        from backend.tools.ema import EMA_METADATA
        assert EMA_METADATA.short_name == "EMA"

    def test_sma_has_short_name(self) -> None:
        from backend.tools.sma import SMA_METADATA
        assert SMA_METADATA.short_name == "SMA"

    def test_rsi_has_short_name(self) -> None:
        from backend.tools.rsi import RSI_METADATA
        assert RSI_METADATA.short_name == "RSI"

    def test_macd_has_short_name(self) -> None:
        from backend.tools.macd import MACD_METADATA
        assert MACD_METADATA.short_name == "MACD"

    def test_atr_has_short_name(self) -> None:
        from backend.tools.atr import ATR_METADATA
        assert ATR_METADATA.short_name == "ATR"

    def test_bollinger_has_short_name(self) -> None:
        from backend.tools.bollinger_bands import BOLLINGER_METADATA
        assert BOLLINGER_METADATA.short_name == "BB"

    def test_short_name_exposed_in_api_response(self) -> None:
        """GET /tools must include short_name for all built-in tools."""
        resp = _client().get("/tools")
        assert resp.status_code == 200
        tools = {t["tool_id"]: t for t in resp.json()["tools"]}
        assert tools["ema"]["short_name"] == "EMA"
        assert tools["sma"]["short_name"] == "SMA"
        assert tools["rsi"]["short_name"] == "RSI"
        assert tools["macd"]["short_name"] == "MACD"
        assert tools["atr"]["short_name"] == "ATR"
        assert tools["bollinger_bands"]["short_name"] == "BB"

    def test_tool_without_short_name_is_none(self) -> None:
        """A ToolMetadata without short_name defaults to None."""
        from backend.strategy_registry.models import RuntimeMode
        meta = ToolMetadata(
            tool_id="no_short",
            name="Tool Without Short Name",
            version="1.0.0",
            category=ToolCategory.indicator,
            status=ToolStatus.experimental,
            description="No short_name defined.",
            input_data_family="ohlcv",
            output_feature_names=("value",),
            parameters=(),
            supported_runtime_modes=frozenset({RuntimeMode.RESEARCH}),
            visualization_capabilities=frozenset(),
        )
        assert meta.short_name is None


# ---------------------------------------------------------------------------
# TOOLSET-UX-ENUM-1 — ParameterSpec.options + API serialization
# ---------------------------------------------------------------------------

class TestParameterSpecOptions:
    """ParameterSpec accepts options and the /tools API serializes them."""

    def test_parameter_spec_accepts_options(self) -> None:
        spec = ParameterSpec(
            name="smoothing_type",
            description="SMA or EMA",
            type_label="str",
            required=True,
            default="SMA",
            options=("SMA", "EMA"),
        )
        assert spec.options == ("SMA", "EMA")

    def test_parameter_spec_options_defaults_to_none(self) -> None:
        spec = ParameterSpec(
            name="period",
            description="Window",
            type_label="int",
            required=True,
            default=14,
        )
        assert spec.options is None

    def test_parameter_spec_options_is_ordered(self) -> None:
        spec = ParameterSpec(
            name="mode",
            description="Mode",
            type_label="str",
            required=True,
            default="A",
            options=("A", "B", "C"),
        )
        assert list(spec.options) == ["A", "B", "C"]  # type: ignore[arg-type]

    def test_rsi_smoothing_smoothing_type_has_options(self) -> None:
        from backend.tools.rsi_smoothing import RSI_SMOOTHING_METADATA
        param = next(p for p in RSI_SMOOTHING_METADATA.parameters if p.name == "smoothing_type")
        assert param.options == ("SMA", "EMA")

    def test_sma_source_has_options(self) -> None:
        from backend.tools.sma import SMA_METADATA
        param = next(p for p in SMA_METADATA.parameters if p.name == "source")
        assert param.options == ("close", "open", "high", "low", "hl2", "hlc3", "ohlc4")

    def test_ema_source_has_options(self) -> None:
        from backend.tools.ema import EMA_METADATA
        param = next(p for p in EMA_METADATA.parameters if p.name == "source")
        assert param.options == ("close", "open", "high", "low", "hl2", "hlc3", "ohlc4")

    def test_rsi_smoothing_other_params_have_no_options(self) -> None:
        from backend.tools.rsi_smoothing import RSI_SMOOTHING_METADATA
        for p in RSI_SMOOTHING_METADATA.parameters:
            if p.name != "smoothing_type":
                assert p.options is None, f"{p.name} should have options=None"

    def test_api_serializes_options_for_rsi_smoothing(self) -> None:
        resp = _client().get("/tools")
        assert resp.status_code == 200
        tools = {t["tool_id"]: t for t in resp.json()["tools"]}
        params = {p["name"]: p for p in tools["rsi_smoothing"]["parameters"]}
        assert params["smoothing_type"]["options"] == ["SMA", "EMA"]

    def test_api_serializes_options_for_source_params(self) -> None:
        resp = _client().get("/tools")
        assert resp.status_code == 200
        tools = {t["tool_id"]: t for t in resp.json()["tools"]}
        expected = ["close", "open", "high", "low", "hl2", "hlc3", "ohlc4"]
        for tool_id in ("sma", "ema"):
            params = {p["name"]: p for p in tools[tool_id]["parameters"]}
            assert params["source"]["options"] == expected

    def test_api_options_field_present_on_all_tools(self) -> None:
        """options key must be present in every parameter response (may be null)."""
        resp = _client().get("/tools")
        assert resp.status_code == 200
        for tool in resp.json()["tools"]:
            for param in tool["parameters"]:
                assert "options" in param, (
                    f"options missing from {tool['tool_id']}.{param['name']}"
                )

    def test_non_enum_params_without_options_are_unaffected(self) -> None:
        """Non-enum params return null; no existing behavior changes."""
        resp = _client().get("/tools")
        assert resp.status_code == 200
        tools = {t["tool_id"]: t for t in resp.json()["tools"]}
        for tool_id in ("sma", "ema", "rsi", "macd", "bollinger_bands", "atr"):
            for param in tools[tool_id]["parameters"]:
                if param["name"] not in ("source", "smoothing_type"):
                    assert param["options"] is None, (
                        f"Unexpected options on {tool_id}.{param['name']}"
                    )
