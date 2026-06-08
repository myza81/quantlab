"""
Historical Tool Computation Service — Phase 2R.0 / 2R.1 / 2S / 2U.

Bridges the gap between:
    StrategyToolSet + OHLCV price bars
and:
    HistoricalBarContext.tool_outputs

Pipeline:
    StrategyToolSet + ToolComputationBarInput[] + ToolRegistry
    → validate toolset against registry
    → compute tool outputs per bar (SMA, EMA, RSI, MACD, ATR, Bollinger in this phase)
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
    source: price_fields["close"]
    warmup: first (period - 1) bars produce no output
    output ref: "{instance_id}.sma"

EMA computation:
    alpha: 2 / (period + 1); seed = SMA of first `period` bars
    warmup: first (period - 1) bars produce no output
    output ref: "{instance_id}.ema"

RSI computation (Wilder's smoothing):
    seed: SMA of first `period` gains/losses (bars 1..period)
    smoothing: (avg * (period-1) + value) / period
    warmup: first `period` bars produce no output (needs `period` price diffs)
    output ref: "{instance_id}.rsi"

MACD computation:
    macd_line   = EMA(fast_period) - EMA(slow_period)
    signal_line = EMA(macd_line, signal_period)
    histogram   = macd_line - signal_line
    macd_line warmup:      slow_period - 1
    signal/histogram warmup: slow_period + signal_period - 2
    output refs: "{instance_id}.macd_line", "{instance_id}.signal_line",
                 "{instance_id}.histogram"

ATR computation (Wilder's smoothing):
    true_range[i] = max(H[i]-L[i], |H[i]-C[i-1]|, |L[i]-C[i-1]|)   (i >= 1)
    seed: SMA of first `period` true ranges
    smoothing: (atr_prev * (period-1) + tr_current) / period
    warmup: first `period` bars produce no output (needs `period` TRs)
    output ref: "{instance_id}.atr"

Bollinger Bands computation:
    middle_band = SMA(close, period)
    std_dev     = population stddev of close over same `period` window
    upper_band  = middle_band + multiplier × std_dev
    lower_band  = middle_band - multiplier × std_dev
    warmup: first (period - 1) bars produce no output (same as SMA)
    output refs: "{instance_id}.middle_band", "{instance_id}.upper_band",
                 "{instance_id}.lower_band"

Dispatch architecture:
    _TOOL_DISPATCHERS maps tool_id → compute function.
    One entry per tool — no other changes required when adding new tools.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.forward_testing
    backend.backtesting
"""
from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime
from typing import Any

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

        try:
            derive_warmup_bars_required(tool_config, metadata)
        except ToolComputationError:
            raise

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


def derive_warmup_bars_required(
    tool_config: ToolConfiguration,
    metadata: Any,
) -> int:
    """
    Derive the exact warmup requirement for one configured tool instance.

    The metadata-level min_warmup_bars is a floor. Each tool derives its actual
    warmup from its parameters:
      - SMA / EMA:  period - 1   (first value at bar index period-1)
      - RSI:        period       (needs `period` price diffs; first value at bar index period)
      - MACD:       slow_period + signal_period - 2  (signal EMA on MACD line)
    """
    tid = tool_config.tool_id
    if tid in {"sma", "ema"}:
        period = tool_config.parameters.get("period")
        if period is None:
            raise ToolComputationError(
                f"instance '{tool_config.instance_id}': missing period for warmup derivation"
            )
        warmup = _derive_period_warmup(period, tool_config.instance_id)
    elif tid == "rsi":
        period = tool_config.parameters.get("period", 14)
        warmup = int(period)   # needs `period` price diffs; first output at bar index `period`
    elif tid == "macd":
        slow   = int(tool_config.parameters.get("slow_period",   26))
        signal = int(tool_config.parameters.get("signal_period",  9))
        warmup = slow + signal - 2
    elif tid == "atr":
        period = tool_config.parameters.get("period", 14)
        warmup = int(period)   # needs `period` TRs; first output at bar index `period`
    elif tid == "bollinger_bands":
        period = tool_config.parameters.get("period", 20)
        warmup = int(period) - 1   # same as SMA; first output at bar index period-1
    elif tid == "volume":
        warmup = 0
    elif tid == "volume_ma":
        ma_length = tool_config.parameters.get("ma_length")
        warmup = 0 if ma_length is None else max(0, int(ma_length) - 1)
    else:
        warmup = int(getattr(metadata, "min_warmup_bars", 0))

    min_warmup = int(getattr(metadata, "min_warmup_bars", 0))
    return max(min_warmup, warmup)


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
    warmup = _derive_period_warmup(period, tool_config.instance_id)

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
# Source-field resolution helper — used by EMA (Tool-Backend-1A)
# ---------------------------------------------------------------------------

_VALID_SOURCE_FIELDS = frozenset({"close", "open", "high", "low", "hl2", "hlc3", "ohlc4"})
_EMA_OUTPUT_NAME     = "ema"  # matches EMA_METADATA.output_feature_names[0]


def _require_price_field(
    price_fields: dict[str, float],
    field:        str,
    instance_id:  str,
    bar_index:    int,
) -> float:
    """Return price_fields[field] or raise ToolComputationError if absent."""
    if field not in price_fields:
        raise ToolComputationError(
            f"instance '{instance_id}': "
            f"price_fields missing '{field}' at bar_index={bar_index}"
        )
    return price_fields[field]


def _resolve_source_value(
    source:       str,
    price_fields: dict[str, float],
    instance_id:  str,
    bar_index:    int,
) -> float:
    """
    Return the scalar price value for `source` from a single bar's price_fields.

    Supported sources:
        close   — closing price
        open    — opening price
        high    — session high
        low     — session low
        hl2     — (high + low) / 2
        hlc3    — (high + low + close) / 3
        ohlc4   — (open + high + low + close) / 4

    Raises:
        ToolComputationError: unknown source value or required price field absent.
    """
    if source not in _VALID_SOURCE_FIELDS:
        raise ToolComputationError(
            f"instance '{instance_id}': invalid source '{source}'. "
            f"Supported values: {sorted(_VALID_SOURCE_FIELDS)}"
        )
    get = _require_price_field  # brevity alias
    if source == "hl2":
        h = get(price_fields, "high",  instance_id, bar_index)
        l = get(price_fields, "low",   instance_id, bar_index)
        return (h + l) / 2.0
    if source == "hlc3":
        h = get(price_fields, "high",  instance_id, bar_index)
        l = get(price_fields, "low",   instance_id, bar_index)
        c = get(price_fields, "close", instance_id, bar_index)
        return (h + l + c) / 3.0
    if source == "ohlc4":
        o = get(price_fields, "open",  instance_id, bar_index)
        h = get(price_fields, "high",  instance_id, bar_index)
        l = get(price_fields, "low",   instance_id, bar_index)
        c = get(price_fields, "close", instance_id, bar_index)
        return (o + h + l + c) / 4.0
    # Simple named field: close, open, high, low
    return get(price_fields, source, instance_id, bar_index)


# ---------------------------------------------------------------------------
# EMA computation (internal)
# ---------------------------------------------------------------------------

def _compute_ema_series(
    tool_config: ToolConfiguration,
    bars:        list[ToolComputationBarInput],
) -> list[ToolOutputSeries]:
    """
    Compute EMA output series for one configured EMA instance.

    Rules:
    - period extracted from tool_config.parameters["period"]
    - source extracted from tool_config.parameters.get("source", "close")
    - seed: first valid EMA = SMA(source[0..period-1])
    - recursion: EMA_t = alpha × source_t + (1 - alpha) × EMA_{t-1},
                 alpha = 2 / (period + 1)
    - warmup: first (period - 1) bars produce no output point
    - no lookahead: bar N uses only source values at positions 0..N
    - deterministic: identical inputs → identical outputs
    - state is purely local to this computation pass

    Source values accepted:
        close (default), open, high, low, hl2, hlc3, ohlc4

    Args:
        tool_config: Validated EMA configuration with at least a "period" parameter.
                     Optional "source" parameter selects the price field (default "close").
        bars: Bar inputs sorted by bar_index; must include all price_fields required
              by the selected source.

    Returns:
        List with one ToolOutputSeries (EMA produces one output: "ema").

    Raises:
        ToolComputationError: invalid source value, or required price field absent.
    """
    period = int(tool_config.parameters["period"])
    source = str(tool_config.parameters.get("source", "close"))
    warmup = _derive_period_warmup(period, tool_config.instance_id)
    alpha  = 2.0 / (period + 1)

    # Validate source and extract per-bar prices in one pass
    prices: list[float] = []
    for bar in bars:
        prices.append(
            _resolve_source_value(source, bar.price_fields, tool_config.instance_id, bar.bar_index)
        )

    points: list[ToolOutputPoint] = []
    ema_value: float | None = None

    for i, bar in enumerate(bars):
        if i < warmup:
            continue

        if ema_value is None:
            # Seed: SMA of the first `period` source values (bars 0..period-1)
            ema_value = sum(prices[:period]) / period
        else:
            ema_value = alpha * prices[i] + (1.0 - alpha) * ema_value

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
# RSI computation (internal)
# ---------------------------------------------------------------------------

_RSI_CLOSE_FIELD  = "close"
_RSI_OUTPUT_NAME  = "rsi"   # matches RSI_METADATA.output_feature_names[0]


def _compute_rsi_series(
    tool_config: ToolConfiguration,
    bars:        list[ToolComputationBarInput],
) -> list[ToolOutputSeries]:
    """
    Compute RSI output series using Wilder's smoothing for one RSI instance.

    Rules:
    - period extracted from tool_config.parameters["period"] (default 14)
    - source field: always "close"
    - seed: SMA of the first `period` price changes (gains/losses)
    - smoothing: (avg * (period-1) + value) / period
    - warmup: first `period` bars produce no output point
      (bar 0 has no delta; bars 1..period provide the seed deltas;
       first RSI value appears at bar index `period`)
    - no lookahead: bar N's RSI uses only closes at positions 0..N
    - deterministic: identical inputs → identical outputs

    Args:
        tool_config: Validated RSI tool configuration.
        bars: Sorted (by bar_index) bar inputs; must have price_fields["close"].

    Returns:
        List with one ToolOutputSeries (RSI produces one output: "rsi").

    Raises:
        ToolComputationError: if "close" is missing from any bar's price_fields.
    """
    period  = int(tool_config.parameters.get("period", 14))
    warmup  = period   # first RSI value at bar_index position `period`

    closes: list[float] = []
    for bar in bars:
        if _RSI_CLOSE_FIELD not in bar.price_fields:
            raise ToolComputationError(
                f"instance '{tool_config.instance_id}': "
                f"price_fields missing '{_RSI_CLOSE_FIELD}' at bar_index={bar.bar_index}"
            )
        closes.append(bar.price_fields[_RSI_CLOSE_FIELD])

    points: list[ToolOutputPoint] = []
    avg_gain: float | None = None
    avg_loss: float | None = None

    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gain  = max(0.0, delta)
        loss  = abs(min(0.0, delta))

        if i < period:
            # Still accumulating seed deltas — no output yet
            continue

        if i == period:
            # Seed: SMA of the first `period` gains and losses (diffs at 1..period)
            gains_seed  = [max(0.0, closes[j] - closes[j - 1]) for j in range(1, period + 1)]
            losses_seed = [abs(min(0.0, closes[j] - closes[j - 1])) for j in range(1, period + 1)]
            avg_gain = sum(gains_seed) / period
            avg_loss = sum(losses_seed) / period
        else:
            # Wilder smoothing
            avg_gain = (avg_gain * (period - 1) + gain)  / period  # type: ignore[operator]
            avg_loss = (avg_loss * (period - 1) + loss)  / period  # type: ignore[operator]

        if avg_loss == 0.0:
            rsi = 100.0
        else:
            rs  = avg_gain / avg_loss   # type: ignore[operator]
            rsi = 100.0 - (100.0 / (1.0 + rs))

        points.append(ToolOutputPoint(
            bar_index=bars[i].bar_index,
            timestamp=bars[i].timestamp,
            value=rsi,
        ))

    return [ToolOutputSeries(
        instance_id=tool_config.instance_id,
        tool_id=tool_config.tool_id,
        output_name=_RSI_OUTPUT_NAME,
        warmup_bar_count=warmup,
        points=tuple(points),
    )]


# ---------------------------------------------------------------------------
# MACD computation (internal)
# ---------------------------------------------------------------------------

_MACD_CLOSE_FIELD     = "close"
_MACD_LINE_OUTPUT     = "macd_line"    # matches MACD_METADATA.output_feature_names[0]
_MACD_SIGNAL_OUTPUT   = "signal_line"  # matches MACD_METADATA.output_feature_names[1]
_MACD_HIST_OUTPUT     = "histogram"    # matches MACD_METADATA.output_feature_names[2]


def _compute_macd_series(
    tool_config: ToolConfiguration,
    bars:        list[ToolComputationBarInput],
) -> list[ToolOutputSeries]:
    """
    Compute MACD output series (three outputs) for one MACD instance.

    Rules:
    - fast_period: from parameters (default 12)
    - slow_period: from parameters (default 26)
    - signal_period: from parameters (default 9)
    - fast/slow EMAs seeded with SMA of first `period` closes
    - MACD line valid from bar slow_period - 1
    - Signal line EMA seeded with SMA of first `signal_period` MACD values
    - Signal/histogram valid from bar slow_period + signal_period - 2
    - No lookahead: bar N uses only closes 0..N
    - Deterministic: identical inputs → identical outputs
    - State is purely local to this computation pass

    Returns:
        List with three ToolOutputSeries:
            macd_line, signal_line, histogram.

    Raises:
        ToolComputationError: if "close" is missing from any bar's price_fields.
    """
    fast_period   = int(tool_config.parameters.get("fast_period",   12))
    slow_period   = int(tool_config.parameters.get("slow_period",   26))
    signal_period = int(tool_config.parameters.get("signal_period",  9))

    macd_line_warmup    = slow_period - 1
    signal_warmup       = slow_period + signal_period - 2

    closes: list[float] = []
    for bar in bars:
        if _MACD_CLOSE_FIELD not in bar.price_fields:
            raise ToolComputationError(
                f"instance '{tool_config.instance_id}': "
                f"price_fields missing '{_MACD_CLOSE_FIELD}' at bar_index={bar.bar_index}"
            )
        closes.append(bar.price_fields[_MACD_CLOSE_FIELD])

    # ── Compute fast and slow EMAs ──────────────────────────────────────────
    fast_alpha = 2.0 / (fast_period + 1)
    slow_alpha = 2.0 / (slow_period + 1)

    fast_ema: float | None = None
    slow_ema: float | None = None

    fast_ema_vals: list[float | None] = []
    slow_ema_vals: list[float | None] = []

    for i, close in enumerate(closes):
        # Fast EMA
        if i < fast_period - 1:
            fast_ema_vals.append(None)
        elif i == fast_period - 1:
            fast_ema = sum(closes[:fast_period]) / fast_period
            fast_ema_vals.append(fast_ema)
        else:
            fast_ema = fast_alpha * close + (1.0 - fast_alpha) * fast_ema  # type: ignore[operator]
            fast_ema_vals.append(fast_ema)

        # Slow EMA
        if i < slow_period - 1:
            slow_ema_vals.append(None)
        elif i == slow_period - 1:
            slow_ema = sum(closes[:slow_period]) / slow_period
            slow_ema_vals.append(slow_ema)
        else:
            slow_ema = slow_alpha * close + (1.0 - slow_alpha) * slow_ema  # type: ignore[operator]
            slow_ema_vals.append(slow_ema)

    # ── Compute MACD line (valid where both EMAs are available) ────────────
    macd_line_points:   list[ToolOutputPoint] = []
    macd_values_only:   list[float]           = []   # for signal EMA seed
    macd_bar_refs:      list[int]             = []   # bar index for each macd value

    for i, bar in enumerate(bars):
        f = fast_ema_vals[i]
        s = slow_ema_vals[i]
        if f is not None and s is not None:
            macd_val = f - s
            macd_line_points.append(ToolOutputPoint(
                bar_index=bar.bar_index,
                timestamp=bar.timestamp,
                value=macd_val,
            ))
            macd_values_only.append(macd_val)
            macd_bar_refs.append(i)

    # ── Compute signal EMA over MACD line ──────────────────────────────────
    sig_alpha = 2.0 / (signal_period + 1)
    signal_ema: float | None = None

    signal_points:   list[ToolOutputPoint] = []
    histogram_points: list[ToolOutputPoint] = []

    for local_i, (macd_val, bar_i) in enumerate(zip(macd_values_only, macd_bar_refs)):
        bar = bars[bar_i]
        if local_i < signal_period - 1:
            continue
        if local_i == signal_period - 1:
            signal_ema = sum(macd_values_only[:signal_period]) / signal_period
        else:
            signal_ema = sig_alpha * macd_val + (1.0 - sig_alpha) * signal_ema  # type: ignore[operator]

        signal_points.append(ToolOutputPoint(
            bar_index=bar.bar_index,
            timestamp=bar.timestamp,
            value=signal_ema,  # type: ignore[arg-type]
        ))
        histogram_points.append(ToolOutputPoint(
            bar_index=bar.bar_index,
            timestamp=bar.timestamp,
            value=macd_val - signal_ema,  # type: ignore[operator]
        ))

    iid = tool_config.instance_id
    tid = tool_config.tool_id
    return [
        ToolOutputSeries(
            instance_id=iid, tool_id=tid,
            output_name=_MACD_LINE_OUTPUT,
            warmup_bar_count=macd_line_warmup,
            points=tuple(macd_line_points),
        ),
        ToolOutputSeries(
            instance_id=iid, tool_id=tid,
            output_name=_MACD_SIGNAL_OUTPUT,
            warmup_bar_count=signal_warmup,
            points=tuple(signal_points),
        ),
        ToolOutputSeries(
            instance_id=iid, tool_id=tid,
            output_name=_MACD_HIST_OUTPUT,
            warmup_bar_count=signal_warmup,
            points=tuple(histogram_points),
        ),
    ]


# ---------------------------------------------------------------------------
# ATR computation (internal)
# ---------------------------------------------------------------------------

_ATR_HIGH_FIELD  = "high"
_ATR_LOW_FIELD   = "low"
_ATR_CLOSE_FIELD = "close"
_ATR_OUTPUT_NAME = "atr"   # matches ATR_METADATA.output_feature_names[0]


def _compute_atr_series(
    tool_config: ToolConfiguration,
    bars:        list[ToolComputationBarInput],
) -> list[ToolOutputSeries]:
    """
    Compute ATR output series using Wilder's smoothing for one ATR instance.

    Rules:
    - period extracted from tool_config.parameters["period"] (default 14)
    - source fields: "high", "low", "close"
    - true range: max(H-L, |H-C_prev|, |L-C_prev|) for each bar i >= 1
    - seed: SMA of the first `period` true ranges
    - smoothing: (atr_prev * (period-1) + tr) / period
    - warmup: first `period` bars produce no output
      (bar 0 has no TR; TRs at bars 1..period seed the initial ATR;
       first ATR value appears at bar index `period`)
    - no lookahead: bar N's ATR uses only closes at positions 0..N
    - deterministic: identical inputs → identical outputs

    Returns:
        List with one ToolOutputSeries (ATR produces one output: "atr").
    """
    period = int(tool_config.parameters.get("period", 14))
    warmup = period   # first ATR at bar position `period` (same pattern as RSI)

    for required_field in (_ATR_HIGH_FIELD, _ATR_LOW_FIELD, _ATR_CLOSE_FIELD):
        for bar in bars:
            if required_field not in bar.price_fields:
                raise ToolComputationError(
                    f"instance '{tool_config.instance_id}': "
                    f"price_fields missing '{required_field}' at bar_index={bar.bar_index}"
                )

    highs  = [b.price_fields[_ATR_HIGH_FIELD]  for b in bars]
    lows   = [b.price_fields[_ATR_LOW_FIELD]   for b in bars]
    closes = [b.price_fields[_ATR_CLOSE_FIELD] for b in bars]

    # tr_values[i] = TR for bars[i+1], using closes[i] as prev_close
    tr_values: list[float] = [
        max(highs[i + 1] - lows[i + 1],
            abs(highs[i + 1] - closes[i]),
            abs(lows[i + 1]  - closes[i]))
        for i in range(len(bars) - 1)
    ]

    points: list[ToolOutputPoint] = []
    atr: float | None = None

    for i, tr in enumerate(tr_values):
        if i < period - 1:
            continue

        if i == period - 1:
            # Seed: SMA of the first `period` true ranges
            atr = sum(tr_values[:period]) / period
        else:
            # Wilder smoothing
            atr = (atr * (period - 1) + tr) / period  # type: ignore[operator]

        # tr_values[i] corresponds to bars[i+1]
        bar = bars[i + 1]
        points.append(ToolOutputPoint(
            bar_index=bar.bar_index,
            timestamp=bar.timestamp,
            value=atr,  # type: ignore[arg-type]
        ))

    return [ToolOutputSeries(
        instance_id=tool_config.instance_id,
        tool_id=tool_config.tool_id,
        output_name=_ATR_OUTPUT_NAME,
        warmup_bar_count=warmup,
        points=tuple(points),
    )]


# ---------------------------------------------------------------------------
# Bollinger Bands computation (internal)
# ---------------------------------------------------------------------------

_BB_CLOSE_FIELD   = "close"
_BB_MIDDLE_OUTPUT = "middle_band"   # matches BOLLINGER_METADATA.output_feature_names[0]
_BB_UPPER_OUTPUT  = "upper_band"    # matches BOLLINGER_METADATA.output_feature_names[1]
_BB_LOWER_OUTPUT  = "lower_band"    # matches BOLLINGER_METADATA.output_feature_names[2]


def _compute_bollinger_series(
    tool_config: ToolConfiguration,
    bars:        list[ToolComputationBarInput],
) -> list[ToolOutputSeries]:
    """
    Compute Bollinger Bands (three output series) for one configured instance.

    Rules:
    - period extracted from tool_config.parameters["period"] (default 20)
    - std_dev extracted from tool_config.parameters["std_dev"] (default 2.0)
    - source field: always "close"
    - middle_band = SMA(close, period)
    - std_dev_value = population stddev(close, period)
    - upper_band = middle_band + multiplier × std_dev_value
    - lower_band = middle_band - multiplier × std_dev_value
    - warmup: first (period - 1) bars produce no output (same as SMA)
    - no lookahead: bar N uses only closes at positions 0..N
    - deterministic: identical inputs → identical outputs
    - state is local to this computation pass (stateless per-window)

    Returns:
        List with three ToolOutputSeries: middle_band, upper_band, lower_band.
    """
    period     = int(tool_config.parameters.get("period",  20))
    multiplier = float(tool_config.parameters.get("std_dev", 2.0))
    warmup     = period - 1   # same as SMA; first output at bar index period-1

    closes: list[float] = []
    for bar in bars:
        if _BB_CLOSE_FIELD not in bar.price_fields:
            raise ToolComputationError(
                f"instance '{tool_config.instance_id}': "
                f"price_fields missing '{_BB_CLOSE_FIELD}' at bar_index={bar.bar_index}"
            )
        closes.append(bar.price_fields[_BB_CLOSE_FIELD])

    middle_points: list[ToolOutputPoint] = []
    upper_points:  list[ToolOutputPoint] = []
    lower_points:  list[ToolOutputPoint] = []

    for i, bar in enumerate(bars):
        if i < warmup:
            continue

        window   = closes[i - period + 1 : i + 1]
        mean     = sum(window) / period
        variance = sum((x - mean) ** 2 for x in window) / period
        sigma    = math.sqrt(variance)

        middle_points.append(ToolOutputPoint(bar_index=bar.bar_index, timestamp=bar.timestamp, value=mean))
        upper_points.append( ToolOutputPoint(bar_index=bar.bar_index, timestamp=bar.timestamp, value=mean + multiplier * sigma))
        lower_points.append( ToolOutputPoint(bar_index=bar.bar_index, timestamp=bar.timestamp, value=mean - multiplier * sigma))

    iid = tool_config.instance_id
    tid = tool_config.tool_id
    return [
        ToolOutputSeries(
            instance_id=iid, tool_id=tid,
            output_name=_BB_MIDDLE_OUTPUT,
            warmup_bar_count=warmup,
            points=tuple(middle_points),
        ),
        ToolOutputSeries(
            instance_id=iid, tool_id=tid,
            output_name=_BB_UPPER_OUTPUT,
            warmup_bar_count=warmup,
            points=tuple(upper_points),
        ),
        ToolOutputSeries(
            instance_id=iid, tool_id=tid,
            output_name=_BB_LOWER_OUTPUT,
            warmup_bar_count=warmup,
            points=tuple(lower_points),
        ),
    ]


# ---------------------------------------------------------------------------
# Raw Volume computation (internal) — "volume" tool
# ---------------------------------------------------------------------------

_RAW_VOLUME_OUTPUT_NAME = "volume"  # matches VOLUME_METADATA.output_feature_names[0]


def _compute_raw_volume_series(
    tool_config: ToolConfiguration,
    bars:        list[ToolComputationBarInput],
) -> list[ToolOutputSeries]:
    """
    Emit raw per-bar volume for the standalone 'volume' tool.

    Rules:
    - No parameters; warmup = 0; every bar produces one output point.
    - volume field: price_fields["volume"] — must be present on every bar.
    - No smoothing, no derived calculation.
    - Deterministic: identical inputs → identical outputs.

    Returns:
        List with one ToolOutputSeries (output_name="volume").

    Raises:
        ToolComputationError: if "volume" is absent from any bar's price_fields.
    """
    points: list[ToolOutputPoint] = []
    for bar in bars:
        if "volume" not in bar.price_fields:
            raise ToolComputationError(
                f"instance '{tool_config.instance_id}': "
                f"price_fields missing 'volume' at bar_index={bar.bar_index}"
            )
        points.append(ToolOutputPoint(
            bar_index=bar.bar_index,
            timestamp=bar.timestamp,
            value=bar.price_fields["volume"],
        ))

    return [ToolOutputSeries(
        instance_id=tool_config.instance_id,
        tool_id=tool_config.tool_id,
        output_name=_RAW_VOLUME_OUTPUT_NAME,
        warmup_bar_count=0,
        points=tuple(points),
    )]


# ---------------------------------------------------------------------------
# Volume Moving Average computation (internal) — "volume_ma" tool
# ---------------------------------------------------------------------------
#
# Strategy output contract: only "volume_ma" is emitted.
# Chart visualization contract: the volume histogram is rendered separately by
# the chart artifact service reading price_fields["volume"] directly from bars.
# These contracts are intentionally different — raw volume is not a strategy
# output of this tool; it is a visualization aid.

_VOLUME_MA_OUTPUT_NAME = "volume_ma"  # matches VOLUME_MA_METADATA.output_feature_names[0]


def _compute_volume_series(
    tool_config: ToolConfiguration,
    bars:        list[ToolComputationBarInput],
) -> list[ToolOutputSeries]:
    """
    Compute the volume MA output series for the 'volume_ma' tool.

    Rules:
    - ma_length: extracted from parameters; None → no strategy output emitted
    - volume field: price_fields["volume"] — must be present when ma_length given
    - MA: SMA of volume with warmup = ma_length - 1
      (first MA value at bar index ma_length - 1)
    - invalid ma_length (non-positive, non-integer) → ToolComputationError
    - ma_length > available bars → MA series has zero points (no crash)
    - no lookahead: bar N uses volumes 0..N
    - deterministic: identical inputs → identical outputs

    Strategy output only:
        Returns [] when ma_length is None.
        Returns [ToolOutputSeries(output_name="volume_ma")] when ma_length is set.

    Volume histogram for chart:
        NOT emitted here. The chart artifact service reads price_fields["volume"]
        directly from bars when building the chart series for the histogram spec.

    Raises:
        ToolComputationError: ma_length invalid, or volume field absent when needed.
    """
    ma_length_raw = tool_config.parameters.get("ma_length")

    if ma_length_raw is None:
        # No MA requested. Chart histogram is handled by the artifact service;
        # no strategy output is produced by this tool instance.
        return []

    # Validate and parse ma_length
    try:
        ma_length = int(ma_length_raw)
    except (ValueError, TypeError) as exc:
        raise ToolComputationError(
            f"instance '{tool_config.instance_id}': "
            f"ma_length must be an integer, got {ma_length_raw!r}"
        ) from exc
    if ma_length < 1:
        raise ToolComputationError(
            f"instance '{tool_config.instance_id}': "
            f"ma_length must be >= 1, got {ma_length}"
        )

    # Extract volumes; validate presence on every bar
    volumes: list[float] = []
    for bar in bars:
        if "volume" not in bar.price_fields:
            raise ToolComputationError(
                f"instance '{tool_config.instance_id}': "
                f"price_fields missing 'volume' at bar_index={bar.bar_index}"
            )
        volumes.append(bar.price_fields["volume"])

    warmup = ma_length - 1
    ma_points: list[ToolOutputPoint] = []
    running_sum = 0.0

    for i, bar in enumerate(bars):
        running_sum += volumes[i]
        if i >= warmup:
            if i >= ma_length:
                running_sum -= volumes[i - ma_length]
            ma_value = running_sum / ma_length
            ma_points.append(ToolOutputPoint(
                bar_index=bar.bar_index,
                timestamp=bar.timestamp,
                value=ma_value,
            ))

    return [ToolOutputSeries(
        instance_id=tool_config.instance_id,
        tool_id=tool_config.tool_id,
        output_name=_VOLUME_MA_OUTPUT_NAME,
        warmup_bar_count=warmup,
        points=tuple(ma_points),
    )]


# ---------------------------------------------------------------------------
# Dispatcher registry (tool_id → compute function)
# ---------------------------------------------------------------------------
# Adding a new indicator: implement _compute_<tool>_series() above,
# then add one entry here. No other changes required.

_TOOL_DISPATCHERS: dict[
    str,
    Callable[[ToolConfiguration, list[ToolComputationBarInput]], list[ToolOutputSeries]],
] = {
    "sma":             _compute_sma_series,
    "ema":             _compute_ema_series,
    "rsi":             _compute_rsi_series,
    "macd":            _compute_macd_series,
    "atr":             _compute_atr_series,
    "bollinger_bands": _compute_bollinger_series,
    "volume":          _compute_raw_volume_series,
    "volume_ma":       _compute_volume_series,
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


def _derive_period_warmup(period: Any, instance_id: str) -> int:
    warmup = int(period) - 1
    if warmup < 0:
        raise ToolComputationError(
            f"instance '{instance_id}': warmup_bars_required must be >= 0"
        )
    return warmup
