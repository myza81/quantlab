"""
Trade Intent Contract Layer — Phase 2P.5.

Passive trade intent models expressing what a future simulator or execution-policy
layer may consider — without executing, sizing, pricing, or allocating capital.

Architectural position:
    SignalEvent → TradeIntent   ← Phase 2P.5 (this layer)
    TradeIntent → Order         ← future execution layer (NOT this phase)

Critical separations:
    signal event  ≠  trade intent
    trade intent  ≠  order
    trade intent  ≠  position
    trade intent  ≠  PnL

Action minimalism:
    Only open_long and close_long are supported.
    Short selling, leverage, and margin are deliberately absent.
    Rationale: QuantLab must remain compatible with halal constraints.
    Execution policy will interpret intents by asset class in a future layer.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.backtesting
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Trade intent action
# ---------------------------------------------------------------------------

class TradeIntentAction(str, Enum):
    """
    High-level action declared by a trade intent.

    Deliberately minimal:
        open_long  — signal that a long position may be opened
        close_long — signal that a long position may be closed

    NOT present (by design):
        short_sell — excluded for halal compatibility
        open_short — excluded for halal compatibility
        leverage   — excluded; sizing belongs to execution policy
        margin     — excluded; belongs to execution policy
    """
    OPEN_LONG  = "open_long"
    CLOSE_LONG = "close_long"


# ---------------------------------------------------------------------------
# Trade intent source traceability
# ---------------------------------------------------------------------------

class TradeIntentSource(BaseModel):
    """
    Full traceability metadata linking a trade intent to its originating signal event.

    Preserves the signal event identity, bar, rule, and kind for audit and
    replay. Does NOT imply order parameters, pricing, or execution readiness.
    """
    model_config = ConfigDict(frozen=True)

    signal_event_id: str                    # event_id from the originating SignalEvent
    bar_index:       int
    timestamp:       datetime | None        # preserved from bar; None if not provided
    rule_id:         str | None             # rule_id from the plan node
    rule_kind:       Literal["entry", "exit"]


# ---------------------------------------------------------------------------
# Trade intent
# ---------------------------------------------------------------------------

class TradeIntent(BaseModel):
    """
    A single passive trade intent.

    Declared when a signal event maps to a recognizable action.
    Carries full traceability to the originating signal event and bar.

    Does NOT represent:
        - orders
        - fills
        - positions
        - broker instructions
        - capital allocation
        - quantity or price
        - execution timing
        - PnL expectations
    """
    model_config = ConfigDict(frozen=True)

    intent_id: str               # deterministic: "intent:{signal_event_id}"
    action:    TradeIntentAction
    source:    TradeIntentSource


# ---------------------------------------------------------------------------
# Trade intent summary
# ---------------------------------------------------------------------------

class TradeIntentSummary(BaseModel):
    """
    Aggregated counts over a TradeIntentBatch.

    No PnL. No positions. No portfolio state.
    Pure informational summary for observability.
    """
    model_config = ConfigDict(frozen=True)

    total_intents:          int
    open_long_intents:      int
    close_long_intents:     int
    ignored_signal_events:  int        # diagnostic events skipped
    first_intent_bar_index: int | None  # None if no intents
    last_intent_bar_index:  int | None  # None if no intents


# ---------------------------------------------------------------------------
# Trade intent batch
# ---------------------------------------------------------------------------

class TradeIntentBatch(BaseModel):
    """
    Complete, ordered collection of trade intents from one SignalEventBatch.

    Ordering matches the source SignalEventBatch ordering (bar_index → entry/exit
    → rule_index → rule_id), ensuring full traceability across layers.

    ignored_event_ids records signal event IDs that were not converted to intents
    (e.g. diagnostic events). These are tracked for audit purposes.

    Does NOT contain:
        - portfolio state
        - position records
        - trade records
        - PnL calculations
        - order parameters
        - execution instructions
    """
    model_config = ConfigDict(frozen=True)

    plan_draft_id:    str | None
    intents:          tuple[TradeIntent, ...]
    summary:          TradeIntentSummary
    ignored_event_ids: tuple[str, ...]    # event_ids of signals not converted to intents
