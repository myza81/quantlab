"""
Trade Intent Extraction API route — Phase 2P.5.

POST /semantics/extract-trade-intents

Accepts a SignalEventBatch.
Extracts passive trade intents from triggered signal events.

No portfolio. No trades. No PnL. No orders. No execution.

Trade intents are passive declarations — they express what a future
simulation or execution-policy layer may consider, without acting on it.
"""
from __future__ import annotations

from fastapi import APIRouter

from backend.api.services.trade_intent_service import extract_trade_intents_from_batch
from backend.strategy_registry.signal_events import SignalEventBatch
from backend.strategy_registry.trade_intents import TradeIntentBatch

router = APIRouter(prefix="/semantics", tags=["trade-intents"])


@router.post("/extract-trade-intents", response_model=TradeIntentBatch)
def post_extract_trade_intents(
    request: SignalEventBatch,
) -> TradeIntentBatch:
    """
    Extract passive trade intents from a SignalEventBatch.

    Maps entry signals to open_long intents and exit signals to close_long intents.
    Diagnostic signal events are ignored and tracked in ignored_event_ids.
    Returns a TradeIntentBatch with ordered intents and summary counts.
    """
    return extract_trade_intents_from_batch(request)
