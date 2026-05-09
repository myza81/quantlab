"""
Provider-specific dataset identity.

A DatasetIdentity is the combination of an Instrument, a data provider,
a timeframe, and an adjustment mode. The same instrument from different
providers (e.g. AAPL/yahoo vs AAPL/polygon) constitutes separate datasets
and must never be silently merged.
"""
from pydantic import BaseModel, ConfigDict, field_validator

from backend.data.models.instrument import AdjustmentMode, Instrument
from backend.data.schemas import ALLOWED_TIMEFRAMES


class DatasetIdentity(BaseModel):
    """
    Provider-specific dataset identity.

    Guarantees that data from different providers is always stored and
    tracked separately, even for the same underlying instrument.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    instrument: Instrument
    provider: str        # e.g. "yahoo", "polygon", "ibkr", "csv"
    timeframe: str       # canonical timeframe, e.g. "1h", "1d"
    adjustment_mode: AdjustmentMode = AdjustmentMode.RAW

    @field_validator("provider")
    @classmethod
    def provider_must_not_be_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("provider must not be empty or whitespace")
        return stripped.lower()

    @field_validator("timeframe")
    @classmethod
    def timeframe_must_be_canonical(cls, v: str) -> str:
        if v not in ALLOWED_TIMEFRAMES:
            raise ValueError(
                f"timeframe '{v}' is not canonical; allowed: {sorted(ALLOWED_TIMEFRAMES)}"
            )
        return v

    @property
    def dataset_id(self) -> str:
        """Unique identifier for this provider-specific dataset."""
        return (
            f"{self.instrument.instrument_id}"
            f"__{self.provider}"
            f"__{self.timeframe}"
            f"__{self.adjustment_mode.value}"
        )
