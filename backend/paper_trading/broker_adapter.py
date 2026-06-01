"""
PaperBrokerAdapter — Phase 4E.2.

Pure, stateless adapter for creating paper trading execution artifacts.

Responsibilities in this phase:
  - Compute fill price (gross price ± slippage) for BUY and SELL orders
  - Compute fee (flat or percentage of gross value)
  - Compute fill quantity from SimulationAssumptions + current equity
  - Create PaperOrder (PENDING_FILL) for NEXT_BAR_OPEN timing
  - Build PaperFill + updated PaperOrder (FILLED) given bar price
  - Create PaperOrder (REJECTED) for intent validation failures

What this module does NOT do:
  - Mutate any store or repository
  - Evaluate strategy signals or rules
  - Update PaperAccount balance or equity
  - Update PaperPosition state
  - Execute a full run cycle (Phase 4E.3)
  - Communicate with any real broker or exchange

Statelessness invariant: every public method is a @staticmethod.  No instance
state is held.  All inputs are passed explicitly as arguments.  This makes the
adapter trivially testable and safe to use from concurrent service workers.

Fill simulation transparency: every computed fill carries gross_price,
slippage, fill_price, gross_value, fee, net_value so a reviewer can
recompute the fill from the PaperFill record alone.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.backtesting
    backend.api
    backend.data_providers
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone

from backend.paper_trading.execution_models import (
    ExecutionReason,
    OrderDirection,
    PaperFill,
    PaperOrder,
    PaperOrderStatus,
)
from backend.paper_trading.models import (
    FeeMode,
    FillTimingModel,
    PositionSizeMode,
    SimulationAssumptions,
    SlippageMode,
)


class PaperBrokerAdapter:
    """
    Stateless simulation adapter.

    All methods are @staticmethod — no instance is required.
    Caller is responsible for persisting returned model objects.
    """

    # ------------------------------------------------------------------
    # Fill price computation
    # ------------------------------------------------------------------

    @staticmethod
    def compute_fill_price(
        direction: OrderDirection,
        gross_price: float,
        assumptions: SimulationAssumptions,
    ) -> tuple[float, float]:
        """
        Compute the net fill price and slippage amount.

        Slippage is adverse:
          BUY  → gross_price + slippage  (you pay more)
          SELL → gross_price − slippage  (you receive less; floored at 0)

        Returns:
            (net_fill_price, slippage_in_price_units)
        """
        mode  = assumptions.slippage_mode
        value = assumptions.slippage_value

        if mode == SlippageMode.NONE or value == 0.0:
            return gross_price, 0.0

        if mode == SlippageMode.FIXED:
            slippage_amount = value
        else:  # PERCENTAGE
            slippage_amount = gross_price * value

        if direction == OrderDirection.BUY:
            net_price = gross_price + slippage_amount
        else:
            net_price = max(0.0, gross_price - slippage_amount)

        return net_price, slippage_amount

    # ------------------------------------------------------------------
    # Fee computation
    # ------------------------------------------------------------------

    @staticmethod
    def compute_fee(
        quantity: int,
        gross_price: float,
        assumptions: SimulationAssumptions,
    ) -> float:
        """
        Compute the fee for a fill in currency units.

        FLAT:       fee = fee_value  (fixed per trade)
        PERCENTAGE: fee = quantity × gross_price × fee_value
                    (percentage of gross transaction value)
        NONE:       fee = 0.0

        Uses gross_price (pre-slippage) as the fee base, matching how
        most brokerage commissions are calculated (on notional value).
        """
        mode  = assumptions.fee_mode
        value = assumptions.fee_value

        if mode == FeeMode.NONE or value == 0.0:
            return 0.0
        if mode == FeeMode.FLAT:
            return value
        # PERCENTAGE
        return quantity * gross_price * value

    # ------------------------------------------------------------------
    # Quantity computation
    # ------------------------------------------------------------------

    @staticmethod
    def compute_quantity(
        assumptions: SimulationAssumptions,
        fill_price: float,
        current_equity: float,
    ) -> int:
        """
        Compute the integer fill quantity from SimulationAssumptions.

        Returns 0 if the computed quantity is < 1 (caller should reject the order
        with rejection_reason = "quantity_resolved_to_zero").

        FIXED_QUANTITY:  quantity = floor(position_size_value)
        EQUITY_FRACTION: quantity = floor(equity × fraction / fill_price)
        FIXED_CASH:      quantity = floor(cash_amount / fill_price)
        """
        mode  = assumptions.position_size_mode
        value = assumptions.position_size_value

        if fill_price <= 0:
            return 0

        if mode == PositionSizeMode.FIXED_QUANTITY:
            return max(0, math.floor(value))

        if mode == PositionSizeMode.EQUITY_FRACTION:
            return max(0, math.floor((current_equity * value) / fill_price))

        # FIXED_CASH
        return max(0, math.floor(value / fill_price))

    # ------------------------------------------------------------------
    # Order creation
    # ------------------------------------------------------------------

    @staticmethod
    def create_pending_order(
        session_id: str,
        account_id: str,
        user_id: str,
        symbol: str,
        direction: OrderDirection,
        quantity: int,
        fill_timing_model: FillTimingModel,
        signal_bar_timestamp: datetime,
        signal_id: str | None = None,
    ) -> PaperOrder:
        """
        Create a PENDING_FILL order for NEXT_BAR_OPEN fill timing.

        The returned order must be persisted by the caller via
        PaperOrderStore.save_pending() before the poll cycle ends.

        target_fill_bar_timestamp is not set here; the service layer sets it
        when the next bar arrives and the order is resolved.
        """
        now = datetime.now(timezone.utc)
        return PaperOrder(
            order_id=str(uuid.uuid4()),
            session_id=session_id,
            account_id=account_id,
            user_id=user_id,
            symbol=symbol,
            direction=direction,
            quantity=float(quantity),
            status=PaperOrderStatus.PENDING_FILL,
            fill_timing_model=fill_timing_model,
            signal_id=signal_id,
            signal_bar_timestamp=signal_bar_timestamp,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def build_fill(
        order: PaperOrder,
        gross_price: float,
        fill_bar_timestamp: datetime,
        assumptions: SimulationAssumptions,
        execution_reason: ExecutionReason | None = None,
        fill_timestamp: datetime | None = None,
    ) -> tuple[PaperOrder, PaperFill]:
        """
        Resolve an order into a FILLED order + PaperFill.

        Works for both fill timing modes:
          NEXT_BAR_OPEN:    gross_price = bar N+1 open price
          SIGNAL_BAR_CLOSE: gross_price = bar N close price

        Applies slippage and fee from SimulationAssumptions to produce a
        fully self-documenting PaperFill record.

        Returns (filled_order, fill).  Neither is persisted here; the caller
        is responsible for calling PaperOrderStore.mark_filled(order, fill).
        """
        now = fill_timestamp or datetime.now(timezone.utc)
        qty = int(order.quantity)

        net_fill_price, slippage = PaperBrokerAdapter.compute_fill_price(
            order.direction, gross_price, assumptions
        )
        fee = PaperBrokerAdapter.compute_fee(qty, gross_price, assumptions)

        gross_value = qty * gross_price
        net_value   = qty * net_fill_price

        fill = PaperFill(
            fill_id=str(uuid.uuid4()),
            order_id=order.order_id,
            session_id=order.session_id,
            account_id=order.account_id,
            user_id=order.user_id,
            symbol=order.symbol,
            direction=order.direction,
            quantity=order.quantity,
            gross_price=gross_price,
            slippage=slippage,
            fill_price=net_fill_price,
            gross_value=gross_value,
            fee=fee,
            net_value=net_value,
            fill_bar_timestamp=fill_bar_timestamp,
            created_at=now,
            execution_reason=execution_reason,
        )

        filled_order = order.model_copy(update={
            "status":    PaperOrderStatus.FILLED,
            "filled_at": now,
            "updated_at": now,
            "target_fill_bar_timestamp": fill_bar_timestamp,
        })

        return filled_order, fill

    @staticmethod
    def reject_order(
        session_id: str,
        account_id: str,
        user_id: str,
        symbol: str,
        direction: OrderDirection,
        quantity: int,
        fill_timing_model: FillTimingModel,
        signal_bar_timestamp: datetime,
        rejection_reason: str,
        signal_id: str | None = None,
    ) -> PaperOrder:
        """
        Create a REJECTED order record.

        Used when intent validation fails before an order can be filled:
          - insufficient_cash
          - max_positions_exceeded
          - no_position_to_close
          - short_selling_disabled

        The rejection_reason parameter should be a structured RejectionReason
        value (or its .value string) — never a raw exception message.

        Note: for rejection_reason="quantity_resolved_to_zero", the service
        layer should emit an audit event but may choose NOT to create a
        PaperOrder (since quantity must be > 0 on the model).  This method
        requires quantity >= 1.
        """
        now = datetime.now(timezone.utc)
        return PaperOrder(
            order_id=str(uuid.uuid4()),
            session_id=session_id,
            account_id=account_id,
            user_id=user_id,
            symbol=symbol,
            direction=direction,
            quantity=float(max(quantity, 1)),  # guard: quantity must be > 0
            status=PaperOrderStatus.REJECTED,
            fill_timing_model=fill_timing_model,
            signal_id=signal_id,
            signal_bar_timestamp=signal_bar_timestamp,
            created_at=now,
            updated_at=now,
            rejection_reason=rejection_reason,
        )
