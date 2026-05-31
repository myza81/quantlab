"""
HTTP boundary leakage tests (Phase 3S-C).

Verifies that all backtest API endpoints never expose in their HTTP responses:
  - password_hash fields
  - raw storage directory paths
  - owner_user_id in history list items (cross-user information hiding)

Coverage:
 1.  GET /backtests/runs             — "password_hash" absent
 2.  GET /backtests/runs             — "owner_user_id" absent from each list item
 3.  GET /backtests/runs             — storage directory path absent from response text
 4.  GET /backtests/runs/{id}/report — "password_hash" absent
 5.  GET /backtests/runs/{id}/report — storage directory path absent from provenance fields
 6.  GET /backtests/runs/{id}/export/trades  — "password_hash" absent
 7.  GET /backtests/runs/{id}/export/equity  — "password_hash" absent
 8.  GET /backtests/runs/{id}/export/report  — "password_hash" absent from JSON body
"""
from __future__ import annotations

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
)

_OWNER_ID = "unit-test-user"   # matches conftest default user
_RUN_ID   = "dddddddd-0000-0000-0000-000000000001"
_TS       = "2024-06-01T10:00:00+00:00"


def _metrics() -> BacktestMetrics:
    return BacktestMetrics(
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


def _report() -> BacktestReport:
    return BacktestReport(
        run=BacktestRunSummary(
            run_id=_RUN_ID,
            draft_id="d1",
            draft_name="Leak Test",
            symbol="AAPL",
            timeframe="1d",
            bars_count=10,
            run_timestamp=_TS,
            status="completed",
            config=BacktestRunConfig(),
            owner_user_id=_OWNER_ID,
            dataset_provenance=DatasetProvenance(
                source_mode="provider",
                provider_name="yahoo",
                catalog_id=None,
                bars_fingerprint="a" * 64,
                bar_count=10,
            ),
        ),
        metrics=_metrics(),
        equity_curve=[],
        drawdown_curve=[],
        trades=[],
        open_position=None,
        rejections=[],
    )


@pytest.fixture()
def leakage_client(tmp_path):
    report = _report()
    (tmp_path / f"{_RUN_ID}.json").write_text(report.model_dump_json(), encoding="utf-8")
    app.dependency_overrides[get_backtest_storage_path] = lambda: tmp_path
    yield TestClient(app), str(tmp_path)
    app.dependency_overrides.pop(get_backtest_storage_path, None)


class TestHTTPBoundaryLeakage:

    def test_list_runs_no_password_hash(self, leakage_client):
        client, _ = leakage_client
        resp = client.get("/backtests/runs")
        assert resp.status_code == 200
        assert "password_hash" not in resp.text

    def test_list_runs_items_no_owner_user_id(self, leakage_client):
        client, _ = leakage_client
        resp = client.get("/backtests/runs")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        # owner_user_id must not be a key in the list item — it's an internal field
        assert "owner_user_id" not in items[0]

    def test_list_runs_no_storage_path(self, leakage_client):
        client, storage_path = leakage_client
        resp = client.get("/backtests/runs")
        assert resp.status_code == 200
        assert storage_path not in resp.text

    def test_report_no_password_hash(self, leakage_client):
        client, _ = leakage_client
        resp = client.get(f"/backtests/runs/{_RUN_ID}/report")
        assert resp.status_code == 200
        assert "password_hash" not in resp.text

    def test_report_provenance_no_storage_path(self, leakage_client):
        client, storage_path = leakage_client
        resp = client.get(f"/backtests/runs/{_RUN_ID}/report")
        assert resp.status_code == 200
        prov = resp.json()["run"].get("dataset_provenance") or {}
        for val in prov.values():
            if isinstance(val, str):
                assert storage_path not in val, f"Storage path leaked in provenance field: {val!r}"

    def test_export_trades_no_password_hash(self, leakage_client):
        client, _ = leakage_client
        resp = client.get(f"/backtests/runs/{_RUN_ID}/export/trades")
        assert resp.status_code == 200
        assert "password_hash" not in resp.text

    def test_export_equity_no_password_hash(self, leakage_client):
        client, _ = leakage_client
        resp = client.get(f"/backtests/runs/{_RUN_ID}/export/equity")
        assert resp.status_code == 200
        assert "password_hash" not in resp.text

    def test_export_report_no_password_hash(self, leakage_client):
        client, _ = leakage_client
        resp = client.get(f"/backtests/runs/{_RUN_ID}/export/report")
        assert resp.status_code == 200
        assert "password_hash" not in resp.text
