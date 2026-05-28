"""
Moving Average Convergence Divergence (MACD) tool — Phase 2S.

Provides:
    MACD_METADATA — registry metadata for the MACD tool
    compute_macd  — standalone MACD computation over NormalizedOHLCV (visualization path)

The historical computation pipeline entry point is in historical_computation.py
(_compute_macd_series), which operates on ToolComputationBarInput and produces
three ToolOutputSeries — the evaluator-compatible output format.

MACD formula:
    fast_ema    = EMA(close, fast_period)          alpha = 2 / (fast_period + 1)
    slow_ema    = EMA(close, slow_period)          alpha = 2 / (slow_period + 1)
    macd_line   = fast_ema - slow_ema
    signal_line = EMA(macd_line, signal_period)    alpha = 2 / (signal_period + 1)
    histogram   = macd_line - signal_line

All EMAs are seeded with the SMA of their first `period` inputs.

Outputs (three series per instance):
    macd_line   — warmup = slow_period - 1
    signal_line — warmup = slow_period + signal_period - 2
    histogram   — warmup = slow_period + signal_period - 2

Default configuration: fast=12, slow=26, signal=9.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime  (except visualization)
    backend.execution
    backend.forward_testing
    backend.backtesting
"""
from __future__ import annotations

from backend.data.schemas import NormalizedOHLCV
from backend.strategy_registry.models import RuntimeMode
from backend.strategy_runtime.visualization import (
    IndicatorPane,
    IndicatorPoint,
    IndicatorSeries,
    IndicatorSeriesKind,
)
from backend.tools.models import (
    ParameterSpec,
    ToolCategory,
    ToolMetadata,
    ToolStatus,
    VisualizationCapability,
)

MACD_METADATA = ToolMetadata(
    tool_id="macd",
    name="Moving Average Convergence Divergence",
    version="1.0.0",
    category=ToolCategory.indicator,
    status=ToolStatus.stable,
    description=(
        "Computes MACD using three EMAs. "
        "macd_line = EMA(fast) - EMA(slow); "
        "signal_line = EMA(macd_line, signal_period); "
        "histogram = macd_line - signal_line. "
        "All EMAs are SMA-seeded. Warmup = slow_period + signal_period - 2 bars. "
        "Three outputs: macd_line, signal_line, histogram. Stateful and deterministic."
    ),
    input_data_family="ohlcv",
    output_feature_names=("macd_line", "signal_line", "histogram"),
    parameters=(
        ParameterSpec(
            name="fast_period",
            description="Fast EMA window length. Must be >= 2 and < slow_period.",
            type_label="int",
            required=False,
            default=12,
            min_value=2,
        ),
        ParameterSpec(
            name="slow_period",
            description="Slow EMA window length. Must be >= 2 and > fast_period.",
            type_label="int",
            required=False,
            default=26,
            min_value=2,
        ),
        ParameterSpec(
            name="signal_period",
            description="Signal line EMA window length. Must be >= 2.",
            type_label="int",
            required=False,
            default=9,
            min_value=2,
        ),
        ParameterSpec(
            name="name",
            description="Custom label prefix for output series names.",
            type_label="str",
            required=False,
            default=None,
        ),
        ParameterSpec(
            name="color",
            description="Hex color string for the MACD line (e.g. '#2196f3').",
            type_label="str",
            required=False,
            default=None,
        ),
    ),
    supported_runtime_modes=frozenset({
        RuntimeMode.RESEARCH,
        RuntimeMode.BACKTESTING,
        RuntimeMode.FORWARD_TESTING,
        RuntimeMode.PAPER_TRADING,
        RuntimeMode.LIVE_TRADING,
    }),
    visualization_capabilities=frozenset({
        VisualizationCapability.produces_oscillator_series,
    }),
    # minimum warmup when using smallest valid periods (fast=2, slow=2, signal=2):
    # slow_period + signal_period - 2 = 2 + 2 - 2 = 2
    min_warmup_bars=2,
    stateful=True,  # recursive EMA: each bar depends on previous EMA values
)


def compute_macd(
    candles: list[NormalizedOHLCV],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    name: str | None = None,
    color: str | None = None,
) -> tuple[IndicatorSeries, IndicatorSeries, IndicatorSeries]:
    """
    Compute MACD over the close prices of the given candles (visualization path).

    Candles are sorted by timestamp internally; the caller need not pre-sort.
    Returns three indicator series: MACD line, signal line, histogram.

    MACD line first value: bar index slow_period - 1 (0-based).
    Signal/histogram first value: bar index slow_period + signal_period - 2 (0-based).

    Args:
        candles:       OHLCV records to compute over.
        fast_period:   Fast EMA window. Must be >= 2.
        slow_period:   Slow EMA window. Must be >= fast_period.
        signal_period: Signal line EMA window. Must be >= 2.
        name:          Label prefix. Defaults to "MACD".
        color:         Optional hex color hint for MACD line.

    Returns:
        Tuple of (macd_line_series, signal_line_series, histogram_series).

    Raises:
        ValueError: if period constraints are violated.
    """
    if fast_period < 2:
        raise ValueError(f"fast_period must be >= 2, got {fast_period}")
    if slow_period < fast_period:
        raise ValueError(f"slow_period ({slow_period}) must be >= fast_period ({fast_period})")
    if signal_period < 2:
        raise ValueError(f"signal_period must be >= 2, got {signal_period}")

    prefix = name if name else "MACD"

    empty_macd   = IndicatorSeries(name=f"{prefix} Line",      kind=IndicatorSeriesKind.line, pane=IndicatorPane.oscillator, color=color,   points=[])
    empty_signal = IndicatorSeries(name=f"{prefix} Signal",    kind=IndicatorSeriesKind.line, pane=IndicatorPane.oscillator, color="#ff6b00", points=[])
    empty_hist   = IndicatorSeries(name=f"{prefix} Histogram", kind=IndicatorSeriesKind.line, pane=IndicatorPane.oscillator, color="#78909c", points=[])

    if not candles:
        return empty_macd, empty_signal, empty_hist

    sorted_candles = sorted(candles, key=lambda c: c.timestamp)
    closes = [c.close for c in sorted_candles]
    timestamps = [c.timestamp for c in sorted_candles]

    fast_ema_vals, slow_ema_vals = _compute_dual_ema(closes, fast_period, slow_period)

    macd_vals: list[tuple[int, float]] = []   # (index, value)
    for i in range(len(closes)):
        f = fast_ema_vals[i]
        s = slow_ema_vals[i]
        if f is not None and s is not None:
            macd_vals.append((i, f - s))

    signal_vals, hist_vals = _compute_signal_and_hist(macd_vals, signal_period)

    macd_points   = [IndicatorPoint(timestamp=timestamps[i], value=v) for i, v in macd_vals]
    signal_points = [IndicatorPoint(timestamp=timestamps[i], value=v) for i, v in signal_vals]
    hist_points   = [IndicatorPoint(timestamp=timestamps[i], value=v) for i, v in hist_vals]

    return (
        IndicatorSeries(name=f"{prefix} Line",      kind=IndicatorSeriesKind.line, pane=IndicatorPane.oscillator, color=color,    points=macd_points),
        IndicatorSeries(name=f"{prefix} Signal",    kind=IndicatorSeriesKind.line, pane=IndicatorPane.oscillator, color="#ff6b00", points=signal_points),
        IndicatorSeries(name=f"{prefix} Histogram", kind=IndicatorSeriesKind.line, pane=IndicatorPane.oscillator, color="#78909c", points=hist_points),
    )


# ---------------------------------------------------------------------------
# Internal helpers (reused by historical_computation.py via import)
# ---------------------------------------------------------------------------

def _ema_series(values: list[float], period: int) -> list[float | None]:
    """
    Compute EMA over a list of scalar values. Returns a same-length list where
    the first (period-1) entries are None (warmup). Seed = SMA of first `period`
    values; subsequent values use alpha = 2 / (period + 1).
    """
    result: list[float | None] = [None] * len(values)
    alpha = 2.0 / (period + 1)
    ema: float | None = None

    for i, v in enumerate(values):
        if i < period - 1:
            continue
        if ema is None:
            ema = sum(values[:period]) / period
        else:
            ema = alpha * v + (1.0 - alpha) * ema
        result[i] = ema

    return result


def _compute_dual_ema(
    closes: list[float],
    fast_period: int,
    slow_period: int,
) -> tuple[list[float | None], list[float | None]]:
    """Return (fast_ema_series, slow_ema_series) over closes."""
    return _ema_series(closes, fast_period), _ema_series(closes, slow_period)


def _compute_signal_and_hist(
    macd_vals: list[tuple[int, float]],
    signal_period: int,
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """
    Compute signal line EMA and histogram over the MACD line values.

    macd_vals: list of (original_index, macd_value) in ascending original_index order.
    Returns (signal_vals, hist_vals) in the same (original_index, value) format,
    starting from the first bar where the signal line is valid.
    """
    if len(macd_vals) < signal_period:
        return [], []

    macd_only = [v for _, v in macd_vals]
    signal_ema = _ema_series(macd_only, signal_period)

    signal_vals: list[tuple[int, float]] = []
    hist_vals: list[tuple[int, float]] = []

    for local_i, (orig_i, macd_v) in enumerate(macd_vals):
        sig = signal_ema[local_i]
        if sig is not None:
            signal_vals.append((orig_i, sig))
            hist_vals.append((orig_i, macd_v - sig))

    return signal_vals, hist_vals
