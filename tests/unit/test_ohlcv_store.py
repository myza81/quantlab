"""Tests for backend/storage/ohlcv_store.py — provider-aware OHLCV persistence."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.data.models.instrument import AdjustmentMode, Instrument
from backend.data.models.dataset import DatasetIdentity
from backend.data.schemas import NormalizedOHLCV
from backend.storage import ohlcv_store
from backend.storage.ohlcv_store import OHLCVWriteError, dataset_path
from backend.storage.parquet_store import StorageError
from tests.conftest import make_ohlcv


# ---------------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------------

def _instrument(symbol: str = "AAPL", asset_class: str = "equity",
                exchange: str = "NASDAQ") -> Instrument:
    return Instrument(symbol=symbol, asset_class=asset_class, exchange=exchange)


def _identity(provider: str = "yahoo", timeframe: str = "1d",
              adjustment_mode: AdjustmentMode = AdjustmentMode.RAW,
              instrument: Instrument | None = None) -> DatasetIdentity:
    if instrument is None:
        instrument = _instrument()
    return DatasetIdentity(
        instrument=instrument,
        provider=provider,
        timeframe=timeframe,
        adjustment_mode=adjustment_mode,
    )


def _ohlcv_record(offset_hours: int = 0, source: str = "yahoo", **overrides) -> NormalizedOHLCV:
    return make_ohlcv(
        symbol="AAPL",
        asset_class="equity",
        venue="NASDAQ",
        timeframe="1d",
        source=source,
        timestamp=datetime(2024, 1, 1, offset_hours, 0, 0, tzinfo=timezone.utc),
        **overrides,
    )


def _series(n: int = 3, source: str = "yahoo") -> list[NormalizedOHLCV]:
    return [_ohlcv_record(offset_hours=i, source=source) for i in range(n)]


# ---------------------------------------------------------------------------
# dataset_path
# ---------------------------------------------------------------------------

class TestDatasetPath:
    def test_path_includes_provider(self, tmp_path: Path) -> None:
        identity = _identity(provider="yahoo")
        p = dataset_path(tmp_path, identity)
        assert "yahoo" in p.parts

    def test_different_providers_produce_different_paths(self, tmp_path: Path) -> None:
        yahoo = _identity(provider="yahoo")
        polygon = _identity(provider="polygon")
        assert dataset_path(tmp_path, yahoo) != dataset_path(tmp_path, polygon)

    def test_path_includes_asset_class(self, tmp_path: Path) -> None:
        identity = _identity()
        p = dataset_path(tmp_path, identity)
        assert "equity" in p.parts

    def test_path_includes_exchange(self, tmp_path: Path) -> None:
        identity = _identity()
        p = dataset_path(tmp_path, identity)
        assert "NASDAQ" in p.parts

    def test_path_includes_symbol(self, tmp_path: Path) -> None:
        identity = _identity()
        p = dataset_path(tmp_path, identity)
        assert "AAPL" in p.parts

    def test_path_includes_timeframe(self, tmp_path: Path) -> None:
        identity = _identity(timeframe="1d")
        p = dataset_path(tmp_path, identity)
        assert "1d" in p.parts

    def test_path_includes_adjustment_mode(self, tmp_path: Path) -> None:
        identity = _identity(adjustment_mode=AdjustmentMode.ADJUSTED)
        p = dataset_path(tmp_path, identity)
        assert "adjusted" in p.parts

    def test_path_ends_with_data_parquet(self, tmp_path: Path) -> None:
        identity = _identity()
        p = dataset_path(tmp_path, identity)
        assert p.name == "data.parquet"


# ---------------------------------------------------------------------------
# write()
# ---------------------------------------------------------------------------

class TestOHLCVWrite:
    def test_write_creates_parquet_file(self, tmp_path: Path) -> None:
        identity = _identity()
        path = ohlcv_store.write(_series(), tmp_path, identity)
        assert path.exists()

    def test_write_returns_canonical_path(self, tmp_path: Path) -> None:
        identity = _identity()
        path = ohlcv_store.write(_series(), tmp_path, identity)
        assert path == dataset_path(tmp_path, identity)

    def test_write_empty_raises(self, tmp_path: Path) -> None:
        with pytest.raises(OHLCVWriteError, match="empty"):
            ohlcv_store.write([], tmp_path, _identity())

    def test_write_symbol_mismatch_raises(self, tmp_path: Path) -> None:
        record = make_ohlcv(symbol="GOOG", asset_class="equity", timeframe="1d",
                            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc))
        with pytest.raises(OHLCVWriteError, match="symbol"):
            ohlcv_store.write([record], tmp_path, _identity())

    def test_write_asset_class_mismatch_raises(self, tmp_path: Path) -> None:
        record = make_ohlcv(symbol="AAPL", asset_class="crypto", timeframe="1d",
                            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc))
        with pytest.raises(OHLCVWriteError, match="asset_class"):
            ohlcv_store.write([record], tmp_path, _identity())

    def test_write_timeframe_mismatch_raises(self, tmp_path: Path) -> None:
        record = make_ohlcv(symbol="AAPL", asset_class="equity", timeframe="1h",
                            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc))
        with pytest.raises(OHLCVWriteError, match="timeframe"):
            ohlcv_store.write([record], tmp_path, _identity(timeframe="1d"))

    def test_write_exchange_mismatch_raises(self, tmp_path: Path) -> None:
        record = make_ohlcv(
            symbol="AAPL",
            asset_class="equity",
            venue="NYSE",
            timeframe="1d",
            source="yahoo",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(OHLCVWriteError, match="venue"):
            ohlcv_store.write([record], tmp_path, _identity())

    def test_write_provider_mismatch_raises(self, tmp_path: Path) -> None:
        record = make_ohlcv(
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
            source="polygon",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(OHLCVWriteError, match="source"):
            ohlcv_store.write([record], tmp_path, _identity(provider="yahoo"))

    def test_write_sorts_by_timestamp(self, tmp_path: Path) -> None:
        records = list(reversed(_series(3)))
        identity = _identity()
        ohlcv_store.write(records, tmp_path, identity)
        loaded = ohlcv_store.read(tmp_path, identity)
        timestamps = [r.timestamp for r in loaded]
        assert timestamps == sorted(timestamps)

    def test_write_deduplicates_within_incoming(self, tmp_path: Path) -> None:
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        r1 = _ohlcv_record(0, close=100.0)
        r2 = _ohlcv_record(0, close=200.0)  # same timestamp — last wins
        identity = _identity()
        ohlcv_store.write([r1, r2], tmp_path, identity, merge=False)
        loaded = ohlcv_store.read(tmp_path, identity)
        assert len(loaded) == 1
        assert loaded[0].close == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# merge behaviour
# ---------------------------------------------------------------------------

class TestOHLCVMerge:
    def test_merge_preserves_existing_records(self, tmp_path: Path) -> None:
        identity = _identity()
        ohlcv_store.write(_series(3), tmp_path, identity)
        new_record = _ohlcv_record(offset_hours=10, close=999.0)
        ohlcv_store.write([new_record], tmp_path, identity, merge=True)
        loaded = ohlcv_store.read(tmp_path, identity)
        assert len(loaded) == 4

    def test_merge_incoming_wins_on_collision(self, tmp_path: Path) -> None:
        identity = _identity()
        original = _ohlcv_record(0, close=100.0)
        ohlcv_store.write([original], tmp_path, identity)
        replacement = _ohlcv_record(0, close=999.0)  # same timestamp
        ohlcv_store.write([replacement], tmp_path, identity, merge=True)
        loaded = ohlcv_store.read(tmp_path, identity)
        assert len(loaded) == 1
        assert loaded[0].close == pytest.approx(999.0)

    def test_no_merge_overwrites_file(self, tmp_path: Path) -> None:
        identity = _identity()
        ohlcv_store.write(_series(5), tmp_path, identity)
        ohlcv_store.write(_series(1), tmp_path, identity, merge=False)
        loaded = ohlcv_store.read(tmp_path, identity)
        assert len(loaded) == 1


# ---------------------------------------------------------------------------
# read()
# ---------------------------------------------------------------------------

class TestOHLCVRead:
    def test_read_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(StorageError):
            ohlcv_store.read(tmp_path, _identity())

    def test_read_returns_normalized_ohlcv_list(self, tmp_path: Path) -> None:
        identity = _identity()
        ohlcv_store.write(_series(3), tmp_path, identity)
        loaded = ohlcv_store.read(tmp_path, identity)
        assert all(isinstance(r, NormalizedOHLCV) for r in loaded)

    def test_read_count_matches_written(self, tmp_path: Path) -> None:
        identity = _identity()
        ohlcv_store.write(_series(4), tmp_path, identity)
        assert len(ohlcv_store.read(tmp_path, identity)) == 4


# ---------------------------------------------------------------------------
# read_range()
# ---------------------------------------------------------------------------

class TestOHLCVReadRange:
    def test_read_range_filters_correctly(self, tmp_path: Path) -> None:
        identity = _identity()
        ohlcv_store.write(_series(5), tmp_path, identity)  # hours 0..4
        start = datetime(2024, 1, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 3, tzinfo=timezone.utc)
        loaded = ohlcv_store.read_range(tmp_path, identity, start, end)
        assert len(loaded) == 3

    def test_read_range_naive_datetime_raises(self, tmp_path: Path) -> None:
        identity = _identity()
        ohlcv_store.write(_series(2), tmp_path, identity)
        naive = datetime(2024, 1, 1)
        with pytest.raises(ValueError, match="timezone-aware"):
            ohlcv_store.read_range(tmp_path, identity, naive, datetime(2024, 1, 2, tzinfo=timezone.utc))


# ---------------------------------------------------------------------------
# Provider isolation guarantee
# ---------------------------------------------------------------------------

class TestProviderIsolation:
    def test_same_instrument_different_providers_stored_separately(self, tmp_path: Path) -> None:
        yahoo = _identity(provider="yahoo")
        polygon = _identity(provider="polygon")

        ohlcv_store.write(_series(3), tmp_path, yahoo)
        ohlcv_store.write(_series(5, source="polygon"), tmp_path, polygon)

        yahoo_loaded = ohlcv_store.read(tmp_path, yahoo)
        polygon_loaded = ohlcv_store.read(tmp_path, polygon)

        assert len(yahoo_loaded) == 3
        assert len(polygon_loaded) == 5

    def test_different_provider_paths_do_not_overlap(self, tmp_path: Path) -> None:
        yahoo = _identity(provider="yahoo")
        polygon = _identity(provider="polygon")
        assert dataset_path(tmp_path, yahoo) != dataset_path(tmp_path, polygon)
