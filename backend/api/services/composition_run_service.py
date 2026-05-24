"""
Composition run service — Strategy Test Panel backend.

Orchestrates: fetch draft → compute tool outputs → evaluate semantics
→ extract signals + indicator series → CompositionRunResponse.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.forward_testing
    backend.backtesting
"""
from __future__ import annotations

import logging
from pathlib import Path

from backend.api.schemas.composition_run import (
    CompositionIndicatorPoint,
    CompositionIndicatorSeries,
    CompositionRunBar,
    CompositionRunResponse,
    CompositionSignal,
)
from backend.strategy_registry.draft_repository import DraftNotFoundError, DraftRepository
from backend.strategy_registry.historical_evaluator import (
    HistoricalBarContext,
    HistoricalEvaluationInput,
    evaluate_history,
)
from backend.strategy_registry.semantic_compiler import compile_semantics
from backend.tools import create_default_registry
from backend.tools.historical_computation import (
    ToolComputationBarInput,
    ToolComputationError,
    build_bar_tool_outputs,
    compute_tool_outputs_for_history,
)

logger = logging.getLogger(__name__)

_DEFAULT_STORAGE = Path("storage/strategy_drafts")


class CompositionRunError(Exception):
    """Raised for recoverable run failures."""


def run_composition(
    draft_id: str,
    symbol: str,
    timeframe: str,
    bars: list[CompositionRunBar],
    repository: DraftRepository,
) -> CompositionRunResponse:
    """
    Run a saved strategy composition against a set of OHLCV bars.

    Steps:
      1. Fetch draft from repository.
      2. Validate draft has semantics.
      3. Compile semantics into an evaluation plan.
      4. Compute tool outputs (SMA, EMA, etc.) from price bars.
      5. Evaluate semantics bar-by-bar.
      6. Extract entry/exit signals from evaluation traces.
      7. Convert tool output series to indicator overlay format.
      8. Return CompositionRunResponse.

    Raises:
        CompositionRunError: for any failure; wraps the underlying cause.
    """
    warnings: list[str] = []

    # Step 1 — fetch draft
    try:
        draft = repository.load(draft_id)
    except DraftNotFoundError as exc:
        raise CompositionRunError(f"Draft '{draft_id}' not found.") from exc

    draft_name = draft.display_name

    # Step 2 — validate semantics present
    if draft.semantics is None:
        raise CompositionRunError(
            f"Draft '{draft_id}' has no semantics. Add entry/exit rules in the Composer first."
        )

    semantics = draft.semantics
    toolset   = draft.toolset

    if len(bars) == 0:
        return CompositionRunResponse(
            draft_id=draft_id,
            draft_name=draft_name,
            status="empty",
            candles_received=0,
            signals=[],
            indicators=[],
            warnings=["No bars supplied."],
        )

    # Step 3 — compile semantics
    compile_result = compile_semantics(semantics, draft_id=draft_id)
    if not compile_result.compiled or compile_result.evaluation_plan is None:
        raise CompositionRunError(
            f"Semantics compilation failed: {'; '.join(compile_result.errors)}"
        )

    plan = compile_result.evaluation_plan

    # Step 4 — compute tool outputs
    computation_bars = [
        ToolComputationBarInput(
            bar_index=b.bar_index,
            timestamp=b.timestamp,
            price_fields={"open": b.open, "high": b.high, "low": b.low,
                          "close": b.close, "volume": b.volume},
        )
        for b in bars
    ]

    registry = create_default_registry()
    indicators: list[CompositionIndicatorSeries] = []

    if toolset.tools:
        try:
            computation_result = compute_tool_outputs_for_history(
                toolset=toolset,
                bars=computation_bars,
                registry=registry,
            )
        except ToolComputationError as exc:
            raise CompositionRunError(f"Tool computation failed: {exc}") from exc

        bar_tool_outputs = build_bar_tool_outputs(computation_result)

        # Build indicator series for overlay rendering
        for series in computation_result.series:
            # Use tool display_name if configured, else instance_id.output_name
            tool_cfg = next(
                (t for t in toolset.tools if t.instance_id == series.instance_id),
                None,
            )
            display = (
                tool_cfg.display_name
                if tool_cfg and tool_cfg.display_name
                else f"{series.instance_id}.{series.output_name}"
            )
            color = tool_cfg.color if tool_cfg else None

            indicators.append(CompositionIndicatorSeries(
                name=display,
                kind="line",
                pane="price",
                color=color,
                points=[
                    CompositionIndicatorPoint(timestamp=p.timestamp, value=p.value)
                    for p in series.points
                ],
            ))
    else:
        bar_tool_outputs = {}
        warnings.append("No tools configured — indicator overlays will be empty.")

    # Step 5 — evaluate semantics bar-by-bar
    bar_contexts = tuple(
        HistoricalBarContext(
            bar_index=b.bar_index,
            timestamp=b.timestamp,
            price_fields={"open": b.open, "high": b.high, "low": b.low,
                          "close": b.close, "volume": b.volume},
            tool_outputs=bar_tool_outputs.get(b.bar_index, {}),
        )
        for b in bars
    )

    eval_result = evaluate_history(HistoricalEvaluationInput(plan=plan, bars=bar_contexts))

    # Step 6 — extract signals from traces
    signals: list[CompositionSignal] = []
    for bar_result in eval_result.bar_results:
        if bar_result.entry_triggered is True:
            signals.append(CompositionSignal(
                timestamp=bar_result.timestamp,
                symbol=symbol,
                timeframe=timeframe,
                signal_type="long",
                bar_index=bar_result.bar_index,
            ))
        if bar_result.exit_triggered is True:
            signals.append(CompositionSignal(
                timestamp=bar_result.timestamp,
                symbol=symbol,
                timeframe=timeframe,
                signal_type="exit",
                bar_index=bar_result.bar_index,
            ))

    status = "empty" if not signals else "success"

    logger.info(
        "composition_run: draft=%s symbol=%s bars=%d signals=%d indicators=%d status=%s",
        draft_id, symbol, len(bars), len(signals), len(indicators), status,
    )

    return CompositionRunResponse(
        draft_id=draft_id,
        draft_name=draft_name,
        status=status,
        candles_received=len(bars),
        signals=signals,
        indicators=indicators,
        warnings=warnings,
    )
