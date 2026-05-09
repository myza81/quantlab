"""
Range-based data provider adapter contract.

Extends BaseDataAdapter with a fetch(start, end) method for incremental
date-range retrieval. This is the interface OHLCVService uses to request
only missing data windows from providers, avoiding re-downloading data
that is already in canonical local storage.

Provider implementations must:
- Return only records within [start, end] (both inclusive)
- Never perform normalization, storage writes, or deduplication
- Return [] if the provider has no data for the requested range
- Not raise if the range is empty — raise only on transport/auth errors
"""
from abc import abstractmethod
from datetime import datetime

from backend.data.schemas import NormalizedOHLCV
from backend.data_providers.base import BaseDataAdapter


class RangeProviderAdapter(BaseDataAdapter):
    """
    Provider adapter that supports incremental date-range fetching.

    Implement this for any provider capable of fetching data for a specific
    date window (REST APIs, database queries, file-based adapters with
    date filtering).

    The orchestration layer (OHLCVService) calls fetch() with only the
    missing date windows — providers must honour the [start, end] bounds.
    """

    @abstractmethod
    def fetch(
        self,
        start: datetime,
        end: datetime,
        **kwargs: object,
    ) -> list[NormalizedOHLCV]:
        """
        Fetch normalized OHLCV records for [start, end] (both inclusive).

        start and end must be UTC-aware datetimes.

        Returns:
            List of NormalizedOHLCV records within the requested window.
            May be empty if the provider has no data for this range.

        Raises:
            ValueError: if start or end are naive datetimes.
            Any provider-specific transport/auth errors.

        Must NOT:
            - perform normalization or series validation
            - write to storage
            - modify coverage metadata
            - raise if the date range is simply empty
        """
        ...
