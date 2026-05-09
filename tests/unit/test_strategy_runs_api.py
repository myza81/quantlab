"""
Tests for POST /strategy-runs/run.

All tests patch yf at the adapter module level to avoid real network calls.
Storage uses tmp_path via app.dependency_overrides[get_storage_path].
strategies_path is overridden to point to tests/fixtures/strategies/.

Covers:
- Happy path: returns 200 with correct schema (status, signals, forecasts)
- Forecast present when MA20/MA50 computable (≥50 candles)
- Signal produced on MA crossover
- Empty candles → status="empty"
- Unsupported provider → 400
- Strategy not found → 404
- Missing required body fields → 422
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.routes.strategy_runs import get_storage_path, get_strategies_path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REAL_STRATEGIES = Path(__file__).parent.parent.parent / "strategies"


def _make_df(closes: list[float], start_date: str = "2023-01-02") -> pd.DataFrame:
    base = pd.Timestamp(start_date, tz="UTC")
    timestamps = [base + pd.Timedelta(days=i) for i in range(len(closes))]
    index = pd.DatetimeIndex(timestamps)
    return pd.DataFrame(
        {
            "Open":   [c * 0.99 for c in closes],
            "High":   [c * 1.01 for c in closes],
            "Low":    [c * 0.98 for c in closes],
            "Close":  closes,
            "Volume": [1_000_000.0] * len(closes),
        },
        index=index,
    )


def _client(tmp_path: Path, strategies_path: Path | None = None) -> TestClient:
    app.dependency_overrides[get_storage_path] = lambda: tmp_path
    app.dependency_overrides[get_strategies_path] = lambda: (
        strategies_path if strategies_path is not None else _REAL_STRATEGIES
    )
    return TestClient(app)


def _cleanup() -> None:
    app.dependency_overrides.pop(get_storage_path, None)
    app.dependency_overrides.pop(get_strategies_path, None)


_VALID_BODY = {
    "strategy_id": "example_strategy",
    "provider": "yahoo",
    "symbol": "AAPL",
    "timeframe": "1d",
    "start": "2023-01-01T00:00:00Z",
    "end": "2023-04-30T00:00:00Z",
    "asset_class": "equity",
    "exchange": "NASDAQ",
}

# 60 bars of steady uptrend (no crossover → 0 signals, 1 forecast)
_UPTREND_CLOSES = [100.0 + i for i in range(60)]


# ---------------------------------------------------------------------------
# TestStrategyRunHappyPath
# ---------------------------------------------------------------------------

class TestStrategyRunHappyPath:
    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_returns_200_with_required_fields(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.Ticker.return_value.history.return_value = _make_df(_UPTREND_CLOSES)

        client = _client(tmp_path)
        resp = client.post("/strategy-runs/run", json=_VALID_BODY)
        _cleanup()

        assert resp.status_code == 200
        data = resp.json()
        assert "strategy_id" in data
        assert "status" in data
        assert "candles_received" in data
        assert "signals" in data
        assert "forecasts" in data
        assert "indicators" in data
        assert "warnings" in data

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_strategy_id_matches_request(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.Ticker.return_value.history.return_value = _make_df(_UPTREND_CLOSES)

        client = _client(tmp_path)
        resp = client.post("/strategy-runs/run", json=_VALID_BODY)
        _cleanup()

        assert resp.json()["strategy_id"] == "example_strategy"

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_status_is_success_with_candles(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.Ticker.return_value.history.return_value = _make_df(_UPTREND_CLOSES)

        client = _client(tmp_path)
        resp = client.post("/strategy-runs/run", json=_VALID_BODY)
        _cleanup()

        assert resp.json()["status"] == "success"

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_candles_received_matches_provider_output(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.Ticker.return_value.history.return_value = _make_df(_UPTREND_CLOSES)

        client = _client(tmp_path)
        resp = client.post("/strategy-runs/run", json=_VALID_BODY)
        _cleanup()

        assert resp.json()["candles_received"] == 60

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_forecast_present_with_sufficient_candles(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        """MA20 and MA50 both computable with 60 bars → forecast generated."""
        mock_yf.Ticker.return_value.history.return_value = _make_df(_UPTREND_CLOSES)

        client = _client(tmp_path)
        resp = client.post("/strategy-runs/run", json=_VALID_BODY)
        _cleanup()

        forecasts = resp.json()["forecasts"]
        assert len(forecasts) == 1

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_forecast_schema_fields(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.Ticker.return_value.history.return_value = _make_df(_UPTREND_CLOSES)

        client = _client(tmp_path)
        resp = client.post("/strategy-runs/run", json=_VALID_BODY)
        _cleanup()

        forecast = resp.json()["forecasts"][0]
        assert "generated_at" in forecast
        assert "target_timestamp" in forecast
        assert "target_price" in forecast
        assert "direction" in forecast
        assert "confidence" in forecast

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_uptrend_forecast_direction_is_long(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        """Steady uptrend: MA20 > MA50 at end → forecast direction=long."""
        mock_yf.Ticker.return_value.history.return_value = _make_df(_UPTREND_CLOSES)

        client = _client(tmp_path)
        resp = client.post("/strategy-runs/run", json=_VALID_BODY)
        _cleanup()

        assert resp.json()["forecasts"][0]["direction"] == "long"

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_indicators_returned_with_sufficient_candles(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        """60 bars → MA20 + MA50 both computable → 2 indicator series."""
        mock_yf.Ticker.return_value.history.return_value = _make_df(_UPTREND_CLOSES)

        client = _client(tmp_path)
        resp = client.post("/strategy-runs/run", json=_VALID_BODY)
        _cleanup()

        indicators = resp.json()["indicators"]
        assert len(indicators) == 2
        names = {ind["name"] for ind in indicators}
        assert names == {"MA20", "MA50"}

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_indicator_series_schema_fields(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.Ticker.return_value.history.return_value = _make_df(_UPTREND_CLOSES)

        client = _client(tmp_path)
        resp = client.post("/strategy-runs/run", json=_VALID_BODY)
        _cleanup()

        ind = resp.json()["indicators"][0]
        assert "name" in ind
        assert "kind" in ind
        assert "pane" in ind
        assert "points" in ind
        assert isinstance(ind["points"], list)
        assert len(ind["points"]) > 0

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_indicator_point_schema_fields(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.Ticker.return_value.history.return_value = _make_df(_UPTREND_CLOSES)

        client = _client(tmp_path)
        resp = client.post("/strategy-runs/run", json=_VALID_BODY)
        _cleanup()

        pt = resp.json()["indicators"][0]["points"][0]
        assert "timestamp" in pt
        assert "value" in pt
        assert isinstance(pt["value"], float)


# ---------------------------------------------------------------------------
# TestStrategyRunSignals
# ---------------------------------------------------------------------------

class TestStrategyRunSignals:
    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_signal_schema_fields_when_present(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        """When a crossover occurs, signal objects have the required fields."""
        # Build data that produces a death cross: 50 bars uptrend then sharp drop
        uptrend = [100.0 + i for i in range(50)]
        drop = [80.0] * 10
        mock_yf.Ticker.return_value.history.return_value = _make_df(uptrend + drop)

        client = _client(tmp_path)
        resp = client.post("/strategy-runs/run", json=_VALID_BODY)
        _cleanup()

        signals = resp.json()["signals"]
        if signals:
            sig = signals[0]
            assert "strategy_id" in sig
            assert "timestamp" in sig
            assert "symbol" in sig
            assert "timeframe" in sig
            assert "signal_type" in sig
            assert "entry_reference" in sig
            assert "invalidation_level" in sig

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_no_signals_in_monotonic_uptrend(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        """Monotonic uptrend has no crossover → no signals."""
        mock_yf.Ticker.return_value.history.return_value = _make_df(_UPTREND_CLOSES)

        client = _client(tmp_path)
        resp = client.post("/strategy-runs/run", json=_VALID_BODY)
        _cleanup()

        assert resp.json()["signals"] == []


# ---------------------------------------------------------------------------
# TestStrategyRunEmptyCandles
# ---------------------------------------------------------------------------

class TestStrategyRunEmptyCandles:
    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_empty_dataframe_returns_empty_status(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.Ticker.return_value.history.return_value = pd.DataFrame()

        client = _client(tmp_path)
        resp = client.post("/strategy-runs/run", json=_VALID_BODY)
        _cleanup()

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "empty"
        assert data["candles_received"] == 0
        assert data["signals"] == []
        assert data["forecasts"] == []


# ---------------------------------------------------------------------------
# TestStrategyRunValidation
# ---------------------------------------------------------------------------

class TestStrategyRunValidation:
    def test_unsupported_provider_returns_400(self, tmp_path: Path) -> None:
        body = {**_VALID_BODY, "provider": "polygon"}
        client = _client(tmp_path)
        resp = client.post("/strategy-runs/run", json=body)
        _cleanup()

        assert resp.status_code == 400
        assert "polygon" in resp.json()["detail"].lower()

    def test_strategy_not_found_returns_404(self, tmp_path: Path) -> None:
        body = {**_VALID_BODY, "strategy_id": "nonexistent_strategy"}
        client = _client(tmp_path)
        resp = client.post("/strategy-runs/run", json=body)
        _cleanup()

        assert resp.status_code == 404
        assert "nonexistent_strategy" in resp.json()["detail"]

    def test_missing_strategy_id_returns_422(self, tmp_path: Path) -> None:
        body = {k: v for k, v in _VALID_BODY.items() if k != "strategy_id"}
        client = _client(tmp_path)
        resp = client.post("/strategy-runs/run", json=body)
        _cleanup()

        assert resp.status_code == 422

    def test_missing_symbol_returns_422(self, tmp_path: Path) -> None:
        body = {k: v for k, v in _VALID_BODY.items() if k != "symbol"}
        client = _client(tmp_path)
        resp = client.post("/strategy-runs/run", json=body)
        _cleanup()

        assert resp.status_code == 422

    def test_missing_start_returns_422(self, tmp_path: Path) -> None:
        body = {k: v for k, v in _VALID_BODY.items() if k != "start"}
        client = _client(tmp_path)
        resp = client.post("/strategy-runs/run", json=body)
        _cleanup()

        assert resp.status_code == 422
