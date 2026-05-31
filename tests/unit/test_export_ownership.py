"""
Export endpoint ownership enforcement tests (Phase 3S-C).

All 3 export endpoints (trades / equity / report) must return HTTP 404 —
not 403 — when the requester does not own the target run, to prevent
existence leakage via status code differentiation.

Coverage:
 1.  GET /backtests/runs/{id}/export/trades  — 404 for cross-user request
 2.  GET /backtests/runs/{id}/export/equity  — 404 for cross-user request
 3.  GET /backtests/runs/{id}/export/report  — 404 for cross-user request
 4.  load_backtest_report raises BacktestAccessDeniedError for wrong owner
 5.  load_backtest_report returns report for correct owner
 6.  load_backtest_report skips ownership check when owner_user_id=None
 7.  Trades export 404 detail says "not found" (not "access denied")
 8.  Equity export 404 detail says "not found"
 9.  Report export 404 detail says "not found"
"""
from __future__ import annotations

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
)
from backend.api.services.backtest_run_service import (
    BacktestAccessDeniedError,
    load_backtest_report,
)

_OWNER_ID   = "user-alpha"       # owns the report
_CALLER_ID  = "unit-test-user"   # conftest default user — NOT the owner
_RUN_ID     = "eeeeeeee-0000-0000-0000-000000000001"
_TS         = "2024-06-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _metrics() -> BacktestMetrics:
    return BacktestMetrics(
        initial_equity=10_000.0, final_equity=10_000.0,
        total_net_profit=0.0, total_return_pct=0.0,
        gross_profit=0.0, gross_loss=0.0,
        total_commission=0.0, total_slippage=0.0, total_cost=0.0,
        trade_count=0, win_count=0, loss_count=0, breakeven_count=0,
        win_rate=None, avg_win=None, avg_loss=None, profit_factor=None,
        best_trade_pnl=None, worst_trade_pnl=None,
        max_drawdown_pct=0.0, peak_equity=10_000.0, trough_equity=10_000.0,
        total_bars=5, total_rejections=0,
    )


def _owned_report(run_id: str = _RUN_ID, owner_id: str = _OWNER_ID) -> BacktestReport:
    return BacktestReport(
        run=BacktestRunSummary(
            run_id=run_id,
            draft_id="d1",
            draft_name="Ownership Test",
            symbol="SPY",
            timeframe="1h",
            bars_count=5,
            run_timestamp=_TS,
            status="completed",
            config=BacktestRunConfig(),
            owner_user_id=owner_id,
        ),
        metrics=_metrics(),
        equity_curve=[],
        drawdown_curve=[],
        trades=[],
        open_position=None,
        rejections=[],
    )


def _write(storage: Path, report: BacktestReport) -> None:
    (storage / f"{report.run.run_id}.json").write_text(
        report.model_dump_json(), encoding="utf-8"
    )


@pytest.fixture()
def cross_user_client(tmp_path):
    """Client as _CALLER_ID; storage contains a report owned by _OWNER_ID."""
    _write(tmp_path, _owned_report())
    app.dependency_overrides[get_backtest_storage_path] = lambda: tmp_path
    yield TestClient(app), tmp_path
    app.dependency_overrides.pop(get_backtest_storage_path, None)


# ---------------------------------------------------------------------------
# 1–3. API cross-user 404 for all 3 export endpoints
# ---------------------------------------------------------------------------

class TestExportOwnershipEnforcement:

    def test_trades_export_cross_user_404(self, cross_user_client):
        client, _ = cross_user_client
        resp = client.get(f"/backtests/runs/{_RUN_ID}/export/trades")
        assert resp.status_code == 404

    def test_equity_export_cross_user_404(self, cross_user_client):
        client, _ = cross_user_client
        resp = client.get(f"/backtests/runs/{_RUN_ID}/export/equity")
        assert resp.status_code == 404

    def test_report_export_cross_user_404(self, cross_user_client):
        client, _ = cross_user_client
        resp = client.get(f"/backtests/runs/{_RUN_ID}/export/report")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4–6. load_backtest_report service ownership checks
# ---------------------------------------------------------------------------

class TestLoadBacktestReportOwnership:

    def test_raises_access_denied_for_wrong_owner(self, tmp_path):
        _write(tmp_path, _owned_report(owner_id="user-a"))
        with pytest.raises(BacktestAccessDeniedError):
            load_backtest_report(_RUN_ID, storage=tmp_path, owner_user_id="user-b")

    def test_returns_report_for_correct_owner(self, tmp_path):
        _write(tmp_path, _owned_report(owner_id="user-a"))
        loaded = load_backtest_report(_RUN_ID, storage=tmp_path, owner_user_id="user-a")
        assert loaded.run.run_id == _RUN_ID

    def test_skips_ownership_check_when_none(self, tmp_path):
        _write(tmp_path, _owned_report(owner_id="user-a"))
        loaded = load_backtest_report(_RUN_ID, storage=tmp_path, owner_user_id=None)
        assert loaded.run.run_id == _RUN_ID


# ---------------------------------------------------------------------------
# 7–9. 404 detail is non-revealing ("not found", not "access denied")
# ---------------------------------------------------------------------------

class TestExportOwnership404Detail:

    def test_trades_detail_says_not_found(self, cross_user_client):
        client, _ = cross_user_client
        resp = client.get(f"/backtests/runs/{_RUN_ID}/export/trades")
        detail = resp.json().get("detail", "").lower()
        assert "not found" in detail
        assert "password" not in detail
        assert "storage" not in detail

    def test_equity_detail_says_not_found(self, cross_user_client):
        client, _ = cross_user_client
        resp = client.get(f"/backtests/runs/{_RUN_ID}/export/equity")
        detail = resp.json().get("detail", "").lower()
        assert "not found" in detail

    def test_report_export_detail_says_not_found(self, cross_user_client):
        client, _ = cross_user_client
        resp = client.get(f"/backtests/runs/{_RUN_ID}/export/report")
        detail = resp.json().get("detail", "").lower()
        assert "not found" in detail
