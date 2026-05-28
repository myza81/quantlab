"""
Local CSV dataset provider adapter.

Loads OHLCV data from a CSV file with the file path embedded at construction
time, making it compatible with ProviderAdapterFactory's builder pattern.

Architecture contract:
    CSV-specific parsing is isolated inside this adapter.
    Callers receive only NormalizedOHLCV records.
    Strategies must never directly access CSV files.

Correct flow:
    factory.build("csv", file_path=..., symbol=...) → LocalCSVProvider
    LocalCSVProvider.fetch(start, end) → list[NormalizedOHLCV]
    → OHLCVService → cache/storage layer

NOT:
    Strategy or service loading CSV directly
"""
import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

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


class LocalCSVProviderError(ProviderFetchError):
    """
    Raised when a local CSV provider operation fails.

    Covers: file not found, missing columns, malformed rows, parse errors.
    Subclasses ProviderFetchError so callers can catch the generic type.
    """


class LocalCSVProvider(RangeProviderAdapter):
    """
    RangeProviderAdapter for local CSV OHLCV files.

    The file path is embedded at construction time so this adapter works
    with ProviderAdapterFactory's request-time builder pattern.

    Supported timestamp formats (tried in order):
    - Unix timestamp (integer or float seconds since epoch)
    - ISO-8601 with timezone   (e.g. 2024-01-01T00:00:00+00:00)
    - ISO-8601 with Z suffix    (e.g. 2024-01-01T00:00:00Z)
    - ISO-8601 naive            (treated as UTC)
    - Date-only YYYY-MM-DD      (midnight UTC)
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
        return "csv"

    def supported_timeframes(self) -> tuple[str, ...]:
        return _SUPPORTED_TIMEFRAMES

    def supported_asset_classes(self) -> tuple[str, ...]:
        return _SUPPORTED_ASSET_CLASSES

    def load(self, **_kwargs: object) -> list[NormalizedOHLCV]:
        """Load all records from the configured CSV file."""
        return self._load_file()

    def fetch(
        self,
        start: datetime,
        end: datetime,
        **_kwargs: object,
    ) -> list[NormalizedOHLCV]:
        """
        Load the CSV file and return records within [start, end] inclusive.

        Args:
            start: UTC-aware lower bound (inclusive).
            end:   UTC-aware upper bound (inclusive).

        Raises:
            ValueError:             if start or end are naive datetimes.
            LocalCSVProviderError:  if the file is missing or malformed.
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
            raise LocalCSVProviderError(
                f"CSV file not found: {self._file_path}"
            )

        col = self._col
        required = {col.timestamp, col.open, col.high, col.low, col.close, col.volume}

        records: list[NormalizedOHLCV] = []
        try:
            with self._file_path.open(newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)

                if reader.fieldnames is None:
                    raise LocalCSVProviderError(
                        f"CSV file is empty or has no header: {self._file_path}"
                    )

                missing = required - set(reader.fieldnames)
                if missing:
                    raise LocalCSVProviderError(
                        f"CSV missing required columns: {sorted(missing)} "
                        f"(found: {list(reader.fieldnames)})"
                    )

                for row_num, row in enumerate(reader, start=2):
                    try:
                        records.append(self._parse_row(row))
                    except (ValueError, KeyError) as exc:
                        raise LocalCSVProviderError(
                            f"CSV parse error at row {row_num}: {exc}"
                        ) from exc

        except LocalCSVProviderError:
            raise
        except OSError as exc:
            raise LocalCSVProviderError(
                f"Failed to read CSV file {self._file_path}: {exc}"
            ) from exc

        logger.debug(
            "LocalCSVProvider: loaded %d records from %s",
            len(records), self._file_path,
        )
        return records

    def _parse_row(self, row: dict[str, str]) -> NormalizedOHLCV:
        col = self._col
        return NormalizedOHLCV(
            symbol=self._symbol,
            asset_class=self._asset_class,
            venue=self._venue,
            timeframe=self._timeframe,
            source="csv",
            timestamp=parse_timestamp_string(row[col.timestamp].strip()),
            open=float(row[col.open]),
            high=float(row[col.high]),
            low=float(row[col.low]),
            close=float(row[col.close]),
            volume=float(row[col.volume]),
        )
