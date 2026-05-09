from datetime import timezone
from pathlib import Path

import pytest

from backend.data_providers.csv_adapter import CSVAdapter, CSVAdapterConfig, CSVColumnMap


def make_config(**overrides: object) -> CSVAdapterConfig:
    defaults = dict(
        symbol="BTCUSDT",
        asset_class="crypto",
        venue="binance",
        timeframe="1h",
        source="csv_test",
    )
    defaults.update(overrides)
    return CSVAdapterConfig(**defaults)  # type: ignore[arg-type]


class TestCSVAdapterLoad:
    def test_loads_valid_csv(self, fixtures_dir: Path) -> None:
        adapter = CSVAdapter(make_config())
        records = adapter.load(file_path=fixtures_dir / "valid_ohlcv.csv")
        assert len(records) == 5

    def test_records_carry_config_metadata(self, fixtures_dir: Path) -> None:
        adapter = CSVAdapter(make_config(symbol="BTCUSDT", venue="binance"))
        records = adapter.load(file_path=fixtures_dir / "valid_ohlcv.csv")
        for r in records:
            assert r.symbol == "BTCUSDT"
            assert r.venue == "binance"
            assert r.asset_class == "crypto"
            assert r.source == "csv_test"

    def test_timestamps_are_utc(self, fixtures_dir: Path) -> None:
        adapter = CSVAdapter(make_config())
        records = adapter.load(file_path=fixtures_dir / "valid_ohlcv.csv")
        for r in records:
            assert r.timestamp.tzinfo == timezone.utc

    def test_naive_timestamps_treated_as_utc(self, fixtures_dir: Path) -> None:
        adapter = CSVAdapter(make_config())
        records = adapter.load(file_path=fixtures_dir / "valid_ohlcv_naive_ts.csv")
        assert len(records) == 2
        for r in records:
            assert r.timestamp.tzinfo == timezone.utc

    def test_unix_timestamps_parsed(self, fixtures_dir: Path) -> None:
        adapter = CSVAdapter(make_config())
        records = adapter.load(file_path=fixtures_dir / "valid_ohlcv_unix_ts.csv")
        assert len(records) == 2
        assert records[0].timestamp.year == 2024
        assert records[0].timestamp.tzinfo == timezone.utc

    def test_ohlcv_values_are_correct(self, fixtures_dir: Path) -> None:
        adapter = CSVAdapter(make_config())
        records = adapter.load(file_path=fixtures_dir / "valid_ohlcv.csv")
        first = records[0]
        assert first.open == 42000.0
        assert first.high == 42500.0
        assert first.low == 41800.0
        assert first.close == 42200.0
        assert first.volume == 1250.5

    def test_provider_name_is_csv(self) -> None:
        adapter = CSVAdapter(make_config())
        assert adapter.provider_name == "csv"

    def test_file_not_found_raises(self) -> None:
        adapter = CSVAdapter(make_config())
        with pytest.raises(FileNotFoundError, match="not found"):
            adapter.load(file_path="/nonexistent/path/data.csv")

    def test_missing_file_path_kwarg_raises(self) -> None:
        adapter = CSVAdapter(make_config())
        with pytest.raises(TypeError, match="file_path"):
            adapter.load()

    def test_missing_column_raises(self, tmp_path: Path) -> None:
        bad_csv = tmp_path / "bad.csv"
        bad_csv.write_text("timestamp,open,high,low,close\n2024-01-01T00:00:00+00:00,1,2,0.5,1.5\n")
        adapter = CSVAdapter(make_config())
        with pytest.raises(ValueError, match="missing required columns"):
            adapter.load(file_path=bad_csv)

    def test_custom_column_map(self, tmp_path: Path) -> None:
        csv_data = "ts,o,h,l,c,v\n2024-01-01T00:00:00+00:00,42000,42500,41800,42200,1250.5\n"
        csv_file = tmp_path / "custom.csv"
        csv_file.write_text(csv_data)

        col_map = CSVColumnMap(timestamp="ts", open="o", high="h", low="l", close="c", volume="v")
        adapter = CSVAdapter(make_config(columns=col_map))
        records = adapter.load(file_path=csv_file)
        assert len(records) == 1
        assert records[0].open == 42000.0

    def test_malformed_high_lt_low_still_loads(self, fixtures_dir: Path) -> None:
        # CSVAdapter creates NormalizedOHLCV which validates high >= low at schema level
        adapter = CSVAdapter(make_config())
        from pydantic import ValidationError
        with pytest.raises((ValidationError, ValueError)):
            adapter.load(file_path=fixtures_dir / "malformed_high_lt_low.csv")


class TestTimestampParsing:
    def _parse(self, raw: str) -> object:
        from backend.data_providers.csv_adapter import CSVAdapter
        return CSVAdapter._parse_timestamp(raw)

    def test_iso_with_utc_offset(self) -> None:
        dt = self._parse("2024-01-01T00:00:00+00:00")
        assert getattr(dt, "tzinfo") == timezone.utc

    def test_iso_with_z_suffix(self) -> None:
        dt = self._parse("2024-01-01T00:00:00Z")
        assert getattr(dt, "tzinfo") == timezone.utc

    def test_iso_with_non_utc_offset_is_normalized_to_utc(self) -> None:
        dt = self._parse("2024-01-01T08:00:00+08:00")
        assert getattr(dt, "tzinfo") == timezone.utc
        assert getattr(dt, "hour") == 0

    def test_iso_naive_becomes_utc(self) -> None:
        dt = self._parse("2024-01-01T00:00:00")
        assert getattr(dt, "tzinfo") == timezone.utc

    def test_date_only_becomes_midnight_utc(self) -> None:
        dt = self._parse("2024-01-01")
        from datetime import datetime
        assert isinstance(dt, datetime)
        assert getattr(dt, "hour") == 0
        assert getattr(dt, "tzinfo") == timezone.utc

    def test_unix_int_parsed(self) -> None:
        dt = self._parse("1704067200")
        from datetime import datetime
        assert isinstance(dt, datetime)
        assert getattr(dt, "year") == 2024

    def test_invalid_timestamp_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse"):
            self._parse("not-a-date")

    def test_invalid_large_unix_timestamp_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse"):
            self._parse("999999999999999999999")
