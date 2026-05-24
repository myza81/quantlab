"""
Backtest Simulation Domain Models — Phase 2P.6 / updated Phase 2P.7 / updated Phase 2P.8.

Foundational models for the long-only backtest simulation layer.
Phase 2P.7 adds deterministic cost modeling (commission + slippage).
Phase 2P.8 adds equity-fraction position sizing.

Critical separations maintained:
    TradeIntent    ≠  Order
    TradeIntent    ≠  SimulatedTrade
    SimulatedTrade ≠  BrokerFill
    SimulatedTrade ≠  LiveTrade

Execution assumptions:
    execution_price = bar close ± slippage  (direction-aware)
    commission applied per trade
    No order book. No latency. No stochastic fills.

Scope constraints — NOT implemented:
    shorting, leverage, margin, partial fills, market impact,
    multi-asset portfolio, broker/execution integration,
    advanced analytics (drawdown series, Sharpe, benchmark),
    risk-based sizing, stop-loss sizing, volatility targeting,
    Kelly sizing, portfolio allocation

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from backend.backtesting.cost_model import (
    CommissionMode,
    SlippageMode,
    TradeCostBreakdown,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class PositionSizeMode(str, Enum):
    """
    Position sizing mode.

    FIXED_QUANTITY:  Open position with a fixed number of units regardless of equity.
    EQUITY_FRACTION: Open position sized as a fraction of current equity.
                     quantity = floor(equity × equity_fraction / adjusted_entry_price)
    """
    FIXED_QUANTITY  = "fixed_quantity"
    EQUITY_FRACTION = "equity_fraction"


class BacktestSimulationConfig(BaseModel):
    """
    Backtest simulation configuration.

    Sizing modes (Phase 2P.8):
        fixed_quantity:   constant unit count per trade (default, backward-compatible)
        equity_fraction:  quantity = floor(equity × equity_fraction / adjusted_price)
                          No leverage — equity_fraction must be in (0, 1].

    Cost models (Phase 2P.7):
        commission_mode:  NONE, FIXED, or PERCENTAGE
        commission_value: flat amount per trade (FIXED) or fraction (PERCENTAGE)
        slippage_mode:    NONE, FIXED, or PERCENTAGE
        slippage_value:   per-share amount (FIXED) or fraction (PERCENTAGE)

    Not supported:
        tiered fees, maker/taker, latency, stochastic fills, order book,
        risk-based sizing, stop-loss sizing, leverage, margin, multiple positions
    """
    model_config = ConfigDict(frozen=True)

    initial_cash:       float = 10_000.0
    position_size_mode: PositionSizeMode = PositionSizeMode.FIXED_QUANTITY
    fixed_quantity:     float = 1.0
    equity_fraction:    float | None = None  # required when mode=EQUITY_FRACTION

    # Cost model — all default to zero-cost (backward-compatible)
    commission_mode:  CommissionMode = CommissionMode.NONE
    commission_value: float = 0.0
    slippage_mode:    SlippageMode = SlippageMode.NONE
    slippage_value:   float = 0.0

    @field_validator("initial_cash")
    @classmethod
    def initial_cash_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"initial_cash must be positive; got {v}")
        return v

    @field_validator("fixed_quantity")
    @classmethod
    def fixed_quantity_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"fixed_quantity must be positive; got {v}")
        return v

    @field_validator("commission_value", "slippage_value")
    @classmethod
    def cost_values_must_be_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"cost values must be non-negative; got {v}")
        return v

    @model_validator(mode="after")
    def validate_sizing_config(self) -> "BacktestSimulationConfig":
        if self.position_size_mode == PositionSizeMode.EQUITY_FRACTION:
            if self.equity_fraction is None:
                raise ValueError(
                    "equity_fraction is required when position_size_mode=equity_fraction"
                )
            if not (0 < self.equity_fraction <= 1.0):
                raise ValueError(
                    f"equity_fraction must be in (0, 1]; got {self.equity_fraction}"
                )
        return self


# ---------------------------------------------------------------------------
# Price bar input (for simulation use)
# ---------------------------------------------------------------------------

class SimulationPriceBar(BaseModel):
    """
    Minimal bar record supplying price to the simulation engine.

    close is the raw bar close; the cost model adjusts execution price
    by applying slippage before any trade is simulated.
    """
    model_config = ConfigDict(frozen=True)

    bar_index: int
    timestamp: datetime | None = None
    close:     float

    @field_validator("close")
    @classmethod
    def close_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"close price must be positive; got {v}")
        return v


# ---------------------------------------------------------------------------
# Rejection
# ---------------------------------------------------------------------------

class BacktestRejectionReason(str, Enum):
    """Enumeration of reasons a trade intent may be rejected by the simulator."""
    ALREADY_LONG       = "already_long"       # open_long while position open
    ALREADY_FLAT       = "already_flat"       # close_long while flat
    INSUFFICIENT_CASH  = "insufficient_cash"  # cash < total cost (price + costs)
    MISSING_PRICE      = "missing_price"      # no price bar for intent's bar_index
    UNSUPPORTED_ACTION = "unsupported_action" # action not handled by long-only tracker
    ZERO_QUANTITY      = "zero_quantity"      # equity_fraction sizing resolved to 0 units


class BacktestRejection(BaseModel):
    """
    Record of a trade intent rejected by the simulation engine.

    Rejections are explicit — they are never silently ignored.
    Captured for full audit traceability.
    """
    model_config = ConfigDict(frozen=True)

    rejection_id: str                      # deterministic: f"rejection:{intent_id}"
    intent_id:    str
    bar_index:    int
    timestamp:    datetime | None
    reason:       BacktestRejectionReason
    detail:       str                      # human-readable explanation


# ---------------------------------------------------------------------------
# Simulated trade
# ---------------------------------------------------------------------------

class SimulatedTrade(BaseModel):
    """
    Record of a simulated position change triggered by a trade intent.

    Does NOT represent:
        - real orders
        - broker fills
        - execution instructions
        - live trade records

    price is the adjusted execution price (after slippage).
    cost_breakdown provides full audit of slippage and commission.

    realized_pnl is all-in net PnL (includes both commissions and slippage):
        realized_pnl = (close_adjusted_price - entry_adjusted_price) × qty
                       - commission_close - commission_open
    This is populated only on close trades; None for open trades.

    position_after records the quantity held after this trade (0.0 for closes).

    Sizing audit fields (Phase 2P.8):
        position_size_mode: the sizing mode used for this trade
        sizing_value:       the configured sizing parameter
                            (fixed_quantity value for FIXED_QUANTITY mode,
                             equity_fraction value for EQUITY_FRACTION mode)
    quantity is the resolved (actual) units traded.
    """
    model_config = ConfigDict(frozen=True)

    trade_id:           str                   # deterministic: f"trade:{source_intent_id}"
    source_intent_id:   str
    action:             Literal["open_long", "close_long"]
    bar_index:          int
    timestamp:          datetime | None
    quantity:           float                 # resolved (actual) units traded
    price:              float                 # adjusted execution price (after slippage)
    cash_before:        float
    cash_after:         float
    realized_pnl:       float | None          # None for open; all-in net PnL for close
    position_after:     float                 # quantity held after trade
    cost_breakdown:     TradeCostBreakdown    # explicit per-trade cost audit

    # Sizing audit (Phase 2P.8)
    position_size_mode: PositionSizeMode      # sizing mode used
    sizing_value:       float                 # configured sizing parameter


# ---------------------------------------------------------------------------
# Equity curve point
# ---------------------------------------------------------------------------

class BacktestEquityPoint(BaseModel):
    """
    Single point on the equity curve — one produced per bar.

    Equity = cash + market_value_of_open_position.
    Market value uses the bar's raw close price (unrealized exit not adjusted).

    realized_pnl is cumulative all-in net PnL (includes commissions).
    unrealized_pnl reflects paper gain/loss on current position at raw close,
    measured from adjusted entry price (no hypothetical exit cost deducted).
    """
    model_config = ConfigDict(frozen=True)

    bar_index:         int
    timestamp:         datetime | None
    cash:              float
    position_quantity: float
    market_value:      float    # position_quantity × raw_close
    realized_pnl:      float    # cumulative all-in net realized PnL
    unrealized_pnl:    float    # paper PnL from adjusted entry to raw close
    equity:            float    # cash + market_value


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

class BacktestSimulationSummary(BaseModel):
    """
    Aggregated summary for a completed BacktestSimulationResult.

    Includes basic capital/PnL tracking and aggregate cost accounting.
    No advanced analytics (Sharpe, drawdown series, benchmark comparison).
    """
    model_config = ConfigDict(frozen=True)

    total_bars:           int
    total_trades:         int
    open_long_trades:     int
    close_long_trades:    int
    total_rejections:     int
    initial_cash:         float
    final_cash:           float
    final_equity:         float
    total_realized_pnl:   float
    final_unrealized_pnl: float
    peak_equity:          float   # highest equity across all bars
    trough_equity:        float   # lowest equity across all bars

    # Cost aggregates (Phase 2P.7)
    total_commission_paid: float  # sum of all commission_paid across trades
    total_slippage_paid:   float  # sum of all slippage_paid across trades
    total_cost_paid:       float  # total_commission_paid + total_slippage_paid
    average_cost_per_trade: float  # total_cost_paid / total_trades (0.0 if no trades)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

class BacktestSimulationResult(BaseModel):
    """
    Complete result of one backtest simulation run.

    Contains:
        - full ordered trade record (with per-trade cost breakdown)
        - per-bar equity curve
        - rejected intent log
        - aggregated summary (including cost totals)

    Does NOT contain:
        - broker fields
        - order IDs
        - live execution artifacts
        - compliance decisions
        - PnL attribution
    """
    model_config = ConfigDict(frozen=True)

    plan_draft_id: str | None
    config:        BacktestSimulationConfig
    trades:        tuple[SimulatedTrade, ...]
    equity_curve:  tuple[BacktestEquityPoint, ...]
    rejections:    tuple[BacktestRejection, ...]
    summary:       BacktestSimulationSummary
