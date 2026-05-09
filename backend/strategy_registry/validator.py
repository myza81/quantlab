from pathlib import Path

# Minimum required files per STRATEGY_CONTRACT.md canonical folder structure.
# strategy.yaml is validated separately by the manifest loader.
REQUIRED_STRATEGY_FILES: frozenset[str] = frozenset(
    {
        "strategy.yaml",
        "metadata.py",
        "parameters.py",
        "features.py",
        "signals.py",
        "risk.py",
        "runtime.py",
        "validators.py",
    }
)


class StrategyValidationError(Exception):
    """Raised when a strategy folder fails structural validation."""


def validate_strategy_files(strategy_dir: Path) -> None:
    """
    Verify that all required strategy files exist in strategy_dir.

    Raises StrategyValidationError listing every missing file.
    Does NOT import or execute any strategy code.
    """
    strategy_dir = Path(strategy_dir)

    if not strategy_dir.exists():
        raise StrategyValidationError(
            f"strategy directory does not exist: '{strategy_dir}'"
        )

    if not strategy_dir.is_dir():
        raise StrategyValidationError(
            f"expected a directory, got a file: '{strategy_dir}'"
        )

    missing = sorted(
        f for f in REQUIRED_STRATEGY_FILES if not (strategy_dir / f).exists()
    )

    if missing:
        raise StrategyValidationError(
            f"strategy at '{strategy_dir}' is missing required files: {missing}"
        )
