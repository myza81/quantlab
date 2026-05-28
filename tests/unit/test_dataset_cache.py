"""
Tests for Phase 3C — Dataset Cache Architecture.

Covers:
  - DatasetCachePolicy: enum values, str membership
  - DatasetCacheState: class constants
  - DatasetCacheEntry: construction, frozen, all fields present
  - DatasetCacheLookupResult: construction, frozen
  - DatasetCacheRegistry:
      - update writes cache_metadata.json
      - get returns None when absent
      - get returns entry after update
      - created_at preserved across updates
      - fingerprint history rolling (max 10)
      - duplicate fingerprint not duplicated in history
      - lookup: EMPTY when no metadata
      - lookup: HIT when full coverage
      - lookup: PARTIAL when partial coverage
      - lookup: correct missing ranges
      - lookup: naive datetime raises
      - invalidate removes metadata file
      - invalidate is safe when file absent
  - OHLCVService cache policy integration (mocked provider):
      - FETCH_AND_STORE default — cache miss calls provider
      - FETCH_AND_STORE — cache HIT skips provider
      - FETCH_AND_STORE — cache_metadata.json written after fetch
      - READ_ONLY — returns empty when no cache
      - READ_ONLY — returns cached data when available
      - READ_ONLY — never calls provider
      - FORCE_REFRESH — calls provider even when cached
      - FORCE_REFRESH — overwrites storage (merge=False)
      - BYPASS_CACHE — returns data without writing storage
      - BYPASS_CACHE — cache_metadata.json NOT written
      - backward compat: no cache_policy kwarg uses FETCH_AND_STORE
  - Architecture boundary: no yahoo import in cache modules
"""
from __future__ import annotations

import json
from dataclasses import fields as dataclass_fields
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from backend.data.models.cache_policy import DatasetCachePolicy
from backend.data.models.dataset import DatasetIdentity
from backend.data.models.instrument import AdjustmentMode, Instrument
from backend.data.schemas import NormalizedOHLCV
from backend.services.ohlcv_service import OHLCVIngestionError, OHLCVService
from backend.storage.dataset_cache import (
    DatasetCacheEntry,
    DatasetCacheLookupResult,
    DatasetCacheRegistry,
    DatasetCacheState,
    _compute_missing_ranges,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_UTC = timezone.utc


def _identity(
    symbol: str = "AAPL",
    asset_class: str = "equity",
    exchange: str = "NASDAQ",
    provider: str = "yahoo",
    timeframe: str = "1d",
    adjustment_mode: AdjustmentMode = AdjustmentMode.ADJUSTED,
) -> DatasetIdentity:
    return DatasetIdentity(
        instrument=Instrument(symbol=symbol, asset_class=asset_class, exchange=exchange),
        provider=provider,
        timeframe=timeframe,
        adjustment_mode=adjustment_mode,
    )


def _record(ts: str, close: float = 100.0) -> NormalizedOHLCV:
    return NormalizedOHLCV(
        timestamp=datetime.fromisoformat(ts),
        symbol="AAPL",
        asset_class="equity",
        timeframe="1d",
        venue="NASDAQ",
        source="yahoo",
        open=close - 1,
        high=close + 1,
        low=close - 2,
        close=close,
        volume=1_000_000,
    )


def _records(*ts_prices: tuple) -> list[NormalizedOHLCV]:
    return [_record(ts, price) for ts, price in ts_prices]


# ---------------------------------------------------------------------------
# TestDatasetCachePolicyEnum
# ---------------------------------------------------------------------------

class TestDatasetCachePolicyEnum:
    def test_fetch_and_store_value(self) -> None:
        assert DatasetCachePolicy.FETCH_AND_STORE == "fetch_and_store"

    def test_read_only_value(self) -> None:
        assert DatasetCachePolicy.READ_ONLY == "read_only"

    def test_force_refresh_value(self) -> None:
        assert DatasetCachePolicy.FORCE_REFRESH == "force_refresh"

    def test_bypass_cache_value(self) -> None:
        assert DatasetCachePolicy.BYPASS_CACHE == "bypass_cache"

    def test_is_str_subclass(self) -> None:
        assert isinstance(DatasetCachePolicy.FETCH_AND_STORE, str)

    def test_all_four_members(self) -> None:
        members = {p.value for p in DatasetCachePolicy}
        assert members == {"fetch_and_store", "read_only", "force_refresh", "bypass_cache"}


# ---------------------------------------------------------------------------
# TestDatasetCacheState
# ---------------------------------------------------------------------------

class TestDatasetCacheState:
    def test_empty_constant(self) -> None:
        assert DatasetCacheState.EMPTY == "empty"

    def test_hit_constant(self) -> None:
        assert DatasetCacheState.HIT == "hit"

    def test_partial_constant(self) -> None:
        assert DatasetCacheState.PARTIAL == "partial"


# ---------------------------------------------------------------------------
# TestDatasetCacheEntry
# ---------------------------------------------------------------------------

class TestDatasetCacheEntry:
    def test_frozen(self) -> None:
        now = datetime.now(tz=_UTC)
        entry = DatasetCacheEntry(
            dataset_id="ds",
            storage_path="/path",
            record_count=10,
            earliest_ts=now,
            latest_ts=now,
            created_at=now,
            last_refreshed_at=now,
            last_fetch_fingerprint="fp",
            fetch_fingerprints=["fp"],
        )
        with pytest.raises(Exception):
            entry.record_count = 99  # type: ignore[misc]

    def test_all_fields_accessible(self) -> None:
        now = datetime.now(tz=_UTC)
        entry = DatasetCacheEntry(
            dataset_id="equity__NASDAQ__AAPL__yahoo__1d__adjusted",
            storage_path="/data/yahoo/equity/NASDAQ/AAPL/1d/adjusted/data.parquet",
            record_count=250,
            earliest_ts=datetime(2023, 1, 1, tzinfo=_UTC),
            latest_ts=datetime(2023, 12, 31, tzinfo=_UTC),
            created_at=now,
            last_refreshed_at=now,
            last_fetch_fingerprint="abc" * 21 + "a",
            fetch_fingerprints=["abc" * 21 + "a"],
        )
        assert entry.dataset_id == "equity__NASDAQ__AAPL__yahoo__1d__adjusted"
        assert entry.record_count == 250
        assert entry.earliest_ts == datetime(2023, 1, 1, tzinfo=_UTC)
        assert entry.last_fetch_fingerprint is not None

    def test_optional_fields_accept_none(self) -> None:
        now = datetime.now(tz=_UTC)
        entry = DatasetCacheEntry(
            dataset_id="ds",
            storage_path="/path",
            record_count=0,
            earliest_ts=None,
            latest_ts=None,
            created_at=now,
            last_refreshed_at=now,
            last_fetch_fingerprint=None,
        )
        assert entry.earliest_ts is None
        assert entry.latest_ts is None
        assert entry.last_fetch_fingerprint is None
        assert entry.fetch_fingerprints == []


# ---------------------------------------------------------------------------
# TestDatasetCacheLookupResult
# ---------------------------------------------------------------------------

class TestDatasetCacheLookupResult:
    def test_frozen(self) -> None:
        result = DatasetCacheLookupResult(
            state=DatasetCacheState.EMPTY,
            missing_ranges=[],
            entry=None,
        )
        with pytest.raises(Exception):
            result.state = DatasetCacheState.HIT  # type: ignore[misc]

    def test_fields_accessible(self) -> None:
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 6, 30, tzinfo=_UTC)
        result = DatasetCacheLookupResult(
            state=DatasetCacheState.PARTIAL,
            missing_ranges=[(start, end)],
            entry=None,
        )
        assert result.state == DatasetCacheState.PARTIAL
        assert len(result.missing_ranges) == 1


# ---------------------------------------------------------------------------
# TestDatasetCacheRegistry
# ---------------------------------------------------------------------------

class TestDatasetCacheRegistry:
    def test_get_returns_none_when_absent(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        assert reg.get(_identity()) is None

    def test_update_creates_cache_file(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        reg.update(_identity(), recs, "data.parquet")
        # File should exist
        from backend.storage.ohlcv_store import dataset_path
        cache_path = dataset_path(tmp_path, _identity()).parent / "cache_metadata.json"
        assert cache_path.exists()

    def test_update_returns_entry(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        entry = reg.update(_identity(), recs, "data.parquet")
        assert isinstance(entry, DatasetCacheEntry)

    def test_get_returns_entry_after_update(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        reg.update(_identity(), recs, "data.parquet")
        entry = reg.get(_identity())
        assert entry is not None
        assert entry.dataset_id == _identity().dataset_id

    def test_record_count_stored(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        recs = _records(
            ("2023-01-03T00:00:00+00:00", 100.0),
            ("2023-01-04T00:00:00+00:00", 101.0),
        )
        entry = reg.update(_identity(), recs, "data.parquet")
        assert entry.record_count == 2

    def test_earliest_latest_ts_stored(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        recs = _records(
            ("2023-01-03T00:00:00+00:00", 100.0),
            ("2023-01-05T00:00:00+00:00", 102.0),
        )
        entry = reg.update(_identity(), recs, "data.parquet")
        assert entry.earliest_ts == datetime(2023, 1, 3, tzinfo=_UTC)
        assert entry.latest_ts == datetime(2023, 1, 5, tzinfo=_UTC)

    def test_created_at_preserved_on_second_update(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        recs1 = _records(("2023-01-03T00:00:00+00:00", 100.0))
        entry1 = reg.update(_identity(), recs1, "data.parquet")
        recs2 = _records(("2023-01-04T00:00:00+00:00", 101.0))
        entry2 = reg.update(_identity(), recs2, "data.parquet")
        assert entry2.created_at == entry1.created_at

    def test_fingerprint_stored_in_entry(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        entry = reg.update(_identity(), recs, "data.parquet", fingerprint="fp123")
        assert entry.last_fetch_fingerprint == "fp123"
        assert "fp123" in entry.fetch_fingerprints

    def test_fingerprint_history_accumulates(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        reg.update(_identity(), recs, "data.parquet", fingerprint="fp1")
        entry = reg.update(_identity(), recs, "data.parquet", fingerprint="fp2")
        assert "fp1" in entry.fetch_fingerprints
        assert "fp2" in entry.fetch_fingerprints
        assert entry.fetch_fingerprints[0] == "fp2"

    def test_fingerprint_history_max_10(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        for i in range(15):
            reg.update(_identity(), recs, "data.parquet", fingerprint=f"fp{i:02d}")
        entry = reg.get(_identity())
        assert entry is not None
        assert len(entry.fetch_fingerprints) == 10

    def test_duplicate_fingerprint_not_duplicated(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        reg.update(_identity(), recs, "data.parquet", fingerprint="same_fp")
        entry = reg.update(_identity(), recs, "data.parquet", fingerprint="same_fp")
        assert entry.fetch_fingerprints.count("same_fp") == 1

    def test_update_without_fingerprint_preserves_history(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        reg.update(_identity(), recs, "data.parquet", fingerprint="fp_old")
        entry = reg.update(_identity(), recs, "data.parquet", fingerprint=None)
        assert "fp_old" in entry.fetch_fingerprints

    def test_update_empty_records_raises(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        with pytest.raises(ValueError, match="empty"):
            reg.update(_identity(), [], "data.parquet")

    def test_invalidate_removes_file(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        reg.update(_identity(), recs, "data.parquet")
        assert reg.get(_identity()) is not None
        reg.invalidate(_identity())
        assert reg.get(_identity()) is None

    def test_invalidate_is_safe_when_absent(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        reg.invalidate(_identity())  # must not raise

    def test_storage_path_stored(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        entry = reg.update(_identity(), recs, "/custom/path/data.parquet")
        assert entry.storage_path == "/custom/path/data.parquet"

    def test_json_file_contains_expected_keys(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        reg.update(_identity(), recs, "data.parquet", fingerprint="fp")
        from backend.storage.ohlcv_store import dataset_path
        cache_path = dataset_path(tmp_path, _identity()).parent / "cache_metadata.json"
        data = json.loads(cache_path.read_text())
        for key in (
            "dataset_id", "storage_path", "record_count",
            "earliest_ts", "latest_ts", "created_at", "last_refreshed_at",
            "last_fetch_fingerprint", "fetch_fingerprints",
        ):
            assert key in data, f"missing key: {key}"


# ---------------------------------------------------------------------------
# TestDatasetCacheRegistryLookup
# ---------------------------------------------------------------------------

class TestDatasetCacheRegistryLookup:
    def test_lookup_empty_when_no_metadata(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 6, 30, tzinfo=_UTC)
        result = reg.lookup(_identity(), start, end)
        assert result.state == DatasetCacheState.EMPTY

    def test_lookup_empty_missing_range_is_full_request(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 6, 30, tzinfo=_UTC)
        result = reg.lookup(_identity(), start, end)
        assert result.missing_ranges == [(start, end)]

    def test_lookup_hit_when_full_coverage(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        recs = _records(
            ("2022-12-01T00:00:00+00:00", 98.0),
            ("2023-08-01T00:00:00+00:00", 105.0),
        )
        reg.update(_identity(), recs, "data.parquet")
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 6, 30, tzinfo=_UTC)
        result = reg.lookup(_identity(), start, end)
        assert result.state == DatasetCacheState.HIT
        assert result.missing_ranges == []

    def test_lookup_hit_entry_is_populated(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        recs = _records(("2022-12-01T00:00:00+00:00", 98.0))
        reg.update(_identity(), recs, "data.parquet")
        start = datetime(2022, 12, 1, tzinfo=_UTC)
        end = datetime(2022, 12, 1, tzinfo=_UTC)
        result = reg.lookup(_identity(), start, end)
        assert result.entry is not None

    def test_lookup_partial_when_missing_start(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        # Cache covers 2023-06 onward
        recs = _records(
            ("2023-06-01T00:00:00+00:00", 100.0),
            ("2023-12-31T00:00:00+00:00", 110.0),
        )
        reg.update(_identity(), recs, "data.parquet")
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 12, 31, tzinfo=_UTC)
        result = reg.lookup(_identity(), start, end)
        assert result.state == DatasetCacheState.PARTIAL
        assert len(result.missing_ranges) >= 1
        # Missing range must start at or after `start`
        assert result.missing_ranges[0][0] == start

    def test_lookup_partial_when_missing_end(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        # Cache covers up to 2023-06
        recs = _records(
            ("2023-01-01T00:00:00+00:00", 100.0),
            ("2023-06-30T00:00:00+00:00", 105.0),
        )
        reg.update(_identity(), recs, "data.parquet")
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 12, 31, tzinfo=_UTC)
        result = reg.lookup(_identity(), start, end)
        assert result.state == DatasetCacheState.PARTIAL
        assert any(r[1] == end for r in result.missing_ranges)

    def test_lookup_naive_start_raises(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        with pytest.raises(ValueError, match="timezone-aware"):
            reg.lookup(_identity(), datetime(2023, 1, 1), datetime(2023, 6, 30, tzinfo=_UTC))

    def test_lookup_naive_end_raises(self, tmp_path: Path) -> None:
        reg = DatasetCacheRegistry(tmp_path)
        with pytest.raises(ValueError, match="timezone-aware"):
            reg.lookup(_identity(), datetime(2023, 1, 1, tzinfo=_UTC), datetime(2023, 6, 30))


# ---------------------------------------------------------------------------
# TestComputeMissingRangesHelper
# ---------------------------------------------------------------------------

class TestComputeMissingRangesHelper:
    def _entry(self, earliest: str, latest: str) -> DatasetCacheEntry:
        now = datetime.now(tz=_UTC)
        return DatasetCacheEntry(
            dataset_id="ds",
            storage_path="/path",
            record_count=1,
            earliest_ts=datetime.fromisoformat(earliest),
            latest_ts=datetime.fromisoformat(latest),
            created_at=now,
            last_refreshed_at=now,
            last_fetch_fingerprint=None,
        )

    def test_no_gap_when_fully_covered(self) -> None:
        entry = self._entry("2023-01-01T00:00:00+00:00", "2023-12-31T00:00:00+00:00")
        start = datetime(2023, 3, 1, tzinfo=_UTC)
        end = datetime(2023, 9, 30, tzinfo=_UTC)
        assert _compute_missing_ranges(entry, start, end) == []

    def test_gap_before_coverage(self) -> None:
        entry = self._entry("2023-06-01T00:00:00+00:00", "2023-12-31T00:00:00+00:00")
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 12, 31, tzinfo=_UTC)
        gaps = _compute_missing_ranges(entry, start, end)
        assert any(g[0] == start for g in gaps)

    def test_gap_after_coverage(self) -> None:
        entry = self._entry("2023-01-01T00:00:00+00:00", "2023-06-30T00:00:00+00:00")
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 12, 31, tzinfo=_UTC)
        gaps = _compute_missing_ranges(entry, start, end)
        assert any(g[1] == end for g in gaps)

    def test_gaps_both_sides(self) -> None:
        entry = self._entry("2023-04-01T00:00:00+00:00", "2023-09-30T00:00:00+00:00")
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 12, 31, tzinfo=_UTC)
        gaps = _compute_missing_ranges(entry, start, end)
        assert len(gaps) == 2

    def test_null_timestamps_returns_full_range(self) -> None:
        now = datetime.now(tz=_UTC)
        entry = DatasetCacheEntry(
            dataset_id="ds", storage_path="/p", record_count=0,
            earliest_ts=None, latest_ts=None,
            created_at=now, last_refreshed_at=now, last_fetch_fingerprint=None,
        )
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 12, 31, tzinfo=_UTC)
        gaps = _compute_missing_ranges(entry, start, end)
        assert gaps == [(start, end)]


# ---------------------------------------------------------------------------
# TestOHLCVServiceCachePolicy (mocked provider)
# ---------------------------------------------------------------------------

def _make_provider(records: list[NormalizedOHLCV]) -> MagicMock:
    provider = MagicMock()
    provider.fetch.return_value = records
    return provider


def _make_service(tmp_path: Path) -> OHLCVService:
    return OHLCVService(tmp_path)


class TestOHLCVServiceCachePolicy:
    def test_fetch_and_store_calls_provider_on_cache_miss(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        ident = _identity()
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        provider = _make_provider(recs)
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 1, 31, tzinfo=_UTC)
        svc.get_ohlcv(ident, start, end, provider,
                      cache_policy=DatasetCachePolicy.FETCH_AND_STORE)
        provider.fetch.assert_called()

    def test_fetch_and_store_skips_provider_on_cache_hit(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        ident = _identity()
        # Seed the cache with a wide range
        recs = _records(
            ("2022-12-01T00:00:00+00:00", 99.0),
            ("2023-03-01T00:00:00+00:00", 101.0),
        )
        provider = _make_provider(recs)
        wide_start = datetime(2022, 12, 1, tzinfo=_UTC)
        wide_end = datetime(2023, 3, 1, tzinfo=_UTC)
        svc.get_ohlcv(ident, wide_start, wide_end, provider)

        # Second call within cached range — provider should NOT be called again
        provider.fetch.reset_mock()
        narrow_start = datetime(2023, 1, 1, tzinfo=_UTC)
        narrow_end = datetime(2023, 2, 1, tzinfo=_UTC)
        svc.get_ohlcv(ident, narrow_start, narrow_end, provider)
        provider.fetch.assert_not_called()

    def test_fetch_and_store_writes_cache_metadata(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        ident = _identity()
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        provider = _make_provider(recs)
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 1, 31, tzinfo=_UTC)
        svc.get_ohlcv(ident, start, end, provider,
                      cache_policy=DatasetCachePolicy.FETCH_AND_STORE,
                      fetch_fingerprint="test_fp")
        cache_reg = DatasetCacheRegistry(tmp_path)
        entry = cache_reg.get(ident)
        assert entry is not None
        assert entry.record_count >= 1

    def test_fetch_and_store_stores_fingerprint(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        ident = _identity()
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        provider = _make_provider(recs)
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 1, 31, tzinfo=_UTC)
        svc.get_ohlcv(ident, start, end, provider,
                      fetch_fingerprint="my_fingerprint")
        entry = DatasetCacheRegistry(tmp_path).get(ident)
        assert entry is not None
        assert "my_fingerprint" in entry.fetch_fingerprints

    def test_read_only_returns_empty_when_no_cache(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        ident = _identity()
        provider = _make_provider([])
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 1, 31, tzinfo=_UTC)
        result = svc.get_ohlcv(ident, start, end, provider,
                               cache_policy=DatasetCachePolicy.READ_ONLY)
        assert result == []

    def test_read_only_never_calls_provider(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        ident = _identity()
        provider = _make_provider([])
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 1, 31, tzinfo=_UTC)
        svc.get_ohlcv(ident, start, end, provider,
                      cache_policy=DatasetCachePolicy.READ_ONLY)
        provider.fetch.assert_not_called()

    def test_read_only_returns_cached_data(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        ident = _identity()
        # First, populate cache with FETCH_AND_STORE
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        provider = _make_provider(recs)
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 1, 31, tzinfo=_UTC)
        svc.get_ohlcv(ident, start, end, provider)

        # Now fetch READ_ONLY
        ro_provider = _make_provider([])
        result = svc.get_ohlcv(ident, start, end, ro_provider,
                               cache_policy=DatasetCachePolicy.READ_ONLY)
        assert len(result) == 1
        ro_provider.fetch.assert_not_called()

    def test_force_refresh_calls_provider_when_cached(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        ident = _identity()
        # Populate cache
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        provider = _make_provider(recs)
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 1, 31, tzinfo=_UTC)
        svc.get_ohlcv(ident, start, end, provider)

        # Force refresh
        new_recs = _records(("2023-01-03T00:00:00+00:00", 105.0))
        fresh_provider = _make_provider(new_recs)
        svc.get_ohlcv(ident, start, end, fresh_provider,
                      cache_policy=DatasetCachePolicy.FORCE_REFRESH)
        fresh_provider.fetch.assert_called_once()

    def test_force_refresh_overwrites_data(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        ident = _identity()
        # Seed with old data
        old_recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        svc.get_ohlcv(ident,
                      datetime(2023, 1, 1, tzinfo=_UTC),
                      datetime(2023, 1, 31, tzinfo=_UTC),
                      _make_provider(old_recs))

        # Force refresh with new data
        new_recs = _records(("2023-01-03T00:00:00+00:00", 999.0))
        svc.get_ohlcv(ident,
                      datetime(2023, 1, 1, tzinfo=_UTC),
                      datetime(2023, 1, 31, tzinfo=_UTC),
                      _make_provider(new_recs),
                      cache_policy=DatasetCachePolicy.FORCE_REFRESH)

        result = svc.get_ohlcv(ident,
                               datetime(2023, 1, 1, tzinfo=_UTC),
                               datetime(2023, 1, 31, tzinfo=_UTC),
                               _make_provider([]),
                               cache_policy=DatasetCachePolicy.READ_ONLY)
        assert len(result) == 1
        assert result[0].close == 999.0

    def test_bypass_cache_returns_provider_data(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        ident = _identity()
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        provider = _make_provider(recs)
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 1, 31, tzinfo=_UTC)
        result = svc.get_ohlcv(ident, start, end, provider,
                               cache_policy=DatasetCachePolicy.BYPASS_CACHE)
        assert len(result) == 1
        assert result[0].close == 100.0

    def test_bypass_cache_does_not_write_storage(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        ident = _identity()
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        provider = _make_provider(recs)
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 1, 31, tzinfo=_UTC)
        svc.get_ohlcv(ident, start, end, provider,
                      cache_policy=DatasetCachePolicy.BYPASS_CACHE)
        # READ_ONLY should see nothing
        result = svc.get_ohlcv(ident, start, end, _make_provider([]),
                               cache_policy=DatasetCachePolicy.READ_ONLY)
        assert result == []

    def test_bypass_cache_does_not_write_cache_metadata(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        ident = _identity()
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        provider = _make_provider(recs)
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 1, 31, tzinfo=_UTC)
        svc.get_ohlcv(ident, start, end, provider,
                      cache_policy=DatasetCachePolicy.BYPASS_CACHE)
        assert DatasetCacheRegistry(tmp_path).get(ident) is None

    def test_bypass_cache_returns_empty_when_provider_returns_empty(
        self, tmp_path: Path
    ) -> None:
        svc = _make_service(tmp_path)
        ident = _identity()
        provider = _make_provider([])
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 1, 31, tzinfo=_UTC)
        result = svc.get_ohlcv(ident, start, end, provider,
                               cache_policy=DatasetCachePolicy.BYPASS_CACHE)
        assert result == []


# ---------------------------------------------------------------------------
# TestOHLCVServiceBackwardCompat
# ---------------------------------------------------------------------------

class TestOHLCVServiceBackwardCompat:
    def test_no_cache_policy_kwarg_uses_fetch_and_store(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        ident = _identity()
        recs = _records(("2023-01-03T00:00:00+00:00", 100.0))
        provider = _make_provider(recs)
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 1, 31, tzinfo=_UTC)
        # Original signature: no cache_policy arg
        result = svc.get_ohlcv(ident, start, end, provider)
        assert isinstance(result, list)
        provider.fetch.assert_called()

    def test_original_ohlcv_service_behavior_preserved(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        ident = _identity()
        recs = _records(("2023-01-03T00:00:00+00:00", 150.0))
        provider = _make_provider(recs)
        start = datetime(2023, 1, 1, tzinfo=_UTC)
        end = datetime(2023, 1, 31, tzinfo=_UTC)
        result = svc.get_ohlcv(ident, start, end, provider)
        assert len(result) == 1
        assert result[0].close == 150.0

    def test_naive_datetimes_still_raise(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path)
        ident = _identity()
        provider = _make_provider([])
        with pytest.raises(ValueError, match="timezone-aware"):
            svc.get_ohlcv(ident, datetime(2023, 1, 1), datetime(2023, 1, 31, tzinfo=_UTC),
                          provider)


# ---------------------------------------------------------------------------
# TestArchitectureBoundary
# ---------------------------------------------------------------------------

class TestArchitectureBoundary:
    def test_cache_policy_no_yahoo_import(self) -> None:
        import ast
        import pathlib
        src = pathlib.Path("backend/data/models/cache_policy.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "yahoo" not in node.module

    def test_dataset_cache_no_yahoo_import(self) -> None:
        import ast
        import pathlib
        src = pathlib.Path("backend/storage/dataset_cache.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "yahoo" not in node.module

    def test_dataset_cache_no_api_import(self) -> None:
        import ast
        import pathlib
        src = pathlib.Path("backend/storage/dataset_cache.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = node.module.split(".")
                assert "api" not in parts, f"dataset_cache must not import from api layer; found: {node.module}"

    def test_ohlcv_service_no_yahoo_import(self) -> None:
        import ast
        import pathlib
        src = pathlib.Path("backend/services/ohlcv_service.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "yahoo" not in node.module
