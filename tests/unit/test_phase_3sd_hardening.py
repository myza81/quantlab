"""
Phase 3S-D hardening regression tests.

Coverage:
  1.  validate_uuid_id — valid UUID passes without error
  2.  validate_uuid_id — path traversal string raises ValueError
  3.  validate_uuid_id — URL-encoded traversal string raises ValueError
  4.  validate_uuid_id — empty string raises ValueError
  5.  validate_uuid_id — non-UUID alphanum raises ValueError
  6.  validate_uuid_id — uppercase UUID is accepted
  7.  GET /backtests/runs/{id}/report — non-UUID run_id returns 400
  8.  GET /backtests/runs/{id}/export/trades — non-UUID run_id returns 400
  9.  GET /backtests/runs/{id}/export/equity — non-UUID run_id returns 400
 10.  GET /backtests/runs/{id}/export/report — non-UUID run_id returns 400
 11.  GET /drafts/{id} — non-UUID draft_id returns 400
 12.  PUT /drafts/{id} — non-UUID draft_id returns 400
 13.  POST /drafts/{id}/archive — non-UUID draft_id returns 400
 14.  DELETE /drafts/{id} — non-UUID draft_id returns 400
 15.  POST /datasets/import/csv — requires auth (401 when no credentials)
 16.  GET  /datasets — requires auth
 17.  GET  /datasets/{id}/ohlcv — requires auth
 18.  POST /strategy-runs/run — requires auth
 19.  POST /semantics/validate — requires auth
 20.  POST /tools/validate-toolset — requires auth
 21.  GET  /tools — public (no auth required, returns 200)
 22.  GET  /market-data/providers — public (no auth required, returns 200)
 23.  DraftRepository — missing valid UUID raises DraftNotFoundError
 24.  DraftRepository — missing archived UUID raises DraftNotFoundError
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.auth.entitlement import require_active_subscription
from backend.core.request_validation import validate_uuid_id
from backend.strategy_registry.draft_repository import DraftNotFoundError, DraftRepository  # noqa: F401

client = TestClient(app)

_VALID_UUID = "12345678-1234-1234-1234-123456789abc"
_TRAVERSAL_IDS = [
    "../../etc/passwd",
    "../secret",
    "%2e%2e%2fetc%2fpasswd",
    "/etc/passwd",
    "not-a-uuid",
    "",
    "   ",
    "12345678_1234_1234_1234_123456789abc",  # underscores not hyphens
]


# ---------------------------------------------------------------------------
# Unit: validate_uuid_id helper
# ---------------------------------------------------------------------------

class TestValidateUuidId:
    def test_valid_uuid_passes(self) -> None:
        validate_uuid_id(_VALID_UUID, "run_id")  # must not raise

    def test_path_traversal_raises(self) -> None:
        with pytest.raises(ValueError, match="run_id"):
            validate_uuid_id("../../etc/passwd", "run_id")

    def test_url_encoded_traversal_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_uuid_id("%2e%2e%2fetc%2fpasswd", "run_id")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_uuid_id("", "run_id")

    def test_non_uuid_alphanum_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_uuid_id("not-a-uuid", "run_id")

    def test_uppercase_uuid_accepted(self) -> None:
        validate_uuid_id(_VALID_UUID.upper(), "run_id")  # must not raise


# ---------------------------------------------------------------------------
# API: run_id path traversal — backtest endpoints
#
# Note: multi-segment traversal strings like "../../etc/passwd" are normalized
# by the HTTP router before reaching a route handler, so they land on a
# different (non-existent) route and return 404 — not a security gap.
# The real risk is single-segment non-UUID strings that slip through URL
# routing but still reach the filesystem path construction.
# ---------------------------------------------------------------------------

class TestRunIdPathTraversal:
    @pytest.fixture(autouse=True)
    def _use_tmp_storage(self, tmp_path):
        from backend.api.dependencies import get_backtest_storage_path
        app.dependency_overrides[get_backtest_storage_path] = lambda: tmp_path
        yield
        app.dependency_overrides.pop(get_backtest_storage_path, None)

    @pytest.mark.parametrize("bad_id", [
        "not-a-uuid",
        "12345678_1234_1234_1234_123456789abc",
        "evil-id",
    ])
    def test_report_rejects_non_uuid_id(self, bad_id: str) -> None:
        resp = client.get(f"/backtests/runs/{bad_id}/report")
        assert resp.status_code == 400

    @pytest.mark.parametrize("bad_id", ["not-a-uuid", "evil-id"])
    def test_export_trades_rejects_non_uuid_id(self, bad_id: str) -> None:
        resp = client.get(f"/backtests/runs/{bad_id}/export/trades")
        assert resp.status_code == 400

    @pytest.mark.parametrize("bad_id", ["not-a-uuid", "evil-id"])
    def test_export_equity_rejects_non_uuid_id(self, bad_id: str) -> None:
        resp = client.get(f"/backtests/runs/{bad_id}/export/equity")
        assert resp.status_code == 400

    @pytest.mark.parametrize("bad_id", ["not-a-uuid", "evil-id"])
    def test_export_report_rejects_non_uuid_id(self, bad_id: str) -> None:
        resp = client.get(f"/backtests/runs/{bad_id}/export/report")
        assert resp.status_code == 400

    def test_valid_uuid_proceeds_to_404(self) -> None:
        resp = client.get(f"/backtests/runs/{_VALID_UUID}/report")
        # Not 400 — UUID is valid, storage is empty so we expect 404
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API: draft_id path traversal — draft endpoints
# ---------------------------------------------------------------------------

class TestDraftIdPathTraversal:
    @pytest.mark.parametrize("bad_id", [
        "not-a-uuid",
        "evil-draft",
    ])
    def test_get_draft_rejects_non_uuid(self, bad_id: str) -> None:
        resp = client.get(f"/drafts/{bad_id}")
        assert resp.status_code == 400

    @pytest.mark.parametrize("bad_id", ["not-a-uuid", "evil-draft"])
    def test_put_draft_rejects_non_uuid(self, bad_id: str) -> None:
        # Use valid (but empty) body — all DraftUpdateRequest fields are optional
        resp = client.put(f"/drafts/{bad_id}", json={})
        assert resp.status_code == 400

    @pytest.mark.parametrize("bad_id", ["not-a-uuid", "evil-draft"])
    def test_archive_draft_rejects_non_uuid(self, bad_id: str) -> None:
        resp = client.post(f"/drafts/{bad_id}/archive")
        assert resp.status_code == 400

    @pytest.mark.parametrize("bad_id", ["not-a-uuid", "evil-draft"])
    def test_delete_draft_rejects_non_uuid(self, bad_id: str) -> None:
        resp = client.delete(f"/drafts/{bad_id}")
        assert resp.status_code == 400

    def test_valid_uuid_proceeds_to_404(self) -> None:
        resp = client.get(f"/drafts/{_VALID_UUID}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API: legacy route auth enforcement
# ---------------------------------------------------------------------------

class TestLegacyRouteAuth:
    """Verify that legacy deprecated routes now require authentication."""

    @pytest.fixture(autouse=True)
    def _remove_auth_override(self):
        prev = app.dependency_overrides.pop(require_active_subscription, None)
        yield
        if prev is not None:
            app.dependency_overrides[require_active_subscription] = prev

    def test_datasets_list_requires_auth(self) -> None:
        resp = client.get("/datasets")
        assert resp.status_code in (401, 403)

    def test_datasets_ohlcv_requires_auth(self) -> None:
        resp = client.get("/datasets/equities__AAPL__1d/ohlcv")
        assert resp.status_code in (401, 403)

    def test_datasets_import_csv_requires_auth(self) -> None:
        resp = client.post(
            "/datasets/import/csv",
            data={
                "symbol": "AAPL", "asset_class": "equities",
                "venue": "NASDAQ", "timeframe": "1d", "source": "test",
            },
            files={"file": ("data.csv", b"timestamp,open,high,low,close,volume\n", "text/csv")},
        )
        assert resp.status_code in (401, 403)

    def test_strategy_runs_run_requires_auth(self) -> None:
        resp = client.post(
            "/strategy-runs/run",
            json={
                "strategy_id": "sma_crossover", "provider": "csv",
                "symbol": "AAPL", "timeframe": "1d",
                "start": "2023-01-01T00:00:00Z", "end": "2023-12-31T00:00:00Z",
            },
        )
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# API: newly-protected route auth enforcement
# ---------------------------------------------------------------------------

class TestNewlyProtectedRouteAuth:
    @pytest.fixture(autouse=True)
    def _remove_auth_override(self):
        prev = app.dependency_overrides.pop(require_active_subscription, None)
        yield
        if prev is not None:
            app.dependency_overrides[require_active_subscription] = prev

    def test_semantics_validate_requires_auth(self) -> None:
        resp = client.post(
            "/semantics/validate",
            json={"semantics": {"entry_logic": "price > sma_20", "exit_logic": "price < sma_20"}},
        )
        assert resp.status_code in (401, 403)

    def test_tools_validate_toolset_requires_auth(self) -> None:
        resp = client.post(
            "/tools/validate-toolset",
            json={"tools": []},
        )
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# API: intentionally public discovery routes
# ---------------------------------------------------------------------------

class TestPublicDiscoveryRoutes:
    @pytest.fixture(autouse=True)
    def _remove_auth_override(self):
        prev = app.dependency_overrides.pop(require_active_subscription, None)
        yield
        if prev is not None:
            app.dependency_overrides[require_active_subscription] = prev

    def test_get_tools_is_public(self) -> None:
        resp = client.get("/tools")
        assert resp.status_code == 200
        assert "tools" in resp.json()

    def test_get_market_data_providers_is_public(self) -> None:
        resp = client.get("/market-data/providers")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Repository: expected behavior for missing drafts
#
# Note: UUID format validation lives at the route handler layer (routes/drafts.py).
# The repository itself accepts any string as draft_id and raises DraftNotFoundError
# if no file exists. URL routing prevents path-separator injection via URL params.
# ---------------------------------------------------------------------------

class TestDraftRepositoryMissingDraftBehavior:
    def test_load_missing_uuid_raises_draft_not_found(self, tmp_path) -> None:
        repo = DraftRepository(tmp_path)
        with pytest.raises(DraftNotFoundError):
            repo.load(_VALID_UUID)

    def test_load_archived_missing_uuid_raises_draft_not_found(self, tmp_path) -> None:
        repo = DraftRepository(tmp_path)
        with pytest.raises(DraftNotFoundError):
            repo.load_archived(_VALID_UUID)
