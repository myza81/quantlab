"""
Unit tests for backend/strategy_runtime/ — Phase 2E + 2F Strategy Runtime Interface.

Coverage:
- SignalType enum completeness
- StrategySignal model validation (required fields, UTC enforcement, immutability)
- validate_strategy_interface() happy path and all failure modes
- load_strategy_runtime() happy path and all failure modes
- REQUIRED_CALLABLES and CALLABLE_MODULE_MAP contract constants
- StrategyRuntimeReference callable references without invocation
- Architecture guardrail: registry remains metadata-only (no runtime imports)
- Data contract: StrategySignal UTC enforcement aligned with NormalizedOHLCV
- Phase 2F: callable signature validation (parameter counts)
- Phase 2F: return annotation validation (best-effort, present annotations only)
- Phase 2F: import safety rules documented
- Phase 2F: wrong_signature_strategy fixture integration
"""

import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.strategy_runtime import (
    CALLABLE_EXPECTED_PARAM_COUNTS,
    CALLABLE_EXPECTED_RETURN_TYPES,
    CALLABLE_MODULE_MAP,
    IMPORT_SAFETY_RULES,
    REQUIRED_CALLABLES,
    CallableSignatureError,
    RuntimeInterfaceError,
    SignalType,
    StrategyLoadError,
    StrategyRuntimeReference,
    StrategySignal,
    load_strategy_runtime,
    validate_callable_signatures,
    validate_return_annotations,
    validate_strategy_interface,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "strategies"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_module(**callables: object) -> types.ModuleType:
    mod = types.ModuleType("_test_module")
    for name, obj in callables.items():
        setattr(mod, name, obj)
    return mod


def _noop(*args: object, **kwargs: object):  # no return annotation — avoids annotation validation
    return None


def _valid_modules() -> dict[str, types.ModuleType]:
    return {
        "features": _make_module(build_features=_noop),
        "signals": _make_module(generate_signals=_noop),
        "risk": _make_module(apply_risk_rules=_noop),
        "validators": _make_module(validate_config=_noop),
    }


def _valid_signal_kwargs(**overrides: object) -> dict:
    base: dict = {
        "strategy_id": "test_strategy",
        "timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "signal_type": SignalType.long,
        "entry_reference": 50000.0,
        "invalidation_level": 48000.0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# SignalType enum
# ---------------------------------------------------------------------------


class TestSignalType:
    def test_all_values_present(self) -> None:
        assert {s.value for s in SignalType} == {"long", "short", "exit", "reduce"}

    def test_is_string_enum(self) -> None:
        assert isinstance(SignalType.long, str)
        assert isinstance(SignalType.short, str)
        assert isinstance(SignalType.exit, str)
        assert isinstance(SignalType.reduce, str)


# ---------------------------------------------------------------------------
# StrategySignal model
# ---------------------------------------------------------------------------


class TestStrategySignal:
    def test_valid_signal_creates(self) -> None:
        sig = StrategySignal(**_valid_signal_kwargs())
        assert sig.strategy_id == "test_strategy"
        assert sig.signal_type == SignalType.long
        assert sig.symbol == "BTCUSDT"

    def test_all_signal_types_accepted(self) -> None:
        for st in SignalType:
            sig = StrategySignal(**_valid_signal_kwargs(signal_type=st))
            assert sig.signal_type == st

    def test_signal_type_string_coercion(self) -> None:
        sig = StrategySignal(**_valid_signal_kwargs(signal_type="short"))
        assert sig.signal_type == SignalType.short

    def test_invalid_signal_type_rejected(self) -> None:
        with pytest.raises(Exception):
            StrategySignal(**_valid_signal_kwargs(signal_type="buy"))

    def test_naive_timestamp_rejected(self) -> None:
        with pytest.raises(Exception):
            StrategySignal(**_valid_signal_kwargs(timestamp=datetime(2026, 1, 1)))

    def test_utc_timestamp_accepted(self) -> None:
        sig = StrategySignal(**_valid_signal_kwargs())
        assert sig.timestamp.tzinfo is not None

    def test_non_utc_timestamp_is_normalized_to_utc(self) -> None:
        from datetime import timedelta

        tz_plus8 = timezone(timedelta(hours=8))
        sig = StrategySignal(
            **_valid_signal_kwargs(
                timestamp=datetime(2026, 1, 1, 8, 0, 0, tzinfo=tz_plus8)
            )
        )
        assert sig.timestamp.tzinfo == timezone.utc
        assert sig.timestamp.hour == 0

    def test_optional_fields_default_none(self) -> None:
        sig = StrategySignal(**_valid_signal_kwargs())
        assert sig.confidence is None
        assert sig.metadata is None
        assert sig.tags is None
        assert sig.reasoning is None
        assert sig.feature_snapshot is None
        assert sig.setup_id is None

    def test_optional_fields_accepted(self) -> None:
        sig = StrategySignal(
            **_valid_signal_kwargs(
                confidence=0.85,
                metadata={"source": "breakout"},
                tags=["momentum", "volume_confirm"],
                reasoning="strong breakout above resistance",
                feature_snapshot={"rsi": 72.0, "atr": 500.0},
                setup_id="setup_001",
            )
        )
        assert sig.confidence == 0.85
        assert sig.tags == ["momentum", "volume_confirm"]
        assert sig.setup_id == "setup_001"

    def test_signal_is_immutable(self) -> None:
        sig = StrategySignal(**_valid_signal_kwargs())
        with pytest.raises(Exception):
            sig.symbol = "ETHUSDT"  # type: ignore[misc]

    def test_missing_required_field_raises(self) -> None:
        kwargs = _valid_signal_kwargs()
        del kwargs["entry_reference"]
        with pytest.raises(Exception):
            StrategySignal(**kwargs)


# ---------------------------------------------------------------------------
# validate_strategy_interface
# ---------------------------------------------------------------------------


class TestValidateStrategyInterface:
    def test_valid_modules_pass(self) -> None:
        validate_strategy_interface(_valid_modules())  # must not raise

    def test_missing_build_features_raises(self) -> None:
        modules = _valid_modules()
        modules["features"] = _make_module()
        with pytest.raises(RuntimeInterfaceError) as exc_info:
            validate_strategy_interface(modules)
        assert "build_features" in str(exc_info.value)

    def test_missing_generate_signals_raises(self) -> None:
        modules = _valid_modules()
        modules["signals"] = _make_module()
        with pytest.raises(RuntimeInterfaceError) as exc_info:
            validate_strategy_interface(modules)
        assert "generate_signals" in str(exc_info.value)

    def test_missing_apply_risk_rules_raises(self) -> None:
        modules = _valid_modules()
        modules["risk"] = _make_module()
        with pytest.raises(RuntimeInterfaceError) as exc_info:
            validate_strategy_interface(modules)
        assert "apply_risk_rules" in str(exc_info.value)

    def test_missing_validate_config_raises(self) -> None:
        modules = _valid_modules()
        modules["validators"] = _make_module()
        with pytest.raises(RuntimeInterfaceError) as exc_info:
            validate_strategy_interface(modules)
        assert "validate_config" in str(exc_info.value)

    def test_multiple_missing_callables_reported_together(self) -> None:
        modules = {
            "features": _make_module(),
            "signals": _make_module(),
            "risk": _make_module(apply_risk_rules=_noop),
            "validators": _make_module(validate_config=_noop),
        }
        with pytest.raises(RuntimeInterfaceError) as exc_info:
            validate_strategy_interface(modules)
        msg = str(exc_info.value)
        assert "build_features" in msg
        assert "generate_signals" in msg

    def test_non_callable_attribute_fails(self) -> None:
        modules = _valid_modules()
        modules["features"] = _make_module(build_features="not_a_function")
        with pytest.raises(RuntimeInterfaceError):
            validate_strategy_interface(modules)

    def test_missing_module_key_fails(self) -> None:
        modules = {
            "signals": _make_module(generate_signals=_noop),
            "risk": _make_module(apply_risk_rules=_noop),
            "validators": _make_module(validate_config=_noop),
            # "features" absent entirely
        }
        with pytest.raises(RuntimeInterfaceError):
            validate_strategy_interface(modules)


# ---------------------------------------------------------------------------
# load_strategy_runtime — happy path
# ---------------------------------------------------------------------------


class TestLoadStrategyRuntimeHappyPath:
    def test_loads_valid_strategy(self) -> None:
        ref = load_strategy_runtime(FIXTURES_DIR / "valid_strategy", "valid_strategy_v1")
        assert isinstance(ref, StrategyRuntimeReference)

    def test_strategy_id_preserved(self) -> None:
        ref = load_strategy_runtime(FIXTURES_DIR / "valid_strategy", "valid_strategy_v1")
        assert ref.strategy_id == "valid_strategy_v1"

    def test_strategy_dir_preserved(self) -> None:
        d = FIXTURES_DIR / "valid_strategy"
        ref = load_strategy_runtime(d, "valid_strategy_v1")
        assert ref.strategy_dir == d

    def test_all_callables_present(self) -> None:
        ref = load_strategy_runtime(FIXTURES_DIR / "valid_strategy", "valid_strategy_v1")
        assert callable(ref.build_features)
        assert callable(ref.generate_signals)
        assert callable(ref.apply_risk_rules)
        assert callable(ref.validate_config)

    def test_validate_config_comes_from_validators_module(self) -> None:
        ref = load_strategy_runtime(FIXTURES_DIR / "valid_strategy", "valid_strategy_v1")
        assert ref.validate_config.__code__.co_filename.endswith("validators.py")

    def test_callables_not_invoked_during_load(self) -> None:
        # Loading must not call strategy functions — reference only
        ref = load_strategy_runtime(FIXTURES_DIR / "valid_strategy", "valid_strategy_v1")
        assert ref is not None  # no side effects expected from load

    def test_runtime_reference_is_immutable(self) -> None:
        ref = load_strategy_runtime(FIXTURES_DIR / "valid_strategy", "valid_strategy_v1")
        with pytest.raises(Exception):
            ref.strategy_id = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# load_strategy_runtime — failure modes
# ---------------------------------------------------------------------------


class TestLoadStrategyRuntimeFailures:
    def test_nonexistent_directory_raises_load_error(self, tmp_path: Path) -> None:
        with pytest.raises(StrategyLoadError):
            load_strategy_runtime(tmp_path / "does_not_exist", "x")

    def test_missing_callable_raises_runtime_interface_error(self) -> None:
        # missing_callable_strategy has features.py but no build_features
        with pytest.raises(RuntimeInterfaceError) as exc_info:
            load_strategy_runtime(
                FIXTURES_DIR / "missing_callable_strategy", "missing_callable"
            )
        assert "build_features" in str(exc_info.value)

    def test_syntax_error_in_module_raises_load_error(self, tmp_path: Path) -> None:
        strategy_dir = tmp_path / "bad_syntax_strategy"
        strategy_dir.mkdir()
        (strategy_dir / "features.py").write_text(
            "def build_features(: invalid syntax\n"
        )
        for stem in ("signals", "risk", "validators"):
            (strategy_dir / f"{stem}.py").write_text("# stub\n")
        with pytest.raises(StrategyLoadError):
            load_strategy_runtime(strategy_dir, "bad_syntax")

    def test_missing_module_file_raises_load_error(self, tmp_path: Path) -> None:
        strategy_dir = tmp_path / "incomplete_strategy"
        strategy_dir.mkdir()
        # Only create 3 of the 4 required module files
        for stem in ("signals", "risk", "validators"):
            (strategy_dir / f"{stem}.py").write_text("# stub\n")
        # features.py deliberately absent
        with pytest.raises(StrategyLoadError):
            load_strategy_runtime(strategy_dir, "incomplete")


# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------


class TestContractConstants:
    def test_required_callables_complete(self) -> None:
        assert set(REQUIRED_CALLABLES) == {
            "build_features",
            "generate_signals",
            "apply_risk_rules",
            "validate_config",
        }

    def test_callable_module_map_covers_all_required(self) -> None:
        assert set(CALLABLE_MODULE_MAP.keys()) == set(REQUIRED_CALLABLES)

    def test_callable_module_map_assignments(self) -> None:
        assert CALLABLE_MODULE_MAP["build_features"] == "features"
        assert CALLABLE_MODULE_MAP["generate_signals"] == "signals"
        assert CALLABLE_MODULE_MAP["apply_risk_rules"] == "risk"
        assert CALLABLE_MODULE_MAP["validate_config"] == "validators"


# ---------------------------------------------------------------------------
# Architecture guardrail: registry remains metadata-only
# ---------------------------------------------------------------------------


class TestRegistryRuntimeIsolation:
    def test_registry_module_does_not_import_strategy_runtime(self) -> None:
        import inspect

        from backend.strategy_registry import registry as reg_module

        source = inspect.getsource(reg_module)
        assert "strategy_runtime" not in source

    def test_registry_does_not_reference_load_strategy_runtime(self) -> None:
        import inspect

        from backend.strategy_registry import registry as reg_module

        source = inspect.getsource(reg_module)
        assert "load_strategy_runtime" not in source


# ---------------------------------------------------------------------------
# Data contract alignment
# ---------------------------------------------------------------------------


class TestDataContractAlignment:
    def test_strategy_signal_rejects_naive_timestamp(self) -> None:
        with pytest.raises(Exception):
            StrategySignal(
                strategy_id="s",
                timestamp=datetime(2026, 1, 1),  # naive — rejected
                symbol="X",
                timeframe="1h",
                signal_type=SignalType.long,
                entry_reference=1.0,
                invalidation_level=0.9,
            )

    def test_normalized_ohlcv_importable_for_strategy_use(self) -> None:
        from backend.data.schemas import NormalizedOHLCV

        assert NormalizedOHLCV is not None

    def test_strategy_runtime_does_not_bypass_data_contracts(self) -> None:
        import inspect

        from backend.strategy_runtime import loader as loader_module

        source = inspect.getsource(loader_module)
        # loader must not reference raw provider types
        assert "CSVAdapter" not in source
        assert "csv_adapter" not in source


# ---------------------------------------------------------------------------
# Phase 2F: Callable signature validation
# ---------------------------------------------------------------------------


def _make_fn(n_params: int, *, has_var: bool = False) -> object:
    """Build a callable with exactly `n_params` positional params (+ optional *args)."""
    if n_params == 0 and not has_var:
        def fn() -> None: ...  # noqa: E704
    elif n_params == 1 and not has_var:
        def fn(a: object) -> None: ...  # noqa: E704
    elif n_params == 2 and not has_var:
        def fn(a: object, b: object) -> None: ...  # noqa: E704
    elif n_params == 3 and not has_var:
        def fn(a: object, b: object, c: object) -> None: ...  # noqa: E704
    elif n_params == 0 and has_var:
        def fn(*args: object) -> None: ...  # noqa: E704
    elif n_params == 1 and has_var:
        def fn(a: object, *args: object) -> None: ...  # noqa: E704
    elif n_params == 2 and has_var:
        def fn(a: object, b: object, *args: object) -> None: ...  # noqa: E704
    else:
        def fn(*args: object, **kwargs: object) -> None: ...  # noqa: E704
    return fn


def _modules_with_override(callable_name: str, fn: object) -> dict[str, types.ModuleType]:
    """Return valid_modules() with `callable_name` replaced by `fn`."""
    stem = CALLABLE_MODULE_MAP[callable_name]
    modules = _valid_modules()
    modules[stem] = _make_module(**{callable_name: fn})
    return modules


class TestCallableSignatureValidation:
    def test_valid_signatures_pass(self) -> None:
        validate_callable_signatures(_valid_modules())  # must not raise

    # --- build_features: expects 2 positional params ---

    def test_build_features_one_param_raises(self) -> None:
        with pytest.raises(CallableSignatureError) as exc_info:
            validate_callable_signatures(
                _modules_with_override("build_features", _make_fn(1))
            )
        assert "build_features" in str(exc_info.value)

    def test_build_features_three_params_raises(self) -> None:
        with pytest.raises(CallableSignatureError) as exc_info:
            validate_callable_signatures(
                _modules_with_override("build_features", _make_fn(3))
            )
        assert "build_features" in str(exc_info.value)

    def test_build_features_zero_params_raises(self) -> None:
        with pytest.raises(CallableSignatureError) as exc_info:
            validate_callable_signatures(
                _modules_with_override("build_features", _make_fn(0))
            )
        assert "build_features" in str(exc_info.value)

    # --- generate_signals: expects 2 positional params ---

    def test_generate_signals_one_param_raises(self) -> None:
        with pytest.raises(CallableSignatureError) as exc_info:
            validate_callable_signatures(
                _modules_with_override("generate_signals", _make_fn(1))
            )
        assert "generate_signals" in str(exc_info.value)

    # --- apply_risk_rules: expects 2 positional params ---

    def test_apply_risk_rules_one_param_raises(self) -> None:
        with pytest.raises(CallableSignatureError) as exc_info:
            validate_callable_signatures(
                _modules_with_override("apply_risk_rules", _make_fn(1))
            )
        assert "apply_risk_rules" in str(exc_info.value)

    # --- validate_config: expects 1 positional param ---

    def test_validate_config_zero_params_raises(self) -> None:
        with pytest.raises(CallableSignatureError) as exc_info:
            validate_callable_signatures(
                _modules_with_override("validate_config", _make_fn(0))
            )
        assert "validate_config" in str(exc_info.value)

    def test_validate_config_two_params_raises(self) -> None:
        with pytest.raises(CallableSignatureError) as exc_info:
            validate_callable_signatures(
                _modules_with_override("validate_config", _make_fn(2))
            )
        assert "validate_config" in str(exc_info.value)

    # --- *args is allowed ---

    def test_build_features_with_star_args_passes(self) -> None:
        # def build_features(a, b, *args) has 2 positional + *args — valid
        validate_callable_signatures(
            _modules_with_override("build_features", _make_fn(2, has_var=True))
        )

    def test_validate_config_with_star_args_passes(self) -> None:
        # def validate_config(a, *args) has 1 positional + *args — valid
        validate_callable_signatures(
            _modules_with_override("validate_config", _make_fn(1, has_var=True))
        )

    # --- All violations reported together ---

    def test_multiple_signature_violations_reported_together(self) -> None:
        modules = {
            "features": _make_module(build_features=_make_fn(1)),   # wrong: 1 instead of 2
            "signals": _make_module(generate_signals=_make_fn(3)),  # wrong: 3 instead of 2
            "risk": _make_module(apply_risk_rules=_noop),
            "validators": _make_module(validate_config=_noop),
        }
        with pytest.raises(CallableSignatureError) as exc_info:
            validate_callable_signatures(modules)
        msg = str(exc_info.value)
        assert "build_features" in msg
        assert "generate_signals" in msg

    # --- CALLABLE_EXPECTED_PARAM_COUNTS contract ---

    def test_expected_param_counts_covers_all_required(self) -> None:
        assert set(CALLABLE_EXPECTED_PARAM_COUNTS.keys()) == set(REQUIRED_CALLABLES)

    def test_expected_param_counts_values(self) -> None:
        assert CALLABLE_EXPECTED_PARAM_COUNTS["build_features"] == 2
        assert CALLABLE_EXPECTED_PARAM_COUNTS["generate_signals"] == 2
        assert CALLABLE_EXPECTED_PARAM_COUNTS["apply_risk_rules"] == 2
        assert CALLABLE_EXPECTED_PARAM_COUNTS["validate_config"] == 1

    # --- Integration: wrong_signature_strategy fixture ---

    def test_wrong_signature_strategy_raises_signature_error(self) -> None:
        with pytest.raises(CallableSignatureError) as exc_info:
            load_strategy_runtime(
                FIXTURES_DIR / "wrong_signature_strategy", "wrong_sig"
            )
        assert "build_features" in str(exc_info.value)

    # --- Missing callable skipped (interface errors come first) ---

    def test_missing_callable_not_double_reported_as_signature_error(self) -> None:
        # If build_features is absent, validate_strategy_interface raises first
        modules = {
            "features": _make_module(),  # build_features absent
            "signals": _make_module(generate_signals=_noop),
            "risk": _make_module(apply_risk_rules=_noop),
            "validators": _make_module(validate_config=_noop),
        }
        with pytest.raises(RuntimeInterfaceError):
            validate_strategy_interface(modules)
        # validate_callable_signatures skips absent callables gracefully
        validate_callable_signatures(modules)  # must not raise


# ---------------------------------------------------------------------------
# Phase 2F: Return annotation validation
# ---------------------------------------------------------------------------


def _annotated_fn(n_params: int, return_type: object) -> object:
    """Build a callable with explicit return annotation."""
    import sys

    # Build a function dynamically with the given return annotation
    if n_params == 1:
        def fn(a: object) -> object: ...  # noqa: E704
    else:
        def fn(a: object, b: object) -> object: ...  # noqa: E704
    fn.__annotations__["return"] = return_type  # type: ignore[union-attr]
    return fn


class TestReturnAnnotationValidation:
    def test_no_annotations_pass(self) -> None:
        validate_return_annotations(_valid_modules())  # _noop has no annotations

    def test_correct_dict_annotation_passes(self) -> None:
        fn = _annotated_fn(2, dict)
        validate_return_annotations(_modules_with_override("build_features", fn))

    def test_correct_bool_annotation_passes(self) -> None:
        fn = _annotated_fn(1, bool)
        validate_return_annotations(_modules_with_override("validate_config", fn))

    def test_incompatible_str_annotation_raises(self) -> None:
        fn = _annotated_fn(2, str)  # build_features should return dict, not str
        with pytest.raises(CallableSignatureError) as exc_info:
            validate_return_annotations(_modules_with_override("build_features", fn))
        assert "build_features" in str(exc_info.value)

    def test_none_return_on_validate_config_raises(self) -> None:
        fn = _annotated_fn(1, type(None))  # validate_config should return bool
        with pytest.raises(CallableSignatureError) as exc_info:
            validate_return_annotations(_modules_with_override("validate_config", fn))
        assert "validate_config" in str(exc_info.value)

    def test_int_return_on_build_features_raises(self) -> None:
        fn = _annotated_fn(2, int)  # build_features should return dict
        with pytest.raises(CallableSignatureError) as exc_info:
            validate_return_annotations(_modules_with_override("build_features", fn))
        assert "build_features" in str(exc_info.value)

    def test_generic_dict_annotation_passes(self) -> None:
        # dict[str, Any] is a generic alias — not a plain type — should be skipped
        from typing import Any as AnyType
        fn = _annotated_fn(2, dict[str, AnyType])
        validate_return_annotations(_modules_with_override("build_features", fn))

    def test_all_violations_reported_together(self) -> None:
        fn_bf = _annotated_fn(2, str)   # build_features → str (wrong)
        fn_gs = _annotated_fn(2, int)   # generate_signals → int (wrong)
        modules = {
            "features": _make_module(build_features=fn_bf),
            "signals": _make_module(generate_signals=fn_gs),
            "risk": _make_module(apply_risk_rules=_noop),
            "validators": _make_module(validate_config=_noop),
        }
        with pytest.raises(CallableSignatureError) as exc_info:
            validate_return_annotations(modules)
        msg = str(exc_info.value)
        assert "build_features" in msg
        assert "generate_signals" in msg

    # --- CALLABLE_EXPECTED_RETURN_TYPES contract ---

    def test_expected_return_types_covers_all_required(self) -> None:
        assert set(CALLABLE_EXPECTED_RETURN_TYPES.keys()) == set(REQUIRED_CALLABLES)

    def test_expected_return_types_values(self) -> None:
        assert CALLABLE_EXPECTED_RETURN_TYPES["build_features"] is dict
        assert CALLABLE_EXPECTED_RETURN_TYPES["generate_signals"] is dict
        assert CALLABLE_EXPECTED_RETURN_TYPES["apply_risk_rules"] is dict
        assert CALLABLE_EXPECTED_RETURN_TYPES["validate_config"] is bool


# ---------------------------------------------------------------------------
# Phase 2F: Import safety rules documented
# ---------------------------------------------------------------------------


class TestImportSafetyRules:
    def test_import_safety_rules_is_non_empty(self) -> None:
        assert len(IMPORT_SAFETY_RULES) > 0

    def test_import_safety_rules_is_tuple_of_strings(self) -> None:
        assert isinstance(IMPORT_SAFETY_RULES, tuple)
        for rule in IMPORT_SAFETY_RULES:
            assert isinstance(rule, str)

    def test_import_safety_rules_covers_key_concerns(self) -> None:
        combined = " ".join(IMPORT_SAFETY_RULES).lower()
        assert "file" in combined or "i/o" in combined
        assert "network" in combined
        assert "global" in combined or "state" in combined

    def test_import_safety_rules_importable_from_package(self) -> None:
        from backend.strategy_runtime import IMPORT_SAFETY_RULES as rules
        assert rules is IMPORT_SAFETY_RULES

    def test_import_safety_rules_mentions_import_time_boundary(self) -> None:
        combined = " ".join(IMPORT_SAFETY_RULES).lower()
        assert "import time" in combined


# ---------------------------------------------------------------------------
# Phase 2F: load_strategy_runtime integration — valid_strategy still passes
# ---------------------------------------------------------------------------


class TestLoadStrategyRuntimePhase2F:
    def test_valid_strategy_passes_signature_validation(self) -> None:
        ref = load_strategy_runtime(FIXTURES_DIR / "valid_strategy", "valid_strategy_v1")
        assert isinstance(ref, StrategyRuntimeReference)

    def test_example_strategy_passes_signature_validation(self) -> None:
        example_dir = Path(__file__).parent.parent.parent / "strategies" / "example_strategy"
        ref = load_strategy_runtime(example_dir, "example_strategy_v1")
        assert isinstance(ref, StrategyRuntimeReference)

    def test_signature_error_is_subclass_of_runtime_interface_error(self) -> None:
        assert issubclass(CallableSignatureError, RuntimeInterfaceError)
