"""
Trade Intent Extractor — Phase 2P.5.

Deterministic extraction of passive trade intents from a SignalEventBatch.
No market data loading. No indicator computation. No execution logic.
No order creation. No position simulation.

Default signal-to-intent mapping:
    entry  SignalEvent → open_long  TradeIntent
    exit   SignalEvent → close_long TradeIntent
    diagnostic SignalEvent → ignored (not converted; tracked in ignored_event_ids)

Intent ID contract:
    intent_id = f"intent:{signal_event_id}"
    This is deterministic and stable for identical inputs.

Ordering:
    Output ordering matches input SignalEventBatch ordering.
    Since the batch is already sorted (bar_index → entry/exit → rule_index → rule_id),
    the intent batch inherits the same stable ordering without re-sorting.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.backtesting
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

from backend.strategy_registry.signal_events import (
    SignalEvent,
    SignalEventBatch,
    SignalEventKind,
)
from backend.strategy_registry.trade_intents import (
    TradeIntent,
    TradeIntentAction,
    TradeIntentBatch,
    TradeIntentSource,
    TradeIntentSummary,
)

# ---------------------------------------------------------------------------
# Default signal → intent action mapping
# ---------------------------------------------------------------------------

_ACTION_MAP: dict[SignalEventKind, TradeIntentAction] = {
    SignalEventKind.ENTRY: TradeIntentAction.OPEN_LONG,
    SignalEventKind.EXIT:  TradeIntentAction.CLOSE_LONG,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_intent_id(signal_event_id: str) -> str:
    """Build a deterministic intent ID from the source signal event ID."""
    return f"intent:{signal_event_id}"


def _event_to_intent(event: SignalEvent) -> TradeIntent:
    """Convert a signal event to a trade intent (caller must ensure kind is mapped)."""
    action = _ACTION_MAP[event.kind]
    source = TradeIntentSource(
        signal_event_id=event.event_id,
        bar_index=event.source.bar_index,
        timestamp=event.source.timestamp,
        rule_id=event.source.rule_id,
        rule_kind=event.source.rule_kind,
    )
    return TradeIntent(
        intent_id=_make_intent_id(event.event_id),
        action=action,
        source=source,
    )


def _compute_summary(
    intents:      list[TradeIntent],
    ignored_count: int,
) -> TradeIntentSummary:
    open_long_count  = sum(1 for i in intents if i.action == TradeIntentAction.OPEN_LONG)
    close_long_count = sum(1 for i in intents if i.action == TradeIntentAction.CLOSE_LONG)
    first_bar        = intents[0].source.bar_index  if intents else None
    last_bar         = intents[-1].source.bar_index if intents else None
    return TradeIntentSummary(
        total_intents=len(intents),
        open_long_intents=open_long_count,
        close_long_intents=close_long_count,
        ignored_signal_events=ignored_count,
        first_intent_bar_index=first_bar,
        last_intent_bar_index=last_bar,
    )


# ---------------------------------------------------------------------------
# Public extraction function
# ---------------------------------------------------------------------------

def extract_trade_intents(
    signal_event_batch: SignalEventBatch,
) -> TradeIntentBatch:
    """
    Extract passive trade intents from a SignalEventBatch.

    Mapping:
        entry  → open_long
        exit   → close_long
        diagnostic → ignored (tracked in ignored_event_ids)

    Ordering matches the source batch (inherits stable deterministic order).

    This function does NOT:
        - generate orders
        - create positions
        - calculate PnL
        - apply sizing or pricing
        - perform compliance validation
        - produce execution intents

    Args:
        signal_event_batch: Ordered signal event batch from extract_signal_events().

    Returns:
        TradeIntentBatch with all intents, summary, and ignored event tracking.
    """
    intents:      list[TradeIntent] = []
    ignored_ids:  list[str]         = []

    for event in signal_event_batch.events:
        if event.kind in _ACTION_MAP:
            intents.append(_event_to_intent(event))
        else:
            # Diagnostic or unknown kind — do NOT convert to trade action
            ignored_ids.append(event.event_id)

    return TradeIntentBatch(
        plan_draft_id=signal_event_batch.plan_draft_id,
        intents=tuple(intents),
        summary=_compute_summary(intents, len(ignored_ids)),
        ignored_event_ids=tuple(ignored_ids),
    )
