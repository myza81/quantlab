"""
Asset search orchestration service.

Thin layer between the search API route and ProviderAdapterFactory.search().
Validates inputs, checks search capability, dispatches to the registered
searcher, and returns the normalized AssetSearchResponse.

Architecture contract:
    This module must NOT import from any concrete provider search module
    (e.g. backend.data_providers.yahoo.search). Provider dispatch is
    exclusively the factory's responsibility.

    Correct flow:
        route → search_assets(..., factory) → factory.search(provider, ...) → provider searcher

Error taxonomy (Chart-UX-2):
    AssetSearchError          — invalid query, unknown provider, or searcher
                                failure.  Maps to HTTP 400.
    ProviderSearchNotSupported — provider registered but has no search
                                capability.  Maps to HTTP 400 with a
                                machine-readable message pattern.
"""
from __future__ import annotations

from typing import Optional

from backend.api.schemas.market_data import AssetSearchResponse, AssetSearchResult
from backend.data_providers.provider_factory import ProviderAdapterFactory

_MIN_QUERY_LEN = 2
_MAX_QUERY_LEN = 100
_MAX_LIMIT = 20
_DEFAULT_LIMIT = 10


class AssetSearchError(Exception):
    """Raised for invalid search requests (→ HTTP 400)."""


class ProviderSearchNotSupported(AssetSearchError):
    """
    Raised when a registered provider does not support asset search.

    The message always contains "does not support" so the frontend can
    classify the error kind by string inspection without a separate error
    code field.
    """


def search_assets(
    *,
    query: str,
    provider: str,
    limit: int = _DEFAULT_LIMIT,
    factory: ProviderAdapterFactory,
    api_key: Optional[str] = None,
) -> AssetSearchResponse:
    """
    Search for assets matching *query* using the named provider's searcher.

    Args:
        query:    User search string (ticker symbol or company name).
                  Must be 2–100 characters after stripping whitespace.
        provider: Registered provider name to dispatch search through.
        limit:    Maximum results to return (capped at 20).
        factory:  ProviderAdapterFactory with registered provider searchers.
        api_key:  Optional pre-resolved API key for credentialed providers
                  (e.g. Polygon).  Passed verbatim to the provider searcher;
                  never logged or included in error messages.

    Returns:
        AssetSearchResponse with zero or more AssetSearchResult items.

    Raises:
        AssetSearchError:          query too short/long, unknown provider,
                                   or provider searcher raised an exception.
        ProviderSearchNotSupported: provider registered but has no searcher.
    """
    query = query.strip()
    if len(query) < _MIN_QUERY_LEN:
        raise AssetSearchError(
            f"Search query must be at least {_MIN_QUERY_LEN} characters."
        )
    if len(query) > _MAX_QUERY_LEN:
        raise AssetSearchError(
            f"Search query must be at most {_MAX_QUERY_LEN} characters."
        )

    effective_limit = min(max(1, limit), _MAX_LIMIT)

    if provider not in factory:
        raise AssetSearchError(
            f"Provider '{provider}' is not registered."
        )

    # Check search capability before calling the searcher
    caps = factory.get_capabilities(provider)
    if not caps.supports_search:
        raise ProviderSearchNotSupported(
            f"Provider '{provider}' does not support asset search."
        )

    try:
        raw_results = factory.search(
            provider, query=query, limit=effective_limit, api_key=api_key
        )
    except Exception as exc:
        raise AssetSearchError(
            f"Search failed for provider '{provider}': {exc}"
        ) from exc

    results = [
        AssetSearchResult(
            symbol=r["symbol"],
            name=r["name"],
            exchange=r["exchange"],
            asset_class=r["asset_class"],
            currency=r["currency"],
            type_label=r["type_label"],
        )
        for r in raw_results
    ]

    return AssetSearchResponse(
        query=query,
        provider=provider,
        results=results,
    )
