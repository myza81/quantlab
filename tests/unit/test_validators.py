from datetime import datetime, timezone

from backend.data.validators import validate_ohlcv_record, validate_ohlcv_series
from tests.conftest import make_ohlcv


class TestValidateOHLCVRecord:
    def test_valid_record_passes(self) -> None:
        result = validate_ohlcv_record(make_ohlcv())
        assert result.valid
        assert result.errors == []

    def test_high_less_than_open_fails(self) -> None:
        record = make_ohlcv(open=43000.0, high=42500.0, low=41800.0, close=42200.0)
        result = validate_ohlcv_record(record)
        assert not result.valid
        assert any("high" in e and "open" in e for e in result.errors)

    def test_high_less_than_close_fails(self) -> None:
        record = make_ohlcv(open=42000.0, high=42100.0, low=41800.0, close=42500.0)
        result = validate_ohlcv_record(record)
        assert not result.valid
        assert any("high" in e and "close" in e for e in result.errors)

    def test_low_greater_than_open_fails(self) -> None:
        record = make_ohlcv(open=42000.0, high=42500.0, low=42300.0, close=42200.0)
        result = validate_ohlcv_record(record)
        assert not result.valid
        assert any("low" in e and "open" in e for e in result.errors)

    def test_low_greater_than_close_fails(self) -> None:
        record = make_ohlcv(open=42000.0, high=42500.0, low=42300.0, close=42100.0)
        result = validate_ohlcv_record(record)
        assert not result.valid
        assert any("low" in e and "close" in e for e in result.errors)

    def test_negative_volume_fails(self) -> None:
        record = make_ohlcv(volume=-1.0)
        result = validate_ohlcv_record(record)
        assert not result.valid
        assert any("volume" in e for e in result.errors)

    def test_zero_volume_passes(self) -> None:
        record = make_ohlcv(volume=0.0)
        result = validate_ohlcv_record(record)
        assert result.valid

    def test_multiple_errors_reported(self) -> None:
        # high=42500 < open=43000 (error) AND high=42500 < close=42900 (error) AND volume<0 (error)
        # high (42500) >= low (41800) so schema validation passes
        record = make_ohlcv(open=43000.0, high=42500.0, low=41800.0, close=42900.0, volume=-5.0)
        result = validate_ohlcv_record(record)
        assert not result.valid
        assert len(result.errors) >= 2


class TestValidateOHLCVSeries:
    def test_valid_series_passes(self, sample_series: list) -> None:
        result = validate_ohlcv_series(sample_series)
        assert result.valid
        assert result.errors == []

    def test_empty_series_passes_with_warning(self) -> None:
        result = validate_ohlcv_series([])
        assert result.valid
        assert any("empty" in w for w in result.warnings)

    def test_non_monotonic_timestamps_fail(self) -> None:
        records = [
            make_ohlcv(timestamp=datetime(2024, 1, 1, 2, 0, 0, tzinfo=timezone.utc)),
            make_ohlcv(timestamp=datetime(2024, 1, 1, 1, 0, 0, tzinfo=timezone.utc)),
        ]
        result = validate_ohlcv_series(records)
        assert not result.valid
        assert any("non-monotonic" in e for e in result.errors)

    def test_duplicate_timestamps_fail(self) -> None:
        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        records = [make_ohlcv(timestamp=ts), make_ohlcv(timestamp=ts)]
        result = validate_ohlcv_series(records)
        assert not result.valid
        assert any("duplicate" in e for e in result.errors)

    def test_mixed_symbols_fail(self) -> None:
        records = [
            make_ohlcv(symbol="BTCUSDT", timestamp=datetime(2024, 1, 1, 0, tzinfo=timezone.utc)),
            make_ohlcv(symbol="ETHUSDT", timestamp=datetime(2024, 1, 1, 1, tzinfo=timezone.utc)),
        ]
        result = validate_ohlcv_series(records)
        assert not result.valid
        assert any("mixed symbols" in e for e in result.errors)

    def test_mixed_timeframes_fail(self) -> None:
        records = [
            make_ohlcv(timeframe="1h", timestamp=datetime(2024, 1, 1, 0, tzinfo=timezone.utc)),
            make_ohlcv(timeframe="1d", timestamp=datetime(2024, 1, 1, 1, tzinfo=timezone.utc)),
        ]
        result = validate_ohlcv_series(records)
        assert not result.valid
        assert any("mixed timeframes" in e for e in result.errors)

    def test_per_record_errors_surface_in_series(self) -> None:
        records = [
            make_ohlcv(timestamp=datetime(2024, 1, 1, 0, tzinfo=timezone.utc)),
            make_ohlcv(
                timestamp=datetime(2024, 1, 1, 1, tzinfo=timezone.utc),
                open=43000.0,
                high=42500.0,
                low=41800.0,
                close=42200.0,
            ),
        ]
        result = validate_ohlcv_series(records)
        assert not result.valid
        assert any("record[1]" in e for e in result.errors)
