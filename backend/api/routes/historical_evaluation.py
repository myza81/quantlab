"""
Historical Evaluation API route — Phase 2P.2.

POST /semantics/evaluate-history

Accepts a StrategySemantics + list of pre-loaded bar payloads.
Compiles the semantics, evaluates each bar sequentially, returns
HistoricalEvaluationResult with per-bar traces and aggregated counts.

No portfolio. No trades. No PnL. No execution.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.api.schemas.historical_evaluation import HistoricalEvaluationRequest
from backend.api.services.historical_evaluation_service import (
    HistoricalEvaluationError,
    evaluate_history_from_payload,
)
from backend.strategy_registry.historical_evaluator import HistoricalEvaluationResult

router = APIRouter(prefix="/semantics", tags=["historical-evaluation"])


@router.post("/evaluate-history", response_model=HistoricalEvaluationResult)
def post_evaluate_history(request: HistoricalEvaluationRequest) -> HistoricalEvaluationResult:
    """
    Evaluate a compiled StrategySemantics over a sequence of bar payloads.

    Two modes:
    - Manual: each bar supplies pre-computed tool_outputs (original path).
    - Toolset: provide toolset; server computes tool outputs from price fields.
      Do not also supply bar.tool_outputs when using toolset mode.

    Returns per-bar EvaluationTraces and aggregated trigger counts.
    """
    try:
        return evaluate_history_from_payload(
            semantics=request.semantics,
            bars=request.bars,
            toolset=request.toolset,
        )
    except HistoricalEvaluationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
