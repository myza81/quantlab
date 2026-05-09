"""Tests for backend/storage/coverage_registry.py — file-based coverage tracking."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.data.models.instrument import Instrument
from backend.data.models.dataset import DatasetIdentity
from backend.storage.coverage_registry import CoverageRecord, CoverageRegistry
from tests.conftest import make_ohlcv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _identity(provider: str = "yahoo") -> DatasetIdentity:
    return DatasetIdentity(
        instrument=Instrument(symbol="AAPL", asset_class="equity", exchange="NASDAQ"),
        provider=provider,
        timeframe="1d",
    )


def _records(n: int = 3, source: str = "yahoo") -> list:
    return [
        make_ohlcv(
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
            source=source,
            timestamp=datetime(2024, 1, i + 1, tzinfo=timezone.utc),
        )
        for i in range(n)
    ]


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# CoverageRegistry.get() — no coverage yet
# ---------------------------------------------------------------------------

class TestCoverageGet:
    def test_get_returns_none_when_no_coverage(self, tmp_path: Path) -> None:
        registry = CoverageRegistry(tmp_path)
        assert registry.get(_identity()) is None

    def test_get_returns_coverage_record_after_update(self, tmp_path: Path) -> None:
        registry = CoverageRegistry(tmp_path)
        identity = _identity()
        records = _records(3)
        registry.update(identity, records)
        result = registry.get(identity)
        assert result is not None
        assert isinstance(result, CoverageRecord)


# ---------------------------------------------------------------------------
# CoverageRegistry.update()
# ---------------------------------------------------------------------------

class TestCoverageUpdate:
    def test_update_writes_coverage_json(self, tmp_path: Path) -> None:
        registry = CoverageRegistry(tmp_path)
        identity = _identity()
        registry.update(identity, _records(3))
        # coverage.json must exist alongside data.parquet
        from backend.storage.ohlcv_store import dataset_path
        coverage_path = dataset_path(tmp_path, identity).parent / "coverage.json"
        assert coverage_path.exists()

    def test_update_empty_records_raises(self, tmp_path: Path) -> None:
        registry = CoverageRegistry(tmp_path)
        with pytest.raises(ValueError, match="empty"):
            registry.update(_identity(), [])

    def test_update_exchange_mismatch_raises(self, tmp_path: Path) -> None:
        registry = CoverageRegistry(tmp_path)
        with pytest.raises(ValueError, match="venue"):
            registry.update(
                _identity(),
                [
                    make_ohlcv(
                        symbol="AAPL",
                        asset_class="equity",
                        venue="NYSE",
                        timeframe="1d",
                        source="yahoo",
                        timestamp=_utc(2024, 1, 1),
                    )
                ],
            )

    def test_update_provider_mismatch_raises(self, tmp_path: Path) -> None:
        registry = CoverageRegistry(tmp_path)
        with pytest.raises(ValueError, match="source"):
            registry.update(
                _identity(provider="yahoo"),
                [
                    make_ohlcv(
                        symbol="AAPL",
                        asset_class="equity",
                        venue="NASDAQ",
                        timeframe="1d",
                        source="polygon",
                        timestamp=_utc(2024, 1, 1),
                    )
                ],
            )

    def test_update_coverage_contains_correct_dataset_id(self, tmp_path: Path) -> None:
        registry = CoverageRegistry(tmp_path)
        identity = _identity()
        record = registry.update(identity, _records(3))
        assert record.dataset_id == identity.dataset_id

    def test_update_coverage_timestamps_correct(self, tmp_path: Path) -> None:
        registry = CoverageRegistry(tmp_path)
        identity = _identity()
        records = _records(3)
        result = registry.update(identity, records)
        assert result.earliest_timestamp == _utc(2024, 1, 1)
        assert result.latest_timestamp == _utc(2024, 1, 3)

    def test_update_record_count_correct(self, tmp_path: Path) -> None:
        registry = CoverageRegistry(tmp_path)
        identity = _identity()
        result = registry.update(identity, _records(5))
        assert result.record_count == 5

    def test_update_persists_and_is_retrievable(self, tmp_path: Path) -> None:
        registry = CoverageRegistry(tmp_path)
        identity = _identity()
        registry.update(identity, _records(3))
        retrieved = registry.get(identity)
        assert retrieved is not None
        assert retrieved.earliest_timestamp == _utc(2024, 1, 1)
        assert retrieved.latest_timestamp == _utc(2024, 1, 3)

    def test_update_overrides_previous_coverage(self, tmp_path: Path) -> None:
        registry = CoverageRegistry(tmp_path)
        identity = _identity()
        registry.update(identity, _records(2))
        registry.update(identity, _records(5))
        result = registry.get(identity)
        assert result is not None
        assert result.record_count == 5


# ---------------------------------------------------------------------------
# has_full_coverage()
# ---------------------------------------------------------------------------

class TestHasFullCoverage:
    def test_no_coverage_returns_false(self, tmp_path: Path) -> None:
        registry = CoverageRegistry(tmp_path)
        assert not registry.has_full_coverage(_identity(), _utc(2024, 1, 1), _utc(2024, 1, 31))

    def test_fully_covered_range_returns_true(self, tmp_path: Path) -> None:
        registry = CoverageRegistry(tmp_path)
        identity = _identity()
        registry.update(identity, _records(10))  # 2024-01-01..2024-01-10
        assert registry.has_full_coverage(identity, _utc(2024, 1, 2), _utc(2024, 1, 9))

    def test_partial_coverage_returns_false(self, tmp_path: Path) -> None:
        registry = CoverageRegistry(tmp_path)
        identity = _identity()
        registry.update(identity, _records(5))  # 2024-01-01..2024-01-05
        assert not registry.has_full_coverage(identity, _utc(2024, 1, 1), _utc(2024, 1, 31))


# ---------------------------------------------------------------------------
# missing_ranges()
# ---------------------------------------------------------------------------

class TestMissingRanges:
    def test_no_coverage_returns_full_range(self, tmp_path: Path) -> None:
        registry = CoverageRegistry(tmp_path)
        start, end = _utc(2024, 1, 1), _utc(2024, 1, 31)
        gaps = registry.missing_ranges(_identity(), start, end)
        assert len(gaps) == 1
        assert gaps[0] == (start, end)

    def test_fully_covered_returns_empty(self, tmp_path: Path) -> None:
        registry = CoverageRegistry(tmp_path)
        identity = _identity()
        registry.update(identity, _records(10))  # 2024-01-01..2024-01-10
        gaps = registry.missing_ranges(identity, _utc(2024, 1, 2), _utc(2024, 1, 9))
        assert gaps == []

    def test_leading_gap_detected(self, tmp_path: Path) -> None:
        registry = CoverageRegistry(tmp_path)
        identity = _identity()
        registry.update(identity, _records(5))  # 2024-01-01..2024-01-05
        gaps = registry.missing_ranges(identity, _utc(2023, 12, 1), _utc(2024, 1, 3))
        assert len(gaps) == 1
        assert gaps[0][0] == _utc(2023, 12, 1)

    def test_trailing_gap_detected(self, tmp_path: Path) -> None:
        registry = CoverageRegistry(tmp_path)
        identity = _identity()
        registry.update(identity, _records(5))  # 2024-01-01..2024-01-05
        gaps = registry.missing_ranges(identity, _utc(2024, 1, 3), _utc(2024, 3, 1))
        assert len(gaps) == 1
        assert gaps[0][1] == _utc(2024, 3, 1)

    def test_both_gaps_detected(self, tmp_path: Path) -> None:
        registry = CoverageRegistry(tmp_path)
        identity = _identity()
        registry.update(identity, _records(5))  # 2024-01-01..2024-01-05
        gaps = registry.missing_ranges(identity, _utc(2023, 12, 1), _utc(2024, 3, 1))
        assert len(gaps) == 2


# ---------------------------------------------------------------------------
# Provider isolation — separate coverage per provider
# ---------------------------------------------------------------------------

class TestCoverageProviderIsolation:
    def test_different_providers_have_independent_coverage(self, tmp_path: Path) -> None:
        yahoo_id = _identity(provider="yahoo")
        polygon_id = _identity(provider="polygon")
        registry = CoverageRegistry(tmp_path)

        registry.update(yahoo_id, _records(3))
        registry.update(polygon_id, _records(2, source="polygon"))

        assert registry.get(yahoo_id) is not None
        polygon_record = registry.get(polygon_id)
        assert polygon_record is not None
        assert polygon_record.provider == "polygon"
