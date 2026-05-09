"""
Execution context passed to StrategyRuntimeRunner for a single strategy run.

Separates run-time configuration (what window, what mode, what parameters)
from the strategy's own logic. The runner receives this and passes relevant
fields down to strategy callables via the parameters dict.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class StrategyExecutionContext(BaseModel):
    """
    Describes the conditions under which a strategy is being executed.

    Invariants:
    - start, end, and created_at must be UTC-aware.
    - strategy_id and timeframe must not be empty.
    - parameters is passed verbatim to strategy callables; runners must not mutate it.

    Optional fields (instrument_id, initial_capital, research_tags) are placeholders
    for future phases (backtesting, portfolio context, research tagging).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: str
    runtime_mode: str
    timeframe: str
    start: datetime
    end: datetime
    parameters: dict[str, Any]
    created_at: datetime

    # Future-ready optional placeholders — not yet consumed by the runner
    instrument_id: str | None = None
    initial_capital: float | None = None
    research_tags: list[str] | None = None

    @field_validator("start", "end", "created_at")
    @classmethod
    def require_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("datetime must be timezone-aware (UTC required)")
        return v.astimezone(timezone.utc)

    @field_validator("strategy_id", "timeframe")
    @classmethod
    def must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty or whitespace")
        return v
