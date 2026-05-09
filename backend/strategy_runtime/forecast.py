"""
StrategyForecast — structured forward-looking output from a strategy run.

Forecasts are optional strategy outputs. Not all strategies will produce forecasts;
those that do should return them under the "forecasts" key in apply_risk_rules()
output. The frontend will later render these as chart annotations.

Strategies must never calculate price targets using execution-layer information.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class ForecastDirection(str, Enum):
    long = "long"
    short = "short"
    neutral = "neutral"


class StrategyForecast(BaseModel):
    """
    A single forward-looking price or directional forecast from a strategy.

    Intended for future frontend chart visualization — strategy runtime returns
    these as structured objects; the frontend renders them without recalculating.

    Invariants:
    - generated_at and target_timestamp must be UTC-aware.
    - confidence must be in [0.0, 1.0].
    - target_price must be positive.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    generated_at: datetime
    target_timestamp: datetime
    target_price: float
    direction: ForecastDirection
    confidence: float

    # Optional enrichment fields
    invalidation_price: float | None = None
    reason: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("generated_at", "target_timestamp")
    @classmethod
    def require_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("datetime must be timezone-aware (UTC required)")
        return v.astimezone(timezone.utc)

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("target_price")
    @classmethod
    def target_price_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"target_price must be positive, got {v}")
        return v
