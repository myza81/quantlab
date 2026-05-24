"""
Backtest runs API routes — Phase 2P.9.

POST /backtests/runs                  — full pipeline: draft + bars → report
GET  /backtests/runs/{run_id}/report  — retrieve persisted report
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from backend.api.schemas.backtest_runs import (
    BacktestReport,
    BacktestRunRequest,
    BacktestRunResponse,
)
from backend.api.services.backtest_run_service import (
    BacktestRunError,
    create_backtest_run,
    load_backtest_report,
)
from backend.strategy_registry.draft_repository import DraftRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtests", tags=["backtests"])

_DEFAULT_DRAFT_STORAGE = Path("storage/strategy_drafts")


def get_draft_repository() -> DraftRepository:
    return DraftRepository(_DEFAULT_DRAFT_STORAGE)


@router.post("/runs", response_model=BacktestRunResponse)
def create_run(
    request:    BacktestRunRequest,
    repository: DraftRepository = Depends(get_draft_repository),
) -> BacktestRunResponse:
    """
    Run the full backtest pipeline for a saved strategy draft.

    Accepts OHLCV bars (already loaded by the chart page) + draft_id + simulation config.
    Returns the full backtest report including metrics, equity curve, and trade ledger.
    """
    try:
        return create_backtest_run(request, repository)
    except BacktestRunError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/runs/{run_id}/report", response_model=BacktestReport)
def get_report(run_id: str) -> BacktestReport:
    """Retrieve a previously persisted backtest report by run_id."""
    try:
        return load_backtest_report(run_id)
    except BacktestRunError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
