"""
Phase 3D — Local Dataset Providers (CSV / Parquet)

Tests covering:
  - LocalCSVProvider: loading, fetching, column map, errors
  - LocalParquetProvider: loading, fetching, timestamp types, errors
  - Factory registration of "csv" and "parquet" in create_default_factory_registry()
  - OHLCVService integration (FETCH_AND_STORE, BYPASS_CACHE) with local providers
  - DatasetFetchIdentity fingerprint determinism for local providers
  - Architecture boundary — no yahoo imports in local provider modules
  - Backward compatibility — yahoo flow and factory contract unchanged
"""
import ast
import csv
import io
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from backend.data.models.dataset import DatasetIdentity
from backend.data.models.fetch_identity import build_fetch_identity
from backend.data.models.instrument import AdjustmentMode, Instrument
from backend.data_providers.base import ProviderFetchError
from backend.data_providers.local import (
    LocalColumnMap,
    LocalCSVProvider,
    LocalCSVProviderError,
    LocalParquetProvider,
    LocalParquetProviderError,
)
from backend.data_providers.provider_factory import (
    ProviderBuildError,
    create_default_factory_registry,
)
from backend.services.ohlcv_service import OHLCVService

# ---------------------------------------------------------------------------
# Fixtures — shared helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
VALID_CSV = FIXTURES_DIR / "valid_ohlcv.csv"
NONSTANDARD_CSV = FIXTURES_DIR / "ohlcv_nonstandard_cols.csv"


def _make_identity(provider: str = "csv") -> DatasetIdentity:
    instrument = Instrument(
        symbol="AAPL", asset_class="equity", exchange="NASDAQ", currency="USD"
    )
    return DatasetIdentity(
        instrument=instrument,
        provider=provider,
        timeframe="1d",
        adjustment_mode=AdjustmentMode.ADJUSTED,
    )


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def _make_parquet_file(path: Path, rows: list[dict]) -> Path:
    """Write a minimal OHLCV Parquet fixture using standard column names."""
    timestamps = pa.array(
        [r["timestamp"] for r in rows],
        type=pa.timestamp("us", tz="UTC"),
    )
    table = pa.table(
        {
            "timestamp": timestamps,
            "open": pa.array([r["open"] for r in rows], type=pa.float64()),
            "high": pa.array([r["high"] for r in rows], type=pa.float64()),
            "low": pa.array([r["low"] for r in rows], type=pa.float64()),
            "close": pa.array([r["close"] for r in rows], type=pa.float64()),
            "volume": pa.array([r["volume"] for r in rows], type=pa.float64()),
        }
    )
    pq.write_table(table, path)
    return path


_SAMPLE_ROWS = [
    {
        "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "open": 100.0, "high": 105.0, "low": 99.0, "close": 103.0, "volume": 5000.0,
    },
    {
        "timestamp": datetime(2024, 1, 2, tzinfo=timezone.utc),
        "open": 103.0, "high": 108.0, "low": 102.0, "close": 107.0, "volume": 6000.0,
    },
    {
        "timestamp": datetime(2024, 1, 3, tzinfo=timezone.utc),
        "open": 107.0, "high": 110.0, "low": 106.0, "close": 109.0, "volume": 4500.0,
    },
]


@pytest.fixture
def sample_parquet(tmp_path: Path) -> Path:
    return _make_parquet_file(tmp_path / "data.parquet", _SAMPLE_ROWS)


@pytest.fixture
def minimal_csv(tmp_path: Path) -> Path:
    path = tmp_path / "data.csv"
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for r in _SAMPLE_ROWS:
            writer.writerow({
                "timestamp": r["timestamp"].strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                "open": r["open"], "high": r["high"], "low": r["low"],
                "close": r["close"], "volume": r["volume"],
            })
    return path


# ===========================================================================
# LocalColumnMap
# ===========================================================================

class TestLocalColumnMap:
    def test_default_values(self):
        col = LocalColumnMap()
        assert col.timestamp == "timestamp"
        assert col.open == "open"
        assert col.high == "high"
        assert col.low == "low"
        assert col.close == "close"
        assert col.volume == "volume"

    def test_custom_values(self):
        col = LocalColumnMap(timestamp="Date", open="Open", high="High",
                             low="Low", close="Close", volume="Volume")
        assert col.timestamp == "Date"
        assert col.open == "Open"

    def test_is_dataclass(self):
        import dataclasses
        assert dataclasses.is_dataclass(LocalColumnMap)


# ===========================================================================
# LocalCSVProvider — basic
# ===========================================================================

class TestLocalCSVProviderBasic:
    def _make(self, path: Path, **kw):
        defaults = dict(symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d")
        defaults.update(kw)
        return LocalCSVProvider(file_path=path, **defaults)

    def test_provider_name(self, minimal_csv):
        assert self._make(minimal_csv).provider_name == "csv"

    def test_source_field_on_records(self, minimal_csv):
        records = self._make(minimal_csv).load()
        assert all(r.source == "csv" for r in records)

    def test_load_returns_normalized_ohlcv(self, minimal_csv):
        from backend.data.schemas import NormalizedOHLCV
        records = self._make(minimal_csv).load()
        assert len(records) == 3
        assert all(isinstance(r, NormalizedOHLCV) for r in records)

    def test_metadata_fields_from_constructor(self, minimal_csv):
        provider = LocalCSVProvider(
            file_path=minimal_csv, symbol="MSFT", asset_class="equity",
            venue="NYSE", timeframe="1h",
        )
        records = provider.load()
        assert all(r.symbol == "MSFT" for r in records)
        assert all(r.asset_class == "equity" for r in records)
        assert all(r.venue == "NYSE" for r in records)
        assert all(r.timeframe == "1h" for r in records)

    def test_supported_timeframes_nonempty(self, minimal_csv):
        tfs = self._make(minimal_csv).supported_timeframes()
        assert "1d" in tfs
        assert "1h" in tfs
        assert len(tfs) > 5

    def test_supported_asset_classes_nonempty(self, minimal_csv):
        acs = self._make(minimal_csv).supported_asset_classes()
        assert "equity" in acs
        assert "crypto" in acs

    def test_empty_csv_body_returns_empty(self, tmp_path):
        path = tmp_path / "empty.csv"
        path.write_text("timestamp,open,high,low,close,volume\n")
        records = self._make(path).load()
        assert records == []

    def test_timestamps_are_utc_aware(self, minimal_csv):
        records = self._make(minimal_csv).load()
        for r in records:
            assert r.timestamp.tzinfo is not None


# ===========================================================================
# LocalCSVProvider — fetch (date filtering)
# ===========================================================================

class TestLocalCSVProviderFetch:
    def _make(self, path: Path):
        return LocalCSVProvider(
            file_path=path, symbol="AAPL", asset_class="equity",
            venue="NASDAQ", timeframe="1d",
        )

    def test_fetch_full_range_returns_all(self, minimal_csv):
        provider = self._make(minimal_csv)
        records = provider.fetch(_utc(2024, 1, 1), _utc(2024, 1, 3))
        assert len(records) == 3

    def test_fetch_excludes_before_start(self, minimal_csv):
        provider = self._make(minimal_csv)
        records = provider.fetch(_utc(2024, 1, 2), _utc(2024, 1, 3))
        assert len(records) == 2
        assert all(r.timestamp >= _utc(2024, 1, 2) for r in records)

    def test_fetch_excludes_after_end(self, minimal_csv):
        provider = self._make(minimal_csv)
        records = provider.fetch(_utc(2024, 1, 1), _utc(2024, 1, 2))
        assert len(records) == 2
        assert all(r.timestamp <= _utc(2024, 1, 2) for r in records)

    def test_fetch_empty_range(self, minimal_csv):
        provider = self._make(minimal_csv)
        records = provider.fetch(_utc(2025, 1, 1), _utc(2025, 12, 31))
        assert records == []

    def test_fetch_naive_start_raises(self, minimal_csv):
        provider = self._make(minimal_csv)
        with pytest.raises(ValueError, match="timezone-aware"):
            provider.fetch(datetime(2024, 1, 1), _utc(2024, 1, 3))

    def test_fetch_naive_end_raises(self, minimal_csv):
        provider = self._make(minimal_csv)
        with pytest.raises(ValueError, match="timezone-aware"):
            provider.fetch(_utc(2024, 1, 1), datetime(2024, 1, 3))


# ===========================================================================
# LocalCSVProvider — errors
# ===========================================================================

class TestLocalCSVProviderErrors:
    def _make(self, path: Path):
        return LocalCSVProvider(
            file_path=path, symbol="AAPL", asset_class="equity",
            venue="NASDAQ", timeframe="1d",
        )

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(LocalCSVProviderError, match="not found"):
            self._make(tmp_path / "nonexistent.csv").load()

    def test_missing_column_raises(self, tmp_path):
        path = tmp_path / "bad.csv"
        path.write_text("timestamp,open,high,low,close\n2024-01-01,1.0,2.0,0.5,1.5\n")
        with pytest.raises(LocalCSVProviderError, match="volume"):
            self._make(path).load()

    def test_error_message_lists_missing_columns(self, tmp_path):
        path = tmp_path / "bad.csv"
        path.write_text("Date,Open\n2024-01-01,1.0\n")
        with pytest.raises(LocalCSVProviderError) as exc_info:
            self._make(path).load()
        assert "volume" in str(exc_info.value) or "missing" in str(exc_info.value).lower()

    def test_invalid_timestamp_raises(self, tmp_path):
        path = tmp_path / "bad_ts.csv"
        path.write_text(
            "timestamp,open,high,low,close,volume\n"
            "NOT_A_DATE,100.0,110.0,90.0,105.0,1000.0\n"
        )
        with pytest.raises(LocalCSVProviderError):
            self._make(path).load()

    def test_is_subclass_of_provider_fetch_error(self):
        assert issubclass(LocalCSVProviderError, ProviderFetchError)


# ===========================================================================
# LocalCSVProvider — column map
# ===========================================================================

class TestLocalCSVProviderColumnMap:
    def test_nonstandard_columns_with_map(self):
        provider = LocalCSVProvider(
            file_path=NONSTANDARD_CSV,
            symbol="TSLA", asset_class="equity", venue="NASDAQ", timeframe="1d",
            column_map=LocalColumnMap(
                timestamp="Date", open="Open", high="High",
                low="Low", close="Close", volume="Volume",
            ),
        )
        records = provider.load()
        assert len(records) == 3
        assert all(r.symbol == "TSLA" for r in records)

    def test_nonstandard_columns_fail_without_map(self):
        provider = LocalCSVProvider(
            file_path=NONSTANDARD_CSV,
            symbol="TSLA", asset_class="equity", venue="NASDAQ", timeframe="1d",
        )
        with pytest.raises(LocalCSVProviderError):
            provider.load()

    def test_date_only_timestamps_parsed(self):
        """NONSTANDARD_CSV uses YYYY-MM-DD dates — verify they parse to midnight UTC."""
        provider = LocalCSVProvider(
            file_path=NONSTANDARD_CSV,
            symbol="TSLA", asset_class="equity", venue="NASDAQ", timeframe="1d",
            column_map=LocalColumnMap(
                timestamp="Date", open="Open", high="High",
                low="Low", close="Close", volume="Volume",
            ),
        )
        records = provider.load()
        assert records[0].timestamp == datetime(2024, 1, 1, tzinfo=timezone.utc)


# ===========================================================================
# LocalCSVProvider — fixture integration (valid_ohlcv.csv)
# ===========================================================================

class TestLocalCSVProviderRealFixture:
    def test_loads_valid_ohlcv_fixture(self):
        provider = LocalCSVProvider(
            file_path=VALID_CSV,
            symbol="BTC", asset_class="crypto", venue="BINANCE", timeframe="1h",
        )
        records = provider.load()
        assert len(records) == 5
        assert records[0].open == 42000.0
        assert records[0].close == 42200.0

    def test_all_records_utc_aware(self):
        provider = LocalCSVProvider(
            file_path=VALID_CSV,
            symbol="BTC", asset_class="crypto", venue="BINANCE", timeframe="1h",
        )
        for r in provider.load():
            assert r.timestamp.tzinfo is not None


# ===========================================================================
# LocalParquetProvider — basic
# ===========================================================================

class TestLocalParquetProviderBasic:
    def _make(self, path: Path, **kw):
        defaults = dict(symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d")
        defaults.update(kw)
        return LocalParquetProvider(file_path=path, **defaults)

    def test_provider_name(self, sample_parquet):
        assert self._make(sample_parquet).provider_name == "parquet"

    def test_source_field_on_records(self, sample_parquet):
        records = self._make(sample_parquet).load()
        assert all(r.source == "parquet" for r in records)

    def test_load_returns_normalized_ohlcv(self, sample_parquet):
        from backend.data.schemas import NormalizedOHLCV
        records = self._make(sample_parquet).load()
        assert len(records) == 3
        assert all(isinstance(r, NormalizedOHLCV) for r in records)

    def test_metadata_fields_from_constructor(self, sample_parquet):
        provider = LocalParquetProvider(
            file_path=sample_parquet, symbol="GOOG", asset_class="equity",
            venue="NASDAQ", timeframe="1h",
        )
        records = provider.load()
        assert all(r.symbol == "GOOG" for r in records)
        assert all(r.timeframe == "1h" for r in records)

    def test_timestamps_are_utc_aware(self, sample_parquet):
        records = self._make(sample_parquet).load()
        for r in records:
            assert r.timestamp.tzinfo is not None

    def test_supported_timeframes_nonempty(self, sample_parquet):
        tfs = self._make(sample_parquet).supported_timeframes()
        assert "1d" in tfs
        assert len(tfs) > 5

    def test_ohlcv_values_correct(self, sample_parquet):
        records = self._make(sample_parquet).load()
        assert records[0].open == 100.0
        assert records[0].high == 105.0
        assert records[0].close == 103.0


# ===========================================================================
# LocalParquetProvider — fetch (date filtering)
# ===========================================================================

class TestLocalParquetProviderFetch:
    def _make(self, path: Path):
        return LocalParquetProvider(
            file_path=path, symbol="AAPL", asset_class="equity",
            venue="NASDAQ", timeframe="1d",
        )

    def test_fetch_full_range(self, sample_parquet):
        records = self._make(sample_parquet).fetch(_utc(2024, 1, 1), _utc(2024, 1, 3))
        assert len(records) == 3

    def test_fetch_excludes_out_of_range(self, sample_parquet):
        records = self._make(sample_parquet).fetch(_utc(2024, 1, 2), _utc(2024, 1, 3))
        assert len(records) == 2
        assert all(r.timestamp >= _utc(2024, 1, 2) for r in records)

    def test_fetch_empty_range(self, sample_parquet):
        records = self._make(sample_parquet).fetch(_utc(2025, 1, 1), _utc(2025, 12, 31))
        assert records == []

    def test_fetch_naive_raises(self, sample_parquet):
        with pytest.raises(ValueError, match="timezone-aware"):
            self._make(sample_parquet).fetch(datetime(2024, 1, 1), _utc(2024, 1, 3))


# ===========================================================================
# LocalParquetProvider — timestamp type handling
# ===========================================================================

class TestLocalParquetTimestampTypes:
    def _provider(self, path: Path):
        return LocalParquetProvider(
            file_path=path, symbol="X", asset_class="equity", venue="NYSE", timeframe="1d",
        )

    def test_datetime_with_tzinfo(self, tmp_path):
        ts = datetime(2024, 6, 15, tzinfo=timezone.utc)
        path = _make_parquet_file(tmp_path / "tz.parquet", [{
            "timestamp": ts, "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5, "volume": 100.0,
        }])
        records = self._provider(path).load()
        assert records[0].timestamp == ts

    def test_datetime_naive_treated_as_utc(self, tmp_path):
        naive_ts = datetime(2024, 6, 15)
        table = pa.table({
            "timestamp": pa.array([naive_ts], type=pa.timestamp("us")),
            "open": [10.0], "high": [11.0], "low": [9.0], "close": [10.5], "volume": [100.0],
        })
        path = tmp_path / "naive.parquet"
        pq.write_table(table, path)
        records = self._provider(path).load()
        assert records[0].timestamp == datetime(2024, 6, 15, tzinfo=timezone.utc)

    def test_microsecond_integer_timestamp(self, tmp_path):
        from backend.data_providers.local.parquet_provider import _resolve_parquet_timestamp
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        us_epoch = int(ts.timestamp() * 1_000_000)
        result = _resolve_parquet_timestamp(us_epoch)
        assert result == ts

    def test_second_integer_timestamp(self, tmp_path):
        from backend.data_providers.local.parquet_provider import _resolve_parquet_timestamp
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        s_epoch = int(ts.timestamp())
        result = _resolve_parquet_timestamp(s_epoch)
        assert result == ts

    def test_string_iso_timestamp(self, tmp_path):
        from backend.data_providers.local.parquet_provider import _resolve_parquet_timestamp
        result = _resolve_parquet_timestamp("2024-03-15T00:00:00+00:00")
        assert result == datetime(2024, 3, 15, tzinfo=timezone.utc)


# ===========================================================================
# LocalParquetProvider — errors
# ===========================================================================

class TestLocalParquetProviderErrors:
    def _make(self, path: Path):
        return LocalParquetProvider(
            file_path=path, symbol="AAPL", asset_class="equity",
            venue="NASDAQ", timeframe="1d",
        )

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(LocalParquetProviderError, match="not found"):
            self._make(tmp_path / "nonexistent.parquet").load()

    def test_missing_column_raises(self, tmp_path):
        table = pa.table({
            "timestamp": pa.array(
                [datetime(2024, 1, 1, tzinfo=timezone.utc)],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "open": [10.0], "high": [11.0], "low": [9.0], "close": [10.5],
            # no volume column
        })
        path = tmp_path / "no_volume.parquet"
        pq.write_table(table, path)
        with pytest.raises(LocalParquetProviderError, match="volume"):
            self._make(path).load()

    def test_invalid_parquet_file_raises(self, tmp_path):
        path = tmp_path / "bad.parquet"
        path.write_bytes(b"this is not a parquet file")
        with pytest.raises(LocalParquetProviderError):
            self._make(path).load()

    def test_empty_parquet_returns_empty_list(self, tmp_path):
        table = pa.table({
            "timestamp": pa.array([], type=pa.timestamp("us", tz="UTC")),
            "open": pa.array([], type=pa.float64()),
            "high": pa.array([], type=pa.float64()),
            "low": pa.array([], type=pa.float64()),
            "close": pa.array([], type=pa.float64()),
            "volume": pa.array([], type=pa.float64()),
        })
        path = tmp_path / "empty.parquet"
        pq.write_table(table, path)
        records = self._make(path).load()
        assert records == []

    def test_is_subclass_of_provider_fetch_error(self):
        assert issubclass(LocalParquetProviderError, ProviderFetchError)


# ===========================================================================
# Factory registration
# ===========================================================================

class TestFactoryRegistration:
    def test_csv_registered(self):
        factory = create_default_factory_registry()
        assert "csv" in factory

    def test_parquet_registered(self):
        factory = create_default_factory_registry()
        assert "parquet" in factory

    def test_yahoo_still_registered(self):
        factory = create_default_factory_registry()
        assert "yahoo" in factory

    def test_factory_len_is_four(self):
        factory = create_default_factory_registry()
        assert len(factory) == 4

    def test_build_csv_returns_local_csv_provider(self, minimal_csv):
        factory = create_default_factory_registry()
        adapter = factory.build(
            "csv", file_path=str(minimal_csv),
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d",
        )
        assert isinstance(adapter, LocalCSVProvider)

    def test_build_parquet_returns_local_parquet_provider(self, sample_parquet):
        factory = create_default_factory_registry()
        adapter = factory.build(
            "parquet", file_path=str(sample_parquet),
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d",
        )
        assert isinstance(adapter, LocalParquetProvider)

    def test_build_csv_without_file_path_raises(self):
        factory = create_default_factory_registry()
        with pytest.raises(ProviderBuildError, match="file_path"):
            factory.build("csv", symbol="AAPL", asset_class="equity",
                          venue="NASDAQ", timeframe="1d")

    def test_build_parquet_without_file_path_raises(self):
        factory = create_default_factory_registry()
        with pytest.raises(ProviderBuildError, match="file_path"):
            factory.build("parquet", symbol="AAPL", asset_class="equity",
                          venue="NASDAQ", timeframe="1d")

    def test_csv_capabilities_provider_id(self):
        factory = create_default_factory_registry()
        caps = factory.get_capabilities("csv")
        assert caps.provider_id == "csv"
        assert caps.display_name == "Local CSV File"

    def test_parquet_capabilities_provider_id(self):
        factory = create_default_factory_registry()
        caps = factory.get_capabilities("parquet")
        assert caps.provider_id == "parquet"
        assert caps.display_name == "Local Parquet File"

    def test_csv_capabilities_timeframes(self):
        factory = create_default_factory_registry()
        caps = factory.get_capabilities("csv")
        assert "1d" in caps.supported_timeframes
        assert "1h" in caps.supported_timeframes

    def test_parquet_capabilities_asset_classes(self):
        factory = create_default_factory_registry()
        caps = factory.get_capabilities("parquet")
        assert "equity" in caps.supported_asset_classes
        assert "crypto" in caps.supported_asset_classes


# ===========================================================================
# OHLCVService integration — CSV provider
# ===========================================================================

class TestOHLCVServiceCSVIntegration:
    def test_fetch_and_store_csv(self, tmp_path, minimal_csv):
        identity = _make_identity("csv")
        provider = LocalCSVProvider(
            file_path=minimal_csv, symbol="AAPL", asset_class="equity",
            venue="NASDAQ", timeframe="1d",
        )
        service = OHLCVService(tmp_path / "storage")
        records = service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 3), provider)
        assert len(records) == 3
        assert all(r.symbol == "AAPL" for r in records)

    def test_bypass_cache_csv(self, tmp_path, minimal_csv):
        from backend.data.models.cache_policy import DatasetCachePolicy

        identity = _make_identity("csv")
        provider = LocalCSVProvider(
            file_path=minimal_csv, symbol="AAPL", asset_class="equity",
            venue="NASDAQ", timeframe="1d",
        )
        service = OHLCVService(tmp_path / "storage")
        records = service.get_ohlcv(
            identity, _utc(2024, 1, 1), _utc(2024, 1, 3), provider,
            cache_policy=DatasetCachePolicy.BYPASS_CACHE,
        )
        assert len(records) == 3
        # BYPASS_CACHE should not write any storage files
        assert not (tmp_path / "storage").exists() or not any(
            (tmp_path / "storage").rglob("data.parquet")
        )

    def test_cache_metadata_written_after_ingest(self, tmp_path, minimal_csv):
        identity = _make_identity("csv")
        provider = LocalCSVProvider(
            file_path=minimal_csv, symbol="AAPL", asset_class="equity",
            venue="NASDAQ", timeframe="1d",
        )
        service = OHLCVService(tmp_path / "storage")
        service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 3), provider)
        cache_files = list((tmp_path / "storage").rglob("cache_metadata.json"))
        assert len(cache_files) == 1

    def test_second_call_hits_cache(self, tmp_path, minimal_csv):
        identity = _make_identity("csv")
        provider = LocalCSVProvider(
            file_path=minimal_csv, symbol="AAPL", asset_class="equity",
            venue="NASDAQ", timeframe="1d",
        )
        service = OHLCVService(tmp_path / "storage")
        records1 = service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 3), provider)
        records2 = service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 3), provider)
        assert len(records1) == len(records2) == 3


# ===========================================================================
# OHLCVService integration — Parquet provider
# ===========================================================================

class TestOHLCVServiceParquetIntegration:
    def test_fetch_and_store_parquet(self, tmp_path, sample_parquet):
        identity = _make_identity("parquet")
        provider = LocalParquetProvider(
            file_path=sample_parquet, symbol="AAPL", asset_class="equity",
            venue="NASDAQ", timeframe="1d",
        )
        service = OHLCVService(tmp_path / "storage")
        records = service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 3), provider)
        assert len(records) == 3

    def test_parquet_records_normalized(self, tmp_path, sample_parquet):
        from backend.data.schemas import NormalizedOHLCV
        identity = _make_identity("parquet")
        provider = LocalParquetProvider(
            file_path=sample_parquet, symbol="AAPL", asset_class="equity",
            venue="NASDAQ", timeframe="1d",
        )
        service = OHLCVService(tmp_path / "storage")
        records = service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 3), provider)
        assert all(isinstance(r, NormalizedOHLCV) for r in records)
        assert all(r.symbol == "AAPL" for r in records)

    def test_cache_metadata_written_for_parquet(self, tmp_path, sample_parquet):
        identity = _make_identity("parquet")
        provider = LocalParquetProvider(
            file_path=sample_parquet, symbol="AAPL", asset_class="equity",
            venue="NASDAQ", timeframe="1d",
        )
        service = OHLCVService(tmp_path / "storage")
        service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 3), provider)
        cache_files = list((tmp_path / "storage").rglob("cache_metadata.json"))
        assert len(cache_files) == 1


# ===========================================================================
# DatasetFetchIdentity fingerprint integration
# ===========================================================================

class TestFetchIdentityIntegration:
    def _identity(self, provider: str):
        return _make_identity(provider)

    def test_build_fetch_identity_csv(self):
        identity = self._identity("csv")
        fi = build_fetch_identity(
            provider="csv", symbol="AAPL", asset_class="equity",
            exchange="NASDAQ", timeframe="1d",
            start=_utc(2024, 1, 1), end=_utc(2024, 12, 31),
            adjustment_mode=AdjustmentMode.ADJUSTED,
            dataset_id=identity.dataset_id,
        )
        assert fi.fingerprint
        assert len(fi.fingerprint) == 64

    def test_csv_fingerprint_deterministic(self):
        identity = self._identity("csv")
        fi1 = build_fetch_identity(
            provider="csv", symbol="AAPL", asset_class="equity",
            exchange="NASDAQ", timeframe="1d",
            start=_utc(2024, 1, 1), end=_utc(2024, 12, 31),
            adjustment_mode=AdjustmentMode.ADJUSTED,
            dataset_id=identity.dataset_id,
        )
        fi2 = build_fetch_identity(
            provider="csv", symbol="AAPL", asset_class="equity",
            exchange="NASDAQ", timeframe="1d",
            start=_utc(2024, 1, 1), end=_utc(2024, 12, 31),
            adjustment_mode=AdjustmentMode.ADJUSTED,
            dataset_id=identity.dataset_id,
        )
        assert fi1.fingerprint == fi2.fingerprint

    def test_build_fetch_identity_parquet(self):
        identity = self._identity("parquet")
        fi = build_fetch_identity(
            provider="parquet", symbol="AAPL", asset_class="equity",
            exchange="NASDAQ", timeframe="1d",
            start=_utc(2024, 1, 1), end=_utc(2024, 12, 31),
            adjustment_mode=AdjustmentMode.ADJUSTED,
            dataset_id=identity.dataset_id,
        )
        assert fi.fingerprint
        assert len(fi.fingerprint) == 64

    def test_csv_and_parquet_fingerprints_differ(self):
        id_csv = _make_identity("csv")
        id_parq = _make_identity("parquet")
        fi_csv = build_fetch_identity(
            provider="csv", symbol="AAPL", asset_class="equity",
            exchange="NASDAQ", timeframe="1d",
            start=_utc(2024, 1, 1), end=_utc(2024, 12, 31),
            adjustment_mode=AdjustmentMode.ADJUSTED,
            dataset_id=id_csv.dataset_id,
        )
        fi_parq = build_fetch_identity(
            provider="parquet", symbol="AAPL", asset_class="equity",
            exchange="NASDAQ", timeframe="1d",
            start=_utc(2024, 1, 1), end=_utc(2024, 12, 31),
            adjustment_mode=AdjustmentMode.ADJUSTED,
            dataset_id=id_parq.dataset_id,
        )
        assert fi_csv.fingerprint != fi_parq.fingerprint


# ===========================================================================
# Architecture boundary
# ===========================================================================

class TestArchitectureBoundary:
    def _get_imports(self, module_path: str) -> list[str]:
        source = Path(module_path).read_text()
        tree = ast.parse(source)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        return imports

    def _local_module(self, name: str) -> str:
        base = Path(__file__).parent.parent.parent / "backend" / "data_providers" / "local"
        return str(base / name)

    def test_csv_provider_no_yahoo_import(self):
        imports = self._get_imports(self._local_module("csv_provider.py"))
        assert not any("yahoo" in i for i in imports)

    def test_parquet_provider_no_yahoo_import(self):
        imports = self._get_imports(self._local_module("parquet_provider.py"))
        assert not any("yahoo" in i for i in imports)

    def test_csv_provider_no_api_import(self):
        imports = self._get_imports(self._local_module("csv_provider.py"))
        assert not any("backend.api" in i for i in imports)

    def test_parquet_provider_no_api_import(self):
        imports = self._get_imports(self._local_module("parquet_provider.py"))
        assert not any("backend.api" in i for i in imports)

    def test_shared_module_no_yahoo_import(self):
        imports = self._get_imports(self._local_module("_shared.py"))
        assert not any("yahoo" in i for i in imports)


# ===========================================================================
# Backward compatibility
# ===========================================================================

class TestBackwardCompatibility:
    def test_yahoo_still_in_factory(self):
        factory = create_default_factory_registry()
        assert "yahoo" in factory

    def test_factory_len_increased_by_three(self):
        """Phase 3A had 1 provider; Phase 3D added 2; Phase 3G added 1 → total 4."""
        factory = create_default_factory_registry()
        assert len(factory) == 4

    def test_existing_csv_adapter_unaffected(self):
        """The legacy CSVAdapter (with file_path at call time) still works."""
        from backend.data_providers.csv_adapter import CSVAdapter, CSVAdapterConfig
        config = CSVAdapterConfig(
            symbol="BTC", asset_class="crypto", venue="BINANCE",
            timeframe="1h", source="csv",
        )
        adapter = CSVAdapter(config)
        records = adapter.fetch(
            _utc(2024, 1, 1), datetime(2024, 1, 1, 4, 59, tzinfo=timezone.utc),
            file_path=str(VALID_CSV),
        )
        assert len(records) == 5

    def test_ohlcv_service_signature_unchanged(self, tmp_path, minimal_csv):
        """OHLCVService.get_ohlcv() still accepts positional/keyword args as before."""
        identity = _make_identity("csv")
        provider = LocalCSVProvider(
            file_path=minimal_csv, symbol="AAPL", asset_class="equity",
            venue="NASDAQ", timeframe="1d",
        )
        service = OHLCVService(tmp_path / "storage")
        # Call without new kwargs — backward-compatible defaults must apply
        records = service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 3), provider)
        assert isinstance(records, list)
