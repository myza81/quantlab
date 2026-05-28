"""
Dataset Catalog API routes — thin layer delegating to catalog_service.

Endpoints:
    POST   /catalog/datasets               — register a local file as a catalog entry
    GET    /catalog/datasets               — list catalog entries (enabled by default)
    GET    /catalog/datasets/{catalog_id}  — get one entry's public metadata
    DELETE /catalog/datasets/{catalog_id}  — permanently remove an entry
    GET    /catalog/datasets/{catalog_id}/ohlcv — fetch candles by catalog_id
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.schemas.catalog import (
    CatalogListResponse,
    CatalogOHLCVResponse,
    CatalogEntryResponse,
    RegisterDatasetRequest,
    RegisterDatasetResponse,
)
from backend.api.services import catalog_service
from backend.api.services.catalog_service import (
    CatalogDatasetDisabledError,
    CatalogFetchError,
    CatalogNotFoundError,
    CatalogRegistrationError,
)
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.core.config import settings
from backend.core.request_validation import validate_date_range
from backend.data_providers.provider_factory import (
    ProviderAdapterFactory,
    create_default_factory_registry,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/catalog", tags=["catalog"])


def get_storage_path() -> Path:
    """Dependency — overridable in tests via app.dependency_overrides."""
    return settings.storage_base_path


def get_provider_factory() -> ProviderAdapterFactory:
    """Dependency — overridable in tests via app.dependency_overrides."""
    return create_default_factory_registry()


@router.post("/datasets", response_model=RegisterDatasetResponse, status_code=201)
def register_dataset(
    request: RegisterDatasetRequest,
    storage_path: Path = Depends(get_storage_path),
    current_user: User = Depends(require_active_subscription),
) -> RegisterDatasetResponse:
    """Register a local file (CSV or Parquet) as a named catalog entry."""
    try:
        return catalog_service.register_dataset(request, storage_path, user_id=current_user.user_id)
    except CatalogRegistrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/datasets", response_model=CatalogListResponse)
def list_datasets(
    include_disabled: Annotated[bool, Query(description="Include disabled entries")] = False,
    storage_path: Path = Depends(get_storage_path),
    current_user: User = Depends(require_active_subscription),
) -> CatalogListResponse:
    """List catalog entries.  Excludes disabled entries by default."""
    return catalog_service.list_datasets(
        storage_path,
        include_disabled=include_disabled,
        user_id=current_user.user_id,
    )


@router.get("/datasets/{catalog_id}", response_model=CatalogEntryResponse)
def get_dataset(
    catalog_id: str,
    storage_path: Path = Depends(get_storage_path),
    current_user: User = Depends(require_active_subscription),
) -> CatalogEntryResponse:
    """Return public metadata for a single catalog entry."""
    try:
        return catalog_service.get_dataset(catalog_id, storage_path, owner_id=current_user.user_id)
    except CatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CatalogDatasetDisabledError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc


@router.delete("/datasets/{catalog_id}", status_code=204)
def remove_dataset(
    catalog_id: str,
    storage_path: Path = Depends(get_storage_path),
    current_user: User = Depends(require_active_subscription),
) -> None:
    """Permanently remove a catalog entry (does not touch the underlying file)."""
    try:
        catalog_service.remove_dataset(catalog_id, storage_path, owner_id=current_user.user_id)
    except CatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/datasets/{catalog_id}/ohlcv", response_model=CatalogOHLCVResponse)
def get_catalog_ohlcv(
    catalog_id: str,
    start: Annotated[datetime, Query(description="Start datetime (ISO 8601, UTC)")],
    end: Annotated[datetime, Query(description="End datetime (ISO 8601, UTC)")],
    storage_path: Path = Depends(get_storage_path),
    factory: ProviderAdapterFactory = Depends(get_provider_factory),
    current_user: User = Depends(require_active_subscription),
) -> CatalogOHLCVResponse:
    """Fetch OHLCV candles for a catalog entry, identified by catalog_id."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    try:
        validate_date_range(start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return catalog_service.fetch_ohlcv(
            catalog_id=catalog_id,
            start=start,
            end=end,
            base_path=storage_path,
            factory=factory,
            owner_id=current_user.user_id,
        )
    except CatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CatalogDatasetDisabledError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except CatalogFetchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
