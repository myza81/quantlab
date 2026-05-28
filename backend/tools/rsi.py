"""
Relative Strength Index (RSI) tool — Phase 2S.

Provides:
    RSI_METADATA — registry metadata for the RSI tool
    compute_rsi  — standalone RSI computation over NormalizedOHLCV (visualization path)

The historical computation pipeline entry point is in historical_computation.py
(_compute_rsi_series), which operates on ToolComputationBarInput and produces
ToolOutputSeries — the evaluator-compatible output format.

RSI formula (Wilder's smoothing method):
    delta[i]    = close[i] - close[i-1]
    gain[i]     = max(0, delta[i])
    loss[i]     = abs(min(0, delta[i]))

    Seed (bar `period`):
        avg_gain = SMA(gain[1..period])
        avg_loss = SMA(loss[1..period])

    Subsequent bars (Wilder smoothing):
        avg_gain = (avg_gain * (period - 1) + gain[i]) / period
        avg_loss = (avg_loss * (period - 1) + loss[i]) / period

    RS  = avg_gain / avg_loss  (if avg_loss == 0: RS = inf → RSI = 100)
    RSI = 100 - (100 / (1 + RS))

Warmup: first `period` bars produce no output (need `period` price differences
to seed the initial average gain/loss). First RSI value is at bar index `period`.
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

RSI_METADATA = ToolMetadata(
    tool_id="rsi",
    name="Relative Strength Index",
    version="1.0.0",
    category=ToolCategory.indicator,
    status=ToolStatus.stable,
    description=(
        "Computes RSI using Wilder's smoothing method. "
        "Seed = SMA of first `period` gains/losses; subsequent bars use exponential smoothing. "
        "Warmup = period bars (first output at bar index `period`). "
        "Output is bounded [0, 100]. Stateful and deterministic."
    ),
    input_data_family="ohlcv",
    output_feature_names=("rsi",),
    parameters=(
        ParameterSpec(
            name="period",
            description="RSI lookback window. Must be >= 2.",
            type_label="int",
            required=True,
            default=14,
            min_value=2,
        ),
        ParameterSpec(
            name="name",
            description="Custom label for the output indicator series.",
            type_label="str",
            required=False,
            default=None,
        ),
        ParameterSpec(
            name="color",
            description="Hex color string for chart rendering (e.g. '#e040fb').",
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
    min_warmup_bars=2,  # minimum when period=2; actual warmup = period bars
    stateful=True,      # Wilder smoothing: each bar depends on previous avg_gain/avg_loss
)


def compute_rsi(
    candles: list[NormalizedOHLCV],
    period: int,
    name: str | None = None,
    color: str | None = None,
) -> IndicatorSeries:
    """
    Compute RSI over the close prices of the given candles (visualization path).

    Candles are sorted by timestamp internally; the caller need not pre-sort.
    The first `period` bars produce no output (warmup). First RSI value appears
    at the (period+1)-th bar (index `period` in 0-based sorted order).

    Args:
        candles: OHLCV records to compute over.
        period:  RSI lookback window. Must be >= 2.
        name:    Label for the output series. Defaults to "RSI(<period>)".
        color:   Optional hex color hint for visualization.

    Returns:
        IndicatorSeries with RSI values in [0, 100] per bar from warmup onwards.

    Raises:
        ValueError: if period < 2.
    """
    if period < 2:
        raise ValueError(f"period must be >= 2, got {period}")

    series_name = name if name else f"RSI({period})"

    if not candles:
        return IndicatorSeries(
            name=series_name,
            kind=IndicatorSeriesKind.line,
            pane=IndicatorPane.oscillator,
            color=color,
            points=[],
        )

    sorted_candles = sorted(candles, key=lambda c: c.timestamp)
    closes = [c.close for c in sorted_candles]
    timestamps = [c.timestamp for c in sorted_candles]

    points: list[IndicatorPoint] = []
    avg_gain: float | None = None
    avg_loss: float | None = None

    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gain  = max(0.0, delta)
        loss  = abs(min(0.0, delta))

        if i < period:
            # Accumulate for seed: will be summed at i == period
            continue

        if i == period:
            # Seed: SMA of gains and losses over bars 1..period
            gains = [max(0.0, closes[j] - closes[j - 1]) for j in range(1, period + 1)]
            losses = [abs(min(0.0, closes[j] - closes[j - 1])) for j in range(1, period + 1)]
            avg_gain = sum(gains) / period
            avg_loss = sum(losses) / period
        else:
            # Wilder smoothing
            assert avg_gain is not None and avg_loss is not None
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period

        if avg_gain is not None:
            if avg_loss == 0.0:
                rsi = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi = 100.0 - (100.0 / (1.0 + rs))
            points.append(IndicatorPoint(timestamp=timestamps[i], value=rsi))

    return IndicatorSeries(
        name=series_name,
        kind=IndicatorSeriesKind.line,
        pane=IndicatorPane.oscillator,
        color=color,
        points=points,
    )
