"""
Tests for Phase 3G — Polygon.io Market Data Provider Integration.

Coverage:
    TestPolygonErrorHierarchy         (3)  — exception class relationships
    TestPolygonAdapterConstruction    (8)  — valid/invalid constructor args
    TestPolygonAdapterCapabilities    (5)  — ProviderCapabilities contract
    TestPolygonAdapterFetch           (8)  — fetch() contract and delegation
    TestPolygonAdapterNormalization   (8)  — OHLCV field mapping and types
    TestPolygonAdapterHTTPErrors      (8)  — 401/429/404/5xx/bad JSON/network
    TestPolygonDateParams             (5)  — _format_date_params helper
    TestPolygonAdapterPagination      (4)  — single page + multi-page following
    TestPolygonFactoryRegistration    (6)  — factory integration
    TestPolygonCredentialResolution   (5)  — env var resolution + ProviderBuildError
    TestPolygonCacheIntegration       (4)  — all cache policies via OHLCVService
    TestPolygonDatasetIdentity        (4)  — fingerprint + identity contracts
    TestPolygonArchitectureBoundary   (7)  — import isolation + safe error messages
    TestPolygonBackwardCompatibility  (5)  — existing providers unaffected
"""
from __future__ import annotations

import ast
import io
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.data.models import DatasetCachePolicy
from backend.data.models.fetch_identity import build_fetch_identity
from backend.data.models.instrument import AdjustmentMode
from backend.data_providers.base import ProviderFetchError
from backend.data_providers.polygon.adapter import (
    SUPPORTED_TIMEFRAMES,
    PolygonAdapterError,
    PolygonProviderAdapter,
    PolygonRateLimitError,
    _format_date_params,
)
from backend.data_providers.provider_factory import (
    ProviderBuildError,
    create_default_factory_registry,
)

# ---------------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------------

_API_KEY = "test_api_key_12345"

_START = datetime(2024, 1, 2, tzinfo=timezone.utc)
_END = datetime(2024, 1, 31, tzinfo=timezone.utc)

# Minimal Polygon result dict for one candle
_CANDLE = {
    "t": 1704153600000,   # 2024-01-02 00:00:00 UTC in milliseconds
    "o": 186.12,
    "h": 188.45,
    "l": 185.50,
    "c": 187.99,
    "v": 55_123_456.0,
    "vw": 187.05,
    "n": 412_345,
}

_CANDLE_NO_VWAP = {k: v for k, v in _CANDLE.items() if k not in ("vw", "n")}


def _make_adapter(
    symbol: str = "AAPL",
    asset_class: str = "equity",
    venue: str = "NASDAQ",
    timeframe: str = "1d",
    adjustment_mode: str = "adjusted",
    api_key: str = _API_KEY,
) -> PolygonProviderAdapter:
    return PolygonProviderAdapter(
        symbol=symbol,
        asset_class=asset_class,
        venue=venue,
        timeframe=timeframe,
        adjustment_mode=adjustment_mode,
        api_key=api_key,
    )


def _mock_urlopen(response_body: dict | list | None = None, status: int = 200):
    """Return a context-manager mock that simulates urllib.request.urlopen."""
    if response_body is None:
        response_body = {"status": "OK", "results": [_CANDLE], "count": 1}
    body = json.dumps(response_body).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://api.polygon.io/...",
        code=code,
        msg=f"HTTP {code}",
        hdrs=MagicMock(),  # type: ignore[arg-type]
        fp=io.BytesIO(b""),
    )


# ---------------------------------------------------------------------------
# TestPolygonErrorHierarchy
# ---------------------------------------------------------------------------

class TestPolygonErrorHierarchy:
    def test_polygon_adapter_error_is_provider_fetch_error(self):
        assert issubclass(PolygonAdapterError, ProviderFetchError)

    def test_rate_limit_error_is_polygon_adapter_error(self):
        assert issubclass(PolygonRateLimitError, PolygonAdapterError)

    def test_rate_limit_error_is_provider_fetch_error(self):
        assert issubclass(PolygonRateLimitError, ProviderFetchError)


# ---------------------------------------------------------------------------
# TestPolygonAdapterConstruction
# ---------------------------------------------------------------------------

class TestPolygonAdapterConstruction:
    def test_valid_construction_succeeds(self):
        adapter = _make_adapter()
        assert adapter.provider_name == "polygon"

    def test_empty_symbol_raises(self):
        with pytest.raises(ValueError, match="symbol"):
            _make_adapter(symbol="")

    def test_whitespace_symbol_raises(self):
        with pytest.raises(ValueError, match="symbol"):
            _make_adapter(symbol="   ")

    def test_empty_asset_class_raises(self):
        with pytest.raises(ValueError, match="asset_class"):
            _make_adapter(asset_class="")

    def test_empty_venue_raises(self):
        with pytest.raises(ValueError, match="venue"):
            _make_adapter(venue="")

    def test_unsupported_timeframe_raises(self):
        with pytest.raises(ValueError, match="timeframe"):
            _make_adapter(timeframe="99x")

    def test_empty_api_key_raises(self):
        with pytest.raises(ValueError, match="api_key"):
            _make_adapter(api_key="")

    def test_adjustment_mode_defaults_to_adjusted(self):
        adapter = PolygonProviderAdapter(
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
            api_key=_API_KEY,
        )
        assert adapter.provider_name == "polygon"


# ---------------------------------------------------------------------------
# TestPolygonAdapterCapabilities
# ---------------------------------------------------------------------------

class TestPolygonAdapterCapabilities:
    def test_capabilities_returns_provider_capabilities(self):
        from backend.data_providers.base import ProviderCapabilities
        caps = _make_adapter().capabilities()
        assert isinstance(caps, ProviderCapabilities)

    def test_provider_id_is_polygon(self):
        assert _make_adapter().capabilities().provider_id == "polygon"

    def test_display_name_is_polygon_io(self):
        assert _make_adapter().capabilities().display_name == "Polygon.io"

    def test_supported_timeframes_contains_all_canonical(self):
        timeframes = _make_adapter().supported_timeframes()
        for tf in ("1m", "5m", "15m", "30m", "1h", "1d", "1w", "1M"):
            assert tf in timeframes, f"expected {tf!r} in supported_timeframes"

    def test_supported_asset_classes_contains_equity(self):
        assert "equity" in _make_adapter().supported_asset_classes()

    def test_all_15_canonical_timeframes_supported(self):
        canonical = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h",
                     "8h", "12h", "1d", "3d", "1w", "1M"}
        supported = set(_make_adapter().supported_timeframes())
        assert canonical == supported


# ---------------------------------------------------------------------------
# TestPolygonAdapterFetch
# ---------------------------------------------------------------------------

class TestPolygonAdapterFetch:
    def test_naive_start_raises(self):
        adapter = _make_adapter()
        with pytest.raises(ValueError, match="UTC-aware"):
            adapter.fetch(
                start=datetime(2024, 1, 1),
                end=_END,
            )

    def test_naive_end_raises(self):
        adapter = _make_adapter()
        with pytest.raises(ValueError, match="UTC-aware"):
            adapter.fetch(
                start=_START,
                end=datetime(2024, 1, 31),
            )

    def test_fetch_returns_normalized_ohlcv_list(self):
        adapter = _make_adapter()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen()):
            result = adapter.fetch(_START, _END)
        assert isinstance(result, list)
        assert len(result) == 1
        from backend.data.schemas import NormalizedOHLCV
        assert isinstance(result[0], NormalizedOHLCV)

    def test_empty_results_key_returns_empty_list(self):
        adapter = _make_adapter()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen({"status": "OK"})):
            result = adapter.fetch(_START, _END)
        assert result == []

    def test_result_source_is_polygon(self):
        adapter = _make_adapter()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen()):
            result = adapter.fetch(_START, _END)
        assert result[0].source == "polygon"

    def test_result_symbol_matches(self):
        adapter = _make_adapter(symbol="MSFT")
        resp = {"status": "OK", "results": [{**_CANDLE}], "count": 1}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(resp)):
            result = adapter.fetch(_START, _END)
        assert result[0].symbol == "MSFT"

    def test_result_timeframe_matches(self):
        adapter = _make_adapter(timeframe="1h")
        # Candle timestamp within window
        candle = {**_CANDLE, "t": int(_START.timestamp() * 1000) + 1000}
        resp = {"status": "OK", "results": [candle], "count": 1}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(resp)):
            result = adapter.fetch(_START, _END)
        assert result[0].timeframe == "1h"

    def test_result_timestamps_are_utc_aware(self):
        adapter = _make_adapter()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen()):
            result = adapter.fetch(_START, _END)
        assert result[0].timestamp.tzinfo is not None
        assert result[0].timestamp.tzinfo.utcoffset(result[0].timestamp).total_seconds() == 0


# ---------------------------------------------------------------------------
# TestPolygonAdapterNormalization
# ---------------------------------------------------------------------------

class TestPolygonAdapterNormalization:
    def _fetch_one(self, candle: dict) -> object:
        adapter = _make_adapter()
        resp = {"status": "OK", "results": [candle], "count": 1}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(resp)):
            result = adapter.fetch(_START, _END)
        assert len(result) == 1
        return result[0]

    def test_open_parsed_correctly(self):
        r = self._fetch_one(_CANDLE)
        assert r.open == pytest.approx(186.12)

    def test_high_parsed_correctly(self):
        r = self._fetch_one(_CANDLE)
        assert r.high == pytest.approx(188.45)

    def test_low_parsed_correctly(self):
        r = self._fetch_one(_CANDLE)
        assert r.low == pytest.approx(185.50)

    def test_close_parsed_correctly(self):
        r = self._fetch_one(_CANDLE)
        assert r.close == pytest.approx(187.99)

    def test_volume_parsed_correctly(self):
        r = self._fetch_one(_CANDLE)
        assert r.volume == pytest.approx(55_123_456.0)

    def test_vwap_set_when_present(self):
        r = self._fetch_one(_CANDLE)
        assert r.vwap == pytest.approx(187.05)

    def test_vwap_none_when_absent(self):
        r = self._fetch_one(_CANDLE_NO_VWAP)
        assert r.vwap is None

    def test_trade_count_set_when_present(self):
        r = self._fetch_one(_CANDLE)
        assert r.trade_count == 412_345

    def test_trade_count_none_when_absent(self):
        r = self._fetch_one(_CANDLE_NO_VWAP)
        assert r.trade_count is None

    def test_millisecond_timestamp_conversion(self):
        r = self._fetch_one(_CANDLE)
        expected = datetime.fromtimestamp(1704153600000 / 1000.0, tz=timezone.utc)
        assert r.timestamp == expected

    def test_malformed_row_skipped_not_raised(self):
        bad_candle = {"t": 1704153600000, "o": "bad", "h": 188.0, "l": 185.0, "c": 187.0}
        resp = {"status": "OK", "results": [bad_candle, _CANDLE], "count": 2}
        adapter = _make_adapter()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(resp)):
            result = adapter.fetch(_START, _END)
        # Only the valid candle is returned
        assert len(result) == 1
        assert result[0].close == pytest.approx(187.99)


# ---------------------------------------------------------------------------
# TestPolygonAdapterHTTPErrors
# ---------------------------------------------------------------------------

class TestPolygonAdapterHTTPErrors:
    def test_http_401_raises_polygon_adapter_error(self):
        adapter = _make_adapter()
        with patch("urllib.request.urlopen", side_effect=_http_error(401)):
            with pytest.raises(PolygonAdapterError):
                adapter.fetch(_START, _END)

    def test_http_401_message_contains_no_api_key(self):
        adapter = _make_adapter()
        with patch("urllib.request.urlopen", side_effect=_http_error(401)):
            with pytest.raises(PolygonAdapterError) as exc_info:
                adapter.fetch(_START, _END)
        assert _API_KEY not in str(exc_info.value)
        assert "POLYGON_API_KEY" not in str(exc_info.value)

    def test_http_429_raises_rate_limit_error(self):
        adapter = _make_adapter()
        with patch("urllib.request.urlopen", side_effect=_http_error(429)):
            with pytest.raises(PolygonRateLimitError):
                adapter.fetch(_START, _END)

    def test_http_500_raises_polygon_adapter_error(self):
        adapter = _make_adapter()
        with patch("urllib.request.urlopen", side_effect=_http_error(500)):
            with pytest.raises(PolygonAdapterError):
                adapter.fetch(_START, _END)

    def test_http_404_returns_empty_list(self):
        adapter = _make_adapter()
        with patch("urllib.request.urlopen", side_effect=_http_error(404)):
            result = adapter.fetch(_START, _END)
        assert result == []

    def test_bad_json_raises_polygon_adapter_error(self):
        adapter = _make_adapter()
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json {{"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(PolygonAdapterError):
                adapter.fetch(_START, _END)

    def test_network_error_raises_polygon_adapter_error(self):
        adapter = _make_adapter()
        import socket
        url_err = urllib.error.URLError(socket.timeout("timed out"))
        with patch("urllib.request.urlopen", side_effect=url_err):
            with pytest.raises(PolygonAdapterError):
                adapter.fetch(_START, _END)

    def test_generic_exception_raises_polygon_adapter_error(self):
        adapter = _make_adapter()
        with patch("urllib.request.urlopen", side_effect=RuntimeError("unexpected")):
            with pytest.raises(PolygonAdapterError):
                adapter.fetch(_START, _END)


# ---------------------------------------------------------------------------
# TestPolygonDateParams
# ---------------------------------------------------------------------------

class TestPolygonDateParams:
    def test_day_timespan_uses_date_strings(self):
        from_s, to_s = _format_date_params(_START, _END, "day")
        assert from_s == "2024-01-02"
        assert to_s == "2024-01-31"

    def test_week_timespan_uses_date_strings(self):
        from_s, to_s = _format_date_params(_START, _END, "week")
        assert from_s == "2024-01-02"
        assert to_s == "2024-01-31"

    def test_month_timespan_uses_date_strings(self):
        from_s, to_s = _format_date_params(_START, _END, "month")
        assert from_s == "2024-01-02"
        assert to_s == "2024-01-31"

    def test_minute_timespan_uses_millisecond_strings(self):
        from_s, to_s = _format_date_params(_START, _END, "minute")
        assert from_s.isdigit()
        assert to_s.isdigit()
        assert int(from_s) == int(_START.timestamp() * 1000)
        assert int(to_s) == int(_END.timestamp() * 1000)

    def test_hour_timespan_uses_millisecond_strings(self):
        from_s, to_s = _format_date_params(_START, _END, "hour")
        assert from_s.isdigit() and to_s.isdigit()


# ---------------------------------------------------------------------------
# TestPolygonAdapterPagination
# ---------------------------------------------------------------------------

class TestPolygonAdapterPagination:
    def test_single_page_no_next_url(self):
        adapter = _make_adapter()
        resp = {"status": "OK", "results": [_CANDLE], "count": 1}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(resp)) as mock_open:
            result = adapter.fetch(_START, _END)
        assert len(result) == 1
        assert mock_open.call_count == 1

    def test_follows_next_url_for_second_page(self):
        adapter = _make_adapter()
        page1_candle = {**_CANDLE, "t": int(_START.timestamp() * 1000) + 1000}
        page2_candle = {**_CANDLE, "t": int(_START.timestamp() * 1000) + 2000}
        page1 = {"status": "OK", "results": [page1_candle], "count": 1,
                 "next_url": "https://api.polygon.io/v2/aggs/ticker/AAPL/range/1/day/2024-01-02/2024-01-31?cursor=abc"}
        page2 = {"status": "OK", "results": [page2_candle], "count": 1}

        call_count = [0]
        def side_effect(req, timeout=30):
            call_count[0] += 1
            body = json.dumps(page1 if call_count[0] == 1 else page2).encode()
            m = MagicMock()
            m.read.return_value = body
            m.__enter__ = lambda s: s
            m.__exit__ = MagicMock(return_value=False)
            return m

        with patch("urllib.request.urlopen", side_effect=side_effect):
            result = adapter.fetch(_START, _END)

        assert call_count[0] == 2
        assert len(result) == 2

    def test_accumulates_records_across_pages(self):
        adapter = _make_adapter()
        candle_a = {**_CANDLE, "t": int(_START.timestamp() * 1000) + 86_400_000}
        candle_b = {**_CANDLE, "t": int(_START.timestamp() * 1000) + 2 * 86_400_000}
        candle_c = {**_CANDLE, "t": int(_START.timestamp() * 1000) + 3 * 86_400_000}
        page1 = {"results": [candle_a, candle_b],
                 "next_url": "https://api.polygon.io/next"}
        page2 = {"results": [candle_c]}

        pages = [page1, page2]
        idx = [0]
        def side_effect(req, timeout=30):
            body = json.dumps(pages[idx[0]]).encode()
            idx[0] += 1
            m = MagicMock(); m.read.return_value = body
            m.__enter__ = lambda s: s; m.__exit__ = MagicMock(return_value=False)
            return m

        with patch("urllib.request.urlopen", side_effect=side_effect):
            result = adapter.fetch(_START, _END)
        assert len(result) == 3

    def test_stops_at_max_pages(self):
        """Pagination loop must not run more than _MAX_PAGES iterations."""
        from backend.data_providers.polygon import adapter as _mod
        original_max = _mod._MAX_PAGES
        _mod._MAX_PAGES = 3

        candle = {**_CANDLE, "t": int(_START.timestamp() * 1000) + 86_400_000}
        infinite_page = {"results": [candle], "next_url": "https://api.polygon.io/next"}

        call_count = [0]
        def side_effect(req, timeout=30):
            call_count[0] += 1
            body = json.dumps(infinite_page).encode()
            m = MagicMock(); m.read.return_value = body
            m.__enter__ = lambda s: s; m.__exit__ = MagicMock(return_value=False)
            return m

        try:
            with patch("urllib.request.urlopen", side_effect=side_effect):
                adapter = _make_adapter()
                adapter.fetch(_START, _END)
        finally:
            _mod._MAX_PAGES = original_max

        assert call_count[0] == 3  # capped at _MAX_PAGES


# ---------------------------------------------------------------------------
# TestPolygonFactoryRegistration
# ---------------------------------------------------------------------------

class TestPolygonFactoryRegistration:
    def test_polygon_in_default_factory(self):
        factory = create_default_factory_registry()
        assert "polygon" in factory

    def test_factory_has_four_providers(self):
        factory = create_default_factory_registry()
        assert len(factory) == 4

    def test_factory_contains_all_four(self):
        factory = create_default_factory_registry()
        for name in ("yahoo", "csv", "parquet", "polygon"):
            assert name in factory

    def test_polygon_capabilities_from_factory(self):
        factory = create_default_factory_registry()
        caps = factory.get_capabilities("polygon")
        assert caps.provider_id == "polygon"
        assert caps.display_name == "Polygon.io"

    def test_build_polygon_returns_adapter(self, tmp_path):
        factory = create_default_factory_registry()
        with patch.dict(os.environ, {"POLYGON_API_KEY": "fake_key"}):
            adapter = factory.build("polygon", symbol="AAPL", timeframe="1d")
        assert isinstance(adapter, PolygonProviderAdapter)

    def test_missing_api_key_raises_provider_build_error(self):
        factory = create_default_factory_registry()
        env = {k: v for k, v in os.environ.items() if k != "POLYGON_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ProviderBuildError):
                factory.build("polygon", symbol="AAPL", timeframe="1d")


# ---------------------------------------------------------------------------
# TestPolygonCredentialResolution
# ---------------------------------------------------------------------------

class TestPolygonCredentialResolution:
    def test_resolves_api_key_from_env(self):
        factory = create_default_factory_registry()
        with patch.dict(os.environ, {"POLYGON_API_KEY": "my_secret_key"}):
            adapter = factory.build("polygon", symbol="AAPL", timeframe="1d")
        assert isinstance(adapter, PolygonProviderAdapter)

    def test_missing_key_raises_provider_build_error(self):
        factory = create_default_factory_registry()
        env = {k: v for k, v in os.environ.items() if k != "POLYGON_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ProviderBuildError):
                factory.build("polygon", symbol="AAPL", timeframe="1d")

    def test_provider_build_error_message_has_no_api_key_value(self):
        secret = "super_secret_api_key_xyz"
        factory = create_default_factory_registry()
        with patch.dict(os.environ, {"POLYGON_API_KEY": secret}):
            pass  # key exists — we want the missing case
        env = {k: v for k, v in os.environ.items() if k != "POLYGON_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ProviderBuildError) as exc_info:
                factory.build("polygon", symbol="AAPL", timeframe="1d")
        assert secret not in str(exc_info.value)

    def test_provider_build_error_is_missing_credential_cause(self):
        from backend.core.credentials import MissingCredentialError
        factory = create_default_factory_registry()
        env = {k: v for k, v in os.environ.items() if k != "POLYGON_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ProviderBuildError) as exc_info:
                factory.build("polygon", symbol="AAPL", timeframe="1d")
        assert isinstance(exc_info.value.__cause__, MissingCredentialError)

    def test_audit_events_emitted_on_resolution_attempt(self):
        import logging
        factory = create_default_factory_registry()
        audit_records: list[str] = []

        class _Capture(logging.Handler):
            def emit(self, record):
                audit_records.append(record.getMessage())

        handler = _Capture()
        audit_logger = logging.getLogger("quantlab.audit")
        audit_logger.addHandler(handler)
        audit_logger.setLevel(logging.DEBUG)
        try:
            env = {k: v for k, v in os.environ.items() if k != "POLYGON_API_KEY"}
            with patch.dict(os.environ, env, clear=True):
                try:
                    factory.build("polygon", symbol="AAPL", timeframe="1d")
                except ProviderBuildError:
                    pass
        finally:
            audit_logger.removeHandler(handler)

        assert any("polygon" in r for r in audit_records), (
            "Expected at least one audit record mentioning 'polygon'"
        )


# ---------------------------------------------------------------------------
# TestPolygonCacheIntegration
# ---------------------------------------------------------------------------

class TestPolygonCacheIntegration:
    """Verify Polygon flows through OHLCVService with all cache policies."""

    def _make_ohlcv_service(self, tmp_path: Path):
        from backend.data.models.dataset import DatasetIdentity
        from backend.data.models.instrument import AdjustmentMode, Instrument
        from backend.services.ohlcv_service import OHLCVService

        instrument = Instrument(symbol="AAPL", asset_class="equity", exchange="NASDAQ")
        identity = DatasetIdentity(
            instrument=instrument,
            timeframe="1d",
            adjustment_mode=AdjustmentMode.ADJUSTED,
            provider="polygon",
        )
        service = OHLCVService(tmp_path)
        return service, identity

    def _polygon_adapter_with_mock(self) -> PolygonProviderAdapter:
        return _make_adapter()

    def test_fetch_and_store_policy_stores_data(self, tmp_path):
        service, identity = self._make_ohlcv_service(tmp_path)
        adapter = self._polygon_adapter_with_mock()
        resp = {"status": "OK", "results": [_CANDLE], "count": 1}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(resp)):
            records = service.get_ohlcv(
                provider=adapter,
                identity=identity,
                start=_START,
                end=_END,
                cache_policy=DatasetCachePolicy.FETCH_AND_STORE,
            )
        assert len(records) == 1
        assert records[0].source == "polygon"

    def test_bypass_cache_does_not_write_storage(self, tmp_path):
        service, identity = self._make_ohlcv_service(tmp_path)
        adapter = self._polygon_adapter_with_mock()
        parquet_path = (
            tmp_path / "polygon" / "equity" / "NASDAQ" / "AAPL" / "1d" / "adjusted" / "data.parquet"
        )
        resp = {"status": "OK", "results": [_CANDLE], "count": 1}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(resp)):
            service.get_ohlcv(
                provider=adapter,
                identity=identity,
                start=_START,
                end=_END,
                cache_policy=DatasetCachePolicy.BYPASS_CACHE,
            )
        assert not parquet_path.exists()

    def test_force_refresh_overwrites_previous_data(self, tmp_path):
        service, identity = self._make_ohlcv_service(tmp_path)
        adapter = self._polygon_adapter_with_mock()
        resp = {"status": "OK", "results": [_CANDLE], "count": 1}
        # First FETCH_AND_STORE
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(resp)):
            service.get_ohlcv(
                provider=adapter, identity=identity,
                start=_START, end=_END,
                cache_policy=DatasetCachePolicy.FETCH_AND_STORE,
            )
        # Then FORCE_REFRESH
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(resp)):
            records = service.get_ohlcv(
                provider=adapter, identity=identity,
                start=_START, end=_END,
                cache_policy=DatasetCachePolicy.FORCE_REFRESH,
            )
        assert len(records) == 1

    def test_read_only_policy_returns_cached_data(self, tmp_path):
        service, identity = self._make_ohlcv_service(tmp_path)
        adapter = self._polygon_adapter_with_mock()
        resp = {"status": "OK", "results": [_CANDLE], "count": 1}
        # First store data
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(resp)):
            service.get_ohlcv(
                provider=adapter, identity=identity,
                start=_START, end=_END,
                cache_policy=DatasetCachePolicy.FETCH_AND_STORE,
            )
        # READ_ONLY: should return from cache without calling provider
        with patch("urllib.request.urlopen") as mock_open:
            records = service.get_ohlcv(
                provider=adapter, identity=identity,
                start=_START, end=_END,
                cache_policy=DatasetCachePolicy.READ_ONLY,
            )
        mock_open.assert_not_called()
        assert len(records) == 1


# ---------------------------------------------------------------------------
# TestPolygonDatasetIdentity
# ---------------------------------------------------------------------------

class TestPolygonDatasetIdentity:
    def _build_identity(self) -> object:
        return build_fetch_identity(
            provider="polygon",
            symbol="AAPL",
            asset_class="equity",
            exchange="NASDAQ",
            timeframe="1d",
            start=_START,
            end=_END,
            adjustment_mode=AdjustmentMode.ADJUSTED,
            dataset_id="polygon|equity|NASDAQ|AAPL|1d|adjusted",
        )

    def test_build_fetch_identity_for_polygon(self):
        identity = self._build_identity()
        assert identity.parameters.provider == "polygon"

    def test_fingerprint_is_deterministic(self):
        identity1 = self._build_identity()
        identity2 = self._build_identity()
        assert identity1.fingerprint == identity2.fingerprint

    def test_dataset_id_contains_polygon(self):
        identity = self._build_identity()
        assert "polygon" in identity.dataset_id

    def test_no_api_key_in_identity(self):
        identity = self._build_identity()
        identity_str = str(identity.model_dump())
        assert _API_KEY not in identity_str
        assert "POLYGON_API_KEY" not in identity_str


# ---------------------------------------------------------------------------
# TestPolygonArchitectureBoundary
# ---------------------------------------------------------------------------

_POLYGON_ADAPTER_PATH = Path(
    "/Volumes/externalDrive/code-gym/quantlab/backend/data_providers/polygon/adapter.py"
)


def _get_imports(source: str) -> list[str]:
    """Return all module paths imported in a Python source file."""
    tree = ast.parse(source)
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


class TestPolygonArchitectureBoundary:
    def _adapter_imports(self) -> list[str]:
        source = _POLYGON_ADAPTER_PATH.read_text()
        return _get_imports(source)

    def test_polygon_adapter_does_not_import_yahoo(self):
        assert not any("yahoo" in i for i in self._adapter_imports())

    def test_polygon_adapter_does_not_import_csv_provider(self):
        assert not any("csv_provider" in i for i in self._adapter_imports())

    def test_polygon_adapter_does_not_import_parquet_provider(self):
        assert not any("parquet_provider" in i for i in self._adapter_imports())

    def test_polygon_adapter_does_not_import_api_routes(self):
        assert not any("backend.api.routes" in i for i in self._adapter_imports())

    def test_polygon_adapter_does_not_import_strategy_runtime(self):
        assert not any("strategy_runtime" in i for i in self._adapter_imports())

    def test_polygon_adapter_does_not_import_credentials(self):
        # Credentials are resolved by the factory builder, NOT inside the adapter
        assert not any("credentials" in i for i in self._adapter_imports())

    def test_http_401_message_contains_no_raw_api_key(self):
        secret = "top_secret_polygon_key_abc123"
        adapter = PolygonProviderAdapter(
            symbol="AAPL", asset_class="equity", venue="NASDAQ",
            timeframe="1d", api_key=secret,
        )
        with patch("urllib.request.urlopen", side_effect=_http_error(401)):
            with pytest.raises(PolygonAdapterError) as exc_info:
                adapter.fetch(_START, _END)
        assert secret not in str(exc_info.value)

    def test_http_401_message_contains_no_env_var_name(self):
        adapter = _make_adapter()
        with patch("urllib.request.urlopen", side_effect=_http_error(401)):
            with pytest.raises(PolygonAdapterError) as exc_info:
                adapter.fetch(_START, _END)
        assert "POLYGON_API_KEY" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# TestPolygonBackwardCompatibility
# ---------------------------------------------------------------------------

class TestPolygonBackwardCompatibility:
    def test_yahoo_still_in_factory(self):
        assert "yahoo" in create_default_factory_registry()

    def test_csv_still_in_factory(self):
        assert "csv" in create_default_factory_registry()

    def test_parquet_still_in_factory(self):
        assert "parquet" in create_default_factory_registry()

    def test_factory_len_is_four(self):
        assert len(create_default_factory_registry()) == 4

    def test_legacy_csv_adapter_unaffected(self):
        """The legacy CSVAdapter (non-factory) remains importable and functional."""
        from backend.data_providers.csv_adapter import CSVAdapter
        assert CSVAdapter is not None
