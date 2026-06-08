"""
API schemas for backtest simulation endpoint — Phase 2P.6.

Wraps domain models into the API request contract.
Response type is the domain BacktestSimulationResult directly.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from backend.backtesting.models import (
    BacktestSimulationConfig,
    SimulationPriceBar,
)
from backend.strategy_registry.trade_intents import TradeIntentBatch


class BacktestSimulationRequest(BaseModel):
    """
    Request body for POST /backtests/simulate.

    Accepts:
        intent_batch: Ordered trade intent batch (from extract-trade-intents).
        price_bars:   Price bars covering the simulation period; must include all
                      bars referenced by intent bar_index values.
                      For NEXT_BAR_OPEN (default), each bar must include 'open'.
        config:       Simulation configuration (including execution_model).

    Default execution model is NEXT_BAR_OPEN: signal on Bar N fills at Bar N+1 open.
    Use config.execution_model = "same_bar_close" to opt into same-bar-close fills.
    Price bars are sorted by bar_index inside the simulator.
    """
    model_config = ConfigDict(extra="forbid")

    intent_batch: TradeIntentBatch
    price_bars:   list[SimulationPriceBar]
    config:       BacktestSimulationConfig = BacktestSimulationConfig()
