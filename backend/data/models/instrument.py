"""
Provider-independent instrument identity.

An Instrument describes a tradeable security without any reference to a
specific data provider, broker, or data source. The same AAPL instrument
is the same regardless of whether data comes from Yahoo, Polygon, or IBKR.
"""
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator


class AdjustmentMode(str, Enum):
    """How price data has been adjusted for corporate actions."""
    RAW = "raw"
    ADJUSTED = "adjusted"
    SPLIT_ADJUSTED = "split_adjusted"


class Instrument(BaseModel):
    """
    Provider-independent instrument identity.

    Identifies a tradeable security without reference to any data vendor.
    Two datasets for the same Instrument but from different providers must
    be stored and tracked as separate datasets (see DatasetIdentity).
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str       # e.g. "AAPL", "BTCUSDT", "BRK_B"
    asset_class: str  # e.g. "equity", "crypto", "fx", "futures"
    exchange: str     # e.g. "NASDAQ", "BINANCE", "CME"
    currency: str = "USD"

    @field_validator("symbol", "asset_class", "exchange", "currency")
    @classmethod
    def must_not_be_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("must not be empty or whitespace")
        return stripped

    @property
    def instrument_id(self) -> str:
        """Stable, provider-independent composite identifier."""
        return f"{self.asset_class}__{self.exchange}__{self.symbol}"
