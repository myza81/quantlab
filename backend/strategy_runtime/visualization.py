"""
Strategy visualization artifacts — reusable, strategy-agnostic chart overlay contracts.

Strategies return these from apply_risk_rules() under the "artifacts" key.
The frontend renders them generically based on artifact type — never based on
strategy identity.

Supported artifact types for Phase 2M:
  IndicatorSeries — a named line series rendered on a chart pane

Future-ready (not yet implemented):
  ReferenceLine   — horizontal price level
  Zone            — shaded price/time region
  OscillatorPane  — separate panel (e.g. RSI, MACD)
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator


class IndicatorSeriesKind(str, Enum):
    """Rendering style for an indicator series."""
    line = "line"
    # future: histogram = "histogram"
    # future: area = "area"


class IndicatorPane(str, Enum):
    """Chart pane the series belongs to."""
    price = "price"
    # future: oscillator = "oscillator"
    # future: separate = "separate"


class IndicatorPoint(BaseModel):
    """A single (timestamp, value) data point for an indicator series."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: datetime
    value: float

    @field_validator("timestamp")
    @classmethod
    def require_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC required)")
        return v.astimezone(timezone.utc)


class IndicatorSeries(BaseModel):
    """
    A named, typed sequence of (timestamp, value) points for chart rendering.

    Strategies return these as reusable visualization artifacts.
    The frontend renders them generically — it does not interpret the name or
    calculate any values itself.

    Invariants:
    - name must not be empty.
    - points is always a list; may be empty if strategy produced no data.
    - color is optional; frontend may apply a default palette.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    kind: IndicatorSeriesKind = IndicatorSeriesKind.line
    pane: IndicatorPane = IndicatorPane.price
    color: str | None = None
    points: list[IndicatorPoint] = []

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty or whitespace")
        return v
