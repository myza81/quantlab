"""
Scalar Evaluation API route — Phase 2P.1.

POST /semantics/evaluate-scalar

Accepts a StrategySemantics + flat scalar context dict.
Compiles the semantics, evaluates against the context, returns EvaluationTrace.

Single-bar only. No tool computation. No signal generation.

Phase 3S-B: requires require_active_subscription — strategy evaluation primitives
must not be publicly callable.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.api.schemas.scalar_evaluation import ScalarEvaluationRequest
from backend.api.services.scalar_evaluation_service import (
    ScalarEvaluationError,
    evaluate_semantics_scalar,
)
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.strategy_registry.evaluator_contracts import EvaluationTrace

router = APIRouter(prefix="/semantics", tags=["scalar-evaluation"])


@router.post("/evaluate-scalar", response_model=EvaluationTrace)
def post_evaluate_scalar(
    request: ScalarEvaluationRequest,
    current_user: User = Depends(require_active_subscription),
) -> EvaluationTrace:
    """
    Evaluate a compiled StrategySemantics against a pre-populated scalar context.

    The caller must supply all required tool output values and price fields
    in scalar_context — the evaluator performs no indicator computation.
    """
    try:
        return evaluate_semantics_scalar(
            semantics=request.semantics,
            scalar_context=request.scalar_context,
            evaluation_id=request.evaluation_id,
        )
    except ScalarEvaluationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
