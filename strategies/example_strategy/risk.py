from datetime import datetime, timedelta, timezone
from typing import Any

from backend.strategy_runtime.forecast import ForecastDirection, StrategyForecast
from backend.strategy_runtime.models import SignalType, StrategySignal
from backend.strategy_runtime.visualization import IndicatorPoint, IndicatorSeries


def apply_risk_rules(signals: dict[str, Any], parameters: Any) -> dict[str, Any]:
    strategy_id = parameters.get("strategy_id", "example_strategy") if isinstance(parameters, dict) else "example_strategy"
    symbol = parameters.get("symbol", "UNKNOWN") if isinstance(parameters, dict) else "UNKNOWN"
    timeframe = parameters.get("timeframe", "1d") if isinstance(parameters, dict) else "1d"

    raw_signals = signals.get("raw_signals", [])
    last_close = signals.get("last_close")
    last_timestamp = signals.get("last_timestamp")
    last_ma20 = signals.get("last_ma20")
    last_ma50 = signals.get("last_ma50")
    timestamps = signals.get("timestamps", [])
    ma20_series = signals.get("ma20_series", [])
    ma50_series = signals.get("ma50_series", [])

    strategy_signals: list[StrategySignal] = []
    for rs in raw_signals:
        signal_type = SignalType.long if rs["type"] == "long" else SignalType.short
        close: float = rs["close"]
        invalidation = round(close * 0.98, 4) if signal_type == SignalType.long else round(close * 1.02, 4)
        cross_label = "golden" if signal_type == SignalType.long else "death"
        strategy_signals.append(
            StrategySignal(
                strategy_id=strategy_id,
                timestamp=rs["timestamp"],
                symbol=symbol,
                timeframe=timeframe,
                signal_type=signal_type,
                entry_reference=close,
                invalidation_level=invalidation,
                confidence=0.65,
                reasoning=f"MA20/MA50 {cross_label} cross",
            )
        )

    forecasts: list[StrategyForecast] = []
    if last_close is not None and last_timestamp is not None and last_ma20 is not None and last_ma50 is not None:
        if last_ma20 > last_ma50:
            direction = ForecastDirection.long
            target_price = round(last_close * 1.04, 4)
            invalidation_price = round(last_close * 0.97, 4)
        else:
            direction = ForecastDirection.short
            target_price = round(last_close * 0.96, 4)
            invalidation_price = round(last_close * 1.03, 4)

        forecasts.append(
            StrategyForecast(
                generated_at=datetime.now(timezone.utc),
                target_timestamp=last_timestamp + timedelta(days=20),
                target_price=target_price,
                direction=direction,
                confidence=0.6,
                invalidation_price=invalidation_price,
                reason="Latest MA20/MA50 relative position projects continuation",
            )
        )

    artifacts: list[IndicatorSeries] = []
    if timestamps:
        ma20_points = [
            IndicatorPoint(timestamp=ts, value=v)
            for ts, v in zip(timestamps, ma20_series)
            if v is not None
        ]
        if ma20_points:
            artifacts.append(IndicatorSeries(
                name="MA20",
                pane="price",
                color="#2196f3",
                points=ma20_points,
            ))

        ma50_points = [
            IndicatorPoint(timestamp=ts, value=v)
            for ts, v in zip(timestamps, ma50_series)
            if v is not None
        ]
        if ma50_points:
            artifacts.append(IndicatorSeries(
                name="MA50",
                pane="price",
                color="#ff9800",
                points=ma50_points,
            ))

    return {"signals": strategy_signals, "forecasts": forecasts, "artifacts": artifacts}
