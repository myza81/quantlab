from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.data.normalizer import DataNormalizer, NormalizationError
from backend.data_providers.csv_adapter import CSVAdapter, CSVAdapterConfig
from tests.conftest import make_ohlcv


def make_config() -> CSVAdapterConfig:
    return CSVAdapterConfig(
        symbol="BTCUSDT",
        asset_class="crypto",
        venue="binance",
        timeframe="1h",
        source="csv_test",
    )


class TestDataNormalizer:
    def test_valid_series_passes(self, sample_series: list) -> None:
        normalizer = DataNormalizer()
        result = normalizer.normalize(sample_series)
        assert result == sample_series

    def test_returns_same_records_unchanged(self, sample_series: list) -> None:
        normalizer = DataNormalizer()
        result = normalizer.normalize(sample_series)
        assert result is sample_series

    def test_empty_series_passes(self) -> None:
        normalizer = DataNormalizer()
        result = normalizer.normalize([])
        assert result == []

    def test_invalid_series_raises_normalization_error(self) -> None:
        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        records = [make_ohlcv(timestamp=ts), make_ohlcv(timestamp=ts)]  # duplicates
        normalizer = DataNormalizer()
        with pytest.raises(NormalizationError):
            normalizer.normalize(records)

    def test_normalization_error_contains_error_list(self) -> None:
        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        records = [make_ohlcv(timestamp=ts), make_ohlcv(timestamp=ts)]
        normalizer = DataNormalizer()
        with pytest.raises(NormalizationError) as exc_info:
            normalizer.normalize(records)
        assert len(exc_info.value.errors) > 0

    def test_non_monotonic_series_raises(self) -> None:
        records = [
            make_ohlcv(timestamp=datetime(2024, 1, 1, 3, tzinfo=timezone.utc)),
            make_ohlcv(timestamp=datetime(2024, 1, 1, 1, tzinfo=timezone.utc)),
        ]
        normalizer = DataNormalizer()
        with pytest.raises(NormalizationError, match="Normalization failed"):
            normalizer.normalize(records)

    def test_price_integrity_failure_raises(self) -> None:
        records = [
            make_ohlcv(
                timestamp=datetime(2024, 1, 1, 0, tzinfo=timezone.utc),
                open=43000.0,
                high=42500.0,  # high < open — invalid
                low=41800.0,
                close=42200.0,
            )
        ]
        normalizer = DataNormalizer()
        with pytest.raises(NormalizationError):
            normalizer.normalize(records)


class TestCSVToNormalizerPipeline:
    """Integration: CSV adapter → DataNormalizer → validated records."""

    def test_full_pipeline_valid_csv(self, fixtures_dir: Path) -> None:
        adapter = CSVAdapter(make_config())
        normalizer = DataNormalizer()

        raw = adapter.load(file_path=fixtures_dir / "valid_ohlcv.csv")
        validated = normalizer.normalize(raw)

        assert len(validated) == 5
        for record in validated:
            assert record.symbol == "BTCUSDT"
            assert record.timestamp.tzinfo == timezone.utc

    def test_full_pipeline_duplicate_csv_raises(self, fixtures_dir: Path) -> None:
        adapter = CSVAdapter(make_config())
        normalizer = DataNormalizer()

        raw = adapter.load(file_path=fixtures_dir / "malformed_duplicate_timestamps.csv")
        with pytest.raises(NormalizationError):
            normalizer.normalize(raw)

    def test_strategy_receives_normalized_records(self, fixtures_dir: Path) -> None:
        """Simulate strategy consuming normalized data — must never know the source."""
        from backend.data.schemas import NormalizedOHLCV

        adapter = CSVAdapter(make_config())
        normalizer = DataNormalizer()
        records = normalizer.normalize(adapter.load(file_path=fixtures_dir / "valid_ohlcv.csv"))

        # Strategy only sees NormalizedOHLCV — no CSV-specific fields
        for record in records:
            assert isinstance(record, NormalizedOHLCV)
            assert hasattr(record, "symbol")
            assert hasattr(record, "timestamp")
            assert hasattr(record, "open")
            assert not hasattr(record, "raw_csv_row")
