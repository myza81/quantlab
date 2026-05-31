"""
OHLCV retrieval and ingestion orchestration service.

Central access path for historical OHLCV data.  Implements the full flow:

    request slice
    → inspect local cache (DatasetCacheRegistry)
    → apply cache policy
    → fetch missing ranges from provider (if needed)
    → normalize incoming records
    → persist to canonical Parquet storage (if policy allows)
    → update coverage + cache metadata
    → return requested date slice

This is the layer that coordinates:

    DatasetCachePolicy  →  RangeProviderAdapter  →  DataNormalizer
    →  ohlcv_store  →  CoverageRegistry  →  DatasetCacheRegistry

Cache policy governs provider fetch behavior:
    FETCH_AND_STORE  (default) — fetch missing ranges only, persist
    READ_ONLY                  — return cached data only, never call provider
    FORCE_REFRESH              — fetch full range, overwrite local storage
    BYPASS_CACHE               — fetch, normalize, return without storing

Phase 4C.3 additions — forward-testing data-access primitives:
    timeframe_to_timedelta()   — canonical timeframe string → timedelta
    is_bar_finalized()         — checks whether a bar's period has fully elapsed
    OHLCVService.get_recent_bars()  — latest N finalized bars (BYPASS_CACHE)
    OHLCVService.get_bars_since()   — finalized bars strictly after a cursor (BYPASS_CACHE)

NOT a live-streaming system.  Historical / research-grade ingestion only.
"""
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from backend.data.models.cache_policy import DatasetCachePolicy
from backend.data.models.dataset import DatasetIdentity
from backend.data.normalizer import DataNormalizer, NormalizationError
from backend.data.schemas import NormalizedOHLCV
from backend.data_providers.provider_registry import ProviderRegistry
from backend.data_providers.range_provider import RangeProviderAdapter
from backend.storage import ohlcv_store
from backend.storage.coverage_registry import CoverageRegistry
from backend.storage.dataset_cache import DatasetCacheRegistry, DatasetCacheState
from backend.storage.parquet_store import StorageError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Timeframe utilities — Phase 4C.3 forward-testing primitives
# ---------------------------------------------------------------------------

# Maps canonical timeframe identifiers to their exact duration as timedelta.
# "1M" uses 30 days as an approximation; actual month length varies by calendar.
# Forward testing uses these durations only for bar-finalization detection, not
# for scheduling or statistical calculations, so the approximation is acceptable.
_TIMEFRAME_DURATIONS: dict[str, timedelta] = {
    "1m":  timedelta(minutes=1),
    "3m":  timedelta(minutes=3),
    "5m":  timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h":  timedelta(hours=1),
    "2h":  timedelta(hours=2),
    "4h":  timedelta(hours=4),
    "6h":  timedelta(hours=6),
    "8h":  timedelta(hours=8),
    "12h": timedelta(hours=12),
    "1d":  timedelta(days=1),
    "3d":  timedelta(days=3),
    "1w":  timedelta(weeks=1),
    "1M":  timedelta(days=30),
}


def timeframe_to_timedelta(timeframe: str) -> timedelta:
    """
    Convert a canonical QuantLab timeframe string to a Python timedelta.

    Args:
        timeframe: Canonical timeframe identifier (e.g. "1d", "1h", "15m").

    Returns:
        Corresponding timedelta representing one candle period.

    Raises:
        ValueError: if the timeframe is not in the canonical set.

    Note:
        "1M" returns timedelta(days=30) — an approximation.  The exact
        calendar month length varies but this is adequate for bar-finalization
        detection, which only needs to know when the candle period has elapsed.
    """
    try:
        return _TIMEFRAME_DURATIONS[timeframe]
    except KeyError:
        from backend.data.schemas import ALLOWED_TIMEFRAMES
        raise ValueError(
            f"Unsupported timeframe {timeframe!r}. "
            f"Allowed values: {sorted(ALLOWED_TIMEFRAMES)}"
        )


def is_bar_finalized(
    bar_timestamp: datetime,
    timeframe: str,
    *,
    current_time: datetime,
    buffer_seconds: int = 60,
) -> bool:
    """
    Return True when a bar's candle period has fully elapsed plus the safety buffer.

    A bar with open-time `bar_timestamp` and period `timeframe` is considered
    finalized when:

        current_time >= bar_timestamp + timeframe_duration + timedelta(seconds=buffer_seconds)

    The safety buffer accounts for provider data lag: a bar that just closed
    may not yet be available from the provider.  A 60-second buffer is the
    conservative default; tune via the caller (ForwardTestService passes
    ``settings.forward_test_bar_finalization_buffer_seconds``).

    Args:
        bar_timestamp:   Candle open-time.  Must be UTC-aware.
        timeframe:       Canonical timeframe string (e.g. "1d", "1h").
        current_time:    Reference "now".  Must be UTC-aware.
        buffer_seconds:  Seconds added to candle close time before the bar is
                         considered safe to evaluate.  Default 60.

    Returns:
        True if the candle period + buffer has elapsed; False otherwise.

    Raises:
        ValueError: if either datetime argument is naive (timezone-unaware).
        ValueError: if timeframe is not in the canonical set.
    """
    if bar_timestamp.tzinfo is None:
        raise ValueError("bar_timestamp must be UTC-aware; got naive datetime")
    if current_time.tzinfo is None:
        raise ValueError("current_time must be UTC-aware; got naive datetime")
    close_time = bar_timestamp + timeframe_to_timedelta(timeframe)
    return current_time >= close_time + timedelta(seconds=buffer_seconds)


class OHLCVIngestionError(Exception):
    """
    Raised when the ingestion pipeline fails unrecoverably.

    Wraps normalization errors, storage write errors, and provider
    contract violations so callers receive a single error type from
    the service boundary.
    """


class OHLCVService:
    """
    Retrieval orchestration for provider-specific OHLCV datasets.

    Guarantees:
    - Provider is only called for date windows not already in local storage
      (under FETCH_AND_STORE policy).
    - All incoming records pass normalization before being persisted.
    - Storage writes use the ohlcv_store merge path (dedup + sort).
    - Coverage and cache metadata are updated after every successful write.
    - Returned slice is always bounded to [start, end], not the full dataset.
    - Failed normalization or storage writes propagate as OHLCVIngestionError.

    See DatasetCachePolicy for the full policy contract.
    """

    def __init__(self, base_path: Path) -> None:
        self._base_path = base_path
        self._coverage = CoverageRegistry(base_path)
        self._cache_registry = DatasetCacheRegistry(base_path)
        self._normalizer = DataNormalizer()

    # ------------------------------------------------------------------
    # Primary public interface
    # ------------------------------------------------------------------

    def get_ohlcv(
        self,
        identity: DatasetIdentity,
        start: datetime,
        end: datetime,
        provider: RangeProviderAdapter,
        cache_policy: DatasetCachePolicy = DatasetCachePolicy.FETCH_AND_STORE,
        fetch_fingerprint: Optional[str] = None,
        **fetch_kwargs: object,
    ) -> list[NormalizedOHLCV]:
        """
        Return NormalizedOHLCV candles for [start, end] (both inclusive).

        Args:
            identity:          Provider-specific dataset identity.
            start:             Inclusive lower bound — must be UTC-aware.
            end:               Inclusive upper bound — must be UTC-aware.
            provider:          RangeProviderAdapter to call for missing windows.
            cache_policy:      Controls cache lookup and fetch behavior.
                               Defaults to FETCH_AND_STORE.
            fetch_fingerprint: Optional SHA-256 fingerprint from
                               DatasetFetchIdentity; stored in cache metadata
                               for lineage tracking.
            **fetch_kwargs:    Passed verbatim to provider.fetch().

        Returns:
            List of NormalizedOHLCV records within [start, end].
            Empty list if no data is available locally or from the provider.

        Raises:
            ValueError:           if start or end are naive datetimes.
            OHLCVIngestionError:  if normalization or storage write fails.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware (UTC)")

        # ---- BYPASS_CACHE: fetch, normalize, return — no storage --------
        if cache_policy == DatasetCachePolicy.BYPASS_CACHE:
            raw = provider.fetch(start, end, **fetch_kwargs)
            if not raw:
                return []
            return self._normalize(identity, raw, start, end)

        # ---- READ_ONLY: return cached data only — no provider call ------
        if cache_policy == DatasetCachePolicy.READ_ONLY:
            logger.debug(
                "OHLCVService: READ_ONLY for %s [%s..%s]",
                identity.dataset_id, start.date(), end.date(),
            )
            return self._read_slice(identity, start, end)

        # ---- FORCE_REFRESH: always fetch full range, overwrite ----------
        if cache_policy == DatasetCachePolicy.FORCE_REFRESH:
            return self._force_refresh(
                identity, start, end, provider, fetch_fingerprint, **fetch_kwargs
            )

        # ---- FETCH_AND_STORE (default): check coverage, fetch gaps ------
        return self._fetch_and_store(
            identity, start, end, provider, fetch_fingerprint, **fetch_kwargs
        )

    def calculate_missing_ranges(
        self,
        identity: DatasetIdentity,
        start: datetime,
        end: datetime,
    ) -> list[tuple[datetime, datetime]]:
        """
        Return date windows within [start, end] not covered by local storage.

        Delegates to CoverageRegistry (boundary-based).  Per-candle gap
        detection is not performed at this stage.
        """
        return self._coverage.missing_ranges(identity, start, end)

    def get_ohlcv_by_provider_name(
        self,
        identity: DatasetIdentity,
        start: datetime,
        end: datetime,
        provider_name: str,
        registry: ProviderRegistry,
        cache_policy: DatasetCachePolicy = DatasetCachePolicy.FETCH_AND_STORE,
        fetch_fingerprint: Optional[str] = None,
        **fetch_kwargs: object,
    ) -> list[NormalizedOHLCV]:
        """
        Resolve a provider adapter from the registry and delegate to get_ohlcv().

        Args:
            identity:          Provider-specific dataset identity.
            start:             Inclusive lower bound — must be UTC-aware.
            end:               Inclusive upper bound — must be UTC-aware.
            provider_name:     Name of the registered provider (e.g. "yahoo").
            registry:          ProviderRegistry containing the named adapter.
            cache_policy:      Cache behavior policy.
            fetch_fingerprint: Optional lineage fingerprint.
            **fetch_kwargs:    Passed verbatim to provider.fetch().

        Returns:
            list[NormalizedOHLCV] within [start, end].
        """
        provider = registry.get(provider_name)
        return self.get_ohlcv(
            identity, start, end, provider,
            cache_policy=cache_policy,
            fetch_fingerprint=fetch_fingerprint,
            **fetch_kwargs,
        )

    def refresh_coverage(self, identity: DatasetIdentity) -> None:
        """
        Recompute and persist coverage metadata from the stored Parquet file.

        Useful when coverage.json is out of sync with the actual data on disk
        (e.g. after a manual file operation or migration).
        """
        self._refresh_coverage(identity)

    # ------------------------------------------------------------------
    # Phase 4C.3 — forward-testing data-access primitives
    # ------------------------------------------------------------------

    def get_recent_bars(
        self,
        identity: DatasetIdentity,
        limit: int,
        provider: RangeProviderAdapter,
        *,
        reference_time: Optional[datetime] = None,
        bar_finalization_buffer_seconds: int = 60,
        lookback_multiplier: int = 2,
    ) -> list[NormalizedOHLCV]:
        """
        Return the latest ``limit`` finalized bars for the given identity.

        Intended use cases:
        - Warmup context at forward-test session activation
        - Initial strategy seed data
        - Latest-bar acquisition without polluting historical storage

        Behavior:
        - Fetches using BYPASS_CACHE (no storage read/write)
        - Excludes any bar whose candle period has not fully elapsed plus
          ``bar_finalization_buffer_seconds``
        - Returns bars in ascending timestamp order
        - Returns fewer than ``limit`` bars if fewer finalized bars are available

        Look-back window:
        - Requests ``limit * lookback_multiplier`` timeframe periods of history
        - The multiplier (default 2) accommodates weekends, market closures,
          and provider gaps without fetching an excessively large window

        Args:
            identity:                      Provider-specific dataset identity;
                                           must have a canonical timeframe.
            limit:                         Maximum number of finalized bars to return.
            provider:                      RangeProviderAdapter to call.
            reference_time:                "Now" reference for finalization check.
                                           Defaults to ``datetime.now(timezone.utc)``.
                                           Pass explicitly in tests for determinism.
            bar_finalization_buffer_seconds: Safety buffer added to candle close time.
                                           Default 60 s.  Pass
                                           ``settings.forward_test_bar_finalization_buffer_seconds``
                                           in production.
            lookback_multiplier:           Factor applied to the look-back window.
                                           Default 2.

        Returns:
            List of NormalizedOHLCV finalized bars, ascending, len <= limit.

        Raises:
            ValueError: if limit <= 0 or reference_time is naive.
            ValueError: if identity.timeframe is not in the canonical set.
        """
        if limit <= 0:
            raise ValueError(f"limit must be a positive integer; got {limit!r}")
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)
        if reference_time.tzinfo is None:
            raise ValueError("reference_time must be UTC-aware; got naive datetime")

        tf_delta = timeframe_to_timedelta(identity.timeframe)
        lookback = tf_delta * limit * lookback_multiplier
        start = reference_time - lookback

        bars = self.get_ohlcv(
            identity, start, reference_time, provider,
            cache_policy=DatasetCachePolicy.BYPASS_CACHE,
        )

        finalized = [
            b for b in bars
            if is_bar_finalized(
                b.timestamp, identity.timeframe,
                current_time=reference_time,
                buffer_seconds=bar_finalization_buffer_seconds,
            )
        ]

        # bars from get_ohlcv are ascending; take the most recent `limit`
        return finalized[-limit:] if len(finalized) > limit else finalized

    def get_bars_since(
        self,
        identity: DatasetIdentity,
        since_timestamp: datetime,
        provider: RangeProviderAdapter,
        *,
        reference_time: Optional[datetime] = None,
        bar_finalization_buffer_seconds: int = 60,
    ) -> list[NormalizedOHLCV]:
        """
        Return finalized bars with timestamp **strictly after** ``since_timestamp``.

        Intended use cases:
        - Forward-test poll cycle: fetch bars the session hasn't seen yet
        - Catch-up after pause/resume
        - Session restart with cursor recovery

        Behavior:
        - Fetches using BYPASS_CACHE (no storage read/write)
        - Strict comparison: ``bar.timestamp > since_timestamp``
        - Excludes any bar whose candle period has not fully elapsed plus
          ``bar_finalization_buffer_seconds``
        - Returns bars in ascending timestamp order
        - Duplicate bars are not returned (provider guarantees uniqueness
          within a fetch window; this layer adds no deduplication)
        - Never mutates session state — this is a pure read primitive

        Args:
            identity:                      Provider-specific dataset identity.
            since_timestamp:               Cursor.  Must be UTC-aware.
                                           Bars at exactly this timestamp are excluded.
            provider:                      RangeProviderAdapter to call.
            reference_time:                "Now" reference for finalization check.
                                           Defaults to ``datetime.now(timezone.utc)``.
            bar_finalization_buffer_seconds: Safety buffer for candle close time.
                                           Default 60 s.

        Returns:
            List of NormalizedOHLCV finalized bars strictly after since_timestamp,
            ascending by timestamp.

        Raises:
            ValueError: if since_timestamp or reference_time is naive.
            ValueError: if identity.timeframe is not in the canonical set.
        """
        if since_timestamp.tzinfo is None:
            raise ValueError("since_timestamp must be UTC-aware; got naive datetime")
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)
        if reference_time.tzinfo is None:
            raise ValueError("reference_time must be UTC-aware; got naive datetime")

        bars = self.get_ohlcv(
            identity, since_timestamp, reference_time, provider,
            cache_policy=DatasetCachePolicy.BYPASS_CACHE,
        )

        return [
            b for b in bars
            if b.timestamp > since_timestamp
            and is_bar_finalized(
                b.timestamp, identity.timeframe,
                current_time=reference_time,
                buffer_seconds=bar_finalization_buffer_seconds,
            )
        ]

    # ------------------------------------------------------------------
    # Policy-specific internal methods
    # ------------------------------------------------------------------

    def _fetch_and_store(
        self,
        identity: DatasetIdentity,
        start: datetime,
        end: datetime,
        provider: RangeProviderAdapter,
        fetch_fingerprint: Optional[str],
        **fetch_kwargs: object,
    ) -> list[NormalizedOHLCV]:
        """FETCH_AND_STORE: check coverage, fetch missing, persist."""
        missing = self.calculate_missing_ranges(identity, start, end)

        if not missing:
            logger.debug(
                "OHLCVService: cache HIT for %s [%s..%s] — skipping provider",
                identity.dataset_id, start.date(), end.date(),
            )
            return self._read_slice(identity, start, end)

        logger.debug(
            "OHLCVService: %d missing range(s) for %s [%s..%s]",
            len(missing), identity.dataset_id, start.date(), end.date(),
        )

        ingested_any = False
        for gap_start, gap_end in missing:
            raw = provider.fetch(gap_start, gap_end, **fetch_kwargs)
            if not raw:
                logger.debug(
                    "OHLCVService: provider returned 0 records for [%s..%s]",
                    gap_start.date(), gap_end.date(),
                )
                continue

            validated = self._normalize(identity, raw, gap_start, gap_end)
            try:
                ohlcv_store.write(validated, self._base_path, identity, merge=True)
            except Exception as exc:
                raise OHLCVIngestionError(
                    f"Storage write failed for {identity.dataset_id} "
                    f"[{gap_start.date()}..{gap_end.date()}]: {exc}"
                ) from exc
            ingested_any = True
            logger.debug(
                "OHLCVService: persisted %d records for %s [%s..%s]",
                len(validated), identity.dataset_id, gap_start.date(), gap_end.date(),
            )

        if ingested_any:
            self._refresh_coverage(identity)
            self._refresh_cache(identity, fetch_fingerprint)

        return self._read_slice(identity, start, end)

    def _force_refresh(
        self,
        identity: DatasetIdentity,
        start: datetime,
        end: datetime,
        provider: RangeProviderAdapter,
        fetch_fingerprint: Optional[str],
        **fetch_kwargs: object,
    ) -> list[NormalizedOHLCV]:
        """FORCE_REFRESH: fetch full range from provider, overwrite storage."""
        logger.debug(
            "OHLCVService: FORCE_REFRESH for %s [%s..%s]",
            identity.dataset_id, start.date(), end.date(),
        )
        raw = provider.fetch(start, end, **fetch_kwargs)
        if raw:
            validated = self._normalize(identity, raw, start, end)
            try:
                ohlcv_store.write(validated, self._base_path, identity, merge=False)
            except Exception as exc:
                raise OHLCVIngestionError(
                    f"Force-refresh storage write failed for {identity.dataset_id}: {exc}"
                ) from exc
            self._refresh_coverage(identity)
            self._refresh_cache(identity, fetch_fingerprint)

        return self._read_slice(identity, start, end)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalize(
        self,
        identity: DatasetIdentity,
        records: list[NormalizedOHLCV],
        gap_start: datetime,
        gap_end: datetime,
    ) -> list[NormalizedOHLCV]:
        try:
            return self._normalizer.normalize(records)
        except NormalizationError as exc:
            raise OHLCVIngestionError(
                f"Normalization failed for {identity.dataset_id} "
                f"[{gap_start.date()}..{gap_end.date()}]: {exc}"
            ) from exc

    def _refresh_coverage(self, identity: DatasetIdentity) -> None:
        try:
            records = ohlcv_store.read(self._base_path, identity)
            self._coverage.update(identity, records)
        except StorageError:
            pass

    def _refresh_cache(
        self, identity: DatasetIdentity, fingerprint: Optional[str] = None
    ) -> None:
        try:
            records = ohlcv_store.read(self._base_path, identity)
            storage_path = str(ohlcv_store.dataset_path(self._base_path, identity))
            self._cache_registry.update(identity, records, storage_path, fingerprint)
        except StorageError:
            pass

    def _read_slice(
        self,
        identity: DatasetIdentity,
        start: datetime,
        end: datetime,
    ) -> list[NormalizedOHLCV]:
        try:
            return ohlcv_store.read_range(self._base_path, identity, start, end)
        except StorageError:
            return []
