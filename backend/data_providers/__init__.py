from backend.data_providers.base import BaseDataAdapter, ProviderCapabilities, ProviderFetchError
from backend.data_providers.range_provider import RangeProviderAdapter
from backend.data_providers.csv_adapter import CSVAdapter, CSVAdapterConfig, CSVColumnMap
from backend.data_providers.local import (
    LocalColumnMap,
    LocalCSVProvider,
    LocalCSVProviderError,
    LocalParquetProvider,
    LocalParquetProviderError,
)
from backend.data_providers.provider_registry import (
    ProviderRegistry,
    ProviderRegistryError,
    ProviderNotFoundError,
    DuplicateProviderError,
)
from backend.data_providers.provider_symbol_map import (
    ProviderSymbolMapping,
    SymbolMapService,
    ProviderSymbolMapError,
)
from backend.data_providers.provider_factory import (
    ProviderAdapterFactory,
    ProviderBuildError,
    UnknownProviderError,
    create_default_factory_registry,
)
from backend.data_providers.polygon import (
    PolygonAdapterError,
    PolygonProviderAdapter,
    PolygonRateLimitError,
    POLYGON_SUPPORTED_TIMEFRAMES,
)

__all__ = [
    # Base
    "BaseDataAdapter",
    "ProviderCapabilities",
    "ProviderFetchError",
    "RangeProviderAdapter",
    # Legacy CSV adapter (general-purpose, file_path passed at call time)
    "CSVAdapter",
    "CSVAdapterConfig",
    "CSVColumnMap",
    # Local file providers (file_path embedded at construction — factory pattern)
    "LocalColumnMap",
    "LocalCSVProvider",
    "LocalCSVProviderError",
    "LocalParquetProvider",
    "LocalParquetProviderError",
    # Provider registry (instance-based, for pre-built adapters)
    "ProviderRegistry",
    "ProviderRegistryError",
    "ProviderNotFoundError",
    "DuplicateProviderError",
    # Provider factory (request-time adapter construction)
    "ProviderAdapterFactory",
    "ProviderBuildError",
    "UnknownProviderError",
    "create_default_factory_registry",
    # Polygon.io provider
    "PolygonAdapterError",
    "PolygonProviderAdapter",
    "PolygonRateLimitError",
    "POLYGON_SUPPORTED_TIMEFRAMES",
    # Symbol mapping
    "ProviderSymbolMapping",
    "SymbolMapService",
    "ProviderSymbolMapError",
]
