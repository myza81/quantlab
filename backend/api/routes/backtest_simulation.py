"""
Backtest simulation API route — Phase 2P.6.

POST /backtests/simulate
    Input:  BacktestSimulationRequest (intent_batch + price_bars + config)
    Output: BacktestSimulationResult

No live execution. No broker integration. No strategy runtime coupling.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.api.schemas.backtest_simulation import BacktestSimulationRequest
from backend.api.services.backtest_simulation_service import simulate_backtest
from backend.backtesting.models import BacktestSimulationResult

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.post("/simulate", response_model=BacktestSimulationResult)
def simulate(request: BacktestSimulationRequest) -> BacktestSimulationResult:
    """
    Run a deterministic long-only backtest simulation.

    Accepts a TradeIntentBatch, price bars, and simulation config.
    Returns a full simulation result including trades, equity curve, and rejections.

    Execution assumptions:
    - execution_price = bar close
    - long-only, fixed quantity sizing
    - no slippage, no fees
    """
    try:
        return simulate_backtest(
            intent_batch=request.intent_batch,
            price_bars=request.price_bars,
            config=request.config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
