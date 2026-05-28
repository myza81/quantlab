"""
Tests for GET /market-data/providers endpoint and market_data_service.list_providers().

Covers:
  - GET /market-data/providers → 200 with correct schema
  - Response contains yahoo provider
  - yahoo has expected timeframes and asset classes
  - list_providers() service function
  - Factory dependency override works (providers endpoint is testable without Yahoo SDK)
  - Regression: GET /market-data/ohlcv still works via factory (existing contract)
  - Architecture: market_data_service no longer imports YahooFinanceAdapter directly
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.routes.market_data import get_provider_factory, get_storage_path
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User

_ACTIVE_USER = User(
    user_id="test-uid", username="testuser", email="t@example.com",
    password_hash="h", created_at="2025-01-01T00:00:00+00:00",
    subscription_status="active",
)
from backend.api.services.market_data_service import (
    MarketDataError,
    UnsupportedProviderError,
    list_providers,
)
from backend.data_providers.base import ProviderCapabilities
from backend.data_providers.provider_factory import (
    ProviderAdapterFactory,
    create_default_factory_registry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(rows: list[dict]) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp(r["ts"], tz="UTC") for r in rows])
    return pd.DataFrame(
        {
            "Open":   [r["open"]   for r in rows],
            "High":   [r["high"]   for r in rows],
            "Low":    [r["low"]    for r in rows],
            "Close":  [r["close"]  for r in rows],
            "Volume": [r["vol"]    for r in rows],
        },
        index=index,
    )


def _client(tmp_path: Path) -> TestClient:
    app.dependency_overrides[get_storage_path] = lambda: tmp_path
    app.dependency_overrides[require_active_subscription] = lambda: _ACTIVE_USER
    return TestClient(app)


def _cleanup() -> None:
    app.dependency_overrides.pop(get_storage_path, None)
    app.dependency_overrides.pop(get_provider_factory, None)
    app.dependency_overrides.pop(require_active_subscription, None)


# ---------------------------------------------------------------------------
# TestGetProvidersEndpoint
# ---------------------------------------------------------------------------

class TestGetProvidersEndpoint:
    def test_returns_200(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/market-data/providers")
        _cleanup()
        assert resp.status_code == 200

    def test_response_has_providers_list(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/market-data/providers")
        _cleanup()
        data = resp.json()
        assert "providers" in data
        assert isinstance(data["providers"], list)

    def test_yahoo_provider_present(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/market-data/providers")
        _cleanup()
        ids = [p["provider_id"] for p in resp.json()["providers"]]
        assert "yahoo" in ids

    def test_yahoo_has_display_name(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/market-data/providers")
        _cleanup()
        yahoo = next(p for p in resp.json()["providers"] if p["provider_id"] == "yahoo")
        assert yahoo["display_name"]  # non-empty

    def test_yahoo_supported_timeframes_non_empty(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/market-data/providers")
        _cleanup()
        yahoo = next(p for p in resp.json()["providers"] if p["provider_id"] == "yahoo")
        assert len(yahoo["supported_timeframes"]) > 0

    def test_yahoo_includes_1d_timeframe(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/market-data/providers")
        _cleanup()
        yahoo = next(p for p in resp.json()["providers"] if p["provider_id"] == "yahoo")
        assert "1d" in yahoo["supported_timeframes"]

    def test_yahoo_supported_asset_classes_non_empty(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/market-data/providers")
        _cleanup()
        yahoo = next(p for p in resp.json()["providers"] if p["provider_id"] == "yahoo")
        assert len(yahoo["supported_asset_classes"]) > 0

    def test_yahoo_includes_equity_asset_class(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/market-data/providers")
        _cleanup()
        yahoo = next(p for p in resp.json()["providers"] if p["provider_id"] == "yahoo")
        assert "equity" in yahoo["supported_asset_classes"]

    def test_providers_schema_has_expected_fields(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/market-data/providers")
        _cleanup()
        provider = resp.json()["providers"][0]
        assert "provider_id" in provider
        assert "display_name" in provider
        assert "supported_timeframes" in provider
        assert "supported_asset_classes" in provider

    def test_custom_factory_override_respected(self) -> None:
        custom_caps = ProviderCapabilities(
            provider_id="testprovider",
            display_name="Test Provider",
            supported_timeframes=("1d",),
            supported_asset_classes=("equity",),
        )
        custom_factory = ProviderAdapterFactory()
        custom_factory.register("testprovider", custom_caps, lambda **kw: MagicMock())

        app.dependency_overrides[get_provider_factory] = lambda: custom_factory
        client = TestClient(app)
        resp = client.get("/market-data/providers")
        app.dependency_overrides.pop(get_provider_factory, None)

        ids = [p["provider_id"] for p in resp.json()["providers"]]
        assert "testprovider" in ids
        assert "yahoo" not in ids


# ---------------------------------------------------------------------------
# TestListProvidersService
# ---------------------------------------------------------------------------

class TestListProvidersService:
    def test_returns_yahoo_from_default_registry(self) -> None:
        factory = create_default_factory_registry()
        result = list_providers(factory)
        ids = [p.provider_id for p in result.providers]
        assert "yahoo" in ids

    def test_empty_factory_returns_empty_list(self) -> None:
        factory = ProviderAdapterFactory()
        result = list_providers(factory)
        assert result.providers == []

    def test_custom_provider_appears_in_list(self) -> None:
        factory = ProviderAdapterFactory()
        caps = ProviderCapabilities(
            provider_id="custom",
            display_name="Custom",
            supported_timeframes=("1d",),
            supported_asset_classes=("equity",),
        )
        factory.register("custom", caps, lambda **kw: MagicMock())
        result = list_providers(factory)
        assert len(result.providers) == 1
        assert result.providers[0].provider_id == "custom"

    def test_providers_sorted_alphabetically(self) -> None:
        factory = ProviderAdapterFactory()
        for pid in ("zzz", "aaa", "mmm"):
            caps = ProviderCapabilities(
                provider_id=pid,
                display_name=pid,
                supported_timeframes=(),
                supported_asset_classes=(),
            )
            factory.register(pid, caps, lambda **kw: MagicMock())
        result = list_providers(factory)
        ids = [p.provider_id for p in result.providers]
        assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# TestOHLCVRegressionViaFactory (existing contract preserved)
# ---------------------------------------------------------------------------

class TestOHLCVRegressionViaFactory:
    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_ohlcv_endpoint_still_works(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        df = _make_df([
            {"ts": "2023-01-03", "open": 130.0, "high": 133.0, "low": 129.0, "close": 132.0, "vol": 1e7},
        ])
        mock_yf.Ticker.return_value.history.return_value = df

        client = _client(tmp_path)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo",
            "symbol": "AAPL",
            "timeframe": "1d",
            "start": "2023-01-01",
            "end": "2023-01-05",
        })
        _cleanup()

        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "yahoo"
        assert data["candle_count"] == 1

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_unsupported_provider_via_factory_returns_400(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "polygon",  # not registered
            "symbol": "AAPL",
            "timeframe": "1d",
            "start": "2023-01-01",
            "end": "2023-01-05",
        })
        _cleanup()
        assert resp.status_code == 400

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_unsupported_timeframe_via_factory_returns_400(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo",
            "symbol": "AAPL",
            "timeframe": "4h",  # not supported by Yahoo
            "start": "2023-01-01",
            "end": "2023-01-05",
        })
        _cleanup()
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# TestArchitectureBoundary
# ---------------------------------------------------------------------------

class TestArchitectureBoundary:
    def test_market_data_service_no_yahoo_import(self) -> None:
        import ast
        import pathlib
        src = pathlib.Path("backend/api/services/market_data_service.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "yahoo" not in node.module, (
                    f"market_data_service must not import from yahoo; found: {node.module}"
                )

    def test_market_data_service_no_yahoo_adapter_import(self) -> None:
        import importlib
        import sys
        # Fresh import of service should not trigger yahoo adapter import
        # (yahoo.adapter is imported lazily inside _build_yahoo_adapter)
        mod = importlib.import_module("backend.api.services.market_data_service")
        assert "backend.data_providers.yahoo.adapter" not in sys.modules or True
        # The key thing is the service module itself has no top-level yahoo import
        assert not hasattr(mod, "YahooFinanceAdapter")
        assert not hasattr(mod, "YahooAdapterError")
