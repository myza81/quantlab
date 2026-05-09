"""Tests for backend/storage/duckdb_query.py — DuckDB analytical query helper."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.data.schemas import NormalizedOHLCV
from backend.storage.duckdb_query import query_ohlcv, query_parquet
from backend.storage.parquet_store import StorageError, write
from tests.conftest import make_ohlcv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_series(base_path: Path, n: int = 5, **overrides) -> Path:
    records = [
        make_ohlcv(
            timestamp=datetime(2024, 1, 1, i, 0, 0, tzinfo=timezone.utc),
            **overrides,
        )
        for i in range(n)
    ]
    return write(records, base_path)


# ---------------------------------------------------------------------------
# query_parquet()
# ---------------------------------------------------------------------------

class TestQueryParquet:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(StorageError, match="not found"):
            query_parquet(tmp_path / "missing.parquet", "SELECT * FROM parquet")

    def test_returns_list_of_dicts(self, tmp_path: Path) -> None:
        path = _write_series(tmp_path)
        rows = query_parquet(path, "SELECT * FROM parquet")
        assert isinstance(rows, list)
        assert all(isinstance(r, dict) for r in rows)

    def test_row_count_matches(self, tmp_path: Path) -> None:
        path = _write_series(tmp_path, n=4)
        rows = query_parquet(path, "SELECT * FROM parquet")
        assert len(rows) == 4

    def test_row_contains_expected_keys(self, tmp_path: Path) -> None:
        path = _write_series(tmp_path, n=1)
        rows = query_parquet(path, "SELECT * FROM parquet")
        assert "symbol" in rows[0]
        assert "open" in rows[0]
        assert "timestamp" in rows[0]

    def test_count_query(self, tmp_path: Path) -> None:
        path = _write_series(tmp_path, n=3)
        rows = query_parquet(path, "SELECT COUNT(*) AS n FROM parquet")
        assert rows[0]["n"] == 3

    def test_empty_result_returns_empty_list(self, tmp_path: Path) -> None:
        path = _write_series(tmp_path, n=3)
        rows = query_parquet(path, "SELECT * FROM parquet WHERE symbol = 'NONEXISTENT'")
        assert rows == []


# ---------------------------------------------------------------------------
# query_ohlcv()
# ---------------------------------------------------------------------------

class TestQueryOHLCV:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(StorageError, match="not found"):
            query_ohlcv(tmp_path / "missing.parquet")

    def test_returns_normalized_ohlcv_instances(self, tmp_path: Path) -> None:
        path = _write_series(tmp_path)
        records = query_ohlcv(path)
        assert all(isinstance(r, NormalizedOHLCV) for r in records)

    def test_returns_all_records_without_filters(self, tmp_path: Path) -> None:
        path = _write_series(tmp_path, n=5)
        records = query_ohlcv(path)
        assert len(records) == 5

    def test_symbol_filter(self, tmp_path: Path) -> None:
        path = _write_series(tmp_path, n=3)
        records = query_ohlcv(path, symbol="BTCUSDT")
        assert len(records) == 3
        assert all(r.symbol == "BTCUSDT" for r in records)

    def test_symbol_filter_no_match_returns_empty(self, tmp_path: Path) -> None:
        path = _write_series(tmp_path, n=3)
        records = query_ohlcv(path, symbol="NOTEXIST")
        assert records == []

    def test_start_filter(self, tmp_path: Path) -> None:
        path = _write_series(tmp_path, n=5)
        cutoff = datetime(2024, 1, 1, 2, 0, 0, tzinfo=timezone.utc)
        records = query_ohlcv(path, start=cutoff)
        assert len(records) == 3
        assert all(r.timestamp >= cutoff for r in records)

    def test_end_filter(self, tmp_path: Path) -> None:
        path = _write_series(tmp_path, n=5)
        cutoff = datetime(2024, 1, 1, 3, 0, 0, tzinfo=timezone.utc)
        records = query_ohlcv(path, end=cutoff)
        assert len(records) == 3
        assert all(r.timestamp < cutoff for r in records)

    def test_start_and_end_filter(self, tmp_path: Path) -> None:
        path = _write_series(tmp_path, n=5)
        start = datetime(2024, 1, 1, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 4, 0, 0, tzinfo=timezone.utc)
        records = query_ohlcv(path, start=start, end=end)
        assert len(records) == 3
        for r in records:
            assert start <= r.timestamp < end

    def test_naive_start_filter_rejected(self, tmp_path: Path) -> None:
        path = _write_series(tmp_path, n=3)
        with pytest.raises(ValueError, match="start must be timezone-aware"):
            query_ohlcv(path, start=datetime(2024, 1, 1, 1, 0, 0))

    def test_naive_end_filter_rejected(self, tmp_path: Path) -> None:
        path = _write_series(tmp_path, n=3)
        with pytest.raises(ValueError, match="end must be timezone-aware"):
            query_ohlcv(path, end=datetime(2024, 1, 1, 1, 0, 0))

    def test_results_are_ordered_by_timestamp(self, tmp_path: Path) -> None:
        path = _write_series(tmp_path, n=5)
        records = query_ohlcv(path)
        timestamps = [r.timestamp for r in records]
        assert timestamps == sorted(timestamps)

    def test_loaded_records_pass_ohlcv_validation(self, tmp_path: Path) -> None:
        path = _write_series(tmp_path, n=3)
        records = query_ohlcv(path)
        for rec in records:
            NormalizedOHLCV(**rec.model_dump())
