"""
StrategyRunResult — structured output from a single StrategyRuntimeRunner.run() call.

Reusable across all execution modes: research, backtest, forward test, paper trading.
The runner always returns a result — never raises directly — so callers can
inspect status and error without catching exceptions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from backend.strategy_runtime.forecast import StrategyForecast
from backend.strategy_runtime.models import StrategySignal


class RunStatus(str, Enum):
    success = "success"
    failed = "failed"
    empty = "empty"


class StrategyRunResult(BaseModel):
    """
    Structured result from a single strategy pipeline execution.

    Invariants:
    - started_at and completed_at must be UTC-aware.
    - status is always set; error is None on success/empty, set on failed.
    - signals and forecasts are always lists (empty if strategy did not produce them).
    - diagnostics always contains at least candles_received.

    Consumers should check `status` before accessing signals or forecasts.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: str
    runtime_mode: str
    status: RunStatus
    started_at: datetime
    completed_at: datetime

    candles_received: int
    features_generated: int

    signals: list[StrategySignal]
    forecasts: list[StrategyForecast]
    diagnostics: dict[str, Any]
    warnings: list[str]

    error: str | None = None

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("datetime must be timezone-aware (UTC required)")
        return v.astimezone(timezone.utc)
