"""
Backtest simulation API route — Phase 2P.6.

POST /backtests/simulate
    Input:  BacktestSimulationRequest (intent_batch + price_bars + config)
    Output: BacktestSimulationResult

No live execution. No broker integration. No strategy runtime coupling.

Phase 3S-B: requires require_active_subscription — compute-heavy simulation
primitive; must not be publicly callable.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.api.schemas.backtest_simulation import BacktestSimulationRequest
from backend.api.services.backtest_simulation_service import simulate_backtest
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.backtesting.models import BacktestSimulationResult
from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event
from backend.core.config import settings
from backend.core.request_validation import validate_bar_count

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.post("/simulate", response_model=BacktestSimulationResult)
def simulate(
    request: BacktestSimulationRequest,
    current_user: User = Depends(require_active_subscription),
) -> BacktestSimulationResult:
    """
    Run a deterministic long-only backtest simulation.

    Accepts a TradeIntentBatch, price bars, and simulation config.
    Returns a full simulation result including trades, equity curve, and rejections.

    Execution assumptions:
    - execution_price = bar close
    - long-only, fixed quantity sizing
    - no slippage, no fees
    """
    bar_count = len(request.price_bars)
    try:
        validate_bar_count(bar_count, settings.max_backtest_bars)
    except ValueError as exc:
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.OVERSIZED_PAYLOAD_REJECTED,
            details={"bar_count": bar_count, "max_bars": settings.max_backtest_bars, "endpoint": "/backtests/simulate"},
        ))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return simulate_backtest(
            intent_batch=request.intent_batch,
            price_bars=request.price_bars,
            config=request.config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
