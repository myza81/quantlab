"""
Signal Event Extractor — Phase 2P.4.

Deterministic extraction of passive semantic signal events from historical
evaluation results. No market data loading. No indicator computation.
No execution logic.

Extraction rules:
    entry_triggered=True  → entry SignalEvent emitted
    exit_triggered=True   → exit SignalEvent emitted
    outcome=False         → no event emitted
    outcome=None          → no event emitted (indeterminate; not a signal)

Ordering contract:
    Events are sorted by: bar_index → rule_kind (entry before exit)
    → rule_index → rule_id (lexicographic, None last).
    This ordering is deterministic. Tests must verify stability.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.backtesting
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

from backend.strategy_registry.historical_evaluator import (
    BarEvaluationResult,
    HistoricalEvaluationResult,
)
from backend.strategy_registry.signal_events import (
    SignalEvent,
    SignalEventBatch,
    SignalEventKind,
    SignalEventSource,
    SignalEventSummary,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_event_id(
    bar_index:  int,
    rule_kind:  str,
    rule_index: int,
    rule_id:    str | None,
) -> str:
    """
    Build a deterministic event identifier.

    Format: "{bar_index}:{rule_kind}:{rule_index}:{rule_id}"
    None rule_id is represented as the literal string "none".
    """
    return f"{bar_index}:{rule_kind}:{rule_index}:{rule_id or 'none'}"


def _extract_bar_events(bar_result: BarEvaluationResult) -> list[SignalEvent]:
    """Extract signal events for a single bar from its evaluation trace."""
    events: list[SignalEvent] = []

    for rule_result in bar_result.trace.rule_results:
        if rule_result.triggered is not True:
            continue  # False and None produce no signal events

        kind = (
            SignalEventKind.ENTRY
            if rule_result.kind == "entry"
            else SignalEventKind.EXIT
        )

        source = SignalEventSource(
            bar_index=bar_result.bar_index,
            timestamp=bar_result.timestamp,
            rule_id=rule_result.rule_id,
            rule_kind=rule_result.kind,
            rule_index=rule_result.index,
        )

        event = SignalEvent(
            event_id=_make_event_id(
                bar_result.bar_index,
                rule_result.kind,
                rule_result.index,
                rule_result.rule_id,
            ),
            kind=kind,
            source=source,
            outcome=True,
            diagnostics=rule_result.diagnostics,
        )
        events.append(event)

    return events


_RULE_KIND_ORDER = {"entry": 0, "exit": 1}


def _sort_key(event: SignalEvent) -> tuple:
    return (
        event.source.bar_index,
        _RULE_KIND_ORDER.get(event.source.rule_kind, 2),
        event.source.rule_index,
        event.source.rule_id or "",
    )


def _compute_summary(events: list[SignalEvent]) -> SignalEventSummary:
    entry_count      = sum(1 for e in events if e.kind == SignalEventKind.ENTRY)
    exit_count       = sum(1 for e in events if e.kind == SignalEventKind.EXIT)
    diagnostic_count = sum(1 for e in events if e.kind == SignalEventKind.DIAGNOSTIC)
    bars_with_events = len({e.source.bar_index for e in events})
    first_bar        = events[0].source.bar_index  if events else None
    last_bar         = events[-1].source.bar_index if events else None

    return SignalEventSummary(
        total_events=len(events),
        entry_events=entry_count,
        exit_events=exit_count,
        diagnostic_events=diagnostic_count,
        bars_with_events=bars_with_events,
        first_event_bar_index=first_bar,
        last_event_bar_index=last_bar,
    )


# ---------------------------------------------------------------------------
# Public extraction function
# ---------------------------------------------------------------------------

def extract_signal_events(
    historical_result: HistoricalEvaluationResult,
) -> SignalEventBatch:
    """
    Extract passive semantic signal events from a historical evaluation result.

    Only bars where entry_triggered=True or exit_triggered=True produce events.
    Indeterminate (None) and False outcomes are silently skipped.

    Events are sorted deterministically:
        bar_index → rule_kind (entry < exit) → rule_index → rule_id

    This function does NOT:
        - generate orders
        - create positions
        - calculate PnL
        - simulate trades
        - produce execution intents

    Args:
        historical_result: Completed historical evaluation result.

    Returns:
        SignalEventBatch with all events, summary, and plan linkage.
    """
    all_events: list[SignalEvent] = []

    for bar_result in historical_result.bar_results:
        all_events.extend(_extract_bar_events(bar_result))

    all_events.sort(key=_sort_key)

    return SignalEventBatch(
        plan_draft_id=historical_result.plan_draft_id,
        events=tuple(all_events),
        summary=_compute_summary(all_events),
    )
