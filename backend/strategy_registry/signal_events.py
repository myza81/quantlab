"""
Signal Event Contracts — Phase 2P.4.

Passive semantic signal event models extracted from evaluation results.

Signal events represent semantic rule triggers from evaluation.
They do NOT represent orders, trades, fills, positions, or execution intent.

Critical architectural separation:
    rule triggered  ≠  trade executed
    entry signal    ≠  buy order
    exit signal     ≠  sell order

Signal events are informational. They preserve traceability to the bar,
rule, and evaluation trace that produced them. Capital allocation, order
generation, and execution decisions belong to future execution layers.

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

from backend.strategy_registry.evaluator_contracts import EvaluationDiagnostic


# ---------------------------------------------------------------------------
# Signal event classification
# ---------------------------------------------------------------------------

class SignalEventKind(str, Enum):
    """Classification of a signal event by semantic meaning."""
    ENTRY      = "entry"       # entry rule triggered True
    EXIT       = "exit"        # exit rule triggered True
    DIAGNOSTIC = "diagnostic"  # reserved; not emitted by default extractor


# ---------------------------------------------------------------------------
# Signal event source traceability
# ---------------------------------------------------------------------------

class SignalEventSource(BaseModel):
    """
    Traceability metadata linking a signal event back to its origin.

    Preserves the bar, rule, and kind for downstream audit and explainability.
    Does NOT imply execution intent.
    """
    model_config = ConfigDict(frozen=True)

    bar_index:  int
    timestamp:  datetime | None     # preserved from bar; None if not provided
    rule_id:    str | None          # rule_id from the plan node (may be None)
    rule_kind:  Literal["entry", "exit"]
    rule_index: int                 # position of the rule within entry_rules/exit_rules


# ---------------------------------------------------------------------------
# Signal event
# ---------------------------------------------------------------------------

class SignalEvent(BaseModel):
    """
    A single passive semantic signal event.

    Produced when an entry or exit rule evaluates to True for a given bar.
    Carries traceability to the bar, rule, and any diagnostics from the trace.

    Does NOT represent:
        - orders
        - trades
        - fills
        - positions
        - portfolio actions
        - broker instructions
        - execution intent of any kind
    """
    model_config = ConfigDict(frozen=True)

    event_id:    str                 # deterministic: "{bar_index}:{rule_kind}:{rule_index}:{rule_id}"
    kind:        SignalEventKind
    source:      SignalEventSource
    outcome:     bool                # always True for entry/exit events from extractor
    diagnostics: tuple[EvaluationDiagnostic, ...] = ()


# ---------------------------------------------------------------------------
# Signal event summary
# ---------------------------------------------------------------------------

class SignalEventSummary(BaseModel):
    """
    Aggregated counts over a SignalEventBatch.

    No PnL. No positions. No portfolio state.
    Pure informational summary for evaluation observability.
    """
    model_config = ConfigDict(frozen=True)

    total_events:         int
    entry_events:         int
    exit_events:          int
    diagnostic_events:    int
    bars_with_events:     int        # unique bar indices that produced at least one event
    first_event_bar_index: int | None  # bar_index of the earliest event; None if no events
    last_event_bar_index:  int | None  # bar_index of the latest event; None if no events


# ---------------------------------------------------------------------------
# Signal event batch
# ---------------------------------------------------------------------------

class SignalEventBatch(BaseModel):
    """
    Complete, ordered collection of signal events from one historical evaluation.

    Events are ordered by: bar_index → rule_kind (entry first) → rule_index → rule_id.
    This ordering is deterministic and stable across identical inputs.

    The batch preserves plan_draft_id from the source evaluation for linkage.

    Does NOT contain:
        - portfolio state
        - position records
        - trade records
        - PnL calculations
        - execution instructions
    """
    model_config = ConfigDict(frozen=True)

    plan_draft_id: str | None
    events:        tuple[SignalEvent, ...]
    summary:       SignalEventSummary
