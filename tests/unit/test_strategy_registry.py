"""
Unit tests for backend/strategy_registry/ — Phase 2D Strategy Registry Foundation.

Coverage:
- StrategyManifest model validation
- StrategyLifecycleStage and RuntimeMode enums
- load_manifest() happy path and all failure modes
- validate_strategy_files() happy path and all failure modes
- StrategyRegistry.register() — success, duplicate, validation/manifest errors
- StrategyRegistry.discover() — finds valid strategies, skips non-strategy dirs
- StrategyRegistry.get() and list_all()
- Registry does NOT import or execute strategy code
"""

import pytest
from pathlib import Path

from backend.strategy_registry import (
    ManifestLoadError,
    RuntimeMode,
    StrategyLifecycleStage,
    StrategyManifest,
    StrategyRegistry,
    StrategyRegistryEntry,
    StrategyRegistryError,
    StrategyValidationError,
    load_manifest,
    validate_strategy_files,
)

# ---------------------------------------------------------------------------
# Fixtures: paths to test fixture strategy directories
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "strategies"


@pytest.fixture()
def valid_strategy_dir() -> Path:
    return FIXTURES_DIR / "valid_strategy"


@pytest.fixture()
def missing_risk_dir() -> Path:
    return FIXTURES_DIR / "missing_risk_strategy"


@pytest.fixture()
def invalid_manifest_dir() -> Path:
    return FIXTURES_DIR / "invalid_manifest_strategy"


@pytest.fixture()
def malformed_yaml_dir() -> Path:
    return FIXTURES_DIR / "malformed_yaml_strategy"


@pytest.fixture()
def duplicate_id_dir() -> Path:
    return FIXTURES_DIR / "duplicate_id_strategy"


@pytest.fixture()
def registry() -> StrategyRegistry:
    return StrategyRegistry()


# ===========================================================================
# StrategyLifecycleStage
# ===========================================================================


class TestStrategyLifecycleStage:
    def test_all_canonical_stages_present(self):
        stages = {s.value for s in StrategyLifecycleStage}
        assert stages == {
            "idea",
            "research",
            "prototype",
            "validated",
            "backtested",
            "forward_tested",
            "paper_traded",
            "approved_for_live",
            "retired",
        }

    def test_str_enum_equality(self):
        assert StrategyLifecycleStage.PROTOTYPE == "prototype"
        assert StrategyLifecycleStage.APPROVED_FOR_LIVE == "approved_for_live"


# ===========================================================================
# RuntimeMode
# ===========================================================================


class TestRuntimeMode:
    def test_all_modes_present(self):
        modes = {m.value for m in RuntimeMode}
        assert modes == {
            "research",
            "backtesting",
            "forward_testing",
            "paper_trading",
            "live_trading",
        }

    def test_str_enum_equality(self):
        assert RuntimeMode.BACKTESTING == "backtesting"


# ===========================================================================
# StrategyManifest model
# ===========================================================================


class TestStrategyManifest:
    def _valid_data(self, **overrides):
        data = {
            "strategy_id": "test_strat",
            "version": "1.0.0",
            "lifecycle_stage": "prototype",
        }
        data.update(overrides)
        return data

    def test_minimal_valid_manifest(self):
        m = StrategyManifest(**self._valid_data())
        assert m.strategy_id == "test_strat"
        assert m.version == "1.0.0"
        assert m.lifecycle_stage == StrategyLifecycleStage.PROTOTYPE
        assert m.supported_assets == []
        assert m.runtime_compatibility == []
        assert m.warmup_bars == 0

    def test_full_manifest(self):
        m = StrategyManifest(
            strategy_id="full_strat",
            version="2.3.1",
            lifecycle_stage="validated",
            name="Full Strategy",
            description="A full strategy.",
            supported_assets=["crypto", "equities"],
            supported_timeframes=["1h", "4h"],
            feature_dependencies=["sma_20"],
            runtime_compatibility=["research", "backtesting"],
            warmup_bars=50,
        )
        assert m.lifecycle_stage == StrategyLifecycleStage.VALIDATED
        assert RuntimeMode.BACKTESTING in m.runtime_compatibility
        assert m.warmup_bars == 50

    def test_missing_strategy_id_raises(self):
        with pytest.raises(Exception):
            StrategyManifest(version="1.0.0", lifecycle_stage="prototype")

    def test_missing_version_raises(self):
        with pytest.raises(Exception):
            StrategyManifest(strategy_id="s", lifecycle_stage="prototype")

    def test_missing_lifecycle_stage_raises(self):
        with pytest.raises(Exception):
            StrategyManifest(strategy_id="s", version="1.0.0")

    def test_empty_strategy_id_raises(self):
        with pytest.raises(Exception):
            StrategyManifest(**self._valid_data(strategy_id="   "))

    def test_empty_version_raises(self):
        with pytest.raises(Exception):
            StrategyManifest(**self._valid_data(version=""))

    def test_invalid_lifecycle_stage_raises(self):
        with pytest.raises(Exception):
            StrategyManifest(**self._valid_data(lifecycle_stage="not_a_stage"))

    def test_hyphenated_lifecycle_stage_is_normalised(self):
        m = StrategyManifest(**self._valid_data(lifecycle_stage="approved-for-live"))
        assert m.lifecycle_stage == StrategyLifecycleStage.APPROVED_FOR_LIVE

    def test_invalid_runtime_mode_raises(self):
        with pytest.raises(Exception):
            StrategyManifest(**self._valid_data(runtime_compatibility=["not_a_mode"]))

    def test_negative_warmup_bars_raises(self):
        with pytest.raises(Exception):
            StrategyManifest(**self._valid_data(warmup_bars=-1))

    def test_extra_fields_are_ignored(self):
        # extra="ignore" — unknown yaml fields must not raise
        m = StrategyManifest(**self._valid_data(unknown_custom_field="ignored"))
        assert not hasattr(m, "unknown_custom_field")

    def test_manifest_is_immutable(self):
        m = StrategyManifest(**self._valid_data())
        with pytest.raises(Exception):
            m.strategy_id = "mutated"  # type: ignore[misc]

    def test_float_version_rejected_by_model(self):
        # StrategyManifest requires str version; float->str conversion is load_manifest's job
        with pytest.raises(Exception):
            StrategyManifest(strategy_id="s", version=1.0, lifecycle_stage="prototype")  # type: ignore[arg-type]


# ===========================================================================
# load_manifest
# ===========================================================================


class TestLoadManifest:
    def test_loads_valid_manifest(self, valid_strategy_dir):
        manifest = load_manifest(valid_strategy_dir)
        assert manifest.strategy_id == "valid_strategy"
        assert manifest.version == "1.0.0"
        assert manifest.lifecycle_stage == StrategyLifecycleStage.PROTOTYPE
        assert "crypto" in manifest.supported_assets
        assert RuntimeMode.BACKTESTING in manifest.runtime_compatibility
        assert manifest.warmup_bars == 20

    def test_missing_manifest_file_raises(self, tmp_path):
        with pytest.raises(ManifestLoadError, match="manifest not found"):
            load_manifest(tmp_path)

    def test_malformed_yaml_raises(self, malformed_yaml_dir):
        with pytest.raises(ManifestLoadError, match="failed to parse YAML"):
            load_manifest(malformed_yaml_dir)

    def test_invalid_manifest_fields_raise(self, invalid_manifest_dir):
        # strategy.yaml exists but is missing strategy_id and lifecycle_stage
        with pytest.raises(ManifestLoadError, match="invalid manifest"):
            load_manifest(invalid_manifest_dir)

    def test_non_mapping_yaml_raises(self, tmp_path):
        (tmp_path / "strategy.yaml").write_text("- just\n- a\n- list\n")
        with pytest.raises(ManifestLoadError, match="must be a YAML mapping"):
            load_manifest(tmp_path)

    def test_float_version_normalised_to_str(self, tmp_path):
        (tmp_path / "strategy.yaml").write_text(
            "strategy_id: s\nversion: 1.0\nlifecycle_stage: prototype\n"
        )
        manifest = load_manifest(tmp_path)
        assert manifest.version == "1.0"

    def test_loads_example_strategy_manifest(self):
        example_dir = Path(__file__).parent.parent.parent / "strategies" / "example_strategy"
        manifest = load_manifest(example_dir)
        assert manifest.strategy_id == "example_strategy"
        assert manifest.lifecycle_stage == StrategyLifecycleStage.PROTOTYPE

    def test_hyphenated_lifecycle_stage_from_yaml_is_accepted(self, tmp_path):
        (tmp_path / "strategy.yaml").write_text(
            "strategy_id: s\nversion: 1.0.0\nlifecycle_stage: approved-for-live\n"
        )
        manifest = load_manifest(tmp_path)
        assert manifest.lifecycle_stage == StrategyLifecycleStage.APPROVED_FOR_LIVE


# ===========================================================================
# validate_strategy_files
# ===========================================================================


class TestValidateStrategyFiles:
    def test_valid_strategy_passes(self, valid_strategy_dir):
        validate_strategy_files(valid_strategy_dir)  # must not raise

    def test_missing_risk_file_raises(self, missing_risk_dir):
        with pytest.raises(StrategyValidationError, match="risk.py"):
            validate_strategy_files(missing_risk_dir)

    def test_missing_multiple_files_raises(self, tmp_path):
        # Only strategy.yaml — no .py stubs
        (tmp_path / "strategy.yaml").write_text("strategy_id: x\nversion: 1.0.0\nlifecycle_stage: prototype\n")
        with pytest.raises(StrategyValidationError) as exc_info:
            validate_strategy_files(tmp_path)
        msg = str(exc_info.value)
        assert "features.py" in msg
        assert "metadata.py" in msg
        assert "parameters.py" in msg
        assert "risk.py" in msg
        assert "runtime.py" in msg
        assert "signals.py" in msg
        assert "validators.py" in msg

    def test_nonexistent_directory_raises(self, tmp_path):
        with pytest.raises(StrategyValidationError, match="does not exist"):
            validate_strategy_files(tmp_path / "no_such_dir")

    def test_file_path_instead_of_dir_raises(self, tmp_path):
        f = tmp_path / "not_a_dir.yaml"
        f.write_text("")
        with pytest.raises(StrategyValidationError, match="expected a directory"):
            validate_strategy_files(f)

    def test_validates_example_strategy(self):
        example_dir = Path(__file__).parent.parent.parent / "strategies" / "example_strategy"
        validate_strategy_files(example_dir)  # must not raise


# ===========================================================================
# StrategyRegistry.register
# ===========================================================================


class TestStrategyRegistryRegister:
    def test_register_valid_strategy(self, registry, valid_strategy_dir):
        entry = registry.register(valid_strategy_dir)
        assert isinstance(entry, StrategyRegistryEntry)
        assert entry.manifest.strategy_id == "valid_strategy"
        assert entry.strategy_dir == valid_strategy_dir.resolve()

    def test_register_stores_entry(self, registry, valid_strategy_dir):
        registry.register(valid_strategy_dir)
        assert "valid_strategy" in registry

    def test_register_increments_length(self, registry, valid_strategy_dir):
        assert len(registry) == 0
        registry.register(valid_strategy_dir)
        assert len(registry) == 1

    def test_duplicate_registration_raises(self, registry, valid_strategy_dir, duplicate_id_dir):
        registry.register(valid_strategy_dir)
        with pytest.raises(StrategyRegistryError, match="already registered"):
            registry.register(duplicate_id_dir)

    def test_missing_files_raises_validation_error(self, registry, missing_risk_dir):
        with pytest.raises(StrategyValidationError):
            registry.register(missing_risk_dir)

    def test_invalid_manifest_raises_manifest_error(self, registry, invalid_manifest_dir):
        with pytest.raises(ManifestLoadError):
            registry.register(invalid_manifest_dir)

    def test_malformed_yaml_raises_manifest_error(self, registry, malformed_yaml_dir):
        with pytest.raises(ManifestLoadError):
            registry.register(malformed_yaml_dir)

    def test_registry_does_not_import_strategy_module(self, registry, valid_strategy_dir, monkeypatch):
        """Registering a strategy must not trigger any import of strategy code."""
        import builtins
        original_import = builtins.__import__

        imported_strategy_modules: list[str] = []

        def guarded_import(name, *args, **kwargs):
            if "valid_strategy" in name and "backend" not in name and "tests" not in name:
                imported_strategy_modules.append(name)
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", guarded_import)
        registry.register(valid_strategy_dir)
        assert imported_strategy_modules == [], (
            f"registry imported strategy code: {imported_strategy_modules}"
        )


# ===========================================================================
# StrategyRegistry.discover
# ===========================================================================


class TestStrategyRegistryDiscover:
    def test_discover_finds_valid_strategy(self, registry, tmp_path):
        # Use an isolated directory containing only a valid strategy
        src = FIXTURES_DIR / "valid_strategy"
        import shutil
        dst = tmp_path / "valid_strategy"
        shutil.copytree(src, dst)
        entries = registry.discover(tmp_path)
        ids = {e.manifest.strategy_id for e in entries}
        assert "valid_strategy" in ids

    def test_discover_skips_dirs_without_yaml(self, registry, tmp_path):
        (tmp_path / "not_a_strategy").mkdir()
        entries = registry.discover(tmp_path)
        assert entries == []

    def test_discover_nonexistent_dir_raises(self, registry, tmp_path):
        with pytest.raises(StrategyRegistryError, match="does not exist"):
            registry.discover(tmp_path / "no_such_dir")

    def test_discover_skips_already_registered(self, registry, valid_strategy_dir, tmp_path):
        import shutil
        dst = tmp_path / "valid_strategy"
        shutil.copytree(valid_strategy_dir, dst)
        registry.register(dst)
        # Second discover on same dir — already registered, must not raise, returns empty list
        entries = registry.discover(tmp_path)
        ids = {e.manifest.strategy_id for e in entries}
        assert "valid_strategy" not in ids

    def test_discover_skips_broken_and_returns_valid(self, registry, tmp_path):
        # One valid strategy directory, one broken (missing required .py files)
        valid = tmp_path / "good"
        valid.mkdir()
        (valid / "strategy.yaml").write_text(
            "strategy_id: good\nversion: 1.0.0\nlifecycle_stage: prototype\n"
        )
        for f in (
            "metadata.py",
            "parameters.py",
            "features.py",
            "signals.py",
            "risk.py",
            "runtime.py",
            "validators.py",
        ):
            (valid / f).write_text("# stub")

        bad = tmp_path / "bad"
        bad.mkdir()
        (bad / "strategy.yaml").write_text(
            "strategy_id: bad\nversion: 1.0.0\nlifecycle_stage: prototype\n"
        )
        # missing required .py files — discover() skips and records error

        entries = registry.discover(tmp_path)
        ids = {e.manifest.strategy_id for e in entries}
        assert "good" in ids
        assert "bad" not in ids
        # broken strategy error is stored in _last_discover_errors
        assert bad.resolve() in registry._last_discover_errors


# ===========================================================================
# StrategyRegistry.get and list_all
# ===========================================================================


class TestStrategyRegistryQuery:
    def test_get_registered_strategy(self, registry, valid_strategy_dir):
        registry.register(valid_strategy_dir)
        entry = registry.get("valid_strategy")
        assert entry.manifest.strategy_id == "valid_strategy"

    def test_get_unknown_strategy_raises(self, registry):
        with pytest.raises(StrategyRegistryError, match="not registered"):
            registry.get("nonexistent")

    def test_list_all_empty_registry(self, registry):
        assert registry.list_all() == []

    def test_list_all_after_registration(self, registry, valid_strategy_dir):
        registry.register(valid_strategy_dir)
        entries = registry.list_all()
        assert len(entries) == 1
        assert entries[0].manifest.strategy_id == "valid_strategy"

    def test_contains_operator(self, registry, valid_strategy_dir):
        assert "valid_strategy" not in registry
        registry.register(valid_strategy_dir)
        assert "valid_strategy" in registry

    def test_len_reflects_registrations(self, registry, valid_strategy_dir):
        assert len(registry) == 0
        registry.register(valid_strategy_dir)
        assert len(registry) == 1
