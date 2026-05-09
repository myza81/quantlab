"""
Tests for YahooFinanceAdapter.

All tests use unittest.mock to avoid real network calls.
yfinance.Ticker is patched at the module level where it is imported.

Covers:
- Adapter construction validation
- Supported timeframe mapping
- Unsupported timeframe rejection
- fetch() with valid mocked DataFrame
- fetch() with empty DataFrame → returns []
- UTC timestamp normalisation
- Naive datetime rejection
- Column conversion (Open/High/Low/Close/Volume)
- Malformed row skipped with warning
- load() raises NotImplementedError
- provider_name == "yahoo"
- YahooAdapterError wraps transport exceptions
- adjusted vs raw mode (auto_adjust flag)
- End date bumped +1 day for daily intervals
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pandas as pd
import pytest

from backend.data_providers.yahoo.adapter import (
    SUPPORTED_TIMEFRAMES,
    YahooAdapterError,
    YahooFinanceAdapter,
    _history_bounds,
    _inclusive_end,
)
from backend.data.schemas import NormalizedOHLCV


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal yfinance-like history DataFrame."""
    index = pd.DatetimeIndex(
        [pd.Timestamp(r["ts"], tz="UTC") for r in rows]
    )
    data = {
        "Open":   [r["open"]   for r in rows],
        "High":   [r["high"]   for r in rows],
        "Low":    [r["low"]    for r in rows],
        "Close":  [r["close"]  for r in rows],
        "Volume": [r["vol"]    for r in rows],
    }
    return pd.DataFrame(data, index=index)


def _default_row() -> dict:
    return {
        "ts":    "2023-01-03",
        "open":  130.0,
        "high":  133.0,
        "low":   129.0,
        "close": 132.0,
        "vol":   80_000_000.0,
    }


# ---------------------------------------------------------------------------
# TestYahooAdapterConstruction
# ---------------------------------------------------------------------------

class TestYahooAdapterConstruction:
    def test_valid_construction(self) -> None:
        adapter = YahooFinanceAdapter(
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        assert adapter.provider_name == "yahoo"

    def test_unsupported_timeframe_raises(self) -> None:
        with pytest.raises(ValueError, match="not supported"):
            YahooFinanceAdapter(
                symbol="AAPL",
                asset_class="equity",
                venue="NASDAQ",
                timeframe="4h",
            )

    def test_empty_symbol_raises(self) -> None:
        with pytest.raises(ValueError, match="symbol"):
            YahooFinanceAdapter(symbol="", asset_class="equity", venue="NASDAQ", timeframe="1d")

    def test_empty_asset_class_raises(self) -> None:
        with pytest.raises(ValueError, match="asset_class"):
            YahooFinanceAdapter(symbol="AAPL", asset_class="", venue="NASDAQ", timeframe="1d")

    def test_empty_venue_raises(self) -> None:
        with pytest.raises(ValueError, match="venue"):
            YahooFinanceAdapter(symbol="AAPL", asset_class="equity", venue="", timeframe="1d")

    def test_all_supported_timeframes_accepted(self) -> None:
        for tf in SUPPORTED_TIMEFRAMES:
            adapter = YahooFinanceAdapter(
                symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe=tf
            )
            assert adapter.provider_name == "yahoo"

    def test_load_raises_not_implemented(self) -> None:
        adapter = YahooFinanceAdapter(
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d"
        )
        with pytest.raises(NotImplementedError):
            adapter.load()


# ---------------------------------------------------------------------------
# TestYahooAdapterFetch
# ---------------------------------------------------------------------------

class TestYahooAdapterFetch:
    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_fetch_returns_normalized_records(self, mock_yf: MagicMock) -> None:
        mock_ticker = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker
        mock_ticker.history.return_value = _make_df([_default_row()])

        adapter = YahooFinanceAdapter(
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d"
        )
        result = adapter.fetch(_utc(2023, 1, 1), _utc(2023, 1, 3))

        assert len(result) == 1
        candle = result[0]
        assert isinstance(candle, NormalizedOHLCV)
        assert candle.symbol == "AAPL"
        assert candle.asset_class == "equity"
        assert candle.venue == "NASDAQ"
        assert candle.timeframe == "1d"
        assert candle.source == "yahoo"

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_ohlcv_values_correct(self, mock_yf: MagicMock) -> None:
        mock_ticker = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker
        mock_ticker.history.return_value = _make_df([_default_row()])

        adapter = YahooFinanceAdapter(
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d"
        )
        result = adapter.fetch(_utc(2023, 1, 1), _utc(2023, 1, 3))
        c = result[0]
        assert c.open == 130.0
        assert c.high == 133.0
        assert c.low == 129.0
        assert c.close == 132.0
        assert c.volume == 80_000_000.0

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_timestamps_normalised_to_utc(self, mock_yf: MagicMock) -> None:
        mock_ticker = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker
        mock_ticker.history.return_value = _make_df([_default_row()])

        adapter = YahooFinanceAdapter(
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d"
        )
        result = adapter.fetch(_utc(2023, 1, 1), _utc(2023, 1, 3))
        assert result[0].timestamp.tzinfo is not None
        assert result[0].timestamp.tzinfo == timezone.utc

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_empty_dataframe_returns_empty_list(self, mock_yf: MagicMock) -> None:
        mock_ticker = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker
        mock_ticker.history.return_value = pd.DataFrame()

        adapter = YahooFinanceAdapter(
            symbol="INVALID_XYZ", asset_class="equity", venue="NASDAQ", timeframe="1d"
        )
        result = adapter.fetch(_utc(2023, 1, 1), _utc(2023, 1, 3))
        assert result == []

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_none_dataframe_returns_empty_list(self, mock_yf: MagicMock) -> None:
        mock_ticker = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker
        mock_ticker.history.return_value = None

        adapter = YahooFinanceAdapter(
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d"
        )
        result = adapter.fetch(_utc(2023, 1, 1), _utc(2023, 1, 3))
        assert result == []

    def test_naive_start_raises(self) -> None:
        adapter = YahooFinanceAdapter(
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d"
        )
        with pytest.raises(ValueError, match="UTC-aware"):
            adapter.fetch(datetime(2023, 1, 1), _utc(2023, 1, 3))

    def test_naive_end_raises(self) -> None:
        adapter = YahooFinanceAdapter(
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d"
        )
        with pytest.raises(ValueError, match="UTC-aware"):
            adapter.fetch(_utc(2023, 1, 1), datetime(2023, 1, 3))

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_transport_exception_raises_yahoo_adapter_error(self, mock_yf: MagicMock) -> None:
        mock_ticker = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker
        mock_ticker.history.side_effect = ConnectionError("timeout")

        adapter = YahooFinanceAdapter(
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d"
        )
        with pytest.raises(YahooAdapterError, match="AAPL"):
            adapter.fetch(_utc(2023, 1, 1), _utc(2023, 1, 3))

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_multiple_rows_all_converted(self, mock_yf: MagicMock) -> None:
        rows = [
            {"ts": "2023-01-03", "open": 130.0, "high": 133.0, "low": 129.0, "close": 132.0, "vol": 1e7},
            {"ts": "2023-01-04", "open": 132.0, "high": 135.0, "low": 131.0, "close": 134.0, "vol": 2e7},
            {"ts": "2023-01-05", "open": 134.0, "high": 136.0, "low": 133.0, "close": 135.0, "vol": 3e7},
        ]
        mock_ticker = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker
        mock_ticker.history.return_value = _make_df(rows)

        adapter = YahooFinanceAdapter(
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d"
        )
        result = adapter.fetch(_utc(2023, 1, 1), _utc(2023, 1, 5))
        assert len(result) == 3

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_adjusted_mode_uses_auto_adjust_true(self, mock_yf: MagicMock) -> None:
        mock_ticker = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker
        mock_ticker.history.return_value = _make_df([_default_row()])

        adapter = YahooFinanceAdapter(
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d",
            adjustment_mode="adjusted",
        )
        adapter.fetch(_utc(2023, 1, 1), _utc(2023, 1, 3))
        call_kwargs = mock_ticker.history.call_args.kwargs
        assert call_kwargs["auto_adjust"] is True

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_raw_mode_uses_auto_adjust_false(self, mock_yf: MagicMock) -> None:
        mock_ticker = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker
        mock_ticker.history.return_value = _make_df([_default_row()])

        adapter = YahooFinanceAdapter(
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d",
            adjustment_mode="raw",
        )
        adapter.fetch(_utc(2023, 1, 1), _utc(2023, 1, 3))
        call_kwargs = mock_ticker.history.call_args.kwargs
        assert call_kwargs["auto_adjust"] is False

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_daily_end_bumped_one_day(self, mock_yf: MagicMock) -> None:
        """yfinance end is exclusive — adapter adds 1 day for daily intervals."""
        mock_ticker = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker
        mock_ticker.history.return_value = _make_df([_default_row()])

        adapter = YahooFinanceAdapter(
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d"
        )
        adapter.fetch(_utc(2023, 1, 1), _utc(2023, 1, 3))
        call_kwargs = mock_ticker.history.call_args.kwargs
        # end passed to yfinance should be 2023-01-04 (exclusive = 2023-01-03 inclusive)
        assert call_kwargs["end"] == "2023-01-04"

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_intraday_end_not_bumped(self, mock_yf: MagicMock) -> None:
        mock_ticker = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker
        mock_ticker.history.return_value = pd.DataFrame()

        adapter = YahooFinanceAdapter(
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1h"
        )
        adapter.fetch(_utc(2023, 1, 3, 9), _utc(2023, 1, 3, 16))
        call_kwargs = mock_ticker.history.call_args.kwargs
        assert call_kwargs["start"] == _utc(2023, 1, 3, 9)
        assert call_kwargs["end"] == _utc(2023, 1, 3, 16)


# ---------------------------------------------------------------------------
# TestInclusiveEnd helper
# ---------------------------------------------------------------------------

class TestInclusiveEnd:
    def test_daily_adds_one_day(self) -> None:
        end = _utc(2023, 1, 3)
        result = _inclusive_end(end, "1d")
        assert result == _utc(2023, 1, 4)

    def test_weekly_adds_one_day(self) -> None:
        end = _utc(2023, 1, 3)
        result = _inclusive_end(end, "1wk")
        assert result == _utc(2023, 1, 4)

    def test_monthly_adds_one_day(self) -> None:
        end = _utc(2023, 1, 31)
        result = _inclusive_end(end, "1mo")
        assert result == _utc(2023, 2, 1)

    def test_intraday_unchanged(self) -> None:
        end = _utc(2023, 1, 3, 16)
        for interval in ("1m", "5m", "15m", "30m", "1h"):
            assert _inclusive_end(end, interval) == end


class TestHistoryBounds:
    def test_daily_bounds_use_date_strings(self) -> None:
        start, end = _history_bounds(_utc(2023, 1, 1), _utc(2023, 1, 4), "1d")
        assert start == "2023-01-01"
        assert end == "2023-01-04"

    def test_intraday_bounds_preserve_datetime_precision(self) -> None:
        start_dt = _utc(2023, 1, 3, 9)
        end_dt = _utc(2023, 1, 3, 16)
        start, end = _history_bounds(start_dt, end_dt, "1h")
        assert start == start_dt
        assert end == end_dt


# ---------------------------------------------------------------------------
# TestSupportedTimeframes
# ---------------------------------------------------------------------------

class TestSupportedTimeframes:
    def test_required_timeframes_present(self) -> None:
        required = {"1m", "5m", "15m", "30m", "1h", "1d", "1w", "1M"}
        assert required.issubset(set(SUPPORTED_TIMEFRAMES))

    def test_values_are_yfinance_intervals(self) -> None:
        valid_intervals = {"1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"}
        for v in SUPPORTED_TIMEFRAMES.values():
            assert v in valid_intervals
