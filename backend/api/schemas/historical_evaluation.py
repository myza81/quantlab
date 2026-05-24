"""
Historical Evaluation API schemas — Phase 2P.2.

Request DTO for POST /semantics/evaluate-history.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from backend.strategy_registry.semantics import StrategySemantics
from backend.tools.toolset import StrategyToolSet


class HistoricalBarPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bar_index:    int
    timestamp:    datetime | None = None
    price_fields: dict[str, float]
    tool_outputs: dict[str, float] = {}


class HistoricalEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semantics: StrategySemantics
    bars:      list[HistoricalBarPayload]
    toolset:   StrategyToolSet | None = None  # if provided, server computes tool outputs from bars
