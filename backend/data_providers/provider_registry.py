"""
Provider registry — resolves RangeProviderAdapter instances by provider name.

Sits between OHLCVService and concrete provider adapters. Callers register
adapters at startup and resolve them by name at call time, which keeps
OHLCVService decoupled from any specific provider SDK.

Expected call pattern:

    registry = ProviderRegistry()
    registry.register("yahoo", YahooFinanceAdapter(...))

    provider = registry.get("yahoo")
    service.get_ohlcv(identity, start, end, provider)

Supports:
- Explicit registration of pre-built adapter instances
- Resolution by provider name (case-insensitive normalised to lowercase)
- Listing registered providers
- Preventing silent double-registration (raises DuplicateProviderError)
"""
import logging

from backend.data_providers.range_provider import RangeProviderAdapter

logger = logging.getLogger(__name__)


class ProviderRegistryError(Exception):
    """Base error for ProviderRegistry failures."""


class ProviderNotFoundError(ProviderRegistryError):
    """Raised when a requested provider name is not registered."""


class DuplicateProviderError(ProviderRegistryError):
    """Raised when a provider name is registered more than once."""


class ProviderRegistry:
    """
    In-process registry of RangeProviderAdapter instances keyed by name.

    Thread-safety: not guaranteed. Intended for single-threaded setup at
    application startup, not concurrent dynamic registration.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, RangeProviderAdapter] = {}

    def register(self, name: str, adapter: RangeProviderAdapter) -> None:
        """
        Register an adapter under the given provider name.

        Args:
            name:    Provider name (normalised to lowercase). e.g. "yahoo".
            adapter: A RangeProviderAdapter instance ready to serve requests.

        Raises:
            DuplicateProviderError: if `name` is already registered.
            TypeError:              if `adapter` is not a RangeProviderAdapter.
        """
        key = name.strip().lower()
        if not key:
            raise ValueError("Provider name must not be empty or whitespace")
        if not isinstance(adapter, RangeProviderAdapter):
            raise TypeError(
                f"adapter must be a RangeProviderAdapter instance, got {type(adapter).__name__}"
            )
        if key in self._adapters:
            raise DuplicateProviderError(
                f"Provider '{key}' is already registered. "
                "Deregister it first or use a different name."
            )
        self._adapters[key] = adapter
        logger.debug("ProviderRegistry: registered provider '%s'", key)

    def get(self, name: str) -> RangeProviderAdapter:
        """
        Resolve and return the adapter registered under `name`.

        Args:
            name: Provider name (case-insensitive).

        Returns:
            The registered RangeProviderAdapter.

        Raises:
            ProviderNotFoundError: if `name` is not registered.
        """
        key = name.strip().lower()
        adapter = self._adapters.get(key)
        if adapter is None:
            available = sorted(self._adapters)
            raise ProviderNotFoundError(
                f"Provider '{key}' is not registered. "
                f"Registered providers: {available}"
            )
        return adapter

    def deregister(self, name: str) -> None:
        """
        Remove a previously registered adapter.

        Raises:
            ProviderNotFoundError: if `name` is not registered.
        """
        key = name.strip().lower()
        if key not in self._adapters:
            raise ProviderNotFoundError(
                f"Cannot deregister '{key}' — provider is not registered."
            )
        del self._adapters[key]
        logger.debug("ProviderRegistry: deregistered provider '%s'", key)

    def list_providers(self) -> list[str]:
        """Return sorted list of registered provider names."""
        return sorted(self._adapters)

    def __len__(self) -> int:
        return len(self._adapters)

    def __contains__(self, name: object) -> bool:
        if not isinstance(name, str):
            return False
        return name.strip().lower() in self._adapters
