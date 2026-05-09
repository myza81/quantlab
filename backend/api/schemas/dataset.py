from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class DatasetInfo(BaseModel):
    dataset_id: str
    asset_class: str
    symbol: str
    timeframe: str


class DatasetListResponse(BaseModel):
    datasets: list[DatasetInfo]
    count: int


class ImportCSVResponse(BaseModel):
    dataset_id: str
    symbol: str
    asset_class: str
    venue: str
    timeframe: str
    record_count: int


class OHLCVCandle(BaseModel):
    """Candle-level data; identity fields (symbol/asset_class/venue/timeframe) live in the envelope."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: Optional[int] = None
    vwap: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None
    adjustment_factor: Optional[float] = None
    metadata: Optional[dict[str, Any]] = None


class DatasetOHLCVResponse(BaseModel):
    dataset_id: str
    symbol: str
    asset_class: str
    venue: str
    timeframe: str
    count: int
    candles: list[OHLCVCandle]
