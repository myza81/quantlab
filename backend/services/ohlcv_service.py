"""
OHLCV retrieval and ingestion orchestration service.

Central access path for historical OHLCV data.  Implements the full flow:

    request slice
    → inspect local coverage
    → calculate missing ranges
    → fetch only missing ranges from provider
    → normalize incoming records
    → persist to canonical Parquet storage
    → update coverage metadata
    → return requested date slice

This is the layer that coordinates:

    RangeProviderAdapter  →  DataNormalizer  →  ohlcv_store  →  CoverageRegistry

Future consumers (backtesting, charting, feature generation, research) should
call OHLCVService.get_ohlcv() as their primary data access point rather than
reading directly from storage or calling provider adapters themselves.

NOT a live-streaming system.  Historical / research-grade ingestion only.
"""
import logging
from datetime import datetime
from pathlib import Path

from backend.data.models.dataset import DatasetIdentity
from backend.data.normalizer import DataNormalizer, NormalizationError
from backend.data.schemas import NormalizedOHLCV
from backend.data_providers.provider_registry import ProviderRegistry
from backend.data_providers.range_provider import RangeProviderAdapter
from backend.storage import ohlcv_store
from backend.storage.coverage_registry import CoverageRegistry
from backend.storage.parquet_store import StorageError

logger = logging.getLogger(__name__)


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
    - Provider is only called for date windows not already in local storage.
    - All incoming records pass normalization before being persisted.
    - Storage writes use the ohlcv_store merge path (dedup + sort).
    - Coverage metadata is updated after every successful write batch.
    - Returned slice is always bounded to [start, end], not the full dataset.
    - Failed normalization or storage writes propagate as OHLCVIngestionError;
      already-written ranges in the same call are preserved (fail-fast).
    """

    def __init__(self, base_path: Path) -> None:
        self._base_path = base_path
        self._coverage = CoverageRegistry(base_path)
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
        **fetch_kwargs: object,
    ) -> list[NormalizedOHLCV]:
        """
        Return NormalizedOHLCV candles for [start, end] (both inclusive).

        Orchestrates the full retrieval flow:
        1. Calculate missing date ranges vs. local coverage.
        2. For each missing range: fetch → normalize → persist.
        3. Refresh coverage registry after successful persistence.
        4. Return requested slice from canonical storage.

        Args:
            identity:      Provider-specific dataset identity.
            start:         Inclusive lower bound — must be UTC-aware.
            end:           Inclusive upper bound — must be UTC-aware.
            provider:      RangeProviderAdapter to call for missing windows.
            **fetch_kwargs: Passed verbatim to provider.fetch() (e.g. file_path).

        Returns:
            List of NormalizedOHLCV records within [start, end].
            Empty list if no data is available locally or from the provider.

        Raises:
            ValueError:           if start or end are naive datetimes.
            OHLCVIngestionError:  if normalization or storage write fails.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware (UTC)")

        missing = self.calculate_missing_ranges(identity, start, end)

        if not missing:
            logger.debug(
                "OHLCVService: full coverage for %s [%s..%s] — skipping provider",
                identity.dataset_id,
                start.date(),
                end.date(),
            )
        else:
            logger.debug(
                "OHLCVService: %d missing range(s) for %s [%s..%s]",
                len(missing),
                identity.dataset_id,
                start.date(),
                end.date(),
            )

        ingested_any = False

        for gap_start, gap_end in missing:
            raw = provider.fetch(gap_start, gap_end, **fetch_kwargs)

            if not raw:
                logger.debug(
                    "OHLCVService: provider returned 0 records for [%s..%s]",
                    gap_start.date(),
                    gap_end.date(),
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
                len(validated),
                identity.dataset_id,
                gap_start.date(),
                gap_end.date(),
            )

        if ingested_any:
            self._refresh_coverage(identity)

        return self._read_slice(identity, start, end)

    def calculate_missing_ranges(
        self,
        identity: DatasetIdentity,
        start: datetime,
        end: datetime,
    ) -> list[tuple[datetime, datetime]]:
        """
        Return date windows within [start, end] not covered by local storage.

        Delegates to CoverageRegistry (boundary-based).  Interior candle-gap
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
        **fetch_kwargs: object,
    ) -> list[NormalizedOHLCV]:
        """
        Resolve a provider adapter from the registry and delegate to get_ohlcv().

        This is the preferred call pattern when using a ProviderRegistry:

            registry = ProviderRegistry()
            registry.register("yahoo", YahooFinanceAdapter(...))
            candles = service.get_ohlcv_by_provider_name(
                identity, start, end, "yahoo", registry
            )

        Args:
            identity:      Provider-specific dataset identity.
            start:         Inclusive lower bound — must be UTC-aware.
            end:           Inclusive upper bound — must be UTC-aware.
            provider_name: Name of the registered provider (e.g. "yahoo").
            registry:      ProviderRegistry containing the named adapter.
            **fetch_kwargs: Passed verbatim to provider.fetch().

        Returns:
            list[NormalizedOHLCV] within [start, end].

        Raises:
            ProviderNotFoundError: if provider_name is not in registry.
            ValueError:            if start or end are naive datetimes.
            OHLCVIngestionError:   if normalization or storage write fails.
        """
        provider = registry.get(provider_name)
        return self.get_ohlcv(identity, start, end, provider, **fetch_kwargs)

    def refresh_coverage(self, identity: DatasetIdentity) -> None:
        """
        Recompute and persist coverage metadata from the stored Parquet file.

        Useful when coverage.json is out of sync with the actual data on disk
        (e.g. after a manual file operation or migration).
        """
        self._refresh_coverage(identity)

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
