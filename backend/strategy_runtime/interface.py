from __future__ import annotations

from types import ModuleType

REQUIRED_CALLABLES: tuple[str, ...] = (
    "build_features",
    "generate_signals",
    "apply_risk_rules",
    "validate_config",
)

# Maps each required callable to the strategy module file that owns it.
# Keys mirror REQUIRED_CALLABLES; values are file stems under the strategy dir.
CALLABLE_MODULE_MAP: dict[str, str] = {
    "build_features": "features",
    "generate_signals": "signals",
    "apply_risk_rules": "risk",
    "validate_config": "validators",
}


class RuntimeInterfaceError(Exception):
    """Raised when a strategy does not expose all required callable contracts."""


def validate_strategy_interface(modules: dict[str, ModuleType]) -> None:
    """
    Validate that loaded strategy modules expose all required callables.

    `modules` maps file stem → loaded ModuleType (e.g. "features" → <module>).

    Raises RuntimeInterfaceError listing all missing callables.
    Does NOT invoke any strategy logic.
    """
    missing: list[str] = []

    for callable_name, module_stem in CALLABLE_MODULE_MAP.items():
        module = modules.get(module_stem)
        if module is None or not callable(getattr(module, callable_name, None)):
            missing.append(callable_name)

    if missing:
        raise RuntimeInterfaceError(
            f"Strategy is missing required callable(s): {missing}"
        )
