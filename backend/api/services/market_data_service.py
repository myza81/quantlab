"""
Market data retrieval service.

Thin orchestration layer between the market-data API route and OHLCVService.
Builds the provider adapter via ProviderAdapterFactory (provider-agnostic),
delegates to OHLCVService.get_ohlcv(), and converts the result to a
frontend-friendly response schema including full fetch traceability metadata.

Architecture contract:
    This module must NOT import from any concrete provider adapter module
    (e.g. backend.data_providers.yahoo.adapter). Provider selection and
    adapter construction are exclusively the factory's responsibility.

    Correct flow:
        route → fetch_ohlcv(..., factory, credential_id, user_id)
              → _resolve_provider_api_key(provider, credential_id, user_id)
              → factory.build(provider, **kwargs, api_key=resolved)
              → OHLCVService.get_ohlcv(adapter)

    Vault integration (Phase 3J):
        When credential_id is provided, _resolve_provider_api_key() uses
        VaultService.resolve_secret() to decrypt the user-owned API key.
        The raw key is passed to factory.build() and never stored or logged.
        When credential_id is absent, factory falls back to ENV resolver.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.api.schemas.market_data import (
    DatasetFetchMetadataResponse,
    MarketDataOHLCVResponse,
    OHLCVCandleResponse,
    ProviderCapabilitiesResponse,
    ProvidersListResponse,
)
from backend.data.models.dataset import DatasetIdentity
from backend.data.models.fetch_identity import build_fetch_identity
from backend.data.models.instrument import AdjustmentMode, Instrument
from backend.data_providers.base import ProviderFetchError
from backend.data_providers.provider_factory import (
    ProviderAdapterFactory,
    ProviderBuildError,
    UnknownProviderError,
)
from backend.services.ohlcv_service import OHLCVIngestionError, OHLCVService

logger = logging.getLogger(__name__)


class MarketDataError(Exception):
    """Raised for recoverable market-data request failures (→ HTTP 400)."""


class UnsupportedProviderError(MarketDataError):
    """Raised when the requested provider is not registered."""


# ---------------------------------------------------------------------------
# Credential resolution helper (vault integration)
# ---------------------------------------------------------------------------

def _resolve_provider_api_key(
    *,
    provider: str,
    credential_id: Optional[str],
    user_id: Optional[str],
) -> Optional[str]:
    """
    Resolve an API key for user-owned provider access via the credential vault.

    Returns:
        Raw decrypted API key string if *credential_id* is provided and
        resolution succeeds.  Returns None when *credential_id* is absent —
        the factory will fall back to its ENV-based resolver.

    INVARIANT: the return value is a raw secret — callers must not log it,
    include it in responses, or pass it beyond the factory.build() call.

    Raises:
        MarketDataError: authentication required, access denied, disabled
                         credential, provider mismatch, or decryption failure.
                         All messages are sanitized — no secret material.
    """
    if not credential_id:
        return None

    if not user_id:
        raise MarketDataError(
            "Authentication required to use user-owned provider credentials"
        )

    from backend.vault.crypto import VaultCryptoError
    from backend.vault.repository import CredentialRepository
    from backend.vault.service import (
        CredentialAccessDeniedError,
        CredentialDisabledError,
        CredentialProviderMismatchError,
        VaultService,
    )
    from backend.core.config import settings

    repo = CredentialRepository(settings.credentials_file_path)
    vault = VaultService(repo)

    try:
        return vault.resolve_secret(
            credential_id=credential_id,
            requesting_user_id=user_id,
            provider_name=provider,
        )
    except CredentialAccessDeniedError:
        raise MarketDataError("Provider credential not found or access denied")
    except CredentialDisabledError:
        raise MarketDataError("Provider credential is disabled")
    except CredentialProviderMismatchError:
        raise MarketDataError("Credential is not registered for this provider")
    except VaultCryptoError:
        raise MarketDataError("Provider credential could not be resolved")


def fetch_ohlcv(
    *,
    provider: str,
    symbol: str,
    asset_class: str,
    exchange: str = "",
    timeframe: str,
    start: datetime,
    end: datetime,
    adjustment_mode: str = "adjusted",
    currency: str = "USD",
    storage_path: Path,
    factory: ProviderAdapterFactory,
    credential_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> MarketDataOHLCVResponse:
    """
    Fetch OHLCV candles for the given parameters via OHLCVService.

    Args:
        provider:        Provider name (routed through factory, e.g. "yahoo").
        symbol:          Instrument symbol, e.g. "AAPL".
        asset_class:     e.g. "equity", "crypto".
        exchange:        Exchange/venue, e.g. "NYSE". Optional — when omitted or
                         empty the service defaults to "unknown" for fingerprinting
                         and storage. Yahoo Finance does not require exchange to
                         fetch data; it is used only as traceability metadata.
        timeframe:       e.g. "1d", "1h".
        start:           Inclusive start — must be UTC-aware.
        end:             Inclusive end — must be UTC-aware.
        adjustment_mode: "adjusted" | "raw" | "split_adjusted".
        currency:        Currency code, e.g. "USD".
        storage_path:    Base path for Parquet storage.
        factory:         ProviderAdapterFactory — resolves provider name to adapter.
        credential_id:   Optional vault credential_id for user-owned provider auth.
                         When provided, the user's stored API key is resolved via
                         VaultService and passed to the factory builder.
        user_id:         Authenticated user_id; required when credential_id is given.

    Returns:
        MarketDataOHLCVResponse with normalized candles.

    Raises:
        UnsupportedProviderError: provider not registered in factory.
        MarketDataError:          invalid timeframe, provider fetch failure,
                                  or credential resolution failure.
    """
    # Normalize exchange: empty/blank is valid (user did not supply it).
    # Use "unknown" as the storage and fingerprint value so downstream
    # validators (which require non-empty exchange) remain satisfied.
    # Existing callers that supply a real exchange are unaffected.
    effective_exchange = exchange.strip() or "unknown"

    # Resolve user-owned API key before building the adapter.
    # Returns None for non-vault providers → factory uses its own resolver.
    api_key = _resolve_provider_api_key(
        provider=provider,
        credential_id=credential_id,
        user_id=user_id,
    )

    try:
        adapter = factory.build(
            provider,
            symbol=symbol,
            asset_class=asset_class,
            venue=effective_exchange,
            timeframe=timeframe,
            adjustment_mode=adjustment_mode,
            api_key=api_key,
        )
    except UnknownProviderError as exc:
        raise UnsupportedProviderError(str(exc)) from exc
    except ProviderBuildError as exc:
        raise MarketDataError(str(exc)) from exc

    try:
        adj_mode = AdjustmentMode(adjustment_mode)
    except ValueError:
        adj_mode = AdjustmentMode.ADJUSTED

    instrument = Instrument(
        symbol=symbol,
        asset_class=asset_class,
        exchange=effective_exchange,
        currency=currency,
    )
    identity = DatasetIdentity(
        instrument=instrument,
        provider=provider,
        timeframe=timeframe,
        adjustment_mode=adj_mode,
    )

    fetch_identity = build_fetch_identity(
        provider=provider,
        symbol=symbol,
        asset_class=asset_class,
        exchange=effective_exchange,
        timeframe=timeframe,
        start=start,
        end=end,
        adjustment_mode=adj_mode,
        dataset_id=identity.dataset_id,
    )

    service = OHLCVService(storage_path)
    try:
        candles = service.get_ohlcv(
            identity, start, end, adapter,
            fetch_fingerprint=fetch_identity.fingerprint,
        )
    except ProviderFetchError as exc:
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

    fetch_metadata = DatasetFetchMetadataResponse(
        dataset_id=fetch_identity.dataset_id,
        fingerprint=fetch_identity.fingerprint,
        provider=provider,
        symbol=symbol,
        asset_class=asset_class,
        exchange=effective_exchange,
        timeframe=timeframe,
        start_utc=start.astimezone(timezone.utc).isoformat(),
        end_utc=end.astimezone(timezone.utc).isoformat(),
        adjustment_mode=adj_mode.value,
        schema_version=fetch_identity.schema_version,
    )

    logger.info(
        "market_data_service: fetched %d candles for %s/%s/%s [%s..%s] fingerprint=%s",
        len(candle_responses),
        provider,
        symbol,
        timeframe,
        start.date(),
        end.date(),
        fetch_identity.fingerprint[:12],
    )

    return MarketDataOHLCVResponse(
        provider=provider,
        symbol=symbol,
        asset_class=asset_class,
        exchange=effective_exchange,
        timeframe=timeframe,
        start=start,
        end=end,
        candle_count=len(candle_responses),
        candles=candle_responses,
        fetch_metadata=fetch_metadata,
    )


def list_providers(factory: ProviderAdapterFactory) -> ProvidersListResponse:
    """
    Return lightweight capability metadata for all registered providers.

    Args:
        factory: ProviderAdapterFactory to query for registered providers.

    Returns:
        ProvidersListResponse listing each provider's id, name, and capabilities.
    """
    caps = factory.list_capabilities()
    return ProvidersListResponse(
        providers=[
            ProviderCapabilitiesResponse(
                provider_id=c.provider_id,
                display_name=c.display_name,
                supported_timeframes=list(c.supported_timeframes),
                supported_asset_classes=list(c.supported_asset_classes),
                supports_search=c.supports_search,
            )
            for c in caps
        ]
    )
