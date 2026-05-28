"""
API schemas for the Dataset Catalog endpoints.

IMPORTANT: file_path is intentionally absent from all response schemas.
    Raw filesystem paths must remain backend-only.
    Consumers interact exclusively through catalog_id and metadata.
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class RegisterDatasetRequest(BaseModel):
    """Input for POST /catalog/datasets — registers a local file by path."""
    provider_type: str          # "csv" | "parquet"
    file_path: str              # backend-only; not echoed in responses
    display_name: str
    symbol: str
    asset_class: str
    venue: str
    timeframe: str
    dataset_type: str = "ohlcv"
    adjustment_mode: str = "adjusted"
    metadata: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class CatalogEntryResponse(BaseModel):
    """Single catalog entry — no file_path."""
    catalog_id: str
    provider_type: str
    display_name: str
    dataset_type: str
    asset_class: str
    timeframe: str
    symbol: str
    venue: str
    adjustment_mode: str
    registered_at: datetime
    enabled: bool
    metadata: Optional[dict[str, Any]] = None


class CatalogListResponse(BaseModel):
    entries: list[CatalogEntryResponse]
    count: int


class RegisterDatasetResponse(BaseModel):
    catalog_id: str
    display_name: str
    provider_type: str
    symbol: str
    asset_class: str
    venue: str
    timeframe: str


class CatalogOHLCVCandle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class CatalogOHLCVResponse(BaseModel):
    catalog_id: str
    provider_type: str
    symbol: str
    asset_class: str
    venue: str
    timeframe: str
    candle_count: int
    candles: list[CatalogOHLCVCandle]
