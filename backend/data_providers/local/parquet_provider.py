"""
Local Parquet dataset provider adapter.

Loads OHLCV data from a Parquet file with the file path embedded at
construction time, making it compatible with ProviderAdapterFactory's
builder pattern.

Supports flexible column mapping for external/research Parquet files
with non-standard schemas.  Default column names match the standard
OHLCV naming convention (timestamp, open, high, low, close, volume).

This provider is NOT a substitute for ohlcv_store.read() — it is designed
for external research datasets that have not yet entered the canonical
storage pipeline.

Architecture contract:
    Parquet-specific reading is isolated inside this adapter.
    Callers receive only NormalizedOHLCV records.
    All provider isolation is preserved.

Timestamp column resolution (tried in order):
    1. Python datetime with tzinfo  → converted to UTC
    2. Python datetime naive        → treated as UTC
    3. Numeric (> 1e12)             → microseconds since epoch (pyarrow style)
    4. Numeric (≤ 1e12)             → seconds since epoch
    5. String                       → ISO-8601 or YYYY-MM-DD via parse_timestamp_string
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pyarrow.parquet as pq

from backend.data.schemas import NormalizedOHLCV
from backend.data_providers.base import ProviderFetchError
from backend.data_providers.local._shared import LocalColumnMap, parse_timestamp_string
from backend.data_providers.range_provider import RangeProviderAdapter

logger = logging.getLogger(__name__)

_SUPPORTED_TIMEFRAMES = (
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
)
_SUPPORTED_ASSET_CLASSES = (
    "crypto", "equity", "etf", "fx", "fund", "futures", "index",
)


class LocalParquetProviderError(ProviderFetchError):
    """
    Raised when a local Parquet provider operation fails.

    Covers: file not found, missing columns, unsupported schema, parse errors.
    Subclasses ProviderFetchError so callers can catch the generic type.
    """


class LocalParquetProvider(RangeProviderAdapter):
    """
    RangeProviderAdapter for local Parquet OHLCV files.

    The file path is embedded at construction time so this adapter works
    with ProviderAdapterFactory's request-time builder pattern.

    Constructor metadata (symbol, asset_class, venue, timeframe) is applied
    uniformly to every row — the file does not need to contain these columns.
    """

    def __init__(
        self,
        *,
        file_path: str | Path,
        symbol: str,
        asset_class: str,
        venue: str,
        timeframe: str,
        adjustment_mode: str = "adjusted",
        column_map: Optional[LocalColumnMap] = None,
    ) -> None:
        self._file_path = Path(file_path)
        self._symbol = symbol
        self._asset_class = asset_class
        self._venue = venue
        self._timeframe = timeframe
        self._adjustment_mode = adjustment_mode
        self._col = column_map if column_map is not None else LocalColumnMap()

    @property
    def provider_name(self) -> str:
        return "parquet"

    def supported_timeframes(self) -> tuple[str, ...]:
        return _SUPPORTED_TIMEFRAMES

    def supported_asset_classes(self) -> tuple[str, ...]:
        return _SUPPORTED_ASSET_CLASSES

    def load(self, **_kwargs: object) -> list[NormalizedOHLCV]:
        """Load all records from the configured Parquet file."""
        return self._load_file()

    def fetch(
        self,
        start: datetime,
        end: datetime,
        **_kwargs: object,
    ) -> list[NormalizedOHLCV]:
        """
        Load the Parquet file and return records within [start, end] inclusive.

        Args:
            start: UTC-aware lower bound (inclusive).
            end:   UTC-aware upper bound (inclusive).

        Raises:
            ValueError:                 if start or end are naive datetimes.
            LocalParquetProviderError:  if the file is missing or malformed.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware (UTC)")
        records = self._load_file()
        return [r for r in records if start <= r.timestamp <= end]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_file(self) -> list[NormalizedOHLCV]:
        if not self._file_path.exists():
            raise LocalParquetProviderError(
                f"Parquet file not found: {self._file_path}"
            )

        try:
            table = pq.read_table(self._file_path)
        except Exception as exc:
            raise LocalParquetProviderError(
                f"Failed to read Parquet file {self._file_path}: {exc}"
            ) from exc

        col = self._col
        required = {col.timestamp, col.open, col.high, col.low, col.close, col.volume}
        present = set(table.column_names)
        missing = required - present
        if missing:
            raise LocalParquetProviderError(
                f"Parquet file missing required columns: {sorted(missing)} "
                f"(found: {sorted(present)})"
            )

        if table.num_rows == 0:
            logger.debug("LocalParquetProvider: file is empty: %s", self._file_path)
            return []

        batch = table.to_pydict()
        records: list[NormalizedOHLCV] = []
        for i in range(table.num_rows):
            try:
                records.append(self._parse_row(batch, i))
            except (ValueError, KeyError, TypeError) as exc:
                raise LocalParquetProviderError(
                    f"Parquet parse error at row {i}: {exc}"
                ) from exc

        logger.debug(
            "LocalParquetProvider: loaded %d records from %s",
            len(records), self._file_path,
        )
        return records

    def _parse_row(self, batch: dict, i: int) -> NormalizedOHLCV:
        col = self._col
        return NormalizedOHLCV(
            symbol=self._symbol,
            asset_class=self._asset_class,
            venue=self._venue,
            timeframe=self._timeframe,
            source="parquet",
            timestamp=_resolve_parquet_timestamp(batch[col.timestamp][i]),
            open=float(batch[col.open][i]),
            high=float(batch[col.high][i]),
            low=float(batch[col.low][i]),
            close=float(batch[col.close][i]),
            volume=float(batch[col.volume][i]),
        )


def _resolve_parquet_timestamp(raw: object) -> datetime:
    """
    Resolve a Parquet column value to a UTC-aware datetime.

    Handles the types that pyarrow's to_pydict() may return for a timestamp
    column depending on how the file was written.
    """
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw.astimezone(timezone.utc)

    if isinstance(raw, (int, float)):
        # pyarrow timestamp[us] → microseconds; plain epoch → seconds
        if abs(raw) > 1_000_000_000_000:
            return datetime.fromtimestamp(raw / 1_000_000, tz=timezone.utc)
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)

    if isinstance(raw, str):
        return parse_timestamp_string(raw)

    raise ValueError(
        f"Cannot resolve timestamp value {raw!r} (type {type(raw).__name__}). "
        "Expected datetime, numeric epoch (seconds or microseconds), or ISO string."
    )
