"""
File-based coverage registry for OHLCV datasets.

Coverage metadata is stored as JSON alongside the Parquet data file:
    {dataset_dir}/coverage.json

This avoids the need to scan all Parquet files to answer coverage questions
and removes any PostgreSQL dependency at this stage.

Coverage answers:
- Do we have data for this dataset in a given date range?
- What is the earliest/latest stored timestamp?
- What ranges are missing from a requested window?
"""
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from backend.data.models.dataset import DatasetIdentity
from backend.data.schemas import NormalizedOHLCV
from backend.storage.ohlcv_store import dataset_path as ohlcv_dataset_path

_COVERAGE_FILENAME = "coverage.json"


@dataclass(frozen=True)
class CoverageRecord:
    """Coverage metadata snapshot for a single provider-specific dataset."""
    dataset_id: str
    provider: str
    instrument_id: str
    timeframe: str
    adjustment_mode: str
    earliest_timestamp: datetime
    latest_timestamp: datetime
    record_count: int
    last_updated: datetime


class CoverageRegistry:
    """
    Read and write coverage metadata for OHLCV datasets.

    Coverage is stored per-dataset as a JSON file alongside the Parquet file.
    Call update() after every successful write to keep coverage current.
    """

    def __init__(self, base_path: Path) -> None:
        self._base_path = base_path

    def _coverage_path(self, identity: DatasetIdentity) -> Path:
        return ohlcv_dataset_path(self._base_path, identity).parent / _COVERAGE_FILENAME

    def update(
        self, identity: DatasetIdentity, records: list[NormalizedOHLCV]
    ) -> CoverageRecord:
        """
        Update coverage metadata from a list of already-persisted records.

        Call this after every successful ohlcv_store.write() to keep the
        coverage registry in sync.
        """
        if not records:
            raise ValueError("cannot update coverage from empty records list")

        inst = identity.instrument
        for record in records:
            if record.symbol != inst.symbol:
                raise ValueError(
                    f"record symbol '{record.symbol}' does not match identity symbol '{inst.symbol}'"
                )
            if record.asset_class != inst.asset_class:
                raise ValueError(
                    f"record asset_class '{record.asset_class}' does not match "
                    f"identity asset_class '{inst.asset_class}'"
                )
            if record.venue != inst.exchange:
                raise ValueError(
                    f"record venue '{record.venue}' does not match identity exchange '{inst.exchange}'"
                )
            if record.timeframe != identity.timeframe:
                raise ValueError(
                    f"record timeframe '{record.timeframe}' does not match "
                    f"identity timeframe '{identity.timeframe}'"
                )
            if record.source != identity.provider:
                raise ValueError(
                    f"record source '{record.source}' does not match identity provider "
                    f"'{identity.provider}'"
                )

        timestamps = [r.timestamp for r in records]
        coverage = CoverageRecord(
            dataset_id=identity.dataset_id,
            provider=identity.provider,
            instrument_id=identity.instrument.instrument_id,
            timeframe=identity.timeframe,
            adjustment_mode=identity.adjustment_mode.value,
            earliest_timestamp=min(timestamps),
            latest_timestamp=max(timestamps),
            record_count=len(records),
            last_updated=datetime.now(tz=timezone.utc),
        )
        self._write(identity, coverage)
        return coverage

    def get(self, identity: DatasetIdentity) -> Optional[CoverageRecord]:
        """Return the coverage record, or None if no coverage exists yet."""
        path = self._coverage_path(identity)
        if not path.exists():
            return None
        return self._read(path)

    def has_full_coverage(
        self, identity: DatasetIdentity, start: datetime, end: datetime
    ) -> bool:
        """
        Return True if stored data fully covers [start, end].

        Uses boundary timestamps only — does not detect per-candle gaps
        within the covered range.
        """
        record = self.get(identity)
        if record is None:
            return False
        return record.earliest_timestamp <= start and record.latest_timestamp >= end

    def missing_ranges(
        self, identity: DatasetIdentity, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime]]:
        """
        Return date ranges within [start, end] that are not covered.

        Based on earliest/latest boundary only — suitable for deciding which
        date windows to fetch from a provider before calling read_range().
        Per-candle gap detection requires loading the full records list.
        """
        record = self.get(identity)
        if record is None:
            return [(start, end)]

        gaps: list[tuple[datetime, datetime]] = []

        if start < record.earliest_timestamp:
            gap_end = min(end, record.earliest_timestamp - timedelta(microseconds=1))
            if gap_end >= start:
                gaps.append((start, gap_end))

        if end > record.latest_timestamp:
            gap_start = max(start, record.latest_timestamp + timedelta(microseconds=1))
            if gap_start <= end:
                gaps.append((gap_start, end))

        return gaps

    # ------------------------------------------------------------------
    # Internal I/O
    # ------------------------------------------------------------------

    def _write(self, identity: DatasetIdentity, record: CoverageRecord) -> None:
        path = self._coverage_path(identity)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "dataset_id": record.dataset_id,
            "provider": record.provider,
            "instrument_id": record.instrument_id,
            "timeframe": record.timeframe,
            "adjustment_mode": record.adjustment_mode,
            "earliest_timestamp": record.earliest_timestamp.isoformat(),
            "latest_timestamp": record.latest_timestamp.isoformat(),
            "record_count": record.record_count,
            "last_updated": record.last_updated.isoformat(),
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _read(self, path: Path) -> CoverageRecord:
        data = json.loads(path.read_text(encoding="utf-8"))
        return CoverageRecord(
            dataset_id=data["dataset_id"],
            provider=data["provider"],
            instrument_id=data["instrument_id"],
            timeframe=data["timeframe"],
            adjustment_mode=data["adjustment_mode"],
            earliest_timestamp=datetime.fromisoformat(data["earliest_timestamp"]),
            latest_timestamp=datetime.fromisoformat(data["latest_timestamp"]),
            record_count=data["record_count"],
            last_updated=datetime.fromisoformat(data["last_updated"]),
        )
