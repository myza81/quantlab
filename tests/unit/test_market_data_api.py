"""
Tests for GET /market-data/ohlcv and GET /market-data/search.

All tests patch yf at the adapter module level to avoid real network calls.
Storage uses tmp_path via app.dependency_overrides[get_storage_path].

Covers:
- Happy path: returns normalized candles
- Response schema fields (provider, symbol, timeframe, candle_count, candles)
- Naive datetime query params treated as UTC
- Unsupported provider → 400
- Unsupported timeframe → 400
- Provider returns empty DataFrame → 200 with empty candles list
- Missing required query params → 422
- OHLCV without exchange → defaults to "unknown" in response
- Asset search happy path (mocked yfinance.Search)
- Asset search returns empty results gracefully
- Asset search query too short → 400
- Chart-UX-2: provider search capability matrix
  - Yahoo search: supports_search=True, results returned
  - Polygon search: supports_search=True, dispatched correctly
  - CSV provider: supports_search=False → 400 "does not support"
  - Unknown provider: not registered → 400 "not registered"
  - Searcher raises → 400 "Search failed"
  - GET /providers response includes supports_search flag
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.routes.market_data import get_storage_path
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User

_ACTIVE_USER = User(
    user_id="test-uid", username="testuser", email="t@example.com",
    password_hash="h", created_at="2025-01-01T00:00:00+00:00",
    subscription_status="active",
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
    app.dependency_overrides.pop(require_active_subscription, None)


# ---------------------------------------------------------------------------
# TestGetOHLCVHappyPath
# ---------------------------------------------------------------------------

class TestGetOHLCVHappyPath:
    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_returns_200_with_candles(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        df = _make_df([
            {"ts": "2023-01-03", "open": 130.0, "high": 133.0, "low": 129.0, "close": 132.0, "vol": 1e7},
            {"ts": "2023-01-04", "open": 132.0, "high": 135.0, "low": 131.0, "close": 134.0, "vol": 2e7},
        ])
        mock_yf.Ticker.return_value.history.return_value = df

        client = _client(tmp_path)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo",
            "symbol": "AAPL",
            "asset_class": "equity",
            "exchange": "NASDAQ",
            "timeframe": "1d",
            "start": "2023-01-01",
            "end": "2023-01-05",
        })
        _cleanup()

        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "yahoo"
        assert data["symbol"] == "AAPL"
        assert data["asset_class"] == "equity"
        assert data["exchange"] == "NASDAQ"
        assert data["timeframe"] == "1d"
        assert data["candle_count"] == 2
        assert len(data["candles"]) == 2

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_candle_fields_correct(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        df = _make_df([
            {"ts": "2023-01-03", "open": 130.0, "high": 133.0, "low": 129.0, "close": 132.0, "vol": 80_000_000.0},
        ])
        mock_yf.Ticker.return_value.history.return_value = df

        client = _client(tmp_path)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo", "symbol": "AAPL", "asset_class": "equity",
            "exchange": "NASDAQ", "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
        })
        _cleanup()

        candle = resp.json()["candles"][0]
        assert candle["open"] == 130.0
        assert candle["high"] == 133.0
        assert candle["low"] == 129.0
        assert candle["close"] == 132.0
        assert candle["volume"] == 80_000_000.0
        assert "timestamp" in candle

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_timestamp_is_utc_aware(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        df = _make_df([
            {"ts": "2023-01-03", "open": 130.0, "high": 133.0, "low": 129.0, "close": 132.0, "vol": 1e7},
        ])
        mock_yf.Ticker.return_value.history.return_value = df

        client = _client(tmp_path)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo", "symbol": "AAPL", "asset_class": "equity",
            "exchange": "NASDAQ", "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
        })
        _cleanup()

        ts = resp.json()["candles"][0]["timestamp"]
        # FastAPI serialises datetime with UTC offset
        assert "2023-01-03" in ts

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_naive_datetime_params_accepted_as_utc(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        """Query params without timezone offset should be treated as UTC."""
        df = _make_df([
            {"ts": "2023-01-03", "open": 130.0, "high": 133.0, "low": 129.0, "close": 132.0, "vol": 1e7},
        ])
        mock_yf.Ticker.return_value.history.return_value = df

        client = _client(tmp_path)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo", "symbol": "AAPL", "asset_class": "equity",
            "exchange": "NASDAQ", "timeframe": "1d",
            "start": "2023-01-01T00:00:00",  # naive — no Z/+00:00
            "end": "2023-01-05T00:00:00",
        })
        _cleanup()

        assert resp.status_code == 200

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_empty_dataframe_returns_empty_candles(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.Ticker.return_value.history.return_value = pd.DataFrame()

        client = _client(tmp_path)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo", "symbol": "INVALID_XYZ", "asset_class": "equity",
            "exchange": "NASDAQ", "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
        })
        _cleanup()

        assert resp.status_code == 200
        data = resp.json()
        assert data["candle_count"] == 0
        assert data["candles"] == []


# ---------------------------------------------------------------------------
# TestGetOHLCVValidation
# ---------------------------------------------------------------------------

class TestGetOHLCVValidation:
    def test_unsupported_provider_returns_400(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "polygon",
            "symbol": "AAPL", "asset_class": "equity",
            "exchange": "NASDAQ", "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
        })
        _cleanup()

        assert resp.status_code == 400
        assert "polygon" in resp.json()["detail"].lower()

    def test_unsupported_timeframe_returns_400(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo",
            "symbol": "AAPL", "asset_class": "equity",
            "exchange": "NASDAQ", "timeframe": "4h",  # not supported
            "start": "2023-01-01", "end": "2023-01-05",
        })
        _cleanup()

        assert resp.status_code == 400

    def test_missing_required_param_provider_returns_422(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/market-data/ohlcv", params={
            # provider missing
            "symbol": "AAPL", "asset_class": "equity",
            "exchange": "NASDAQ", "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
        })
        _cleanup()

        assert resp.status_code == 422

    def test_missing_required_param_symbol_returns_422(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo",
            # symbol missing
            "asset_class": "equity", "exchange": "NASDAQ", "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
        })
        _cleanup()

        assert resp.status_code == 422

    def test_missing_required_param_start_returns_422(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo", "symbol": "AAPL", "asset_class": "equity",
            "exchange": "NASDAQ", "timeframe": "1d",
            # start missing
            "end": "2023-01-05",
        })
        _cleanup()

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# TestGetOHLCVDefaults
# ---------------------------------------------------------------------------

class TestGetOHLCVDefaults:
    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_default_asset_class(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.Ticker.return_value.history.return_value = pd.DataFrame()

        client = _client(tmp_path)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo", "symbol": "AAPL",
            "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
            # asset_class and exchange omitted — both use defaults
        })
        _cleanup()

        assert resp.status_code == 200
        data = resp.json()
        assert data["asset_class"] == "equity"

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_omitted_exchange_defaults_to_unknown(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        """When exchange is not supplied, backend normalises it to 'unknown'."""
        mock_yf.Ticker.return_value.history.return_value = pd.DataFrame()

        client = _client(tmp_path)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo", "symbol": "KO",
            "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
        })
        _cleanup()

        assert resp.status_code == 200
        assert resp.json()["exchange"] == "unknown"


# ---------------------------------------------------------------------------
# TestAssetSearch
# ---------------------------------------------------------------------------

class TestAssetSearch:
    def _make_mock_search(self, quotes: list[dict]) -> MagicMock:
        """Build a mock yfinance.Search instance whose .quotes returns *quotes*."""
        mock_instance = MagicMock()
        mock_instance.quotes = quotes
        return mock_instance

    @patch("yfinance.Search")
    def test_search_happy_path(self, mock_Search: MagicMock, tmp_path: Path) -> None:
        mock_Search.return_value = self._make_mock_search([
            {
                "symbol": "KO", "longname": "The Coca-Cola Company",
                "exchDisp": "NYSE", "quoteType": "EQUITY",
                "currency": "USD", "typeDisp": "Equity",
            },
        ])

        client = _client(tmp_path)
        resp = client.get("/market-data/search", params={"q": "KO"})
        _cleanup()

        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "KO"
        assert data["provider"] == "yahoo"
        assert len(data["results"]) == 1
        result = data["results"][0]
        assert result["symbol"] == "KO"
        assert result["name"] == "The Coca-Cola Company"
        assert result["exchange"] == "NYSE"
        assert result["asset_class"] == "equity"
        assert result["currency"] == "USD"
        assert result["type_label"] == "Equity"

    @patch("yfinance.Search")
    def test_search_empty_results_returned_gracefully(self, mock_Search: MagicMock, tmp_path: Path) -> None:
        mock_Search.return_value = self._make_mock_search([])

        client = _client(tmp_path)
        resp = client.get("/market-data/search", params={"q": "XYZNOTREAL123"})
        _cleanup()

        assert resp.status_code == 200
        data = resp.json()
        assert data["results"] == []

    def test_search_query_too_short_returns_400(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/market-data/search", params={"q": "X"})
        _cleanup()

        assert resp.status_code == 400
        assert "2" in resp.json()["detail"]  # minimum length mentioned

    @patch("yfinance.Search")
    def test_search_multiple_results(self, mock_Search: MagicMock, tmp_path: Path) -> None:
        mock_Search.return_value = self._make_mock_search([
            {
                "symbol": "AAPL", "longname": "Apple Inc.",
                "exchDisp": "NASDAQ", "quoteType": "EQUITY",
                "currency": "USD", "typeDisp": "Equity",
            },
            {
                "symbol": "AAPLX", "longname": "Apple Mutual Fund",
                "exchDisp": "NYSE", "quoteType": "MUTUALFUND",
                "currency": "USD", "typeDisp": "Fund",
            },
        ])

        client = _client(tmp_path)
        resp = client.get("/market-data/search", params={"q": "apple"})
        _cleanup()

        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 2
        assert results[0]["asset_class"] == "equity"
        assert results[1]["asset_class"] == "fund"

    @patch("yfinance.Search")
    def test_search_yfinance_error_returns_empty(self, mock_Search: MagicMock, tmp_path: Path) -> None:
        """When yfinance.Search raises, the service returns empty results (no 500)."""
        mock_Search.side_effect = RuntimeError("network timeout")

        client = _client(tmp_path)
        resp = client.get("/market-data/search", params={"q": "AAPL"})
        _cleanup()

        assert resp.status_code == 200
        assert resp.json()["results"] == []


# ---------------------------------------------------------------------------
# TestSearchCapability — Chart-UX-2 provider search capability matrix
# ---------------------------------------------------------------------------

class TestSearchCapability:
    """
    API-level tests for Chart-UX-2 provider search capability handling.

    Error-message taxonomy (must match backend market_data.py docstring):
        unknown provider     → "is not registered"
        unsupported provider → "does not support"
        searcher raised      → "Search failed"
    """

    @patch("yfinance.Search")
    def test_yahoo_search_returns_results(
        self, mock_Search: MagicMock, tmp_path: Path
    ) -> None:
        """Yahoo supports search — results returned normally."""
        mock_instance = MagicMock()
        mock_instance.quotes = [
            {
                "symbol": "KO", "longname": "The Coca-Cola Company",
                "exchDisp": "NYSE", "quoteType": "EQUITY",
                "currency": "USD", "typeDisp": "Equity",
            },
        ]
        mock_Search.return_value = mock_instance

        client = _client(tmp_path)
        resp = client.get("/market-data/search", params={"q": "KO", "provider": "yahoo"})
        _cleanup()

        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 1
        assert resp.json()["results"][0]["symbol"] == "KO"

    def test_csv_provider_search_returns_400_unsupported(
        self, tmp_path: Path
    ) -> None:
        """CSV has no searcher → 400 with 'does not support' message."""
        client = _client(tmp_path)
        resp = client.get("/market-data/search", params={"q": "AAPL", "provider": "csv"})
        _cleanup()

        assert resp.status_code == 400
        assert "does not support" in resp.json()["detail"]

    def test_parquet_provider_search_returns_400_unsupported(
        self, tmp_path: Path
    ) -> None:
        """Parquet has no searcher → 400 with 'does not support' message."""
        client = _client(tmp_path)
        resp = client.get("/market-data/search", params={"q": "AAPL", "provider": "parquet"})
        _cleanup()

        assert resp.status_code == 400
        assert "does not support" in resp.json()["detail"]

    def test_unknown_provider_returns_400_not_registered(
        self, tmp_path: Path
    ) -> None:
        """Unregistered provider name → 400 with 'not registered' message."""
        client = _client(tmp_path)
        resp = client.get("/market-data/search", params={"q": "AAPL", "provider": "binance"})
        _cleanup()

        assert resp.status_code == 400
        assert "not registered" in resp.json()["detail"].lower()

    def test_get_providers_includes_supports_search_flag(
        self, tmp_path: Path
    ) -> None:
        """GET /providers exposes supports_search for each registered provider."""
        client = _client(tmp_path)
        resp = client.get("/market-data/providers")
        _cleanup()

        assert resp.status_code == 200
        providers = {p["provider_id"]: p for p in resp.json()["providers"]}
        assert providers["yahoo"]["supports_search"] is True
        assert providers["polygon"]["supports_search"] is True
        assert providers["csv"]["supports_search"] is False
        assert providers["parquet"]["supports_search"] is False

    @patch("yfinance.Search")
    def test_yahoo_search_no_results_returns_200_empty(
        self, mock_Search: MagicMock, tmp_path: Path
    ) -> None:
        """Yahoo search with no matches → 200 with empty results list."""
        mock_instance = MagicMock()
        mock_instance.quotes = []
        mock_Search.return_value = mock_instance

        client = _client(tmp_path)
        resp = client.get(
            "/market-data/search", params={"q": "XYZNOTREAL999", "provider": "yahoo"}
        )
        _cleanup()

        assert resp.status_code == 200
        assert resp.json()["results"] == []

    @patch("backend.data_providers.yahoo.search.search_yahoo",
           side_effect=RuntimeError("provider unavailable"))
    def test_searcher_exception_returns_400_search_failed(
        self, _mock: MagicMock, tmp_path: Path
    ) -> None:
        """
        When the searcher callable raises (not caught internally), the service
        wraps it as AssetSearchError → 400 'Search failed'.
        Yahoo's search_yahoo normally swallows exceptions; here we patch it
        at the module level so the raise propagates through factory.search().
        """
        client = _client(tmp_path)
        resp = client.get("/market-data/search", params={"q": "AAPL", "provider": "yahoo"})
        _cleanup()

        assert resp.status_code == 400
        assert "Search failed" in resp.json()["detail"]

    @patch("backend.data_providers.polygon.search.search_polygon")
    def test_polygon_search_dispatched_and_returns_results(
        self, mock_search_polygon: MagicMock, tmp_path: Path
    ) -> None:
        """Polygon search is dispatched via factory and results are normalized."""
        mock_search_polygon.return_value = [
            {
                "symbol": "AAPL", "name": "Apple Inc.",
                "exchange": "NASDAQ", "asset_class": "equity",
                "currency": "USD", "type_label": "Equity",
            },
        ]

        client = _client(tmp_path)
        resp = client.get(
            "/market-data/search", params={"q": "AAPL", "provider": "polygon"}
        )
        _cleanup()

        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 1
        assert resp.json()["results"][0]["symbol"] == "AAPL"
        mock_search_polygon.assert_called_once()

    def test_search_result_schema_consistent_across_providers(
        self, tmp_path: Path
    ) -> None:
        """All AssetSearchResult objects have the six required fields."""
        with patch("yfinance.Search") as mock_Search:
            mock_instance = MagicMock()
            mock_instance.quotes = [
                {
                    "symbol": "TSLA", "longname": "Tesla Inc.",
                    "exchDisp": "NASDAQ", "quoteType": "EQUITY",
                    "currency": "USD", "typeDisp": "Equity",
                },
            ]
            mock_Search.return_value = mock_instance

            client = _client(tmp_path)
            resp = client.get("/market-data/search", params={"q": "TSLA"})
            _cleanup()

        assert resp.status_code == 200
        result = resp.json()["results"][0]
        for field in ("symbol", "name", "exchange", "asset_class", "currency", "type_label"):
            assert field in result, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# TestCacheRegression — API-level proof of FETCH_AND_STORE cache behavior
# (MD-1 requirement 1 & 2)
# ---------------------------------------------------------------------------

class TestCacheRegression:
    """
    API-level regression tests proving the OHLCVService cache layer works
    correctly through the full HTTP path.

    Design note — boundary-exact candles:
        Coverage is boundary-based (earliest/latest stored timestamp).
        To guarantee a true cache HIT on a repeated request, the stored
        candles must reach the exact start and end dates of the request.
        All tests below use candles that sit on the precise boundaries so
        that coverage.earliest == request.start and coverage.latest == request.end,
        leaving zero gaps on the repeat.

    All dates are in 2023 — well in the past — so the trailing-edge freshness
    rule (MD-1) is never triggered, giving clean single-call assertions.
    """

    # Candle timestamps that exactly match the request start/end boundaries
    _START = "2023-01-01"
    _END   = "2023-03-31"

    def _boundary_df(self) -> "pd.DataFrame":
        """Three candles: one on start, one in the middle, one on end."""
        return _make_df([
            {"ts": self._START, "open": 130.0, "high": 133.0, "low": 129.0, "close": 132.0, "vol": 1e7},
            {"ts": "2023-02-15", "open": 135.0, "high": 138.0, "low": 133.0, "close": 136.0, "vol": 1.5e7},
            {"ts": self._END,   "open": 140.0, "high": 143.0, "low": 138.0, "close": 141.0, "vol": 2e7},
        ])

    def _params(self, **overrides: str) -> dict:
        base = {
            "provider": "yahoo", "symbol": "CACH",
            "asset_class": "equity", "exchange": "NASDAQ",
            "timeframe": "1d",
            "start": self._START, "end": self._END,
        }
        base.update(overrides)
        return base

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_repeated_identical_request_calls_provider_only_once(
        self, mock_yf: MagicMock, tmp_path: Path
    ) -> None:
        """Second identical /ohlcv request is served from storage, not the provider."""
        mock_yf.Ticker.return_value.history.return_value = self._boundary_df()

        client = _client(tmp_path)
        resp1 = client.get("/market-data/ohlcv", params=self._params())
        resp2 = client.get("/market-data/ohlcv", params=self._params())
        _cleanup()

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert mock_yf.Ticker.return_value.history.call_count == 1, (
            "Provider should be called exactly once — second request is a cache hit"
        )

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_second_request_returns_same_candles_despite_provider_going_offline(
        self, mock_yf: MagicMock, tmp_path: Path
    ) -> None:
        """
        After the first request populates storage, a second request succeeds
        even if the provider would now return nothing (simulating an offline
        or quota-exhausted data source).
        """
        mock_yf.Ticker.return_value.history.return_value = self._boundary_df()

        client = _client(tmp_path)
        resp1 = client.get("/market-data/ohlcv", params=self._params())

        # Provider now returns nothing — cache must serve data independently
        mock_yf.Ticker.return_value.history.return_value = pd.DataFrame()
        resp2 = client.get("/market-data/ohlcv", params=self._params())
        _cleanup()

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["candles"] == resp2.json()["candles"], (
            "Candles must be identical — second response came from storage"
        )

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_partial_range_extension_only_fetches_missing_gap(
        self, mock_yf: MagicMock, tmp_path: Path
    ) -> None:
        """
        Jan–Mar cached (boundary-exact coverage); Jan–Apr request fetches
        only the Apr gap.  Total provider calls: exactly 2.
        """
        # First: populate Jan–Mar with boundary-exact candles
        mock_yf.Ticker.return_value.history.return_value = self._boundary_df()
        client = _client(tmp_path)
        resp1 = client.get("/market-data/ohlcv", params=self._params())
        assert resp1.status_code == 200
        assert mock_yf.Ticker.return_value.history.call_count == 1

        # Second: extend end to Apr — only the Apr gap should be fetched
        apr_df = _make_df([
            {"ts": "2023-04-03", "open": 142.0, "high": 145.0, "low": 140.0, "close": 143.0, "vol": 1.8e7},
        ])
        mock_yf.Ticker.return_value.history.return_value = apr_df
        resp2 = client.get("/market-data/ohlcv", params=self._params(end="2023-04-30"))
        _cleanup()

        assert resp2.status_code == 200
        assert mock_yf.Ticker.return_value.history.call_count == 2, (
            "Expected exactly 2 total provider calls: Jan–Mar initial + Apr gap only"
        )
        # Jan–Mar (3 candles) + Apr (1 candle) = 4 total
        assert resp2.json()["candle_count"] == 4

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_backward_compat_explicit_exchange_still_works(
        self, mock_yf: MagicMock, tmp_path: Path
    ) -> None:
        """Existing callers that supply exchange= still receive correct data."""
        df = _make_df([
            {"ts": "2023-01-03", "open": 130.0, "high": 133.0, "low": 129.0, "close": 132.0, "vol": 1e7},
        ])
        mock_yf.Ticker.return_value.history.return_value = df

        client = _client(tmp_path)
        resp = client.get("/market-data/ohlcv", params=self._params(exchange="NASDAQ"))
        _cleanup()

        assert resp.status_code == 200
        assert resp.json()["exchange"] == "NASDAQ"
        assert resp.json()["candle_count"] == 1
