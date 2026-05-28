"""
Provider adapter factory — routes provider names to per-request adapter instances.

This module is the isolation boundary between API service layers and concrete
provider SDK imports. API services know a provider name and request parameters;
the factory knows which adapter class to construct and how to map parameters.

Correct flow:
    API service → ProviderAdapterFactory.build("yahoo", symbol=...) → RangeProviderAdapter

NOT:
    API service → YahooFinanceAdapter(symbol=...) directly

Supported providers:
    yahoo   — Yahoo Finance via yfinance
    csv     — Local CSV file (requires file_path kwarg)
    parquet — Local Parquet file (requires file_path kwarg)
    polygon — Polygon.io REST API
                Primary path:   api_key kwarg pre-resolved via VaultService (Phase 3J+)
                Fallback path:  POLYGON_API_KEY env var (transitional backward compat)

Architecture boundary:
    This module imports concrete adapter classes so API services do not have to.
    No concrete adapter import should appear in backend/api/services/.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from backend.data_providers.base import ProviderCapabilities, ProviderFetchError
from backend.data_providers.range_provider import RangeProviderAdapter

logger = logging.getLogger(__name__)


class ProviderBuildError(Exception):
    """Raised when adapter construction fails due to invalid parameters."""


class UnknownProviderError(Exception):
    """Raised when a requested provider is not registered in the factory."""


class ProviderAdapterFactory:
    """
    In-process registry of provider capabilities and adapter builders.

    Callers register providers at startup (once) and call build() per request.
    Each call to build() constructs a fresh adapter instance with request-time
    parameters — providers like Yahoo require per-request configuration
    (symbol, timeframe) that cannot be fixed at registration time.

    Thread-safety: registration is intended for single-threaded startup;
    build() calls are read-only and safe for concurrent use after setup.
    """

    def __init__(self) -> None:
        self._capabilities: dict[str, ProviderCapabilities] = {}
        self._builders: dict[str, Callable[..., RangeProviderAdapter]] = {}

    def register(
        self,
        provider_id: str,
        capabilities: ProviderCapabilities,
        builder: Callable[..., RangeProviderAdapter],
    ) -> None:
        """
        Register a provider with its capability descriptor and adapter builder.

        Args:
            provider_id:  Canonical provider name (normalised to lowercase).
            capabilities: Static capability descriptor for this provider.
            builder:      Callable that accepts request kwargs and returns a
                          RangeProviderAdapter instance.

        Raises:
            ValueError: if provider_id is empty or already registered.
        """
        key = provider_id.strip().lower()
        if not key:
            raise ValueError("provider_id must not be empty")
        if key in self._capabilities:
            raise ValueError(
                f"Provider '{key}' is already registered in the factory. "
                "Deregister it first."
            )
        self._capabilities[key] = capabilities
        self._builders[key] = builder
        logger.debug("ProviderAdapterFactory: registered provider '%s'", key)

    def build(self, provider_id: str, **kwargs: Any) -> RangeProviderAdapter:
        """
        Construct and return a RangeProviderAdapter for the given provider.

        Args:
            provider_id: Provider name (case-insensitive).
            **kwargs:    Request-time parameters forwarded to the builder
                         (e.g. symbol, timeframe, asset_class, venue).

        Returns:
            A RangeProviderAdapter ready to serve fetch() calls.

        Raises:
            UnknownProviderError: if provider_id is not registered.
            ProviderBuildError:   if the builder raises ValueError
                                  (e.g. unsupported timeframe).
        """
        key = provider_id.strip().lower()
        builder = self._builders.get(key)
        if builder is None:
            available = sorted(self._capabilities)
            raise UnknownProviderError(
                f"Provider '{key}' is not registered. "
                f"Registered providers: {available}"
            )
        try:
            return builder(**kwargs)
        except ValueError as exc:
            raise ProviderBuildError(str(exc)) from exc

    def get_capabilities(self, provider_id: str) -> ProviderCapabilities:
        """
        Return the ProviderCapabilities descriptor for a registered provider.

        Raises:
            UnknownProviderError: if provider_id is not registered.
        """
        key = provider_id.strip().lower()
        caps = self._capabilities.get(key)
        if caps is None:
            available = sorted(self._capabilities)
            raise UnknownProviderError(
                f"Provider '{key}' is not registered. "
                f"Registered providers: {available}"
            )
        return caps

    def list_capabilities(self) -> list[ProviderCapabilities]:
        """Return a list of ProviderCapabilities for all registered providers."""
        return sorted(self._capabilities.values(), key=lambda c: c.provider_id)

    def __contains__(self, provider_id: object) -> bool:
        if not isinstance(provider_id, str):
            return False
        return provider_id.strip().lower() in self._capabilities

    def __len__(self) -> int:
        return len(self._capabilities)


# ---------------------------------------------------------------------------
# Default registry
# ---------------------------------------------------------------------------

_YAHOO_CAPABILITIES = ProviderCapabilities(
    provider_id="yahoo",
    display_name="Yahoo Finance",
    supported_timeframes=("1M", "1d", "1h", "1m", "1w", "15m", "30m", "5m"),
    supported_asset_classes=("crypto", "equity", "etf", "fx", "fund", "future", "index"),
)


def _build_yahoo_adapter(
    *,
    symbol: str,
    timeframe: str,
    asset_class: str = "equity",
    venue: str = "NASDAQ",
    adjustment_mode: str = "adjusted",
    **_ignored: Any,
) -> RangeProviderAdapter:
    from backend.data_providers.yahoo.adapter import YahooFinanceAdapter

    return YahooFinanceAdapter(
        symbol=symbol,
        asset_class=asset_class,
        venue=venue,
        timeframe=timeframe,
        adjustment_mode=adjustment_mode,
    )


_CSV_CAPABILITIES = ProviderCapabilities(
    provider_id="csv",
    display_name="Local CSV File",
    supported_timeframes=(
        "1M", "1d", "1h", "1m", "1w",
        "12h", "15m", "2h", "30m", "3d", "3m", "4h", "5m", "6h", "8h",
    ),
    supported_asset_classes=(
        "crypto", "equity", "etf", "fx", "fund", "futures", "index",
    ),
)


def _build_csv_provider(
    *,
    symbol: str,
    asset_class: str = "equity",
    venue: str = "NASDAQ",
    timeframe: str = "1d",
    adjustment_mode: str = "adjusted",
    file_path: Any = None,
    **_ignored: Any,
) -> RangeProviderAdapter:
    if not file_path:
        raise ValueError(
            "csv provider requires 'file_path' kwarg — "
            "pass the path to the CSV file when calling factory.build()"
        )
    from backend.data_providers.local.csv_provider import LocalCSVProvider

    return LocalCSVProvider(
        file_path=file_path,
        symbol=symbol,
        asset_class=asset_class,
        venue=venue,
        timeframe=timeframe,
        adjustment_mode=adjustment_mode,
    )


_PARQUET_CAPABILITIES = ProviderCapabilities(
    provider_id="parquet",
    display_name="Local Parquet File",
    supported_timeframes=(
        "1M", "1d", "1h", "1m", "1w",
        "12h", "15m", "2h", "30m", "3d", "3m", "4h", "5m", "6h", "8h",
    ),
    supported_asset_classes=(
        "crypto", "equity", "etf", "fx", "fund", "futures", "index",
    ),
)


def _build_parquet_provider(
    *,
    symbol: str,
    asset_class: str = "equity",
    venue: str = "NASDAQ",
    timeframe: str = "1d",
    adjustment_mode: str = "adjusted",
    file_path: Any = None,
    **_ignored: Any,
) -> RangeProviderAdapter:
    if not file_path:
        raise ValueError(
            "parquet provider requires 'file_path' kwarg — "
            "pass the path to the Parquet file when calling factory.build()"
        )
    from backend.data_providers.local.parquet_provider import LocalParquetProvider

    return LocalParquetProvider(
        file_path=file_path,
        symbol=symbol,
        asset_class=asset_class,
        venue=venue,
        timeframe=timeframe,
        adjustment_mode=adjustment_mode,
    )


_POLYGON_CAPABILITIES = ProviderCapabilities(
    provider_id="polygon",
    display_name="Polygon.io",
    supported_timeframes=(
        "1M", "1d", "1h", "1m", "1w",
        "12h", "15m", "2h", "30m", "3d", "3m", "4h", "5m", "6h", "8h",
    ),
    supported_asset_classes=("crypto", "equity", "etf", "fx", "index"),
)


def _build_polygon_adapter(
    *,
    symbol: str,
    asset_class: str = "equity",
    venue: str = "NASDAQ",
    timeframe: str = "1d",
    adjustment_mode: str = "adjusted",
    api_key: str | None = None,
    **_ignored: Any,
) -> RangeProviderAdapter:
    """
    Build a PolygonProviderAdapter.

    Credential resolution order:
      1. Primary path (Phase 3J+): *api_key* kwarg pre-resolved by the service
         layer via VaultService.resolve_secret().  Caller is responsible for
         ownership/active/provider-match checks before passing the key here.
      2. Transitional ENV fallback: when *api_key* is None or empty, reads
         POLYGON_API_KEY from the environment via EnvironmentCredentialResolver.
         Preserved for backward compatibility and headless/server deployments;
         will be removed once all integrations are migrated to the vault.

    INVARIANT: the resolved key is never logged or included in error messages.
    """
    if api_key:
        resolved_key = api_key
    else:
        # Transitional fallback — ENV-based resolver.
        from backend.core.credentials import (
            CredentialSpec,
            EnvironmentCredentialResolver,
            MissingCredentialError,
        )
        _spec = CredentialSpec(
            provider_name="polygon",
            credential_key="POLYGON_API_KEY",
            description="Polygon.io API key — transitional ENV path (migrate to vault)",
        )
        try:
            resolved_key = EnvironmentCredentialResolver().resolve(_spec)
        except MissingCredentialError as exc:
            raise ProviderBuildError(str(exc)) from exc

    from backend.data_providers.polygon.adapter import PolygonProviderAdapter

    return PolygonProviderAdapter(
        symbol=symbol,
        asset_class=asset_class,
        venue=venue,
        timeframe=timeframe,
        adjustment_mode=adjustment_mode,
        api_key=resolved_key,
    )


def create_default_factory_registry() -> ProviderAdapterFactory:
    """
    Create and return a ProviderAdapterFactory with built-in providers registered.

    Registered providers:
        yahoo   — Yahoo Finance via yfinance
        csv     — Local CSV file (requires file_path kwarg at build time)
        parquet — Local Parquet file (requires file_path kwarg at build time)
        polygon — Polygon.io REST API
                    Pass api_key kwarg (pre-resolved via VaultService) for primary path.
                    Falls back to POLYGON_API_KEY env var if api_key is absent.

    Future providers (Binance, IBKR) can be registered here without
    touching any API service or route code.
    """
    factory = ProviderAdapterFactory()
    factory.register("yahoo", _YAHOO_CAPABILITIES, _build_yahoo_adapter)
    factory.register("csv", _CSV_CAPABILITIES, _build_csv_provider)
    factory.register("parquet", _PARQUET_CAPABILITIES, _build_parquet_provider)
    factory.register("polygon", _POLYGON_CAPABILITIES, _build_polygon_adapter)
    return factory
