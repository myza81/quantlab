from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict

from backend.data.schemas import NormalizedOHLCV


class ProviderFetchError(Exception):
    """
    Base exception for provider-level fetch failures.

    Concrete adapters should subclass this so callers can catch a single
    provider-agnostic error type without importing adapter-specific exceptions.
    """


class ProviderCapabilities(BaseModel):
    """
    Static capability descriptor for a data provider.

    Describes what a provider supports so API layers and tooling can expose
    provider metadata without importing concrete adapter classes.
    """

    model_config = ConfigDict(frozen=True)

    provider_id: str
    display_name: str
    supported_timeframes: tuple[str, ...]
    supported_asset_classes: tuple[str, ...]


class BaseDataAdapter(ABC):
    """
    Abstract base for all data provider adapters.

    Responsibility:
    - Accept provider-native data (files, API responses, streams)
    - Convert to NormalizedOHLCV using canonical schema
    - Never expose provider-specific schemas outside the adapter

    Strategies must never import from concrete adapter implementations.
    All provider isolation must be preserved within subclasses.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable identifier for the data provider."""
        ...

    @abstractmethod
    def load(self, **kwargs: object) -> list[NormalizedOHLCV]:
        """
        Load and return normalized OHLCV records from the provider.

        All provider-specific logic (field mapping, timestamp parsing,
        schema quirks) must stay inside this method.
        Returns structurally valid NormalizedOHLCV records.
        Callers should pass result through DataNormalizer for full validation.
        """
        ...

    def supported_timeframes(self) -> tuple[str, ...]:
        """Return canonical timeframe strings supported by this provider."""
        return ()

    def supported_asset_classes(self) -> tuple[str, ...]:
        """Return asset class strings supported by this provider."""
        return ()

    def capabilities(self) -> ProviderCapabilities:
        """Return a ProviderCapabilities descriptor for this adapter."""
        return ProviderCapabilities(
            provider_id=self.provider_name,
            display_name=self.provider_name.title(),
            supported_timeframes=self.supported_timeframes(),
            supported_asset_classes=self.supported_asset_classes(),
        )
