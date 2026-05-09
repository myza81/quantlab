import csv
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.data.schemas import NormalizedOHLCV
from backend.data_providers.range_provider import RangeProviderAdapter

logger = logging.getLogger(__name__)


@dataclass
class CSVColumnMap:
    """
    Maps CSV column names to normalized field names.

    Override defaults when CSV uses non-standard column names.
    """

    timestamp: str = "timestamp"
    open: str = "open"
    high: str = "high"
    low: str = "low"
    close: str = "close"
    volume: str = "volume"
    trade_count: Optional[str] = None
    vwap: Optional[str] = None


@dataclass
class CSVAdapterConfig:
    """
    Configuration for loading a CSV OHLCV dataset.

    Metadata fields (symbol, asset_class, venue, timeframe, source) are
    applied uniformly across all rows — they describe the dataset, not
    individual candles.
    """

    symbol: str
    asset_class: str
    venue: str
    timeframe: str
    source: str
    columns: CSVColumnMap = field(default_factory=CSVColumnMap)


class CSVAdapter(RangeProviderAdapter):
    """
    Loads OHLCV data from CSV files and normalizes to canonical schema.

    Provider isolation contract:
    - CSV-specific parsing stays entirely inside this class
    - Callers receive only NormalizedOHLCV records
    - Strategies must never directly read CSV files

    Supported timestamp formats:
    - ISO-8601 with timezone  (e.g. 2024-01-01T00:00:00+00:00)
    - ISO-8601 with Z suffix   (e.g. 2024-01-01T00:00:00Z)
    - ISO-8601 naive           (treated as UTC per config)
    - Date-only YYYY-MM-DD     (treated as midnight UTC)
    - Unix timestamp (int/float seconds since epoch)
    """

    def __init__(self, config: CSVAdapterConfig) -> None:
        self._config = config

    @property
    def provider_name(self) -> str:
        return "csv"

    def load(self, **kwargs: object) -> list[NormalizedOHLCV]:
        """
        Load CSV from `file_path` keyword argument.

        Usage:
            adapter.load(file_path="/path/to/data.csv")
        """
        file_path = kwargs.get("file_path")
        if file_path is None:
            raise TypeError("load() requires keyword argument 'file_path'")
        return self._load_file(Path(str(file_path)))

    def _load_file(self, path: Path) -> list[NormalizedOHLCV]:
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")

        records: list[NormalizedOHLCV] = []
        col = self._config.columns

        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            if reader.fieldnames is None:
                raise ValueError(f"CSV file is empty or has no header: {path}")

            missing = {col.timestamp, col.open, col.high, col.low, col.close, col.volume} - set(
                reader.fieldnames
            )
            if missing:
                raise ValueError(
                    f"CSV missing required columns: {missing} "
                    f"(found: {list(reader.fieldnames)})"
                )

            for row_num, row in enumerate(reader, start=2):
                try:
                    record = self._parse_row(row, col)
                    records.append(record)
                except (ValueError, KeyError) as exc:
                    raise ValueError(f"CSV parse error at row {row_num}: {exc}") from exc

        logger.debug("CSVAdapter: loaded %d records from %s", len(records), path)
        return records

    def _parse_row(self, row: dict[str, str], col: CSVColumnMap) -> NormalizedOHLCV:
        trade_count: Optional[int] = None
        if col.trade_count and row.get(col.trade_count, "").strip():
            trade_count = int(row[col.trade_count])

        vwap: Optional[float] = None
        if col.vwap and row.get(col.vwap, "").strip():
            vwap = float(row[col.vwap])

        return NormalizedOHLCV(
            symbol=self._config.symbol,
            asset_class=self._config.asset_class,
            venue=self._config.venue,
            timeframe=self._config.timeframe,
            source=self._config.source,
            timestamp=self._parse_timestamp(row[col.timestamp].strip()),
            open=float(row[col.open]),
            high=float(row[col.high]),
            low=float(row[col.low]),
            close=float(row[col.close]),
            volume=float(row[col.volume]),
            trade_count=trade_count,
            vwap=vwap,
        )

    @staticmethod
    def _parse_timestamp(raw: str) -> datetime:
        # Unix timestamp (integer or float seconds)
        try:
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            pass

        # ISO-8601 — Python 3.11+ fromisoformat handles Z suffix natively
        # Fallback: replace Z for older compat even though we require 3.11+
        normalized = raw.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass

        # Date-only YYYY-MM-DD → midnight UTC
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

        raise ValueError(
            f"Cannot parse timestamp '{raw}'. "
            "Supported formats: ISO-8601 (with/without timezone), "
            "YYYY-MM-DD, Unix timestamp."
        )

    def fetch(
        self,
        start: datetime,
        end: datetime,
        **kwargs: object,
    ) -> list[NormalizedOHLCV]:
        """
        Load the CSV (via load()) and filter records to [start, end] inclusive.

        start and end must be UTC-aware. Pass file_path via kwargs just as
        you would when calling load() directly.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware (UTC)")
        records = self.load(**kwargs)
        return [r for r in records if start <= r.timestamp <= end]
