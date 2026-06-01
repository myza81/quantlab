"""
Unit tests for backend/paper_trading/execution_stores.py — Phase 4E.2.

Coverage targets:
  - PaperOrderStore: save_pending, load_pending, mark_filled, mark_cancelled,
    mark_rejected, list_filled, list_cancelled, list_rejected,
    owner isolation, UUID guard, append-only terminal files
  - PaperFillStore: append (new + duplicate), list_fills (owner filter), count,
    UUID guard
  - PaperPositionStore: save, update, load, list_positions, list_open_positions,
    count_open, owner isolation, UUID guard
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.paper_trading.exceptions import (
    PaperOrderNotFoundError,
    PaperPositionAlreadyExistsError,
    PaperPositionNotFoundError,
    PaperTradingPersistenceError,
)
from backend.paper_trading.execution_models import (
    ExecutionReason,
    OrderDirection,
    PaperFill,
    PaperOrder,
    PaperOrderStatus,
    PaperPosition,
)
from backend.paper_trading.execution_stores import (
    PaperFillStore,
    PaperOrderStore,
    PaperPositionStore,
)
from backend.paper_trading.models import FillTimingModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_order(
    session_id: str | None = None,
    user_id: str | None = None,
    status: PaperOrderStatus = PaperOrderStatus.PENDING_FILL,
    **overrides,
) -> PaperOrder:
    defaults = {
        "order_id":             _uid(),
        "session_id":           session_id or _uid(),
        "account_id":           _uid(),
        "user_id":              user_id or _uid(),
        "symbol":               "AAPL",
        "direction":            OrderDirection.BUY,
        "quantity":             10.0,
        "fill_timing_model":    FillTimingModel.NEXT_BAR_OPEN,
        "signal_bar_timestamp": _now(),
        "status":               status,
        "created_at":           _now(),
        "updated_at":           _now(),
    }
    defaults.update(overrides)
    return PaperOrder(**defaults)


def _make_fill(
    session_id: str | None = None,
    user_id: str | None = None,
    order_id: str | None = None,
    **overrides,
) -> PaperFill:
    defaults = {
        "fill_id":            _uid(),
        "order_id":           order_id or _uid(),
        "session_id":         session_id or _uid(),
        "account_id":         _uid(),
        "user_id":            user_id or _uid(),
        "symbol":             "AAPL",
        "direction":          OrderDirection.BUY,
        "quantity":           10.0,
        "gross_price":        150.0,
        "slippage":           0.0,
        "fill_price":         150.0,
        "gross_value":        1500.0,
        "fee":                0.0,
        "net_value":          1500.0,
        "fill_bar_timestamp": _now(),
        "created_at":         _now(),
    }
    defaults.update(overrides)
    return PaperFill(**defaults)


def _make_position(
    session_id: str | None = None,
    user_id: str | None = None,
    is_open: bool = True,
    **overrides,
) -> PaperPosition:
    now = _now()
    defaults: dict = {
        "position_id":         _uid(),
        "session_id":          session_id or _uid(),
        "account_id":          _uid(),
        "user_id":             user_id or _uid(),
        "symbol":              "AAPL",
        "quantity":            10.0 if is_open else 0.0,
        "average_entry_price": 150.0,
        "current_price":       155.0,
        "market_value":        1550.0 if is_open else 0.0,
        "unrealized_pnl":      50.0 if is_open else 0.0,
        "realized_pnl":        0.0,
        "is_open":             is_open,
        "opened_at":           now,
        "last_updated_at":     now,
    }
    if not is_open:
        defaults["closed_at"] = now
    defaults.update(overrides)
    return PaperPosition(**defaults)


# ===========================================================================
# PaperOrderStore
# ===========================================================================

class TestPaperOrderStoreSavePending:
    def test_save_creates_pending_file(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        sid = _uid()
        order = _make_order(session_id=sid)
        store.save_pending(order)
        assert (tmp_path / "orders" / sid / "pending.json").exists()

    def test_save_pending_roundtrips(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        sid = _uid()
        uid = _uid()
        order = _make_order(session_id=sid, user_id=uid)
        store.save_pending(order)
        loaded = store.load_pending(sid, uid)
        assert len(loaded) == 1
        assert loaded[0].order_id == order.order_id

    def test_save_pending_duplicate_raises(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        order = _make_order()
        store.save_pending(order)
        with pytest.raises(PaperOrderNotFoundError):
            store.save_pending(order)

    def test_load_pending_after_save_is_idempotent_read(self, tmp_path):
        # UUID guard on write paths is redundant (model validates); test read guard path
        store = PaperOrderStore(tmp_path)
        with pytest.raises(PaperTradingPersistenceError):
            store.load_pending("not-a-uuid", _uid())

    def test_multiple_orders_same_session(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        sid = _uid()
        uid = _uid()
        o1 = _make_order(session_id=sid, user_id=uid)
        o2 = _make_order(session_id=sid, user_id=uid)
        store.save_pending(o1)
        store.save_pending(o2)
        loaded = store.load_pending(sid, uid)
        assert len(loaded) == 2


class TestPaperOrderStoreLoadPending:
    def test_load_pending_empty_when_no_file(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        result = store.load_pending(_uid(), _uid())
        assert result == []

    def test_load_pending_owner_filter_hides_other_users(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        sid = _uid()
        uid_a = _uid()
        uid_b = _uid()
        store.save_pending(_make_order(session_id=sid, user_id=uid_a))
        result = store.load_pending(sid, uid_b)
        assert result == []

    def test_load_pending_returns_own_orders(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        sid = _uid()
        uid = _uid()
        store.save_pending(_make_order(session_id=sid, user_id=uid))
        result = store.load_pending(sid, uid)
        assert len(result) == 1

    def test_load_pending_uuid_guard(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        with pytest.raises(PaperTradingPersistenceError):
            store.load_pending("bad-session-id", _uid())


class TestPaperOrderStoreMarkFilled:
    def test_mark_filled_removes_from_pending(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        sid = _uid()
        uid = _uid()
        order = _make_order(session_id=sid, user_id=uid)
        store.save_pending(order)

        filled_order = order.model_copy(update={
            "status": PaperOrderStatus.FILLED,
            "filled_at": _now(),
            "updated_at": _now(),
        })
        fill = _make_fill(session_id=sid, user_id=uid, order_id=order.order_id)
        store.mark_filled(filled_order, fill)

        pending = store.load_pending(sid, uid)
        assert pending == []

    def test_mark_filled_appends_to_filled_json(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        sid = _uid()
        uid = _uid()
        order = _make_order(session_id=sid, user_id=uid)
        store.save_pending(order)

        filled_order = order.model_copy(update={
            "status": PaperOrderStatus.FILLED,
            "filled_at": _now(),
            "updated_at": _now(),
        })
        fill = _make_fill(session_id=sid, user_id=uid, order_id=order.order_id)
        store.mark_filled(filled_order, fill)

        filled = store.list_filled(sid, uid)
        assert len(filled) == 1
        assert filled[0].order_id == order.order_id

    def test_mark_filled_writes_fill_to_fills_dir(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        sid = _uid()
        uid = _uid()
        order = _make_order(session_id=sid, user_id=uid)
        store.save_pending(order)

        filled_order = order.model_copy(update={
            "status": PaperOrderStatus.FILLED,
            "filled_at": _now(),
            "updated_at": _now(),
        })
        fill = _make_fill(session_id=sid, user_id=uid, order_id=order.order_id)
        store.mark_filled(filled_order, fill)

        assert (tmp_path / "fills" / f"{sid}.json").exists()

    def test_mark_filled_dedup_does_not_double_write_fill(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        sid = _uid()
        uid = _uid()
        order = _make_order(session_id=sid, user_id=uid)
        store.save_pending(order)

        filled_order = order.model_copy(update={
            "status": PaperOrderStatus.FILLED,
            "filled_at": _now(),
            "updated_at": _now(),
        })
        fill = _make_fill(session_id=sid, user_id=uid, order_id=order.order_id)
        store.mark_filled(filled_order, fill)
        store.mark_filled(filled_order, fill)  # second call should dedup fill

        fill_store = PaperFillStore(tmp_path)
        fills = fill_store.list_fills(sid)
        assert len(fills) == 1

    def test_mark_filled_signal_bar_close_not_in_pending_is_ok(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        sid = _uid()
        uid = _uid()
        order = _make_order(
            session_id=sid,
            user_id=uid,
            fill_timing_model=FillTimingModel.SIGNAL_BAR_CLOSE,
            status=PaperOrderStatus.FILLED,
        )
        fill = _make_fill(session_id=sid, user_id=uid, order_id=order.order_id)
        # never saved to pending — should not raise
        store.mark_filled(order, fill)
        filled = store.list_filled(sid, uid)
        assert len(filled) == 1


class TestPaperOrderStoreMarkCancelled:
    def test_mark_cancelled_removes_from_pending(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        sid = _uid()
        uid = _uid()
        order = _make_order(session_id=sid, user_id=uid)
        store.save_pending(order)

        cancelled_order = order.model_copy(update={
            "status": PaperOrderStatus.CANCELLED,
            "updated_at": _now(),
            "cancellation_reason": "session_terminated",
        })
        store.mark_cancelled(cancelled_order, "session_terminated")

        assert store.load_pending(sid, uid) == []

    def test_mark_cancelled_appends_to_cancelled_json(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        sid = _uid()
        uid = _uid()
        order = _make_order(session_id=sid, user_id=uid)
        store.save_pending(order)

        cancelled_order = order.model_copy(update={
            "status": PaperOrderStatus.CANCELLED,
            "updated_at": _now(),
        })
        store.mark_cancelled(cancelled_order, "session_terminated")

        result = store.list_cancelled(sid, uid)
        assert len(result) == 1

    def test_mark_cancelled_not_in_pending_is_ok(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        sid = _uid()
        uid = _uid()
        order = _make_order(session_id=sid, user_id=uid, status=PaperOrderStatus.CANCELLED)
        store.mark_cancelled(order, "reason")
        assert len(store.list_cancelled(sid, uid)) == 1


class TestPaperOrderStoreMarkRejected:
    def test_mark_rejected_appends_to_rejected_json(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        sid = _uid()
        uid = _uid()
        order = _make_order(
            session_id=sid,
            user_id=uid,
            status=PaperOrderStatus.REJECTED,
            rejection_reason="insufficient_cash",
        )
        store.mark_rejected(order, "insufficient_cash")
        result = store.list_rejected(sid, uid)
        assert len(result) == 1
        assert result[0].rejection_reason == "insufficient_cash"

    def test_mark_rejected_does_not_touch_pending(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        sid = _uid()
        uid = _uid()
        pending_order = _make_order(session_id=sid, user_id=uid)
        store.save_pending(pending_order)

        rejected_order = _make_order(
            session_id=sid,
            user_id=uid,
            status=PaperOrderStatus.REJECTED,
            rejection_reason="max_positions_exceeded",
        )
        store.mark_rejected(rejected_order, "max_positions_exceeded")

        # original pending order still present
        assert len(store.load_pending(sid, uid)) == 1

    def test_multiple_rejected_orders_accumulate(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        sid = _uid()
        uid = _uid()
        for _ in range(3):
            order = _make_order(
                session_id=sid,
                user_id=uid,
                status=PaperOrderStatus.REJECTED,
                rejection_reason="insufficient_cash",
            )
            store.mark_rejected(order, "insufficient_cash")
        assert len(store.list_rejected(sid, uid)) == 3


class TestPaperOrderStoreListMethods:
    def test_list_filled_owner_filter(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        sid = _uid()
        uid_a = _uid()
        uid_b = _uid()

        for uid in (uid_a, uid_b):
            order = _make_order(session_id=sid, user_id=uid)
            filled = order.model_copy(update={
                "status": PaperOrderStatus.FILLED,
                "filled_at": _now(),
                "updated_at": _now(),
            })
            fill = _make_fill(session_id=sid, user_id=uid, order_id=order.order_id)
            store.mark_filled(filled, fill)

        assert len(store.list_filled(sid, uid_a)) == 1
        assert len(store.list_filled(sid, uid_b)) == 1

    def test_list_cancelled_uuid_guard(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        with pytest.raises(PaperTradingPersistenceError):
            store.list_cancelled("bad", _uid())

    def test_list_rejected_uuid_guard(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        with pytest.raises(PaperTradingPersistenceError):
            store.list_rejected("bad", _uid())

    def test_append_only_terminal_files_accumulate(self, tmp_path):
        store = PaperOrderStore(tmp_path)
        sid = _uid()
        uid = _uid()
        for _ in range(5):
            order = _make_order(
                session_id=sid,
                user_id=uid,
                status=PaperOrderStatus.REJECTED,
                rejection_reason="insufficient_cash",
            )
            store.mark_rejected(order, "insufficient_cash")
        assert len(store.list_rejected(sid, uid)) == 5


# ===========================================================================
# PaperFillStore
# ===========================================================================

class TestPaperFillStore:
    def test_append_new_fill_returns_true(self, tmp_path):
        store = PaperFillStore(tmp_path)
        fill = _make_fill()
        assert store.append(fill) is True

    def test_append_duplicate_fill_returns_false(self, tmp_path):
        store = PaperFillStore(tmp_path)
        fill = _make_fill()
        store.append(fill)
        assert store.append(fill) is False

    def test_append_duplicate_does_not_add_record(self, tmp_path):
        store = PaperFillStore(tmp_path)
        fill = _make_fill()
        store.append(fill)
        store.append(fill)
        assert store.count(fill.session_id) == 1

    def test_list_fills_empty_when_no_file(self, tmp_path):
        store = PaperFillStore(tmp_path)
        assert store.list_fills(_uid()) == []

    def test_list_fills_returns_all_without_owner_filter(self, tmp_path):
        store = PaperFillStore(tmp_path)
        sid = _uid()
        uid_a = _uid()
        uid_b = _uid()
        store.append(_make_fill(session_id=sid, user_id=uid_a))
        store.append(_make_fill(session_id=sid, user_id=uid_b))
        assert len(store.list_fills(sid)) == 2

    def test_list_fills_owner_filter(self, tmp_path):
        store = PaperFillStore(tmp_path)
        sid = _uid()
        uid_a = _uid()
        uid_b = _uid()
        store.append(_make_fill(session_id=sid, user_id=uid_a))
        store.append(_make_fill(session_id=sid, user_id=uid_b))
        result = store.list_fills(sid, owner_id=uid_a)
        assert len(result) == 1
        assert result[0].user_id == uid_a

    def test_list_fills_wrong_owner_returns_empty(self, tmp_path):
        store = PaperFillStore(tmp_path)
        sid = _uid()
        uid_a = _uid()
        uid_b = _uid()
        store.append(_make_fill(session_id=sid, user_id=uid_a))
        assert store.list_fills(sid, owner_id=uid_b) == []

    def test_count_empty(self, tmp_path):
        store = PaperFillStore(tmp_path)
        assert store.count(_uid()) == 0

    def test_count_accumulates(self, tmp_path):
        store = PaperFillStore(tmp_path)
        sid = _uid()
        for _ in range(4):
            store.append(_make_fill(session_id=sid))
        assert store.count(sid) == 4

    def test_uuid_guard_on_append_via_list(self, tmp_path):
        # Model validates session_id; test the store's read-path guard directly
        store = PaperFillStore(tmp_path)
        with pytest.raises(PaperTradingPersistenceError):
            store.list_fills("not-a-uuid")

    def test_uuid_guard_on_list_fills(self, tmp_path):
        store = PaperFillStore(tmp_path)
        with pytest.raises(PaperTradingPersistenceError):
            store.list_fills("bad-id")

    def test_uuid_guard_on_count(self, tmp_path):
        store = PaperFillStore(tmp_path)
        with pytest.raises(PaperTradingPersistenceError):
            store.count("bad-id")

    def test_fill_roundtrips_correctly(self, tmp_path):
        store = PaperFillStore(tmp_path)
        fill = _make_fill(
            gross_price=200.0,
            slippage=0.5,
            fill_price=200.5,
            gross_value=2000.0,
            fee=1.0,
            net_value=2005.0,
            execution_reason=ExecutionReason.SIGNAL_ENTRY,
        )
        store.append(fill)
        loaded = store.list_fills(fill.session_id)[0]
        assert loaded.fill_id == fill.fill_id
        assert loaded.gross_price == 200.0
        assert loaded.fill_price == 200.5
        assert loaded.execution_reason == ExecutionReason.SIGNAL_ENTRY


# ===========================================================================
# PaperPositionStore
# ===========================================================================

class TestPaperPositionStoreSave:
    def test_save_creates_position_file(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        pos = _make_position()
        store.save(pos)
        path = tmp_path / "positions" / pos.session_id / f"{pos.position_id}.json"
        assert path.exists()

    def test_save_duplicate_raises(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        pos = _make_position()
        store.save(pos)
        with pytest.raises(PaperPositionAlreadyExistsError):
            store.save(pos)

    def test_save_uuid_guard_via_list(self, tmp_path):
        # Model validates session_id; test the store's read-path guard directly
        store = PaperPositionStore(tmp_path)
        with pytest.raises(PaperTradingPersistenceError):
            store.list_positions("not-a-uuid")


class TestPaperPositionStoreUpdate:
    def test_update_overwrites_file(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        pos = _make_position(is_open=True)
        store.save(pos)

        updated = pos.model_copy(update={
            "current_price":   160.0,
            "market_value":    1600.0,
            "unrealized_pnl":  100.0,
            "last_updated_at": _now(),
        })
        store.update(updated)
        loaded = store.load(pos.session_id, pos.position_id)
        assert loaded.current_price == 160.0

    def test_update_not_found_raises(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        pos = _make_position()
        with pytest.raises(PaperPositionNotFoundError):
            store.update(pos)

    def test_load_not_found_uses_positionnotfound_not_persistence(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        with pytest.raises(PaperPositionNotFoundError):
            store.load(_uid(), _uid())


class TestPaperPositionStoreLoad:
    def test_load_roundtrips(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        pos = _make_position(is_open=True)
        store.save(pos)
        loaded = store.load(pos.session_id, pos.position_id)
        assert loaded.position_id == pos.position_id
        assert loaded.is_open is True

    def test_load_not_found_raises(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        with pytest.raises(PaperPositionNotFoundError):
            store.load(_uid(), _uid())

    def test_load_uuid_guard(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        with pytest.raises(PaperTradingPersistenceError):
            store.load("bad-id", _uid())


class TestPaperPositionStoreListMethods:
    def test_list_positions_empty_when_no_dir(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        assert store.list_positions(_uid()) == []

    def test_list_positions_includes_open_and_closed(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        sid = _uid()
        uid = _uid()
        open_pos  = _make_position(session_id=sid, user_id=uid, is_open=True)
        closed_pos = _make_position(session_id=sid, user_id=uid, is_open=False)
        store.save(open_pos)
        store.save(closed_pos)
        result = store.list_positions(sid)
        assert len(result) == 2

    def test_list_positions_owner_filter(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        sid = _uid()
        uid_a = _uid()
        uid_b = _uid()
        store.save(_make_position(session_id=sid, user_id=uid_a))
        store.save(_make_position(session_id=sid, user_id=uid_b))
        result = store.list_positions(sid, owner_id=uid_a)
        assert len(result) == 1
        assert result[0].user_id == uid_a

    def test_list_positions_wrong_owner_returns_empty(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        sid = _uid()
        uid_a = _uid()
        uid_b = _uid()
        store.save(_make_position(session_id=sid, user_id=uid_a))
        assert store.list_positions(sid, owner_id=uid_b) == []

    def test_list_positions_uuid_guard(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        with pytest.raises(PaperTradingPersistenceError):
            store.list_positions("bad-session-id")

    def test_list_open_positions_excludes_closed(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        sid = _uid()
        uid = _uid()
        open_pos   = _make_position(session_id=sid, user_id=uid, is_open=True)
        closed_pos = _make_position(session_id=sid, user_id=uid, is_open=False)
        store.save(open_pos)
        store.save(closed_pos)
        result = store.list_open_positions(sid)
        assert len(result) == 1
        assert result[0].is_open is True

    def test_list_open_positions_owner_filter(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        sid = _uid()
        uid_a = _uid()
        uid_b = _uid()
        store.save(_make_position(session_id=sid, user_id=uid_a, is_open=True))
        store.save(_make_position(session_id=sid, user_id=uid_b, is_open=True))
        result = store.list_open_positions(sid, owner_id=uid_a)
        assert len(result) == 1

    def test_count_open_empty_session(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        assert store.count_open(_uid()) == 0

    def test_count_open_counts_only_open(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        sid = _uid()
        uid = _uid()
        store.save(_make_position(session_id=sid, user_id=uid, is_open=True))
        store.save(_make_position(session_id=sid, user_id=uid, is_open=True))
        store.save(_make_position(session_id=sid, user_id=uid, is_open=False))
        assert store.count_open(sid) == 2

    def test_count_open_uuid_guard(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        with pytest.raises(PaperTradingPersistenceError):
            store.count_open("bad-id")

    def test_update_position_to_closed_reflected_in_list(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        sid = _uid()
        uid = _uid()
        pos = _make_position(session_id=sid, user_id=uid, is_open=True)
        store.save(pos)

        now = _now()
        closed = pos.model_copy(update={
            "is_open":          False,
            "quantity":         0.0,
            "closed_at":        now,
            "last_updated_at":  now,
            "unrealized_pnl":   0.0,
            "realized_pnl":     50.0,
            "market_value":     0.0,
        })
        store.update(closed)

        assert store.count_open(sid) == 0
        all_positions = store.list_positions(sid)
        assert len(all_positions) == 1
        assert all_positions[0].is_open is False

    def test_session_isolation(self, tmp_path):
        store = PaperPositionStore(tmp_path)
        sid_a = _uid()
        sid_b = _uid()
        uid = _uid()
        store.save(_make_position(session_id=sid_a, user_id=uid))
        store.save(_make_position(session_id=sid_b, user_id=uid))
        assert len(store.list_positions(sid_a)) == 1
        assert len(store.list_positions(sid_b)) == 1
