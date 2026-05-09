"""
StrategyRuntimeRunner — deterministic executor for the strategy callable pipeline.

Executes the four required strategy callables in sequence, collects structured
outputs, and returns a StrategyRunResult. The runner does not know about:
- data storage or provider paths
- broker or execution systems
- frontend rendering

It only receives normalized OHLCV and returns structured outputs.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from backend.data.schemas import NormalizedOHLCV
from backend.strategy_runtime.execution_context import StrategyExecutionContext
from backend.strategy_runtime.forecast import StrategyForecast
from backend.strategy_runtime.loader import StrategyRuntimeReference
from backend.strategy_runtime.models import StrategySignal
from backend.strategy_runtime.run_result import RunStatus, StrategyRunResult
from backend.strategy_runtime.visualization import IndicatorSeries

logger = logging.getLogger(__name__)

_BAR_BY_BAR_NOT_IMPLEMENTED = (
    "Bar-by-bar execution is not yet implemented. "
    "Use run() for full-window mode."
)


class StrategyRuntimeRunner:
    """
    Executes strategy callables in a controlled, deterministic sequence.

    Guarantees:
    - validate_config is called before pipeline entry; False return adds a warning
      but does not abort execution.
    - build_features → generate_signals → apply_risk_rules are called in order.
    - StrategySignal objects are extracted from apply_risk_rules() output under
      the "signals" key; other dict content is ignored.
    - StrategyForecast objects are extracted from apply_risk_rules() output under
      the "forecasts" key; absent or non-list values produce an empty list.
    - Any callable exception returns RunStatus.failed with error set; it does not
      propagate to the caller.
    - Empty candle input short-circuits to RunStatus.empty without calling callables.
    """

    def run(
        self,
        runtime_ref: StrategyRuntimeReference,
        context: StrategyExecutionContext,
        candles: list[NormalizedOHLCV],
    ) -> StrategyRunResult:
        """
        Execute the full strategy pipeline over the provided candle window.

        Args:
            runtime_ref: Validated strategy callable references.
            context:     Execution context (mode, parameters, time window).
            candles:     Normalized OHLCV records to pass into the strategy.

        Returns:
            StrategyRunResult — always returned, never raises.
        """
        started_at = datetime.now(timezone.utc)
        warnings: list[str] = []
        features_generated = 0
        failed_stage = "validate_config"

        if not candles:
            completed_at = datetime.now(timezone.utc)
            logger.debug(
                "StrategyRuntimeRunner: empty candle input for %s — skipping pipeline",
                runtime_ref.strategy_id,
            )
            return StrategyRunResult(
                strategy_id=runtime_ref.strategy_id,
                runtime_mode=context.runtime_mode,
                status=RunStatus.empty,
                started_at=started_at,
                completed_at=completed_at,
                candles_received=0,
                features_generated=0,
                signals=[],
                forecasts=[],
                diagnostics={"candles_received": 0},
                warnings=warnings,
                error=None,
            )

        try:
            config_valid = runtime_ref.validate_config(context.parameters)
            if not config_valid:
                warnings.append(
                    "validate_config returned False — check strategy parameters"
                )

            failed_stage = "build_features"
            features: dict[str, Any] = runtime_ref.build_features(
                candles, context.parameters
            )
            features_generated = len(features) if isinstance(features, dict) else 0

            failed_stage = "generate_signals"
            signals_out: dict[str, Any] = runtime_ref.generate_signals(
                features, context.parameters
            )

            failed_stage = "apply_risk_rules"
            final_out: dict[str, Any] = runtime_ref.apply_risk_rules(
                signals_out, context.parameters
            )

        except Exception as exc:
            completed_at = datetime.now(timezone.utc)
            logger.exception(
                "StrategyRuntimeRunner: strategy %s raised during execution: %s",
                runtime_ref.strategy_id,
                exc,
            )
            return StrategyRunResult(
                strategy_id=runtime_ref.strategy_id,
                runtime_mode=context.runtime_mode,
                status=RunStatus.failed,
                started_at=started_at,
                completed_at=completed_at,
                candles_received=len(candles),
                features_generated=features_generated,
                signals=[],
                forecasts=[],
                diagnostics={
                    "candles_received": len(candles),
                    "features_generated": features_generated,
                    "failed_stage": failed_stage,
                },
                warnings=warnings,
                error=str(exc),
            )

        signals, signal_warnings = _extract_signals(final_out)
        forecasts, forecast_warnings = _extract_forecasts(final_out)
        artifacts, artifact_warnings = _extract_artifacts(final_out)
        warnings.extend(signal_warnings)
        warnings.extend(forecast_warnings)
        warnings.extend(artifact_warnings)

        completed_at = datetime.now(timezone.utc)

        diagnostics: dict[str, Any] = {
            "candles_received": len(candles),
            "features_generated": features_generated,
            "signals_generated": len(signals),
            "forecasts_generated": len(forecasts),
            "artifacts_generated": len(artifacts),
            "runtime_seconds": (completed_at - started_at).total_seconds(),
        }

        logger.debug(
            "StrategyRuntimeRunner: %s complete — %d candles, %d signals, %d forecasts",
            runtime_ref.strategy_id,
            len(candles),
            len(signals),
            len(forecasts),
        )

        return StrategyRunResult(
            strategy_id=runtime_ref.strategy_id,
            runtime_mode=context.runtime_mode,
            status=RunStatus.success,
            started_at=started_at,
            completed_at=completed_at,
            candles_received=len(candles),
            features_generated=features_generated,
            signals=signals,
            forecasts=forecasts,
            artifacts=artifacts,
            diagnostics=diagnostics,
            warnings=warnings,
            error=None,
        )

    def run_bar_by_bar(
        self,
        runtime_ref: StrategyRuntimeReference,
        context: StrategyExecutionContext,
        candles: list[NormalizedOHLCV],
    ) -> StrategyRunResult:
        """Bar-by-bar execution skeleton. Reserved for future backtesting integration."""
        raise NotImplementedError(_BAR_BY_BAR_NOT_IMPLEMENTED)


# ---------------------------------------------------------------------------
# Internal extraction helpers
# ---------------------------------------------------------------------------


def _extract_signals(output: Any) -> tuple[list[StrategySignal], list[str]]:
    if not isinstance(output, dict):
        return [], []
    warnings: list[str] = []
    raw = output.get("signals", [])
    if not isinstance(raw, list):
        warnings.append(
            "apply_risk_rules returned non-list 'signals'; ignoring malformed payload"
        )
        return [], warnings

    signals = [s for s in raw if isinstance(s, StrategySignal)]
    ignored_count = len(raw) - len(signals)
    if ignored_count:
        warnings.append(
            f"ignored {ignored_count} non-StrategySignal item(s) from 'signals' payload"
        )
    return signals, warnings


def _extract_artifacts(output: Any) -> tuple[list[IndicatorSeries], list[str]]:
    if not isinstance(output, dict):
        return [], []
    warnings: list[str] = []
    raw = output.get("artifacts", [])
    if not isinstance(raw, list):
        warnings.append(
            "apply_risk_rules returned non-list 'artifacts'; ignoring malformed payload"
        )
        return [], warnings

    artifacts = [a for a in raw if isinstance(a, IndicatorSeries)]
    ignored_count = len(raw) - len(artifacts)
    if ignored_count:
        warnings.append(
            f"ignored {ignored_count} non-IndicatorSeries item(s) from 'artifacts' payload"
        )
    return artifacts, warnings


def _extract_forecasts(output: Any) -> tuple[list[StrategyForecast], list[str]]:
    if not isinstance(output, dict):
        return [], []
    warnings: list[str] = []
    raw = output.get("forecasts", [])
    if not isinstance(raw, list):
        warnings.append(
            "apply_risk_rules returned non-list 'forecasts'; ignoring malformed payload"
        )
        return [], warnings

    forecasts = [f for f in raw if isinstance(f, StrategyForecast)]
    ignored_count = len(raw) - len(forecasts)
    if ignored_count:
        warnings.append(
            f"ignored {ignored_count} non-StrategyForecast item(s) from 'forecasts' payload"
        )
    return forecasts, warnings
