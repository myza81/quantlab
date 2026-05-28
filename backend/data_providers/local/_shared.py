"""
Shared utilities for local dataset providers (CSV and Parquet).

Kept in a private module to avoid exposing implementation details at
the package level.  Only csv_provider.py and parquet_provider.py import
from here; external callers use the public package exports.
"""
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class LocalColumnMap:
    """
    Maps source file column names to the canonical NormalizedOHLCV fields.

    Default values match the standard OHLCV naming convention.  Override
    any field when the source file uses non-standard column names.

    Example — Yahoo CSV export (capitalised headers):
        LocalColumnMap(timestamp="Date", open="Open", high="High",
                       low="Low", close="Close", volume="Volume")
    """

    timestamp: str = "timestamp"
    open: str = "open"
    high: str = "high"
    low: str = "low"
    close: str = "close"
    volume: str = "volume"


def parse_timestamp_string(raw: str) -> datetime:
    """
    Parse a raw string timestamp to a UTC-aware datetime.

    Supported formats (tried in order):
    1. Unix timestamp — integer or float seconds since epoch
    2. ISO-8601 with timezone  (e.g. 2024-01-01T00:00:00+00:00)
    3. ISO-8601 with Z suffix   (e.g. 2024-01-01T00:00:00Z)
    4. ISO-8601 naive           (treated as UTC)
    5. Date-only YYYY-MM-DD     (midnight UTC)

    Raises:
        ValueError: if the string cannot be parsed by any supported format.
    """
    # Unix timestamp (integer or float seconds)
    try:
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        pass

    # ISO-8601 — Python 3.11+ fromisoformat handles Z natively; replace for safety
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
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    raise ValueError(
        f"Cannot parse timestamp '{raw}'. "
        "Supported formats: ISO-8601 (with/without timezone), "
        "YYYY-MM-DD, Unix timestamp (seconds)."
    )
