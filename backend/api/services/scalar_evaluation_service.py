"""
Scalar Evaluation Service — Phase 2P.1.

Orchestrates: compile semantics → build context → evaluate plan → return trace.

No market data. No tool computation. No signal generation.
"""
from __future__ import annotations

import uuid

from backend.strategy_registry.evaluator_contracts import EvaluationTrace
from backend.strategy_registry.scalar_evaluation_context import ScalarEvaluationContext
from backend.strategy_registry.scalar_evaluator import ScalarEvaluationEngine
from backend.strategy_registry.semantic_compiler import compile_semantics
from backend.strategy_registry.semantics import StrategySemantics


class ScalarEvaluationError(Exception):
    """Raised when the semantics cannot be compiled for scalar evaluation."""


def evaluate_semantics_scalar(
    semantics:      StrategySemantics,
    scalar_context: dict[str, float],
    evaluation_id:  str | None = None,
) -> EvaluationTrace:
    """
    Compile semantics and evaluate against a pre-populated scalar context.

    Args:
        semantics:      Strategy semantics to compile and evaluate.
        scalar_context: Pre-resolved scalar values (price.*, tool.*.*).
        evaluation_id:  Optional evaluation identifier; auto-generated if None.

    Returns:
        EvaluationTrace with all rule results and trigger flags.

    Raises:
        ScalarEvaluationError: If semantics compilation fails.
    """
    result = compile_semantics(semantics, draft_id=None)
    if not result.compiled or result.evaluation_plan is None:
        raise ScalarEvaluationError(
            f"Semantics compilation failed: {'; '.join(result.errors)}"
        )

    eval_id = evaluation_id or str(uuid.uuid4())
    context = ScalarEvaluationContext(
        evaluation_id=eval_id,
        scalar_values=scalar_context,
    )
    engine = ScalarEvaluationEngine()
    return engine.evaluate_plan(result.evaluation_plan, context)
