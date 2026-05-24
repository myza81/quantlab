"""
Long-Only Position Tracker — Phase 2P.6 / updated Phase 2P.7 / updated Phase 2P.8.

Sequential position tracker for a single long-only simulated position.
Phase 2P.7 adds deterministic commission and slippage support.
Phase 2P.8 adds equity-fraction position sizing.

Rules:
    open_long:
        if flat → resolve quantity, adjust price for slippage, apply commission,
                  deduct total cost
        if long → reject with ALREADY_LONG
        if resolved quantity == 0 → reject with ZERO_QUANTITY
        if insufficient cash (after costs) → reject with INSUFFICIENT_CASH

    close_long:
        if long → adjust price for slippage, apply commission, receive net proceeds
        if flat → reject with ALREADY_FLAT

No partial positions.
No multiple simultaneous positions.
No short positions.
No leverage.
No margin.
No latency.
No stochastic fills.

Execution price rules:
    open_long:   adjusted_price = close + slippage   (adverse to buyer)
    close_long:  adjusted_price = close - slippage   (adverse to seller)

Equity-fraction sizing (Phase 2P.8):
    quantity = floor(current_equity × equity_fraction / adjusted_entry_price)
    current_equity = cash (always flat when opening, so no unrealized PnL)

realized_pnl at close is all-in net PnL:
    realized_pnl = (adjusted_close_price - avg_entry_price) × qty
                   - commission_close - entry_commission

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from backend.backtesting.cost_model import (
    CommissionMode,
    SlippageMode,
    apply_slippage,
    build_cost_breakdown,
    compute_commission,
)
from backend.backtesting.models import (
    BacktestRejection,
    BacktestRejectionReason,
    PositionSizeMode,
    SimulatedTrade,
)
from backend.strategy_registry.trade_intents import TradeIntent, TradeIntentAction


# ---------------------------------------------------------------------------
# Mutable simulation state (internal — not serialized)
# ---------------------------------------------------------------------------

@dataclass
class PositionState:
    """
    Mutable internal position, cash, and cost state for one simulation run.

    Not a Pydantic model — mutability is required for sequential processing.
    Initialized once per simulation run; mutated by process_intent().

    Cost configuration fields carry the per-run cost model from config.
    entry_commission records the commission paid at open for realized PnL computation.

    Sizing configuration fields carry the per-run sizing mode from config.
    """
    cash:                    float
    fixed_quantity:          float
    position_quantity:       float = field(default=0.0)
    average_entry_price:     float = field(default=0.0)
    cumulative_realized_pnl: float = field(default=0.0)

    # Cost model (from BacktestSimulationConfig)
    commission_mode:  CommissionMode = field(default=CommissionMode.NONE)
    commission_value: float          = field(default=0.0)
    slippage_mode:    SlippageMode   = field(default=SlippageMode.NONE)
    slippage_value:   float          = field(default=0.0)

    # Tracks commission paid at entry for net realized PnL computation at close
    entry_commission: float = field(default=0.0)

    # Sizing model (Phase 2P.8)
    position_size_mode: PositionSizeMode = field(default=PositionSizeMode.FIXED_QUANTITY)
    equity_fraction:    float            = field(default=0.0)  # 0.0 when mode=FIXED_QUANTITY

    @property
    def is_long(self) -> bool:
        return self.position_quantity > 0.0

    @property
    def is_flat(self) -> bool:
        return self.position_quantity == 0.0


# ---------------------------------------------------------------------------
# Position sizing helper
# ---------------------------------------------------------------------------

def resolve_position_quantity(
    position_size_mode:   PositionSizeMode,
    fixed_quantity:       float,
    equity_fraction:      float,
    current_equity:       float,
    adjusted_entry_price: float,
) -> float:
    """
    Resolve the quantity to open based on the configured sizing mode.

    FIXED_QUANTITY:
        Returns fixed_quantity unchanged (deterministic constant).

    EQUITY_FRACTION:
        quantity = floor(current_equity × equity_fraction / adjusted_entry_price)
        No leverage — equity_fraction must be in (0, 1].
        Returns 0.0 when the budget cannot afford even one unit.

    Args:
        position_size_mode:   FIXED_QUANTITY or EQUITY_FRACTION
        fixed_quantity:       constant unit count (used in FIXED_QUANTITY mode)
        equity_fraction:      fraction of equity to allocate (used in EQUITY_FRACTION mode)
        current_equity:       current portfolio equity at open time (cash when flat)
        adjusted_entry_price: slippage-adjusted entry price

    Returns:
        Resolved quantity as float (always a whole number for EQUITY_FRACTION mode).
    """
    if position_size_mode == PositionSizeMode.FIXED_QUANTITY:
        return fixed_quantity
    # EQUITY_FRACTION
    available_budget = current_equity * equity_fraction
    qty = math.floor(available_budget / adjusted_entry_price)
    return float(qty)


# ---------------------------------------------------------------------------
# Intent processor
# ---------------------------------------------------------------------------

def process_intent(
    intent: TradeIntent,
    price:  float | None,
    state:  PositionState,
) -> tuple[SimulatedTrade | None, BacktestRejection | None]:
    """
    Process a single TradeIntent against the current PositionState.

    Returns (SimulatedTrade, None) on success or (None, BacktestRejection) on failure.
    Mutates state on success.

    Execution price is adjusted for slippage before cash/position are updated.
    Commission is computed on adjusted notional (qty × adjusted_price).

    Args:
        intent: The trade intent to process.
        price:  Raw bar close price; None if price unavailable.
        state:  Current mutable position/cash/cost state (mutated in place on success).

    Returns:
        Tuple of (trade_or_none, rejection_or_none). Exactly one is non-None.
    """
    bar_index = intent.source.bar_index
    timestamp = intent.source.timestamp
    intent_id = intent.intent_id

    if price is None:
        return None, BacktestRejection(
            rejection_id=f"rejection:{intent_id}",
            intent_id=intent_id,
            bar_index=bar_index,
            timestamp=timestamp,
            reason=BacktestRejectionReason.MISSING_PRICE,
            detail=f"No price bar found for bar_index={bar_index}",
        )

    if intent.action == TradeIntentAction.OPEN_LONG:
        return _open_long(intent_id, bar_index, timestamp, price, state)
    elif intent.action == TradeIntentAction.CLOSE_LONG:
        return _close_long(intent_id, bar_index, timestamp, price, state)
    else:
        return None, BacktestRejection(
            rejection_id=f"rejection:{intent_id}",
            intent_id=intent_id,
            bar_index=bar_index,
            timestamp=timestamp,
            reason=BacktestRejectionReason.UNSUPPORTED_ACTION,
            detail=f"Action '{intent.action}' is not supported by the long-only tracker",
        )


def _open_long(
    intent_id: str,
    bar_index: int,
    timestamp: object,
    raw_price: float,
    state:     PositionState,
) -> tuple[SimulatedTrade | None, BacktestRejection | None]:
    if state.is_long:
        return None, BacktestRejection(
            rejection_id=f"rejection:{intent_id}",
            intent_id=intent_id,
            bar_index=bar_index,
            timestamp=timestamp,
            reason=BacktestRejectionReason.ALREADY_LONG,
            detail=(
                f"open_long rejected: already holding {state.position_quantity} units "
                f"at average entry {state.average_entry_price:.4f}"
            ),
        )

    adj_price = apply_slippage("open_long", raw_price, state.slippage_mode, state.slippage_value)

    # Resolve quantity — equity = cash when flat (no unrealized PnL possible)
    sizing_value = (
        state.equity_fraction
        if state.position_size_mode == PositionSizeMode.EQUITY_FRACTION
        else state.fixed_quantity
    )
    qty = resolve_position_quantity(
        position_size_mode=state.position_size_mode,
        fixed_quantity=state.fixed_quantity,
        equity_fraction=state.equity_fraction,
        current_equity=state.cash,
        adjusted_entry_price=adj_price,
    )

    if qty <= 0:
        return None, BacktestRejection(
            rejection_id=f"rejection:{intent_id}",
            intent_id=intent_id,
            bar_index=bar_index,
            timestamp=timestamp,
            reason=BacktestRejectionReason.ZERO_QUANTITY,
            detail=(
                f"open_long rejected: equity_fraction sizing resolved to 0 units "
                f"(equity={state.cash:.4f}, equity_fraction={state.equity_fraction:.6f}, "
                f"adjusted_price={adj_price:.4f})"
            ),
        )

    notional       = qty * adj_price
    commission     = compute_commission(state.commission_mode, state.commission_value, qty, notional)
    total_cash_out = notional + commission

    if total_cash_out > state.cash:
        return None, BacktestRejection(
            rejection_id=f"rejection:{intent_id}",
            intent_id=intent_id,
            bar_index=bar_index,
            timestamp=timestamp,
            reason=BacktestRejectionReason.INSUFFICIENT_CASH,
            detail=(
                f"open_long rejected: total cost={total_cash_out:.4f} "
                f"(notional={notional:.4f} + commission={commission:.4f}) "
                f"exceeds available cash={state.cash:.4f}"
            ),
        )

    cash_before = state.cash
    state.cash               -= total_cash_out
    state.position_quantity   = qty
    state.average_entry_price = adj_price
    state.entry_commission    = commission

    cost_bd = build_cost_breakdown("open_long", qty, raw_price, adj_price, commission)

    return SimulatedTrade(
        trade_id=f"trade:{intent_id}",
        source_intent_id=intent_id,
        action="open_long",
        bar_index=bar_index,
        timestamp=timestamp,
        quantity=qty,
        price=adj_price,
        cash_before=cash_before,
        cash_after=state.cash,
        realized_pnl=None,
        position_after=state.position_quantity,
        cost_breakdown=cost_bd,
        position_size_mode=state.position_size_mode,
        sizing_value=sizing_value,
    ), None


def _close_long(
    intent_id: str,
    bar_index: int,
    timestamp: object,
    raw_price: float,
    state:     PositionState,
) -> tuple[SimulatedTrade | None, BacktestRejection | None]:
    if state.is_flat:
        return None, BacktestRejection(
            rejection_id=f"rejection:{intent_id}",
            intent_id=intent_id,
            bar_index=bar_index,
            timestamp=timestamp,
            reason=BacktestRejectionReason.ALREADY_FLAT,
            detail="close_long rejected: no open long position to close",
        )

    qty          = state.position_quantity
    adj_price    = apply_slippage("close_long", raw_price, state.slippage_mode, state.slippage_value)
    notional     = qty * adj_price
    commission   = compute_commission(state.commission_mode, state.commission_value, qty, notional)
    proceeds     = notional - commission

    # All-in net realized PnL: accounts for entry slippage (via avg_entry_price),
    # exit slippage (via adj_price), and both commissions.
    realized_pnl = (adj_price - state.average_entry_price) * qty - commission - state.entry_commission
    cash_before  = state.cash

    state.cash                   += proceeds
    state.cumulative_realized_pnl += realized_pnl
    state.position_quantity        = 0.0
    state.average_entry_price      = 0.0
    state.entry_commission         = 0.0

    cost_bd = build_cost_breakdown("close_long", qty, raw_price, adj_price, commission)

    sizing_value = (
        state.equity_fraction
        if state.position_size_mode == PositionSizeMode.EQUITY_FRACTION
        else state.fixed_quantity
    )

    return SimulatedTrade(
        trade_id=f"trade:{intent_id}",
        source_intent_id=intent_id,
        action="close_long",
        bar_index=bar_index,
        timestamp=timestamp,
        quantity=qty,
        price=adj_price,
        cash_before=cash_before,
        cash_after=state.cash,
        realized_pnl=realized_pnl,
        position_after=0.0,
        cost_breakdown=cost_bd,
        position_size_mode=state.position_size_mode,
        sizing_value=sizing_value,
    ), None
