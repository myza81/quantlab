"""
Provider-aware OHLCV storage service.

Storage path convention:
    {base_path}/{provider}/{asset_class}/{exchange}/{symbol}/{timeframe}/{adjustment_mode}/data.parquet

Key guarantees:
- Data from different providers for the same instrument is always stored in
  separate files — never silently merged.
- Deduplication: incoming records overwrite existing records with the same
  timestamp within the same dataset (same provider + instrument + timeframe +
  adjustment_mode).
- Merge (default): existing records not present in the incoming batch are
  preserved. Use merge=False to do a full overwrite.
- All writes sort records by timestamp ascending before persisting.
"""
from datetime import datetime
from pathlib import Path

import pyarrow.parquet as pq

from backend.data.models.dataset import DatasetIdentity
from backend.data.schemas import NormalizedOHLCV
from backend.storage.parquet_store import (
    SCHEMA,
    StorageError,
    records_to_table,
    table_to_records,
)


class OHLCVWriteError(StorageError):
    """Raised when records fail dataset-identity validation before write."""


def dataset_path(base_path: Path, identity: DatasetIdentity) -> Path:
    """Return the canonical Parquet file path for a provider-specific dataset."""
    inst = identity.instrument
    return (
        base_path
        / identity.provider
        / inst.asset_class
        / inst.exchange
        / inst.symbol
        / identity.timeframe
        / identity.adjustment_mode.value
        / "data.parquet"
    )


def write(
    records: list[NormalizedOHLCV],
    base_path: Path,
    identity: DatasetIdentity,
    *,
    merge: bool = True,
) -> Path:
    """
    Persist OHLCV records with deduplication.

    merge=True (default): load existing records, merge with incoming
    (incoming wins on timestamp collision), sort, write.
    merge=False: overwrite the file entirely after deduplication.

    All records must match the dataset identity (symbol, asset_class, timeframe).
    """
    if not records:
        raise OHLCVWriteError("cannot write empty records list")

    inst = identity.instrument
    for rec in records:
        if rec.symbol != inst.symbol:
            raise OHLCVWriteError(
                f"record symbol '{rec.symbol}' does not match identity symbol '{inst.symbol}'"
            )
        if rec.asset_class != inst.asset_class:
            raise OHLCVWriteError(
                f"record asset_class '{rec.asset_class}' does not match "
                f"identity asset_class '{inst.asset_class}'"
            )
        if rec.timeframe != identity.timeframe:
            raise OHLCVWriteError(
                f"record timeframe '{rec.timeframe}' does not match "
                f"identity timeframe '{identity.timeframe}'"
            )
        if rec.venue != inst.exchange:
            raise OHLCVWriteError(
                f"record venue '{rec.venue}' does not match identity exchange '{inst.exchange}'"
            )
        if rec.source != identity.provider:
            raise OHLCVWriteError(
                f"record source '{rec.source}' does not match identity provider '{identity.provider}'"
            )

    path = dataset_path(base_path, identity)

    if merge and path.exists():
        existing = _read_raw(path)
        merged = _merge_and_deduplicate(existing, records)
    else:
        merged = _deduplicate(records)

    merged = sorted(merged, key=lambda r: r.timestamp)

    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(records_to_table(merged), path)
    return path


def read(base_path: Path, identity: DatasetIdentity) -> list[NormalizedOHLCV]:
    """Load all NormalizedOHLCV records for a provider-specific dataset."""
    path = dataset_path(base_path, identity)
    if not path.exists():
        raise StorageError(f"dataset not found: {path}")
    return _read_raw(path)


def read_range(
    base_path: Path,
    identity: DatasetIdentity,
    start: datetime,
    end: datetime,
) -> list[NormalizedOHLCV]:
    """Load records within [start, end] inclusive. Both must be UTC-aware."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware (UTC)")
    records = read(base_path, identity)
    return [r for r in records if start <= r.timestamp <= end]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_raw(path: Path) -> list[NormalizedOHLCV]:
    table = pq.read_table(path, schema=SCHEMA)
    return table_to_records(table)


def _merge_and_deduplicate(
    existing: list[NormalizedOHLCV],
    incoming: list[NormalizedOHLCV],
) -> list[NormalizedOHLCV]:
    """Merge incoming over existing — incoming wins on timestamp collision."""
    by_ts = {r.timestamp: r for r in existing}
    for r in incoming:
        by_ts[r.timestamp] = r
    return list(by_ts.values())


def _deduplicate(records: list[NormalizedOHLCV]) -> list[NormalizedOHLCV]:
    """Deduplicate within a single list — last occurrence wins."""
    by_ts: dict[datetime, NormalizedOHLCV] = {}
    for r in records:
        by_ts[r.timestamp] = r
    return list(by_ts.values())
