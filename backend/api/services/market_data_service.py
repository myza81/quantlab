"""
Market data retrieval service.

Thin orchestration layer between the market-data API route and OHLCVService.
Builds the provider adapter and DatasetIdentity from request parameters,
delegates to OHLCVService.get_ohlcv(), and converts the result to a
frontend-friendly response schema.

Allowed providers in this phase: yahoo
"""
import logging
from datetime import datetime
from pathlib import Path

from backend.api.schemas.market_data import MarketDataOHLCVResponse, OHLCVCandleResponse
from backend.data.models.dataset import DatasetIdentity
from backend.data.models.instrument import AdjustmentMode, Instrument
from backend.data_providers.yahoo.adapter import YahooAdapterError, YahooFinanceAdapter
from backend.services.ohlcv_service import OHLCVIngestionError, OHLCVService

logger = logging.getLogger(__name__)

_SUPPORTED_PROVIDERS = frozenset({"yahoo"})


class MarketDataError(Exception):
    """Raised for recoverable market-data request failures (→ HTTP 400)."""


class UnsupportedProviderError(MarketDataError):
    """Raised when the requested provider is not registered."""


def fetch_ohlcv(
    *,
    provider: str,
    symbol: str,
    asset_class: str,
    exchange: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    adjustment_mode: str = "adjusted",
    currency: str = "USD",
    storage_path: Path,
) -> MarketDataOHLCVResponse:
    """
    Fetch OHLCV candles for the given parameters via OHLCVService.

    Args:
        provider:        Provider name (currently only "yahoo").
        symbol:          Instrument symbol, e.g. "AAPL".
        asset_class:     e.g. "equity", "crypto".
        exchange:        Exchange/venue, e.g. "NASDAQ".
        timeframe:       e.g. "1d", "1h".
        start:           Inclusive start — must be UTC-aware.
        end:             Inclusive end — must be UTC-aware.
        adjustment_mode: "adjusted" | "raw" | "split_adjusted".
        currency:        Currency code, e.g. "USD".
        storage_path:    Base path for Parquet storage.

    Returns:
        MarketDataOHLCVResponse with normalized candles.

    Raises:
        UnsupportedProviderError: provider not in supported set.
        MarketDataError:          invalid timeframe or provider fetch failure.
    """
    if provider not in _SUPPORTED_PROVIDERS:
        raise UnsupportedProviderError(
            f"Provider '{provider}' is not supported. "
            f"Supported providers: {sorted(_SUPPORTED_PROVIDERS)}"
        )

    try:
        adj_mode = AdjustmentMode(adjustment_mode)
    except ValueError:
        adj_mode = AdjustmentMode.ADJUSTED

    try:
        adapter = YahooFinanceAdapter(
            symbol=symbol,
            asset_class=asset_class,
            venue=exchange,
            timeframe=timeframe,
            adjustment_mode=adjustment_mode,
        )
    except ValueError as exc:
        raise MarketDataError(str(exc)) from exc

    instrument = Instrument(
        symbol=symbol,
        asset_class=asset_class,
        exchange=exchange,
        currency=currency,
    )
    identity = DatasetIdentity(
        instrument=instrument,
        provider=provider,
        timeframe=timeframe,
        adjustment_mode=adj_mode,
    )

    service = OHLCVService(storage_path)
    try:
        candles = service.get_ohlcv(identity, start, end, adapter)
    except YahooAdapterError as exc:
        raise MarketDataError(f"Provider fetch failed: {exc}") from exc
    except OHLCVIngestionError as exc:
        raise MarketDataError(f"Data ingestion failed: {exc}") from exc

    candle_responses = [
        OHLCVCandleResponse(
            timestamp=c.timestamp,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            volume=c.volume,
        )
        for c in candles
    ]

    logger.info(
        "market_data_service: fetched %d candles for %s/%s/%s [%s..%s]",
        len(candle_responses),
        provider,
        symbol,
        timeframe,
        start.date(),
        end.date(),
    )

    return MarketDataOHLCVResponse(
        provider=provider,
        symbol=symbol,
        asset_class=asset_class,
        exchange=exchange,
        timeframe=timeframe,
        start=start,
        end=end,
        candle_count=len(candle_responses),
        candles=candle_responses,
    )
