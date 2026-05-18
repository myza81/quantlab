from backend.strategy_registry.manifest import ManifestLoadError, load_manifest
from backend.strategy_registry.models import (
    RuntimeMode,
    StrategyLifecycleStage,
    StrategyManifest,
)
from backend.strategy_registry.registry import (
    StrategyRegistry,
    StrategyRegistryEntry,
    StrategyRegistryError,
)
from backend.strategy_registry.validator import (
    REQUIRED_STRATEGY_FILES,
    StrategyValidationError,
    validate_strategy_files,
)

# StrategyDraft is intentionally NOT re-exported from this package __init__
# to avoid a circular import:
#   strategy_registry.__init__
#   → drafts.py → backend.tools.registry → backend.tools.models
#   → backend.strategy_registry.models (needs the package) → CIRCULAR
#
# Import directly from backend.strategy_registry.drafts instead.

__all__ = [
    # Models
    "StrategyLifecycleStage",
    "RuntimeMode",
    "StrategyManifest",
    # Manifest
    "load_manifest",
    "ManifestLoadError",
    # Validator
    "validate_strategy_files",
    "StrategyValidationError",
    "REQUIRED_STRATEGY_FILES",
    # Registry
    "StrategyRegistry",
    "StrategyRegistryEntry",
    "StrategyRegistryError",
]
