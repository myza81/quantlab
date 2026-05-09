"""
DuckDB query helper for analytical access to Parquet-backed OHLCV datasets.

Uses DuckDB's fetch_arrow_table() to avoid a pytz/pandas/numpy dependency.
Timestamps are read back via pyarrow (already a project dependency).

Usage:
    from backend.storage.duckdb_query import query_parquet, query_ohlcv

    rows = query_parquet(path, "SELECT * FROM parquet")
    records = query_ohlcv(path)
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import duckdb
import pyarrow as pa

from backend.data.schemas import NormalizedOHLCV
from backend.storage.parquet_store import StorageError


def query_parquet(parquet_path: Path, sql: str) -> list[dict[str, Any]]:
    """
    Execute a SQL query against a Parquet file via DuckDB.

    The keyword ``parquet`` in the SQL is replaced with ``read_parquet('<path>')``.
    Returns a list of row dicts with Python-native values.
    Timestamps are returned as UTC-aware datetime objects.

    Raises StorageError if the file does not exist.
    """
    if not parquet_path.exists():
        raise StorageError(f"parquet file not found: {parquet_path}")

    resolved_sql = sql.replace("parquet", f"read_parquet('{parquet_path}')")
    conn = duckdb.connect()
    try:
        arrow_table = conn.execute(resolved_sql).arrow().read_all()
    finally:
        conn.close()

    return _arrow_table_to_dicts(arrow_table)


def query_ohlcv(
    parquet_path: Path,
    *,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    symbol: Optional[str] = None,
) -> list[NormalizedOHLCV]:
    """
    Query a Parquet OHLCV dataset and return validated NormalizedOHLCV records.

    Optional filters:
        start  — inclusive lower bound on timestamp (UTC-aware datetime)
        end    — exclusive upper bound on timestamp (UTC-aware datetime)
        symbol — exact symbol match

    Raises StorageError if the file does not exist.
    Raises pydantic.ValidationError if any row fails schema validation.
    """
    if not parquet_path.exists():
        raise StorageError(f"parquet file not found: {parquet_path}")

    conditions: list[str] = []
    if symbol is not None:
        conditions.append(f"symbol = '{symbol}'")
    if start is not None:
        start_utc = _require_utc_aware(start, name="start")
        iso = start_utc.strftime("%Y-%m-%d %H:%M:%S+00")
        conditions.append(f"timestamp >= TIMESTAMPTZ '{iso}'")
    if end is not None:
        end_utc = _require_utc_aware(end, name="end")
        iso = end_utc.strftime("%Y-%m-%d %H:%M:%S+00")
        conditions.append(f"timestamp < TIMESTAMPTZ '{iso}'")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM read_parquet('{parquet_path}') {where} ORDER BY timestamp"

    conn = duckdb.connect()
    try:
        arrow_table = conn.execute(sql).arrow().read_all()
    finally:
        conn.close()

    return _arrow_table_to_ohlcv(arrow_table)


# ---------------------------------------------------------------------------
# Internal conversion helpers
# ---------------------------------------------------------------------------

def _arrow_table_to_dicts(table: pa.Table) -> list[dict[str, Any]]:
    """Convert a pyarrow Table to a list of Python-native dicts."""
    result: list[dict[str, Any]] = []
    batch = table.to_pydict()
    columns = list(batch.keys())
    n = table.num_rows

    for i in range(n):
        row: dict[str, Any] = {}
        for col in columns:
            val = batch[col][i]
            # Normalise pyarrow timestamp int (epoch us) → UTC datetime
            if isinstance(val, int) and col == "timestamp":
                val = datetime.fromtimestamp(val / 1_000_000, tz=timezone.utc)
            row[col] = val
        result.append(row)

    return result


def _arrow_table_to_ohlcv(table: pa.Table) -> list[NormalizedOHLCV]:
    """Convert a pyarrow Table (from DuckDB) to validated NormalizedOHLCV list."""
    batch = table.to_pydict()
    n = table.num_rows
    records = []

    for i in range(n):
        ts_raw = batch["timestamp"][i]
        # Parquet stores timestamp as INT64 epoch microseconds (pa.timestamp("us", tz="UTC"))
        if isinstance(ts_raw, int):
            ts = datetime.fromtimestamp(ts_raw / 1_000_000, tz=timezone.utc)
        elif isinstance(ts_raw, datetime):
            ts = ts_raw if ts_raw.tzinfo is not None else ts_raw.replace(tzinfo=timezone.utc)
        else:
            ts = datetime.fromtimestamp(float(ts_raw) / 1_000_000, tz=timezone.utc)

        metadata_raw = batch.get("metadata_json", [None] * n)[i]
        metadata = json.loads(metadata_raw) if metadata_raw is not None else None

        records.append(
            NormalizedOHLCV(
                symbol=str(batch["symbol"][i]),
                asset_class=str(batch["asset_class"][i]),
                venue=str(batch["venue"][i]),
                timeframe=str(batch["timeframe"][i]),
                source=str(batch["source"][i]),
                timestamp=ts,
                open=float(batch["open"][i]),
                high=float(batch["high"][i]),
                low=float(batch["low"][i]),
                close=float(batch["close"][i]),
                volume=float(batch["volume"][i]),
                trade_count=_opt_int(batch["trade_count"][i]),
                vwap=_opt_float(batch["vwap"][i]),
                bid=_opt_float(batch["bid"][i]),
                ask=_opt_float(batch["ask"][i]),
                spread=_opt_float(batch["spread"][i]),
                adjustment_factor=_opt_float(batch["adjustment_factor"][i]),
                metadata=metadata,
            )
        )

    return records


def _require_utc_aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _opt_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    return int(val)


def _opt_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    return float(val)
