"""
Tests for Phase 3B — Dataset Fetch Identity & Provider Traceability.

Covers:
  - DatasetFetchParameters: frozen, field validation, UTC enforcement
  - compute_fetch_fingerprint: determinism, sensitivity, canonical format
  - DatasetFetchIdentity: fields, frozen, schema version
  - build_fetch_identity: convenience builder round-trip
  - DatasetFetchMetadataResponse: schema fields, backward compat (None default)
  - MarketDataOHLCVResponse.fetch_metadata: integration with existing response
  - market_data_service integration: fetch_metadata present in API response
  - Architecture boundary: no yahoo import in fetch_identity or market_data_service
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.routes.market_data import get_provider_factory, get_storage_path
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.api.schemas.market_data import (
    DatasetFetchMetadataResponse,
    MarketDataOHLCVResponse,
)
from backend.data.models.fetch_identity import (
    FETCH_IDENTITY_SCHEMA_VERSION,
    DatasetFetchIdentity,
    DatasetFetchParameters,
    build_fetch_identity,
    compute_fetch_fingerprint,
)
from backend.data.models.instrument import AdjustmentMode


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_UTC = timezone.utc

_START = datetime(2023, 1, 1, tzinfo=_UTC)
_END = datetime(2023, 6, 30, tzinfo=_UTC)

_BASE_PARAMS = dict(
    provider="yahoo",
    symbol="AAPL",
    asset_class="equity",
    exchange="NASDAQ",
    timeframe="1d",
    start=_START,
    end=_END,
    adjustment_mode=AdjustmentMode.ADJUSTED,
)


def _make_params(**overrides: object) -> DatasetFetchParameters:
    return DatasetFetchParameters(**{**_BASE_PARAMS, **overrides})


# ---------------------------------------------------------------------------
# TestDatasetFetchParameters
# ---------------------------------------------------------------------------

class TestDatasetFetchParameters:
    def test_frozen(self) -> None:
        p = _make_params()
        with pytest.raises(Exception):
            p.provider = "polygon"  # type: ignore[misc]

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(Exception):
            DatasetFetchParameters(**_BASE_PARAMS, unknown_field="oops")  # type: ignore[arg-type]

    def test_fields_stored_correctly(self) -> None:
        p = _make_params()
        assert p.provider == "yahoo"
        assert p.symbol == "AAPL"
        assert p.asset_class == "equity"
        assert p.exchange == "NASDAQ"
        assert p.timeframe == "1d"
        assert p.start == _START
        assert p.end == _END
        assert p.adjustment_mode == AdjustmentMode.ADJUSTED

    def test_empty_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            _make_params(provider="")

    def test_whitespace_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            _make_params(provider="   ")

    def test_empty_symbol_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            _make_params(symbol="")

    def test_empty_asset_class_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            _make_params(asset_class="")

    def test_empty_exchange_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            _make_params(exchange="")

    def test_empty_timeframe_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            _make_params(timeframe="")

    def test_naive_start_raises(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _make_params(start=datetime(2023, 1, 1))

    def test_naive_end_raises(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _make_params(end=datetime(2023, 6, 30))

    def test_utc_aware_datetimes_accepted(self) -> None:
        p = _make_params(
            start=datetime(2023, 1, 1, tzinfo=_UTC),
            end=datetime(2023, 6, 30, tzinfo=_UTC),
        )
        assert p.start.tzinfo is not None
        assert p.end.tzinfo is not None

    def test_non_utc_aware_datetime_accepted(self) -> None:
        import datetime as dt
        tz_east8 = dt.timezone(dt.timedelta(hours=8))
        p = _make_params(start=datetime(2023, 1, 1, tzinfo=tz_east8))
        assert p.start.tzinfo is not None


# ---------------------------------------------------------------------------
# TestComputeFetchFingerprint
# ---------------------------------------------------------------------------

class TestComputeFetchFingerprint:
    def test_returns_string(self) -> None:
        fp = compute_fetch_fingerprint(_make_params())
        assert isinstance(fp, str)

    def test_sha256_length(self) -> None:
        fp = compute_fetch_fingerprint(_make_params())
        assert len(fp) == 64

    def test_deterministic(self) -> None:
        p = _make_params()
        assert compute_fetch_fingerprint(p) == compute_fetch_fingerprint(p)

    def test_same_params_same_fingerprint(self) -> None:
        a = _make_params()
        b = _make_params()
        assert compute_fetch_fingerprint(a) == compute_fetch_fingerprint(b)

    def test_different_provider_different_fingerprint(self) -> None:
        a = compute_fetch_fingerprint(_make_params(provider="yahoo"))
        b = compute_fetch_fingerprint(_make_params(provider="polygon"))
        assert a != b

    def test_different_symbol_different_fingerprint(self) -> None:
        a = compute_fetch_fingerprint(_make_params(symbol="AAPL"))
        b = compute_fetch_fingerprint(_make_params(symbol="MSFT"))
        assert a != b

    def test_different_asset_class_different_fingerprint(self) -> None:
        a = compute_fetch_fingerprint(_make_params(asset_class="equity"))
        b = compute_fetch_fingerprint(_make_params(asset_class="crypto"))
        assert a != b

    def test_different_exchange_different_fingerprint(self) -> None:
        a = compute_fetch_fingerprint(_make_params(exchange="NASDAQ"))
        b = compute_fetch_fingerprint(_make_params(exchange="NYSE"))
        assert a != b

    def test_different_timeframe_different_fingerprint(self) -> None:
        a = compute_fetch_fingerprint(_make_params(timeframe="1d"))
        b = compute_fetch_fingerprint(_make_params(timeframe="1h"))
        assert a != b

    def test_different_start_different_fingerprint(self) -> None:
        a = compute_fetch_fingerprint(_make_params(start=datetime(2023, 1, 1, tzinfo=_UTC)))
        b = compute_fetch_fingerprint(_make_params(start=datetime(2023, 2, 1, tzinfo=_UTC)))
        assert a != b

    def test_different_end_different_fingerprint(self) -> None:
        a = compute_fetch_fingerprint(_make_params(end=datetime(2023, 6, 30, tzinfo=_UTC)))
        b = compute_fetch_fingerprint(_make_params(end=datetime(2023, 12, 31, tzinfo=_UTC)))
        assert a != b

    def test_different_adjustment_mode_different_fingerprint(self) -> None:
        a = compute_fetch_fingerprint(_make_params(adjustment_mode=AdjustmentMode.ADJUSTED))
        b = compute_fetch_fingerprint(_make_params(adjustment_mode=AdjustmentMode.RAW))
        assert a != b

    def test_canonical_is_sha256_of_expected_string(self) -> None:
        p = _make_params()
        start_utc = _START.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        end_utc = _END.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        expected_canonical = "|".join([
            "yahoo", "aapl", "equity", "nasdaq", "1d",
            start_utc, end_utc, "adjusted",
        ])
        expected = hashlib.sha256(expected_canonical.encode("utf-8")).hexdigest()
        assert compute_fetch_fingerprint(p) == expected

    def test_timestamps_normalized_to_utc_in_fingerprint(self) -> None:
        import datetime as dt
        tz_plus2 = dt.timezone(dt.timedelta(hours=2))
        # 2023-01-01T02:00:00+02:00  ==  2023-01-01T00:00:00+00:00
        start_shifted = datetime(2023, 1, 1, 2, 0, 0, tzinfo=tz_plus2)
        p_shifted = _make_params(start=start_shifted)
        p_utc = _make_params(start=_START)
        assert compute_fetch_fingerprint(p_shifted) == compute_fetch_fingerprint(p_utc)

    def test_provider_case_insensitive_in_fingerprint(self) -> None:
        # The canonical uses lowercase, so "Yahoo" == "yahoo" == "YAHOO"
        a = compute_fetch_fingerprint(_make_params(provider="Yahoo"))
        b = compute_fetch_fingerprint(_make_params(provider="yahoo"))
        c = compute_fetch_fingerprint(_make_params(provider="YAHOO"))
        assert a == b == c

    def test_symbol_case_insensitive_in_fingerprint(self) -> None:
        a = compute_fetch_fingerprint(_make_params(symbol="AAPL"))
        b = compute_fetch_fingerprint(_make_params(symbol="aapl"))
        assert a == b


# ---------------------------------------------------------------------------
# TestDatasetFetchIdentity
# ---------------------------------------------------------------------------

class TestDatasetFetchIdentity:
    def test_frozen(self) -> None:
        params = _make_params()
        identity = DatasetFetchIdentity(
            parameters=params,
            fingerprint="abc123",
            dataset_id="equity__NASDAQ__AAPL__yahoo__1d__adjusted",
        )
        with pytest.raises(Exception):
            identity.fingerprint = "different"  # type: ignore[misc]

    def test_parameters_stored(self) -> None:
        params = _make_params()
        identity = DatasetFetchIdentity(
            parameters=params,
            fingerprint="fp",
            dataset_id="ds_id",
        )
        assert identity.parameters is params

    def test_fingerprint_stored(self) -> None:
        identity = DatasetFetchIdentity(
            parameters=_make_params(),
            fingerprint="abc123",
            dataset_id="ds_id",
        )
        assert identity.fingerprint == "abc123"

    def test_dataset_id_stored(self) -> None:
        identity = DatasetFetchIdentity(
            parameters=_make_params(),
            fingerprint="fp",
            dataset_id="equity__NASDAQ__AAPL__yahoo__1d__adjusted",
        )
        assert identity.dataset_id == "equity__NASDAQ__AAPL__yahoo__1d__adjusted"

    def test_schema_version_has_default(self) -> None:
        identity = DatasetFetchIdentity(
            parameters=_make_params(),
            fingerprint="fp",
            dataset_id="ds_id",
        )
        assert identity.schema_version == FETCH_IDENTITY_SCHEMA_VERSION

    def test_schema_version_is_non_empty_string(self) -> None:
        assert isinstance(FETCH_IDENTITY_SCHEMA_VERSION, str)
        assert FETCH_IDENTITY_SCHEMA_VERSION.strip() != ""

    def test_schema_version_matches_module_constant(self) -> None:
        identity = DatasetFetchIdentity(
            parameters=_make_params(),
            fingerprint="fp",
            dataset_id="ds_id",
        )
        assert identity.schema_version == FETCH_IDENTITY_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# TestBuildFetchIdentity
# ---------------------------------------------------------------------------

class TestBuildFetchIdentity:
    def test_returns_dataset_fetch_identity(self) -> None:
        result = build_fetch_identity(
            **_BASE_PARAMS,
            dataset_id="equity__NASDAQ__AAPL__yahoo__1d__adjusted",
        )
        assert isinstance(result, DatasetFetchIdentity)

    def test_fingerprint_is_deterministic(self) -> None:
        a = build_fetch_identity(
            **_BASE_PARAMS,
            dataset_id="ds_id",
        )
        b = build_fetch_identity(
            **_BASE_PARAMS,
            dataset_id="ds_id",
        )
        assert a.fingerprint == b.fingerprint

    def test_fingerprint_matches_direct_computation(self) -> None:
        params = _make_params()
        direct = compute_fetch_fingerprint(params)
        via_builder = build_fetch_identity(
            **_BASE_PARAMS,
            dataset_id="ds_id",
        )
        assert via_builder.fingerprint == direct

    def test_parameters_reflect_inputs(self) -> None:
        result = build_fetch_identity(
            **_BASE_PARAMS,
            dataset_id="ds_id",
        )
        assert result.parameters.provider == "yahoo"
        assert result.parameters.symbol == "AAPL"
        assert result.parameters.asset_class == "equity"
        assert result.parameters.exchange == "NASDAQ"
        assert result.parameters.timeframe == "1d"
        assert result.parameters.adjustment_mode == AdjustmentMode.ADJUSTED

    def test_dataset_id_passed_through(self) -> None:
        result = build_fetch_identity(
            **_BASE_PARAMS,
            dataset_id="equity__NASDAQ__AAPL__yahoo__1d__adjusted",
        )
        assert result.dataset_id == "equity__NASDAQ__AAPL__yahoo__1d__adjusted"

    def test_schema_version_set(self) -> None:
        result = build_fetch_identity(**_BASE_PARAMS, dataset_id="ds_id")
        assert result.schema_version == FETCH_IDENTITY_SCHEMA_VERSION

    def test_empty_provider_raises(self) -> None:
        with pytest.raises(ValueError):
            build_fetch_identity(**{**_BASE_PARAMS, "provider": ""}, dataset_id="ds_id")

    def test_naive_datetime_raises(self) -> None:
        with pytest.raises(ValueError):
            build_fetch_identity(
                **{**_BASE_PARAMS, "start": datetime(2023, 1, 1)},
                dataset_id="ds_id",
            )


# ---------------------------------------------------------------------------
# TestDatasetFetchMetadataResponseSchema
# ---------------------------------------------------------------------------

class TestDatasetFetchMetadataResponseSchema:
    def test_has_expected_fields(self) -> None:
        fields = DatasetFetchMetadataResponse.model_fields
        expected = {
            "dataset_id", "fingerprint", "provider", "symbol",
            "asset_class", "exchange", "timeframe",
            "start_utc", "end_utc", "adjustment_mode", "schema_version",
        }
        assert expected.issubset(set(fields.keys()))

    def test_can_be_constructed(self) -> None:
        resp = DatasetFetchMetadataResponse(
            dataset_id="equity__NASDAQ__AAPL__yahoo__1d__adjusted",
            fingerprint="a" * 64,
            provider="yahoo",
            symbol="AAPL",
            asset_class="equity",
            exchange="NASDAQ",
            timeframe="1d",
            start_utc="2023-01-01T00:00:00+00:00",
            end_utc="2023-06-30T00:00:00+00:00",
            adjustment_mode="adjusted",
            schema_version="1",
        )
        assert resp.fingerprint == "a" * 64
        assert resp.dataset_id == "equity__NASDAQ__AAPL__yahoo__1d__adjusted"

    def test_serializes_to_dict(self) -> None:
        resp = DatasetFetchMetadataResponse(
            dataset_id="ds_id",
            fingerprint="fp",
            provider="yahoo",
            symbol="AAPL",
            asset_class="equity",
            exchange="NASDAQ",
            timeframe="1d",
            start_utc="2023-01-01T00:00:00+00:00",
            end_utc="2023-06-30T00:00:00+00:00",
            adjustment_mode="adjusted",
            schema_version="1",
        )
        d = resp.model_dump()
        assert "fingerprint" in d
        assert "dataset_id" in d
        assert "schema_version" in d


# ---------------------------------------------------------------------------
# TestMarketDataOHLCVResponseBackwardCompat
# ---------------------------------------------------------------------------

class TestMarketDataOHLCVResponseBackwardCompat:
    def test_fetch_metadata_defaults_to_none(self) -> None:
        resp = MarketDataOHLCVResponse(
            provider="yahoo",
            symbol="AAPL",
            asset_class="equity",
            exchange="NASDAQ",
            timeframe="1d",
            start=_START,
            end=_END,
            candle_count=0,
            candles=[],
        )
        assert resp.fetch_metadata is None

    def test_existing_fields_unchanged(self) -> None:
        resp = MarketDataOHLCVResponse(
            provider="yahoo",
            symbol="AAPL",
            asset_class="equity",
            exchange="NASDAQ",
            timeframe="1d",
            start=_START,
            end=_END,
            candle_count=5,
            candles=[],
        )
        assert resp.provider == "yahoo"
        assert resp.symbol == "AAPL"
        assert resp.candle_count == 5

    def test_response_with_fetch_metadata_serializes(self) -> None:
        meta = DatasetFetchMetadataResponse(
            dataset_id="ds_id",
            fingerprint="fp",
            provider="yahoo",
            symbol="AAPL",
            asset_class="equity",
            exchange="NASDAQ",
            timeframe="1d",
            start_utc="2023-01-01T00:00:00+00:00",
            end_utc="2023-06-30T00:00:00+00:00",
            adjustment_mode="adjusted",
            schema_version="1",
        )
        resp = MarketDataOHLCVResponse(
            provider="yahoo",
            symbol="AAPL",
            asset_class="equity",
            exchange="NASDAQ",
            timeframe="1d",
            start=_START,
            end=_END,
            candle_count=0,
            candles=[],
            fetch_metadata=meta,
        )
        d = resp.model_dump()
        assert d["fetch_metadata"] is not None
        assert d["fetch_metadata"]["fingerprint"] == "fp"


# ---------------------------------------------------------------------------
# TestMarketDataServiceFetchMetadataIntegration
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


_ACTIVE_USER = User(
    user_id="test-uid", username="testuser", email="t@example.com",
    password_hash="h", created_at="2025-01-01T00:00:00+00:00",
    subscription_status="active",
)


class TestMarketDataServiceFetchMetadataIntegration:
    def setup_method(self):
        app.dependency_overrides[require_active_subscription] = lambda: _ACTIVE_USER

    def teardown_method(self):
        app.dependency_overrides.pop(require_active_subscription, None)

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_response_includes_fetch_metadata(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        df = _make_df([
            {"ts": "2023-01-03", "open": 130.0, "high": 133.0, "low": 129.0, "close": 132.0, "vol": 1e7},
        ])
        mock_yf.Ticker.return_value.history.return_value = df
        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        client = TestClient(app)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo", "symbol": "AAPL", "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
        })
        app.dependency_overrides.pop(get_storage_path, None)
        assert resp.status_code == 200
        data = resp.json()
        assert "fetch_metadata" in data
        assert data["fetch_metadata"] is not None

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_fetch_metadata_fingerprint_non_empty(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        df = _make_df([
            {"ts": "2023-01-03", "open": 130.0, "high": 133.0, "low": 129.0, "close": 132.0, "vol": 1e7},
        ])
        mock_yf.Ticker.return_value.history.return_value = df
        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        client = TestClient(app)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo", "symbol": "AAPL", "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
        })
        app.dependency_overrides.pop(get_storage_path, None)
        assert len(resp.json()["fetch_metadata"]["fingerprint"]) == 64

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_fetch_metadata_dataset_id_non_empty(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        df = _make_df([
            {"ts": "2023-01-03", "open": 130.0, "high": 133.0, "low": 129.0, "close": 132.0, "vol": 1e7},
        ])
        mock_yf.Ticker.return_value.history.return_value = df
        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        client = TestClient(app)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo", "symbol": "AAPL", "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
        })
        app.dependency_overrides.pop(get_storage_path, None)
        meta = resp.json()["fetch_metadata"]
        assert meta["dataset_id"] != ""
        assert "yahoo" in meta["dataset_id"]
        assert "AAPL" in meta["dataset_id"]

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_fetch_metadata_provider_matches_request(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        df = _make_df([
            {"ts": "2023-01-03", "open": 130.0, "high": 133.0, "low": 129.0, "close": 132.0, "vol": 1e7},
        ])
        mock_yf.Ticker.return_value.history.return_value = df
        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        client = TestClient(app)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo", "symbol": "AAPL", "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
        })
        app.dependency_overrides.pop(get_storage_path, None)
        assert resp.json()["fetch_metadata"]["provider"] == "yahoo"

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_fetch_metadata_symbol_matches_request(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        df = _make_df([
            {"ts": "2023-01-03", "open": 130.0, "high": 133.0, "low": 129.0, "close": 132.0, "vol": 1e7},
        ])
        mock_yf.Ticker.return_value.history.return_value = df
        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        client = TestClient(app)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo", "symbol": "AAPL", "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
        })
        app.dependency_overrides.pop(get_storage_path, None)
        assert resp.json()["fetch_metadata"]["symbol"] == "AAPL"

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_fetch_metadata_timeframe_matches_request(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        df = _make_df([
            {"ts": "2023-01-03", "open": 130.0, "high": 133.0, "low": 129.0, "close": 132.0, "vol": 1e7},
        ])
        mock_yf.Ticker.return_value.history.return_value = df
        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        client = TestClient(app)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo", "symbol": "AAPL", "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
        })
        app.dependency_overrides.pop(get_storage_path, None)
        assert resp.json()["fetch_metadata"]["timeframe"] == "1d"

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_fetch_metadata_adjustment_mode_present(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        df = _make_df([
            {"ts": "2023-01-03", "open": 130.0, "high": 133.0, "low": 129.0, "close": 132.0, "vol": 1e7},
        ])
        mock_yf.Ticker.return_value.history.return_value = df
        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        client = TestClient(app)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo", "symbol": "AAPL", "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
        })
        app.dependency_overrides.pop(get_storage_path, None)
        assert resp.json()["fetch_metadata"]["adjustment_mode"] != ""

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_fetch_metadata_schema_version_present(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        df = _make_df([
            {"ts": "2023-01-03", "open": 130.0, "high": 133.0, "low": 129.0, "close": 132.0, "vol": 1e7},
        ])
        mock_yf.Ticker.return_value.history.return_value = df
        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        client = TestClient(app)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo", "symbol": "AAPL", "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
        })
        app.dependency_overrides.pop(get_storage_path, None)
        assert resp.json()["fetch_metadata"]["schema_version"] == FETCH_IDENTITY_SCHEMA_VERSION

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_fetch_metadata_start_utc_and_end_utc_present(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        df = _make_df([
            {"ts": "2023-01-03", "open": 130.0, "high": 133.0, "low": 129.0, "close": 132.0, "vol": 1e7},
        ])
        mock_yf.Ticker.return_value.history.return_value = df
        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        client = TestClient(app)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo", "symbol": "AAPL", "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
        })
        app.dependency_overrides.pop(get_storage_path, None)
        meta = resp.json()["fetch_metadata"]
        assert meta["start_utc"] != ""
        assert meta["end_utc"] != ""
        assert "2023" in meta["start_utc"]

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_fetch_metadata_fingerprint_deterministic_across_requests(
        self, mock_yf: MagicMock, tmp_path: Path
    ) -> None:
        df = _make_df([
            {"ts": "2023-01-03", "open": 130.0, "high": 133.0, "low": 129.0, "close": 132.0, "vol": 1e7},
        ])
        mock_yf.Ticker.return_value.history.return_value = df
        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        client = TestClient(app)
        params = {
            "provider": "yahoo", "symbol": "AAPL", "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
        }
        r1 = client.get("/market-data/ohlcv", params=params)
        r2 = client.get("/market-data/ohlcv", params=params)
        app.dependency_overrides.pop(get_storage_path, None)
        assert r1.json()["fetch_metadata"]["fingerprint"] == r2.json()["fetch_metadata"]["fingerprint"]

    @patch("backend.data_providers.yahoo.adapter.yf")
    def test_existing_ohlcv_fields_unchanged(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        df = _make_df([
            {"ts": "2023-01-03", "open": 130.0, "high": 133.0, "low": 129.0, "close": 132.0, "vol": 1e7},
        ])
        mock_yf.Ticker.return_value.history.return_value = df
        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        client = TestClient(app)
        resp = client.get("/market-data/ohlcv", params={
            "provider": "yahoo", "symbol": "AAPL", "timeframe": "1d",
            "start": "2023-01-01", "end": "2023-01-05",
        })
        app.dependency_overrides.pop(get_storage_path, None)
        data = resp.json()
        # All existing fields must still be present and correct
        assert data["provider"] == "yahoo"
        assert data["symbol"] == "AAPL"
        assert data["timeframe"] == "1d"
        assert data["candle_count"] == 1
        assert len(data["candles"]) == 1


# ---------------------------------------------------------------------------
# TestArchitectureBoundary
# ---------------------------------------------------------------------------

class TestArchitectureBoundary:
    def test_fetch_identity_module_no_yahoo_import(self) -> None:
        import ast
        import pathlib
        src = pathlib.Path("backend/data/models/fetch_identity.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "yahoo" not in node.module, (
                    f"fetch_identity must not import from yahoo; found: {node.module}"
                )

    def test_fetch_identity_module_no_provider_factory_import(self) -> None:
        import ast
        import pathlib
        src = pathlib.Path("backend/data/models/fetch_identity.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "provider_factory" not in node.module, (
                    f"fetch_identity must not import from provider_factory; found: {node.module}"
                )

    def test_market_data_service_still_no_yahoo_import(self) -> None:
        import ast
        import pathlib
        src = pathlib.Path("backend/api/services/market_data_service.py").read_text()
        tree = ast.parse(src)
        forbidden = "data_providers.yahoo"
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = ""
                if isinstance(node, ast.ImportFrom) and node.module:
                    module = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name
                assert forbidden not in module, (
                    f"market_data_service must not import from {forbidden}; found: {module}"
                )

    def test_fetch_identity_module_has_no_api_imports(self) -> None:
        import ast
        import pathlib
        src = pathlib.Path("backend/data/models/fetch_identity.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "api" not in node.module.split("."), (
                    f"fetch_identity must not import from API layer; found: {node.module}"
                )
