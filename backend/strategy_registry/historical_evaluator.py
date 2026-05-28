"""
Historical Evaluation Iterator — Phase 2P.2 / updated Phase 2P.3.

Evaluates a pre-compiled EvaluationPlan sequentially over a historical bar sequence.
Each bar produces a two-bar context from current price fields + pre-injected tool
outputs, carrying the previous bar's values for crossover operator support.

NOT a backtesting engine. No portfolio. No trades. No PnL. No fills.
This is repeated single-bar semantic evaluation — deterministic and execution-free.

Design:
    Each bar is evaluated in sequence. The previous bar's scalar values are carried
    forward so TwoBarEvaluationContext can support crosses_above / crosses_below.
    For the first bar, previous_values=None → has_previous_bar=False → crossover
    operators return outcome=None with "no_previous_bar" diagnostic.

Constraints:
    - Sequential, deterministic, execution-free
    - No portfolio state, no positions, no trades, no PnL
    - Tool outputs must be pre-injected per bar — no computation here

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.backtesting
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from backend.strategy_registry.crossover_evaluator import TwoBarScalarEngine
from backend.strategy_registry.evaluator_contracts import EvaluationTrace
from backend.strategy_registry.two_bar_context import TwoBarEvaluationContext
from backend.strategy_registry.semantic_plan import EvaluationPlan


# ---------------------------------------------------------------------------
# Input contracts
# ---------------------------------------------------------------------------

class HistoricalBarContext(BaseModel):
    """
    Per-bar input for historical evaluation.

    price_fields: named scalar price values for this bar (e.g. "close", "open")
    tool_outputs: pre-computed tool output values keyed by "instance_id.output_name"

    No data is computed here. All values must be pre-loaded by the caller.
    The evaluator reads from these dicts; it never writes to them.
    """
    model_config = ConfigDict(frozen=True)

    bar_index:    int
    timestamp:    datetime | None = None
    price_fields: dict[str, float]       # e.g. {"close": 101.5, "open": 100.0}
    tool_outputs: dict[str, float] = {}  # e.g. {"sma_fast.value": 100.2}


class HistoricalEvaluationInput(BaseModel):
    """Complete input contract for a historical evaluation run."""
    model_config = ConfigDict(frozen=True)

    plan: EvaluationPlan
    bars: tuple[HistoricalBarContext, ...]


# ---------------------------------------------------------------------------
# Result contracts
# ---------------------------------------------------------------------------

class BarEvaluationResult(BaseModel):
    """Result of evaluating the EvaluationPlan against a single historical bar."""
    model_config = ConfigDict(frozen=True)

    bar_index:       int
    timestamp:       datetime | None
    entry_triggered: bool | None   # None if indeterminate (unresolved operands)
    exit_triggered:  bool | None   # None if indeterminate
    trace:           EvaluationTrace


class HistoricalEvaluationResult(BaseModel):
    """
    Aggregated result of evaluating an EvaluationPlan over a historical bar sequence.

    entry_triggered_count and exit_triggered_count count only True outcomes.
    Indeterminate (None) outcomes are not counted.

    No signal generation. No trade simulation. No PnL.
    Triggered flags are returned for the calling layer to interpret.
    """
    model_config = ConfigDict(frozen=True)

    plan_draft_id:         str | None
    bars_evaluated:        int
    entry_triggered_count: int  # bars where entry_triggered is True
    exit_triggered_count:  int  # bars where exit_triggered is True
    bar_results:           tuple[BarEvaluationResult, ...]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_scalar_values(bar: HistoricalBarContext) -> dict[str, float]:
    """
    Build a flat scalar values dict from a HistoricalBarContext.

    Key layout:
        price_fields["close"] → "price.close"
        tool_outputs["sma_fast.value"] → "tool.sma_fast.value"
    """
    values: dict[str, float] = {}
    for field, value in bar.price_fields.items():
        values[f"price.{field}"] = value
    for ref, value in bar.tool_outputs.items():
        values[f"tool.{ref}"] = value
    return values


def _build_scalar_context(
    bar:             HistoricalBarContext,
    plan_draft_id:   str | None,
    previous_values: dict[str, float] | None = None,
) -> TwoBarEvaluationContext:
    """Build a TwoBarEvaluationContext from current bar and optional previous values."""
    current_values = _build_scalar_values(bar)
    return TwoBarEvaluationContext(
        evaluation_id=f"{plan_draft_id or 'plan'}:bar:{bar.bar_index}",
        current_values=current_values,
        previous_values=previous_values,
        plan_draft_id=plan_draft_id,
    )


# ---------------------------------------------------------------------------
# Historical evaluation function
# ---------------------------------------------------------------------------

_TWO_BAR_ENGINE = TwoBarScalarEngine()  # stateless reusable instance


def evaluate_history(
    input: HistoricalEvaluationInput,
) -> HistoricalEvaluationResult:
    """
    Evaluate an EvaluationPlan sequentially over a historical bar sequence.

    Each bar is evaluated with its current values + the previous bar's values,
    enabling crossover operator support:

        HistoricalBarContext → TwoBarEvaluationContext → EvaluationTrace

    The previous bar's scalar values are carried forward between iterations.
    The first bar has no previous values (has_previous_bar=False); crossover
    operators on the first bar produce outcome=None with "no_previous_bar" diagnostic.

    Args:
        input: Pre-compiled EvaluationPlan + ordered bars with pre-loaded scalars.

    Returns:
        HistoricalEvaluationResult with per-bar results and aggregated counts.
    """
    bar_results: list[BarEvaluationResult] = []
    entry_triggered_count = 0
    exit_triggered_count  = 0

    sorted_bars = _sort_and_validate_bars(input.bars)
    previous_values: dict[str, float] | None = None

    for bar in sorted_bars:
        current_values = _build_scalar_values(bar)
        context = TwoBarEvaluationContext(
            evaluation_id=f"{input.plan.draft_id or 'plan'}:bar:{bar.bar_index}",
            current_values=current_values,
            previous_values=previous_values,
            plan_draft_id=input.plan.draft_id,
        )
        trace = _TWO_BAR_ENGINE.evaluate_plan(input.plan, context)

        bar_result = BarEvaluationResult(
            bar_index=bar.bar_index,
            timestamp=bar.timestamp,
            entry_triggered=trace.entry_triggered,
            exit_triggered=trace.exit_triggered,
            trace=trace,
        )
        bar_results.append(bar_result)

        if trace.entry_triggered is True:
            entry_triggered_count += 1
        if trace.exit_triggered is True:
            exit_triggered_count += 1

        previous_values = current_values  # propagate for next bar

    return HistoricalEvaluationResult(
        plan_draft_id=input.plan.draft_id,
        bars_evaluated=len(bar_results),
        entry_triggered_count=entry_triggered_count,
        exit_triggered_count=exit_triggered_count,
        bar_results=tuple(bar_results),
    )


def _sort_and_validate_bars(
    bars: tuple[HistoricalBarContext, ...],
) -> tuple[HistoricalBarContext, ...]:
    """
    Return bars in canonical replay order and reject ambiguous sequences.

    Historical replay state, especially previous-bar crossover state, must be
    based on ascending bar_index rather than caller payload order.
    """
    sorted_bars = tuple(sorted(bars, key=lambda b: b.bar_index))
    seen: set[int] = set()
    previous_timestamp: datetime | None = None

    for bar in sorted_bars:
        if bar.bar_index in seen:
            raise ValueError(f"duplicate bar_index={bar.bar_index} in historical evaluation")
        seen.add(bar.bar_index)

        if bar.timestamp is not None and previous_timestamp is not None:
            if bar.timestamp < previous_timestamp:
                raise ValueError(
                    "bar timestamps must be non-decreasing when ordered by bar_index"
                )
        if bar.timestamp is not None:
            previous_timestamp = bar.timestamp

    return sorted_bars
