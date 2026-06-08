"""
Composition run API schemas — Strategy Test Panel.

POST /strategy-runs/run-composition
    Input:  draft_id + OHLCV bars already loaded by the Chart page
    Output: CompositionRunResponse — signals + indicator series for overlay rendering
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CompositionRunBar(BaseModel):
    """Single OHLCV bar supplied by the frontend from its already-loaded chart dataset."""
    model_config = ConfigDict(frozen=True)

    bar_index: int
    timestamp: datetime | None = None
    open:      float
    high:      float
    low:       float
    close:     float
    volume:    float


class CompositionRunRequest(BaseModel):
    """
    Request body for POST /strategy-runs/run-composition.

    draft_id:  ID of the saved strategy composition to run.
    symbol:    Symbol the bars represent (metadata only; used in signal responses).
    timeframe: Timeframe the bars represent (metadata only).
    bars:      OHLCV bars already loaded on the Chart page, ordered by bar_index.
    """
    model_config = ConfigDict(extra="forbid")

    draft_id:  str
    symbol:    str
    timeframe: str
    bars:      list[CompositionRunBar]


class CompositionSignal(BaseModel):
    """Signal produced by a semantic rule trigger during composition run."""
    model_config = ConfigDict(frozen=True)

    timestamp:  datetime | None
    symbol:     str
    timeframe:  str
    signal_type: str   # 'long' | 'exit'
    bar_index:  int
    rule_id:    str | None = None


class CompositionIndicatorPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime | None
    value:     float


class CompositionIndicatorSeries(BaseModel):
    """Computed indicator series (SMA, EMA, etc.) for chart overlay rendering."""
    model_config = ConfigDict(frozen=True)

    name:        str
    kind:        str = "line"         # "line" | "histogram"
    pane:        str = "price"        # "price" | "oscillator"
    price_scale: str = "default"      # "default" | "volume"
    color:       str | None = None
    points:      list[CompositionIndicatorPoint]


class CompositionRunResponse(BaseModel):
    """
    Result of running a strategy composition against a chart dataset.

    Structured for direct consumption by the frontend overlay/indicator system.
    """
    draft_id:         str
    draft_name:       str
    status:           str   # 'success' | 'empty' | 'failed'
    candles_received: int
    signals:          list[CompositionSignal]
    indicators:       list[CompositionIndicatorSeries]
    warnings:         list[str]
    error:            str | None = None
