import math
from dataclasses import dataclass, field

from backend.data.schemas import NormalizedOHLCV


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_ohlcv_record(record: NormalizedOHLCV) -> ValidationResult:
    """
    Validate a single OHLCV record for numerical and financial integrity.

    Schema-level checks (types, UTC, timeframe, empty fields, high >= low)
    are handled by NormalizedOHLCV itself. This layer adds:
    - finite value checks
    - non-negative volume
    - OHLC price relationship consistency
    """
    errors: list[str] = []

    for fname in ("open", "high", "low", "close", "volume"):
        val: float = getattr(record, fname)
        if not math.isfinite(val):
            errors.append(f"{fname} is not finite: {val}")

    if math.isfinite(record.open) and math.isfinite(record.high):
        if record.high < record.open:
            errors.append(f"high ({record.high}) < open ({record.open})")

    if math.isfinite(record.close) and math.isfinite(record.high):
        if record.high < record.close:
            errors.append(f"high ({record.high}) < close ({record.close})")

    if math.isfinite(record.open) and math.isfinite(record.low):
        if record.low > record.open:
            errors.append(f"low ({record.low}) > open ({record.open})")

    if math.isfinite(record.close) and math.isfinite(record.low):
        if record.low > record.close:
            errors.append(f"low ({record.low}) > close ({record.close})")

    if math.isfinite(record.volume) and record.volume < 0:
        errors.append(f"volume is negative: {record.volume}")

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def validate_ohlcv_series(records: list[NormalizedOHLCV]) -> ValidationResult:
    """
    Validate a series of OHLCV records for time-series integrity.

    Checks per-record numerical validity plus series-level rules:
    - monotonic timestamps (per DATA_CONTRACT.md)
    - no duplicate timestamps
    - symbol / timeframe / venue consistency within series
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not records:
        warnings.append("empty OHLCV series")
        return ValidationResult(valid=True, errors=errors, warnings=warnings)

    for i, record in enumerate(records):
        result = validate_ohlcv_record(record)
        for err in result.errors:
            errors.append(f"record[{i}] ({record.timestamp}): {err}")

    # Monotonic timestamp check
    for i in range(1, len(records)):
        if records[i].timestamp <= records[i - 1].timestamp:
            errors.append(
                f"non-monotonic timestamp at index {i}: "
                f"{records[i].timestamp} <= {records[i - 1].timestamp}"
            )

    # Duplicate timestamp check (DATA_CONTRACT.md: duplicates prohibited)
    seen: set[object] = set()
    for i, r in enumerate(records):
        if r.timestamp in seen:
            errors.append(f"duplicate timestamp at index {i}: {r.timestamp}")
        seen.add(r.timestamp)

    # Series consistency checks
    symbols = {r.symbol for r in records}
    if len(symbols) > 1:
        errors.append(f"mixed symbols in series: {symbols}")

    timeframes = {r.timeframe for r in records}
    if len(timeframes) > 1:
        errors.append(f"mixed timeframes in series: {timeframes}")

    venues = {r.venue for r in records}
    if len(venues) > 1:
        errors.append(f"mixed venues in series: {venues}")

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)
