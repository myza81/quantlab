"""
Dataset API routes — DEPRECATED (Phase 3S-D).

These routes predate the governed dataset catalog system (/catalog/*).
They are retained for backward compatibility but:
  - all routes now require require_active_subscription
  - no new functionality will be added here
  - callers should migrate to /catalog/* endpoints

Canonical dataset workflow: POST/GET/DELETE /catalog/datasets

Endpoints (deprecated):
    POST /datasets/import/csv          — import CSV → Parquet (deprecated: use catalog)
    GET  /datasets                     — list stored datasets (deprecated: use catalog)
    GET  /datasets/{dataset_id}/ohlcv  — read candle data (deprecated: use catalog)
"""
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from backend.api.schemas.dataset import (
    DatasetListResponse,
    DatasetOHLCVResponse,
    ImportCSVResponse,
)
from backend.api.services import dataset_service
from backend.api.services.dataset_service import (
    DatasetImportError,
    DatasetNotFoundError,
    parse_dataset_id,
)
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.core.config import settings
from backend.data_providers.csv_adapter import CSVColumnMap

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["datasets-deprecated"])


def get_storage_path() -> Path:
    """Dependency — overridable in tests via app.dependency_overrides."""
    return settings.storage_base_path


@router.post("/import/csv", response_model=ImportCSVResponse, status_code=201)
async def import_csv(
    file: UploadFile,
    symbol: str = Form(...),
    asset_class: str = Form(...),
    venue: str = Form(...),
    timeframe: str = Form(...),
    source: str = Form(...),
    timestamp_col: str = Form("timestamp"),
    open_col: str = Form("open"),
    high_col: str = Form("high"),
    low_col: str = Form("low"),
    close_col: str = Form("close"),
    volume_col: str = Form("volume"),
    storage_path: Path = Depends(get_storage_path),
    current_user: User = Depends(require_active_subscription),
) -> ImportCSVResponse:
    file_bytes = await file.read()
    column_map = CSVColumnMap(
        timestamp=timestamp_col,
        open=open_col,
        high=high_col,
        low=low_col,
        close=close_col,
        volume=volume_col,
    )
    try:
        return dataset_service.import_csv(
            file_bytes=file_bytes,
            symbol=symbol,
            asset_class=asset_class,
            venue=venue,
            timeframe=timeframe,
            source=source,
            column_map=column_map,
            base_path=storage_path,
        )
    except DatasetImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=DatasetListResponse)
def list_datasets(
    storage_path: Path = Depends(get_storage_path),
    current_user: User = Depends(require_active_subscription),
) -> DatasetListResponse:
    return dataset_service.list_datasets(storage_path)


@router.get("/{dataset_id}/ohlcv", response_model=DatasetOHLCVResponse)
def get_ohlcv(
    dataset_id: str,
    storage_path: Path = Depends(get_storage_path),
    current_user: User = Depends(require_active_subscription),
) -> DatasetOHLCVResponse:
    try:
        asset_class, symbol, timeframe = parse_dataset_id(dataset_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return dataset_service.read_ohlcv(storage_path, asset_class, symbol, timeframe)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
