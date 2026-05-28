"""
Backtest runs API routes.

POST /backtests/runs                          — full pipeline: draft + bars → report
GET  /backtests/runs/{run_id}/report          — retrieve persisted report
GET  /backtests/runs/{run_id}/export/trades   — trade ledger CSV download
GET  /backtests/runs/{run_id}/export/equity   — equity+drawdown CSV download
GET  /backtests/runs/{run_id}/export/report   — full report JSON download
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, Response

from backend.api.schemas.backtest_runs import (
    BacktestReport,
    BacktestRunRequest,
    BacktestRunResponse,
)
from backend.api.services.backtest_run_service import (
    BacktestAccessDeniedError,
    BacktestRunError,
    create_backtest_run,
    load_backtest_report,
)
from backend.api.services.export_service import (
    export_equity_curve_csv,
    export_report_json,
    export_trade_ledger_csv,
)
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.strategy_registry.draft_repository import DraftNotFoundError, DraftRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtests", tags=["backtests"])

_DEFAULT_DRAFT_STORAGE = Path("storage/strategy_drafts")


def get_draft_repository() -> DraftRepository:
    return DraftRepository(_DEFAULT_DRAFT_STORAGE)


@router.post("/runs", response_model=BacktestRunResponse)
def create_run(
    request:      BacktestRunRequest,
    repository:   DraftRepository = Depends(get_draft_repository),
    current_user: User = Depends(require_active_subscription),
) -> BacktestRunResponse:
    """
    Run the full backtest pipeline for a saved strategy draft.

    Accepts OHLCV bars (already loaded by the chart page) + draft_id + simulation config.
    Returns the full backtest report including metrics, equity curve, and trade ledger.
    """
    try:
        return create_backtest_run(request, repository, user_id=current_user.user_id)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BacktestRunError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/runs/{run_id}/report", response_model=BacktestReport)
def get_report(
    run_id: str,
    current_user: User = Depends(require_active_subscription),
) -> BacktestReport:
    """Retrieve a previously persisted backtest report by run_id."""
    try:
        return load_backtest_report(run_id, owner_user_id=current_user.user_id)
    except BacktestAccessDeniedError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BacktestRunError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Export endpoints
# ---------------------------------------------------------------------------

@router.get("/runs/{run_id}/export/trades")
def export_trades_csv(
    run_id: str,
    current_user: User = Depends(require_active_subscription),
) -> PlainTextResponse:
    """Download trade ledger (all closed + open positions) as CSV."""
    try:
        report = load_backtest_report(run_id, owner_user_id=current_user.user_id)
    except BacktestAccessDeniedError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BacktestRunError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    csv_text = export_trade_ledger_csv(report)
    filename = f"trades_{run_id[:8]}.csv"
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs/{run_id}/export/equity")
def export_equity_csv(
    run_id: str,
    current_user: User = Depends(require_active_subscription),
) -> PlainTextResponse:
    """Download per-bar equity curve with drawdown percentage as CSV."""
    try:
        report = load_backtest_report(run_id, owner_user_id=current_user.user_id)
    except BacktestAccessDeniedError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BacktestRunError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    csv_text = export_equity_curve_csv(report)
    filename = f"equity_{run_id[:8]}.csv"
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs/{run_id}/export/report")
def export_report(
    run_id: str,
    current_user: User = Depends(require_active_subscription),
) -> Response:
    """Download the full backtest report as JSON."""
    try:
        report = load_backtest_report(run_id, owner_user_id=current_user.user_id)
    except BacktestAccessDeniedError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BacktestRunError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    json_text = export_report_json(report)
    filename = f"backtest_{run_id[:8]}.json"
    return Response(
        content=json_text,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
