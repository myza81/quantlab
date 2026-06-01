"""
Backtest runs API routes.

POST /backtests/runs                              — full pipeline: draft + bars → report
GET  /backtests/runs                              — list user's run history, newest-first
GET  /backtests/runs/{run_id}/report              — retrieve persisted report
POST /backtests/runs/{run_id}/promote-draft       — promote draft to 'backtested' (Phase R3)
GET  /backtests/runs/{run_id}/export/trades       — trade ledger CSV download
GET  /backtests/runs/{run_id}/export/equity       — equity+drawdown CSV download
GET  /backtests/runs/{run_id}/export/report       — full report JSON download
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, Response

from backend.api.dependencies import get_backtest_storage_path, get_draft_repository
from backend.api.schemas.backtest_runs import (
    BacktestReport,
    BacktestRunListItem,
    BacktestRunRequest,
    BacktestRunResponse,
    PromoteDraftRequest,
)
from backend.api.schemas.drafts import DraftResponse
from backend.api.services.backtest_run_service import (
    BacktestAccessDeniedError,
    BacktestRunError,
    create_backtest_run,
    list_backtest_runs,
    load_backtest_report,
)
from backend.api.services.draft_service import (
    LifecyclePromotionError,
    promote_draft_to_backtested,
)
from backend.api.services.export_service import (
    export_equity_curve_csv,
    export_report_json,
    export_trade_ledger_csv,
)
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event
from backend.core.config import settings
from backend.core.request_validation import validate_bar_count, validate_uuid_id
from backend.strategy_registry.draft_repository import DraftNotFoundError, DraftRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.post("/runs", response_model=BacktestRunResponse)
def create_run(
    request:      BacktestRunRequest,
    repository:   DraftRepository = Depends(get_draft_repository),
    storage:      Path = Depends(get_backtest_storage_path),
    current_user: User = Depends(require_active_subscription),
) -> BacktestRunResponse:
    """
    Run the full backtest pipeline for a saved strategy draft.

    Accepts OHLCV bars (already loaded by the chart page) + draft_id + simulation config.
    Returns the full backtest report including metrics, equity curve, and trade ledger.
    """
    bar_count = len(request.bars)
    try:
        validate_bar_count(bar_count, settings.max_backtest_bars)
    except ValueError as exc:
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.OVERSIZED_PAYLOAD_REJECTED,
            details={"bar_count": bar_count, "max_bars": settings.max_backtest_bars, "endpoint": "/backtests/runs"},
        ))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return create_backtest_run(request, repository, storage=storage, user_id=current_user.user_id)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BacktestRunError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/runs", response_model=list[BacktestRunListItem])
def list_runs(
    limit:        int  = 50,
    storage:      Path = Depends(get_backtest_storage_path),
    current_user: User = Depends(require_active_subscription),
) -> list[BacktestRunListItem]:
    """
    List all backtest runs owned by the authenticated user, newest-first.

    Returns lightweight metadata only — no equity curves, trade ledgers, or
    drawdown series.  Clients use run_id from each item to reopen the full
    report via GET /backtests/runs/{run_id}/report.

    limit: maximum number of results (default 50, max 200).
    """
    capped_limit = min(max(1, limit), 200)
    return list_backtest_runs(storage, owner_user_id=current_user.user_id, limit=capped_limit)


@router.get("/runs/{run_id}/report", response_model=BacktestReport)
def get_report(
    run_id: str,
    storage: Path = Depends(get_backtest_storage_path),
    current_user: User = Depends(require_active_subscription),
) -> BacktestReport:
    """Retrieve a previously persisted backtest report by run_id."""
    try:
        validate_uuid_id(run_id, "run_id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return load_backtest_report(run_id, storage=storage, owner_user_id=current_user.user_id)
    except BacktestAccessDeniedError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BacktestRunError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/promote-draft", response_model=DraftResponse)
def promote_draft(
    run_id: str,
    request: PromoteDraftRequest,
    repository: DraftRepository = Depends(get_draft_repository),
    storage: Path = Depends(get_backtest_storage_path),
    current_user: User = Depends(require_active_subscription),
) -> DraftResponse:
    """
    Promote a strategy draft to 'backtested' lifecycle status.

    Requires a completed backtest run as evidence — the run must have been
    executed against the specified draft by the same authenticated user.
    This is the ONLY supported path for promoting a draft to 'backtested';
    the general PATCH /drafts/{id} endpoint does not gate lifecycle changes
    on backtest evidence.

    Returns the updated DraftResponse with lifecycle_status='backtested'.
    """
    try:
        validate_uuid_id(run_id, "run_id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return promote_draft_to_backtested(
            draft_id=request.draft_id,
            run_id=run_id,
            repository=repository,
            storage=storage,
            owner_id=current_user.user_id,
            notes=request.notes,
        )
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BacktestAccessDeniedError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BacktestRunError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LifecyclePromotionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Export endpoints
# ---------------------------------------------------------------------------

@router.get("/runs/{run_id}/export/trades")
def export_trades_csv(
    run_id: str,
    storage: Path = Depends(get_backtest_storage_path),
    current_user: User = Depends(require_active_subscription),
) -> PlainTextResponse:
    """Download trade ledger (all closed + open positions) as CSV."""
    try:
        validate_uuid_id(run_id, "run_id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        report = load_backtest_report(run_id, storage=storage, owner_user_id=current_user.user_id)
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
    storage: Path = Depends(get_backtest_storage_path),
    current_user: User = Depends(require_active_subscription),
) -> PlainTextResponse:
    """Download per-bar equity curve with drawdown percentage as CSV."""
    try:
        validate_uuid_id(run_id, "run_id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        report = load_backtest_report(run_id, storage=storage, owner_user_id=current_user.user_id)
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
    storage: Path = Depends(get_backtest_storage_path),
    current_user: User = Depends(require_active_subscription),
) -> Response:
    """Download the full backtest report as JSON."""
    try:
        validate_uuid_id(run_id, "run_id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        report = load_backtest_report(run_id, storage=storage, owner_user_id=current_user.user_id)
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
