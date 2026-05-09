"""
Provider-specific symbol mapping layer.

Separates the internal instrument symbol identity from the symbol form
required by a specific data provider's API.

Examples:
    Internal "MAYBANK" → Yahoo Finance "1155.KL"
    Internal "AAPL"    → Yahoo Finance "AAPL"   (identity mapping)
    Internal "AAPL"    → IBKR "AAPL" + conId    (future: richer mapping)

Design:
- ProviderSymbolMapping: immutable Pydantic model describing one mapping entry
- SymbolMapService: in-memory mapping store; defaults to identity if no mapping exists

This is a minimal foundation, not a full instrument master database.
"""
from pydantic import BaseModel, ConfigDict, field_validator


class ProviderSymbolMapping(BaseModel):
    """
    Maps one internal symbol to a provider-specific symbol for a given provider.

    Immutable by design — mappings should be constructed once and stored.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    internal_symbol: str
    provider: str
    provider_symbol: str

    @field_validator("internal_symbol", "provider", "provider_symbol")
    @classmethod
    def must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field must not be empty or whitespace")
        return v.strip()

    @field_validator("provider")
    @classmethod
    def provider_to_lowercase(cls, v: str) -> str:
        return v.strip().lower()


class ProviderSymbolMapError(Exception):
    """Raised for invalid operations on SymbolMapService."""


class SymbolMapService:
    """
    In-memory store for provider symbol mappings.

    Resolution strategy:
    - If an explicit mapping exists for (internal_symbol, provider): return it.
    - Otherwise: return internal_symbol unchanged (identity fallback).

    This means providers that use the same symbol format (e.g. Yahoo for US
    equities) need no mapping entries at all. Only non-identity mappings
    (e.g. Bursa stocks on Yahoo: "MAYBANK" → "1155.KL") need to be registered.
    """

    def __init__(self) -> None:
        self._mappings: dict[tuple[str, str], str] = {}

    @staticmethod
    def _key(internal_symbol: str, provider: str) -> tuple[str, str]:
        return (internal_symbol.strip().upper(), provider.strip().lower())

    def add_mapping(self, mapping: ProviderSymbolMapping) -> None:
        """
        Register a symbol mapping.

        Args:
            mapping: ProviderSymbolMapping instance.

        Raises:
            ProviderSymbolMapError: if a mapping for (symbol, provider) already exists.
        """
        key = self._key(mapping.internal_symbol, mapping.provider)
        if key in self._mappings:
            raise ProviderSymbolMapError(
                f"Mapping for ('{mapping.internal_symbol}', '{mapping.provider}') "
                "already exists. Remove it before adding a replacement."
            )
        self._mappings[key] = mapping.provider_symbol

    def remove_mapping(self, internal_symbol: str, provider: str) -> None:
        """
        Remove an existing mapping entry.

        Raises:
            ProviderSymbolMapError: if the mapping does not exist.
        """
        key = self._key(internal_symbol, provider)
        if key not in self._mappings:
            raise ProviderSymbolMapError(
                f"No mapping found for ('{internal_symbol}', '{provider}')."
            )
        del self._mappings[key]

    def resolve(self, internal_symbol: str, provider: str) -> str:
        """
        Resolve the provider-specific symbol for the given internal symbol.

        Falls back to `internal_symbol` unchanged when no explicit mapping exists.
        This supports providers where symbol formats match (e.g. US equities on Yahoo).

        Args:
            internal_symbol: The canonical internal symbol (e.g. "AAPL", "MAYBANK").
            provider:        Provider name (case-insensitive, e.g. "yahoo").

        Returns:
            Provider-specific symbol string.
        """
        key = self._key(internal_symbol, provider)
        return self._mappings.get(key, internal_symbol)

    def has_mapping(self, internal_symbol: str, provider: str) -> bool:
        """Return True if an explicit mapping exists for (symbol, provider)."""
        key = self._key(internal_symbol, provider)
        return key in self._mappings

    def list_mappings(self, provider: str | None = None) -> list[ProviderSymbolMapping]:
        """
        Return all registered mappings, optionally filtered by provider.
        """
        result = []
        for (sym, prov), provider_sym in self._mappings.items():
            if provider is None or prov == provider.strip().lower():
                result.append(
                    ProviderSymbolMapping(
                        internal_symbol=sym,
                        provider=prov,
                        provider_symbol=provider_sym,
                    )
                )
        return sorted(result, key=lambda m: (m.provider, m.internal_symbol))
