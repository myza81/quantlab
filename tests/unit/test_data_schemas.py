from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.data.schemas import ALLOWED_TIMEFRAMES, NormalizedOHLCV
from tests.conftest import make_ohlcv


class TestNormalizedOHLCVCreation:
    def test_valid_record_creates_successfully(self) -> None:
        record = make_ohlcv()
        assert record.symbol == "BTCUSDT"
        assert record.timeframe == "1h"
        assert record.timestamp.tzinfo is not None

    def test_timestamp_is_always_utc(self) -> None:
        from datetime import timedelta

        tz_plus8 = timezone(timedelta(hours=8))
        ts_local = datetime(2024, 1, 1, 8, 0, 0, tzinfo=tz_plus8)
        record = make_ohlcv(timestamp=ts_local)
        assert record.timestamp.tzinfo == timezone.utc
        assert record.timestamp.hour == 0

    def test_naive_timestamp_rejected(self) -> None:
        naive = datetime(2024, 1, 1, 0, 0, 0)
        with pytest.raises(ValidationError, match="timezone-aware"):
            make_ohlcv(timestamp=naive)

    def test_invalid_timeframe_rejected(self) -> None:
        with pytest.raises(ValidationError, match="canonical"):
            make_ohlcv(timeframe="2m")

    def test_all_allowed_timeframes_accepted(self) -> None:
        for tf in ALLOWED_TIMEFRAMES:
            record = make_ohlcv(timeframe=tf)
            assert record.timeframe == tf

    def test_empty_symbol_rejected(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            make_ohlcv(symbol="")

    def test_whitespace_only_symbol_rejected(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            make_ohlcv(symbol="   ")

    def test_symbol_is_stripped(self) -> None:
        record = make_ohlcv(symbol="  BTCUSDT  ")
        assert record.symbol == "BTCUSDT"

    def test_empty_source_rejected(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            make_ohlcv(source="")

    def test_high_less_than_low_rejected(self) -> None:
        with pytest.raises(ValidationError, match="high.*>=.*low"):
            make_ohlcv(high=41000.0, low=42000.0)

    def test_optional_fields_default_to_none(self) -> None:
        record = make_ohlcv()
        assert record.trade_count is None
        assert record.vwap is None
        assert record.metadata is None

    def test_optional_fields_accepted(self) -> None:
        record = make_ohlcv(trade_count=500, vwap=42100.0, metadata={"raw_id": "abc"})
        assert record.trade_count == 500
        assert record.vwap == 42100.0

    def test_unexpected_provider_field_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            NormalizedOHLCV(
                **make_ohlcv().model_dump(),
                provider_candle_id="abc123",
            )

    def test_record_is_immutable(self) -> None:
        record = make_ohlcv()
        with pytest.raises(Exception):
            record.close = 99999.0  # type: ignore[misc]
