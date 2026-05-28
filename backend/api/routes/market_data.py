"""
Market data API routes — thin layer delegating to market_data_service.

Endpoints:
    GET /market-data/providers   — list registered providers and their capabilities
    GET /market-data/ohlcv       — fetch normalized OHLCV candles via a provider adapter

Credential-aware OHLCV flow (Phase 3J):
    When `credential_id` is supplied, the endpoint requires a valid Bearer token.
    The service layer resolves the user-owned credential via VaultService before
    constructing the provider adapter.  No secret values appear in the request,
    response, or any log output.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.schemas.market_data import (
    MarketDataOHLCVResponse,
    ProvidersListResponse,
)
from backend.api.services.market_data_service import (
    MarketDataError,
    UnsupportedProviderError,
    fetch_ohlcv,
    list_providers,
)
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.core.config import settings
from backend.data_providers.provider_factory import (
    ProviderAdapterFactory,
    create_default_factory_registry,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market-data", tags=["market-data"])


def get_storage_path() -> Path:
    """Dependency — overridable in tests via app.dependency_overrides."""
    return settings.storage_base_path


def get_provider_factory() -> ProviderAdapterFactory:
    """Dependency — overridable in tests via app.dependency_overrides."""
    return create_default_factory_registry()


@router.get("/providers", response_model=ProvidersListResponse)
def get_providers(
    factory: ProviderAdapterFactory = Depends(get_provider_factory),
) -> ProvidersListResponse:
    """List all registered data providers and their capabilities."""
    return list_providers(factory)


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
    credential_id: Annotated[
        Optional[str],
        Query(description="Vault credential_id for user-owned provider API key"),
    ] = None,
    storage_path: Path = Depends(get_storage_path),
    factory: ProviderAdapterFactory = Depends(get_provider_factory),
    current_user: User = Depends(require_active_subscription),
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
            factory=factory,
            credential_id=credential_id,
            user_id=current_user.user_id,
        )
    except UnsupportedProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MarketDataError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
