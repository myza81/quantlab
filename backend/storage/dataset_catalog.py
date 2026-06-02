"""
Dataset Catalog — JSON-backed registry mapping catalog_id → local file paths.

Bridges the HTTP API layer to local dataset providers (CSV / Parquet) without
exposing raw filesystem paths to API consumers.  The catalog is the sole place
that knows the mapping from an opaque `catalog_id` (UUID) to a `file_path`.

Architecture contract:
    API consumers receive only catalog_id and metadata.
    file_path is NEVER returned to callers outside this module.
    Resolution flow: catalog_id → DatasetCatalog.get() → file_path (internal)
                     → ProviderFactory.build() → OHLCVService

Storage layout:
    {base_path}/catalog/datasets.json

JSON schema per entry:
    catalog_id, provider_type, file_path, display_name, dataset_type,
    asset_class, timeframe, symbol, venue, adjustment_mode,
    registered_at (ISO-8601 UTC), enabled (bool), metadata (optional dict)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

_CATALOG_SUBDIR = "catalog"
_CATALOG_FILENAME = "datasets.json"


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------

class DatasetCatalogError(Exception):
    """Base error for all catalog operations."""


class UnknownDatasetError(DatasetCatalogError):
    """Raised when a catalog_id does not exist in the registry."""


class DatasetDisabledError(DatasetCatalogError):
    """Raised when a catalog entry is present but has been disabled."""


class DuplicateDatasetError(DatasetCatalogError):
    """Raised when a registration would create a duplicate file_path entry."""


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------

class LocalDatasetEntry(BaseModel):
    """
    Immutable catalog record for a locally registered dataset.

    file_path is intentionally excluded from JSON serialisation helpers
    used by the API layer; the catalog service resolves it internally.
    """
    model_config = ConfigDict(frozen=True)

    catalog_id: str
    provider_type: str          # "csv" | "parquet"
    file_path: str              # absolute path — NEVER expose to API consumers
    display_name: str
    dataset_type: str           # e.g. "ohlcv"
    asset_class: str            # e.g. "equity"
    timeframe: str              # canonical, e.g. "1d"
    symbol: str                 # e.g. "AAPL"
    venue: str                  # e.g. "NASDAQ"
    adjustment_mode: str = "adjusted"
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    enabled: bool = True
    user_id: str | None = None
    metadata: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Catalog registry
# ---------------------------------------------------------------------------

class DatasetCatalog:
    """
    JSON-backed registry of locally registered datasets.

    Each instance targets a single catalog file.  Mutations (register, disable,
    remove) immediately flush to disk.  Reads deserialise from disk each time
    so multiple processes see the same state (no in-memory write-through cache).

    Thread-safety: not guaranteed — suitable for single-process dev/research use.
    """

    def __init__(self, base_path: Path) -> None:
        self._catalog_path = base_path / _CATALOG_SUBDIR / _CATALOG_FILENAME

    # ------------------------------------------------------------------
    # Mutation API
    # ------------------------------------------------------------------

    def register(
        self,
        *,
        provider_type: str,
        file_path: str,
        display_name: str,
        symbol: str,
        asset_class: str,
        venue: str,
        timeframe: str,
        dataset_type: str = "ohlcv",
        adjustment_mode: str = "adjusted",
        metadata: Optional[dict[str, Any]] = None,
        allow_duplicate_path: bool = False,
        user_id: str | None = None,
    ) -> LocalDatasetEntry:
        """
        Register a new local dataset and persist the catalog.

        Args:
            provider_type:        "csv" or "parquet".
            file_path:            Absolute path to the dataset file.
            display_name:         Human-readable label.
            symbol:               Instrument symbol, e.g. "AAPL".
            asset_class:          e.g. "equity".
            venue:                Exchange/venue, e.g. "NASDAQ".
            timeframe:            Canonical timeframe, e.g. "1d".
            dataset_type:         Defaults to "ohlcv".
            adjustment_mode:      Defaults to "adjusted".
            metadata:             Optional free-form dict.
            allow_duplicate_path: If False (default), raise DuplicateDatasetError
                                  when file_path is already registered.

        Returns:
            The newly created LocalDatasetEntry.

        Raises:
            DuplicateDatasetError: if file_path already registered and
                                   allow_duplicate_path is False.
            ValueError:            if required fields are empty.
        """
        for field, value in [
            ("provider_type", provider_type),
            ("file_path", file_path),
            ("display_name", display_name),
            ("symbol", symbol),
            ("asset_class", asset_class),
            ("venue", venue),
            ("timeframe", timeframe),
        ]:
            if not str(value).strip():
                raise ValueError(f"{field} must not be empty or whitespace")

        entries = self._load_all()

        if not allow_duplicate_path:
            for entry in entries.values():
                if entry.file_path == file_path:
                    raise DuplicateDatasetError(
                        f"file_path already registered as {entry.catalog_id!r}: {file_path!r}"
                    )

        catalog_id = str(uuid4())
        entry = LocalDatasetEntry(
            catalog_id=catalog_id,
            provider_type=provider_type.strip().lower(),
            file_path=file_path,
            display_name=display_name.strip(),
            dataset_type=dataset_type,
            asset_class=asset_class.strip().lower(),
            timeframe=timeframe.strip(),
            symbol=symbol.strip().upper(),
            venue=venue.strip().upper(),
            adjustment_mode=adjustment_mode.strip().lower(),
            user_id=user_id,
            metadata=metadata,
        )
        entries[catalog_id] = entry
        self._persist(entries)
        logger.info("DatasetCatalog: registered %s (%s)", catalog_id, display_name)
        return entry

    def disable(self, catalog_id: str, owner_id: str | None = None) -> LocalDatasetEntry:
        """
        Mark a catalog entry as disabled.

        If owner_id is provided, raises UnknownDatasetError (same as not-found)
        when the entry's user_id does not match — information hiding.

        A disabled entry remains in the registry but raises DatasetDisabledError
        when fetched via get().

        Raises:
            UnknownDatasetError: catalog_id not found or wrong owner.
        """
        entries = self._load_all()
        if catalog_id not in entries:
            raise UnknownDatasetError(f"No dataset with catalog_id {catalog_id!r}")
        old = entries[catalog_id]
        if owner_id is not None and old.user_id != owner_id:
            raise UnknownDatasetError(f"No dataset with catalog_id {catalog_id!r}")
        updated = old.model_copy(update={"enabled": False})
        entries[catalog_id] = updated
        self._persist(entries)
        logger.info("DatasetCatalog: disabled %s", catalog_id)
        return updated

    def remove(self, catalog_id: str, owner_id: str | None = None) -> None:
        """
        Permanently remove a catalog entry.

        If owner_id is provided, raises UnknownDatasetError (same as not-found)
        when the entry's user_id does not match — information hiding.

        Raises:
            UnknownDatasetError: catalog_id not found or wrong owner.
        """
        entries = self._load_all()
        if catalog_id not in entries:
            raise UnknownDatasetError(f"No dataset with catalog_id {catalog_id!r}")
        entry = entries[catalog_id]
        if owner_id is not None and entry.user_id != owner_id:
            raise UnknownDatasetError(f"No dataset with catalog_id {catalog_id!r}")
        del entries[catalog_id]
        self._persist(entries)
        logger.info("DatasetCatalog: removed %s", catalog_id)

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get(self, catalog_id: str, owner_id: str | None = None) -> LocalDatasetEntry:
        """
        Retrieve an entry by catalog_id.

        If owner_id is provided, raises UnknownDatasetError (same as not-found)
        when the entry's user_id does not match — information hiding.

        Raises:
            UnknownDatasetError:  catalog_id not in registry or wrong owner.
            DatasetDisabledError: entry exists but is disabled.
        """
        entries = self._load_all()
        if catalog_id not in entries:
            raise UnknownDatasetError(f"No dataset with catalog_id {catalog_id!r}")
        entry = entries[catalog_id]
        if owner_id is not None and entry.user_id != owner_id:
            raise UnknownDatasetError(f"No dataset with catalog_id {catalog_id!r}")
        if not entry.enabled:
            raise DatasetDisabledError(
                f"Dataset {catalog_id!r} ({entry.display_name!r}) is disabled"
            )
        return entry

    def get_any(self, catalog_id: str, owner_id: str | None = None) -> LocalDatasetEntry:
        """
        Return entry regardless of enabled state (for admin / delete flows).

        If owner_id is provided, raises UnknownDatasetError when user_id doesn't match.
        """
        entries = self._load_all()
        if catalog_id not in entries:
            raise UnknownDatasetError(f"No dataset with catalog_id {catalog_id!r}")
        entry = entries[catalog_id]
        if owner_id is not None and entry.user_id != owner_id:
            raise UnknownDatasetError(f"No dataset with catalog_id {catalog_id!r}")
        return entry

    def list_all(self, user_id: str | None = None) -> list[LocalDatasetEntry]:
        """
        Return all entries (enabled and disabled), sorted by registered_at.

        If user_id is provided, only entries whose user_id matches are returned.
        Legacy entries (user_id=None) are NOT returned when user_id is provided.
        """
        entries = self._load_all()
        all_entries = sorted(entries.values(), key=lambda e: e.registered_at)
        if user_id is not None:
            return [e for e in all_entries if e.user_id == user_id]
        return all_entries

    def list_enabled(self, user_id: str | None = None) -> list[LocalDatasetEntry]:
        """Return only enabled entries, sorted by registered_at."""
        return [e for e in self.list_all(user_id=user_id) if e.enabled]

    def __len__(self) -> int:
        return len(self._load_all())

    def __contains__(self, catalog_id: object) -> bool:
        if not isinstance(catalog_id, str):
            return False
        return catalog_id in self._load_all()

    # ------------------------------------------------------------------
    # Internal persistence helpers
    # ------------------------------------------------------------------

    def _catalog_file(self) -> Path:
        return self._catalog_path

    def _load_all(self) -> dict[str, LocalDatasetEntry]:
        path = self._catalog_file()
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("DatasetCatalog: could not read %s: %s", path, exc)
            return {}
        entries: dict[str, LocalDatasetEntry] = {}
        for record in raw:
            try:
                entry = LocalDatasetEntry(**record)
                entries[entry.catalog_id] = entry
            except Exception as exc:  # noqa: BLE001
                logger.warning("DatasetCatalog: skipping malformed record: %s", exc)
        return entries

    def _persist(self, entries: dict[str, LocalDatasetEntry]) -> None:
        path = self._catalog_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        serialised = [
            {
                **e.model_dump(),
                "registered_at": e.registered_at.isoformat(),
            }
            for e in entries.values()
        ]
        path.write_text(
            json.dumps(serialised, indent=2, default=str),
            encoding="utf-8",
        )
