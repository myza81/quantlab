from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, field_validator


class SignalType(str, Enum):
    long = "long"
    short = "short"
    exit = "exit"
    reduce = "reduce"


class StrategySignal(BaseModel, frozen=True):
    """
    Canonical signal output from a strategy's generate_signals() call.

    Strategies produce StrategySignals only — never orders or broker instructions.
    Timestamp must be UTC-aware (naive datetimes are rejected).
    """

    strategy_id: str
    timestamp: datetime
    symbol: str
    timeframe: str
    signal_type: SignalType
    entry_reference: float
    invalidation_level: float
    # Optional fields per STRATEGY_CONTRACT.md
    confidence: float | None = None
    metadata: dict[str, Any] | None = None
    tags: list[str] | None = None
    reasoning: str | None = None
    feature_snapshot: dict[str, Any] | None = None
    setup_id: str | None = None

    @field_validator("timestamp")
    @classmethod
    def require_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC required)")
        return v.astimezone(timezone.utc)
