"""
Unit tests for backend/paper_trading/broker_adapter.py — Phase 4E.2.

Coverage targets:
  - compute_fill_price: no slippage, fixed BUY adverse, fixed SELL adverse,
    percentage BUY, percentage SELL, slippage_value=0 short-circuits
  - compute_fee: none, flat, percentage
  - compute_quantity: all 3 modes, fill_price=0 guard, result<1 returns 0
  - create_pending_order: PENDING_FILL, correct fields, no target_fill_bar_timestamp
  - build_fill: price computation, filled order fields, fill fields, execution_reason
  - reject_order: REJECTED status, rejection_reason, quantity guard
  - stateless: no side effects between calls
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from backend.paper_trading.broker_adapter import PaperBrokerAdapter
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _assumptions(**overrides) -> SimulationAssumptions:
    defaults = {
        "starting_cash":      10_000.0,
        "fee_mode":           FeeMode.NONE,
        "fee_value":          0.0,
        "slippage_mode":      SlippageMode.NONE,
        "slippage_value":     0.0,
        "position_size_mode": PositionSizeMode.FIXED_QUANTITY,
        "position_size_value": 10.0,
    }
    defaults.update(overrides)
    return SimulationAssumptions(**defaults)


def _make_pending_order(**overrides) -> PaperOrder:
    defaults = {
        "order_id":             _uid(),
        "session_id":           _uid(),
        "account_id":           _uid(),
        "user_id":              _uid(),
        "symbol":               "AAPL",
        "direction":            OrderDirection.BUY,
        "quantity":             10.0,
        "fill_timing_model":    FillTimingModel.NEXT_BAR_OPEN,
        "signal_bar_timestamp": _now(),
        "status":               PaperOrderStatus.PENDING_FILL,
        "created_at":           _now(),
        "updated_at":           _now(),
    }
    defaults.update(overrides)
    return PaperOrder(**defaults)


# ===========================================================================
# compute_fill_price
# ===========================================================================

class TestComputeFillPrice:
    def test_no_slippage_returns_gross_price(self):
        assumptions = _assumptions(slippage_mode=SlippageMode.NONE, slippage_value=0.0)
        price, slip = PaperBrokerAdapter.compute_fill_price(
            OrderDirection.BUY, 100.0, assumptions
        )
        assert price == 100.0
        assert slip == 0.0

    def test_slippage_value_zero_short_circuits(self):
        assumptions = _assumptions(slippage_mode=SlippageMode.FIXED, slippage_value=0.0)
        price, slip = PaperBrokerAdapter.compute_fill_price(
            OrderDirection.BUY, 100.0, assumptions
        )
        assert price == 100.0
        assert slip == 0.0

    def test_fixed_buy_adverse_increases_price(self):
        assumptions = _assumptions(slippage_mode=SlippageMode.FIXED, slippage_value=0.5)
        price, slip = PaperBrokerAdapter.compute_fill_price(
            OrderDirection.BUY, 100.0, assumptions
        )
        assert price == pytest.approx(100.5)
        assert slip == pytest.approx(0.5)

    def test_fixed_sell_adverse_decreases_price(self):
        assumptions = _assumptions(slippage_mode=SlippageMode.FIXED, slippage_value=0.5)
        price, slip = PaperBrokerAdapter.compute_fill_price(
            OrderDirection.SELL, 100.0, assumptions
        )
        assert price == pytest.approx(99.5)
        assert slip == pytest.approx(0.5)

    def test_fixed_sell_floored_at_zero(self):
        assumptions = _assumptions(slippage_mode=SlippageMode.FIXED, slippage_value=200.0)
        price, slip = PaperBrokerAdapter.compute_fill_price(
            OrderDirection.SELL, 100.0, assumptions
        )
        assert price == 0.0
        assert slip == pytest.approx(200.0)

    def test_percentage_buy_adverse(self):
        # 0.5% slippage on $100.00 = $0.50 → fill = $100.50
        assumptions = _assumptions(slippage_mode=SlippageMode.PERCENTAGE, slippage_value=0.005)
        price, slip = PaperBrokerAdapter.compute_fill_price(
            OrderDirection.BUY, 100.0, assumptions
        )
        assert price == pytest.approx(100.5)
        assert slip == pytest.approx(0.5)

    def test_percentage_sell_adverse(self):
        # 0.5% slippage on $100.00 = $0.50 → fill = $99.50
        assumptions = _assumptions(slippage_mode=SlippageMode.PERCENTAGE, slippage_value=0.005)
        price, slip = PaperBrokerAdapter.compute_fill_price(
            OrderDirection.SELL, 100.0, assumptions
        )
        assert price == pytest.approx(99.5)
        assert slip == pytest.approx(0.5)


# ===========================================================================
# compute_fee
# ===========================================================================

class TestComputeFee:
    def test_fee_none_returns_zero(self):
        a = _assumptions(fee_mode=FeeMode.NONE, fee_value=0.0)
        assert PaperBrokerAdapter.compute_fee(10, 150.0, a) == 0.0

    def test_fee_value_zero_short_circuits(self):
        a = _assumptions(fee_mode=FeeMode.FLAT, fee_value=0.0)
        assert PaperBrokerAdapter.compute_fee(10, 150.0, a) == 0.0

    def test_fee_flat_returns_fixed_value(self):
        a = _assumptions(fee_mode=FeeMode.FLAT, fee_value=5.0)
        assert PaperBrokerAdapter.compute_fee(10, 150.0, a) == pytest.approx(5.0)

    def test_fee_flat_independent_of_quantity(self):
        a = _assumptions(fee_mode=FeeMode.FLAT, fee_value=5.0)
        assert PaperBrokerAdapter.compute_fee(1, 150.0, a) == pytest.approx(5.0)
        assert PaperBrokerAdapter.compute_fee(100, 150.0, a) == pytest.approx(5.0)

    def test_fee_percentage_of_gross_value(self):
        # 0.1% of 10 * 150.0 = 1500 → fee = 1.5
        a = _assumptions(fee_mode=FeeMode.PERCENTAGE, fee_value=0.001)
        assert PaperBrokerAdapter.compute_fee(10, 150.0, a) == pytest.approx(1.5)

    def test_fee_percentage_uses_gross_price(self):
        # Fee base is gross_price × quantity, not fill_price
        a = _assumptions(fee_mode=FeeMode.PERCENTAGE, fee_value=0.01)
        fee = PaperBrokerAdapter.compute_fee(5, 200.0, a)
        assert fee == pytest.approx(10.0)  # 5 * 200 * 0.01


# ===========================================================================
# compute_quantity
# ===========================================================================

class TestComputeQuantity:
    def test_fixed_quantity_floors_value(self):
        a = _assumptions(position_size_mode=PositionSizeMode.FIXED_QUANTITY, position_size_value=7.9)
        qty = PaperBrokerAdapter.compute_quantity(a, fill_price=100.0, current_equity=10_000.0)
        assert qty == 7

    def test_fixed_quantity_exact(self):
        a = _assumptions(position_size_mode=PositionSizeMode.FIXED_QUANTITY, position_size_value=10.0)
        assert PaperBrokerAdapter.compute_quantity(a, fill_price=100.0, current_equity=5_000.0) == 10

    def test_equity_fraction_floors(self):
        # equity=10_000, fraction=0.1, price=150.0 → 10_000 * 0.1 / 150 = 6.67 → 6
        a = _assumptions(position_size_mode=PositionSizeMode.EQUITY_FRACTION, position_size_value=0.1)
        qty = PaperBrokerAdapter.compute_quantity(a, fill_price=150.0, current_equity=10_000.0)
        assert qty == 6

    def test_equity_fraction_zero_equity_returns_zero(self):
        a = _assumptions(position_size_mode=PositionSizeMode.EQUITY_FRACTION, position_size_value=0.1)
        assert PaperBrokerAdapter.compute_quantity(a, fill_price=100.0, current_equity=0.0) == 0

    def test_fixed_cash_floors(self):
        # cash=1000, price=150.0 → floor(1000/150) = 6
        a = _assumptions(position_size_mode=PositionSizeMode.FIXED_CASH, position_size_value=1000.0)
        assert PaperBrokerAdapter.compute_quantity(a, fill_price=150.0, current_equity=5_000.0) == 6

    def test_fill_price_zero_returns_zero(self):
        a = _assumptions(position_size_mode=PositionSizeMode.FIXED_QUANTITY, position_size_value=10.0)
        assert PaperBrokerAdapter.compute_quantity(a, fill_price=0.0, current_equity=10_000.0) == 0

    def test_result_less_than_one_returns_zero(self):
        # equity_fraction of tiny equity → < 1 share
        a = _assumptions(position_size_mode=PositionSizeMode.EQUITY_FRACTION, position_size_value=0.001)
        assert PaperBrokerAdapter.compute_quantity(a, fill_price=1000.0, current_equity=500.0) == 0

    def test_fixed_cash_too_small_returns_zero(self):
        # cash=10, price=100 → floor(0.1) = 0
        a = _assumptions(position_size_mode=PositionSizeMode.FIXED_CASH, position_size_value=10.0)
        assert PaperBrokerAdapter.compute_quantity(a, fill_price=100.0, current_equity=5_000.0) == 0


# ===========================================================================
# create_pending_order
# ===========================================================================

class TestCreatePendingOrder:
    def test_returns_pending_fill_status(self):
        order = PaperBrokerAdapter.create_pending_order(
            session_id=_uid(), account_id=_uid(), user_id=_uid(),
            symbol="AAPL", direction=OrderDirection.BUY, quantity=10,
            fill_timing_model=FillTimingModel.NEXT_BAR_OPEN,
            signal_bar_timestamp=_now(),
        )
        assert order.status == PaperOrderStatus.PENDING_FILL

    def test_order_id_is_valid_uuid(self):
        order = PaperBrokerAdapter.create_pending_order(
            session_id=_uid(), account_id=_uid(), user_id=_uid(),
            symbol="AAPL", direction=OrderDirection.BUY, quantity=10,
            fill_timing_model=FillTimingModel.NEXT_BAR_OPEN,
            signal_bar_timestamp=_now(),
        )
        uuid.UUID(order.order_id)  # raises if not valid

    def test_target_fill_bar_timestamp_is_none(self):
        order = PaperBrokerAdapter.create_pending_order(
            session_id=_uid(), account_id=_uid(), user_id=_uid(),
            symbol="AAPL", direction=OrderDirection.BUY, quantity=5,
            fill_timing_model=FillTimingModel.NEXT_BAR_OPEN,
            signal_bar_timestamp=_now(),
        )
        assert order.target_fill_bar_timestamp is None

    def test_signal_id_none_by_default(self):
        order = PaperBrokerAdapter.create_pending_order(
            session_id=_uid(), account_id=_uid(), user_id=_uid(),
            symbol="MSFT", direction=OrderDirection.SELL, quantity=3,
            fill_timing_model=FillTimingModel.NEXT_BAR_OPEN,
            signal_bar_timestamp=_now(),
        )
        assert order.signal_id is None

    def test_signal_id_optional_uuid(self):
        sig_id = _uid()
        order = PaperBrokerAdapter.create_pending_order(
            session_id=_uid(), account_id=_uid(), user_id=_uid(),
            symbol="AAPL", direction=OrderDirection.BUY, quantity=10,
            fill_timing_model=FillTimingModel.NEXT_BAR_OPEN,
            signal_bar_timestamp=_now(),
            signal_id=sig_id,
        )
        assert order.signal_id == sig_id

    def test_quantity_stored_as_float(self):
        order = PaperBrokerAdapter.create_pending_order(
            session_id=_uid(), account_id=_uid(), user_id=_uid(),
            symbol="AAPL", direction=OrderDirection.BUY, quantity=7,
            fill_timing_model=FillTimingModel.NEXT_BAR_OPEN,
            signal_bar_timestamp=_now(),
        )
        assert order.quantity == 7.0

    def test_symbol_uppercased(self):
        order = PaperBrokerAdapter.create_pending_order(
            session_id=_uid(), account_id=_uid(), user_id=_uid(),
            symbol="aapl", direction=OrderDirection.BUY, quantity=1,
            fill_timing_model=FillTimingModel.NEXT_BAR_OPEN,
            signal_bar_timestamp=_now(),
        )
        assert order.symbol == "AAPL"

    def test_each_call_generates_unique_order_id(self):
        kwargs = dict(
            session_id=_uid(), account_id=_uid(), user_id=_uid(),
            symbol="AAPL", direction=OrderDirection.BUY, quantity=10,
            fill_timing_model=FillTimingModel.NEXT_BAR_OPEN,
            signal_bar_timestamp=_now(),
        )
        o1 = PaperBrokerAdapter.create_pending_order(**kwargs)
        o2 = PaperBrokerAdapter.create_pending_order(**kwargs)
        assert o1.order_id != o2.order_id


# ===========================================================================
# build_fill
# ===========================================================================

class TestBuildFill:
    def test_returns_filled_order_and_fill(self):
        order = _make_pending_order()
        assumptions = _assumptions()
        filled_order, fill = PaperBrokerAdapter.build_fill(
            order, gross_price=150.0,
            fill_bar_timestamp=_now(),
            assumptions=assumptions,
        )
        assert isinstance(filled_order, PaperOrder)
        assert isinstance(fill, PaperFill)

    def test_filled_order_status_is_filled(self):
        order = _make_pending_order()
        filled_order, _ = PaperBrokerAdapter.build_fill(
            order, gross_price=150.0, fill_bar_timestamp=_now(),
            assumptions=_assumptions(),
        )
        assert filled_order.status == PaperOrderStatus.FILLED

    def test_filled_order_has_filled_at(self):
        order = _make_pending_order()
        filled_order, _ = PaperBrokerAdapter.build_fill(
            order, gross_price=150.0, fill_bar_timestamp=_now(),
            assumptions=_assumptions(),
        )
        assert filled_order.filled_at is not None

    def test_target_fill_bar_timestamp_set_on_filled_order(self):
        order = _make_pending_order()
        bar_ts = _now()
        filled_order, _ = PaperBrokerAdapter.build_fill(
            order, gross_price=150.0, fill_bar_timestamp=bar_ts,
            assumptions=_assumptions(),
        )
        assert filled_order.target_fill_bar_timestamp == bar_ts

    def test_fill_gross_price_stored(self):
        order = _make_pending_order()
        _, fill = PaperBrokerAdapter.build_fill(
            order, gross_price=200.0, fill_bar_timestamp=_now(),
            assumptions=_assumptions(),
        )
        assert fill.gross_price == 200.0

    def test_fill_no_slippage_fill_price_equals_gross(self):
        order = _make_pending_order()
        _, fill = PaperBrokerAdapter.build_fill(
            order, gross_price=150.0, fill_bar_timestamp=_now(),
            assumptions=_assumptions(slippage_mode=SlippageMode.NONE),
        )
        assert fill.fill_price == pytest.approx(150.0)
        assert fill.slippage == pytest.approx(0.0)

    def test_fill_with_fixed_slippage_buy(self):
        order = _make_pending_order(direction=OrderDirection.BUY, quantity=10.0)
        a = _assumptions(slippage_mode=SlippageMode.FIXED, slippage_value=0.5)
        _, fill = PaperBrokerAdapter.build_fill(
            order, gross_price=100.0, fill_bar_timestamp=_now(), assumptions=a,
        )
        assert fill.fill_price == pytest.approx(100.5)
        assert fill.slippage == pytest.approx(0.5)

    def test_fill_gross_value_computed(self):
        order = _make_pending_order(quantity=10.0)
        _, fill = PaperBrokerAdapter.build_fill(
            order, gross_price=150.0, fill_bar_timestamp=_now(),
            assumptions=_assumptions(),
        )
        assert fill.gross_value == pytest.approx(1500.0)

    def test_fill_net_value_computed(self):
        order = _make_pending_order(quantity=10.0)
        _, fill = PaperBrokerAdapter.build_fill(
            order, gross_price=100.0, fill_bar_timestamp=_now(),
            assumptions=_assumptions(slippage_mode=SlippageMode.FIXED, slippage_value=1.0),
        )
        # fill_price = 101.0; net_value = 10 * 101.0 = 1010.0
        assert fill.net_value == pytest.approx(1010.0)

    def test_fill_fee_applied(self):
        order = _make_pending_order(quantity=10.0)
        a = _assumptions(fee_mode=FeeMode.FLAT, fee_value=5.0)
        _, fill = PaperBrokerAdapter.build_fill(
            order, gross_price=100.0, fill_bar_timestamp=_now(), assumptions=a,
        )
        assert fill.fee == pytest.approx(5.0)

    def test_fill_execution_reason_passed_through(self):
        order = _make_pending_order()
        _, fill = PaperBrokerAdapter.build_fill(
            order, gross_price=100.0, fill_bar_timestamp=_now(),
            assumptions=_assumptions(),
            execution_reason=ExecutionReason.SESSION_END_CLOSE,
        )
        assert fill.execution_reason == ExecutionReason.SESSION_END_CLOSE

    def test_fill_execution_reason_none_by_default(self):
        order = _make_pending_order()
        _, fill = PaperBrokerAdapter.build_fill(
            order, gross_price=100.0, fill_bar_timestamp=_now(),
            assumptions=_assumptions(),
        )
        assert fill.execution_reason is None

    def test_original_order_unchanged(self):
        order = _make_pending_order()
        filled_order, _ = PaperBrokerAdapter.build_fill(
            order, gross_price=100.0, fill_bar_timestamp=_now(),
            assumptions=_assumptions(),
        )
        # Frozen; original should be unchanged
        assert order.status == PaperOrderStatus.PENDING_FILL
        assert filled_order.status == PaperOrderStatus.FILLED

    def test_fill_id_is_valid_uuid(self):
        order = _make_pending_order()
        _, fill = PaperBrokerAdapter.build_fill(
            order, gross_price=100.0, fill_bar_timestamp=_now(),
            assumptions=_assumptions(),
        )
        uuid.UUID(fill.fill_id)

    def test_fill_inherits_order_identity(self):
        order = _make_pending_order()
        _, fill = PaperBrokerAdapter.build_fill(
            order, gross_price=100.0, fill_bar_timestamp=_now(),
            assumptions=_assumptions(),
        )
        assert fill.order_id == order.order_id
        assert fill.session_id == order.session_id
        assert fill.user_id == order.user_id
        assert fill.symbol == order.symbol


# ===========================================================================
# reject_order
# ===========================================================================

class TestRejectOrder:
    def test_returns_rejected_status(self):
        order = PaperBrokerAdapter.reject_order(
            session_id=_uid(), account_id=_uid(), user_id=_uid(),
            symbol="AAPL", direction=OrderDirection.BUY, quantity=10,
            fill_timing_model=FillTimingModel.NEXT_BAR_OPEN,
            signal_bar_timestamp=_now(),
            rejection_reason="insufficient_cash",
        )
        assert order.status == PaperOrderStatus.REJECTED

    def test_rejection_reason_stored(self):
        order = PaperBrokerAdapter.reject_order(
            session_id=_uid(), account_id=_uid(), user_id=_uid(),
            symbol="AAPL", direction=OrderDirection.BUY, quantity=10,
            fill_timing_model=FillTimingModel.NEXT_BAR_OPEN,
            signal_bar_timestamp=_now(),
            rejection_reason="max_positions_exceeded",
        )
        assert order.rejection_reason == "max_positions_exceeded"

    def test_quantity_zero_guarded_to_one(self):
        order = PaperBrokerAdapter.reject_order(
            session_id=_uid(), account_id=_uid(), user_id=_uid(),
            symbol="AAPL", direction=OrderDirection.BUY, quantity=0,
            fill_timing_model=FillTimingModel.NEXT_BAR_OPEN,
            signal_bar_timestamp=_now(),
            rejection_reason="quantity_resolved_to_zero",
        )
        assert order.quantity == 1.0

    def test_negative_quantity_guarded_to_one(self):
        order = PaperBrokerAdapter.reject_order(
            session_id=_uid(), account_id=_uid(), user_id=_uid(),
            symbol="AAPL", direction=OrderDirection.BUY, quantity=-5,
            fill_timing_model=FillTimingModel.NEXT_BAR_OPEN,
            signal_bar_timestamp=_now(),
            rejection_reason="insufficient_cash",
        )
        assert order.quantity == 1.0

    def test_positive_quantity_preserved(self):
        order = PaperBrokerAdapter.reject_order(
            session_id=_uid(), account_id=_uid(), user_id=_uid(),
            symbol="AAPL", direction=OrderDirection.BUY, quantity=5,
            fill_timing_model=FillTimingModel.NEXT_BAR_OPEN,
            signal_bar_timestamp=_now(),
            rejection_reason="insufficient_cash",
        )
        assert order.quantity == 5.0

    def test_order_id_is_valid_uuid(self):
        order = PaperBrokerAdapter.reject_order(
            session_id=_uid(), account_id=_uid(), user_id=_uid(),
            symbol="AAPL", direction=OrderDirection.BUY, quantity=10,
            fill_timing_model=FillTimingModel.NEXT_BAR_OPEN,
            signal_bar_timestamp=_now(),
            rejection_reason="short_selling_disabled",
        )
        uuid.UUID(order.order_id)

    def test_signal_id_optional(self):
        sig = _uid()
        order = PaperBrokerAdapter.reject_order(
            session_id=_uid(), account_id=_uid(), user_id=_uid(),
            symbol="AAPL", direction=OrderDirection.BUY, quantity=10,
            fill_timing_model=FillTimingModel.NEXT_BAR_OPEN,
            signal_bar_timestamp=_now(),
            rejection_reason="insufficient_cash",
            signal_id=sig,
        )
        assert order.signal_id == sig


# ===========================================================================
# Stateless invariant
# ===========================================================================

class TestStateless:
    def test_no_instance_state_between_calls(self):
        adapter = PaperBrokerAdapter()
        a = _assumptions()
        o1 = adapter.create_pending_order(
            session_id=_uid(), account_id=_uid(), user_id=_uid(),
            symbol="AAPL", direction=OrderDirection.BUY, quantity=10,
            fill_timing_model=FillTimingModel.NEXT_BAR_OPEN,
            signal_bar_timestamp=_now(),
        )
        o2 = adapter.create_pending_order(
            session_id=_uid(), account_id=_uid(), user_id=_uid(),
            symbol="MSFT", direction=OrderDirection.BUY, quantity=5,
            fill_timing_model=FillTimingModel.SIGNAL_BAR_CLOSE,
            signal_bar_timestamp=_now(),
        )
        assert o1.order_id != o2.order_id
        assert o1.symbol == "AAPL"
        assert o2.symbol == "MSFT"
