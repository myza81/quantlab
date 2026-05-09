from __future__ import annotations

import inspect
import typing
from types import ModuleType
from typing import Any, Callable

from backend.strategy_runtime.interface import CALLABLE_MODULE_MAP, RuntimeInterfaceError

# Expected positional (POSITIONAL_ONLY + POSITIONAL_OR_KEYWORD) parameter counts
# for each required strategy callable, derived from STRATEGY_CONTRACT.md.
CALLABLE_EXPECTED_PARAM_COUNTS: dict[str, int] = {
    "build_features": 2,    # (normalized_data, parameters)
    "generate_signals": 2,  # (features, parameters)
    "apply_risk_rules": 2,  # (signals, parameters)
    "validate_config": 1,   # (parameters,)
}

# Expected return types for best-effort annotation validation.
# Only checked when a return annotation is explicitly declared; absent annotations
# are silently skipped so unannotated strategies still pass.
CALLABLE_EXPECTED_RETURN_TYPES: dict[str, type] = {
    "build_features": dict,
    "generate_signals": dict,
    "apply_risk_rules": dict,
    "validate_config": bool,
}

# Import safety rules — contractually required but cannot all be statically detected.
# Strategy authors MUST comply. Violations may surface as StrategyLoadError at load time
# (e.g., a file-open that raises), but silent side effects (prints, logging, env reads)
# are the author's responsibility.
IMPORT_SAFETY_RULES: tuple[str, ...] = (
    "Strategy modules must not perform file I/O at import time.",
    "Strategy modules must not make network calls at import time.",
    "Strategy modules must not print or log at import time.",
    "Strategy modules must not modify global state at import time.",
    "Strategy modules must not start threads or processes at import time.",
    "Strategy modules must not access environment variables at import time.",
    "Strategy modules must not raise exceptions at import time.",
)


class CallableSignatureError(RuntimeInterfaceError):
    """Raised when a strategy callable has an invalid parameter signature or return annotation."""


def _count_positional_params(fn: Callable[..., Any]) -> tuple[int, int, bool]:
    """
    Inspect positional parameter counts of a callable.

    Returns (required_count, total_positional_count, has_var_positional) where:
      required_count        — POSITIONAL_ONLY / POSITIONAL_OR_KEYWORD params without defaults
      total_positional_count — all POSITIONAL_ONLY + POSITIONAL_OR_KEYWORD params
      has_var_positional    — True if *args is present in the signature
    """
    sig = inspect.signature(fn)
    required = 0
    total = 0
    has_var = False
    for p in sig.parameters.values():
        if p.kind == inspect.Parameter.VAR_POSITIONAL:
            has_var = True
        elif p.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            total += 1
            if p.default is inspect.Parameter.empty:
                required += 1
    return required, total, has_var


def validate_callable_signatures(modules: dict[str, ModuleType]) -> None:
    """
    Validate that each required strategy callable has the correct parameter signature.

    Rules per STRATEGY_CONTRACT.md:
      build_features(normalized_data, parameters)  → 2 positional params
      generate_signals(features, parameters)        → 2 positional params
      apply_risk_rules(signals, parameters)         → 2 positional params
      validate_config(parameters)                  → 1 positional param

    *args is permitted; only the positional count is enforced.
    Modules or callables missing from `modules` are skipped — those violations
    are the responsibility of validate_strategy_interface().

    Raises CallableSignatureError listing ALL violations (not first-failure-only).
    Does NOT invoke any strategy logic.
    """
    violations: list[str] = []

    for callable_name, module_stem in CALLABLE_MODULE_MAP.items():
        expected_count = CALLABLE_EXPECTED_PARAM_COUNTS.get(callable_name)
        if expected_count is None:
            continue

        module = modules.get(module_stem)
        if module is None:
            continue  # missing module already handled by validate_strategy_interface

        fn = getattr(module, callable_name, None)
        if not callable(fn):
            continue  # non-callable attribute already handled by validate_strategy_interface

        try:
            required, total, has_var = _count_positional_params(fn)
        except (ValueError, TypeError):
            violations.append(f"{callable_name}: cannot inspect signature")
            continue

        if has_var:
            # *args present: require that no more than `expected_count` positional
            # params precede *args (the strategy engine will pass exactly that many).
            if required > expected_count:
                violations.append(
                    f"{callable_name}: expected at most {expected_count} required "
                    f"positional parameter(s) before *args, but found {required}"
                )
        else:
            if total != expected_count:
                violations.append(
                    f"{callable_name}: expected exactly {expected_count} positional "
                    f"parameter(s) but found {total}"
                )

    if violations:
        raise CallableSignatureError(
            f"Strategy callable signature violation(s): {violations}"
        )


def validate_return_annotations(modules: dict[str, ModuleType]) -> None:
    """
    Best-effort validation of return type annotations for required callables.

    Only raises if an annotation IS explicitly declared AND is clearly incompatible
    with the expected return type. Absent annotations are silently skipped.
    Generic annotations (e.g. dict[str, Any]) cannot be deeply inspected and are
    also skipped — this keeps the check conservative and non-breaking.

    Raises CallableSignatureError listing ALL annotation violations.
    Does NOT invoke any strategy logic.
    """
    violations: list[str] = []

    for callable_name, module_stem in CALLABLE_MODULE_MAP.items():
        expected_type = CALLABLE_EXPECTED_RETURN_TYPES.get(callable_name)
        if expected_type is None:
            continue

        module = modules.get(module_stem)
        if module is None:
            continue

        fn = getattr(module, callable_name, None)
        if not callable(fn):
            continue

        try:
            hints = typing.get_type_hints(fn)
        except Exception:
            continue  # unresolvable hints — skip gracefully

        annotation = hints.get("return", inspect.Parameter.empty)
        if annotation is inspect.Parameter.empty:
            continue  # no return annotation declared — skip

        # Only flag plain concrete types that are clearly incompatible.
        # Generics (dict[str, Any], List[...], etc.) are not plain `type` instances
        # in Python 3.9+ and will be skipped by the isinstance guard below.
        try:
            if isinstance(annotation, type) and not issubclass(annotation, expected_type):
                violations.append(
                    f"{callable_name}: return annotation `{annotation.__name__}` is "
                    f"incompatible with expected `{expected_type.__name__}`"
                )
        except TypeError:
            pass  # complex generic — skip

    if violations:
        raise CallableSignatureError(
            f"Strategy return annotation violation(s): {violations}"
        )
