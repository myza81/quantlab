"""
Historical Evaluation Service — Phase 2P.2 / 2R.0.

Orchestrates: compile semantics → compute tool outputs (optional) → convert bars
→ evaluate history → return result.

Two input paths:
  1. Manual tool_outputs per bar (original path) — caller pre-computes outputs.
  2. toolset provided — server computes tool outputs from price fields using the
     Historical Tool Computation Pipeline.

Ambiguity rule: if toolset is provided AND any bar carries non-empty tool_outputs,
the call is rejected with HistoricalEvaluationError to prevent silent overrides.
"""
from __future__ import annotations

from backend.api.schemas.historical_evaluation import HistoricalBarPayload
from backend.strategy_registry.historical_evaluator import (
    HistoricalBarContext,
    HistoricalEvaluationInput,
    HistoricalEvaluationResult,
    evaluate_history,
)
from backend.strategy_registry.semantic_compiler import compile_semantics
from backend.strategy_registry.semantics import StrategySemantics
from backend.tools import create_default_registry
from backend.tools.historical_computation import (
    ToolComputationBarInput,
    ToolComputationError,
    build_bar_tool_outputs,
    compute_tool_outputs_for_history,
)
from backend.tools.toolset import StrategyToolSet


class HistoricalEvaluationError(Exception):
    """Raised when the semantics cannot be compiled for historical evaluation."""


def evaluate_history_from_payload(
    semantics: StrategySemantics,
    bars:      list[HistoricalBarPayload],
    toolset:   StrategyToolSet | None = None,
) -> HistoricalEvaluationResult:
    """
    Compile semantics and evaluate over a sequence of bar payloads.

    When toolset is None, bar.tool_outputs are used as-is (original path).
    When toolset is provided, tool outputs are computed server-side from
    bar.price_fields via the Historical Tool Computation Pipeline and injected
    into each bar's context; caller must not also supply bar.tool_outputs.

    Args:
        semantics: Strategy semantics to compile and evaluate.
        bars:      Ordered bar payloads with price fields (and optionally tool outputs).
        toolset:   Optional toolset; if provided, server computes tool outputs.

    Returns:
        HistoricalEvaluationResult with per-bar results and aggregated counts.

    Raises:
        HistoricalEvaluationError: If semantics compilation or tool computation fails,
            or if both toolset and manual tool_outputs are provided (ambiguous).
    """
    result = compile_semantics(semantics, draft_id=None)
    if not result.compiled or result.evaluation_plan is None:
        raise HistoricalEvaluationError(
            f"Semantics compilation failed: {'; '.join(result.errors)}"
        )

    bar_tool_outputs: dict[int, dict[str, float]] = {}

    if toolset is not None:
        # Ambiguity check: caller must not mix manual and server-computed outputs
        ambiguous = [b.bar_index for b in bars if b.tool_outputs]
        if ambiguous:
            raise HistoricalEvaluationError(
                f"Ambiguous input: toolset provided but bar(s) {ambiguous} also carry "
                f"tool_outputs. Remove manual tool_outputs or omit the toolset."
            )

        computation_bars = [
            ToolComputationBarInput(
                bar_index=b.bar_index,
                timestamp=b.timestamp,
                price_fields=b.price_fields,
            )
            for b in bars
        ]

        try:
            computation_result = compute_tool_outputs_for_history(
                toolset=toolset,
                bars=computation_bars,
                registry=create_default_registry(),
            )
        except ToolComputationError as exc:
            raise HistoricalEvaluationError(f"Tool computation failed: {exc}") from exc

        bar_tool_outputs = build_bar_tool_outputs(computation_result)

    bar_contexts = tuple(
        HistoricalBarContext(
            bar_index=b.bar_index,
            timestamp=b.timestamp,
            price_fields=b.price_fields,
            tool_outputs=bar_tool_outputs.get(b.bar_index, b.tool_outputs),
        )
        for b in bars
    )

    return evaluate_history(
        HistoricalEvaluationInput(
            plan=result.evaluation_plan,
            bars=bar_contexts,
        )
    )
