"""
Signal Event Service — Phase 2P.4.

Orchestrates: compile semantics → evaluate history → extract signal events.

No market data. No indicator computation. No trade generation. No execution.
"""
from __future__ import annotations

from backend.api.schemas.historical_evaluation import HistoricalBarPayload
from backend.api.services.historical_evaluation_service import (
    HistoricalEvaluationError,
    evaluate_history_from_payload,
)
from backend.strategy_registry.semantics import StrategySemantics
from backend.strategy_registry.signal_event_extractor import extract_signal_events
from backend.strategy_registry.signal_events import SignalEventBatch


class SignalEventExtractionError(Exception):
    """Raised when evaluation or extraction fails."""


def extract_signal_events_from_payload(
    semantics: StrategySemantics,
    bars:      list[HistoricalBarPayload],
) -> SignalEventBatch:
    """
    Compile semantics, evaluate bars, and extract semantic signal events.

    Args:
        semantics: Strategy semantics to compile and evaluate.
        bars:      Ordered bar payloads with pre-loaded price and tool scalars.

    Returns:
        SignalEventBatch with ordered signal events and summary counts.

    Raises:
        SignalEventExtractionError: If compilation or evaluation fails.
    """
    try:
        historical_result = evaluate_history_from_payload(
            semantics=semantics,
            bars=bars,
        )
    except HistoricalEvaluationError as exc:
        raise SignalEventExtractionError(str(exc)) from exc

    return extract_signal_events(historical_result)
