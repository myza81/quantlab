"""
Historical Tool Computation Service — Phase 2R.0 / 2R.1.

Bridges the gap between:
    StrategyToolSet + OHLCV price bars
and:
    HistoricalBarContext.tool_outputs

Pipeline:
    StrategyToolSet + ToolComputationBarInput[] + ToolRegistry
    → validate toolset against registry
    → compute tool outputs per bar (SMA + EMA in this phase)
    → ToolComputationResult
    → build_bar_tool_outputs() → dict[bar_index, dict[ref, float]]
    → inject into HistoricalBarContext.tool_outputs
    → evaluate_history()

Key rules:
    - No lookahead bias: bar N uses only bars 0..N
    - Warmup bars produce NO output (key absent from bar_tool_outputs)
    - Computation is deterministic: identical inputs → identical outputs
    - Tools are computational primitives — no signal generation, no portfolio logic
    - Evaluator reads values; it never computes tools

SMA computation:
    source: price_fields["close"] (always; no source parameter yet)
    warmup: first (period - 1) bars produce no output
    output name: "sma" (from SMA_METADATA.output_feature_names)
    output ref: "{instance_id}.sma"

EMA computation:
    alpha: 2 / (period + 1)
    seed: SMA of first `period` bars
    warmup: first (period - 1) bars produce no output
    output name: "ema" (from EMA_METADATA.output_feature_names)
    output ref: "{instance_id}.ema"

Dispatch architecture:
    _TOOL_DISPATCHERS maps tool_id → compute function.
    Adding RSI, ATR, etc. in future phases is one registration per tool.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.forward_testing
    backend.backtesting
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from backend.tools.computation_models import (
    ToolComputationResult,
    ToolOutputPoint,
    ToolOutputSeries,
)
from backend.tools.configuration import ToolConfiguration
from backend.tools.registry import ToolRegistry
from backend.tools.toolset import StrategyToolSet
from backend.tools.validation import (
    ConfigurationValidationError,
    validate_tool_configuration,
)


# ---------------------------------------------------------------------------
# Input contract
# ---------------------------------------------------------------------------

class ToolComputationBarInput(BaseModel):
    """
    Minimal per-bar input for tool computation.

    price_fields must contain at least "close" for SMA computation.
    Additional fields (open, high, low, volume) may be used by future tools.

    bar_index must be unique across the input list.
    """
    model_config = ConfigDict(frozen=True)

    bar_index:    int
    timestamp:    datetime | None = None
    price_fields: dict[str, float]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ToolComputationError(Exception):
    """
    Raised when tool computation cannot proceed.

    Covers:
    - unknown tool_id in toolset
    - invalid tool parameters
    - missing required price field (e.g. "close")
    - unsupported tool_id in computation dispatcher
    """


# ---------------------------------------------------------------------------
# Public computation entry point
# ---------------------------------------------------------------------------

def compute_tool_outputs_for_history(
    toolset:  StrategyToolSet,
    bars:     list[ToolComputationBarInput],
    registry: ToolRegistry,
) -> ToolComputationResult:
    """
    Compute all tool outputs for every enabled tool in the toolset over the bar sequence.

    Only enabled tools (tool.enabled=True) are computed. Disabled tools are skipped.
    Bars are sorted internally by bar_index so caller ordering does not matter.
    Duplicate bar_index values raise ToolComputationError.

    Warmup bars are excluded from output points — their absence in the resulting
    dict signals unavailability to the downstream evaluator, which will produce
    indeterminate (None) outcomes for conditions that reference those bars.

    Args:
        toolset:  The StrategyToolSet declaring which tools to compute.
        bars:     Per-bar price field inputs; must include "close" for SMA.
        registry: Tool registry used to validate tool configurations.

    Returns:
        ToolComputationResult with one ToolOutputSeries per (instance_id, output_name).

    Raises:
        ToolComputationError: on validation failure, unsupported tool, or missing fields.
    """
    _validate_bar_index_uniqueness(bars)

    sorted_bars = sorted(bars, key=lambda b: b.bar_index)
    all_series: list[ToolOutputSeries] = []

    for tool_config in toolset.tools:
        if not tool_config.enabled:
            continue

        # Validate against registry (authority check)
        try:
            metadata = registry.get(tool_config.tool_id)
        except Exception as exc:
            raise ToolComputationError(
                f"instance '{tool_config.instance_id}': "
                f"tool_id '{tool_config.tool_id}' not found in registry"
            ) from exc

        try:
            validate_tool_configuration(tool_config, metadata)
        except ConfigurationValidationError as exc:
            raise ToolComputationError(
                f"instance '{tool_config.instance_id}' configuration invalid: "
                + "; ".join(exc.errors)
            ) from exc

        # Dispatch to tool-specific computation
        dispatcher = _TOOL_DISPATCHERS.get(tool_config.tool_id)
        if dispatcher is None:
            raise ToolComputationError(
                f"instance '{tool_config.instance_id}': "
                f"tool_id '{tool_config.tool_id}' has no computation dispatcher. "
                f"Supported tools: {sorted(_TOOL_DISPATCHERS)}"
            )

        series_list = dispatcher(tool_config, sorted_bars)
        all_series.extend(series_list)

    return ToolComputationResult(
        toolset_id=toolset.toolset_id,
        total_bars=len(sorted_bars),
        series=tuple(all_series),
    )


def build_bar_tool_outputs(
    result: ToolComputationResult,
) -> dict[int, dict[str, float]]:
    """
    Convert a ToolComputationResult into a bar-indexed output dict.

    Returns:
        dict mapping bar_index → {"instance_id.output_name": value}

    Bars within the warmup window have NO entry in the dict — their absence
    signals unavailability to the evaluator layer, which produces outcome=None
    for conditions that reference those bars. This is the correct no-lookahead
    behavior: warmup bars cannot trigger semantic conditions.

    Only bars with at least one available output appear as keys.
    Multiple series are merged: a single bar_index accumulates all available
    tool outputs from all series.
    """
    output: dict[int, dict[str, float]] = {}

    for series in result.series:
        ref = series.output_ref  # e.g. "sma_fast.sma"
        for point in series.points:
            bar_outputs = output.setdefault(point.bar_index, {})
            bar_outputs[ref] = point.value

    return output


# ---------------------------------------------------------------------------
# SMA computation (internal)
# ---------------------------------------------------------------------------

_SMA_CLOSE_FIELD = "close"
_SMA_OUTPUT_NAME = "sma"  # matches SMA_METADATA.output_feature_names[0]


def _compute_sma_series(
    tool_config: ToolConfiguration,
    bars:        list[ToolComputationBarInput],
) -> list[ToolOutputSeries]:
    """
    Compute SMA output series for one configured SMA instance.

    Rules:
    - period extracted from tool_config.parameters["period"]
    - source field: always "close" (price_fields["close"])
    - warmup: first (period - 1) bars produce no output point
    - no lookahead: bar N's SMA uses only closes at positions 0..N
    - deterministic: identical inputs → identical outputs

    Args:
        tool_config: Validated SMA tool configuration with period parameter.
        bars: Sorted (by bar_index) bar inputs; must have price_fields["close"].

    Returns:
        List with one ToolOutputSeries (SMA produces one output: "sma").

    Raises:
        ToolComputationError: if "close" is missing from any bar's price_fields.
    """
    period = int(tool_config.parameters["period"])
    warmup = period - 1

    # Extract close prices, validating presence
    closes: list[float] = []
    for bar in bars:
        if _SMA_CLOSE_FIELD not in bar.price_fields:
            raise ToolComputationError(
                f"instance '{tool_config.instance_id}': "
                f"price_fields missing '{_SMA_CLOSE_FIELD}' at bar_index={bar.bar_index}"
            )
        closes.append(bar.price_fields[_SMA_CLOSE_FIELD])

    points: list[ToolOutputPoint] = []
    running_sum = 0.0

    for i, bar in enumerate(bars):
        running_sum += closes[i]
        if i >= warmup:
            # Remove bar that fell out of window
            if i >= period:
                running_sum -= closes[i - period]
            sma_value = running_sum / period
            points.append(ToolOutputPoint(
                bar_index=bar.bar_index,
                timestamp=bar.timestamp,
                value=sma_value,
            ))

    return [ToolOutputSeries(
        instance_id=tool_config.instance_id,
        tool_id=tool_config.tool_id,
        output_name=_SMA_OUTPUT_NAME,
        warmup_bar_count=warmup,
        points=tuple(points),
    )]


# ---------------------------------------------------------------------------
# EMA computation (internal)
# ---------------------------------------------------------------------------

_EMA_CLOSE_FIELD = "close"
_EMA_OUTPUT_NAME = "ema"  # matches EMA_METADATA.output_feature_names[0]


def _compute_ema_series(
    tool_config: ToolConfiguration,
    bars:        list[ToolComputationBarInput],
) -> list[ToolOutputSeries]:
    """
    Compute EMA output series for one configured EMA instance.

    Rules:
    - period extracted from tool_config.parameters["period"]
    - source field: always "close" (price_fields["close"])
    - seed: first valid EMA = SMA(close[0..period-1])
    - recursion: EMA_t = alpha × close_t + (1 - alpha) × EMA_{t-1}
    - warmup: first (period - 1) bars produce no output point
    - no lookahead: bar N's EMA uses only closes at positions 0..N
    - deterministic: identical inputs → identical outputs
    - state is purely local to this computation pass

    Args:
        tool_config: Validated EMA tool configuration with period parameter.
        bars: Sorted (by bar_index) bar inputs; must have price_fields["close"].

    Returns:
        List with one ToolOutputSeries (EMA produces one output: "ema").

    Raises:
        ToolComputationError: if "close" is missing from any bar's price_fields.
    """
    period = int(tool_config.parameters["period"])
    warmup = period - 1
    alpha = 2.0 / (period + 1)

    # Extract close prices, validating presence
    closes: list[float] = []
    for bar in bars:
        if _EMA_CLOSE_FIELD not in bar.price_fields:
            raise ToolComputationError(
                f"instance '{tool_config.instance_id}': "
                f"price_fields missing '{_EMA_CLOSE_FIELD}' at bar_index={bar.bar_index}"
            )
        closes.append(bar.price_fields[_EMA_CLOSE_FIELD])

    points: list[ToolOutputPoint] = []
    ema_value: float | None = None

    for i, bar in enumerate(bars):
        if i < warmup:
            continue

        if ema_value is None:
            # Seed: SMA of the first `period` closes (bars 0..period-1)
            ema_value = sum(closes[:period]) / period
        else:
            ema_value = alpha * closes[i] + (1.0 - alpha) * ema_value

        points.append(ToolOutputPoint(
            bar_index=bar.bar_index,
            timestamp=bar.timestamp,
            value=ema_value,
        ))

    return [ToolOutputSeries(
        instance_id=tool_config.instance_id,
        tool_id=tool_config.tool_id,
        output_name=_EMA_OUTPUT_NAME,
        warmup_bar_count=warmup,
        points=tuple(points),
    )]


# ---------------------------------------------------------------------------
# Dispatcher registry (tool_id → compute function)
# ---------------------------------------------------------------------------
# Adding a new indicator: implement _compute_<tool>_series() above,
# then add one entry here. No other changes required.
# "rsi": _compute_rsi_series,
# "atr": _compute_atr_series,

_TOOL_DISPATCHERS: dict[
    str,
    "type[list[ToolOutputSeries]]",  # callable type annotation (runtime: plain dict)
] = {
    "sma": _compute_sma_series,  # type: ignore[dict-item]
    "ema": _compute_ema_series,  # type: ignore[dict-item]
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_bar_index_uniqueness(bars: list[ToolComputationBarInput]) -> None:
    seen: set[int] = set()
    for bar in bars:
        if bar.bar_index in seen:
            raise ToolComputationError(
                f"duplicate bar_index={bar.bar_index} in computation input"
            )
        seen.add(bar.bar_index)
