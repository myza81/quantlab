from datetime import datetime

from pydantic import BaseModel


class OHLCVCandleResponse(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


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
