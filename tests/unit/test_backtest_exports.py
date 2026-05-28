"""
Backtest Export Service + Schema Stability tests.

Coverage areas:
  1.  export_trade_ledger_csv — produces valid CSV with correct headers
  2.  export_trade_ledger_csv — closed trade fields serialize correctly
  3.  export_trade_ledger_csv — open position serializes with status='open'
  4.  export_trade_ledger_csv — None fields render as empty string (not 'None')
  5.  export_trade_ledger_csv — empty trade list produces header-only CSV
  6.  export_trade_ledger_csv — audit rule_id fields included
  7.  export_equity_curve_csv — produces valid CSV with correct headers
  8.  export_equity_curve_csv — drawdown joined per bar_index
  9.  export_equity_curve_csv — missing drawdown for a bar → empty cell
  10. export_report_json — output is valid JSON
  11. export_report_json — round-trips via BacktestReport.model_validate
  12. export_report_json — schema-stable (required keys always present)
  13. API GET /backtests/runs/{id}/export/trades — 200 with text/csv
  14. API GET /backtests/runs/{id}/export/equity — 200 with text/csv
  15. API GET /backtests/runs/{id}/export/report — 200 with application/json
  16. API export — 404 for unknown run_id
  17. BacktestReport schema stability — all required top-level fields present
  18. BacktestRunSummary reproducibility fields present (dataset_start/end, engine_version)
  19. TradeRecord audit fields present (entry/exit rule_id, signal_event_id)
  20. export CSV row count matches trade count
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.schemas.backtest_runs import (
    BacktestDrawdownRecord,
    BacktestEquityRecord,
    BacktestMetrics,
    BacktestRejectionRecord,
    BacktestReport,
    BacktestRunConfig,
    BacktestRunSummary,
    TradeRecord,
)
from backend.api.services.export_service import (
    export_equity_curve_csv,
    export_report_json,
    export_trade_ledger_csv,
)
from backend.backtesting.cost_model import CommissionMode, SlippageMode
from backend.backtesting.models import PositionSizeMode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TS = "2024-01-15T10:00:00+00:00"
_RUN_ID = "test-run-00000000-0000-0000-0000-000000000001"


def _config() -> BacktestRunConfig:
    return BacktestRunConfig(
        initial_equity=10_000.0,
        position_size_mode=PositionSizeMode.EQUITY_FRACTION,
        equity_fraction=0.95,
        fixed_quantity=1.0,
        commission_mode=CommissionMode.NONE,
        commission_value=0.0,
        slippage_mode=SlippageMode.NONE,
        slippage_value=0.0,
    )


def _run_summary(run_id: str = _RUN_ID) -> BacktestRunSummary:
    return BacktestRunSummary(
        run_id=run_id,
        draft_id="draft-abc",
        draft_name="Test Strategy",
        symbol="AAPL",
        timeframe="1d",
        bars_count=10,
        run_timestamp=_TS,
        status="completed",
        config=_config(),
        dataset_start="2024-01-01T00:00:00+00:00",
        dataset_end="2024-01-10T00:00:00+00:00",
        engine_version="2P.9",
    )


def _metrics() -> BacktestMetrics:
    return BacktestMetrics(
        initial_equity=10_000.0,
        final_equity=10_500.0,
        total_net_profit=500.0,
        total_return_pct=5.0,
        gross_profit=600.0,
        gross_loss=-100.0,
        total_commission=0.0,
        total_slippage=0.0,
        total_cost=0.0,
        trade_count=1,
        win_count=1,
        loss_count=0,
        breakeven_count=0,
        win_rate=1.0,
        avg_win=500.0,
        avg_loss=None,
        profit_factor=None,
        best_trade_pnl=500.0,
        worst_trade_pnl=None,
        max_drawdown_pct=5.0,
        peak_equity=10_500.0,
        trough_equity=9_800.0,
        total_bars=10,
        total_rejections=0,
    )


def _trade(trade_num: int = 1, with_audit: bool = True) -> TradeRecord:
    return TradeRecord(
        trade_num=trade_num,
        entry_bar_index=2,
        exit_bar_index=7,
        entry_timestamp="2024-01-03T00:00:00+00:00",
        exit_timestamp="2024-01-08T00:00:00+00:00",
        side="long",
        quantity=95.0,
        entry_price=100.0,
        exit_price=105.26,
        entry_commission=0.0,
        exit_commission=0.0,
        entry_slippage=0.0,
        exit_slippage=0.0,
        gross_pnl=499.7,
        net_pnl=499.7,
        return_pct=5.26,
        holding_bars=5,
        equity_after=10_499.7,
        entry_rule_id="entry-rule-1" if with_audit else None,
        exit_rule_id="exit-rule-1" if with_audit else None,
        entry_signal_event_id="2:entry:0:entry-rule-1" if with_audit else None,
        exit_signal_event_id="7:exit:0:exit-rule-1" if with_audit else None,
    )


def _open_trade() -> TradeRecord:
    return TradeRecord(
        trade_num=2,
        entry_bar_index=8,
        exit_bar_index=None,
        entry_timestamp="2024-01-09T00:00:00+00:00",
        exit_timestamp=None,
        side="long",
        quantity=95.0,
        entry_price=100.0,
        exit_price=None,
        entry_commission=0.0,
        exit_commission=None,
        entry_slippage=0.0,
        exit_slippage=None,
        gross_pnl=None,
        net_pnl=None,
        return_pct=None,
        holding_bars=None,
        equity_after=None,
        entry_rule_id="entry-rule-1",
        exit_rule_id=None,
        entry_signal_event_id="8:entry:0:entry-rule-1",
        exit_signal_event_id=None,
    )


def _equity_records() -> list[BacktestEquityRecord]:
    return [
        BacktestEquityRecord(
            bar_index=i,
            timestamp=f"2024-01-{i+1:02d}T00:00:00+00:00",
            cash=9_000.0,
            position_quantity=10.0,
            market_value=1_000.0 + i * 50,
            realized_pnl=0.0,
            unrealized_pnl=i * 50.0,
            equity=10_000.0 + i * 50,
        )
        for i in range(5)
    ]


def _drawdown_records() -> list[BacktestDrawdownRecord]:
    return [
        BacktestDrawdownRecord(bar_index=i, timestamp=f"2024-01-{i+1:02d}T00:00:00+00:00", drawdown_pct=0.0)
        for i in range(5)
    ]


def _report(
    trades: list[TradeRecord] | None = None,
    open_position: TradeRecord | None = None,
    run_id: str = _RUN_ID,
) -> BacktestReport:
    return BacktestReport(
        run=_run_summary(run_id),
        metrics=_metrics(),
        equity_curve=_equity_records(),
        drawdown_curve=_drawdown_records(),
        trades=trades if trades is not None else [_trade()],
        open_position=open_position,
        rejections=[],
    )


# ---------------------------------------------------------------------------
# 1–6. export_trade_ledger_csv
# ---------------------------------------------------------------------------

def test_csv_has_correct_headers():
    report = _report()
    csv_text = export_trade_ledger_csv(report)
    reader = csv.DictReader(io.StringIO(csv_text))
    assert "trade_num" in (reader.fieldnames or [])
    assert "entry_rule_id" in (reader.fieldnames or [])
    assert "exit_signal_event_id" in (reader.fieldnames or [])
    assert "status" in (reader.fieldnames or [])


def test_csv_closed_trade_fields():
    report = _report()
    csv_text = export_trade_ledger_csv(report)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "closed"
    assert row["trade_num"] == "1"
    assert row["entry_price"] == "100.0"
    assert row["net_pnl"] == "499.7"
    assert row["entry_rule_id"] == "entry-rule-1"
    assert row["exit_rule_id"] == "exit-rule-1"


def test_csv_open_position_status():
    report = _report(open_position=_open_trade())
    csv_text = export_trade_ledger_csv(report)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(rows) == 2
    assert rows[1]["status"] == "open"
    assert rows[1]["exit_bar_index"] == ""
    assert rows[1]["net_pnl"] == ""


def test_csv_none_renders_as_empty_string_not_none_literal():
    trade_no_audit = _trade(with_audit=False)
    report = _report(trades=[trade_no_audit])
    csv_text = export_trade_ledger_csv(report)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    # None fields must serialize to empty string, never the literal "None"
    assert rows[0]["entry_rule_id"] != "None"
    assert rows[0]["entry_rule_id"] == ""


def test_csv_empty_trades_header_only():
    report = _report(trades=[])
    csv_text = export_trade_ledger_csv(report)
    lines = [l for l in csv_text.strip().splitlines() if l]
    assert len(lines) == 1  # header only


def test_csv_audit_rule_id_fields_present():
    report = _report()
    csv_text = export_trade_ledger_csv(report)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert rows[0]["entry_signal_event_id"] == "2:entry:0:entry-rule-1"
    assert rows[0]["exit_signal_event_id"] == "7:exit:0:exit-rule-1"


# ---------------------------------------------------------------------------
# 7–9. export_equity_curve_csv
# ---------------------------------------------------------------------------

def test_equity_csv_has_correct_headers():
    report = _report()
    csv_text = export_equity_curve_csv(report)
    reader = csv.DictReader(io.StringIO(csv_text))
    assert "bar_index" in (reader.fieldnames or [])
    assert "equity" in (reader.fieldnames or [])
    assert "drawdown_pct" in (reader.fieldnames or [])


def test_equity_csv_drawdown_joined_by_bar_index():
    report = _report()
    csv_text = export_equity_curve_csv(report)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(rows) == 5
    for row in rows:
        assert row["drawdown_pct"] == "0.0"


def test_equity_csv_missing_drawdown_bar_renders_empty():
    report = BacktestReport(
        run=_run_summary(),
        metrics=_metrics(),
        equity_curve=[
            BacktestEquityRecord(
                bar_index=99,
                timestamp=None,
                cash=10_000.0,
                position_quantity=0.0,
                market_value=0.0,
                realized_pnl=0.0,
                unrealized_pnl=0.0,
                equity=10_000.0,
            )
        ],
        drawdown_curve=[],  # no drawdown record for bar 99
        trades=[],
        open_position=None,
        rejections=[],
    )
    csv_text = export_equity_curve_csv(report)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert rows[0]["drawdown_pct"] == ""


# ---------------------------------------------------------------------------
# 10–12. export_report_json
# ---------------------------------------------------------------------------

def test_export_report_json_is_valid_json():
    report = _report()
    json_text = export_report_json(report)
    parsed = json.loads(json_text)
    assert isinstance(parsed, dict)


def test_export_report_json_round_trips():
    report = _report()
    json_text = export_report_json(report)
    restored = BacktestReport.model_validate(json.loads(json_text))
    assert restored.run.run_id == report.run.run_id
    assert restored.metrics.trade_count == report.metrics.trade_count
    assert len(restored.trades) == len(report.trades)


def test_export_report_json_schema_stable():
    """All required top-level keys are always present in exported JSON."""
    report = _report(trades=[], open_position=None)
    parsed = json.loads(export_report_json(report))
    for key in ("run", "metrics", "equity_curve", "drawdown_curve", "trades", "open_position", "rejections"):
        assert key in parsed, f"Missing key in exported JSON: {key}"


# ---------------------------------------------------------------------------
# 13–16. API export endpoints
# ---------------------------------------------------------------------------

from backend.auth.dependencies import get_current_user
from backend.auth.models import User

_TEST_USER = User(
    user_id="test-user-id",
    username="testuser",
    email="test@example.com",
    password_hash="hash",
    created_at="2026-01-01T00:00:00+00:00",
    subscription_status="active",
)


@pytest.fixture()
def export_client():
    """TestClient with auth override for export API tests."""
    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


def _mock_report(run_id: str = _RUN_ID) -> BacktestReport:
    return _report(run_id=run_id)


def test_api_export_trades_csv_200(export_client):
    with patch(
        "backend.api.routes.backtest_runs.load_backtest_report",
        return_value=_mock_report(),
    ):
        resp = export_client.get(f"/backtests/runs/{_RUN_ID}/export/trades")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "attachment" in resp.headers.get("content-disposition", "")
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert len(rows) == 1
    assert rows[0]["status"] == "closed"


def test_api_export_equity_csv_200(export_client):
    with patch(
        "backend.api.routes.backtest_runs.load_backtest_report",
        return_value=_mock_report(),
    ):
        resp = export_client.get(f"/backtests/runs/{_RUN_ID}/export/equity")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert len(rows) == 5


def test_api_export_report_json_200(export_client):
    with patch(
        "backend.api.routes.backtest_runs.load_backtest_report",
        return_value=_mock_report(),
    ):
        resp = export_client.get(f"/backtests/runs/{_RUN_ID}/export/report")
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    parsed = json.loads(resp.text)
    assert parsed["run"]["run_id"] == _RUN_ID


def test_api_export_404_for_unknown_run_id(export_client):
    from backend.api.services.backtest_run_service import BacktestRunError
    with patch(
        "backend.api.routes.backtest_runs.load_backtest_report",
        side_effect=BacktestRunError("not found"),
    ):
        for endpoint in ("trades", "equity", "report"):
            resp = export_client.get(f"/backtests/runs/nonexistent/export/{endpoint}")
            assert resp.status_code == 404, f"{endpoint} should return 404"


# ---------------------------------------------------------------------------
# 17–19. Schema stability and new field presence
# ---------------------------------------------------------------------------

def test_backtest_report_schema_required_fields():
    """BacktestReport must always contain all required top-level sections."""
    report = _report()
    d = report.model_dump()
    for field in ("run", "metrics", "equity_curve", "drawdown_curve", "trades", "open_position", "rejections"):
        assert field in d


def test_run_summary_reproducibility_fields():
    """BacktestRunSummary must expose dataset_start, dataset_end, engine_version."""
    summary = _run_summary()
    assert summary.dataset_start == "2024-01-01T00:00:00+00:00"
    assert summary.dataset_end == "2024-01-10T00:00:00+00:00"
    assert summary.engine_version == "2P.9"


def test_run_summary_reproducibility_fields_optional():
    """dataset_start and dataset_end may be None for legacy reports."""
    summary = BacktestRunSummary(
        run_id="x",
        draft_id="d",
        draft_name="n",
        symbol="X",
        timeframe="1d",
        bars_count=0,
        run_timestamp=_TS,
        status="completed",
        config=_config(),
    )
    assert summary.dataset_start is None
    assert summary.dataset_end is None
    assert summary.engine_version == "2P.9"


def test_trade_record_audit_fields():
    """TradeRecord must expose entry/exit rule_id and signal_event_id."""
    trade = _trade()
    assert trade.entry_rule_id == "entry-rule-1"
    assert trade.exit_rule_id == "exit-rule-1"
    assert trade.entry_signal_event_id == "2:entry:0:entry-rule-1"
    assert trade.exit_signal_event_id == "7:exit:0:exit-rule-1"


def test_trade_record_audit_fields_optional():
    """Audit fields default to None — backward-compatible with older reports."""
    trade = TradeRecord(
        trade_num=1,
        entry_bar_index=0,
        exit_bar_index=1,
        entry_timestamp=None,
        exit_timestamp=None,
        side="long",
        quantity=1.0,
        entry_price=100.0,
        exit_price=110.0,
        entry_commission=0.0,
        exit_commission=0.0,
        entry_slippage=0.0,
        exit_slippage=0.0,
        gross_pnl=10.0,
        net_pnl=10.0,
        return_pct=10.0,
        holding_bars=1,
        equity_after=10_010.0,
    )
    assert trade.entry_rule_id is None
    assert trade.exit_rule_id is None
    assert trade.entry_signal_event_id is None
    assert trade.exit_signal_event_id is None


# ---------------------------------------------------------------------------
# 20. CSV row count matches trade count
# ---------------------------------------------------------------------------

def test_csv_row_count_matches_trades():
    n = 7
    trades = [_trade(trade_num=i + 1) for i in range(n)]
    report = _report(trades=trades, open_position=_open_trade())
    csv_text = export_trade_ledger_csv(report)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(rows) == n + 1  # 7 closed + 1 open


def test_equity_csv_row_count_matches_equity_curve():
    report = _report()
    csv_text = export_equity_curve_csv(report)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(rows) == len(report.equity_curve)
