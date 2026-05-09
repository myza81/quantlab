from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

ALLOWED_TIMEFRAMES = frozenset(
    {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"}
)


class NormalizedOHLCV(BaseModel):
    """
    Canonical normalized OHLCV record per DATA_CONTRACT.md.

    Strategies and runtime systems must consume only this schema.
    Provider-native fields must never reach this layer.
    Immutable by design — records must not be modified after creation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Identity
    symbol: str
    asset_class: str
    venue: str
    timeframe: str
    source: str

    # Candle open time — UTC, timezone-aware (per DATA_CONTRACT.md timestamp contract)
    timestamp: datetime

    # OHLCV
    open: float
    high: float
    low: float
    close: float
    volume: float

    # Optional extended fields
    trade_count: Optional[int] = None
    vwap: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None
    adjustment_factor: Optional[float] = None
    metadata: Optional[dict[str, Any]] = None

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError(
                "timestamp must be timezone-aware; naive datetimes are forbidden per DATA_CONTRACT.md"
            )
        return v.astimezone(timezone.utc)

    @field_validator("timeframe")
    @classmethod
    def timeframe_must_be_canonical(cls, v: str) -> str:
        if v not in ALLOWED_TIMEFRAMES:
            raise ValueError(
                f"timeframe '{v}' is not a canonical identifier; "
                f"allowed: {sorted(ALLOWED_TIMEFRAMES)}"
            )
        return v

    @field_validator("symbol", "asset_class", "venue", "source")
    @classmethod
    def identity_fields_must_not_be_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("identity field must not be empty or whitespace")
        return stripped

    @model_validator(mode="after")
    def ohlcv_price_relationships(self) -> "NormalizedOHLCV":
        if self.high < self.low:
            raise ValueError(f"high ({self.high}) must be >= low ({self.low})")
        return self
