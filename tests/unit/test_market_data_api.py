"""
Tests for GET /market-data/ohlcv.

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
    return TestClient(app)


def _cleanup() -> None:
    app.dependency_overrides.pop(get_storage_path, None)


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
    def test_default_asset_class_and_exchange(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.Ticker.return_value.history.return_value = pd.DataFrame()

        client = _client(tmp_path)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo", "symbol": "AAPL",
            "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
            # asset_class and exchange use defaults
        })
        _cleanup()

        assert resp.status_code == 200
        data = resp.json()
        assert data["asset_class"] == "equity"
        assert data["exchange"] == "NASDAQ"
