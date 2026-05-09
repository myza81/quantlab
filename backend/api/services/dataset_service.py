"""
Dataset service — business logic for CSV import, dataset listing, and OHLCV reads.

Routes must remain thin; all domain logic lives here.
Flow: CSVAdapter → DataNormalizer → parquet_store (per DATA_CONTRACT.md pipeline).
"""
import logging
import os
import tempfile
from pathlib import Path

from backend.api.schemas.dataset import (
    DatasetInfo,
    DatasetListResponse,
    DatasetOHLCVResponse,
    ImportCSVResponse,
    OHLCVCandle,
)
from backend.data.normalizer import DataNormalizer, NormalizationError
from backend.data.schemas import NormalizedOHLCV
from backend.data_providers.csv_adapter import CSVAdapter, CSVAdapterConfig, CSVColumnMap
from backend.storage import parquet_store
from backend.storage.parquet_store import StorageError

logger = logging.getLogger(__name__)


class DatasetImportError(Exception):
    """Raised when CSV import, normalization, or storage fails for a known reason."""


class DatasetNotFoundError(Exception):
    """Raised when a requested dataset does not exist in storage."""


def make_dataset_id(asset_class: str, symbol: str, timeframe: str) -> str:
    return f"{asset_class}__{symbol}__{timeframe}"


def parse_dataset_id(dataset_id: str) -> tuple[str, str, str]:
    """Return (asset_class, symbol, timeframe) from a dataset_id string."""
    parts = dataset_id.split("__", maxsplit=2)
    if len(parts) != 3 or any(p == "" for p in parts):
        raise ValueError(
            f"Invalid dataset_id {dataset_id!r}. "
            "Expected format: '<asset_class>__<symbol>__<timeframe>'"
        )
    return parts[0], parts[1], parts[2]


def import_csv(
    file_bytes: bytes,
    symbol: str,
    asset_class: str,
    venue: str,
    timeframe: str,
    source: str,
    column_map: CSVColumnMap,
    base_path: Path,
) -> ImportCSVResponse:
    """
    Parse, normalize, and persist a CSV OHLCV upload.

    Writes a Parquet file to base_path using the canonical path convention.
    Raises DatasetImportError for all recoverable failures.
    """
    fd, tmp_path_str = tempfile.mkstemp(suffix=".csv")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(file_bytes)

        config = CSVAdapterConfig(
            symbol=symbol,
            asset_class=asset_class,
            venue=venue,
            timeframe=timeframe,
            source=source,
            columns=column_map,
        )
        adapter = CSVAdapter(config)

        try:
            records = adapter.load(file_path=tmp_path_str)
        except (ValueError, FileNotFoundError) as exc:
            raise DatasetImportError(f"CSV parse error: {exc}") from exc

        normalizer = DataNormalizer()
        try:
            normalized = normalizer.normalize(records)
        except NormalizationError as exc:
            raise DatasetImportError(f"Normalization failed: {exc}") from exc

        try:
            parquet_store.write(normalized, base_path)
        except StorageError as exc:
            raise DatasetImportError(f"Storage error: {exc}") from exc

        logger.info(
            "Dataset imported: %s records → %s",
            len(normalized),
            make_dataset_id(asset_class, symbol, timeframe),
        )
        return ImportCSVResponse(
            dataset_id=make_dataset_id(asset_class, symbol, timeframe),
            symbol=symbol,
            asset_class=asset_class,
            venue=venue,
            timeframe=timeframe,
            record_count=len(normalized),
        )
    finally:
        try:
            os.unlink(tmp_path_str)
        except OSError:
            pass


def list_datasets(base_path: Path) -> DatasetListResponse:
    """
    Scan base_path for stored Parquet datasets.

    Expected directory structure (per DATA_CONTRACT.md):
        base_path/{asset_class}/{symbol}/{timeframe}/data.parquet
    """
    if not base_path.exists():
        return DatasetListResponse(datasets=[], count=0)

    datasets: list[DatasetInfo] = []
    for parquet_file in sorted(base_path.glob("*/*/*/data.parquet")):
        rel_parts = parquet_file.relative_to(base_path).parts
        # parts: (asset_class, symbol, timeframe, "data.parquet")
        if len(rel_parts) != 4:
            continue
        asset_class, symbol, timeframe = rel_parts[0], rel_parts[1], rel_parts[2]
        datasets.append(
            DatasetInfo(
                dataset_id=make_dataset_id(asset_class, symbol, timeframe),
                asset_class=asset_class,
                symbol=symbol,
                timeframe=timeframe,
            )
        )

    return DatasetListResponse(datasets=datasets, count=len(datasets))


def read_ohlcv(
    base_path: Path,
    asset_class: str,
    symbol: str,
    timeframe: str,
) -> DatasetOHLCVResponse:
    """
    Load and return validated NormalizedOHLCV records from Parquet.

    Raises DatasetNotFoundError if no dataset exists at the derived path.
    All returned records are re-validated as NormalizedOHLCV by the storage layer.
    """
    try:
        records: list[NormalizedOHLCV] = parquet_store.read(
            base_path, asset_class, symbol, timeframe
        )
    except StorageError as exc:
        raise DatasetNotFoundError(str(exc)) from exc

    candles = [
        OHLCVCandle(
            timestamp=rec.timestamp,
            open=rec.open,
            high=rec.high,
            low=rec.low,
            close=rec.close,
            volume=rec.volume,
            trade_count=rec.trade_count,
            vwap=rec.vwap,
            bid=rec.bid,
            ask=rec.ask,
            spread=rec.spread,
            adjustment_factor=rec.adjustment_factor,
            metadata=rec.metadata,
        )
        for rec in records
    ]

    first = records[0]
    return DatasetOHLCVResponse(
        dataset_id=make_dataset_id(asset_class, symbol, timeframe),
        symbol=first.symbol,
        asset_class=first.asset_class,
        venue=first.venue,
        timeframe=first.timeframe,
        count=len(candles),
        candles=candles,
    )
