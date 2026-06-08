"""
Unit tests for backend/paper_trading/execution_models.py — Phase 4E.2.

Coverage targets:
  - OrderDirection, PaperOrderStatus, ExecutionReason, RejectionReason enums
  - PaperOrder field validation, UUID guards, UTC enforcement, frozen behavior
  - PaperFill field validation, price/cost non-negative, frozen behavior
  - PaperPosition field validation, open/closed invariants, frozen behavior
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from pydantic import ValidationError

from backend.paper_trading.execution_models import (
    ExecutionReason,
    OrderDirection,
    PaperFill,
    PaperOrder,
    PaperOrderStatus,
    PaperPosition,
    RejectionReason,
)
from backend.paper_trading.models import FillTimingModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_order(**overrides) -> PaperOrder:
    defaults = {
        "order_id":              _uuid(),
        "session_id":            _uuid(),
        "account_id":            _uuid(),
        "user_id":               _uuid(),
        "symbol":                "AAPL",
        "direction":             OrderDirection.BUY,
        "quantity":              10.0,
        "fill_timing_model":     FillTimingModel.NEXT_BAR_OPEN,
        "signal_bar_timestamp":  _now(),
        "created_at":            _now(),
        "updated_at":            _now(),
    }
    defaults.update(overrides)
    return PaperOrder(**defaults)


def _make_fill(**overrides) -> PaperFill:
    defaults = {
        "fill_id":              _uuid(),
        "order_id":             _uuid(),
        "session_id":           _uuid(),
        "account_id":           _uuid(),
        "user_id":              _uuid(),
        "symbol":               "AAPL",
        "direction":            OrderDirection.BUY,
        "quantity":             10.0,
        "gross_price":          150.0,
        "slippage":             0.0,
        "fill_price":           150.0,
        "gross_value":          1500.0,
        "fee":                  0.0,
        "net_value":            1500.0,
        "fill_bar_timestamp":   _now(),
        "created_at":           _now(),
    }
    defaults.update(overrides)
    return PaperFill(**defaults)


def _make_position(is_open: bool = True, **overrides) -> PaperPosition:
    now = _now()
    defaults: dict = {
        "position_id":          _uuid(),
        "session_id":           _uuid(),
        "account_id":           _uuid(),
        "user_id":              _uuid(),
        "symbol":               "AAPL",
        "quantity":             10.0,
        "average_entry_price":  150.0,
        "current_price":        155.0,
        "market_value":         1550.0,
        "unrealized_pnl":       50.0,
        "realized_pnl":         0.0,
        "is_open":              is_open,
        "opened_at":            now,
        "last_updated_at":      now,
    }
    if not is_open:
        defaults["closed_at"] = now
        defaults["quantity"]   = 0.0
    defaults.update(overrides)
    return PaperPosition(**defaults)


# ===========================================================================
# Enum sanity
# ===========================================================================

class TestEnums:
    def test_order_direction_values(self):
        assert OrderDirection.BUY.value  == "buy"
        assert OrderDirection.SELL.value == "sell"

    def test_paper_order_status_values(self):
        assert PaperOrderStatus.PENDING_FILL.value == "pending_fill"
        assert PaperOrderStatus.FILLED.value       == "filled"
        assert PaperOrderStatus.CANCELLED.value    == "cancelled"
        assert PaperOrderStatus.REJECTED.value     == "rejected"

    def test_execution_reason_values(self):
        assert ExecutionReason.SIGNAL_ENTRY.value        == "signal_entry"
        assert ExecutionReason.SIGNAL_EXIT.value         == "signal_exit"
        assert ExecutionReason.SESSION_END_CLOSE.value   == "session_end_close"
        assert ExecutionReason.DRAWDOWN_STOP_CLOSE.value == "drawdown_stop_close"

    def test_rejection_reason_values(self):
        assert RejectionReason.INSUFFICIENT_CASH.value      == "insufficient_cash"
        assert RejectionReason.MAX_POSITIONS_EXCEEDED.value == "max_positions_exceeded"
        assert RejectionReason.NO_POSITION_TO_CLOSE.value   == "no_position_to_close"
        assert RejectionReason.SHORT_SELLING_DISABLED.value == "short_selling_disabled"
        # EXEC-2A: execution-contract alignment additions
        assert RejectionReason.DUPLICATE_LONG_ENTRY.value   == "duplicate_long_entry"
        assert RejectionReason.PENDING_ENTRY_EXISTS.value   == "pending_entry_exists"

    def test_rejection_reason_exec2a_values_are_distinct(self):
        """EXEC-2A rejection codes must be distinct from all pre-existing codes."""
        existing = {
            RejectionReason.INSUFFICIENT_CASH.value,
            RejectionReason.MAX_POSITIONS_EXCEEDED.value,
            RejectionReason.NO_POSITION_TO_CLOSE.value,
            RejectionReason.SHORT_SELLING_DISABLED.value,
        }
        assert RejectionReason.DUPLICATE_LONG_ENTRY.value not in existing
        assert RejectionReason.PENDING_ENTRY_EXISTS.value not in existing


# ===========================================================================
# PaperOrder
# ===========================================================================

class TestPaperOrder:
    def test_valid_pending_fill_order(self):
        order = _make_order()
        assert order.status == PaperOrderStatus.PENDING_FILL
        assert order.signal_id is None
        assert order.filled_at is None
        assert order.cancellation_reason is None
        assert order.rejection_reason is None

    def test_valid_sell_order(self):
        order = _make_order(direction=OrderDirection.SELL)
        assert order.direction == OrderDirection.SELL

    def test_valid_signal_bar_close_timing(self):
        order = _make_order(fill_timing_model=FillTimingModel.SIGNAL_BAR_CLOSE)
        assert order.fill_timing_model == FillTimingModel.SIGNAL_BAR_CLOSE

    def test_signal_id_optional_uuid_accepted(self):
        order = _make_order(signal_id=_uuid())
        assert order.signal_id is not None

    def test_signal_id_none_accepted(self):
        order = _make_order(signal_id=None)
        assert order.signal_id is None

    def test_signal_id_invalid_uuid_rejected(self):
        with pytest.raises(ValidationError, match="valid UUID"):
            _make_order(signal_id="not-a-uuid")

    def test_invalid_order_id_rejected(self):
        with pytest.raises(ValidationError, match="valid UUID"):
            _make_order(order_id="bad")

    def test_invalid_session_id_rejected(self):
        with pytest.raises(ValidationError, match="valid UUID"):
            _make_order(session_id="bad")

    def test_invalid_user_id_rejected(self):
        with pytest.raises(ValidationError, match="valid UUID"):
            _make_order(user_id="bad")

    def test_quantity_zero_rejected(self):
        with pytest.raises(ValidationError, match="quantity must be > 0"):
            _make_order(quantity=0.0)

    def test_quantity_negative_rejected(self):
        with pytest.raises(ValidationError, match="quantity must be > 0"):
            _make_order(quantity=-1.0)

    def test_symbol_empty_rejected(self):
        with pytest.raises(ValidationError, match="symbol must not be empty"):
            _make_order(symbol="  ")

    def test_symbol_uppercased(self):
        order = _make_order(symbol="aapl")
        assert order.symbol == "AAPL"

    def test_created_at_naive_rejected(self):
        with pytest.raises(ValidationError, match="UTC-aware"):
            _make_order(created_at=datetime(2024, 1, 1))

    def test_signal_bar_timestamp_naive_rejected(self):
        with pytest.raises(ValidationError, match="UTC-aware"):
            _make_order(signal_bar_timestamp=datetime(2024, 1, 1))

    def test_filled_at_naive_rejected(self):
        with pytest.raises(ValidationError, match="UTC-aware"):
            _make_order(filled_at=datetime(2024, 1, 1))

    def test_filled_at_none_allowed(self):
        order = _make_order(filled_at=None)
        assert order.filled_at is None

    def test_target_fill_bar_timestamp_none_allowed(self):
        order = _make_order(target_fill_bar_timestamp=None)
        assert order.target_fill_bar_timestamp is None

    def test_frozen(self):
        order = _make_order()
        with pytest.raises(ValidationError):
            order.status = PaperOrderStatus.FILLED  # type: ignore[misc]

    def test_model_copy_status_update(self):
        order = _make_order()
        filled = order.model_copy(update={
            "status": PaperOrderStatus.FILLED,
            "filled_at": _now(),
            "updated_at": _now(),
        })
        assert filled.status == PaperOrderStatus.FILLED
        assert order.status  == PaperOrderStatus.PENDING_FILL  # original unchanged

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            _make_order(unknown_field="x")  # type: ignore[call-arg]

    def test_rejection_reason_stores_string(self):
        order = _make_order(
            status=PaperOrderStatus.REJECTED,
            rejection_reason=RejectionReason.INSUFFICIENT_CASH.value,
        )
        assert order.rejection_reason == "insufficient_cash"


# ===========================================================================
# PaperFill
# ===========================================================================

class TestPaperFill:
    def test_valid_fill(self):
        fill = _make_fill()
        assert fill.slippage     == 0.0
        assert fill.fee          == 0.0
        assert fill.execution_reason is None

    def test_with_execution_reason(self):
        fill = _make_fill(execution_reason=ExecutionReason.SIGNAL_ENTRY)
        assert fill.execution_reason == ExecutionReason.SIGNAL_ENTRY

    def test_invalid_fill_id_rejected(self):
        with pytest.raises(ValidationError, match="valid UUID"):
            _make_fill(fill_id="bad")

    def test_invalid_order_id_rejected(self):
        with pytest.raises(ValidationError, match="valid UUID"):
            _make_fill(order_id="bad")

    def test_quantity_zero_rejected(self):
        with pytest.raises(ValidationError, match="quantity must be > 0"):
            _make_fill(quantity=0.0)

    def test_quantity_negative_rejected(self):
        with pytest.raises(ValidationError, match="quantity must be > 0"):
            _make_fill(quantity=-1.0)

    def test_gross_price_negative_rejected(self):
        with pytest.raises(ValidationError):
            _make_fill(gross_price=-1.0)

    def test_fill_price_negative_rejected(self):
        with pytest.raises(ValidationError):
            _make_fill(fill_price=-0.01)

    def test_slippage_negative_rejected(self):
        with pytest.raises(ValidationError, match="slippage and fee"):
            _make_fill(slippage=-0.01)

    def test_fee_negative_rejected(self):
        with pytest.raises(ValidationError, match="slippage and fee"):
            _make_fill(fee=-1.0)

    def test_gross_value_negative_rejected(self):
        with pytest.raises(ValidationError):
            _make_fill(gross_value=-1.0)

    def test_net_value_negative_rejected(self):
        with pytest.raises(ValidationError):
            _make_fill(net_value=-1.0)

    def test_fill_bar_timestamp_naive_rejected(self):
        with pytest.raises(ValidationError, match="UTC-aware"):
            _make_fill(fill_bar_timestamp=datetime(2024, 1, 1))

    def test_symbol_uppercased(self):
        fill = _make_fill(symbol="msft")
        assert fill.symbol == "MSFT"

    def test_frozen(self):
        fill = _make_fill()
        with pytest.raises(ValidationError):
            fill.quantity = 5.0  # type: ignore[misc]

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            _make_fill(unknown_field="x")  # type: ignore[call-arg]

    def test_sell_direction(self):
        fill = _make_fill(direction=OrderDirection.SELL)
        assert fill.direction == OrderDirection.SELL

    def test_timestamps_normalized_to_utc(self):
        offset_tz = timezone(timedelta(hours=5))
        ts = datetime(2024, 6, 1, 12, 0, tzinfo=offset_tz)
        fill = _make_fill(fill_bar_timestamp=ts)
        assert fill.fill_bar_timestamp.tzinfo == timezone.utc


# ===========================================================================
# PaperPosition
# ===========================================================================

class TestPaperPosition:
    def test_valid_open_position(self):
        pos = _make_position(is_open=True)
        assert pos.is_open is True
        assert pos.quantity > 0
        assert pos.closed_at is None

    def test_valid_closed_position(self):
        pos = _make_position(is_open=False)
        assert pos.is_open is False
        assert pos.closed_at is not None

    def test_open_position_zero_quantity_rejected(self):
        with pytest.raises(ValidationError, match="quantity must be > 0 when is_open=True"):
            _make_position(is_open=True, quantity=0.0)

    def test_open_position_with_closed_at_rejected(self):
        with pytest.raises(ValidationError, match="closed_at must be None when is_open=True"):
            _make_position(is_open=True, closed_at=_now())

    def test_closed_position_without_closed_at_rejected(self):
        with pytest.raises(ValidationError, match="closed_at must be set when is_open=False"):
            _make_position(is_open=False, closed_at=None)

    def test_closed_position_quantity_zero_allowed(self):
        pos = _make_position(is_open=False, quantity=0.0)
        assert pos.quantity == 0.0

    def test_quantity_negative_rejected(self):
        with pytest.raises(ValidationError, match="quantity must be >= 0"):
            _make_position(is_open=False, quantity=-1.0, closed_at=_now())

    def test_average_entry_price_negative_rejected(self):
        with pytest.raises(ValidationError):
            _make_position(is_open=True, average_entry_price=-1.0)

    def test_current_price_negative_rejected(self):
        with pytest.raises(ValidationError):
            _make_position(is_open=True, current_price=-0.01)

    def test_market_value_negative_rejected(self):
        with pytest.raises(ValidationError):
            _make_position(is_open=True, market_value=-0.01)

    def test_unrealized_pnl_can_be_negative(self):
        pos = _make_position(is_open=True, unrealized_pnl=-100.0)
        assert pos.unrealized_pnl == -100.0

    def test_realized_pnl_can_be_negative(self):
        pos = _make_position(is_open=True, realized_pnl=-50.0)
        assert pos.realized_pnl == -50.0

    def test_symbol_uppercased(self):
        pos = _make_position(is_open=True, symbol="tsla")
        assert pos.symbol == "TSLA"

    def test_invalid_position_id_rejected(self):
        with pytest.raises(ValidationError, match="valid UUID"):
            _make_position(is_open=True, position_id="bad")

    def test_opening_signal_id_optional_uuid(self):
        pos = _make_position(is_open=True, opening_signal_id=_uuid())
        assert pos.opening_signal_id is not None

    def test_opening_signal_id_invalid_uuid_rejected(self):
        with pytest.raises(ValidationError, match="valid UUID"):
            _make_position(is_open=True, opening_signal_id="bad-id")

    def test_opened_at_naive_rejected(self):
        with pytest.raises(ValidationError, match="UTC-aware"):
            _make_position(is_open=True, opened_at=datetime(2024, 1, 1))

    def test_closed_at_naive_rejected(self):
        with pytest.raises(ValidationError, match="UTC-aware"):
            _make_position(is_open=False, closed_at=datetime(2024, 1, 1))

    def test_frozen(self):
        pos = _make_position(is_open=True)
        with pytest.raises(ValidationError):
            pos.quantity = 5.0  # type: ignore[misc]

    def test_model_copy_close_position(self):
        pos = _make_position(is_open=True, quantity=10.0)
        now = _now()
        closed = pos.model_copy(update={
            "is_open":          False,
            "quantity":         0.0,
            "closed_at":        now,
            "last_updated_at":  now,
            "unrealized_pnl":   0.0,
            "realized_pnl":     50.0,
        })
        assert closed.is_open is False
        assert closed.quantity == 0.0
        assert pos.is_open is True  # original unchanged

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            _make_position(is_open=True, unknown_field="x")  # type: ignore[call-arg]
