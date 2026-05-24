"""
Backtest simulation service — Phase 2P.6.

Thin orchestration layer between the API route and the simulation engine.
Validates inputs and delegates to run_simulation().
"""
from __future__ import annotations

from backend.backtesting.models import (
    BacktestSimulationConfig,
    BacktestSimulationResult,
    SimulationPriceBar,
)
from backend.backtesting.simulator import run_simulation
from backend.strategy_registry.trade_intents import TradeIntentBatch


def simulate_backtest(
    intent_batch: TradeIntentBatch,
    price_bars:   list[SimulationPriceBar],
    config:       BacktestSimulationConfig,
) -> BacktestSimulationResult:
    """
    Orchestrate a backtest simulation run.

    Validates that price_bars is non-empty, then delegates to run_simulation().

    Does NOT:
        - regenerate signals from semantics
        - call strategy runtime
        - interface with brokers or execution systems
    """
    return run_simulation(
        intent_batch=intent_batch,
        price_bars=price_bars,
        config=config,
    )
