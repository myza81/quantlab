"""
Tests for Phase 2I — Strategy Runtime Orchestration Foundation.

Covers:
  StrategyExecutionContext  — creation, validation, UTC enforcement
  StrategyForecast          — creation, validation, optional fields
  StrategyRunResult         — structure, RunStatus enum, UTC enforcement
  StrategyRuntimeRunner     — full pipeline, empty candles, failure handling,
                              signal/forecast extraction, diagnostics, warnings,
                              bar-by-bar skeleton

Runner tests use a stub StrategyRuntimeReference built from lambdas — no file
system access required. The example_strategy integration test exercises the real
loader + runner path end-to-end.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from backend.strategy_runtime.execution_context import StrategyExecutionContext
from backend.strategy_runtime.forecast import ForecastDirection, StrategyForecast
from backend.strategy_runtime.loader import StrategyRuntimeReference, load_strategy_runtime
from backend.strategy_runtime.models import SignalType, StrategySignal
from backend.strategy_runtime.run_result import RunStatus, StrategyRunResult
from backend.strategy_runtime.runner import StrategyRuntimeRunner

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_UTC = timezone.utc
EXAMPLE_STRATEGY_DIR = Path(__file__).parents[2] / "strategies" / "example_strategy"


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=_UTC)


def _context(**overrides: Any) -> StrategyExecutionContext:
    defaults: dict[str, Any] = dict(
        strategy_id="test_strategy",
        runtime_mode="research",
        timeframe="1h",
        start=_utc(2024, 1, 1),
        end=_utc(2024, 1, 31),
        parameters={},
        created_at=_utc(2024, 1, 1),
    )
    defaults.update(overrides)
    return StrategyExecutionContext(**defaults)


def _candle(hour: int = 0) -> Any:
    from tests.conftest import make_ohlcv
    return make_ohlcv(timestamp=_utc(2024, 1, 1, hour))


def _make_ref(
    strategy_id: str = "test_strategy",
    build_features: Any = None,
    generate_signals: Any = None,
    apply_risk_rules: Any = None,
    validate_config: Any = None,
) -> StrategyRuntimeReference:
    return StrategyRuntimeReference(
        strategy_id=strategy_id,
        strategy_dir=Path("."),
        build_features=build_features or (lambda data, params: {}),
        generate_signals=generate_signals or (lambda features, params: {}),
        apply_risk_rules=apply_risk_rules or (lambda signals, params: signals),
        validate_config=validate_config or (lambda params: True),
    )


def _signal() -> StrategySignal:
    return StrategySignal(
        strategy_id="test_strategy",
        timestamp=_utc(2024, 1, 2),
        symbol="BTCUSDT",
        timeframe="1h",
        signal_type=SignalType.long,
        entry_reference=42000.0,
        invalidation_level=41000.0,
    )


def _forecast() -> StrategyForecast:
    return StrategyForecast(
        generated_at=_utc(2024, 1, 2),
        target_timestamp=_utc(2024, 1, 10),
        target_price=45000.0,
        direction=ForecastDirection.long,
        confidence=0.75,
    )


# ===========================================================================
# StrategyExecutionContext
# ===========================================================================


class TestStrategyExecutionContext:
    def test_basic_creation(self) -> None:
        ctx = _context()
        assert ctx.strategy_id == "test_strategy"
        assert ctx.runtime_mode == "research"
        assert ctx.timeframe == "1h"

    def test_utc_enforcement_start(self) -> None:
        with pytest.raises(ValueError, match="UTC"):
            _context(start=datetime(2024, 1, 1))

    def test_utc_enforcement_end(self) -> None:
        with pytest.raises(ValueError, match="UTC"):
            _context(end=datetime(2024, 1, 31))

    def test_utc_enforcement_created_at(self) -> None:
        with pytest.raises(ValueError, match="UTC"):
            _context(created_at=datetime(2024, 1, 1))

    def test_aware_non_utc_normalized_to_utc(self) -> None:
        from datetime import timedelta, timezone as tz
        plus8 = tz(timedelta(hours=8))
        ctx = _context(created_at=datetime(2024, 1, 1, 8, 0, tzinfo=plus8))
        assert ctx.created_at.tzinfo == _UTC
        assert ctx.created_at.hour == 0

    def test_empty_strategy_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            _context(strategy_id="  ")

    def test_empty_timeframe_rejected(self) -> None:
        with pytest.raises(ValueError):
            _context(timeframe="")

    def test_parameters_passthrough(self) -> None:
        ctx = _context(parameters={"fast": 10, "slow": 50})
        assert ctx.parameters["fast"] == 10

    def test_optional_fields_default_none(self) -> None:
        ctx = _context()
        assert ctx.instrument_id is None
        assert ctx.initial_capital is None
        assert ctx.research_tags is None

    def test_optional_fields_accepted(self) -> None:
        ctx = _context(
            instrument_id="equity__NYSE__AAPL",
            initial_capital=100_000.0,
            research_tags=["momentum", "cycle"],
        )
        assert ctx.instrument_id == "equity__NYSE__AAPL"
        assert ctx.initial_capital == 100_000.0
        assert ctx.research_tags == ["momentum", "cycle"]

    def test_frozen(self) -> None:
        ctx = _context()
        with pytest.raises(Exception):
            ctx.strategy_id = "other"  # type: ignore[misc]

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(Exception):
            StrategyExecutionContext(
                strategy_id="x",
                runtime_mode="research",
                timeframe="1h",
                start=_utc(2024, 1, 1),
                end=_utc(2024, 1, 31),
                parameters={},
                created_at=_utc(2024, 1, 1),
                unknown_field="oops",
            )


# ===========================================================================
# StrategyForecast
# ===========================================================================


class TestStrategyForecast:
    def test_basic_creation(self) -> None:
        f = _forecast()
        assert f.target_price == 45000.0
        assert f.direction == ForecastDirection.long
        assert f.confidence == 0.75

    def test_utc_enforcement_generated_at(self) -> None:
        with pytest.raises(ValueError, match="UTC"):
            StrategyForecast(
                generated_at=datetime(2024, 1, 2),
                target_timestamp=_utc(2024, 1, 10),
                target_price=45000.0,
                direction=ForecastDirection.long,
                confidence=0.75,
            )

    def test_utc_enforcement_target_timestamp(self) -> None:
        with pytest.raises(ValueError, match="UTC"):
            StrategyForecast(
                generated_at=_utc(2024, 1, 2),
                target_timestamp=datetime(2024, 1, 10),
                target_price=45000.0,
                direction=ForecastDirection.long,
                confidence=0.75,
            )

    def test_confidence_below_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            StrategyForecast(
                generated_at=_utc(2024, 1, 2),
                target_timestamp=_utc(2024, 1, 10),
                target_price=45000.0,
                direction=ForecastDirection.long,
                confidence=-0.1,
            )

    def test_confidence_above_one_rejected(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            StrategyForecast(
                generated_at=_utc(2024, 1, 2),
                target_timestamp=_utc(2024, 1, 10),
                target_price=45000.0,
                direction=ForecastDirection.long,
                confidence=1.01,
            )

    def test_confidence_boundary_values_accepted(self) -> None:
        for v in (0.0, 1.0):
            f = StrategyForecast(
                generated_at=_utc(2024, 1, 2),
                target_timestamp=_utc(2024, 1, 10),
                target_price=1.0,
                direction=ForecastDirection.neutral,
                confidence=v,
            )
            assert f.confidence == v

    def test_target_price_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="target_price"):
            StrategyForecast(
                generated_at=_utc(2024, 1, 2),
                target_timestamp=_utc(2024, 1, 10),
                target_price=0.0,
                direction=ForecastDirection.long,
                confidence=0.5,
            )

    def test_optional_fields_default_none(self) -> None:
        f = _forecast()
        assert f.invalidation_price is None
        assert f.reason is None
        assert f.tags is None
        assert f.metadata is None

    def test_optional_fields_accepted(self) -> None:
        f = StrategyForecast(
            generated_at=_utc(2024, 1, 2),
            target_timestamp=_utc(2024, 1, 10),
            target_price=45000.0,
            direction=ForecastDirection.long,
            confidence=0.8,
            invalidation_price=40000.0,
            reason="breakout above resistance",
            tags=["momentum"],
            metadata={"cycle_phase": "expansion"},
        )
        assert f.invalidation_price == 40000.0
        assert f.reason == "breakout above resistance"

    def test_direction_enum_values(self) -> None:
        assert ForecastDirection.long == "long"
        assert ForecastDirection.short == "short"
        assert ForecastDirection.neutral == "neutral"

    def test_frozen(self) -> None:
        f = _forecast()
        with pytest.raises(Exception):
            f.target_price = 99999.0  # type: ignore[misc]


# ===========================================================================
# StrategyRunResult
# ===========================================================================


class TestStrategyRunResult:
    def _make_result(self, **overrides: Any) -> StrategyRunResult:
        defaults: dict[str, Any] = dict(
            strategy_id="test",
            runtime_mode="research",
            status=RunStatus.success,
            started_at=_utc(2024, 1, 1, 0),
            completed_at=_utc(2024, 1, 1, 0, 0, 1),
            candles_received=10,
            features_generated=3,
            signals=[],
            forecasts=[],
            diagnostics={"candles_received": 10},
            warnings=[],
            error=None,
        )
        defaults.update(overrides)
        return StrategyRunResult(**defaults)

    def test_basic_creation(self) -> None:
        r = self._make_result()
        assert r.status == RunStatus.success
        assert r.candles_received == 10
        assert r.error is None

    def test_utc_enforcement_started_at(self) -> None:
        with pytest.raises(ValueError, match="UTC"):
            self._make_result(started_at=datetime(2024, 1, 1))

    def test_utc_enforcement_completed_at(self) -> None:
        with pytest.raises(ValueError, match="UTC"):
            self._make_result(completed_at=datetime(2024, 1, 1))

    def test_run_status_enum_values(self) -> None:
        assert RunStatus.success == "success"
        assert RunStatus.failed == "failed"
        assert RunStatus.empty == "empty"

    def test_failed_result_carries_error(self) -> None:
        r = self._make_result(status=RunStatus.failed, error="build_features exploded")
        assert r.status == RunStatus.failed
        assert r.error == "build_features exploded"

    def test_empty_result_structure(self) -> None:
        r = self._make_result(status=RunStatus.empty, candles_received=0)
        assert r.signals == []
        assert r.forecasts == []
        assert r.candles_received == 0

    def test_signals_list_accepted(self) -> None:
        r = self._make_result(signals=[_signal()])
        assert len(r.signals) == 1
        assert isinstance(r.signals[0], StrategySignal)

    def test_forecasts_list_accepted(self) -> None:
        r = self._make_result(forecasts=[_forecast()])
        assert len(r.forecasts) == 1
        assert isinstance(r.forecasts[0], StrategyForecast)

    def test_warnings_list(self) -> None:
        r = self._make_result(warnings=["validate_config returned False"])
        assert "validate_config returned False" in r.warnings

    def test_frozen(self) -> None:
        r = self._make_result()
        with pytest.raises(Exception):
            r.status = RunStatus.failed  # type: ignore[misc]


# ===========================================================================
# StrategyRuntimeRunner — core scenarios
# ===========================================================================


class TestRunnerSuccessPath:
    def test_call_order_is_deterministic(self) -> None:
        calls: list[str] = []

        def validate_config(params: Any) -> bool:
            calls.append("validate_config")
            return True

        def build_features(data: Any, params: Any) -> dict[str, Any]:
            calls.append("build_features")
            return {}

        def generate_signals(features: Any, params: Any) -> dict[str, Any]:
            calls.append("generate_signals")
            return {}

        def apply_risk_rules(signals: Any, params: Any) -> dict[str, Any]:
            calls.append("apply_risk_rules")
            return {}

        runner = StrategyRuntimeRunner()
        ref = _make_ref(
            validate_config=validate_config,
            build_features=build_features,
            generate_signals=generate_signals,
            apply_risk_rules=apply_risk_rules,
        )

        result = runner.run(ref, _context(), [_candle()])

        assert result.status == RunStatus.success
        assert calls == [
            "validate_config",
            "build_features",
            "generate_signals",
            "apply_risk_rules",
        ]

    def test_basic_success(self) -> None:
        runner = StrategyRuntimeRunner()
        ref = _make_ref()
        ctx = _context()
        candles = [_candle(i) for i in range(5)]
        result = runner.run(ref, ctx, candles)
        assert result.status == RunStatus.success
        assert result.candles_received == 5
        assert result.error is None

    def test_strategy_id_propagated(self) -> None:
        runner = StrategyRuntimeRunner()
        ref = _make_ref(strategy_id="my_sma_cross")
        result = runner.run(ref, _context(strategy_id="my_sma_cross"), [_candle()])
        assert result.strategy_id == "my_sma_cross"

    def test_runtime_mode_propagated(self) -> None:
        runner = StrategyRuntimeRunner()
        result = runner.run(_make_ref(), _context(runtime_mode="backtesting"), [_candle()])
        assert result.runtime_mode == "backtesting"

    def test_candles_received_count(self) -> None:
        runner = StrategyRuntimeRunner()
        candles = [_candle(i) for i in range(8)]
        result = runner.run(_make_ref(), _context(), candles)
        assert result.candles_received == 8

    def test_features_generated_counts_dict_keys(self) -> None:
        runner = StrategyRuntimeRunner()
        ref = _make_ref(
            build_features=lambda data, params: {"sma_fast": 100.0, "sma_slow": 200.0}
        )
        result = runner.run(ref, _context(), [_candle()])
        assert result.features_generated == 2

    def test_started_and_completed_at_utc(self) -> None:
        runner = StrategyRuntimeRunner()
        result = runner.run(_make_ref(), _context(), [_candle()])
        assert result.started_at.tzinfo is not None
        assert result.completed_at.tzinfo is not None
        assert result.completed_at >= result.started_at

    def test_diagnostics_keys_present(self) -> None:
        runner = StrategyRuntimeRunner()
        result = runner.run(_make_ref(), _context(), [_candle()])
        d = result.diagnostics
        assert "candles_received" in d
        assert "features_generated" in d
        assert "signals_generated" in d
        assert "forecasts_generated" in d
        assert "runtime_seconds" in d

    def test_diagnostics_candles_received_matches(self) -> None:
        runner = StrategyRuntimeRunner()
        candles = [_candle(i) for i in range(3)]
        result = runner.run(_make_ref(), _context(), candles)
        assert result.diagnostics["candles_received"] == 3

    def test_warnings_empty_on_happy_path(self) -> None:
        runner = StrategyRuntimeRunner()
        result = runner.run(_make_ref(), _context(), [_candle()])
        assert result.warnings == []


class TestRunnerEmptyCandles:
    def test_empty_candles_returns_empty_status(self) -> None:
        runner = StrategyRuntimeRunner()
        result = runner.run(_make_ref(), _context(), [])
        assert result.status == RunStatus.empty

    def test_empty_candles_no_signals(self) -> None:
        runner = StrategyRuntimeRunner()
        result = runner.run(_make_ref(), _context(), [])
        assert result.signals == []
        assert result.forecasts == []

    def test_empty_candles_skips_callables(self) -> None:
        calls: list[str] = []

        def track_build(data: Any, params: Any) -> dict:
            calls.append("build_features")
            return {}

        ref = _make_ref(build_features=track_build)
        runner = StrategyRuntimeRunner()
        runner.run(ref, _context(), [])
        assert calls == []

    def test_empty_candles_candles_received_is_zero(self) -> None:
        runner = StrategyRuntimeRunner()
        result = runner.run(_make_ref(), _context(), [])
        assert result.candles_received == 0


class TestRunnerFailurePath:
    def test_validate_config_raises_returns_failed(self) -> None:
        ref = _make_ref(
            validate_config=lambda params: (_ for _ in ()).throw(RuntimeError("config crash"))
        )
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert result.status == RunStatus.failed
        assert result.error is not None
        assert result.diagnostics["failed_stage"] == "validate_config"

    def test_build_features_raises_returns_failed(self) -> None:
        ref = _make_ref(
            build_features=lambda data, params: (_ for _ in ()).throw(RuntimeError("feature crash"))
        )
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert result.status == RunStatus.failed
        assert "feature crash" in result.error  # type: ignore[operator]

    def test_generate_signals_raises_returns_failed(self) -> None:
        ref = _make_ref(
            generate_signals=lambda features, params: 1 / 0
        )
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert result.status == RunStatus.failed
        assert result.error is not None

    def test_apply_risk_rules_raises_returns_failed(self) -> None:
        ref = _make_ref(
            apply_risk_rules=lambda signals, params: (_ for _ in ()).throw(ValueError("bad risk"))
        )
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert result.status == RunStatus.failed
        assert "bad risk" in result.error  # type: ignore[operator]

    def test_failed_result_error_is_string(self) -> None:
        ref = _make_ref(build_features=lambda d, p: (_ for _ in ()).throw(TypeError("oops")))
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert isinstance(result.error, str)

    def test_failed_result_candles_received_set(self) -> None:
        ref = _make_ref(build_features=lambda d, p: (_ for _ in ()).throw(RuntimeError("x")))
        runner = StrategyRuntimeRunner()
        candles = [_candle(i) for i in range(4)]
        result = runner.run(ref, _context(), candles)
        assert result.candles_received == 4

    def test_failed_result_tracks_failed_stage(self) -> None:
        ref = _make_ref(generate_signals=lambda features, params: (_ for _ in ()).throw(RuntimeError("x")))
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert result.diagnostics["failed_stage"] == "generate_signals"

    def test_failed_result_preserves_feature_count_if_later_stage_fails(self) -> None:
        ref = _make_ref(
            build_features=lambda data, params: {"sma_fast": 1.0, "sma_slow": 2.0},
            generate_signals=lambda features, params: (_ for _ in ()).throw(RuntimeError("later crash")),
        )
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert result.status == RunStatus.failed
        assert result.features_generated == 2
        assert result.diagnostics["features_generated"] == 2

    def test_failed_result_signals_empty(self) -> None:
        ref = _make_ref(build_features=lambda d, p: (_ for _ in ()).throw(RuntimeError("x")))
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert result.signals == []
        assert result.forecasts == []

    def test_runner_never_raises_to_caller(self) -> None:
        ref = _make_ref(build_features=lambda d, p: (_ for _ in ()).throw(RuntimeError("boom")))
        runner = StrategyRuntimeRunner()
        # Must not propagate the exception
        result = runner.run(ref, _context(), [_candle()])
        assert result.status == RunStatus.failed


class TestSignalExtraction:
    def test_signals_extracted_from_output(self) -> None:
        sig = _signal()
        ref = _make_ref(
            apply_risk_rules=lambda s, p: {"signals": [sig]}
        )
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert result.status == RunStatus.success
        assert len(result.signals) == 1
        assert result.signals[0] is sig

    def test_non_signal_objects_in_signals_key_ignored(self) -> None:
        ref = _make_ref(
            apply_risk_rules=lambda s, p: {"signals": ["not_a_signal", 42, None]}
        )
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert result.signals == []
        assert any("signals" in warning for warning in result.warnings)

    def test_non_list_signals_payload_warns_and_returns_empty(self) -> None:
        ref = _make_ref(
            apply_risk_rules=lambda s, p: {"signals": {"bad": True}}
        )
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert result.signals == []
        assert any("non-list 'signals'" in warning for warning in result.warnings)

    def test_missing_signals_key_produces_empty_list(self) -> None:
        ref = _make_ref(apply_risk_rules=lambda s, p: {"something_else": "data"})
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert result.signals == []

    def test_signals_count_in_diagnostics(self) -> None:
        ref = _make_ref(
            apply_risk_rules=lambda s, p: {"signals": [_signal(), _signal()]}
        )
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert result.diagnostics["signals_generated"] == 2


class TestForecastExtraction:
    def test_forecasts_extracted_from_output(self) -> None:
        fc = _forecast()
        ref = _make_ref(
            apply_risk_rules=lambda s, p: {"forecasts": [fc]}
        )
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert len(result.forecasts) == 1
        assert result.forecasts[0] is fc

    def test_forecasts_default_empty_when_absent(self) -> None:
        runner = StrategyRuntimeRunner()
        result = runner.run(_make_ref(), _context(), [_candle()])
        assert result.forecasts == []

    def test_non_forecast_objects_in_forecasts_key_ignored(self) -> None:
        ref = _make_ref(
            apply_risk_rules=lambda s, p: {"forecasts": ["str", {"dict": True}]}
        )
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert result.forecasts == []
        assert any("forecasts" in warning for warning in result.warnings)

    def test_non_list_forecasts_payload_warns_and_returns_empty(self) -> None:
        ref = _make_ref(
            apply_risk_rules=lambda s, p: {"forecasts": {"bad": True}}
        )
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert result.forecasts == []
        assert any("non-list 'forecasts'" in warning for warning in result.warnings)

    def test_forecasts_count_in_diagnostics(self) -> None:
        ref = _make_ref(
            apply_risk_rules=lambda s, p: {"forecasts": [_forecast(), _forecast()]}
        )
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert result.diagnostics["forecasts_generated"] == 2

    def test_forecasts_optional_not_forced_on_strategy(self) -> None:
        # Strategy returning plain dict (current example_strategy contract) → no forecasts
        ref = _make_ref(
            generate_signals=lambda f, p: {"signal": None, "direction": None},
            apply_risk_rules=lambda s, p: s,
        )
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert result.forecasts == []


class TestValidateConfigWarning:
    def test_validate_config_false_adds_warning(self) -> None:
        ref = _make_ref(validate_config=lambda params: False)
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert result.status == RunStatus.success
        assert any("validate_config" in w for w in result.warnings)

    def test_validate_config_false_does_not_abort_run(self) -> None:
        ref = _make_ref(validate_config=lambda params: False)
        runner = StrategyRuntimeRunner()
        candles = [_candle(i) for i in range(3)]
        result = runner.run(ref, _context(), candles)
        assert result.status == RunStatus.success
        assert result.candles_received == 3

    def test_validate_config_true_no_warning(self) -> None:
        ref = _make_ref(validate_config=lambda params: True)
        runner = StrategyRuntimeRunner()
        result = runner.run(ref, _context(), [_candle()])
        assert result.warnings == []


class TestBarByBarSkeleton:
    def test_run_bar_by_bar_raises_not_implemented(self) -> None:
        runner = StrategyRuntimeRunner()
        with pytest.raises(NotImplementedError):
            runner.run_bar_by_bar(_make_ref(), _context(), [_candle()])

    def test_not_implemented_error_message_descriptive(self) -> None:
        runner = StrategyRuntimeRunner()
        with pytest.raises(NotImplementedError, match="[Bb]ar"):
            runner.run_bar_by_bar(_make_ref(), _context(), [_candle()])


class TestRunnerExampleStrategyIntegration:
    """End-to-end: load example_strategy via real loader, run via runner."""

    def test_example_strategy_run_succeeds(self) -> None:
        ref = load_strategy_runtime(EXAMPLE_STRATEGY_DIR, "example_strategy")
        runner = StrategyRuntimeRunner()
        candles = [_candle(i) for i in range(10)]
        ctx = _context(strategy_id="example_strategy")
        result = runner.run(ref, ctx, candles)
        assert result.status == RunStatus.success

    def test_example_strategy_candles_received(self) -> None:
        ref = load_strategy_runtime(EXAMPLE_STRATEGY_DIR, "example_strategy")
        runner = StrategyRuntimeRunner()
        candles = [_candle(i) for i in range(5)]
        ctx = _context(strategy_id="example_strategy")
        result = runner.run(ref, ctx, candles)
        assert result.candles_received == 5

    def test_example_strategy_forecasts_empty_by_default(self) -> None:
        ref = load_strategy_runtime(EXAMPLE_STRATEGY_DIR, "example_strategy")
        runner = StrategyRuntimeRunner()
        ctx = _context(strategy_id="example_strategy")
        result = runner.run(ref, ctx, [_candle()])
        assert result.forecasts == []

    def test_example_strategy_no_error(self) -> None:
        ref = load_strategy_runtime(EXAMPLE_STRATEGY_DIR, "example_strategy")
        runner = StrategyRuntimeRunner()
        ctx = _context(strategy_id="example_strategy")
        result = runner.run(ref, ctx, [_candle()])
        assert result.error is None

    def test_example_strategy_empty_candles(self) -> None:
        ref = load_strategy_runtime(EXAMPLE_STRATEGY_DIR, "example_strategy")
        runner = StrategyRuntimeRunner()
        ctx = _context(strategy_id="example_strategy")
        result = runner.run(ref, ctx, [])
        assert result.status == RunStatus.empty
        assert result.candles_received == 0
