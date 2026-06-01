"""
Market data API routes — thin layer delegating to market_data_service.

Endpoints:
    GET /market-data/providers   — list registered providers and their capabilities
    GET /market-data/search      — asset search (ticker / company name autocomplete)
    GET /market-data/ohlcv       — fetch normalized OHLCV candles via a provider adapter

Credential-aware OHLCV flow (Phase 3J):
    When `credential_id` is supplied, the endpoint requires a valid Bearer token.
    The service layer resolves the user-owned credential via VaultService before
    constructing the provider adapter.  No secret values appear in the request,
    response, or any log output.

Asset search (Chart-UX-2):
    The search endpoint resolves user queries (ticker prefix, company name, fuzzy)
    to structured asset metadata (symbol, name, exchange, asset_class).

    Providers without search support (csv, parquet) → HTTP 400 with a message
    containing "does not support" — the frontend classifies this as the
    "unsupported provider" state.

    For credentialed providers (polygon), pass credential_id so the vault key
    is resolved and forwarded to the provider searcher.

    Error taxonomy returned to clients:
        unknown provider      → 400 "Provider 'x' is not registered."
        unsupported provider  → 400 "Provider 'x' does not support asset search."
        searcher raised       → 400 "Search failed for provider 'x': <message>"
        0 results             → 200 with results: []
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.schemas.market_data import (
    AssetSearchResponse,
    MarketDataOHLCVResponse,
    ProvidersListResponse,
)
from backend.api.services.asset_search_service import (
    AssetSearchError,
    ProviderSearchNotSupported,
    search_assets,
)
from backend.api.services.market_data_service import (
    MarketDataError,
    UnsupportedProviderError,
    _resolve_provider_api_key,
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


@router.get("/search", response_model=AssetSearchResponse)
def search_market_data(
    q: Annotated[str, Query(description="Search query: ticker symbol or company name")],
    provider: Annotated[str, Query(description="Provider to search through")] = "yahoo",
    limit: Annotated[int, Query(description="Maximum results (1–20)", ge=1, le=20)] = 10,
    credential_id: Annotated[
        Optional[str],
        Query(description="Vault credential_id for user-owned provider API key (e.g. Polygon)"),
    ] = None,
    factory: ProviderAdapterFactory = Depends(get_provider_factory),
    current_user: User = Depends(require_active_subscription),
) -> AssetSearchResponse:
    """
    Search for assets by ticker symbol or company name.

    Returns up to *limit* matching assets with symbol, name, exchange,
    and asset_class populated — removing the need for users to manually
    enter venue information before fetching OHLCV data.

    Providers with no search capability (csv, parquet) return HTTP 400
    with a message containing "does not support asset search".

    For Polygon search, pass credential_id so the API key is resolved
    from the vault and forwarded to the Polygon searcher.
    """
    # Resolve API key for credentialed providers (e.g. Polygon)
    api_key: Optional[str] = None
    if credential_id:
        try:
            api_key = _resolve_provider_api_key(
                provider=provider,
                credential_id=credential_id,
                user_id=current_user.user_id,
            )
        except MarketDataError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return search_assets(
            query=q,
            provider=provider,
            limit=limit,
            factory=factory,
            api_key=api_key,
        )
    except ProviderSearchNotSupported as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AssetSearchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/ohlcv", response_model=MarketDataOHLCVResponse)
def get_ohlcv(
    provider: Annotated[str, Query(description="Data provider name, e.g. 'yahoo'")],
    symbol: Annotated[str, Query(description="Instrument symbol, e.g. 'AAPL'")],
    timeframe: Annotated[str, Query(description="Candle timeframe, e.g. '1d'")],
    start: Annotated[datetime, Query(description="Start datetime (ISO 8601, UTC)")],
    end: Annotated[datetime, Query(description="End datetime (ISO 8601, UTC)")],
    asset_class: Annotated[str, Query(description="Asset class")] = "equity",
    exchange: Annotated[str, Query(description="Exchange or venue (optional — resolved from asset search)")] = "",
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
