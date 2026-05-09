from pathlib import Path
from typing import Any

import yaml

from backend.strategy_registry.models import StrategyManifest

MANIFEST_FILENAME = "strategy.yaml"


class ManifestLoadError(Exception):
    """Raised when a strategy manifest cannot be loaded or parsed."""


def load_manifest(strategy_dir: Path) -> StrategyManifest:
    """
    Load and validate a strategy manifest from strategy.yaml.

    Raises ManifestLoadError for:
    - missing manifest file
    - invalid YAML syntax
    - non-mapping YAML content
    - missing or invalid required fields
    """
    strategy_dir = Path(strategy_dir)
    manifest_path = strategy_dir / MANIFEST_FILENAME

    if not manifest_path.exists():
        raise ManifestLoadError(
            f"manifest not found: '{manifest_path}'"
        )

    try:
        raw: Any = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ManifestLoadError(
            f"failed to parse YAML in '{manifest_path}': {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise ManifestLoadError(
            f"manifest must be a YAML mapping, got {type(raw).__name__} in '{manifest_path}'"
        )

    # YAML may parse bare version strings like `1.0` as float — normalise to str
    if "version" in raw:
        raw["version"] = str(raw["version"])

    try:
        return StrategyManifest(**raw)
    except Exception as exc:
        raise ManifestLoadError(
            f"invalid manifest in '{manifest_path}': {exc}"
        ) from exc
