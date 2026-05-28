"""
Tests for DatasetCatalog, catalog_service, and catalog routes.

Covers:
  - LocalDatasetEntry construction and immutability
  - DatasetCatalog: register, get, list, disable, remove, persistence, duplicates
  - catalog_service: register_dataset, list_datasets, get_dataset, remove_dataset, fetch_ohlcv
  - Catalog HTTP routes (via TestClient): POST/GET/DELETE /catalog/datasets, GET .../ohlcv
  - File path isolation: file_path absent from all service/route response objects
  - Architecture: file_path never in CatalogEntryResponse / RegisterDatasetResponse
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.storage.dataset_catalog import (
    DatasetCatalog,
    DatasetCatalogError,
    DatasetDisabledError,
    DuplicateDatasetError,
    LocalDatasetEntry,
    UnknownDatasetError,
)
from backend.api.schemas.catalog import (
    CatalogEntryResponse,
    CatalogListResponse,
    CatalogOHLCVCandle,
    CatalogOHLCVResponse,
    RegisterDatasetRequest,
    RegisterDatasetResponse,
)
from backend.api.services.catalog_service import (
    CatalogDatasetDisabledError,
    CatalogFetchError,
    CatalogNotFoundError,
    CatalogRegistrationError,
    fetch_ohlcv,
    get_dataset,
    list_datasets,
    register_dataset,
    remove_dataset,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(**overrides: Any) -> LocalDatasetEntry:
    defaults: dict[str, Any] = {
        "catalog_id": "abc-123",
        "provider_type": "csv",
        "file_path": "/data/aapl.csv",
        "display_name": "AAPL Daily",
        "dataset_type": "ohlcv",
        "asset_class": "equity",
        "timeframe": "1d",
        "symbol": "AAPL",
        "venue": "NASDAQ",
        "adjustment_mode": "adjusted",
        "registered_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "enabled": True,
    }
    defaults.update(overrides)
    return LocalDatasetEntry(**defaults)


def _make_register_request(tmp_file: Path, **overrides: Any) -> RegisterDatasetRequest:
    defaults: dict[str, Any] = {
        "provider_type": "csv",
        "file_path": str(tmp_file),
        "display_name": "AAPL Daily",
        "symbol": "AAPL",
        "asset_class": "equity",
        "venue": "NASDAQ",
        "timeframe": "1d",
    }
    defaults.update(overrides)
    return RegisterDatasetRequest(**defaults)


# ---------------------------------------------------------------------------
# TestLocalDatasetEntry
# ---------------------------------------------------------------------------

class TestLocalDatasetEntry:
    def test_construction(self) -> None:
        entry = _make_entry()
        assert entry.catalog_id == "abc-123"
        assert entry.provider_type == "csv"
        assert entry.file_path == "/data/aapl.csv"
        assert entry.display_name == "AAPL Daily"
        assert entry.enabled is True

    def test_immutable(self) -> None:
        entry = _make_entry()
        with pytest.raises(Exception):
            entry.catalog_id = "other"  # type: ignore[misc]

    def test_default_enabled_true(self) -> None:
        entry = _make_entry()
        assert entry.enabled is True

    def test_metadata_optional(self) -> None:
        entry = _make_entry(metadata=None)
        assert entry.metadata is None

    def test_metadata_stored(self) -> None:
        entry = _make_entry(metadata={"source": "bloomberg"})
        assert entry.metadata == {"source": "bloomberg"}


# ---------------------------------------------------------------------------
# TestDatasetCatalogRegistration
# ---------------------------------------------------------------------------

class TestDatasetCatalogRegistration:
    def test_register_returns_entry(self, tmp_path: Path, tmp_csv: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        entry = catalog.register(
            provider_type="csv",
            file_path=str(tmp_csv),
            display_name="Test",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        assert entry.catalog_id
        assert entry.provider_type == "csv"

    def test_register_creates_catalog_file(self, tmp_path: Path, tmp_csv: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        catalog.register(
            provider_type="csv",
            file_path=str(tmp_csv),
            display_name="Test",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        assert (tmp_path / "catalog" / "datasets.json").exists()

    def test_register_symbol_uppercased(self, tmp_path: Path, tmp_csv: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        entry = catalog.register(
            provider_type="csv",
            file_path=str(tmp_csv),
            display_name="Test",
            symbol="aapl",
            asset_class="equity",
            venue="nasdaq",
            timeframe="1d",
        )
        assert entry.symbol == "AAPL"
        assert entry.venue == "NASDAQ"

    def test_register_provider_type_lowercased(self, tmp_path: Path, tmp_csv: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        entry = catalog.register(
            provider_type="CSV",
            file_path=str(tmp_csv),
            display_name="Test",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        assert entry.provider_type == "csv"

    def test_register_duplicate_file_path_raises(
        self, tmp_path: Path, tmp_csv: Path
    ) -> None:
        catalog = DatasetCatalog(tmp_path)
        catalog.register(
            provider_type="csv",
            file_path=str(tmp_csv),
            display_name="First",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        with pytest.raises(DuplicateDatasetError):
            catalog.register(
                provider_type="csv",
                file_path=str(tmp_csv),
                display_name="Second",
                symbol="AAPL",
                asset_class="equity",
                venue="NASDAQ",
                timeframe="1d",
            )

    def test_register_allow_duplicate_path_flag(
        self, tmp_path: Path, tmp_csv: Path
    ) -> None:
        catalog = DatasetCatalog(tmp_path)
        catalog.register(
            provider_type="csv",
            file_path=str(tmp_csv),
            display_name="First",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        entry2 = catalog.register(
            provider_type="csv",
            file_path=str(tmp_csv),
            display_name="Second",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
            allow_duplicate_path=True,
        )
        assert entry2.display_name == "Second"

    def test_register_empty_symbol_raises(self, tmp_path: Path, tmp_csv: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        with pytest.raises(ValueError, match="symbol"):
            catalog.register(
                provider_type="csv",
                file_path=str(tmp_csv),
                display_name="Test",
                symbol="",
                asset_class="equity",
                venue="NASDAQ",
                timeframe="1d",
            )

    def test_register_assigns_unique_catalog_ids(
        self, tmp_path: Path, tmp_csv: Path, tmp_csv2: Path
    ) -> None:
        catalog = DatasetCatalog(tmp_path)
        e1 = catalog.register(
            provider_type="csv", file_path=str(tmp_csv), display_name="A",
            symbol="AAPL", asset_class="equity", venue="NYSE", timeframe="1d",
        )
        e2 = catalog.register(
            provider_type="csv", file_path=str(tmp_csv2), display_name="B",
            symbol="MSFT", asset_class="equity", venue="NASDAQ", timeframe="1d",
        )
        assert e1.catalog_id != e2.catalog_id


# ---------------------------------------------------------------------------
# TestDatasetCatalogGet
# ---------------------------------------------------------------------------

class TestDatasetCatalogGet:
    def test_get_registered_entry(self, tmp_path: Path, tmp_csv: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        registered = catalog.register(
            provider_type="csv",
            file_path=str(tmp_csv),
            display_name="AAPL",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        fetched = catalog.get(registered.catalog_id)
        assert fetched.catalog_id == registered.catalog_id
        assert fetched.file_path == str(tmp_csv)

    def test_get_unknown_raises(self, tmp_path: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        with pytest.raises(UnknownDatasetError):
            catalog.get("nonexistent-id")

    def test_get_disabled_raises_dataset_disabled_error(
        self, tmp_path: Path, tmp_csv: Path
    ) -> None:
        catalog = DatasetCatalog(tmp_path)
        entry = catalog.register(
            provider_type="csv",
            file_path=str(tmp_csv),
            display_name="AAPL",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        catalog.disable(entry.catalog_id)
        with pytest.raises(DatasetDisabledError):
            catalog.get(entry.catalog_id)

    def test_get_any_returns_disabled_entry(self, tmp_path: Path, tmp_csv: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        entry = catalog.register(
            provider_type="csv",
            file_path=str(tmp_csv),
            display_name="AAPL",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        catalog.disable(entry.catalog_id)
        fetched = catalog.get_any(entry.catalog_id)
        assert fetched.enabled is False


# ---------------------------------------------------------------------------
# TestDatasetCatalogList
# ---------------------------------------------------------------------------

class TestDatasetCatalogList:
    def test_list_all_empty(self, tmp_path: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        assert catalog.list_all() == []

    def test_list_all_returns_all(
        self, tmp_path: Path, tmp_csv: Path, tmp_csv2: Path
    ) -> None:
        catalog = DatasetCatalog(tmp_path)
        catalog.register(
            provider_type="csv", file_path=str(tmp_csv), display_name="A",
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d",
        )
        catalog.register(
            provider_type="csv", file_path=str(tmp_csv2), display_name="B",
            symbol="MSFT", asset_class="equity", venue="NASDAQ", timeframe="1d",
        )
        assert len(catalog.list_all()) == 2

    def test_list_enabled_excludes_disabled(
        self, tmp_path: Path, tmp_csv: Path, tmp_csv2: Path
    ) -> None:
        catalog = DatasetCatalog(tmp_path)
        e1 = catalog.register(
            provider_type="csv", file_path=str(tmp_csv), display_name="A",
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d",
        )
        catalog.register(
            provider_type="csv", file_path=str(tmp_csv2), display_name="B",
            symbol="MSFT", asset_class="equity", venue="NASDAQ", timeframe="1d",
        )
        catalog.disable(e1.catalog_id)
        enabled = catalog.list_enabled()
        assert len(enabled) == 1
        assert enabled[0].symbol == "MSFT"

    def test_list_all_includes_disabled(
        self, tmp_path: Path, tmp_csv: Path
    ) -> None:
        catalog = DatasetCatalog(tmp_path)
        entry = catalog.register(
            provider_type="csv", file_path=str(tmp_csv), display_name="A",
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d",
        )
        catalog.disable(entry.catalog_id)
        all_entries = catalog.list_all()
        assert len(all_entries) == 1
        assert all_entries[0].enabled is False


# ---------------------------------------------------------------------------
# TestDatasetCatalogDisableRemove
# ---------------------------------------------------------------------------

class TestDatasetCatalogDisableRemove:
    def test_disable_unknown_raises(self, tmp_path: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        with pytest.raises(UnknownDatasetError):
            catalog.disable("no-such-id")

    def test_disable_returns_updated_entry(self, tmp_path: Path, tmp_csv: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        entry = catalog.register(
            provider_type="csv", file_path=str(tmp_csv), display_name="A",
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d",
        )
        updated = catalog.disable(entry.catalog_id)
        assert updated.enabled is False

    def test_remove_unknown_raises(self, tmp_path: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        with pytest.raises(UnknownDatasetError):
            catalog.remove("no-such-id")

    def test_remove_then_not_in_catalog(self, tmp_path: Path, tmp_csv: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        entry = catalog.register(
            provider_type="csv", file_path=str(tmp_csv), display_name="A",
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d",
        )
        catalog.remove(entry.catalog_id)
        assert entry.catalog_id not in catalog

    def test_remove_reduces_len(self, tmp_path: Path, tmp_csv: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        entry = catalog.register(
            provider_type="csv", file_path=str(tmp_csv), display_name="A",
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d",
        )
        assert len(catalog) == 1
        catalog.remove(entry.catalog_id)
        assert len(catalog) == 0


# ---------------------------------------------------------------------------
# TestDatasetCatalogPersistence
# ---------------------------------------------------------------------------

class TestDatasetCatalogPersistence:
    def test_entries_survive_new_catalog_instance(
        self, tmp_path: Path, tmp_csv: Path
    ) -> None:
        catalog1 = DatasetCatalog(tmp_path)
        entry = catalog1.register(
            provider_type="csv", file_path=str(tmp_csv), display_name="A",
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d",
        )
        catalog2 = DatasetCatalog(tmp_path)
        fetched = catalog2.get(entry.catalog_id)
        assert fetched.catalog_id == entry.catalog_id
        assert fetched.file_path == str(tmp_csv)

    def test_json_file_does_not_expose_file_path_in_list_response(
        self, tmp_path: Path, tmp_csv: Path
    ) -> None:
        catalog = DatasetCatalog(tmp_path)
        catalog.register(
            provider_type="csv", file_path=str(tmp_csv), display_name="A",
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d",
        )
        response = list_datasets(tmp_path)
        for entry_resp in response.entries:
            assert not hasattr(entry_resp, "file_path") or entry_resp.__dict__.get("file_path") is None  # type: ignore[attr-defined]

    def test_contains_operator(self, tmp_path: Path, tmp_csv: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        entry = catalog.register(
            provider_type="csv", file_path=str(tmp_csv), display_name="A",
            symbol="AAPL", asset_class="equity", venue="NASDAQ", timeframe="1d",
        )
        assert entry.catalog_id in catalog

    def test_contains_missing_returns_false(self, tmp_path: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        assert "missing-id" not in catalog

    def test_non_string_contains_false(self, tmp_path: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        assert 42 not in catalog  # type: ignore[operator]

    def test_empty_catalog_no_file(self, tmp_path: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        assert catalog.list_all() == []
        assert not (tmp_path / "catalog" / "datasets.json").exists()


# ---------------------------------------------------------------------------
# TestCatalogServiceRegister
# ---------------------------------------------------------------------------

class TestCatalogServiceRegister:
    def test_register_file_not_found_raises(self, tmp_path: Path) -> None:
        request = RegisterDatasetRequest(
            provider_type="csv",
            file_path="/nonexistent/path/file.csv",
            display_name="Test",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        with pytest.raises(CatalogRegistrationError, match="not found"):
            register_dataset(request, tmp_path)

    def test_register_returns_no_file_path(self, tmp_path: Path, tmp_csv: Path) -> None:
        request = _make_register_request(tmp_csv)
        response = register_dataset(request, tmp_path)
        assert isinstance(response, RegisterDatasetResponse)
        assert not hasattr(response, "file_path")

    def test_register_response_has_catalog_id(self, tmp_path: Path, tmp_csv: Path) -> None:
        request = _make_register_request(tmp_csv)
        response = register_dataset(request, tmp_path)
        assert response.catalog_id

    def test_register_duplicate_raises(self, tmp_path: Path, tmp_csv: Path) -> None:
        request = _make_register_request(tmp_csv)
        register_dataset(request, tmp_path)
        with pytest.raises(CatalogRegistrationError):
            register_dataset(request, tmp_path)

    def test_register_directory_path_raises(self, tmp_path: Path) -> None:
        request = RegisterDatasetRequest(
            provider_type="csv",
            file_path=str(tmp_path),
            display_name="Test",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        with pytest.raises(CatalogRegistrationError):
            register_dataset(request, tmp_path)


# ---------------------------------------------------------------------------
# TestCatalogServiceList
# ---------------------------------------------------------------------------

class TestCatalogServiceList:
    def test_list_empty(self, tmp_path: Path) -> None:
        result = list_datasets(tmp_path)
        assert result.entries == []
        assert result.count == 0

    def test_list_returns_registered_entries(
        self, tmp_path: Path, tmp_csv: Path
    ) -> None:
        request = _make_register_request(tmp_csv)
        register_dataset(request, tmp_path)
        result = list_datasets(tmp_path)
        assert result.count == 1
        assert result.entries[0].symbol == "AAPL"

    def test_list_excludes_disabled_by_default(
        self, tmp_path: Path, tmp_csv: Path
    ) -> None:
        request = _make_register_request(tmp_csv)
        response = register_dataset(request, tmp_path)
        from backend.storage.dataset_catalog import DatasetCatalog
        DatasetCatalog(tmp_path).disable(response.catalog_id)
        result = list_datasets(tmp_path)
        assert result.count == 0

    def test_list_include_disabled_flag(
        self, tmp_path: Path, tmp_csv: Path
    ) -> None:
        request = _make_register_request(tmp_csv)
        response = register_dataset(request, tmp_path)
        from backend.storage.dataset_catalog import DatasetCatalog
        DatasetCatalog(tmp_path).disable(response.catalog_id)
        result = list_datasets(tmp_path, include_disabled=True)
        assert result.count == 1

    def test_list_entries_have_no_file_path_field(
        self, tmp_path: Path, tmp_csv: Path
    ) -> None:
        register_dataset(_make_register_request(tmp_csv), tmp_path)
        result = list_datasets(tmp_path)
        assert "file_path" not in CatalogEntryResponse.model_fields


# ---------------------------------------------------------------------------
# TestCatalogServiceGetRemove
# ---------------------------------------------------------------------------

class TestCatalogServiceGetRemove:
    def test_get_unknown_raises(self, tmp_path: Path) -> None:
        with pytest.raises(CatalogNotFoundError):
            get_dataset("nonexistent", tmp_path)

    def test_get_disabled_raises(self, tmp_path: Path, tmp_csv: Path) -> None:
        response = register_dataset(_make_register_request(tmp_csv), tmp_path)
        from backend.storage.dataset_catalog import DatasetCatalog
        DatasetCatalog(tmp_path).disable(response.catalog_id)
        with pytest.raises(CatalogDatasetDisabledError):
            get_dataset(response.catalog_id, tmp_path)

    def test_get_returns_entry_response(self, tmp_path: Path, tmp_csv: Path) -> None:
        response = register_dataset(_make_register_request(tmp_csv), tmp_path)
        entry_resp = get_dataset(response.catalog_id, tmp_path)
        assert isinstance(entry_resp, CatalogEntryResponse)
        assert entry_resp.catalog_id == response.catalog_id

    def test_get_response_no_file_path(self, tmp_path: Path, tmp_csv: Path) -> None:
        register_dataset(_make_register_request(tmp_csv), tmp_path)
        assert "file_path" not in CatalogEntryResponse.model_fields

    def test_remove_unknown_raises(self, tmp_path: Path) -> None:
        with pytest.raises(CatalogNotFoundError):
            remove_dataset("nonexistent", tmp_path)

    def test_remove_then_get_raises(self, tmp_path: Path, tmp_csv: Path) -> None:
        response = register_dataset(_make_register_request(tmp_csv), tmp_path)
        remove_dataset(response.catalog_id, tmp_path)
        with pytest.raises(CatalogNotFoundError):
            get_dataset(response.catalog_id, tmp_path)


# ---------------------------------------------------------------------------
# TestCatalogServiceFetchOHLCV
# ---------------------------------------------------------------------------

class TestCatalogServiceFetchOHLCV:
    def test_fetch_unknown_raises_catalog_not_found(self, tmp_path: Path) -> None:
        from backend.data_providers.provider_factory import create_default_factory_registry
        factory = create_default_factory_registry()
        with pytest.raises(CatalogNotFoundError):
            fetch_ohlcv(
                catalog_id="nonexistent",
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2024, 1, 31, tzinfo=timezone.utc),
                base_path=tmp_path,
                factory=factory,
            )

    def test_fetch_disabled_raises_catalog_disabled(
        self, tmp_path: Path, tmp_csv: Path
    ) -> None:
        from backend.data_providers.provider_factory import create_default_factory_registry
        factory = create_default_factory_registry()
        response = register_dataset(_make_register_request(tmp_csv), tmp_path)
        from backend.storage.dataset_catalog import DatasetCatalog
        DatasetCatalog(tmp_path).disable(response.catalog_id)
        with pytest.raises(CatalogDatasetDisabledError):
            fetch_ohlcv(
                catalog_id=response.catalog_id,
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2024, 1, 31, tzinfo=timezone.utc),
                base_path=tmp_path,
                factory=factory,
            )

    def test_fetch_returns_ohlcv_response(
        self, tmp_path: Path, tmp_csv_with_data: Path
    ) -> None:
        from backend.data_providers.provider_factory import create_default_factory_registry
        factory = create_default_factory_registry()
        request = RegisterDatasetRequest(
            provider_type="csv",
            file_path=str(tmp_csv_with_data),
            display_name="AAPL Daily",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        reg_resp = register_dataset(request, tmp_path)
        result = fetch_ohlcv(
            catalog_id=reg_resp.catalog_id,
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 12, 31, tzinfo=timezone.utc),
            base_path=tmp_path,
            factory=factory,
        )
        assert isinstance(result, CatalogOHLCVResponse)
        assert result.catalog_id == reg_resp.catalog_id
        assert result.candle_count >= 1

    def test_fetch_response_no_file_path(
        self, tmp_path: Path, tmp_csv_with_data: Path
    ) -> None:
        assert "file_path" not in CatalogOHLCVResponse.model_fields

    def test_fetch_naive_datetimes_treated_as_utc(
        self, tmp_path: Path, tmp_csv_with_data: Path
    ) -> None:
        from backend.data_providers.provider_factory import create_default_factory_registry
        factory = create_default_factory_registry()
        request = RegisterDatasetRequest(
            provider_type="csv",
            file_path=str(tmp_csv_with_data),
            display_name="AAPL Daily",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        reg_resp = register_dataset(request, tmp_path)
        # naive datetimes should not raise
        result = fetch_ohlcv(
            catalog_id=reg_resp.catalog_id,
            start=datetime(2024, 1, 1),  # naive
            end=datetime(2024, 12, 31),  # naive
            base_path=tmp_path,
            factory=factory,
        )
        assert isinstance(result, CatalogOHLCVResponse)


# ---------------------------------------------------------------------------
# TestCatalogRoutes (HTTP)
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_client(tmp_path: Path) -> TestClient:
    from backend.api.main import app
    from backend.api.routes.catalog import get_storage_path, get_provider_factory
    from backend.auth.dependencies import get_current_user
    from backend.auth.models import User
    from backend.data_providers.provider_factory import create_default_factory_registry

    _test_user = User(
        user_id="test-user-id",
        username="testuser",
        email="test@example.com",
        password_hash="hash",
        created_at="2026-01-01T00:00:00+00:00",
        subscription_status="active",
    )

    app.dependency_overrides[get_storage_path] = lambda: tmp_path
    app.dependency_overrides[get_provider_factory] = create_default_factory_registry
    app.dependency_overrides[get_current_user] = lambda: _test_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestCatalogHTTPRegister:
    def test_post_register_201(self, test_client: TestClient, tmp_csv: Path) -> None:
        resp = test_client.post(
            "/catalog/datasets",
            json={
                "provider_type": "csv",
                "file_path": str(tmp_csv),
                "display_name": "AAPL Daily",
                "symbol": "AAPL",
                "asset_class": "equity",
                "venue": "NASDAQ",
                "timeframe": "1d",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "catalog_id" in data
        assert "file_path" not in data

    def test_post_register_file_not_found_400(self, test_client: TestClient) -> None:
        resp = test_client.post(
            "/catalog/datasets",
            json={
                "provider_type": "csv",
                "file_path": "/no/such/file.csv",
                "display_name": "X",
                "symbol": "X",
                "asset_class": "equity",
                "venue": "NYSE",
                "timeframe": "1d",
            },
        )
        assert resp.status_code == 400

    def test_post_register_duplicate_400(self, test_client: TestClient, tmp_csv: Path) -> None:
        payload = {
            "provider_type": "csv",
            "file_path": str(tmp_csv),
            "display_name": "AAPL",
            "symbol": "AAPL",
            "asset_class": "equity",
            "venue": "NASDAQ",
            "timeframe": "1d",
        }
        test_client.post("/catalog/datasets", json=payload)
        resp = test_client.post("/catalog/datasets", json=payload)
        assert resp.status_code == 400


class TestCatalogHTTPList:
    def test_get_list_empty_200(self, test_client: TestClient) -> None:
        resp = test_client.get("/catalog/datasets")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["entries"] == []

    def test_get_list_after_register(self, test_client: TestClient, tmp_csv: Path) -> None:
        test_client.post(
            "/catalog/datasets",
            json={
                "provider_type": "csv",
                "file_path": str(tmp_csv),
                "display_name": "AAPL",
                "symbol": "AAPL",
                "asset_class": "equity",
                "venue": "NASDAQ",
                "timeframe": "1d",
            },
        )
        resp = test_client.get("/catalog/datasets")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_list_entries_no_file_path(self, test_client: TestClient, tmp_csv: Path) -> None:
        test_client.post(
            "/catalog/datasets",
            json={
                "provider_type": "csv",
                "file_path": str(tmp_csv),
                "display_name": "AAPL",
                "symbol": "AAPL",
                "asset_class": "equity",
                "venue": "NASDAQ",
                "timeframe": "1d",
            },
        )
        resp = test_client.get("/catalog/datasets")
        for entry in resp.json()["entries"]:
            assert "file_path" not in entry


class TestCatalogHTTPGetDelete:
    def test_get_single_200(self, test_client: TestClient, tmp_csv: Path) -> None:
        reg = test_client.post(
            "/catalog/datasets",
            json={
                "provider_type": "csv",
                "file_path": str(tmp_csv),
                "display_name": "AAPL",
                "symbol": "AAPL",
                "asset_class": "equity",
                "venue": "NASDAQ",
                "timeframe": "1d",
            },
        ).json()
        resp = test_client.get(f"/catalog/datasets/{reg['catalog_id']}")
        assert resp.status_code == 200
        assert resp.json()["catalog_id"] == reg["catalog_id"]
        assert "file_path" not in resp.json()

    def test_get_unknown_404(self, test_client: TestClient) -> None:
        resp = test_client.get("/catalog/datasets/no-such-id")
        assert resp.status_code == 404

    def test_delete_204(self, test_client: TestClient, tmp_csv: Path) -> None:
        reg = test_client.post(
            "/catalog/datasets",
            json={
                "provider_type": "csv",
                "file_path": str(tmp_csv),
                "display_name": "AAPL",
                "symbol": "AAPL",
                "asset_class": "equity",
                "venue": "NASDAQ",
                "timeframe": "1d",
            },
        ).json()
        resp = test_client.delete(f"/catalog/datasets/{reg['catalog_id']}")
        assert resp.status_code == 204

    def test_delete_then_get_404(self, test_client: TestClient, tmp_csv: Path) -> None:
        reg = test_client.post(
            "/catalog/datasets",
            json={
                "provider_type": "csv",
                "file_path": str(tmp_csv),
                "display_name": "AAPL",
                "symbol": "AAPL",
                "asset_class": "equity",
                "venue": "NASDAQ",
                "timeframe": "1d",
            },
        ).json()
        test_client.delete(f"/catalog/datasets/{reg['catalog_id']}")
        resp = test_client.get(f"/catalog/datasets/{reg['catalog_id']}")
        assert resp.status_code == 404

    def test_delete_unknown_404(self, test_client: TestClient) -> None:
        resp = test_client.delete("/catalog/datasets/no-such-id")
        assert resp.status_code == 404


class TestCatalogHTTPOHLCV:
    def test_ohlcv_unknown_catalog_id_404(self, test_client: TestClient) -> None:
        resp = test_client.get(
            "/catalog/datasets/no-such-id/ohlcv",
            params={"start": "2024-01-01T00:00:00Z", "end": "2024-12-31T00:00:00Z"},
        )
        assert resp.status_code == 404

    def test_ohlcv_returns_candles(
        self, test_client: TestClient, tmp_csv_with_data: Path
    ) -> None:
        reg = test_client.post(
            "/catalog/datasets",
            json={
                "provider_type": "csv",
                "file_path": str(tmp_csv_with_data),
                "display_name": "AAPL Daily",
                "symbol": "AAPL",
                "asset_class": "equity",
                "venue": "NASDAQ",
                "timeframe": "1d",
            },
        ).json()
        resp = test_client.get(
            f"/catalog/datasets/{reg['catalog_id']}/ohlcv",
            params={"start": "2024-01-01T00:00:00Z", "end": "2024-12-31T00:00:00Z"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "candles" in data
        assert data["candle_count"] >= 1
        assert "file_path" not in data

    def test_ohlcv_response_no_file_path(
        self, test_client: TestClient, tmp_csv_with_data: Path
    ) -> None:
        reg = test_client.post(
            "/catalog/datasets",
            json={
                "provider_type": "csv",
                "file_path": str(tmp_csv_with_data),
                "display_name": "AAPL Daily",
                "symbol": "AAPL",
                "asset_class": "equity",
                "venue": "NASDAQ",
                "timeframe": "1d",
            },
        ).json()
        resp = test_client.get(
            f"/catalog/datasets/{reg['catalog_id']}/ohlcv",
            params={"start": "2024-01-01T00:00:00Z", "end": "2024-12-31T00:00:00Z"},
        )
        assert "file_path" not in resp.json()


# ---------------------------------------------------------------------------
# TestFilePathIsolation — explicit architecture boundary enforcement
# ---------------------------------------------------------------------------

class TestFilePathIsolation:
    def test_catalog_entry_response_has_no_file_path_field(self) -> None:
        assert "file_path" not in CatalogEntryResponse.model_fields

    def test_register_dataset_response_has_no_file_path_field(self) -> None:
        assert "file_path" not in RegisterDatasetResponse.model_fields

    def test_catalog_ohlcv_response_has_no_file_path_field(self) -> None:
        assert "file_path" not in CatalogOHLCVResponse.model_fields

    def test_catalog_list_response_has_no_file_path_field(self) -> None:
        assert "file_path" not in CatalogListResponse.model_fields

    def test_catalog_service_does_not_import_yahoo_adapter(self) -> None:
        import ast
        import pathlib
        src = pathlib.Path("backend/api/services/catalog_service.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = ""
                if isinstance(node, ast.ImportFrom) and node.module:
                    module = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name
                assert "data_providers.yahoo" not in module, (
                    f"catalog_service must not import from data_providers.yahoo; found: {module}"
                )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_csv(tmp_path: Path) -> Path:
    """An empty but existing CSV file (for registration tests that don't read data)."""
    p = tmp_path / "empty.csv"
    p.write_text("timestamp,open,high,low,close,volume\n")
    return p


@pytest.fixture()
def tmp_csv2(tmp_path: Path) -> Path:
    p = tmp_path / "empty2.csv"
    p.write_text("timestamp,open,high,low,close,volume\n")
    return p


@pytest.fixture()
def tmp_csv_with_data(tmp_path: Path) -> Path:
    """A CSV file with 3 valid OHLCV rows for AAPL."""
    p = tmp_path / "aapl_1d.csv"
    p.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2024-01-02,185.0,186.5,184.2,185.9,55000000\n"
        "2024-01-03,185.9,187.0,185.1,186.5,48000000\n"
        "2024-01-04,186.5,188.0,186.0,187.1,62000000\n"
    )
    return p
