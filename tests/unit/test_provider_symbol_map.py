"""
Tests for ProviderSymbolMapping and SymbolMapService.

Covers:
- ProviderSymbolMapping model validation
- SymbolMapService add/resolve/remove/list operations
- Identity fallback when no explicit mapping exists
- Case normalisation (provider lowercase, symbol uppercase key)
- Duplicate mapping rejection
- Removing non-existent mapping
"""
import pytest

from backend.data_providers.provider_symbol_map import (
    ProviderSymbolMapError,
    ProviderSymbolMapping,
    SymbolMapService,
)


# ---------------------------------------------------------------------------
# TestProviderSymbolMappingModel
# ---------------------------------------------------------------------------

class TestProviderSymbolMappingModel:
    def test_valid_mapping(self) -> None:
        m = ProviderSymbolMapping(
            internal_symbol="MAYBANK",
            provider="yahoo",
            provider_symbol="1155.KL",
        )
        assert m.internal_symbol == "MAYBANK"
        assert m.provider == "yahoo"
        assert m.provider_symbol == "1155.KL"

    def test_provider_normalised_to_lowercase(self) -> None:
        m = ProviderSymbolMapping(
            internal_symbol="AAPL",
            provider="YAHOO",
            provider_symbol="AAPL",
        )
        assert m.provider == "yahoo"

    def test_whitespace_stripped(self) -> None:
        m = ProviderSymbolMapping(
            internal_symbol="  AAPL  ",
            provider="  yahoo  ",
            provider_symbol="  AAPL  ",
        )
        assert m.internal_symbol == "AAPL"
        assert m.provider == "yahoo"
        assert m.provider_symbol == "AAPL"

    def test_empty_internal_symbol_raises(self) -> None:
        with pytest.raises(Exception):
            ProviderSymbolMapping(
                internal_symbol="",
                provider="yahoo",
                provider_symbol="AAPL",
            )

    def test_empty_provider_raises(self) -> None:
        with pytest.raises(Exception):
            ProviderSymbolMapping(
                internal_symbol="AAPL",
                provider="",
                provider_symbol="AAPL",
            )

    def test_frozen(self) -> None:
        m = ProviderSymbolMapping(
            internal_symbol="AAPL",
            provider="yahoo",
            provider_symbol="AAPL",
        )
        with pytest.raises(Exception):
            m.internal_symbol = "CHANGED"  # type: ignore[misc]

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(Exception):
            ProviderSymbolMapping(  # type: ignore[call-arg]
                internal_symbol="AAPL",
                provider="yahoo",
                provider_symbol="AAPL",
                unknown_field="x",
            )


# ---------------------------------------------------------------------------
# TestSymbolMapServiceResolve
# ---------------------------------------------------------------------------

class TestSymbolMapServiceResolve:
    def test_identity_fallback_when_no_mapping(self) -> None:
        svc = SymbolMapService()
        assert svc.resolve("AAPL", "yahoo") == "AAPL"

    def test_resolve_explicit_mapping(self) -> None:
        svc = SymbolMapService()
        svc.add_mapping(
            ProviderSymbolMapping(
                internal_symbol="MAYBANK",
                provider="yahoo",
                provider_symbol="1155.KL",
            )
        )
        assert svc.resolve("MAYBANK", "yahoo") == "1155.KL"

    def test_resolve_is_case_insensitive_on_symbol(self) -> None:
        svc = SymbolMapService()
        svc.add_mapping(
            ProviderSymbolMapping(
                internal_symbol="maybank",
                provider="yahoo",
                provider_symbol="1155.KL",
            )
        )
        assert svc.resolve("MAYBANK", "yahoo") == "1155.KL"
        assert svc.resolve("maybank", "yahoo") == "1155.KL"

    def test_resolve_is_case_insensitive_on_provider(self) -> None:
        svc = SymbolMapService()
        svc.add_mapping(
            ProviderSymbolMapping(
                internal_symbol="AAPL",
                provider="YAHOO",
                provider_symbol="AAPL",
            )
        )
        assert svc.resolve("AAPL", "yahoo") == "AAPL"
        assert svc.resolve("AAPL", "YAHOO") == "AAPL"

    def test_resolve_strips_whitespace_on_symbol_and_provider(self) -> None:
        svc = SymbolMapService()
        svc.add_mapping(
            ProviderSymbolMapping(
                internal_symbol="MAYBANK",
                provider="yahoo",
                provider_symbol="1155.KL",
            )
        )
        assert svc.resolve("  MAYBANK  ", "  YAHOO  ") == "1155.KL"

    def test_different_providers_independent(self) -> None:
        svc = SymbolMapService()
        svc.add_mapping(
            ProviderSymbolMapping(
                internal_symbol="MAYBANK",
                provider="yahoo",
                provider_symbol="1155.KL",
            )
        )
        # Polygon has no mapping → identity fallback
        assert svc.resolve("MAYBANK", "polygon") == "MAYBANK"

    def test_resolve_unchanged_when_no_mapping_for_provider(self) -> None:
        svc = SymbolMapService()
        svc.add_mapping(
            ProviderSymbolMapping(
                internal_symbol="AAPL",
                provider="yahoo",
                provider_symbol="AAPL",
            )
        )
        # Different symbol, same provider → identity fallback
        assert svc.resolve("MSFT", "yahoo") == "MSFT"


# ---------------------------------------------------------------------------
# TestSymbolMapServiceAddRemove
# ---------------------------------------------------------------------------

class TestSymbolMapServiceAddRemove:
    def test_duplicate_mapping_raises(self) -> None:
        svc = SymbolMapService()
        mapping = ProviderSymbolMapping(
            internal_symbol="MAYBANK",
            provider="yahoo",
            provider_symbol="1155.KL",
        )
        svc.add_mapping(mapping)
        with pytest.raises(ProviderSymbolMapError, match="already exists"):
            svc.add_mapping(mapping)

    def test_remove_mapping(self) -> None:
        svc = SymbolMapService()
        svc.add_mapping(
            ProviderSymbolMapping(
                internal_symbol="MAYBANK",
                provider="yahoo",
                provider_symbol="1155.KL",
            )
        )
        svc.remove_mapping("MAYBANK", "yahoo")
        # Should fall back to identity after removal
        assert svc.resolve("MAYBANK", "yahoo") == "MAYBANK"

    def test_remove_nonexistent_raises(self) -> None:
        svc = SymbolMapService()
        with pytest.raises(ProviderSymbolMapError, match="No mapping"):
            svc.remove_mapping("AAPL", "yahoo")

    def test_remove_strips_whitespace(self) -> None:
        svc = SymbolMapService()
        svc.add_mapping(
            ProviderSymbolMapping(
                internal_symbol="MAYBANK",
                provider="yahoo",
                provider_symbol="1155.KL",
            )
        )
        svc.remove_mapping("  MAYBANK  ", "  yahoo  ")
        assert svc.resolve("MAYBANK", "yahoo") == "MAYBANK"

    def test_has_mapping_true(self) -> None:
        svc = SymbolMapService()
        svc.add_mapping(
            ProviderSymbolMapping(
                internal_symbol="AAPL",
                provider="yahoo",
                provider_symbol="AAPL",
            )
        )
        assert svc.has_mapping("AAPL", "yahoo") is True

    def test_has_mapping_false(self) -> None:
        svc = SymbolMapService()
        assert svc.has_mapping("AAPL", "yahoo") is False

    def test_has_mapping_strips_whitespace(self) -> None:
        svc = SymbolMapService()
        svc.add_mapping(
            ProviderSymbolMapping(
                internal_symbol="AAPL",
                provider="yahoo",
                provider_symbol="AAPL",
            )
        )
        assert svc.has_mapping("  AAPL  ", "  yahoo  ") is True


# ---------------------------------------------------------------------------
# TestSymbolMapServiceListMappings
# ---------------------------------------------------------------------------

class TestSymbolMapServiceListMappings:
    def test_list_empty(self) -> None:
        svc = SymbolMapService()
        assert svc.list_mappings() == []

    def test_list_all(self) -> None:
        svc = SymbolMapService()
        svc.add_mapping(
            ProviderSymbolMapping(internal_symbol="MAYBANK", provider="yahoo", provider_symbol="1155.KL")
        )
        svc.add_mapping(
            ProviderSymbolMapping(internal_symbol="CIMB", provider="yahoo", provider_symbol="1023.KL")
        )
        result = svc.list_mappings()
        assert len(result) == 2

    def test_list_filtered_by_provider(self) -> None:
        svc = SymbolMapService()
        svc.add_mapping(
            ProviderSymbolMapping(internal_symbol="AAPL", provider="yahoo", provider_symbol="AAPL")
        )
        svc.add_mapping(
            ProviderSymbolMapping(internal_symbol="AAPL", provider="polygon", provider_symbol="AAPL")
        )
        yahoo_only = svc.list_mappings(provider="yahoo")
        assert len(yahoo_only) == 1
        assert yahoo_only[0].provider == "yahoo"

    def test_list_filtered_by_provider_strips_whitespace(self) -> None:
        svc = SymbolMapService()
        svc.add_mapping(
            ProviderSymbolMapping(internal_symbol="AAPL", provider="yahoo", provider_symbol="AAPL")
        )
        yahoo_only = svc.list_mappings(provider="  yahoo  ")
        assert len(yahoo_only) == 1
