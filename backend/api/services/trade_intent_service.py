"""
Trade Intent Service — Phase 2P.5.

Thin service wrapping extract_trade_intents().
No market data. No execution. No portfolio logic.
"""
from __future__ import annotations

from backend.strategy_registry.signal_events import SignalEventBatch
from backend.strategy_registry.trade_intent_extractor import extract_trade_intents
from backend.strategy_registry.trade_intents import TradeIntentBatch


def extract_trade_intents_from_batch(
    signal_event_batch: SignalEventBatch,
) -> TradeIntentBatch:
    """
    Extract passive trade intents from a pre-built SignalEventBatch.

    Args:
        signal_event_batch: Ordered signal event batch.

    Returns:
        TradeIntentBatch with ordered intents and summary.
    """
    return extract_trade_intents(signal_event_batch)
