"""
Tests for backend/services/ohlcv_service.py — OHLCV retrieval orchestration.

Covers:
  - full miss: no local data, provider called, data persisted and returned
  - full overlap: local data covers requested window, provider NOT called
  - leading partial overlap: only pre-coverage window fetched
  - trailing partial overlap: only post-coverage window fetched
  - provider returns empty: no crash, empty slice returned
  - duplicate ingestion: same candles written twice, no duplicates in storage
  - provider isolation: different providers → different files, independent coverage
  - coverage updates correctly after ingestion
  - returned slice is bounded to [start, end], not the full dataset
  - normalization error propagates as OHLCVIngestionError
  - naive datetime bounds rejected
  - CSVAdapter.fetch() range filtering
  - calculate_missing_ranges() delegation
  MD-1 hardening:
  - _EmptyResponseGuard: unguarded/guarded/expired/different-gap/prevents-double-call
  - _trailing_edge_is_stale: finalized/unfinalized unit; integration stale+settled
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from backend.data.models.dataset import DatasetIdentity
from backend.data.models.instrument import Instrument
from backend.data.schemas import NormalizedOHLCV
from backend.data_providers.csv_adapter import CSVAdapter, CSVAdapterConfig
from backend.data_providers.range_provider import RangeProviderAdapter
from backend.services.ohlcv_service import (
    OHLCVIngestionError,
    OHLCVService,
    _EmptyResponseGuard,
    _EMPTY_RESPONSE_TTL_SECONDS,
)
from backend.storage.coverage_registry import CoverageRegistry
from backend.storage import ohlcv_store
from tests.conftest import make_ohlcv


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def _instrument() -> Instrument:
    return Instrument(symbol="AAPL", asset_class="equity", exchange="NASDAQ")


def _identity(provider: str = "stub") -> DatasetIdentity:
    return DatasetIdentity(
        instrument=_instrument(),
        provider=provider,
        timeframe="1d",
    )


def _record(day: int, *, provider: str = "stub", close: float = 150.0) -> NormalizedOHLCV:
    """Return a NormalizedOHLCV for 2024-01-{day} matching the default identity."""
    return make_ohlcv(
        symbol="AAPL",
        asset_class="equity",
        venue="NASDAQ",
        timeframe="1d",
        source=provider,
        timestamp=_utc(2024, 1, day),
        open=148.0,
        high=155.0,
        low=145.0,
        close=close,
        volume=1_000_000.0,
    )


def _days(first: int, last: int, *, provider: str = "stub") -> list[NormalizedOHLCV]:
    """Return a monotonic series from day `first` to `last` inclusive."""
    return [_record(d, provider=provider) for d in range(first, last + 1)]


# ---------------------------------------------------------------------------
# Stub provider — controllable, call-tracking
# ---------------------------------------------------------------------------

class _StubProvider(RangeProviderAdapter):
    """
    In-memory provider stub backed by a fixed list of NormalizedOHLCV records.

    fetch() filters to [start, end] and records every call for assertion.
    """

    def __init__(self, records: list[NormalizedOHLCV]) -> None:
        self._all = records
        self.fetch_calls: list[tuple[datetime, datetime]] = []

    @property
    def provider_name(self) -> str:
        return "stub"

    def load(self, **kwargs: Any) -> list[NormalizedOHLCV]:
        return self._all

    def fetch(self, start: datetime, end: datetime, **kwargs: Any) -> list[NormalizedOHLCV]:
        self.fetch_calls.append((start, end))
        return [r for r in self._all if start <= r.timestamp <= end]


class _EmptyProvider(_StubProvider):
    """Provider that always returns an empty list."""

    def __init__(self) -> None:
        super().__init__([])


class _BadRecordProvider(RangeProviderAdapter):
    """Provider that returns records with duplicate timestamps (fails normalization)."""

    @property
    def provider_name(self) -> str:
        return "stub"

    def load(self, **kwargs: Any) -> list[NormalizedOHLCV]:
        return []

    def fetch(self, _start: datetime, _end: datetime, **kwargs: Any) -> list[NormalizedOHLCV]:
        r = _record(5)
        return [r, r]  # duplicate timestamp → normalization error


# ---------------------------------------------------------------------------
# Full miss — no local data
# ---------------------------------------------------------------------------

class TestFullMiss:
    def test_provider_called_when_no_local_data(self, tmp_path: Path) -> None:
        provider = _StubProvider(_days(1, 10))
        service = OHLCVService(tmp_path)
        identity = _identity()
        service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 10), provider)
        assert len(provider.fetch_calls) == 1

    def test_full_miss_returns_records(self, tmp_path: Path) -> None:
        provider = _StubProvider(_days(1, 10))
        service = OHLCVService(tmp_path)
        identity = _identity()
        result = service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 10), provider)
        assert len(result) == 10

    def test_full_miss_persists_to_parquet(self, tmp_path: Path) -> None:
        provider = _StubProvider(_days(1, 5))
        service = OHLCVService(tmp_path)
        identity = _identity()
        service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 5), provider)
        stored = ohlcv_store.read(tmp_path, identity)
        assert len(stored) == 5

    def test_full_miss_updates_coverage(self, tmp_path: Path) -> None:
        provider = _StubProvider(_days(1, 5))
        service = OHLCVService(tmp_path)
        identity = _identity()
        service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 5), provider)
        coverage = CoverageRegistry(tmp_path).get(identity)
        assert coverage is not None
        assert coverage.earliest_timestamp == _utc(2024, 1, 1)
        assert coverage.latest_timestamp == _utc(2024, 1, 5)

    def test_full_miss_returns_only_requested_slice(self, tmp_path: Path) -> None:
        # Provider has data Jan 1-20; request Jan 5-10
        provider = _StubProvider(_days(1, 20))
        service = OHLCVService(tmp_path)
        identity = _identity()
        result = service.get_ohlcv(identity, _utc(2024, 1, 5), _utc(2024, 1, 10), provider)
        timestamps = [r.timestamp for r in result]
        assert all(_utc(2024, 1, 5) <= ts <= _utc(2024, 1, 10) for ts in timestamps)
        assert len(result) == 6


# ---------------------------------------------------------------------------
# Full overlap — local data covers the entire requested window
# ---------------------------------------------------------------------------

class TestFullOverlap:
    def test_provider_not_called_when_fully_covered(self, tmp_path: Path) -> None:
        identity = _identity()
        # Pre-populate storage
        ohlcv_store.write(_days(1, 10), tmp_path, identity)
        CoverageRegistry(tmp_path).update(identity, _days(1, 10))

        provider = _StubProvider(_days(1, 10))
        service = OHLCVService(tmp_path)
        service.get_ohlcv(identity, _utc(2024, 1, 3), _utc(2024, 1, 7), provider)
        assert provider.fetch_calls == []

    def test_full_overlap_returns_correct_slice(self, tmp_path: Path) -> None:
        identity = _identity()
        ohlcv_store.write(_days(1, 10), tmp_path, identity)
        CoverageRegistry(tmp_path).update(identity, _days(1, 10))

        service = OHLCVService(tmp_path)
        result = service.get_ohlcv(
            identity, _utc(2024, 1, 3), _utc(2024, 1, 7), _StubProvider([])
        )
        assert len(result) == 5
        assert result[0].timestamp == _utc(2024, 1, 3)
        assert result[-1].timestamp == _utc(2024, 1, 7)

    def test_full_overlap_returns_all_normalized_ohlcv(self, tmp_path: Path) -> None:
        identity = _identity()
        ohlcv_store.write(_days(1, 5), tmp_path, identity)
        CoverageRegistry(tmp_path).update(identity, _days(1, 5))

        service = OHLCVService(tmp_path)
        result = service.get_ohlcv(
            identity, _utc(2024, 1, 1), _utc(2024, 1, 5), _StubProvider([])
        )
        assert all(isinstance(r, NormalizedOHLCV) for r in result)


# ---------------------------------------------------------------------------
# Partial overlap — leading gap
# ---------------------------------------------------------------------------

class TestLeadingPartialOverlap:
    def test_leading_gap_fetched_only(self, tmp_path: Path) -> None:
        identity = _identity()
        # Local data: Jan 5-10
        ohlcv_store.write(_days(5, 10), tmp_path, identity)
        CoverageRegistry(tmp_path).update(identity, _days(5, 10))

        provider = _StubProvider(_days(1, 10))
        service = OHLCVService(tmp_path)
        service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 10), provider)

        # Provider should be called exactly once, and only for the leading gap
        assert len(provider.fetch_calls) == 1
        gap_start, gap_end = provider.fetch_calls[0]
        assert gap_start <= _utc(2024, 1, 5)

    def test_leading_gap_merged_into_storage(self, tmp_path: Path) -> None:
        identity = _identity()
        ohlcv_store.write(_days(5, 10), tmp_path, identity)
        CoverageRegistry(tmp_path).update(identity, _days(5, 10))

        provider = _StubProvider(_days(1, 10))
        service = OHLCVService(tmp_path)
        service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 10), provider)
        stored = ohlcv_store.read(tmp_path, identity)
        assert len(stored) == 10

    def test_leading_gap_result_includes_all_days(self, tmp_path: Path) -> None:
        identity = _identity()
        ohlcv_store.write(_days(5, 10), tmp_path, identity)
        CoverageRegistry(tmp_path).update(identity, _days(5, 10))

        provider = _StubProvider(_days(1, 10))
        service = OHLCVService(tmp_path)
        result = service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 10), provider)
        assert len(result) == 10


# ---------------------------------------------------------------------------
# Partial overlap — trailing gap
# ---------------------------------------------------------------------------

class TestTrailingPartialOverlap:
    def test_trailing_gap_fetched_only(self, tmp_path: Path) -> None:
        identity = _identity()
        # Local data: Jan 1-5
        ohlcv_store.write(_days(1, 5), tmp_path, identity)
        CoverageRegistry(tmp_path).update(identity, _days(1, 5))

        provider = _StubProvider(_days(1, 10))
        service = OHLCVService(tmp_path)
        service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 10), provider)

        assert len(provider.fetch_calls) == 1
        gap_start, _ = provider.fetch_calls[0]
        assert gap_start >= _utc(2024, 1, 5)

    def test_trailing_gap_merged_into_storage(self, tmp_path: Path) -> None:
        identity = _identity()
        ohlcv_store.write(_days(1, 5), tmp_path, identity)
        CoverageRegistry(tmp_path).update(identity, _days(1, 5))

        provider = _StubProvider(_days(1, 10))
        service = OHLCVService(tmp_path)
        service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 10), provider)
        stored = ohlcv_store.read(tmp_path, identity)
        assert len(stored) == 10

    def test_trailing_gap_coverage_updated(self, tmp_path: Path) -> None:
        identity = _identity()
        ohlcv_store.write(_days(1, 5), tmp_path, identity)
        CoverageRegistry(tmp_path).update(identity, _days(1, 5))

        provider = _StubProvider(_days(1, 10))
        service = OHLCVService(tmp_path)
        service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 10), provider)

        coverage = CoverageRegistry(tmp_path).get(identity)
        assert coverage is not None
        assert coverage.latest_timestamp == _utc(2024, 1, 10)


# ---------------------------------------------------------------------------
# Provider returns empty for the missing window
# ---------------------------------------------------------------------------

class TestProviderReturnsEmpty:
    def test_empty_provider_returns_empty_list(self, tmp_path: Path) -> None:
        service = OHLCVService(tmp_path)
        result = service.get_ohlcv(
            _identity(), _utc(2024, 1, 1), _utc(2024, 1, 5), _EmptyProvider()
        )
        assert result == []

    def test_empty_provider_does_not_crash(self, tmp_path: Path) -> None:
        service = OHLCVService(tmp_path)
        service.get_ohlcv(
            _identity(), _utc(2024, 1, 1), _utc(2024, 1, 5), _EmptyProvider()
        )

    def test_empty_provider_does_not_update_coverage(self, tmp_path: Path) -> None:
        identity = _identity()
        service = OHLCVService(tmp_path)
        service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 5), _EmptyProvider())
        assert CoverageRegistry(tmp_path).get(identity) is None


# ---------------------------------------------------------------------------
# Deduplication — same candles ingested twice
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_second_ingestion_does_not_duplicate_candles(self, tmp_path: Path) -> None:
        provider = _StubProvider(_days(1, 5))
        service = OHLCVService(tmp_path)
        identity = _identity()
        service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 5), provider)
        # Coverage now [Jan 1..Jan 5] so second call for same window is a full-overlap
        # Provider won't be called again — but even if it were, merge deduplicates
        service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 5), provider)
        stored = ohlcv_store.read(tmp_path, identity)
        assert len(stored) == 5

    def test_overlapping_fetch_does_not_duplicate(self, tmp_path: Path) -> None:
        identity = _identity()
        # Pre-populate Jan 1-5
        ohlcv_store.write(_days(1, 5), tmp_path, identity)
        CoverageRegistry(tmp_path).update(identity, _days(1, 5))

        # Fetch Jan 3-8 — overlap Jan 3-5, new Jan 6-8
        provider = _StubProvider(_days(1, 10))
        service = OHLCVService(tmp_path)
        service.get_ohlcv(identity, _utc(2024, 1, 3), _utc(2024, 1, 8), provider)

        stored = ohlcv_store.read(tmp_path, identity)
        timestamps = [r.timestamp for r in stored]
        assert len(timestamps) == len(set(timestamps)), "duplicate timestamps in storage"


# ---------------------------------------------------------------------------
# Provider isolation
# ---------------------------------------------------------------------------

class TestProviderIsolation:
    def test_different_providers_do_not_share_storage(self, tmp_path: Path) -> None:
        yahoo_id = _identity(provider="yahoo")
        polygon_id = _identity(provider="polygon")

        yahoo_records = [_record(d, provider="yahoo") for d in range(1, 6)]
        polygon_records = [_record(d, provider="polygon") for d in range(1, 11)]

        service = OHLCVService(tmp_path)
        service.get_ohlcv(
            yahoo_id, _utc(2024, 1, 1), _utc(2024, 1, 5),
            _StubProvider(yahoo_records),
        )
        service.get_ohlcv(
            polygon_id, _utc(2024, 1, 1), _utc(2024, 1, 10),
            _StubProvider(polygon_records),
        )

        yahoo_stored = ohlcv_store.read(tmp_path, yahoo_id)
        polygon_stored = ohlcv_store.read(tmp_path, polygon_id)

        assert len(yahoo_stored) == 5
        assert len(polygon_stored) == 10

    def test_different_provider_coverage_is_independent(self, tmp_path: Path) -> None:
        yahoo_id = _identity(provider="yahoo")
        polygon_id = _identity(provider="polygon")
        yahoo_records = [_record(d, provider="yahoo") for d in range(1, 4)]

        service = OHLCVService(tmp_path)
        service.get_ohlcv(
            yahoo_id, _utc(2024, 1, 1), _utc(2024, 1, 3),
            _StubProvider(yahoo_records),
        )

        registry = CoverageRegistry(tmp_path)
        assert registry.get(yahoo_id) is not None
        assert registry.get(polygon_id) is None


# ---------------------------------------------------------------------------
# Coverage registry synchronisation
# ---------------------------------------------------------------------------

class TestCoverageSync:
    def test_coverage_reflects_full_stored_range_after_partial_fills(self, tmp_path: Path) -> None:
        identity = _identity()
        service = OHLCVService(tmp_path)
        provider = _StubProvider(_days(1, 10))

        # First call: Jan 1-5
        service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 5), provider)
        # Second call: Jan 6-10 (trailing gap)
        service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 10), provider)

        coverage = CoverageRegistry(tmp_path).get(identity)
        assert coverage is not None
        assert coverage.earliest_timestamp == _utc(2024, 1, 1)
        assert coverage.latest_timestamp == _utc(2024, 1, 10)
        assert coverage.record_count == 10

    def test_refresh_coverage_syncs_from_disk(self, tmp_path: Path) -> None:
        identity = _identity()
        # Write directly to ohlcv_store, bypassing the service
        ohlcv_store.write(_days(1, 7), tmp_path, identity)

        service = OHLCVService(tmp_path)
        service.refresh_coverage(identity)

        coverage = CoverageRegistry(tmp_path).get(identity)
        assert coverage is not None
        assert coverage.record_count == 7


# ---------------------------------------------------------------------------
# Normalization errors
# ---------------------------------------------------------------------------

class TestNormalizationError:
    def test_bad_data_raises_ingestion_error(self, tmp_path: Path) -> None:
        service = OHLCVService(tmp_path)
        with pytest.raises(OHLCVIngestionError, match="Normalization failed"):
            service.get_ohlcv(
                _identity(),
                _utc(2024, 1, 1),
                _utc(2024, 1, 10),
                _BadRecordProvider(),
            )

    def test_normalization_error_does_not_corrupt_existing_storage(self, tmp_path: Path) -> None:
        identity = _identity()
        # Pre-populate Jan 1-5 cleanly
        ohlcv_store.write(_days(1, 5), tmp_path, identity)
        CoverageRegistry(tmp_path).update(identity, _days(1, 5))

        service = OHLCVService(tmp_path)
        with pytest.raises(OHLCVIngestionError):
            service.get_ohlcv(
                identity, _utc(2024, 1, 1), _utc(2024, 1, 10), _BadRecordProvider()
            )

        # Pre-existing data must be intact
        stored = ohlcv_store.read(tmp_path, identity)
        assert len(stored) == 5


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_naive_start_raises(self, tmp_path: Path) -> None:
        service = OHLCVService(tmp_path)
        with pytest.raises(ValueError, match="timezone-aware"):
            service.get_ohlcv(
                _identity(),
                datetime(2024, 1, 1),          # naive
                _utc(2024, 1, 10),
                _StubProvider([]),
            )

    def test_naive_end_raises(self, tmp_path: Path) -> None:
        service = OHLCVService(tmp_path)
        with pytest.raises(ValueError, match="timezone-aware"):
            service.get_ohlcv(
                _identity(),
                _utc(2024, 1, 1),
                datetime(2024, 1, 10),          # naive
                _StubProvider([]),
            )


# ---------------------------------------------------------------------------
# calculate_missing_ranges()
# ---------------------------------------------------------------------------

class TestCalculateMissingRanges:
    def test_no_coverage_returns_full_range(self, tmp_path: Path) -> None:
        service = OHLCVService(tmp_path)
        gaps = service.calculate_missing_ranges(
            _identity(), _utc(2024, 1, 1), _utc(2024, 1, 31)
        )
        assert len(gaps) == 1
        assert gaps[0][0] == _utc(2024, 1, 1)
        assert gaps[0][1] == _utc(2024, 1, 31)

    def test_full_coverage_returns_empty(self, tmp_path: Path) -> None:
        identity = _identity()
        ohlcv_store.write(_days(1, 10), tmp_path, identity)
        CoverageRegistry(tmp_path).update(identity, _days(1, 10))

        service = OHLCVService(tmp_path)
        gaps = service.calculate_missing_ranges(
            identity, _utc(2024, 1, 2), _utc(2024, 1, 9)
        )
        assert gaps == []

    def test_partial_coverage_returns_gaps(self, tmp_path: Path) -> None:
        identity = _identity()
        ohlcv_store.write(_days(5, 10), tmp_path, identity)
        CoverageRegistry(tmp_path).update(identity, _days(5, 10))

        service = OHLCVService(tmp_path)
        gaps = service.calculate_missing_ranges(
            identity, _utc(2024, 1, 1), _utc(2024, 1, 10)
        )
        assert len(gaps) == 1
        assert gaps[0][0] == _utc(2024, 1, 1)


# ---------------------------------------------------------------------------
# CSVAdapter.fetch() — range filtering contract
# ---------------------------------------------------------------------------

class TestCSVAdapterFetch:
    def _make_csv(self, tmp_path: Path, days: range) -> Path:
        """Write a minimal CSV with one row per day in `days`."""
        csv_path = tmp_path / "ohlcv.csv"
        lines = ["timestamp,open,high,low,close,volume"]
        for d in days:
            ts = f"2024-01-{d:02d}T00:00:00+00:00"
            lines.append(f"{ts},100.0,105.0,95.0,102.0,1000.0")
        csv_path.write_text("\n".join(lines))
        return csv_path

    def _adapter(self) -> CSVAdapter:
        from backend.data_providers.csv_adapter import CSVAdapterConfig
        config = CSVAdapterConfig(
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
            source="csv",
        )
        return CSVAdapter(config)

    def test_fetch_filters_to_start_end(self, tmp_path: Path) -> None:
        csv_path = self._make_csv(tmp_path, range(1, 16))
        adapter = self._adapter()
        result = adapter.fetch(
            _utc(2024, 1, 5),
            _utc(2024, 1, 10),
            file_path=str(csv_path),
        )
        assert len(result) == 6
        assert all(_utc(2024, 1, 5) <= r.timestamp <= _utc(2024, 1, 10) for r in result)

    def test_fetch_empty_when_no_data_in_range(self, tmp_path: Path) -> None:
        csv_path = self._make_csv(tmp_path, range(1, 6))
        adapter = self._adapter()
        result = adapter.fetch(
            _utc(2024, 2, 1),
            _utc(2024, 2, 28),
            file_path=str(csv_path),
        )
        assert result == []

    def test_fetch_naive_start_raises(self, tmp_path: Path) -> None:
        csv_path = self._make_csv(tmp_path, range(1, 6))
        adapter = self._adapter()
        with pytest.raises(ValueError, match="timezone-aware"):
            adapter.fetch(datetime(2024, 1, 1), _utc(2024, 1, 5), file_path=str(csv_path))

    def test_fetch_is_subtype_of_range_provider_adapter(self) -> None:
        from backend.data_providers.range_provider import RangeProviderAdapter
        assert isinstance(self._adapter(), RangeProviderAdapter)


# ---------------------------------------------------------------------------
# MD-1 — _EmptyResponseGuard
# ---------------------------------------------------------------------------

class TestEmptyResponseGuard:
    """Unit tests for the negative-response guard (MD-1 hardening)."""

    def _guard(self, tmp_path: Path) -> _EmptyResponseGuard:
        return _EmptyResponseGuard(tmp_path, _identity())

    def test_unguarded_when_no_entries(self, tmp_path: Path) -> None:
        assert not self._guard(tmp_path).is_guarded(
            _utc(2024, 1, 1), _utc(2024, 1, 5)
        )

    def test_guarded_after_record(self, tmp_path: Path) -> None:
        guard = self._guard(tmp_path)
        gap = (_utc(2024, 1, 1), _utc(2024, 1, 5))
        guard.record(*gap)
        assert guard.is_guarded(*gap)

    def test_different_gap_is_not_guarded(self, tmp_path: Path) -> None:
        guard = self._guard(tmp_path)
        guard.record(_utc(2024, 1, 1), _utc(2024, 1, 5))
        assert not guard.is_guarded(_utc(2024, 2, 1), _utc(2024, 2, 28))

    def test_expired_entry_returns_false(self, tmp_path: Path) -> None:
        """An entry whose expires_at is in the past is not guarded."""
        guard = self._guard(tmp_path)
        gap_start, gap_end = _utc(2024, 1, 1), _utc(2024, 1, 5)
        # Manually write an expired entry
        from datetime import timedelta
        past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        path = guard._path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({guard._key(gap_start, gap_end): past}))
        assert not guard.is_guarded(gap_start, gap_end)

    def test_corrupt_sidecar_treated_as_no_guard(self, tmp_path: Path) -> None:
        guard = self._guard(tmp_path)
        guard._path.parent.mkdir(parents=True, exist_ok=True)
        guard._path.write_text("NOT JSON", encoding="utf-8")
        # Should not raise — falls back to empty dict
        assert not guard.is_guarded(_utc(2024, 1, 1), _utc(2024, 1, 5))

    def test_ttl_constant_is_positive_and_reasonable(self) -> None:
        assert 60 <= _EMPTY_RESPONSE_TTL_SECONDS <= 3600

    def test_guard_prevents_second_provider_call_after_empty(
        self, tmp_path: Path
    ) -> None:
        """Provider called once for empty range; second call is blocked by guard."""
        identity = _identity()
        service = OHLCVService(tmp_path)
        provider = _EmptyProvider()

        # First call — provider returns empty, guard is recorded
        service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 5), provider)
        assert len(provider.fetch_calls) == 1

        # Second call — same gap, same empty provider; guard should block it
        service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 5), provider)
        # Still 1 — provider was not called again
        assert len(provider.fetch_calls) == 1


# ---------------------------------------------------------------------------
# MD-1 — trailing-edge freshness (_trailing_edge_is_stale + integration)
# ---------------------------------------------------------------------------

class TestTrailingEdgeFreshness:
    """Tests for the trailing-candle finality rule (MD-1 hardening)."""

    # ---- Unit tests for _trailing_edge_is_stale ----

    def test_finalized_2024_bar_not_stale(self, tmp_path: Path) -> None:
        """A bar from January 2024 is fully finalized by June 2026."""
        service = OHLCVService(tmp_path)
        identity = _identity()  # "1d" timeframe
        old_ts = _utc(2024, 1, 5)
        now = _utc(2026, 6, 1)
        assert not service._trailing_edge_is_stale(identity, old_ts, _now=now)

    def test_unfinalized_bar_within_candle_period_is_stale(
        self, tmp_path: Path
    ) -> None:
        """A '1d' bar opened at midnight is stale when checked 12 hours later."""
        service = OHLCVService(tmp_path)
        identity = _identity()  # "1d" timeframe
        bar_open = _utc(2026, 5, 31, 0, 0)   # bar closes at 2026-06-01 00:00
        now = _utc(2026, 5, 31, 12, 0)        # 12 h after open — still forming
        assert service._trailing_edge_is_stale(identity, bar_open, _now=now)

    def test_bar_at_exact_close_plus_buffer_is_not_stale(
        self, tmp_path: Path
    ) -> None:
        """A bar is not stale once current_time >= bar_close + 60 s."""
        service = OHLCVService(tmp_path)
        identity = _identity()  # "1d" timeframe
        bar_open = _utc(2026, 5, 31, 0, 0)
        # bar closes at 2026-06-01 00:00; add 61 s safety margin
        now = _utc(2026, 6, 1, 0, 1, 1)
        assert not service._trailing_edge_is_stale(identity, bar_open, _now=now)

    def test_naive_latest_ts_treated_as_stale(self, tmp_path: Path) -> None:
        """Defensive: a naive (timezone-unaware) latest_ts is treated as stale."""
        service = OHLCVService(tmp_path)
        identity = _identity()
        naive_ts = datetime(2024, 1, 5)  # no tzinfo
        assert service._trailing_edge_is_stale(identity, naive_ts)

    # ---- Integration tests ----

    def test_finalized_bars_do_not_trigger_provider_refetch(
        self, tmp_path: Path
    ) -> None:
        """Fully cached 2024 data is served from storage — provider not called."""
        identity = _identity()
        ohlcv_store.write(_days(1, 5), tmp_path, identity)
        CoverageRegistry(tmp_path).update(identity, _days(1, 5))

        provider = _StubProvider(_days(1, 5))
        service = OHLCVService(tmp_path)
        service.get_ohlcv(identity, _utc(2024, 1, 1), _utc(2024, 1, 5), provider)

        assert provider.fetch_calls == [], (
            "Provider should not be called — all 2024 bars are finalized"
        )

    def test_unfinalized_trailing_bar_triggers_provider_refetch(
        self, tmp_path: Path
    ) -> None:
        """
        A bar opened today (1d timeframe) is not yet finalized.
        Coverage says 'full hit' but the trailing-edge check should force a
        re-fetch so we don't permanently serve a mid-session partial close.
        """
        identity = _identity()  # "1d" timeframe

        # Build a record with today's open-time (UTC midnight)
        today_midnight = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_bar = make_ohlcv(
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
            source="stub",
            timestamp=today_midnight,
            open=100.0, high=110.0, low=90.0, close=105.0, volume=1_000_000.0,
        )

        ohlcv_store.write([today_bar], tmp_path, identity)
        CoverageRegistry(tmp_path).update(identity, [today_bar])

        provider = _StubProvider([today_bar])
        service = OHLCVService(tmp_path)
        service.get_ohlcv(identity, today_midnight, today_midnight, provider)

        assert len(provider.fetch_calls) == 1, (
            "Provider should be re-called for an unfinalized trailing bar"
        )

    def test_stale_trailing_bar_beyond_requested_end_skipped(
        self, tmp_path: Path
    ) -> None:
        """
        If the latest stored bar is stale but beyond the requested end,
        no trailing re-fetch is issued (the stale bar is irrelevant to the slice).
        """
        identity = _identity()  # "1d" timeframe

        today_midnight = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_bar = make_ohlcv(
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
            source="stub",
            timestamp=today_midnight,
            open=100.0, high=110.0, low=90.0, close=105.0, volume=1_000_000.0,
        )

        # Also add a 2024 finalized bar to give us coverage back to 2024
        jan_bar = _record(5)  # 2024-01-05

        ohlcv_store.write([jan_bar, today_bar], tmp_path, identity)
        CoverageRegistry(tmp_path).update(identity, [jan_bar, today_bar])

        # Request ends at a 2024 finalized bar — today's stale bar is beyond `end`
        provider = _StubProvider([jan_bar, today_bar])
        service = OHLCVService(tmp_path)
        service.get_ohlcv(identity, _utc(2024, 1, 5), _utc(2024, 1, 5), provider)

        # No provider call: trail_start (today) > end (2024-01-05)
        assert provider.fetch_calls == []
