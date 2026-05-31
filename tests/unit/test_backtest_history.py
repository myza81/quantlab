"""
Backtest history — list runs + reopen + API isolation (Phase 3S-C).

Coverage:
 1.  list_backtest_runs — empty list when storage directory missing
 2.  list_backtest_runs — empty list when storage exists but is empty
 3.  list_backtest_runs — filters by owner_user_id (cross-user invisible)
 4.  list_backtest_runs — newest-first ordering by run_timestamp
 5.  list_backtest_runs — respects limit parameter
 6.  list_backtest_runs — skips corrupt / unreadable JSON files (silent)
 7.  list_backtest_runs — extracts key metrics (return, trades, drawdown)
 8.  list_backtest_runs — includes provenance fields when present in run
 9.  API GET /backtests/runs — 200 with caller-owned runs
10.  API GET /backtests/runs — empty list for user with no runs
11.  API GET /backtests/runs — cross-user isolation (other user's runs absent)
12.  API GET /backtests/runs/{id}/report — 200 for owner (reopen flow)
13.  API GET /backtests/runs/{id}/report — 404 for cross-user access
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.dependencies import get_backtest_storage_path
from backend.api.main import app
from backend.api.schemas.backtest_runs import (
    BacktestMetrics,
    BacktestReport,
    BacktestRunConfig,
    BacktestRunSummary,
    DatasetProvenance,
    DraftProvenance,
)
from backend.api.services.backtest_run_service import list_backtest_runs

# Conftest autouse fixture already wires require_active_subscription → this user.
_OWNER_ID = "unit-test-user"
_OTHER_ID = "other-user-id"
_TS_BASE  = "2024-01-15T10:00:00+00:00"

# Valid UUIDs for API path-param tests (UUID validation enforced by route handler).
_UUID_OWNED = "aaaaaaaa-0000-0000-0000-000000000001"
_UUID_CROSS = "bbbbbbbb-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _metrics(**overrides) -> BacktestMetrics:
    base = dict(
        initial_equity=10_000.0, final_equity=10_500.0,
        total_net_profit=500.0, total_return_pct=5.0,
        gross_profit=600.0, gross_loss=-100.0,
        total_commission=0.0, total_slippage=0.0, total_cost=0.0,
        trade_count=1, win_count=1, loss_count=0, breakeven_count=0,
        win_rate=1.0, avg_win=500.0, avg_loss=None, profit_factor=None,
        best_trade_pnl=500.0, worst_trade_pnl=None,
        max_drawdown_pct=2.0, peak_equity=10_500.0, trough_equity=9_800.0,
        total_bars=10, total_rejections=0,
    )
    base.update(overrides)
    return BacktestMetrics(**base)  # type: ignore[arg-type]


def _run_summary(
    run_id: str,
    owner_id: str,
    run_timestamp: str = _TS_BASE,
    *,
    dataset_provenance: DatasetProvenance | None = None,
    draft_provenance: DraftProvenance | None = None,
) -> BacktestRunSummary:
    return BacktestRunSummary(
        run_id=run_id,
        draft_id="d1",
        draft_name="Test Strategy",
        symbol="AAPL",
        timeframe="1d",
        bars_count=10,
        run_timestamp=run_timestamp,
        status="completed",
        config=BacktestRunConfig(),
        owner_user_id=owner_id,
        dataset_provenance=dataset_provenance,
        draft_provenance=draft_provenance,
    )


def _report(
    run_id: str,
    owner_id: str,
    run_timestamp: str = _TS_BASE,
    metrics_overrides: dict | None = None,
    **summary_kwargs,
) -> BacktestReport:
    return BacktestReport(
        run=_run_summary(run_id, owner_id, run_timestamp, **summary_kwargs),
        metrics=_metrics(**(metrics_overrides or {})),
        equity_curve=[],
        drawdown_curve=[],
        trades=[],
        open_position=None,
        rejections=[],
    )


def _write(directory: Path, report: BacktestReport) -> None:
    (directory / f"{report.run.run_id}.json").write_text(
        report.model_dump_json(), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# 1–8. list_backtest_runs service tests
# ---------------------------------------------------------------------------

class TestListBacktestRunsService:

    def test_empty_when_storage_missing(self, tmp_path):
        result = list_backtest_runs(tmp_path / "nonexistent", _OWNER_ID)
        assert result == []

    def test_empty_when_no_files(self, tmp_path):
        result = list_backtest_runs(tmp_path, _OWNER_ID)
        assert result == []

    def test_filters_by_owner(self, tmp_path):
        _write(tmp_path, _report("run-a", _OWNER_ID))
        _write(tmp_path, _report("run-b", _OTHER_ID))
        result = list_backtest_runs(tmp_path, _OWNER_ID)
        assert len(result) == 1
        assert result[0].run_id == "run-a"

    def test_other_user_invisible(self, tmp_path):
        _write(tmp_path, _report("run-other", _OTHER_ID))
        result = list_backtest_runs(tmp_path, _OWNER_ID)
        assert result == []

    def test_newest_first_ordering(self, tmp_path):
        _write(tmp_path, _report("run-1", _OWNER_ID, "2024-01-10T00:00:00+00:00"))
        _write(tmp_path, _report("run-2", _OWNER_ID, "2024-01-20T00:00:00+00:00"))
        _write(tmp_path, _report("run-3", _OWNER_ID, "2024-01-05T00:00:00+00:00"))
        result = list_backtest_runs(tmp_path, _OWNER_ID)
        assert [r.run_id for r in result] == ["run-2", "run-1", "run-3"]

    def test_respects_limit(self, tmp_path):
        for i in range(5):
            ts = f"2024-01-{i + 1:02d}T00:00:00+00:00"
            _write(tmp_path, _report(f"run-{i}", _OWNER_ID, ts))
        result = list_backtest_runs(tmp_path, _OWNER_ID, limit=2)
        assert len(result) == 2

    def test_skips_corrupt_files_silently(self, tmp_path):
        (tmp_path / "corrupt.json").write_text("not valid json", encoding="utf-8")
        (tmp_path / "partial.json").write_text('{"run": {}}', encoding="utf-8")
        _write(tmp_path, _report("run-good", _OWNER_ID))
        result = list_backtest_runs(tmp_path, _OWNER_ID)
        assert len(result) == 1
        assert result[0].run_id == "run-good"

    def test_extracts_key_metrics(self, tmp_path):
        _write(tmp_path, _report(
            "run-m", _OWNER_ID,
            metrics_overrides=dict(total_return_pct=7.5, trade_count=3, max_drawdown_pct=4.2),
        ))
        result = list_backtest_runs(tmp_path, _OWNER_ID)
        item = result[0]
        assert item.total_return_pct == pytest.approx(7.5)
        assert item.trade_count == 3
        assert item.max_drawdown_pct == pytest.approx(4.2)

    def test_includes_provenance_when_present(self, tmp_path):
        _write(tmp_path, _report(
            "run-prov", _OWNER_ID,
            dataset_provenance=DatasetProvenance(
                source_mode="provider",
                provider_name="yahoo",
                bars_fingerprint="a" * 64,
                bar_count=10,
            ),
            draft_provenance=DraftProvenance(
                draft_id="d1",
                display_name="Prov Strategy",
                lifecycle_status_at_run="draft",
                semantics_hash="b" * 64,
            ),
        ))
        result = list_backtest_runs(tmp_path, _OWNER_ID)
        item = result[0]
        assert item.dataset_provenance is not None
        assert item.dataset_provenance.source_mode == "provider"
        assert item.draft_provenance is not None
        assert item.draft_provenance.lifecycle_status_at_run == "draft"


# ---------------------------------------------------------------------------
# 9–13. API endpoint tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def api_client(tmp_path):
    app.dependency_overrides[get_backtest_storage_path] = lambda: tmp_path
    yield TestClient(app), tmp_path
    app.dependency_overrides.pop(get_backtest_storage_path, None)


class TestListBacktestRunsAPI:

    def test_returns_200_with_owned_runs(self, api_client):
        client, storage = api_client
        _write(storage, _report("run-owned", _OWNER_ID))
        resp = client.get("/backtests/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["run_id"] == "run-owned"

    def test_returns_empty_for_new_user(self, api_client):
        client, _storage = api_client
        resp = client.get("/backtests/runs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_cross_user_isolation(self, api_client):
        client, storage = api_client
        _write(storage, _report("run-other", _OTHER_ID))
        resp = client.get("/backtests/runs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_reopen_report_200_for_owner(self, api_client):
        client, storage = api_client
        _write(storage, _report(_UUID_OWNED, _OWNER_ID))
        resp = client.get(f"/backtests/runs/{_UUID_OWNED}/report")
        assert resp.status_code == 200
        assert resp.json()["run"]["run_id"] == _UUID_OWNED

    def test_reopen_report_404_for_cross_user(self, api_client):
        client, storage = api_client
        _write(storage, _report(_UUID_CROSS, _OTHER_ID))
        resp = client.get(f"/backtests/runs/{_UUID_CROSS}/report")
        assert resp.status_code == 404
