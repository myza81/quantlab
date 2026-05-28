"""
Phase 3L — User Ownership & Resource Scoping tests.

Covers:
  1. TestDraftRepositoryOwnership   — repository-level ownership enforcement
  2. TestDraftServiceOwnership      — service-layer ownership enforcement
  3. TestCatalogOwnership           — DatasetCatalog ownership enforcement
  4. TestDraftRouteOwnership        — HTTP route auth + ownership (TestClient)
  5. TestCatalogRouteOwnership      — HTTP route auth + ownership (TestClient)
  6. TestBacktestOwnership          — backtest run ownership enforcement
  7. TestGlobalRouteStillPublic     — system routes remain unauthenticated
  8. TestLegacyResourceBehavior     — legacy (user_id=None) resource behavior
  9. TestProviderCredentialsUnaffected — vault routes unaffected by Phase 3L
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.routes.catalog import get_storage_path, get_provider_factory
from backend.api.routes.drafts import get_draft_repository
from backend.api.services.catalog_service import CatalogNotFoundError
from backend.api.services.draft_service import (
    create_draft as svc_create_draft,
    delete_draft as svc_delete_draft,
    archive_draft as svc_archive_draft,
    get_draft as svc_get_draft,
    list_drafts as svc_list_drafts,
    update_draft as svc_update_draft,
)
from backend.auth.dependencies import get_current_user
from backend.auth.models import User
from backend.storage.dataset_catalog import (
    DatasetCatalog,
    UnknownDatasetError,
)
from backend.strategy_registry.draft_repository import DraftNotFoundError, DraftRepository
from backend.strategy_registry.drafts import StrategyDraft
from backend.tools.toolset import StrategyToolSet

_UTC = timezone.utc
_NOW = datetime(2026, 1, 1, tzinfo=_UTC)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_USER_A = User(
    user_id="user-a",
    username="alice",
    email="alice@example.com",
    password_hash="hash",
    created_at="2026-01-01T00:00:00+00:00",
    subscription_status="active",
)

_USER_B = User(
    user_id="user-b",
    username="bob",
    email="bob@example.com",
    password_hash="hash",
    created_at="2026-01-01T00:00:00+00:00",
    subscription_status="active",
)


def _make_toolset(toolset_id: str = "ts1") -> StrategyToolSet:
    return StrategyToolSet(toolset_id=toolset_id, tools=())


def _make_draft(
    draft_id: str,
    user_id: str | None = None,
) -> StrategyDraft:
    return StrategyDraft(
        draft_id=draft_id,
        display_name=f"Draft {draft_id}",
        toolset=_make_toolset(draft_id),
        created_at=_NOW,
        updated_at=_NOW,
        user_id=user_id,
    )


def _valid_create_request_dict(draft_id: str = "alpha") -> dict[str, Any]:
    return {
        "draft_id": draft_id,
        "display_name": f"Draft {draft_id}",
        "toolset": {"toolset_id": draft_id, "tools": []},
    }


def _client_for_user(tmp_path: Path, user: User) -> TestClient:
    """Create a TestClient with auth override for the given user."""
    app.dependency_overrides[get_draft_repository] = lambda: DraftRepository(tmp_path / "drafts")
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. TestDraftRepositoryOwnership
# ---------------------------------------------------------------------------

class TestDraftRepositoryOwnership:
    def test_load_with_owner_id_succeeds_for_owner(self, tmp_path: Path) -> None:
        repo = DraftRepository(tmp_path)
        draft = _make_draft("d1", user_id="user-a")
        repo.save(draft)
        loaded = repo.load("d1", owner_id="user-a")
        assert loaded.draft_id == "d1"

    def test_load_with_wrong_owner_raises_not_found(self, tmp_path: Path) -> None:
        repo = DraftRepository(tmp_path)
        draft = _make_draft("d1", user_id="user-a")
        repo.save(draft)
        with pytest.raises(DraftNotFoundError):
            repo.load("d1", owner_id="user-b")

    def test_load_with_no_owner_id_skips_check(self, tmp_path: Path) -> None:
        repo = DraftRepository(tmp_path)
        draft = _make_draft("d1", user_id="user-a")
        repo.save(draft)
        loaded = repo.load("d1")  # no owner_id → no check
        assert loaded.draft_id == "d1"

    def test_list_all_with_user_id_filters_to_owner(self, tmp_path: Path) -> None:
        repo = DraftRepository(tmp_path)
        repo.save(_make_draft("d1", user_id="user-a"))
        repo.save(_make_draft("d2", user_id="user-b"))
        repo.save(_make_draft("d3", user_id="user-a"))
        result = repo.list_all(user_id="user-a")
        ids = [d.draft_id for d in result]
        assert "d1" in ids
        assert "d3" in ids
        assert "d2" not in ids

    def test_list_all_with_no_user_id_returns_all(self, tmp_path: Path) -> None:
        repo = DraftRepository(tmp_path)
        repo.save(_make_draft("d1", user_id="user-a"))
        repo.save(_make_draft("d2", user_id="user-b"))
        result = repo.list_all()
        assert len(result) == 2

    def test_archive_wrong_owner_raises_not_found(self, tmp_path: Path) -> None:
        repo = DraftRepository(tmp_path)
        repo.save(_make_draft("d1", user_id="user-a"))
        with pytest.raises(DraftNotFoundError):
            repo.archive("d1", owner_id="user-b")

    def test_delete_wrong_owner_raises_not_found(self, tmp_path: Path) -> None:
        repo = DraftRepository(tmp_path)
        repo.save(_make_draft("d1", user_id="user-a"))
        with pytest.raises(DraftNotFoundError):
            repo.delete("d1", owner_id="user-b")

    def test_update_wrong_owner_raises_not_found(self, tmp_path: Path) -> None:
        repo = DraftRepository(tmp_path)
        repo.save(_make_draft("d1", user_id="user-a"))
        updated = _make_draft("d1", user_id="user-a")
        with pytest.raises(DraftNotFoundError):
            repo.update(updated, owner_id="user-b")

    def test_wrong_owner_and_not_found_give_same_error(self, tmp_path: Path) -> None:
        """Wrong owner raises DraftNotFoundError — same type as not-found (information hiding)."""
        repo = DraftRepository(tmp_path)
        repo.save(_make_draft("d1", user_id="user-a"))
        # Both raise DraftNotFoundError — callers cannot distinguish
        with pytest.raises(DraftNotFoundError):
            repo.load("d1", owner_id="user-b")
        with pytest.raises(DraftNotFoundError):
            repo.load("does-not-exist", owner_id="user-a")

    def test_legacy_draft_inaccessible_when_owner_id_provided(self, tmp_path: Path) -> None:
        """Legacy drafts (user_id=None) are invisible to any authenticated user."""
        repo = DraftRepository(tmp_path)
        repo.save(_make_draft("legacy", user_id=None))
        with pytest.raises(DraftNotFoundError):
            repo.load("legacy", owner_id="user-a")

    def test_legacy_draft_visible_when_no_owner_id(self, tmp_path: Path) -> None:
        """Legacy drafts are visible when no owner_id filter is applied (unauthenticated access)."""
        repo = DraftRepository(tmp_path)
        repo.save(_make_draft("legacy", user_id=None))
        loaded = repo.load("legacy")
        assert loaded.draft_id == "legacy"


# ---------------------------------------------------------------------------
# 2. TestDraftServiceOwnership
# ---------------------------------------------------------------------------

class TestDraftServiceOwnership:
    def test_create_draft_attaches_user_id(self, tmp_path: Path) -> None:
        from backend.api.schemas.drafts import DraftCreateRequest
        repo = DraftRepository(tmp_path)
        req = DraftCreateRequest(**_valid_create_request_dict("my-draft"))
        svc_create_draft(req, repo, user_id="user-a")
        draft = repo.load("my-draft")
        assert draft.user_id == "user-a"

    def test_user_a_cannot_get_user_b_draft(self, tmp_path: Path) -> None:
        from backend.api.schemas.drafts import DraftCreateRequest
        repo = DraftRepository(tmp_path)
        req = DraftCreateRequest(**_valid_create_request_dict("d1"))
        svc_create_draft(req, repo, user_id="user-b")
        with pytest.raises(DraftNotFoundError):
            svc_get_draft("d1", repo, owner_id="user-a")

    def test_user_a_cannot_list_user_b_drafts(self, tmp_path: Path) -> None:
        from backend.api.schemas.drafts import DraftCreateRequest
        repo = DraftRepository(tmp_path)
        req = DraftCreateRequest(**_valid_create_request_dict("d1"))
        svc_create_draft(req, repo, user_id="user-b")
        result = svc_list_drafts(repo, user_id="user-a")
        assert result.count == 0
        assert result.drafts == []

    def test_user_a_cannot_update_user_b_draft(self, tmp_path: Path) -> None:
        from backend.api.schemas.drafts import DraftCreateRequest, DraftUpdateRequest
        repo = DraftRepository(tmp_path)
        req = DraftCreateRequest(**_valid_create_request_dict("d1"))
        svc_create_draft(req, repo, user_id="user-b")
        update_req = DraftUpdateRequest(display_name="Updated")
        with pytest.raises(DraftNotFoundError):
            svc_update_draft("d1", update_req, repo, owner_id="user-a")

    def test_user_a_cannot_archive_user_b_draft(self, tmp_path: Path) -> None:
        from backend.api.schemas.drafts import DraftCreateRequest
        repo = DraftRepository(tmp_path)
        req = DraftCreateRequest(**_valid_create_request_dict("d1"))
        svc_create_draft(req, repo, user_id="user-b")
        with pytest.raises(DraftNotFoundError):
            svc_archive_draft("d1", repo, owner_id="user-a")

    def test_user_a_cannot_delete_user_b_draft(self, tmp_path: Path) -> None:
        from backend.api.schemas.drafts import DraftCreateRequest
        repo = DraftRepository(tmp_path)
        req = DraftCreateRequest(**_valid_create_request_dict("d1"))
        svc_create_draft(req, repo, user_id="user-b")
        with pytest.raises(DraftNotFoundError):
            svc_delete_draft("d1", repo, owner_id="user-a")


# ---------------------------------------------------------------------------
# 3. TestCatalogOwnership
# ---------------------------------------------------------------------------

class TestCatalogOwnership:
    def _register(
        self,
        catalog: DatasetCatalog,
        file_path: Path,
        symbol: str = "AAPL",
        user_id: str | None = None,
    ):
        return catalog.register(
            provider_type="csv",
            file_path=str(file_path),
            display_name=f"{symbol} Daily",
            symbol=symbol,
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
            user_id=user_id,
        )

    def test_register_attaches_user_id(self, tmp_path: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        csv_file = tmp_path / "aapl.csv"
        csv_file.write_text("date,open,high,low,close,volume\n")
        entry = self._register(catalog, csv_file, user_id="user-a")
        assert entry.user_id == "user-a"

    def test_user_a_cannot_get_user_b_entry(self, tmp_path: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        csv_file = tmp_path / "aapl.csv"
        csv_file.write_text("date,open,high,low,close,volume\n")
        entry = self._register(catalog, csv_file, user_id="user-b")
        with pytest.raises(UnknownDatasetError):
            catalog.get(entry.catalog_id, owner_id="user-a")

    def test_user_a_cannot_list_user_b_entries(self, tmp_path: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        csv_file = tmp_path / "aapl.csv"
        csv_file.write_text("date,open,high,low,close,volume\n")
        self._register(catalog, csv_file, user_id="user-b")
        result = catalog.list_all(user_id="user-a")
        assert result == []

    def test_user_a_cannot_remove_user_b_entry(self, tmp_path: Path) -> None:
        catalog = DatasetCatalog(tmp_path)
        csv_file = tmp_path / "aapl.csv"
        csv_file.write_text("date,open,high,low,close,volume\n")
        entry = self._register(catalog, csv_file, user_id="user-b")
        with pytest.raises(UnknownDatasetError):
            catalog.remove(entry.catalog_id, owner_id="user-a")

    def test_wrong_owner_and_not_found_same_error(self, tmp_path: Path) -> None:
        """Wrong-owner raises UnknownDatasetError — same as not-found (information hiding)."""
        catalog = DatasetCatalog(tmp_path)
        csv_file = tmp_path / "aapl.csv"
        csv_file.write_text("date,open,high,low,close,volume\n")
        entry = self._register(catalog, csv_file, user_id="user-b")
        with pytest.raises(UnknownDatasetError):
            catalog.get(entry.catalog_id, owner_id="user-a")
        with pytest.raises(UnknownDatasetError):
            catalog.get("does-not-exist", owner_id="user-a")

    def test_legacy_entry_inaccessible_when_owner_id_provided(self, tmp_path: Path) -> None:
        """Legacy entries (user_id=None) are invisible to authenticated users."""
        catalog = DatasetCatalog(tmp_path)
        csv_file = tmp_path / "aapl.csv"
        csv_file.write_text("date,open,high,low,close,volume\n")
        entry = self._register(catalog, csv_file, user_id=None)
        with pytest.raises(UnknownDatasetError):
            catalog.get(entry.catalog_id, owner_id="user-a")


# ---------------------------------------------------------------------------
# 4. TestDraftRouteOwnership
# ---------------------------------------------------------------------------

class TestDraftRouteOwnership:
    """HTTP route auth + ownership enforcement via TestClient."""

    @pytest.fixture(autouse=True)
    def _cleanup(self):
        yield
        app.dependency_overrides.clear()

    def test_list_drafts_requires_auth(self, tmp_path: Path) -> None:
        app.dependency_overrides[get_draft_repository] = lambda: DraftRepository(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/drafts")
        assert resp.status_code == 401

    def test_create_draft_requires_auth(self, tmp_path: Path) -> None:
        app.dependency_overrides[get_draft_repository] = lambda: DraftRepository(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/drafts", json=_valid_create_request_dict("alpha"))
        assert resp.status_code == 401

    def test_get_draft_requires_auth(self, tmp_path: Path) -> None:
        app.dependency_overrides[get_draft_repository] = lambda: DraftRepository(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/drafts/alpha")
        assert resp.status_code == 401

    def test_update_draft_requires_auth(self, tmp_path: Path) -> None:
        app.dependency_overrides[get_draft_repository] = lambda: DraftRepository(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.put("/drafts/alpha", json={"display_name": "Updated"})
        assert resp.status_code == 401

    def test_archive_draft_requires_auth(self, tmp_path: Path) -> None:
        app.dependency_overrides[get_draft_repository] = lambda: DraftRepository(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/drafts/alpha/archive")
        assert resp.status_code == 401

    def test_delete_draft_requires_auth(self, tmp_path: Path) -> None:
        app.dependency_overrides[get_draft_repository] = lambda: DraftRepository(tmp_path)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.delete("/drafts/alpha")
        assert resp.status_code == 401

    def test_authenticated_user_can_list_own_drafts(self, tmp_path: Path) -> None:
        repo = DraftRepository(tmp_path)
        app.dependency_overrides[get_draft_repository] = lambda: repo
        app.dependency_overrides[get_current_user] = lambda: _USER_A
        client = TestClient(app)
        # Create a draft for user A
        client.post("/drafts", json=_valid_create_request_dict("my-draft"))
        resp = client.get("/drafts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["drafts"][0]["draft_id"] == "my-draft"

    def test_user_a_gets_404_for_user_b_draft(self, tmp_path: Path) -> None:
        repo = DraftRepository(tmp_path)
        # Create draft as user B
        app.dependency_overrides[get_draft_repository] = lambda: repo
        app.dependency_overrides[get_current_user] = lambda: _USER_B
        client_b = TestClient(app)
        client_b.post("/drafts", json=_valid_create_request_dict("b-draft"))

        # Try to access as user A
        app.dependency_overrides[get_current_user] = lambda: _USER_A
        client_a = TestClient(app)
        resp = client_a.get("/drafts/b-draft")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. TestCatalogRouteOwnership
# ---------------------------------------------------------------------------

class TestCatalogRouteOwnership:
    """HTTP catalog route auth + ownership via TestClient."""

    @pytest.fixture(autouse=True)
    def _cleanup(self):
        yield
        app.dependency_overrides.clear()

    @pytest.fixture()
    def tmp_csv(self, tmp_path: Path) -> Path:
        p = tmp_path / "aapl.csv"
        p.write_text("date,open,high,low,close,volume\n2024-01-01,100,110,99,105,1000\n")
        return p

    def test_register_dataset_requires_auth(self, tmp_path: Path, tmp_csv: Path) -> None:
        from backend.data_providers.provider_factory import create_default_factory_registry
        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        app.dependency_overrides[get_provider_factory] = create_default_factory_registry
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/catalog/datasets", json={
            "provider_type": "csv",
            "file_path": str(tmp_csv),
            "display_name": "AAPL",
            "symbol": "AAPL",
            "asset_class": "equity",
            "venue": "NASDAQ",
            "timeframe": "1d",
        })
        assert resp.status_code == 401

    def test_list_datasets_requires_auth(self, tmp_path: Path) -> None:
        from backend.data_providers.provider_factory import create_default_factory_registry
        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        app.dependency_overrides[get_provider_factory] = create_default_factory_registry
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/catalog/datasets")
        assert resp.status_code == 401

    def test_get_dataset_requires_auth(self, tmp_path: Path) -> None:
        from backend.data_providers.provider_factory import create_default_factory_registry
        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        app.dependency_overrides[get_provider_factory] = create_default_factory_registry
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/catalog/datasets/some-id")
        assert resp.status_code == 401

    def test_delete_dataset_requires_auth(self, tmp_path: Path) -> None:
        from backend.data_providers.provider_factory import create_default_factory_registry
        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        app.dependency_overrides[get_provider_factory] = create_default_factory_registry
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.delete("/catalog/datasets/some-id")
        assert resp.status_code == 401

    def test_fetch_ohlcv_requires_auth(self, tmp_path: Path) -> None:
        from backend.data_providers.provider_factory import create_default_factory_registry
        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        app.dependency_overrides[get_provider_factory] = create_default_factory_registry
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/catalog/datasets/some-id/ohlcv",
            params={"start": "2024-01-01T00:00:00Z", "end": "2024-01-10T00:00:00Z"},
        )
        assert resp.status_code == 401

    def test_authenticated_user_can_register_dataset(self, tmp_path: Path, tmp_csv: Path) -> None:
        from backend.data_providers.provider_factory import create_default_factory_registry
        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        app.dependency_overrides[get_provider_factory] = create_default_factory_registry
        app.dependency_overrides[get_current_user] = lambda: _USER_A
        client = TestClient(app)
        resp = client.post("/catalog/datasets", json={
            "provider_type": "csv",
            "file_path": str(tmp_csv),
            "display_name": "AAPL",
            "symbol": "AAPL",
            "asset_class": "equity",
            "venue": "NASDAQ",
            "timeframe": "1d",
        })
        assert resp.status_code == 201
        assert "catalog_id" in resp.json()

    def test_user_a_gets_404_for_user_b_catalog_entry(self, tmp_path: Path, tmp_csv: Path) -> None:
        from backend.data_providers.provider_factory import create_default_factory_registry
        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        app.dependency_overrides[get_provider_factory] = create_default_factory_registry

        # Register as user B
        app.dependency_overrides[get_current_user] = lambda: _USER_B
        client_b = TestClient(app)
        resp = client_b.post("/catalog/datasets", json={
            "provider_type": "csv",
            "file_path": str(tmp_csv),
            "display_name": "AAPL",
            "symbol": "AAPL",
            "asset_class": "equity",
            "venue": "NASDAQ",
            "timeframe": "1d",
        })
        assert resp.status_code == 201
        catalog_id = resp.json()["catalog_id"]

        # Access as user A → 404
        app.dependency_overrides[get_current_user] = lambda: _USER_A
        client_a = TestClient(app)
        resp = client_a.get(f"/catalog/datasets/{catalog_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. TestBacktestOwnership
# ---------------------------------------------------------------------------

class TestBacktestOwnership:
    """Backtest run creation and report retrieval ownership."""

    @pytest.fixture(autouse=True)
    def _cleanup(self):
        yield
        app.dependency_overrides.clear()

    def test_backtest_run_attaches_owner(self, tmp_path: Path) -> None:
        from backend.api.schemas.backtest_runs import BacktestRunSummary, BacktestRunConfig
        from backend.backtesting.models import PositionSizeMode
        from backend.backtesting.cost_model import CommissionMode, SlippageMode

        # Minimal BacktestRunSummary with owner_user_id
        summary = BacktestRunSummary(
            run_id="run-1",
            draft_id="draft-1",
            draft_name="Test",
            symbol="AAPL",
            timeframe="1d",
            bars_count=10,
            run_timestamp="2026-01-01T00:00:00+00:00",
            status="completed",
            config=BacktestRunConfig(),
            owner_user_id="user-a",
        )
        assert summary.owner_user_id == "user-a"

    def test_owner_can_retrieve_own_report(self, tmp_path: Path) -> None:
        from backend.api.services.backtest_run_service import load_backtest_report
        from backend.api.schemas.backtest_runs import (
            BacktestReport, BacktestRunSummary, BacktestRunConfig, BacktestMetrics,
        )
        from backend.backtesting.cost_model import CommissionMode, SlippageMode
        from backend.backtesting.models import PositionSizeMode

        run_id = "test-run-owner-check"
        summary = BacktestRunSummary(
            run_id=run_id,
            draft_id="d1",
            draft_name="D1",
            symbol="AAPL",
            timeframe="1d",
            bars_count=1,
            run_timestamp="2026-01-01T00:00:00+00:00",
            status="completed",
            config=BacktestRunConfig(),
            owner_user_id="user-a",
        )
        metrics = BacktestMetrics(
            initial_equity=10000, final_equity=10000,
            total_net_profit=0, total_return_pct=0,
            gross_profit=0, gross_loss=0,
            total_commission=0, total_slippage=0, total_cost=0,
            trade_count=0, win_count=0, loss_count=0, breakeven_count=0,
            win_rate=None, avg_win=None, avg_loss=None, profit_factor=None,
            best_trade_pnl=None, worst_trade_pnl=None,
            max_drawdown_pct=0, peak_equity=10000, trough_equity=10000,
            total_bars=1, total_rejections=0,
        )
        report = BacktestReport(
            run=summary, metrics=metrics,
            equity_curve=[], drawdown_curve=[], trades=[],
            open_position=None, rejections=[],
        )
        storage = tmp_path / "runs"
        storage.mkdir()
        (storage / f"{run_id}.json").write_text(report.model_dump_json())
        loaded = load_backtest_report(run_id, storage=storage, owner_user_id="user-a")
        assert loaded.run.run_id == run_id

    def test_wrong_owner_gets_404(self, tmp_path: Path) -> None:
        from backend.api.services.backtest_run_service import (
            BacktestAccessDeniedError,
            load_backtest_report,
        )
        from backend.api.schemas.backtest_runs import (
            BacktestReport, BacktestRunSummary, BacktestRunConfig, BacktestMetrics,
        )

        run_id = "test-run-wrong-owner"
        summary = BacktestRunSummary(
            run_id=run_id,
            draft_id="d1",
            draft_name="D1",
            symbol="AAPL",
            timeframe="1d",
            bars_count=1,
            run_timestamp="2026-01-01T00:00:00+00:00",
            status="completed",
            config=BacktestRunConfig(),
            owner_user_id="user-a",
        )
        metrics = BacktestMetrics(
            initial_equity=10000, final_equity=10000,
            total_net_profit=0, total_return_pct=0,
            gross_profit=0, gross_loss=0,
            total_commission=0, total_slippage=0, total_cost=0,
            trade_count=0, win_count=0, loss_count=0, breakeven_count=0,
            win_rate=None, avg_win=None, avg_loss=None, profit_factor=None,
            best_trade_pnl=None, worst_trade_pnl=None,
            max_drawdown_pct=0, peak_equity=10000, trough_equity=10000,
            total_bars=1, total_rejections=0,
        )
        report = BacktestReport(
            run=summary, metrics=metrics,
            equity_curve=[], drawdown_curve=[], trades=[],
            open_position=None, rejections=[],
        )
        storage = tmp_path / "runs"
        storage.mkdir()
        (storage / f"{run_id}.json").write_text(report.model_dump_json())
        with pytest.raises(BacktestAccessDeniedError):
            load_backtest_report(run_id, storage=storage, owner_user_id="user-b")

    def test_create_run_requires_auth(self) -> None:
        from backend.api.routes.backtest_runs import get_draft_repository as bt_get_repo
        from backend.strategy_registry.draft_repository import DraftRepository
        app.dependency_overrides[bt_get_repo] = lambda: DraftRepository(Path("/tmp"))
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/backtests/runs", json={
            "draft_id": "d1", "symbol": "AAPL", "timeframe": "1d", "bars": [],
        })
        assert resp.status_code == 401

    def test_get_report_requires_auth(self) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/backtests/runs/some-run-id/report")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 7. TestGlobalRouteStillPublic
# ---------------------------------------------------------------------------

class TestGlobalRouteStillPublic:
    """System-wide routes must remain unauthenticated."""

    @pytest.fixture(autouse=True)
    def _cleanup(self):
        yield
        app.dependency_overrides.clear()

    def test_get_tools_no_auth_required(self) -> None:
        client = TestClient(app)
        resp = client.get("/tools")
        assert resp.status_code == 200

    def test_get_providers_no_auth_required(self) -> None:
        client = TestClient(app)
        resp = client.get("/market-data/providers")
        assert resp.status_code == 200

    def test_health_no_auth_required(self) -> None:
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 8. TestLegacyResourceBehavior
# ---------------------------------------------------------------------------

class TestLegacyResourceBehavior:
    """Legacy resources (user_id=None) are inaccessible to authenticated users."""

    @pytest.fixture(autouse=True)
    def _cleanup(self):
        yield
        app.dependency_overrides.clear()

    def test_legacy_draft_not_found_for_authenticated_user(self, tmp_path: Path) -> None:
        """A draft written before Phase 3L (no user_id) returns 404 via API."""
        repo = DraftRepository(tmp_path)
        legacy = _make_draft("legacy", user_id=None)
        repo.save(legacy)

        app.dependency_overrides[get_draft_repository] = lambda: repo
        app.dependency_overrides[get_current_user] = lambda: _USER_A
        client = TestClient(app)
        resp = client.get("/drafts/legacy")
        assert resp.status_code == 404

    def test_legacy_catalog_entry_not_found_for_owner(self, tmp_path: Path) -> None:
        """A catalog entry written before Phase 3L (no user_id) returns 404 via API."""
        from backend.data_providers.provider_factory import create_default_factory_registry
        catalog = DatasetCatalog(tmp_path)
        csv_file = tmp_path / "legacy.csv"
        csv_file.write_text("date,open,high,low,close,volume\n")
        entry = catalog.register(
            provider_type="csv",
            file_path=str(csv_file),
            display_name="Legacy",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
            user_id=None,  # legacy — no owner
        )

        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        app.dependency_overrides[get_provider_factory] = create_default_factory_registry
        app.dependency_overrides[get_current_user] = lambda: _USER_A
        client = TestClient(app)
        resp = client.get(f"/catalog/datasets/{entry.catalog_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 9. TestProviderCredentialsUnaffected
# ---------------------------------------------------------------------------

class TestProviderCredentialsUnaffected:
    """Vault routes are unaffected by Phase 3L (vault has its own auth from Phase 3I)."""

    @pytest.fixture(autouse=True)
    def _cleanup(self):
        yield
        app.dependency_overrides.clear()

    def test_vault_routes_still_require_auth(self) -> None:
        """Vault route still requires auth (unchanged from Phase 3I)."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/provider-credentials")
        assert resp.status_code == 401

    def test_vault_ownership_unchanged(self) -> None:
        """Vault routes haven't been modified — they still use their own auth."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/provider-credentials", json={
            "provider_name": "yahoo",
            "credential_key": "YAHOO_API_KEY",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 10. TestCompositionAndBacktestRunOwnership (Phase 3M.1)
# ---------------------------------------------------------------------------

class TestCompositionAndBacktestRunOwnership:
    """
    Phase 3M.1 — composition run and backtest run endpoints must return 404
    (not 422) when the requested draft belongs to a different user.

    Regression guard for the DraftNotFoundError propagation fix: previously
    both services wrapped DraftNotFoundError inside their own error class,
    causing the route to emit 422 instead of the correct 404.
    """

    @pytest.fixture(autouse=True)
    def _cleanup(self):
        yield
        app.dependency_overrides.clear()

    def test_composition_run_wrong_owner_returns_404(self, tmp_path: Path) -> None:
        from backend.api.routes.strategy_runs import get_draft_repository as sr_get_repo
        repo = DraftRepository(tmp_path / "drafts")
        repo.save(_make_draft("draft-a", user_id="user-a"))
        app.dependency_overrides[sr_get_repo] = lambda: repo
        app.dependency_overrides[get_current_user] = lambda: _USER_B
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/strategy-runs/run-composition", json={
            "draft_id": "draft-a", "symbol": "AAPL", "timeframe": "1d", "bars": [],
        })
        assert resp.status_code == 404

    def test_backtest_run_wrong_owner_returns_404(self, tmp_path: Path) -> None:
        from backend.api.routes.backtest_runs import get_draft_repository as bt_get_repo
        repo = DraftRepository(tmp_path / "drafts")
        repo.save(_make_draft("draft-a", user_id="user-a"))
        app.dependency_overrides[bt_get_repo] = lambda: repo
        app.dependency_overrides[get_current_user] = lambda: _USER_B
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/backtests/runs", json={
            "draft_id": "draft-a", "symbol": "AAPL", "timeframe": "1d", "bars": [],
        })
        assert resp.status_code == 404

    def test_composition_run_requires_auth(self) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/strategy-runs/run-composition", json={
            "draft_id": "draft-a", "symbol": "AAPL", "timeframe": "1d", "bars": [],
        })
        assert resp.status_code == 401
