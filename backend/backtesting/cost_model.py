"""
Deterministic Backtest Cost Model — Phase 2P.7.

Provides deterministic commission and slippage models for backtest simulation.
All models are configurable, explicit, and produce reproducible results.

Supported commission models:
    NONE        — zero commission per trade
    FIXED       — flat monetary amount per trade (e.g. $1.00)
    PERCENTAGE  — percentage of notional (e.g. 0.001 = 0.1%)

Supported slippage models:
    NONE        — execution at bar close price exactly
    FIXED       — fixed monetary amount per share adverse to direction
    PERCENTAGE  — percentage of close price adverse to direction

Execution price adjustment rules:
    open_long:   adjusted_price = close + slippage   (we pay more to buy)
    close_long:  adjusted_price = close - slippage   (we receive less when selling)

No randomness. No stochastic models. No latency. No order book simulation.
No partial fills. No volume constraints. No market impact.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Commission model
# ---------------------------------------------------------------------------

class CommissionMode(str, Enum):
    """Commission model for trade cost accounting."""
    NONE       = "none"        # zero commission
    FIXED      = "fixed"       # flat amount per trade (e.g. $1.00)
    PERCENTAGE = "percentage"  # fraction of notional (e.g. 0.001 = 0.1%)


# ---------------------------------------------------------------------------
# Slippage model
# ---------------------------------------------------------------------------

class SlippageMode(str, Enum):
    """Slippage model for execution price adjustment."""
    NONE       = "none"        # no slippage — fill at bar close
    FIXED      = "fixed"       # fixed monetary amount per share
    PERCENTAGE = "percentage"  # fraction of bar close price


# ---------------------------------------------------------------------------
# Trade cost breakdown (per-trade, attached to SimulatedTrade)
# ---------------------------------------------------------------------------

class TradeCostBreakdown(BaseModel):
    """
    Explicit cost breakdown for a single simulated trade.

    Attached to each SimulatedTrade for full audit traceability.
    All values are non-negative (costs are never negative).

    Fields:
        gross_value:      quantity × adjusted_execution_price
        commission_paid:  commission charged for this trade
        slippage_paid:    adverse price movement due to slippage × quantity
        total_cost:       commission_paid + slippage_paid
        net_cash_impact:  actual cash change (positive = cash in, negative = cash out)
    """
    model_config = ConfigDict(frozen=True)

    raw_price:       float  # bar close (before slippage adjustment)
    adjusted_price:  float  # actual execution price after slippage
    gross_value:     float  # quantity × adjusted_price
    commission_paid: float  # commission charged
    slippage_paid:   float  # |adjusted_price - raw_price| × quantity
    total_cost:      float  # commission_paid + slippage_paid
    net_cash_impact: float  # actual signed cash impact (negative for opens)


# ---------------------------------------------------------------------------
# Computation helpers
# ---------------------------------------------------------------------------

def compute_slippage_per_unit(
    mode:  SlippageMode,
    value: float,
    price: float,
) -> float:
    """
    Compute the slippage amount per share/unit for a given bar close price.

    Args:
        mode:  NONE, FIXED, or PERCENTAGE
        value: slippage value (monetary amount or fraction)
        price: raw bar close price

    Returns:
        Slippage amount per unit (always non-negative).
    """
    if mode == SlippageMode.NONE:
        return 0.0
    if mode == SlippageMode.FIXED:
        return value
    if mode == SlippageMode.PERCENTAGE:
        return price * value
    return 0.0  # unreachable — exhaustive enum


def apply_slippage(
    action:         Literal["open_long", "close_long"],
    raw_price:      float,
    slippage_mode:  SlippageMode,
    slippage_value: float,
) -> float:
    """
    Apply deterministic slippage to the bar close price.

    Direction-aware:
        open_long:   adjusted_price = close + slippage_per_unit  (pay more)
        close_long:  adjusted_price = close - slippage_per_unit  (receive less)

    Args:
        action:         "open_long" or "close_long"
        raw_price:      bar close price
        slippage_mode:  slippage model
        slippage_value: slippage parameter (monetary or fraction)

    Returns:
        Adjusted execution price (always positive for valid inputs).
    """
    slip = compute_slippage_per_unit(slippage_mode, slippage_value, raw_price)
    if action == "open_long":
        return raw_price + slip
    else:  # close_long
        return max(raw_price - slip, 0.0)  # floor at zero (edge case guard)


def compute_commission(
    mode:     CommissionMode,
    value:    float,
    qty:      float,
    notional: float,
) -> float:
    """
    Compute the commission for a single trade.

    Args:
        mode:     NONE, FIXED, or PERCENTAGE
        value:    commission parameter (monetary amount or fraction)
        qty:      quantity traded (used for FIXED mode per-trade semantics)
        notional: qty × adjusted_price (used for PERCENTAGE)

    Returns:
        Commission amount (always non-negative).
    """
    if mode == CommissionMode.NONE:
        return 0.0
    if mode == CommissionMode.FIXED:
        return value  # flat per trade, not per share
    if mode == CommissionMode.PERCENTAGE:
        return notional * value
    return 0.0  # unreachable — exhaustive enum


def build_cost_breakdown(
    action:           Literal["open_long", "close_long"],
    qty:              float,
    raw_price:        float,
    adjusted_price:   float,
    commission_paid:  float,
) -> TradeCostBreakdown:
    """
    Build a TradeCostBreakdown for a completed simulated trade.

    Args:
        action:           "open_long" or "close_long"
        qty:              quantity traded
        raw_price:        bar close price (before slippage)
        adjusted_price:   execution price (after slippage)
        commission_paid:  commission for this trade

    Returns:
        Fully populated TradeCostBreakdown (all values non-negative except net_cash_impact).
    """
    gross_value    = qty * adjusted_price
    slippage_paid  = abs(adjusted_price - raw_price) * qty
    total_cost     = commission_paid + slippage_paid

    if action == "open_long":
        net_cash_impact = -(gross_value + commission_paid)  # cash out
    else:  # close_long
        net_cash_impact = gross_value - commission_paid     # cash in

    return TradeCostBreakdown(
        raw_price=raw_price,
        adjusted_price=adjusted_price,
        gross_value=gross_value,
        commission_paid=commission_paid,
        slippage_paid=slippage_paid,
        total_cost=total_cost,
        net_cash_impact=net_cash_impact,
    )
