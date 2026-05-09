"""Tests for backend/data/models/ — Instrument, AdjustmentMode, DatasetIdentity."""
import pytest
from pydantic import ValidationError

from backend.data.models.instrument import AdjustmentMode, Instrument
from backend.data.models.dataset import DatasetIdentity


# ---------------------------------------------------------------------------
# AdjustmentMode
# ---------------------------------------------------------------------------

class TestAdjustmentMode:
    def test_enum_values_exist(self) -> None:
        assert AdjustmentMode.RAW.value == "raw"
        assert AdjustmentMode.ADJUSTED.value == "adjusted"
        assert AdjustmentMode.SPLIT_ADJUSTED.value == "split_adjusted"

    def test_is_str_enum(self) -> None:
        assert isinstance(AdjustmentMode.RAW, str)


# ---------------------------------------------------------------------------
# Instrument
# ---------------------------------------------------------------------------

class TestInstrument:
    def test_basic_creation(self) -> None:
        inst = Instrument(symbol="AAPL", asset_class="equity", exchange="NASDAQ")
        assert inst.symbol == "AAPL"
        assert inst.asset_class == "equity"
        assert inst.exchange == "NASDAQ"
        assert inst.currency == "USD"

    def test_currency_default_is_usd(self) -> None:
        inst = Instrument(symbol="AAPL", asset_class="equity", exchange="NASDAQ")
        assert inst.currency == "USD"

    def test_custom_currency(self) -> None:
        inst = Instrument(symbol="SHEL", asset_class="equity", exchange="LSE", currency="GBP")
        assert inst.currency == "GBP"

    def test_instrument_id_format(self) -> None:
        inst = Instrument(symbol="AAPL", asset_class="equity", exchange="NASDAQ")
        assert inst.instrument_id == "equity__NASDAQ__AAPL"

    def test_instrument_id_crypto(self) -> None:
        inst = Instrument(symbol="BTCUSDT", asset_class="crypto", exchange="BINANCE")
        assert inst.instrument_id == "crypto__BINANCE__BTCUSDT"

    def test_instrument_is_frozen(self) -> None:
        inst = Instrument(symbol="AAPL", asset_class="equity", exchange="NASDAQ")
        with pytest.raises(Exception):
            inst.symbol = "GOOG"  # type: ignore[misc]

    def test_empty_symbol_raises(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            Instrument(symbol="", asset_class="equity", exchange="NASDAQ")

    def test_whitespace_symbol_raises(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            Instrument(symbol="   ", asset_class="equity", exchange="NASDAQ")

    def test_whitespace_is_stripped(self) -> None:
        inst = Instrument(symbol=" AAPL ", asset_class="equity", exchange="NASDAQ")
        assert inst.symbol == "AAPL"

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            Instrument(symbol="AAPL", asset_class="equity", exchange="NASDAQ", broker="ibkr")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# DatasetIdentity
# ---------------------------------------------------------------------------

class _Instruments:
    AAPL = Instrument(symbol="AAPL", asset_class="equity", exchange="NASDAQ")
    BTC = Instrument(symbol="BTCUSDT", asset_class="crypto", exchange="BINANCE")


class TestDatasetIdentity:
    def test_basic_creation(self) -> None:
        did = DatasetIdentity(instrument=_Instruments.AAPL, provider="yahoo", timeframe="1d")
        assert did.provider == "yahoo"
        assert did.timeframe == "1d"
        assert did.adjustment_mode == AdjustmentMode.RAW

    def test_provider_lowercased(self) -> None:
        did = DatasetIdentity(instrument=_Instruments.AAPL, provider="Yahoo", timeframe="1d")
        assert did.provider == "yahoo"

    def test_default_adjustment_mode_is_raw(self) -> None:
        did = DatasetIdentity(instrument=_Instruments.AAPL, provider="yahoo", timeframe="1d")
        assert did.adjustment_mode == AdjustmentMode.RAW

    def test_custom_adjustment_mode(self) -> None:
        did = DatasetIdentity(
            instrument=_Instruments.AAPL,
            provider="yahoo",
            timeframe="1d",
            adjustment_mode=AdjustmentMode.ADJUSTED,
        )
        assert did.adjustment_mode == AdjustmentMode.ADJUSTED

    def test_dataset_id_format(self) -> None:
        did = DatasetIdentity(instrument=_Instruments.AAPL, provider="yahoo", timeframe="1d")
        assert did.dataset_id == "equity__NASDAQ__AAPL__yahoo__1d__raw"

    def test_different_providers_produce_different_dataset_ids(self) -> None:
        yahoo = DatasetIdentity(instrument=_Instruments.AAPL, provider="yahoo", timeframe="1d")
        polygon = DatasetIdentity(instrument=_Instruments.AAPL, provider="polygon", timeframe="1d")
        assert yahoo.dataset_id != polygon.dataset_id

    def test_different_adjustment_modes_produce_different_dataset_ids(self) -> None:
        raw = DatasetIdentity(instrument=_Instruments.AAPL, provider="yahoo", timeframe="1d",
                              adjustment_mode=AdjustmentMode.RAW)
        adj = DatasetIdentity(instrument=_Instruments.AAPL, provider="yahoo", timeframe="1d",
                              adjustment_mode=AdjustmentMode.ADJUSTED)
        assert raw.dataset_id != adj.dataset_id

    def test_invalid_timeframe_raises(self) -> None:
        with pytest.raises(ValidationError, match="not canonical"):
            DatasetIdentity(instrument=_Instruments.AAPL, provider="yahoo", timeframe="2d")

    def test_empty_provider_raises(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            DatasetIdentity(instrument=_Instruments.AAPL, provider="", timeframe="1d")

    def test_identity_is_frozen(self) -> None:
        did = DatasetIdentity(instrument=_Instruments.AAPL, provider="yahoo", timeframe="1d")
        with pytest.raises(Exception):
            did.provider = "polygon"  # type: ignore[misc]
