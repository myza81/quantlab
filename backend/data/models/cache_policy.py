"""
Dataset cache policy — controls how OHLCVService interacts with local storage
before calling a provider.

Four policies cover the full matrix of research and operational use cases:
    FETCH_AND_STORE — check coverage, fetch missing ranges only, persist
    READ_ONLY       — return whatever is in local cache, never call provider
    FORCE_REFRESH   — always fetch the full requested range, overwrite cache
    BYPASS_CACHE    — fetch from provider, return result, skip storage entirely
"""
from enum import Enum


class DatasetCachePolicy(str, Enum):
    """
    Controls the cache behavior of OHLCVService.get_ohlcv().

    FETCH_AND_STORE (default):
        Check local coverage; only call provider for date windows not already
        in storage. Persist incoming records. Preferred for all normal
        research and backtest workflows.

    READ_ONLY:
        Return data from local storage only. Never call the provider.
        Returns an empty list if no local data exists for the requested range.
        Use for offline research or when provider quota must be preserved.

    FORCE_REFRESH:
        Ignore local coverage. Fetch the full [start, end] window from the
        provider and overwrite local storage. Use to correct stale or
        incomplete cached data.

    BYPASS_CACHE:
        Fetch from provider, normalize, and return immediately without
        reading from or writing to local storage. Use for one-shot
        exploratory queries where persistence is not desired.
    """

    FETCH_AND_STORE = "fetch_and_store"
    READ_ONLY = "read_only"
    FORCE_REFRESH = "force_refresh"
    BYPASS_CACHE = "bypass_cache"
