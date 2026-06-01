"""
Unit tests for backend/data_providers/polygon/search.py — Chart-UX-2.

Covers:
  - search_polygon: happy path with mocked HTTP (single + multiple results)
  - search_polygon: normalizes type codes → asset_class
  - search_polygon: normalizes exchange MIC codes → display names
  - search_polygon: empty results list → []
  - search_polygon: HTTP 404 → [] (graceful)
  - search_polygon: HTTP 429 → [] (graceful, rate limit)
  - search_polygon: HTTP 401 → raises PolygonSearchError
  - search_polygon: HTTP 500 → raises PolygonSearchError
  - search_polygon: network OSError → raises PolygonSearchError
  - search_polygon: missing api_key + fallback disabled → raises PolygonSearchError
  - _normalize: valid dict → correct fields
  - _normalize: missing ticker → None
  - Architecture boundary: no API imports in polygon.search
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from backend.data_providers.polygon.search import (
    PolygonSearchError,
    _normalize,
    search_polygon,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_RESULT = {
    "ticker":           "AAPL",
    "name":             "Apple Inc.",
    "primary_exchange": "XNAS",
    "type":             "CS",
    "currency_name":    "usd",
    "active":           True,
}

_SAMPLE_ETF_RESULT = {
    "ticker":           "SPY",
    "name":             "SPDR S&P 500 ETF Trust",
    "primary_exchange": "ARCX",
    "type":             "ETF",
    "currency_name":    "usd",
    "active":           True,
}

_SAMPLE_CRYPTO_RESULT = {
    "ticker":           "X:BTCUSD",
    "name":             "Bitcoin / US Dollar",
    "primary_exchange": "",
    "type":             "CRYPTOCURRENCIES",
    "currency_name":    "usd",
    "active":           True,
}


def _mock_urlopen(results: list[dict], status: int = 200) -> MagicMock:
    """Return a mock for urllib.request.urlopen that yields the given results."""
    body = json.dumps({"status": "OK", "results": results}).encode()
    mock_response = MagicMock()
    mock_response.read.return_value = body
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    return mock_response


def _mock_http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url="", code=code, msg="", hdrs=None, fp=None)  # type: ignore


# ---------------------------------------------------------------------------
# _normalize — unit tests
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_happy_path_equity(self) -> None:
        result = _normalize(_SAMPLE_RESULT)
        assert result is not None
        assert result["symbol"]      == "AAPL"
        assert result["name"]        == "Apple Inc."
        assert result["exchange"]    == "NASDAQ"    # XNAS → NASDAQ
        assert result["asset_class"] == "equity"
        assert result["currency"]    == "USD"
        assert result["type_label"]  == "Equity"

    def test_etf_type_code(self) -> None:
        result = _normalize(_SAMPLE_ETF_RESULT)
        assert result is not None
        assert result["asset_class"] == "etf"
        assert result["exchange"]    == "NYSE ARCA"  # ARCX → NYSE ARCA
        assert result["type_label"]  == "ETF"

    def test_crypto_type_code(self) -> None:
        result = _normalize(_SAMPLE_CRYPTO_RESULT)
        assert result is not None
        assert result["asset_class"] == "crypto"
        assert result["type_label"]  == "Cryptocurrency"

    def test_missing_ticker_returns_none(self) -> None:
        assert _normalize({"name": "No ticker", "type": "CS"}) is None

    def test_currency_upcased(self) -> None:
        result = _normalize({**_SAMPLE_RESULT, "currency_name": "myr"})
        assert result is not None
        assert result["currency"] == "MYR"

    def test_unknown_exchange_kept_as_is(self) -> None:
        result = _normalize({**_SAMPLE_RESULT, "primary_exchange": "BURSA"})
        assert result is not None
        assert result["exchange"] == "BURSA"

    def test_empty_primary_exchange_shows_unknown(self) -> None:
        result = _normalize({**_SAMPLE_RESULT, "primary_exchange": ""})
        assert result is not None
        assert result["exchange"] == "Unknown"

    def test_unknown_type_falls_back_to_equity(self) -> None:
        result = _normalize({**_SAMPLE_RESULT, "type": "WEIRD"})
        assert result is not None
        assert result["asset_class"] == "equity"


# ---------------------------------------------------------------------------
# search_polygon — integration-style with mocked HTTP
# ---------------------------------------------------------------------------

class TestSearchPolygon:
    @patch("urllib.request.urlopen")
    def test_happy_path_returns_results(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_urlopen([_SAMPLE_RESULT])
        results = search_polygon(query="AAPL", limit=5, api_key="testkey")
        assert len(results) == 1
        assert results[0]["symbol"] == "AAPL"

    @patch("urllib.request.urlopen")
    def test_multiple_results_capped_to_limit(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_urlopen([_SAMPLE_RESULT, _SAMPLE_ETF_RESULT])
        results = search_polygon(query="A", limit=1, api_key="testkey")
        assert len(results) == 1

    @patch("urllib.request.urlopen")
    def test_empty_results_returns_empty_list(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_urlopen([])
        results = search_polygon(query="XYZNOTREAL", limit=5, api_key="testkey")
        assert results == []

    @patch("urllib.request.urlopen")
    def test_http_404_returns_empty_list(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = _mock_http_error(404)
        results = search_polygon(query="AAPL", limit=5, api_key="testkey")
        assert results == []

    @patch("urllib.request.urlopen")
    def test_http_429_returns_empty_list(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = _mock_http_error(429)
        results = search_polygon(query="AAPL", limit=5, api_key="testkey")
        assert results == []

    @patch("urllib.request.urlopen")
    def test_http_401_raises_polygon_search_error(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = _mock_http_error(401)
        with pytest.raises(PolygonSearchError, match="authentication failed"):
            search_polygon(query="AAPL", limit=5, api_key="badkey")

    @patch("urllib.request.urlopen")
    def test_http_500_raises_polygon_search_error(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = _mock_http_error(500)
        with pytest.raises(PolygonSearchError, match="server error"):
            search_polygon(query="AAPL", limit=5, api_key="testkey")

    @patch("urllib.request.urlopen")
    def test_network_oserror_raises_polygon_search_error(
        self, mock_urlopen: MagicMock
    ) -> None:
        mock_urlopen.side_effect = OSError("connection refused")
        with pytest.raises(PolygonSearchError, match="network error"):
            search_polygon(query="AAPL", limit=5, api_key="testkey")

    def test_missing_api_key_fallback_disabled_raises(self) -> None:
        """No key + polygon_allow_env_fallback=False → PolygonSearchError."""
        from backend.core.config import settings
        original = settings.polygon_allow_env_fallback
        settings.polygon_allow_env_fallback = False  # type: ignore[misc]
        try:
            with pytest.raises(PolygonSearchError, match="API key"):
                search_polygon(query="AAPL", limit=5, api_key=None)
        finally:
            settings.polygon_allow_env_fallback = original  # type: ignore[misc]

    @patch("urllib.request.urlopen")
    def test_result_has_all_required_fields(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_urlopen([_SAMPLE_RESULT])
        results = search_polygon(query="AAPL", limit=5, api_key="testkey")
        assert len(results) == 1
        for field in ("symbol", "name", "exchange", "asset_class", "currency", "type_label"):
            assert field in results[0], f"Missing field: {field}"


# ---------------------------------------------------------------------------
# Architecture boundary
# ---------------------------------------------------------------------------

class TestPolygonSearchArchitectureBoundary:
    def test_no_api_route_imports_in_polygon_search(self) -> None:
        import importlib
        import sys
        mod_name = "backend.data_providers.polygon.search"
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
        else:
            mod = importlib.import_module(mod_name)
        source = getattr(mod, "__file__", "") or ""
        if source:
            content = open(source).read()
            assert "from backend.api" not in content
            assert "import backend.api" not in content
