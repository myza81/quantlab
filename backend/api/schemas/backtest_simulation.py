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
        config:       Simulation configuration.

    The simulator uses bar close as execution price for all trades.
    Price bars are sorted by bar_index inside the simulator.
    """
    model_config = ConfigDict(extra="forbid")

    intent_batch: TradeIntentBatch
    price_bars:   list[SimulationPriceBar]
    config:       BacktestSimulationConfig = BacktestSimulationConfig()
