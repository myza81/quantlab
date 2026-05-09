from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from backend.strategy_runtime.interface import (
    CALLABLE_MODULE_MAP,
    validate_strategy_interface,
)
from backend.strategy_runtime.signature_validator import (
    validate_callable_signatures,
    validate_return_annotations,
)

# Module file stems loaded for runtime interface validation
_RUNTIME_MODULE_STEMS: tuple[str, ...] = ("features", "signals", "risk", "validators")


class StrategyLoadError(Exception):
    """Raised when a strategy module file cannot be loaded from disk."""


@dataclass(frozen=True)
class StrategyRuntimeReference:
    """
    Validated callable references for a single strategy.

    Holds direct references to the four required strategy callables.
    Does NOT invoke the required strategy callables during loading — callers
    invoke them explicitly later. Note that Python import still executes any
    module top-level code, so strategy files must remain import-safe.
    """

    strategy_id: str
    strategy_dir: Path
    build_features: Callable[..., Any]
    generate_signals: Callable[..., Any]
    apply_risk_rules: Callable[..., Any]
    validate_config: Callable[..., Any]


def _load_module(strategy_dir: Path, stem: str) -> ModuleType:
    """Load a single strategy sub-module by file path."""
    file = strategy_dir / f"{stem}.py"
    if not file.exists():
        raise StrategyLoadError(f"Strategy module file not found: {file}")

    qualified_name = f"_quantlab_strategy_{strategy_dir.name}_{stem}"
    spec = importlib.util.spec_from_file_location(qualified_name, file)
    if spec is None or spec.loader is None:
        raise StrategyLoadError(f"Cannot create module spec for: {file}")

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        raise StrategyLoadError(
            f"Error executing strategy module {file}: {exc}"
        ) from exc

    return module


def load_strategy_runtime(
    strategy_dir: Path, strategy_id: str
) -> StrategyRuntimeReference:
    """
    Load and validate a strategy's runtime interface from `strategy_dir`.

    Loads features.py, signals.py, risk.py, validators.py, then validates
    that all required callables are present.

    Returns a StrategyRuntimeReference holding callable references without
    invoking any of the required strategy callables.

    Important boundary:
    - The loader does NOT call build_features/generate_signals/apply_risk_rules/
      validate_config during validation.
    - Python import DOES execute module top-level code. Strategy modules must
      therefore obey IMPORT_SAFETY_RULES and remain side-effect-free at import.

    Raises:
        StrategyLoadError: if any module file cannot be loaded
        RuntimeInterfaceError: if any required callable is missing
    """
    strategy_dir = Path(strategy_dir)

    modules: dict[str, ModuleType] = {}
    for stem in _RUNTIME_MODULE_STEMS:
        modules[stem] = _load_module(strategy_dir, stem)

    validate_strategy_interface(modules)
    validate_callable_signatures(modules)
    validate_return_annotations(modules)

    def _get(callable_name: str) -> Callable[..., Any]:
        stem = CALLABLE_MODULE_MAP[callable_name]
        return getattr(modules[stem], callable_name)

    return StrategyRuntimeReference(
        strategy_id=strategy_id,
        strategy_dir=strategy_dir,
        build_features=_get("build_features"),
        generate_signals=_get("generate_signals"),
        apply_risk_rules=_get("apply_risk_rules"),
        validate_config=_get("validate_config"),
    )
