from datetime import datetime
from typing import Any

from pydantic import BaseModel


class StrategyRunRequest(BaseModel):
    strategy_id: str
    provider: str
    symbol: str
    timeframe: str
    start: datetime
    end: datetime
    asset_class: str = "equity"
    exchange: str = "NASDAQ"
    parameters: dict[str, Any] = {}


class SignalResponse(BaseModel):
    strategy_id: str
    timestamp: datetime
    symbol: str
    timeframe: str
    signal_type: str
    entry_reference: float
    invalidation_level: float
    confidence: float | None = None
    reasoning: str | None = None


class ForecastResponse(BaseModel):
    generated_at: datetime
    target_timestamp: datetime
    target_price: float
    direction: str
    confidence: float
    invalidation_price: float | None = None
    reason: str | None = None


class IndicatorPointResponse(BaseModel):
    timestamp: datetime
    value: float


class IndicatorSeriesResponse(BaseModel):
    name: str
    kind: str
    pane: str
    color: str | None = None
    points: list[IndicatorPointResponse]


class StrategyRunResponse(BaseModel):
    strategy_id: str
    status: str
    candles_received: int
    signals: list[SignalResponse]
    forecasts: list[ForecastResponse]
    indicators: list[IndicatorSeriesResponse] = []
    warnings: list[str]
    error: str | None = None
