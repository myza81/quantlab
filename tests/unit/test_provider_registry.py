"""
Tests for ProviderRegistry.

Covers:
- Registration of valid adapters
- Resolution by name (case-insensitive)
- Duplicate registration rejection
- Missing provider error
- Deregistration
- List providers
- __len__ and __contains__
- Invalid input rejection (empty name, wrong type)
"""
import pytest

from backend.data_providers.provider_registry import (
    DuplicateProviderError,
    ProviderNotFoundError,
    ProviderRegistry,
    ProviderRegistryError,
)
from backend.data_providers.range_provider import RangeProviderAdapter
from backend.data.schemas import NormalizedOHLCV
from datetime import datetime


# ---------------------------------------------------------------------------
# Minimal stub adapter
# ---------------------------------------------------------------------------

class _StubAdapter(RangeProviderAdapter):
    def __init__(self, name: str = "stub") -> None:
        self._name = name

    @property
    def provider_name(self) -> str:
        return self._name

    def load(self, **kwargs: object) -> list[NormalizedOHLCV]:
        return []

    def fetch(self, start: datetime, end: datetime, **kwargs: object) -> list[NormalizedOHLCV]:
        return []


# ---------------------------------------------------------------------------
# TestProviderRegistryRegistration
# ---------------------------------------------------------------------------

class TestProviderRegistryRegistration:
    def test_register_and_get_returns_same_adapter(self) -> None:
        reg = ProviderRegistry()
        adapter = _StubAdapter()
        reg.register("csv", adapter)
        assert reg.get("csv") is adapter

    def test_case_insensitive_registration(self) -> None:
        reg = ProviderRegistry()
        adapter = _StubAdapter()
        reg.register("Yahoo", adapter)
        assert reg.get("YAHOO") is adapter
        assert reg.get("yahoo") is adapter

    def test_register_multiple_providers(self) -> None:
        reg = ProviderRegistry()
        a = _StubAdapter("a")
        b = _StubAdapter("b")
        reg.register("alpha", a)
        reg.register("beta", b)
        assert reg.get("alpha") is a
        assert reg.get("beta") is b

    def test_duplicate_registration_raises(self) -> None:
        reg = ProviderRegistry()
        reg.register("yahoo", _StubAdapter())
        with pytest.raises(DuplicateProviderError, match="yahoo"):
            reg.register("yahoo", _StubAdapter())

    def test_duplicate_registration_case_insensitive(self) -> None:
        reg = ProviderRegistry()
        reg.register("Yahoo", _StubAdapter())
        with pytest.raises(DuplicateProviderError):
            reg.register("YAHOO", _StubAdapter())

    def test_register_empty_name_raises(self) -> None:
        reg = ProviderRegistry()
        with pytest.raises(ValueError, match="empty"):
            reg.register("", _StubAdapter())

    def test_register_whitespace_name_raises(self) -> None:
        reg = ProviderRegistry()
        with pytest.raises(ValueError, match="empty"):
            reg.register("   ", _StubAdapter())

    def test_register_non_adapter_raises(self) -> None:
        reg = ProviderRegistry()
        with pytest.raises(TypeError, match="RangeProviderAdapter"):
            reg.register("bad", object())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TestProviderRegistryResolution
# ---------------------------------------------------------------------------

class TestProviderRegistryResolution:
    def test_get_missing_raises_provider_not_found(self) -> None:
        reg = ProviderRegistry()
        with pytest.raises(ProviderNotFoundError, match="yahoo"):
            reg.get("yahoo")

    def test_error_message_lists_available_providers(self) -> None:
        reg = ProviderRegistry()
        reg.register("csv", _StubAdapter())
        with pytest.raises(ProviderNotFoundError, match="csv"):
            reg.get("polygon")

    def test_provider_registry_error_is_base(self) -> None:
        with pytest.raises(ProviderRegistryError):
            reg = ProviderRegistry()
            reg.get("missing")


# ---------------------------------------------------------------------------
# TestProviderRegistryDeregistration
# ---------------------------------------------------------------------------

class TestProviderRegistryDeregistration:
    def test_deregister_removes_provider(self) -> None:
        reg = ProviderRegistry()
        reg.register("yahoo", _StubAdapter())
        reg.deregister("yahoo")
        with pytest.raises(ProviderNotFoundError):
            reg.get("yahoo")

    def test_deregister_allows_re_registration(self) -> None:
        reg = ProviderRegistry()
        adapter1 = _StubAdapter("a")
        adapter2 = _StubAdapter("b")
        reg.register("yahoo", adapter1)
        reg.deregister("yahoo")
        reg.register("yahoo", adapter2)
        assert reg.get("yahoo") is adapter2

    def test_deregister_missing_raises(self) -> None:
        reg = ProviderRegistry()
        with pytest.raises(ProviderNotFoundError):
            reg.deregister("yahoo")


# ---------------------------------------------------------------------------
# TestProviderRegistryIntrospection
# ---------------------------------------------------------------------------

class TestProviderRegistryIntrospection:
    def test_list_providers_empty(self) -> None:
        reg = ProviderRegistry()
        assert reg.list_providers() == []

    def test_list_providers_sorted(self) -> None:
        reg = ProviderRegistry()
        reg.register("polygon", _StubAdapter())
        reg.register("csv", _StubAdapter())
        reg.register("yahoo", _StubAdapter())
        assert reg.list_providers() == ["csv", "polygon", "yahoo"]

    def test_len_empty(self) -> None:
        reg = ProviderRegistry()
        assert len(reg) == 0

    def test_len_after_registration(self) -> None:
        reg = ProviderRegistry()
        reg.register("a", _StubAdapter())
        reg.register("b", _StubAdapter())
        assert len(reg) == 2

    def test_contains_registered(self) -> None:
        reg = ProviderRegistry()
        reg.register("yahoo", _StubAdapter())
        assert "yahoo" in reg
        assert "YAHOO" in reg

    def test_contains_missing(self) -> None:
        reg = ProviderRegistry()
        assert "yahoo" not in reg

    def test_contains_non_string(self) -> None:
        reg = ProviderRegistry()
        assert 42 not in reg  # type: ignore[operator]
