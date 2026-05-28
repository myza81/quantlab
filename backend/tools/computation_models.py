"""
Tool Output Contracts — Phase 2R.0.

Defines the per-bar output contract for computed tool values produced by the
Historical Tool Computation Pipeline.

Design:
    ToolOutputPoint   — a single bar's computed scalar value for one output
    ToolOutputSeries  — all computed values for one (instance_id, output_name) pair
    ToolComputationResult — full computation result for an entire StrategyToolSet

Output reference format (matches evaluator key convention):
    "{instance_id}.{output_name}"

    Example:
        instance_id  = "sma_fast"
        output_name  = "sma"          (from ToolMetadata.output_feature_names)
        → ref key    = "sma_fast.sma"

This reference format matches how HistoricalBarContext.tool_outputs keyed values
are consumed by ScalarOperandResolver and TwoBarEvaluationContext.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.forward_testing
    backend.backtesting
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ToolOutputPoint(BaseModel):
    """
    A single bar's computed scalar value for one tool output.

    Produced only for bars where the output is available (past warmup).
    Warmup bars are omitted — their absence signals unavailability to callers.

    bar_index matches the bar_index from the corresponding ToolComputationBarInput.
    """
    model_config = ConfigDict(frozen=True)

    bar_index: int
    timestamp: datetime | None
    value:     float


class ToolOutputSeries(BaseModel):
    """
    All computed values for one (instance_id, output_name) pair across all bars.

    warmup_bar_count: number of leading bars that produced no output.
    points: only available (post-warmup) output points, ordered by bar_index.

    The output reference key is:
        f"{instance_id}.{output_name}"
    """
    model_config = ConfigDict(frozen=True)

    instance_id:      str
    tool_id:          str
    output_name:      str
    warmup_bar_count: int                    # bars at the start with no valid output
    points:           tuple[ToolOutputPoint, ...]  # ordered by bar_index

    @property
    def output_ref(self) -> str:
        """Return the evaluator-compatible reference key: 'instance_id.output_name'."""
        return f"{self.instance_id}.{self.output_name}"

    @property
    def warmup_bars_required(self) -> int:
        """Return the configured warmup requirement for this computed series."""
        return self.warmup_bar_count


class ToolComputationResult(BaseModel):
    """
    Complete computation result for a full StrategyToolSet over a bar sequence.

    Contains one ToolOutputSeries per (enabled tool instance × output_name).
    total_bars records the number of input bars processed (including warmup bars).

    Use build_bar_tool_outputs() to convert this result into the dict[bar_index →
    dict[ref, float]] format required by HistoricalBarContext.tool_outputs.
    """
    model_config = ConfigDict(frozen=True)

    toolset_id:  str
    total_bars:  int
    series:      tuple[ToolOutputSeries, ...]  # one per (instance_id, output_name)
