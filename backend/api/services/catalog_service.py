"""
Dataset Catalog service — orchestration layer for catalog registration and OHLCV retrieval.

Implements the resolution flow:
    catalog_id → DatasetCatalog.get() → entry (with file_path, internally)
               → factory.build(provider_type, file_path=..., ...)
               → OHLCVService.get_ohlcv()

Routes must remain thin; all domain logic lives here.

Architecture contract:
    file_path is resolved inside this module and never propagated to callers.
    Callers (routes / tests) interact only with catalog_id and response schemas.
    Provider errors are sanitized before surfacing to HTTP callers (paths stripped).
    Audit events are emitted for all security-sensitive actions.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from backend.api.schemas.catalog import (
    CatalogEntryResponse,
    CatalogListResponse,
    CatalogOHLCVCandle,
    CatalogOHLCVResponse,
    RegisterDatasetRequest,
    RegisterDatasetResponse,
)
from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event
from backend.core.request_validation import validate_provider_type
from backend.data.models.dataset import DatasetIdentity
from backend.data.models.instrument import AdjustmentMode, Instrument
from backend.data_providers.base import ProviderFetchError
from backend.data_providers.provider_factory import (
    ProviderAdapterFactory,
    ProviderBuildError,
    UnknownProviderError,
)
from backend.services.ohlcv_service import OHLCVIngestionError, OHLCVService
from backend.storage.dataset_catalog import (
    DatasetCatalog,
    DatasetCatalogError,
    DatasetDisabledError,
    DuplicateDatasetError,
    LocalDatasetEntry,
    UnknownDatasetError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Service-level errors
# ---------------------------------------------------------------------------

class CatalogRegistrationError(Exception):
    """Raised when a registration request cannot be fulfilled."""


class CatalogNotFoundError(Exception):
    """Raised when a catalog_id lookup fails."""


class CatalogDatasetDisabledError(Exception):
    """Raised when a catalog entry exists but is disabled."""


class CatalogFetchError(Exception):
    """Raised when OHLCV retrieval from a catalog entry fails."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_response(entry: LocalDatasetEntry) -> CatalogEntryResponse:
    return CatalogEntryResponse(
        catalog_id=entry.catalog_id,
        provider_type=entry.provider_type,
        display_name=entry.display_name,
        dataset_type=entry.dataset_type,
        asset_class=entry.asset_class,
        timeframe=entry.timeframe,
        symbol=entry.symbol,
        venue=entry.venue,
        adjustment_mode=entry.adjustment_mode,
        registered_at=entry.registered_at,
        enabled=entry.enabled,
        metadata=entry.metadata,
    )


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------

def register_dataset(
    request: RegisterDatasetRequest,
    base_path: Path,
    user_id: str | None = None,
) -> RegisterDatasetResponse:
    """
    Validate and register a local dataset file in the catalog.

    The file must exist on disk; the path is stored internally and
    is never echoed back to callers after this point.

    Args:
        request:   RegisterDatasetRequest with file_path and metadata.
        base_path: Storage base path (catalog lives at base_path/catalog/).

    Returns:
        RegisterDatasetResponse with catalog_id and public metadata.

    Raises:
        CatalogRegistrationError: file not found, duplicate path, or invalid fields.
    """
    # Validate provider type before touching the filesystem or catalog
    try:
        validate_provider_type(request.provider_type)
    except ValueError as exc:
        raise CatalogRegistrationError(str(exc)) from exc

    file_path = Path(request.file_path)
    if not file_path.exists():
        raise CatalogRegistrationError(
            "The specified dataset file was not found on the server."
        )
    if not file_path.is_file():
        raise CatalogRegistrationError(
            "The specified path does not point to a regular file."
        )

    catalog = DatasetCatalog(base_path)
    try:
        entry = catalog.register(
            provider_type=request.provider_type,
            file_path=request.file_path,
            display_name=request.display_name,
            symbol=request.symbol,
            asset_class=request.asset_class,
            venue=request.venue,
            timeframe=request.timeframe,
            dataset_type=request.dataset_type,
            adjustment_mode=request.adjustment_mode,
            metadata=request.metadata,
            user_id=user_id,
        )
    except DuplicateDatasetError as exc:
        raise CatalogRegistrationError(
            "A dataset with this file path is already registered in the catalog."
        ) from exc
    except ValueError as exc:
        raise CatalogRegistrationError(str(exc)) from exc

    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.DATASET_REGISTERED,
        provider_name=entry.provider_type,
        details={
            "catalog_id": entry.catalog_id,
            "symbol": entry.symbol,
            "asset_class": entry.asset_class,
            "timeframe": entry.timeframe,
        },
    ))
    logger.info(
        "catalog_service: registered catalog_id=%s provider=%s symbol=%s timeframe=%s",
        entry.catalog_id, entry.provider_type, entry.symbol, entry.timeframe,
    )
    return RegisterDatasetResponse(
        catalog_id=entry.catalog_id,
        display_name=entry.display_name,
        provider_type=entry.provider_type,
        symbol=entry.symbol,
        asset_class=entry.asset_class,
        venue=entry.venue,
        timeframe=entry.timeframe,
    )


def list_datasets(
    base_path: Path,
    include_disabled: bool = False,
    user_id: str | None = None,
) -> CatalogListResponse:
    """
    Return all (or only enabled) catalog entries.

    Args:
        base_path:        Storage base path.
        include_disabled: If True, include disabled entries.
        user_id:          If provided, filter to only entries owned by this user.

    Returns:
        CatalogListResponse with entries sorted by registration time.
    """
    catalog = DatasetCatalog(base_path)
    entries = (
        catalog.list_all(user_id=user_id)
        if include_disabled
        else catalog.list_enabled(user_id=user_id)
    )
    return CatalogListResponse(
        entries=[_to_response(e) for e in entries],
        count=len(entries),
    )


def get_dataset(
    catalog_id: str,
    base_path: Path,
    owner_id: str | None = None,
) -> CatalogEntryResponse:
    """
    Retrieve public metadata for a catalog entry.

    Raises:
        CatalogNotFoundError:       catalog_id unknown or wrong owner.
        CatalogDatasetDisabledError: entry disabled.
    """
    catalog = DatasetCatalog(base_path)
    try:
        entry = catalog.get(catalog_id, owner_id=owner_id)
    except UnknownDatasetError as exc:
        raise CatalogNotFoundError(str(exc)) from exc
    except DatasetDisabledError as exc:
        raise CatalogDatasetDisabledError(str(exc)) from exc
    return _to_response(entry)


def remove_dataset(
    catalog_id: str,
    base_path: Path,
    owner_id: str | None = None,
) -> None:
    """
    Permanently remove a catalog entry (does not touch the underlying file).

    Raises:
        CatalogNotFoundError: catalog_id unknown or wrong owner.
    """
    catalog = DatasetCatalog(base_path)
    try:
        catalog.remove(catalog_id, owner_id=owner_id)
    except UnknownDatasetError as exc:
        raise CatalogNotFoundError(str(exc)) from exc

    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.DATASET_REMOVED,
        details={"catalog_id": catalog_id},
    ))
    logger.info("catalog_service: removed catalog entry %s", catalog_id)


def fetch_ohlcv(
    catalog_id: str,
    start: datetime,
    end: datetime,
    base_path: Path,
    factory: ProviderAdapterFactory,
    owner_id: str | None = None,
) -> CatalogOHLCVResponse:
    """
    Resolve catalog_id → file_path → provider → OHLCVService → candles.

    file_path is resolved internally and never surfaces in the return value.

    Args:
        catalog_id: Opaque identifier from the catalog.
        start:      Inclusive start (UTC-aware).
        end:        Inclusive end (UTC-aware).
        base_path:  Storage base path.
        factory:    ProviderAdapterFactory (for building local providers).

    Returns:
        CatalogOHLCVResponse with candles.

    Raises:
        CatalogNotFoundError:       catalog_id unknown.
        CatalogDatasetDisabledError: entry disabled.
        CatalogFetchError:          provider build or data fetch failed.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    catalog = DatasetCatalog(base_path)
    try:
        entry = catalog.get(catalog_id, owner_id=owner_id)
    except UnknownDatasetError as exc:
        raise CatalogNotFoundError(str(exc)) from exc
    except DatasetDisabledError as exc:
        raise CatalogDatasetDisabledError(str(exc)) from exc

    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.CATALOG_OHLCV_FETCH,
        provider_name=entry.provider_type,
        details={
            "catalog_id": catalog_id,
            "symbol": entry.symbol,
            "asset_class": entry.asset_class,
            "timeframe": entry.timeframe,
        },
    ))

    # Build provider adapter — file_path resolved here, never leaves this function
    try:
        adapter = factory.build(
            entry.provider_type,
            symbol=entry.symbol,
            asset_class=entry.asset_class,
            venue=entry.venue,
            timeframe=entry.timeframe,
            adjustment_mode=entry.adjustment_mode,
            file_path=entry.file_path,
        )
    except (UnknownProviderError, ProviderBuildError) as exc:
        logger.error(
            "catalog_service: provider build error catalog_id=%s provider=%s: %s",
            catalog_id, entry.provider_type, exc,
        )
        raise CatalogFetchError(
            f"Provider '{entry.provider_type}' could not be initialised for "
            f"catalog entry '{catalog_id}'. Check server logs for details."
        ) from exc

    try:
        adj_mode = AdjustmentMode(entry.adjustment_mode)
    except ValueError:
        adj_mode = AdjustmentMode.ADJUSTED

    instrument = Instrument(
        symbol=entry.symbol,
        asset_class=entry.asset_class,
        exchange=entry.venue,
    )
    identity = DatasetIdentity(
        instrument=instrument,
        provider=entry.provider_type,
        timeframe=entry.timeframe,
        adjustment_mode=adj_mode,
    )

    service = OHLCVService(base_path)
    try:
        records = service.get_ohlcv(identity, start, end, adapter)
    except ProviderFetchError as exc:
        # Log full error internally (may include file path — must not reach caller)
        logger.error(
            "catalog_service: provider fetch error catalog_id=%s provider=%s: %s",
            catalog_id, entry.provider_type, exc,
        )
        raise CatalogFetchError(
            f"Data retrieval failed for catalog entry '{catalog_id}'. "
            "Check server logs for details."
        ) from exc
    except OHLCVIngestionError as exc:
        logger.error(
            "catalog_service: ingestion error catalog_id=%s: %s",
            catalog_id, exc,
        )
        raise CatalogFetchError(
            f"Data ingestion failed for catalog entry '{catalog_id}'. "
            "Check server logs for details."
        ) from exc

    candles = [
        CatalogOHLCVCandle(
            timestamp=r.timestamp,
            open=r.open,
            high=r.high,
            low=r.low,
            close=r.close,
            volume=r.volume,
        )
        for r in records
    ]

    logger.info(
        "catalog_service: fetched %d candles for catalog_id=%s [%s..%s]",
        len(candles), catalog_id, start.date(), end.date(),
    )

    return CatalogOHLCVResponse(
        catalog_id=catalog_id,
        provider_type=entry.provider_type,
        symbol=entry.symbol,
        asset_class=entry.asset_class,
        venue=entry.venue,
        timeframe=entry.timeframe,
        candle_count=len(candles),
        candles=candles,
    )
