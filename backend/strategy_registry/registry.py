from dataclasses import dataclass
from pathlib import Path

from backend.strategy_registry.manifest import ManifestLoadError, load_manifest
from backend.strategy_registry.models import StrategyManifest
from backend.strategy_registry.validator import StrategyValidationError, validate_strategy_files


class StrategyRegistryError(Exception):
    """Raised for registry-level errors (duplicate ID, not found, bad path)."""


@dataclass(frozen=True)
class StrategyRegistryEntry:
    """An immutable record of a successfully registered strategy."""

    manifest: StrategyManifest
    strategy_dir: Path


class StrategyRegistry:
    """
    Discovers and registers strategy modules from the filesystem.

    Responsibilities:
    - validate required strategy files exist
    - load and validate strategy.yaml manifests
    - maintain an in-memory index keyed by strategy_id

    Out of scope:
    - executing strategy code
    - importing strategy modules
    - runtime orchestration
    - database persistence
    """

    def __init__(self) -> None:
        self._entries: dict[str, StrategyRegistryEntry] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, strategy_dir: Path) -> StrategyRegistryEntry:
        """
        Register a single strategy directory.

        Validates required files, loads and validates the manifest,
        then stores the entry indexed by strategy_id.

        Raises:
            StrategyValidationError: if required files are missing
            ManifestLoadError: if strategy.yaml is missing, invalid YAML, or fails contract
            StrategyRegistryError: if the strategy_id is already registered
        """
        strategy_dir = Path(strategy_dir).resolve()

        validate_strategy_files(strategy_dir)
        manifest = load_manifest(strategy_dir)

        if manifest.strategy_id in self._entries:
            raise StrategyRegistryError(
                f"strategy '{manifest.strategy_id}' is already registered "
                f"(from '{self._entries[manifest.strategy_id].strategy_dir}')"
            )

        entry = StrategyRegistryEntry(manifest=manifest, strategy_dir=strategy_dir)
        self._entries[manifest.strategy_id] = entry
        return entry

    def discover(self, strategies_dir: Path) -> list[StrategyRegistryEntry]:
        """
        Scan strategies_dir for strategy subdirectories and register each one.

        A subdirectory is treated as a strategy candidate only if it contains
        a strategy.yaml file. Directories without strategy.yaml are silently skipped.

        Strategies that fail structural validation or manifest parsing are skipped
        and their errors are collected. Already-registered strategies are also skipped
        to allow incremental re-discovery. Returns only newly registered entries.

        Raises:
            StrategyRegistryError: if strategies_dir does not exist
        """
        strategies_dir = Path(strategies_dir).resolve()

        if not strategies_dir.exists():
            raise StrategyRegistryError(
                f"strategies directory does not exist: '{strategies_dir}'"
            )

        registered: list[StrategyRegistryEntry] = []
        self._last_discover_errors: dict[Path, Exception] = {}

        for candidate in sorted(strategies_dir.iterdir()):
            if not candidate.is_dir():
                continue
            if not (candidate / "strategy.yaml").exists():
                continue

            try:
                entry = self.register(candidate)
                registered.append(entry)
            except (StrategyRegistryError, StrategyValidationError, ManifestLoadError) as exc:
                self._last_discover_errors[candidate] = exc

        return registered

    def get(self, strategy_id: str) -> StrategyRegistryEntry:
        """
        Return the registered entry for strategy_id.

        Raises:
            StrategyRegistryError: if no strategy with that ID is registered
        """
        entry = self._entries.get(strategy_id)
        if entry is None:
            raise StrategyRegistryError(
                f"strategy '{strategy_id}' is not registered"
            )
        return entry

    def list_all(self) -> list[StrategyRegistryEntry]:
        """Return all registered entries in insertion order."""
        return list(self._entries.values())

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, strategy_id: str) -> bool:
        return strategy_id in self._entries
