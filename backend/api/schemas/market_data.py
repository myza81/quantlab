from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OHLCVCandleResponse(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class DatasetFetchMetadataResponse(BaseModel):
    """
    Provider traceability metadata attached to a completed OHLCV fetch.

    Exposes the full normalized fetch identity — dataset_id, deterministic
    fingerprint, all request parameters, and schema version — so that
    callers can audit, reproduce, and trace any fetch result back to its
    origin without importing provider-specific modules.
    """
    dataset_id: str
    fingerprint: str
    provider: str
    symbol: str
    asset_class: str
    exchange: str
    timeframe: str
    start_utc: str
    end_utc: str
    adjustment_mode: str
    schema_version: str


class MarketDataOHLCVResponse(BaseModel):
    provider: str
    symbol: str
    asset_class: str
    exchange: str
    timeframe: str
    start: datetime
    end: datetime
    candle_count: int
    candles: list[OHLCVCandleResponse]
    fetch_metadata: DatasetFetchMetadataResponse | None = None


class ProviderCapabilitiesResponse(BaseModel):
    provider_id: str
    display_name: str
    supported_timeframes: list[str]
    supported_asset_classes: list[str]
    supports_search: bool = False


class ProvidersListResponse(BaseModel):
    providers: list[ProviderCapabilitiesResponse]


class AssetSearchResult(BaseModel):
    """
    One asset returned by the asset search endpoint.

    Provides all metadata required to populate a subsequent OHLCV fetch
    without the user manually entering exchange or asset_class.
    """
    symbol:      str
    name:        str
    exchange:    str
    asset_class: str
    currency:    str
    type_label:  str


class AssetSearchResponse(BaseModel):
    """
    Response envelope for GET /market-data/search.

    Designed as a platform-wide reusable contract — Chart, Backtesting,
    Strategy Composer, Forward Testing, and Paper Trading all share this schema.
    """
    query:    str
    provider: str
    results:  list[AssetSearchResult] = Field(default_factory=list)
