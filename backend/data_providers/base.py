from abc import ABC, abstractmethod

from backend.data.schemas import NormalizedOHLCV


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
