"""
Dataset cache metadata layer.

Tracks rich metadata for each locally-stored OHLCV dataset, extending the
basic boundary-coverage tracked by CoverageRegistry with:
- cache state classification (EMPTY / PARTIAL / HIT)
- first-write creation timestamp
- provider refresh timestamp
- fetch fingerprint lineage (last N fingerprints that contributed to the data)
- storage path reference

Storage layout (per dataset):
    {base_path}/{provider}/{asset_class}/{exchange}/{symbol}/{timeframe}/
        {adjustment_mode}/
            data.parquet          ← normalized OHLCV records
            coverage.json         ← boundary coverage (managed by CoverageRegistry)
            cache_metadata.json   ← rich cache metadata (managed by DatasetCacheRegistry)

Architecture contracts:
    - This module MUST NOT import from any provider adapter module.
    - This module MUST NOT import from the API layer.
    - Cache metadata is stored locally as JSON; no remote/distributed caching.
    - DatasetCacheRegistry is independent from CoverageRegistry — they coexist.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from backend.data.models.dataset import DatasetIdentity
from backend.data.schemas import NormalizedOHLCV
from backend.storage.ohlcv_store import dataset_path as ohlcv_dataset_path

_CACHE_FILENAME = "cache_metadata.json"
_MAX_FINGERPRINT_HISTORY = 10


# ---------------------------------------------------------------------------
# Cache state
# ---------------------------------------------------------------------------

class DatasetCacheState:
    """
    Classification of local cache coverage for a specific [start, end] request.

    EMPTY:   No locally stored data for this dataset.
    PARTIAL: Data exists but does not fully cover the requested date range.
    HIT:     Local data fully covers the requested date range — no provider
             call needed for the default FETCH_AND_STORE policy.
    """
    EMPTY = "empty"
    HIT = "hit"
    PARTIAL = "partial"


# ---------------------------------------------------------------------------
# Cache entry and lookup result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DatasetCacheEntry:
    """
    Rich metadata for a locally-stored OHLCV dataset.

    Persisted as ``cache_metadata.json`` alongside ``data.parquet``.
    Designed to remain stable across schema changes — new fields should be
    added with safe defaults so older JSON files remain readable.
    """
    dataset_id: str
    storage_path: str
    record_count: int
    earliest_ts: Optional[datetime]
    latest_ts: Optional[datetime]
    created_at: datetime
    last_refreshed_at: datetime
    last_fetch_fingerprint: Optional[str]
    fetch_fingerprints: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DatasetCacheLookupResult:
    """
    Result of a cache lookup for a specific [start, end] request.

    ``state`` classifies coverage; ``missing_ranges`` lists windows that
    require provider calls under the FETCH_AND_STORE policy; ``entry`` is
    the raw cache entry (None when state is EMPTY).
    """
    state: str
    missing_ranges: list[tuple[datetime, datetime]]
    entry: Optional[DatasetCacheEntry]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class DatasetCacheRegistry:
    """
    Read/write provider-agnostic cache metadata for OHLCV datasets.

    Each dataset's metadata lives in ``cache_metadata.json`` adjacent to its
    Parquet file — no external database required.

    Lifecycle (called by OHLCVService):
        1. lookup(identity, start, end)      → DatasetCacheLookupResult
        2. <fetch + store records>
        3. update(identity, records, ...)    → DatasetCacheEntry
    """

    def __init__(self, base_path: Path) -> None:
        self._base_path = base_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lookup(
        self,
        identity: DatasetIdentity,
        start: datetime,
        end: datetime,
    ) -> DatasetCacheLookupResult:
        """
        Classify cache coverage for the given [start, end] window.

        Returns a ``DatasetCacheLookupResult`` with state, missing ranges
        (relative to the request), and the raw entry.  The result does NOT
        apply any cache policy — callers apply the policy themselves.

        Args:
            identity:  Provider-specific dataset identity.
            start:     Inclusive lower bound — must be UTC-aware.
            end:       Inclusive upper bound — must be UTC-aware.

        Returns:
            DatasetCacheLookupResult.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware (UTC)")

        entry = self.get(identity)

        if entry is None or entry.earliest_ts is None or entry.latest_ts is None:
            return DatasetCacheLookupResult(
                state=DatasetCacheState.EMPTY,
                missing_ranges=[(start, end)],
                entry=None,
            )

        if entry.earliest_ts <= start and entry.latest_ts >= end:
            return DatasetCacheLookupResult(
                state=DatasetCacheState.HIT,
                missing_ranges=[],
                entry=entry,
            )

        return DatasetCacheLookupResult(
            state=DatasetCacheState.PARTIAL,
            missing_ranges=_compute_missing_ranges(entry, start, end),
            entry=entry,
        )

    def update(
        self,
        identity: DatasetIdentity,
        records: list[NormalizedOHLCV],
        storage_path: str,
        fingerprint: Optional[str] = None,
    ) -> DatasetCacheEntry:
        """
        Persist cache metadata derived from the provided records list.

        Should be called after every successful ``ohlcv_store.write()`` to
        keep cache metadata in sync with stored data.

        Preserves ``created_at`` across updates (only set on first write).
        Appends ``fingerprint`` to the rolling history (max
        ``_MAX_FINGERPRINT_HISTORY`` entries kept).

        Args:
            identity:      Provider-specific dataset identity.
            records:       All records now stored for this dataset (post-merge).
            storage_path:  Absolute or relative path to the Parquet file.
            fingerprint:   Fetch fingerprint to associate with this update.

        Returns:
            The newly written DatasetCacheEntry.
        """
        if not records:
            raise ValueError("cannot update cache from empty records list")

        now = datetime.now(tz=timezone.utc)
        existing = self._read_entry(identity)
        created_at = existing.created_at if existing is not None else now

        # Rolling fingerprint history — newest first
        existing_fps: list[str] = existing.fetch_fingerprints if existing is not None else []
        if fingerprint:
            new_fps: list[str] = [fingerprint] + [
                fp for fp in existing_fps if fp != fingerprint
            ]
            new_fps = new_fps[:_MAX_FINGERPRINT_HISTORY]
        else:
            new_fps = existing_fps

        timestamps = [r.timestamp for r in records]
        entry = DatasetCacheEntry(
            dataset_id=identity.dataset_id,
            storage_path=storage_path,
            record_count=len(records),
            earliest_ts=min(timestamps) if timestamps else None,
            latest_ts=max(timestamps) if timestamps else None,
            created_at=created_at,
            last_refreshed_at=now,
            last_fetch_fingerprint=fingerprint,
            fetch_fingerprints=new_fps,
        )
        self._write_entry(identity, entry)
        return entry

    def get(self, identity: DatasetIdentity) -> Optional[DatasetCacheEntry]:
        """Return the cache entry for this dataset, or None if absent."""
        return self._read_entry(identity)

    def invalidate(self, identity: DatasetIdentity) -> None:
        """
        Remove the cache_metadata.json file for this dataset.

        Safe to call even when no metadata file exists.
        Does NOT delete the Parquet data — only the cache metadata.
        """
        path = self._cache_path(identity)
        if path.exists():
            path.unlink()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cache_path(self, identity: DatasetIdentity) -> Path:
        return ohlcv_dataset_path(self._base_path, identity).parent / _CACHE_FILENAME

    def _write_entry(self, identity: DatasetIdentity, entry: DatasetCacheEntry) -> None:
        path = self._cache_path(identity)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "dataset_id": entry.dataset_id,
            "storage_path": entry.storage_path,
            "record_count": entry.record_count,
            "earliest_ts": entry.earliest_ts.isoformat() if entry.earliest_ts else None,
            "latest_ts": entry.latest_ts.isoformat() if entry.latest_ts else None,
            "created_at": entry.created_at.isoformat(),
            "last_refreshed_at": entry.last_refreshed_at.isoformat(),
            "last_fetch_fingerprint": entry.last_fetch_fingerprint,
            "fetch_fingerprints": entry.fetch_fingerprints,
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _read_entry(self, identity: DatasetIdentity) -> Optional[DatasetCacheEntry]:
        path = self._cache_path(identity)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))

        def _parse_dt(value: Optional[str]) -> Optional[datetime]:
            return datetime.fromisoformat(value) if value else None

        return DatasetCacheEntry(
            dataset_id=data["dataset_id"],
            storage_path=data["storage_path"],
            record_count=data["record_count"],
            earliest_ts=_parse_dt(data.get("earliest_ts")),
            latest_ts=_parse_dt(data.get("latest_ts")),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_refreshed_at=datetime.fromisoformat(data["last_refreshed_at"]),
            last_fetch_fingerprint=data.get("last_fetch_fingerprint"),
            fetch_fingerprints=data.get("fetch_fingerprints", []),
        )


# ---------------------------------------------------------------------------
# Internal pure helpers
# ---------------------------------------------------------------------------

def _compute_missing_ranges(
    entry: DatasetCacheEntry,
    start: datetime,
    end: datetime,
) -> list[tuple[datetime, datetime]]:
    """
    Compute sub-ranges of [start, end] not covered by the cache entry.

    Uses boundary timestamps only — does not detect per-candle gaps within
    the covered window (same contract as CoverageRegistry.missing_ranges).
    """
    gaps: list[tuple[datetime, datetime]] = []

    if entry.earliest_ts is None or entry.latest_ts is None:
        return [(start, end)]

    if start < entry.earliest_ts:
        gap_end = min(end, entry.earliest_ts - timedelta(microseconds=1))
        if gap_end >= start:
            gaps.append((start, gap_end))

    if end > entry.latest_ts:
        gap_start = max(start, entry.latest_ts + timedelta(microseconds=1))
        if gap_start <= end:
            gaps.append((gap_start, end))

    return gaps
