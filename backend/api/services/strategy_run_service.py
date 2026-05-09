"""
Strategy run orchestration service.

Thin layer that wires together: OHLCVService → load_strategy_runtime →
StrategyRuntimeRunner → StrategyRunResponse.

Supported providers in this phase: yahoo
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

from backend.api.schemas.strategy_runs import (
    ForecastResponse,
    IndicatorPointResponse,
    IndicatorSeriesResponse,
    SignalResponse,
    StrategyRunRequest,
    StrategyRunResponse,
)
from backend.data.models.dataset import DatasetIdentity
from backend.data.models.instrument import AdjustmentMode, Instrument
from backend.data_providers.yahoo.adapter import YahooAdapterError, YahooFinanceAdapter
from backend.services.ohlcv_service import OHLCVIngestionError, OHLCVService
from backend.strategy_runtime.execution_context import StrategyExecutionContext
from backend.strategy_runtime.loader import StrategyLoadError, load_strategy_runtime
from backend.strategy_runtime.runner import StrategyRuntimeRunner

logger = logging.getLogger(__name__)

_SUPPORTED_PROVIDERS = frozenset({"yahoo"})


class StrategyRunError(Exception):
    """Raised for recoverable strategy-run failures (→ HTTP 400)."""


class StrategyNotFoundError(StrategyRunError):
    """Raised when the strategy directory does not exist."""


class UnsupportedProviderError(StrategyRunError):
    """Raised when the requested provider is not supported."""


def run_strategy(
    request: StrategyRunRequest,
    *,
    storage_path: Path,
    strategies_path: Path,
) -> StrategyRunResponse:
    """
    Execute a strategy over a fetched OHLCV window and return structured results.

    Args:
        request:         Validated run request with provider/symbol/timeframe/dates.
        storage_path:    Base path for Parquet storage (injectable for tests).
        strategies_path: Base path containing strategy directories (injectable for tests).

    Returns:
        StrategyRunResponse with signals, forecasts, and run metadata.

    Raises:
        StrategyNotFoundError:  strategy directory not found at strategies_path/strategy_id.
        UnsupportedProviderError: provider not in supported set.
        StrategyRunError:       load failure, invalid timeframe, or provider fetch failure.
    """
    if request.provider not in _SUPPORTED_PROVIDERS:
        raise UnsupportedProviderError(
            f"Provider '{request.provider}' is not supported. "
            f"Supported providers: {sorted(_SUPPORTED_PROVIDERS)}"
        )

    strategy_dir = strategies_path / request.strategy_id
    if not strategy_dir.exists():
        raise StrategyNotFoundError(
            f"Strategy '{request.strategy_id}' not found at {strategy_dir}"
        )

    try:
        runtime_ref = load_strategy_runtime(strategy_dir, request.strategy_id)
    except StrategyLoadError as exc:
        raise StrategyRunError(f"Strategy load failed: {exc}") from exc

    try:
        adapter = YahooFinanceAdapter(
            symbol=request.symbol,
            asset_class=request.asset_class,
            venue=request.exchange,
            timeframe=request.timeframe,
            adjustment_mode="adjusted",
        )
    except ValueError as exc:
        raise StrategyRunError(str(exc)) from exc

    instrument = Instrument(
        symbol=request.symbol,
        asset_class=request.asset_class,
        exchange=request.exchange,
        currency="USD",
    )
    identity = DatasetIdentity(
        instrument=instrument,
        provider=request.provider,
        timeframe=request.timeframe,
        adjustment_mode=AdjustmentMode.ADJUSTED,
    )

    start = _ensure_utc(request.start)
    end = _ensure_utc(request.end)

    service = OHLCVService(storage_path)
    try:
        candles = service.get_ohlcv(identity, start, end, adapter)
    except YahooAdapterError as exc:
        raise StrategyRunError(f"Provider fetch failed: {exc}") from exc
    except OHLCVIngestionError as exc:
        raise StrategyRunError(f"Data ingestion failed: {exc}") from exc

    parameters: dict = {
        "strategy_id": request.strategy_id,
        "symbol": request.symbol,
        "timeframe": request.timeframe,
        **request.parameters,
    }
    context = StrategyExecutionContext(
        strategy_id=request.strategy_id,
        runtime_mode="research",
        timeframe=request.timeframe,
        start=start,
        end=end,
        parameters=parameters,
        created_at=datetime.now(timezone.utc),
    )

    runner = StrategyRuntimeRunner()
    result = runner.run(runtime_ref, context, candles)

    signals = [
        SignalResponse(
            strategy_id=s.strategy_id,
            timestamp=s.timestamp,
            symbol=s.symbol,
            timeframe=s.timeframe,
            signal_type=s.signal_type.value,
            entry_reference=s.entry_reference,
            invalidation_level=s.invalidation_level,
            confidence=s.confidence,
            reasoning=s.reasoning,
        )
        for s in result.signals
    ]
    forecasts = [
        ForecastResponse(
            generated_at=f.generated_at,
            target_timestamp=f.target_timestamp,
            target_price=f.target_price,
            direction=f.direction.value,
            confidence=f.confidence,
            invalidation_price=f.invalidation_price,
            reason=f.reason,
        )
        for f in result.forecasts
    ]
    indicators = [
        IndicatorSeriesResponse(
            name=a.name,
            kind=a.kind.value,
            pane=a.pane.value,
            color=a.color,
            points=[
                IndicatorPointResponse(timestamp=p.timestamp, value=p.value)
                for p in a.points
            ],
        )
        for a in result.artifacts
    ]

    logger.info(
        "strategy_run_service: %s/%s/%s [%s..%s] — status=%s signals=%d forecasts=%d indicators=%d",
        request.strategy_id,
        request.symbol,
        request.timeframe,
        start.date(),
        end.date(),
        result.status.value,
        len(signals),
        len(forecasts),
        len(indicators),
    )

    return StrategyRunResponse(
        strategy_id=result.strategy_id,
        status=result.status.value,
        candles_received=result.candles_received,
        signals=signals,
        forecasts=forecasts,
        indicators=indicators,
        warnings=result.warnings,
        error=result.error,
    )


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
