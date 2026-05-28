"""
Tests for ProviderAdapterFactory and create_default_factory_registry.

Covers:
  - Registration: valid, duplicate, empty name
  - build(): correct adapter construction, unknown provider, invalid params
  - get_capabilities(): known/unknown provider
  - list_capabilities(): sorting
  - __contains__, __len__
  - Default registry: yahoo registered, correct capabilities
  - Yahoo builder: valid symbol+timeframe → adapter, unsupported timeframe → ProviderBuildError
  - Architecture boundary: no concrete adapter imports in market_data_service
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from backend.data_providers.base import ProviderCapabilities, ProviderFetchError
from backend.data_providers.provider_factory import (
    ProviderAdapterFactory,
    ProviderBuildError,
    UnknownProviderError,
    create_default_factory_registry,
)
from backend.data_providers.range_provider import RangeProviderAdapter
from backend.data.schemas import NormalizedOHLCV


# ---------------------------------------------------------------------------
# Minimal stub adapter + factory
# ---------------------------------------------------------------------------

class _StubAdapter(RangeProviderAdapter):
    @property
    def provider_name(self) -> str:
        return "stub"

    def load(self, **kwargs: object) -> list[NormalizedOHLCV]:
        return []

    def fetch(self, start: datetime, end: datetime, **kwargs: object) -> list[NormalizedOHLCV]:
        return []


_STUB_CAPS = ProviderCapabilities(
    provider_id="stub",
    display_name="Stub Provider",
    supported_timeframes=("1d",),
    supported_asset_classes=("equity",),
)


def _stub_builder(**kwargs: object) -> _StubAdapter:
    return _StubAdapter()


# ---------------------------------------------------------------------------
# TestProviderCapabilitiesModel
# ---------------------------------------------------------------------------

class TestProviderCapabilitiesModel:
    def test_frozen(self) -> None:
        caps = ProviderCapabilities(
            provider_id="test",
            display_name="Test",
            supported_timeframes=("1d",),
            supported_asset_classes=("equity",),
        )
        with pytest.raises(Exception):
            caps.provider_id = "other"  # type: ignore[misc]

    def test_fields_stored(self) -> None:
        caps = ProviderCapabilities(
            provider_id="yahoo",
            display_name="Yahoo Finance",
            supported_timeframes=("1d", "1h"),
            supported_asset_classes=("equity", "crypto"),
        )
        assert caps.provider_id == "yahoo"
        assert caps.display_name == "Yahoo Finance"
        assert "1d" in caps.supported_timeframes
        assert "equity" in caps.supported_asset_classes


# ---------------------------------------------------------------------------
# TestProviderAdapterFactoryRegistration
# ---------------------------------------------------------------------------

class TestProviderAdapterFactoryRegistration:
    def test_register_then_contains(self) -> None:
        f = ProviderAdapterFactory()
        f.register("stub", _STUB_CAPS, _stub_builder)
        assert "stub" in f

    def test_case_insensitive_contains(self) -> None:
        f = ProviderAdapterFactory()
        f.register("Stub", _STUB_CAPS, _stub_builder)
        assert "STUB" in f
        assert "stub" in f

    def test_len_increases_on_register(self) -> None:
        f = ProviderAdapterFactory()
        assert len(f) == 0
        f.register("stub", _STUB_CAPS, _stub_builder)
        assert len(f) == 1

    def test_duplicate_registration_raises(self) -> None:
        f = ProviderAdapterFactory()
        f.register("stub", _STUB_CAPS, _stub_builder)
        with pytest.raises(ValueError, match="already registered"):
            f.register("stub", _STUB_CAPS, _stub_builder)

    def test_empty_provider_id_raises(self) -> None:
        f = ProviderAdapterFactory()
        with pytest.raises(ValueError, match="empty"):
            f.register("", _STUB_CAPS, _stub_builder)

    def test_whitespace_provider_id_raises(self) -> None:
        f = ProviderAdapterFactory()
        with pytest.raises(ValueError, match="empty"):
            f.register("  ", _STUB_CAPS, _stub_builder)

    def test_non_string_not_in_factory(self) -> None:
        f = ProviderAdapterFactory()
        assert 42 not in f  # type: ignore[operator]


# ---------------------------------------------------------------------------
# TestProviderAdapterFactoryBuild
# ---------------------------------------------------------------------------

class TestProviderAdapterFactoryBuild:
    def test_build_returns_adapter(self) -> None:
        f = ProviderAdapterFactory()
        f.register("stub", _STUB_CAPS, _stub_builder)
        adapter = f.build("stub")
        assert isinstance(adapter, _StubAdapter)

    def test_build_unknown_provider_raises(self) -> None:
        f = ProviderAdapterFactory()
        with pytest.raises(UnknownProviderError, match="unknown"):
            f.build("unknown")

    def test_build_error_message_lists_available(self) -> None:
        f = ProviderAdapterFactory()
        f.register("stub", _STUB_CAPS, _stub_builder)
        with pytest.raises(UnknownProviderError, match="stub"):
            f.build("other")

    def test_build_case_insensitive(self) -> None:
        f = ProviderAdapterFactory()
        f.register("stub", _STUB_CAPS, _stub_builder)
        adapter = f.build("STUB")
        assert isinstance(adapter, _StubAdapter)

    def test_build_kwargs_forwarded_to_builder(self) -> None:
        received: dict = {}

        def capturing_builder(**kwargs: object) -> _StubAdapter:
            received.update(kwargs)
            return _StubAdapter()

        f = ProviderAdapterFactory()
        f.register("stub", _STUB_CAPS, capturing_builder)
        f.build("stub", symbol="AAPL", timeframe="1d")
        assert received["symbol"] == "AAPL"
        assert received["timeframe"] == "1d"

    def test_build_builder_value_error_becomes_provider_build_error(self) -> None:
        def raising_builder(**kwargs: object) -> _StubAdapter:
            raise ValueError("bad timeframe")

        f = ProviderAdapterFactory()
        f.register("stub", _STUB_CAPS, raising_builder)
        with pytest.raises(ProviderBuildError, match="bad timeframe"):
            f.build("stub")


# ---------------------------------------------------------------------------
# TestProviderAdapterFactoryCapabilities
# ---------------------------------------------------------------------------

class TestProviderAdapterFactoryCapabilities:
    def test_get_capabilities_returns_registered_caps(self) -> None:
        f = ProviderAdapterFactory()
        f.register("stub", _STUB_CAPS, _stub_builder)
        caps = f.get_capabilities("stub")
        assert caps.provider_id == "stub"
        assert caps.display_name == "Stub Provider"

    def test_get_capabilities_unknown_raises(self) -> None:
        f = ProviderAdapterFactory()
        with pytest.raises(UnknownProviderError):
            f.get_capabilities("unknown")

    def test_list_capabilities_empty(self) -> None:
        f = ProviderAdapterFactory()
        assert f.list_capabilities() == []

    def test_list_capabilities_sorted_by_provider_id(self) -> None:
        f = ProviderAdapterFactory()
        caps_z = ProviderCapabilities(
            provider_id="zzz", display_name="Z", supported_timeframes=(), supported_asset_classes=()
        )
        caps_a = ProviderCapabilities(
            provider_id="aaa", display_name="A", supported_timeframes=(), supported_asset_classes=()
        )
        f.register("zzz", caps_z, _stub_builder)
        f.register("aaa", caps_a, _stub_builder)
        result = f.list_capabilities()
        assert result[0].provider_id == "aaa"
        assert result[1].provider_id == "zzz"

    def test_list_capabilities_returns_all(self) -> None:
        f = ProviderAdapterFactory()
        f.register("a", _STUB_CAPS, _stub_builder)
        f.register("b", _STUB_CAPS, _stub_builder)
        assert len(f.list_capabilities()) == 2


# ---------------------------------------------------------------------------
# TestCreateDefaultFactoryRegistry
# ---------------------------------------------------------------------------

class TestCreateDefaultFactoryRegistry:
    def test_contains_yahoo(self) -> None:
        registry = create_default_factory_registry()
        assert "yahoo" in registry

    def test_yahoo_capabilities_provider_id(self) -> None:
        registry = create_default_factory_registry()
        caps = registry.get_capabilities("yahoo")
        assert caps.provider_id == "yahoo"

    def test_yahoo_capabilities_display_name(self) -> None:
        registry = create_default_factory_registry()
        caps = registry.get_capabilities("yahoo")
        assert "Yahoo" in caps.display_name

    def test_yahoo_supports_1d_timeframe(self) -> None:
        registry = create_default_factory_registry()
        caps = registry.get_capabilities("yahoo")
        assert "1d" in caps.supported_timeframes

    def test_yahoo_supports_equity_asset_class(self) -> None:
        registry = create_default_factory_registry()
        caps = registry.get_capabilities("yahoo")
        assert "equity" in caps.supported_asset_classes

    def test_yahoo_supports_multiple_timeframes(self) -> None:
        registry = create_default_factory_registry()
        caps = registry.get_capabilities("yahoo")
        assert len(caps.supported_timeframes) >= 4

    def test_default_registry_has_four_providers(self) -> None:
        # Phase 3D added csv/parquet; Phase 3G added polygon → total = 4
        registry = create_default_factory_registry()
        assert len(registry) == 4

    def test_list_capabilities_contains_yahoo(self) -> None:
        registry = create_default_factory_registry()
        ids = [c.provider_id for c in registry.list_capabilities()]
        assert "yahoo" in ids


# ---------------------------------------------------------------------------
# TestYahooBuilderIntegration
# ---------------------------------------------------------------------------

class TestYahooBuilderIntegration:
    def test_build_yahoo_returns_adapter(self) -> None:
        registry = create_default_factory_registry()
        adapter = registry.build(
            "yahoo",
            symbol="AAPL",
            timeframe="1d",
            asset_class="equity",
            venue="NASDAQ",
        )
        assert isinstance(adapter, RangeProviderAdapter)

    def test_build_yahoo_adapter_provider_name(self) -> None:
        registry = create_default_factory_registry()
        adapter = registry.build("yahoo", symbol="AAPL", timeframe="1d")
        assert adapter.provider_name == "yahoo"

    def test_build_yahoo_unsupported_timeframe_raises_provider_build_error(self) -> None:
        registry = create_default_factory_registry()
        with pytest.raises(ProviderBuildError):
            registry.build("yahoo", symbol="AAPL", timeframe="4h")  # not supported by Yahoo

    def test_build_yahoo_extra_kwargs_ignored(self) -> None:
        registry = create_default_factory_registry()
        adapter = registry.build(
            "yahoo",
            symbol="AAPL",
            timeframe="1d",
            unknown_kwarg="should_be_ignored",
        )
        assert adapter is not None


# ---------------------------------------------------------------------------
# TestProviderFetchErrorInheritance
# ---------------------------------------------------------------------------

class TestProviderFetchErrorInheritance:
    def test_yahoo_adapter_error_is_provider_fetch_error(self) -> None:
        from backend.data_providers.yahoo.adapter import YahooAdapterError
        assert issubclass(YahooAdapterError, ProviderFetchError)

    def test_provider_fetch_error_is_exception(self) -> None:
        assert issubclass(ProviderFetchError, Exception)


# ---------------------------------------------------------------------------
# TestArchitectureBoundary
# ---------------------------------------------------------------------------

class TestArchitectureBoundary:
    def test_market_data_service_does_not_import_yahoo_adapter(self) -> None:
        import ast
        import pathlib

        service_path = pathlib.Path(
            "backend/api/services/market_data_service.py"
        )
        src = service_path.read_text()
        tree = ast.parse(src)

        forbidden = "data_providers.yahoo"
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = ""
                if isinstance(node, ast.ImportFrom) and node.module:
                    module = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name
                assert forbidden not in module, (
                    f"market_data_service must not import from {forbidden}; "
                    f"found: {module}"
                )

    def test_provider_factory_imports_yahoo_internally(self) -> None:
        import ast
        import pathlib

        factory_path = pathlib.Path(
            "backend/data_providers/provider_factory.py"
        )
        src = factory_path.read_text()
        # The factory may import yahoo inside functions — verify the module loads
        from backend.data_providers.provider_factory import create_default_factory_registry
        registry = create_default_factory_registry()
        assert "yahoo" in registry
