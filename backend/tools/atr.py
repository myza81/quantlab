"""
Average True Range (ATR) tool — Phase 2U.

Provides:
    ATR_METADATA — registry metadata for the ATR tool
    compute_atr  — standalone ATR computation over NormalizedOHLCV (visualization path)

The historical computation pipeline entry point is in historical_computation.py
(_compute_atr_series), which operates on ToolComputationBarInput and produces
ToolOutputSeries — the evaluator-compatible output format.

ATR formula (Wilder's smoothing):
    True Range (TR) at bar i (i >= 1):
        TR = max(high[i] - low[i],
                 abs(high[i] - close[i-1]),
                 abs(low[i]  - close[i-1]))

    Seed (bar `period`):
        ATR = SMA(TR[1..period])   — average of the first `period` true ranges

    Subsequent bars (Wilder smoothing):
        ATR = (ATR_prev * (period - 1) + TR_current) / period

Warmup: first `period` bars produce no output (need `period` TR values starting
from bar 1 to seed the initial average). First ATR value is at bar index `period`.
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

ATR_METADATA = ToolMetadata(
    tool_id="atr",
    name="Average True Range",
    version="1.0.0",
    category=ToolCategory.indicator,
    status=ToolStatus.stable,
    description=(
        "Computes ATR using Wilder's smoothing method. "
        "True Range = max(H-L, |H-C_prev|, |L-C_prev|). "
        "Seed = SMA of first `period` true ranges; subsequent bars use Wilder smoothing. "
        "Warmup = period bars (first output at bar index `period`). "
        "Output is always non-negative. Stateful and deterministic."
    ),
    input_data_family="ohlcv",
    output_feature_names=("atr",),
    parameters=(
        ParameterSpec(
            name="period",
            description="ATR lookback window. Must be >= 1.",
            type_label="int",
            required=True,
            default=14,
            min_value=1,
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
            description="Hex color string for chart rendering (e.g. '#ff6b00').",
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
    min_warmup_bars=1,  # minimum when period=1; actual warmup = period bars
    stateful=True,      # Wilder smoothing: each bar depends on previous ATR value
)


def compute_atr(
    candles: list[NormalizedOHLCV],
    period: int,
    name: str | None = None,
    color: str | None = None,
) -> IndicatorSeries:
    """
    Compute ATR over OHLCV candles (visualization path).

    Candles are sorted by timestamp internally. The first `period` bars produce
    no output (warmup). First ATR value appears at the (period+1)-th bar.

    Args:
        candles: OHLCV records to compute over.
        period:  ATR lookback window. Must be >= 1.
        name:    Label for the output series. Defaults to "ATR(<period>)".
        color:   Optional hex color hint for visualization.

    Returns:
        IndicatorSeries with ATR values (always non-negative) from warmup onwards.

    Raises:
        ValueError: if period < 1.
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")

    series_name = name if name else f"ATR({period})"

    if not candles:
        return IndicatorSeries(
            name=series_name,
            kind=IndicatorSeriesKind.line,
            pane=IndicatorPane.oscillator,
            color=color,
            points=[],
        )

    sorted_candles = sorted(candles, key=lambda c: c.timestamp)
    highs      = [c.high  for c in sorted_candles]
    lows       = [c.low   for c in sorted_candles]
    closes     = [c.close for c in sorted_candles]
    timestamps = [c.timestamp for c in sorted_candles]

    # True ranges: tr_values[i] = TR for sorted_candles[i+1] (uses closes[i] as prev_close)
    tr_values: list[float] = [
        _true_range(highs[i + 1], lows[i + 1], closes[i])
        for i in range(len(sorted_candles) - 1)
    ]

    points: list[IndicatorPoint] = []
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

        # tr_values[i] corresponds to sorted_candles[i+1]
        points.append(IndicatorPoint(timestamp=timestamps[i + 1], value=atr))  # type: ignore[arg-type]

    return IndicatorSeries(
        name=series_name,
        kind=IndicatorSeriesKind.line,
        pane=IndicatorPane.oscillator,
        color=color,
        points=points,
    )


def _true_range(high: float, low: float, prev_close: float) -> float:
    """True Range for one bar: max of three range measures."""
    return max(high - low, abs(high - prev_close), abs(low - prev_close))
