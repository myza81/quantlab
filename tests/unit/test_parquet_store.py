"""Tests for backend/storage/parquet_store.py — Parquet write/read round-trip."""
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.data.schemas import NormalizedOHLCV
from backend.storage.parquet_store import StorageError, dataset_path, read, write
from tests.conftest import make_ohlcv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _series(n: int = 3, **overrides) -> list[NormalizedOHLCV]:
    """Return a list of n records with incrementing hourly timestamps."""
    return [
        make_ohlcv(
            timestamp=datetime(2024, 1, 1, i, 0, 0, tzinfo=timezone.utc),
            **overrides,
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# dataset_path
# ---------------------------------------------------------------------------

class TestDatasetPath:
    def test_canonical_path_structure(self, tmp_path: Path) -> None:
        p = dataset_path(tmp_path, "crypto", "BTCUSDT", "1h")
        assert p == tmp_path / "crypto" / "BTCUSDT" / "1h" / "data.parquet"

    def test_path_does_not_create_dirs(self, tmp_path: Path) -> None:
        p = dataset_path(tmp_path, "crypto", "BTCUSDT", "1h")
        assert not p.exists()


# ---------------------------------------------------------------------------
# write()
# ---------------------------------------------------------------------------

class TestParquetWrite:
    def test_write_creates_parquet_file(self, tmp_path: Path) -> None:
        records = _series()
        out = write(records, tmp_path)
        assert out.exists()
        assert out.suffix == ".parquet"

    def test_write_returns_canonical_path(self, tmp_path: Path) -> None:
        records = _series()
        out = write(records, tmp_path)
        expected = dataset_path(tmp_path, "crypto", "BTCUSDT", "1h")
        assert out == expected

    def test_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        records = _series(asset_class="equities", symbol="AAPL", timeframe="1d")
        out = write(records, tmp_path)
        assert out.parent.exists()

    def test_write_empty_list_raises(self, tmp_path: Path) -> None:
        with pytest.raises(StorageError, match="empty"):
            write([], tmp_path)

    def test_write_inconsistent_symbol_raises(self, tmp_path: Path) -> None:
        records = [make_ohlcv(symbol="BTCUSDT"), make_ohlcv(symbol="ETHUSDT")]
        with pytest.raises(StorageError, match="symbol"):
            write(records, tmp_path)

    def test_write_inconsistent_asset_class_raises(self, tmp_path: Path) -> None:
        records = [
            make_ohlcv(asset_class="crypto"),
            make_ohlcv(asset_class="equities"),
        ]
        with pytest.raises(StorageError, match="asset_class"):
            write(records, tmp_path)

    def test_write_inconsistent_venue_raises(self, tmp_path: Path) -> None:
        records = [make_ohlcv(venue="binance"), make_ohlcv(venue="coinbase")]
        with pytest.raises(StorageError, match="venue"):
            write(records, tmp_path)

    def test_write_inconsistent_timeframe_raises(self, tmp_path: Path) -> None:
        records = [make_ohlcv(timeframe="1h"), make_ohlcv(timeframe="1d")]
        with pytest.raises(StorageError, match="timeframe"):
            write(records, tmp_path)

    def test_write_overwrites_existing_file(self, tmp_path: Path) -> None:
        write(_series(n=3), tmp_path)
        write(_series(n=1), tmp_path)  # should not raise
        loaded = read(tmp_path, "crypto", "BTCUSDT", "1h")
        assert len(loaded) == 1


# ---------------------------------------------------------------------------
# read()
# ---------------------------------------------------------------------------

class TestParquetRead:
    def test_read_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(StorageError, match="not found"):
            read(tmp_path, "crypto", "BTCUSDT", "1h")

    def test_read_returns_list_of_normalized_ohlcv(self, tmp_path: Path) -> None:
        write(_series(), tmp_path)
        loaded = read(tmp_path, "crypto", "BTCUSDT", "1h")
        assert all(isinstance(r, NormalizedOHLCV) for r in loaded)

    def test_read_count_matches_written(self, tmp_path: Path) -> None:
        write(_series(n=5), tmp_path)
        loaded = read(tmp_path, "crypto", "BTCUSDT", "1h")
        assert len(loaded) == 5


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_scalar_fields_preserved(self, tmp_path: Path) -> None:
        original = make_ohlcv()
        write([original], tmp_path)
        [loaded] = read(tmp_path, "crypto", "BTCUSDT", "1h")

        assert loaded.symbol == original.symbol
        assert loaded.asset_class == original.asset_class
        assert loaded.venue == original.venue
        assert loaded.timeframe == original.timeframe
        assert loaded.source == original.source
        assert loaded.open == pytest.approx(original.open)
        assert loaded.high == pytest.approx(original.high)
        assert loaded.low == pytest.approx(original.low)
        assert loaded.close == pytest.approx(original.close)
        assert loaded.volume == pytest.approx(original.volume)

    def test_timestamp_roundtrip_is_utc(self, tmp_path: Path) -> None:
        ts = datetime(2024, 6, 15, 12, 30, 0, tzinfo=timezone.utc)
        write([make_ohlcv(timestamp=ts)], tmp_path)
        [loaded] = read(tmp_path, "crypto", "BTCUSDT", "1h")
        assert loaded.timestamp == ts
        assert loaded.timestamp.tzinfo == timezone.utc

    def test_optional_fields_none_by_default(self, tmp_path: Path) -> None:
        write([make_ohlcv()], tmp_path)
        [loaded] = read(tmp_path, "crypto", "BTCUSDT", "1h")
        assert loaded.trade_count is None
        assert loaded.vwap is None
        assert loaded.bid is None
        assert loaded.ask is None
        assert loaded.spread is None
        assert loaded.adjustment_factor is None
        assert loaded.metadata is None

    def test_optional_numeric_fields_preserved(self, tmp_path: Path) -> None:
        record = make_ohlcv(
            trade_count=500,
            vwap=42100.0,
            bid=42090.0,
            ask=42110.0,
            spread=20.0,
            adjustment_factor=1.0,
        )
        write([record], tmp_path)
        [loaded] = read(tmp_path, "crypto", "BTCUSDT", "1h")
        assert loaded.trade_count == 500
        assert loaded.vwap == pytest.approx(42100.0)
        assert loaded.bid == pytest.approx(42090.0)
        assert loaded.ask == pytest.approx(42110.0)
        assert loaded.spread == pytest.approx(20.0)
        assert loaded.adjustment_factor == pytest.approx(1.0)

    def test_metadata_dict_preserved(self, tmp_path: Path) -> None:
        meta = {"provider_id": "cb_1234", "adj": True}
        write([make_ohlcv(metadata=meta)], tmp_path)
        [loaded] = read(tmp_path, "crypto", "BTCUSDT", "1h")
        assert loaded.metadata == meta

    def test_series_order_preserved(self, tmp_path: Path) -> None:
        series = _series(n=4)
        write(series, tmp_path)
        loaded = read(tmp_path, "crypto", "BTCUSDT", "1h")
        for orig, load in zip(series, loaded):
            assert orig.timestamp == load.timestamp

    def test_roundtrip_validates_as_normalized_ohlcv(self, tmp_path: Path) -> None:
        """Loaded records must pass NormalizedOHLCV schema validation (already done by read())."""
        write(_series(), tmp_path)
        loaded = read(tmp_path, "crypto", "BTCUSDT", "1h")
        for rec in loaded:
            # Re-instantiation would raise ValidationError if invalid
            NormalizedOHLCV(**rec.model_dump())
