"""
Parquet-based persistence for NormalizedOHLCV records.

Path convention (per DATA_CONTRACT.md):
    {base_path}/{asset_class}/{symbol}/{timeframe}/data.parquet

All records written must share the same symbol, asset_class, venue, and timeframe.
Records are fully re-validated as NormalizedOHLCV on read.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pyarrow as pa
import pyarrow.parquet as pq

from backend.data.schemas import NormalizedOHLCV

SCHEMA = pa.schema(
    [
        pa.field("symbol", pa.string()),
        pa.field("asset_class", pa.string()),
        pa.field("venue", pa.string()),
        pa.field("timeframe", pa.string()),
        pa.field("source", pa.string()),
        pa.field("timestamp", pa.timestamp("us", tz="UTC")),
        pa.field("open", pa.float64()),
        pa.field("high", pa.float64()),
        pa.field("low", pa.float64()),
        pa.field("close", pa.float64()),
        pa.field("volume", pa.float64()),
        pa.field("trade_count", pa.int64()),
        pa.field("vwap", pa.float64()),
        pa.field("bid", pa.float64()),
        pa.field("ask", pa.float64()),
        pa.field("spread", pa.float64()),
        pa.field("adjustment_factor", pa.float64()),
        pa.field("metadata_json", pa.string()),
    ]
)

# Backward-compatible alias
_SCHEMA = SCHEMA


class StorageError(Exception):
    """Raised when a storage-layer operation fails."""


def dataset_path(base_path: Path, asset_class: str, symbol: str, timeframe: str) -> Path:
    """Return the canonical Parquet file path for a dataset."""
    return base_path / asset_class / symbol / timeframe / "data.parquet"


def write(records: list[NormalizedOHLCV], base_path: Path) -> Path:
    """
    Persist a list of NormalizedOHLCV records to Parquet.

    All records must share the same symbol, asset_class, venue, and timeframe.
    Existing file at the target path is overwritten.
    Returns the path written to.
    """
    if not records:
        raise StorageError("cannot write empty records list")

    first = records[0]
    for rec in records[1:]:
        if rec.symbol != first.symbol:
            raise StorageError(
                f"inconsistent symbol: expected '{first.symbol}', got '{rec.symbol}'"
            )
        if rec.asset_class != first.asset_class:
            raise StorageError(
                f"inconsistent asset_class: expected '{first.asset_class}', got '{rec.asset_class}'"
            )
        if rec.venue != first.venue:
            raise StorageError(
                f"inconsistent venue: expected '{first.venue}', got '{rec.venue}'"
            )
        if rec.timeframe != first.timeframe:
            raise StorageError(
                f"inconsistent timeframe: expected '{first.timeframe}', got '{rec.timeframe}'"
            )

    out_path = dataset_path(base_path, first.asset_class, first.symbol, first.timeframe)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    table = records_to_table(records)
    pq.write_table(table, out_path)
    return out_path


def read(
    base_path: Path,
    asset_class: str,
    symbol: str,
    timeframe: str,
) -> list[NormalizedOHLCV]:
    """
    Load NormalizedOHLCV records from Parquet and re-validate each row.

    Raises StorageError if the file does not exist.
    Raises pydantic.ValidationError if any row fails schema validation.
    """
    path = dataset_path(base_path, asset_class, symbol, timeframe)
    if not path.exists():
        raise StorageError(f"parquet dataset not found: {path}")

    table = pq.read_table(path, schema=SCHEMA)
    return table_to_records(table)


def records_to_table(records: list[NormalizedOHLCV]) -> pa.Table:
    cols: dict[str, list] = {field.name: [] for field in _SCHEMA}

    for rec in records:
        cols["symbol"].append(rec.symbol)
        cols["asset_class"].append(rec.asset_class)
        cols["venue"].append(rec.venue)
        cols["timeframe"].append(rec.timeframe)
        cols["source"].append(rec.source)
        # pyarrow timestamp[us, UTC] expects microseconds since epoch
        ts_us = int(rec.timestamp.timestamp() * 1_000_000)
        cols["timestamp"].append(ts_us)
        cols["open"].append(rec.open)
        cols["high"].append(rec.high)
        cols["low"].append(rec.low)
        cols["close"].append(rec.close)
        cols["volume"].append(rec.volume)
        cols["trade_count"].append(rec.trade_count)
        cols["vwap"].append(rec.vwap)
        cols["bid"].append(rec.bid)
        cols["ask"].append(rec.ask)
        cols["spread"].append(rec.spread)
        cols["adjustment_factor"].append(rec.adjustment_factor)
        cols["metadata_json"].append(
            json.dumps(rec.metadata) if rec.metadata is not None else None
        )

    arrays = [pa.array(cols[field.name], type=field.type) for field in _SCHEMA]
    return pa.table(dict(zip([f.name for f in _SCHEMA], arrays)), schema=_SCHEMA)


def table_to_records(table: pa.Table) -> list[NormalizedOHLCV]:
    records = []
    batch = table.to_pydict()
    n = len(batch["symbol"])

    for i in range(n):
        ts_raw = batch["timestamp"][i]
        if isinstance(ts_raw, datetime):
            ts = ts_raw if ts_raw.tzinfo is not None else ts_raw.replace(tzinfo=timezone.utc)
        else:
            # pyarrow may return a pandas Timestamp or int — normalise to datetime
            ts = datetime.fromtimestamp(int(ts_raw) / 1_000_000, tz=timezone.utc)

        metadata_raw: Optional[str] = batch["metadata_json"][i]
        metadata = json.loads(metadata_raw) if metadata_raw is not None else None

        records.append(
            NormalizedOHLCV(
                symbol=batch["symbol"][i],
                asset_class=batch["asset_class"][i],
                venue=batch["venue"][i],
                timeframe=batch["timeframe"][i],
                source=batch["source"][i],
                timestamp=ts,
                open=batch["open"][i],
                high=batch["high"][i],
                low=batch["low"][i],
                close=batch["close"][i],
                volume=batch["volume"][i],
                trade_count=batch["trade_count"][i],
                vwap=batch["vwap"][i],
                bid=batch["bid"][i],
                ask=batch["ask"][i],
                spread=batch["spread"][i],
                adjustment_factor=batch["adjustment_factor"][i],
                metadata=metadata,
            )
        )

    return records
