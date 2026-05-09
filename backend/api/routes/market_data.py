"""
Market data API route — thin layer delegating to market_data_service.

Endpoint:
    GET /market-data/ohlcv  — fetch normalized OHLCV candles via a provider adapter
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.schemas.market_data import MarketDataOHLCVResponse
from backend.api.services.market_data_service import (
    MarketDataError,
    UnsupportedProviderError,
    fetch_ohlcv,
)
from backend.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market-data", tags=["market-data"])


def get_storage_path() -> Path:
    """Dependency — overridable in tests via app.dependency_overrides."""
    return settings.storage_base_path


@router.get("/ohlcv", response_model=MarketDataOHLCVResponse)
def get_ohlcv(
    provider: Annotated[str, Query(description="Data provider name, e.g. 'yahoo'")],
    symbol: Annotated[str, Query(description="Instrument symbol, e.g. 'AAPL'")],
    timeframe: Annotated[str, Query(description="Candle timeframe, e.g. '1d'")],
    start: Annotated[datetime, Query(description="Start datetime (ISO 8601, UTC)")],
    end: Annotated[datetime, Query(description="End datetime (ISO 8601, UTC)")],
    asset_class: Annotated[str, Query(description="Asset class")] = "equity",
    exchange: Annotated[str, Query(description="Exchange or venue")] = "NASDAQ",
    adjustment_mode: Annotated[str, Query(description="Adjustment mode")] = "adjusted",
    currency: Annotated[str, Query(description="Currency code")] = "USD",
    storage_path: Path = Depends(get_storage_path),
) -> MarketDataOHLCVResponse:
    # Treat naive datetimes from query string as UTC
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    try:
        return fetch_ohlcv(
            provider=provider,
            symbol=symbol,
            asset_class=asset_class,
            exchange=exchange,
            timeframe=timeframe,
            start=start,
            end=end,
            adjustment_mode=adjustment_mode,
            currency=currency,
            storage_path=storage_path,
        )
    except UnsupportedProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MarketDataError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
