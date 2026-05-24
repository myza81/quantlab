"""
Signal Event Extraction API route — Phase 2P.4.

POST /semantics/extract-signal-events

Accepts a StrategySemantics + list of pre-loaded bar payloads.
Compiles the semantics, evaluates each bar sequentially, and extracts
passive semantic signal events from triggered rules.

No portfolio. No trades. No PnL. No execution. No orders.

Signal events are informational — they record which rules triggered on
which bars. Capital allocation and execution decisions are not made here.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.api.schemas.historical_evaluation import HistoricalEvaluationRequest
from backend.api.services.signal_event_service import (
    SignalEventExtractionError,
    extract_signal_events_from_payload,
)
from backend.strategy_registry.signal_events import SignalEventBatch

router = APIRouter(prefix="/semantics", tags=["signal-events"])


@router.post("/extract-signal-events", response_model=SignalEventBatch)
def post_extract_signal_events(
    request: HistoricalEvaluationRequest,
) -> SignalEventBatch:
    """
    Evaluate semantics over bars and extract passive semantic signal events.

    Returns a SignalEventBatch with events ordered by bar_index → rule_kind
    (entry before exit) → rule_index → rule_id. Only True triggered rules
    produce signal events. False and indeterminate outcomes produce none.
    """
    try:
        return extract_signal_events_from_payload(
            semantics=request.semantics,
            bars=request.bars,
        )
    except SignalEventExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
