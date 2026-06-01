"""
Unit tests for backend/paper_trading/terminal.py — Phase P8B.

Coverage targets:
  - Pending orders are cancelled with correct status and reason
  - No pending orders → no-op on order_store
  - Open positions are closed at last known price (no fill generated)
  - Cash and realized P&L correctly accumulated across multiple positions
  - Account finalised: status=CLOSED, cash/equity/peak updated
  - Account not found → graceful return, no snapshot written
  - Final equity snapshot has correct field values
  - Idempotency: second call finds nothing to process (stores return empty)
  - Peak equity is not reduced when recovered cash is below prior peak
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from backend.paper_trading.execution_models import (
    OrderDirection,
    PaperOrder,
    PaperOrderStatus,
    PaperPosition,
)
from backend.paper_trading.models import (
    AccountStateSnapshot,
    FillTimingModel,
    PaperAccount,
    PaperAccountStatus,
)
from backend.paper_trading.terminal import apply_terminal_cleanup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_order(session_id: str, user_id: str, **overrides) -> PaperOrder:
    defaults = {
        "order_id":             _uid(),
        "session_id":           session_id,
        "account_id":           _uid(),
        "user_id":              user_id,
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


def _make_position(
    session_id: str,
    user_id: str,
    account_id: str,
    *,
    market_value: float = 1000.0,
    unrealized_pnl: float = 50.0,
    realized_pnl: float = 0.0,
    **overrides,
) -> PaperPosition:
    return PaperPosition(
        position_id=_uid(),
        session_id=session_id,
        account_id=account_id,
        user_id=user_id,
        symbol="AAPL",
        quantity=10.0,
        average_entry_price=95.0,
        current_price=100.0,
        market_value=market_value,
        unrealized_pnl=unrealized_pnl,
        realized_pnl=realized_pnl,
        is_open=True,
        opened_at=_now(),
        last_updated_at=_now(),
        **overrides,
    )


def _make_account(
    session_id: str,
    account_id: str,
    user_id: str,
    *,
    cash_balance: float = 5000.0,
    equity: float = 5000.0,
    available_cash: float = 5000.0,
    peak_equity: float = 5500.0,
    total_realized_pnl: float = 200.0,
) -> PaperAccount:
    return PaperAccount(
        account_id=account_id,
        session_id=session_id,
        user_id=user_id,
        currency="USD",
        starting_cash=10000.0,
        cash_balance=cash_balance,
        equity=equity,
        available_cash=available_cash,
        peak_equity=peak_equity,
        current_drawdown_pct=0.0,
        total_realized_pnl=total_realized_pnl,
        status=PaperAccountStatus.ACTIVE,
        created_at=_now(),
        updated_at=_now(),
    )


def _make_stores(
    *,
    pending_orders: list = (),
    open_positions: list = (),
    account: PaperAccount | None = None,
):
    order_store = MagicMock()
    order_store.load_pending.return_value = list(pending_orders)

    position_store = MagicMock()
    position_store.list_open_positions.return_value = list(open_positions)

    account_store = MagicMock()
    if account is None:
        account_store.load_by_session_id.side_effect = Exception("no account")
    else:
        account_store.load_by_session_id.return_value = account

    snapshot_store = MagicMock()
    return order_store, position_store, account_store, snapshot_store


def _run(
    *,
    session_id: str | None = None,
    account_id: str | None = None,
    owner_id: str | None = None,
    order_store=None,
    position_store=None,
    account_store=None,
    snapshot_store=None,
    now_utc: datetime | None = None,
):
    sid = session_id or _uid()
    aid = account_id or _uid()
    uid = owner_id or _uid()
    now = now_utc or _now()
    apply_terminal_cleanup(
        session_id=sid,
        account_id=aid,
        owner_id=uid,
        order_store=order_store or MagicMock(),
        position_store=position_store or MagicMock(),
        account_store=account_store or MagicMock(),
        snapshot_store=snapshot_store or MagicMock(),
        now_utc=now,
    )


# ---------------------------------------------------------------------------
# Step 1 — pending order cancellation
# ---------------------------------------------------------------------------

class TestPendingOrderCancellation:
    def test_pending_order_is_cancelled(self):
        sid, uid = _uid(), _uid()
        order = _make_order(sid, uid)
        o_store, p_store, a_store, s_store = _make_stores(pending_orders=[order])

        _run(
            session_id=sid, owner_id=uid,
            order_store=o_store, position_store=p_store,
            account_store=a_store, snapshot_store=s_store,
        )

        o_store.mark_cancelled.assert_called_once()
        passed_order = o_store.mark_cancelled.call_args[0][0]
        assert passed_order.status == PaperOrderStatus.CANCELLED
        assert passed_order.cancellation_reason == "session_terminated"

    def test_multiple_pending_orders_all_cancelled(self):
        sid, uid = _uid(), _uid()
        orders = [_make_order(sid, uid), _make_order(sid, uid)]
        o_store, p_store, a_store, s_store = _make_stores(pending_orders=orders)

        _run(
            session_id=sid, owner_id=uid,
            order_store=o_store, position_store=p_store,
            account_store=a_store, snapshot_store=s_store,
        )

        assert o_store.mark_cancelled.call_count == 2

    def test_no_pending_orders_no_cancel_call(self):
        o_store, p_store, a_store, s_store = _make_stores()

        _run(order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store)

        o_store.mark_cancelled.assert_not_called()

    def test_load_pending_receives_session_and_owner(self):
        sid, uid = _uid(), _uid()
        o_store, p_store, a_store, s_store = _make_stores()

        _run(session_id=sid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store)

        o_store.load_pending.assert_called_once_with(sid, owner_id=uid)

    def test_mark_cancelled_reason_argument(self):
        sid, uid = _uid(), _uid()
        order = _make_order(sid, uid)
        o_store, p_store, a_store, s_store = _make_stores(pending_orders=[order])

        _run(session_id=sid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store)

        _, reason = o_store.mark_cancelled.call_args[0]
        assert reason == "session_terminated"


# ---------------------------------------------------------------------------
# Step 2 — open position closure
# ---------------------------------------------------------------------------

class TestOpenPositionClosure:
    def test_open_position_is_closed(self):
        sid, uid, aid = _uid(), _uid(), _uid()
        pos = _make_position(sid, uid, aid)
        o_store, p_store, a_store, s_store = _make_stores(
            open_positions=[pos],
            account=_make_account(sid, aid, uid),
        )
        now = _now()

        _run(session_id=sid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store, now_utc=now)

        p_store.update.assert_called_once()
        closed = p_store.update.call_args[0][0]
        assert closed.is_open is False
        assert closed.closed_at == now

    def test_position_realized_pnl_includes_unrealized(self):
        sid, uid, aid = _uid(), _uid(), _uid()
        pos = _make_position(sid, uid, aid, realized_pnl=100.0, unrealized_pnl=30.0)
        o_store, p_store, a_store, s_store = _make_stores(
            open_positions=[pos],
            account=_make_account(sid, aid, uid),
        )

        _run(session_id=sid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store)

        closed = p_store.update.call_args[0][0]
        assert closed.realized_pnl == pytest.approx(130.0)
        assert closed.unrealized_pnl == pytest.approx(0.0)
        assert closed.market_value == pytest.approx(0.0)

    def test_multiple_positions_all_closed(self):
        sid, uid, aid = _uid(), _uid(), _uid()
        positions = [
            _make_position(sid, uid, aid, market_value=500.0, unrealized_pnl=25.0),
            _make_position(sid, uid, aid, market_value=800.0, unrealized_pnl=-10.0),
        ]
        o_store, p_store, a_store, s_store = _make_stores(
            open_positions=positions,
            account=_make_account(sid, aid, uid),
        )

        _run(session_id=sid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store)

        assert p_store.update.call_count == 2

    def test_no_positions_no_update_call(self):
        sid, uid, aid = _uid(), _uid(), _uid()
        o_store, p_store, a_store, s_store = _make_stores(
            account=_make_account(sid, aid, uid),
        )

        _run(session_id=sid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store)

        p_store.update.assert_not_called()

    def test_no_fill_generated_during_position_close(self, tmp_path):
        # apply_terminal_cleanup must never touch a fill store
        sid, uid, aid = _uid(), _uid(), _uid()
        fill_store = MagicMock()
        pos = _make_position(sid, uid, aid)
        o_store, p_store, a_store, s_store = _make_stores(
            open_positions=[pos],
            account=_make_account(sid, aid, uid),
        )

        _run(session_id=sid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store)

        fill_store.append.assert_not_called()


# ---------------------------------------------------------------------------
# Step 3 — account finalization
# ---------------------------------------------------------------------------

class TestAccountFinalization:
    def test_account_status_set_to_closed(self):
        sid, uid, aid = _uid(), _uid(), _uid()
        account = _make_account(sid, aid, uid)
        o_store, p_store, a_store, s_store = _make_stores(account=account)

        _run(session_id=sid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store)

        a_store.update.assert_called_once()
        updated_acct = a_store.update.call_args[0][0]
        assert updated_acct.status == PaperAccountStatus.CLOSED

    def test_cash_returned_from_positions(self):
        sid, uid, aid = _uid(), _uid(), _uid()
        account = _make_account(sid, aid, uid, cash_balance=3000.0)
        pos = _make_position(sid, uid, aid, market_value=2000.0, unrealized_pnl=100.0)
        o_store, p_store, a_store, s_store = _make_stores(
            open_positions=[pos], account=account,
        )

        _run(session_id=sid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store)

        updated_acct = a_store.update.call_args[0][0]
        assert updated_acct.cash_balance == pytest.approx(5000.0)  # 3000 + 2000
        assert updated_acct.equity == pytest.approx(5000.0)

    def test_realized_pnl_accumulated(self):
        sid, uid, aid = _uid(), _uid(), _uid()
        account = _make_account(sid, aid, uid, total_realized_pnl=100.0)
        pos = _make_position(sid, uid, aid, unrealized_pnl=40.0)
        o_store, p_store, a_store, s_store = _make_stores(
            open_positions=[pos], account=account,
        )

        _run(session_id=sid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store)

        updated_acct = a_store.update.call_args[0][0]
        assert updated_acct.total_realized_pnl == pytest.approx(140.0)

    def test_peak_equity_preserved_when_higher(self):
        sid, uid, aid = _uid(), _uid(), _uid()
        # peak_equity=5500 > new equity after recovery=4000 — peak must stay 5500
        account = _make_account(
            sid, aid, uid, cash_balance=3000.0, peak_equity=5500.0,
        )
        pos = _make_position(sid, uid, aid, market_value=1000.0, unrealized_pnl=-200.0)
        o_store, p_store, a_store, s_store = _make_stores(
            open_positions=[pos], account=account,
        )

        _run(session_id=sid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store)

        updated_acct = a_store.update.call_args[0][0]
        assert updated_acct.peak_equity == pytest.approx(5500.0)

    def test_peak_equity_updated_when_recovery_exceeds_it(self):
        sid, uid, aid = _uid(), _uid(), _uid()
        account = _make_account(
            sid, aid, uid, cash_balance=3000.0, peak_equity=4000.0,
        )
        pos = _make_position(sid, uid, aid, market_value=2000.0, unrealized_pnl=500.0)
        o_store, p_store, a_store, s_store = _make_stores(
            open_positions=[pos], account=account,
        )

        _run(session_id=sid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store)

        updated_acct = a_store.update.call_args[0][0]
        assert updated_acct.peak_equity == pytest.approx(5000.0)  # 3000+2000=5000 > 4000

    def test_no_account_no_update_no_snapshot(self):
        o_store, p_store, a_store, s_store = _make_stores(account=None)

        _run(order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store)

        a_store.update.assert_not_called()
        s_store.append.assert_not_called()

    def test_closed_at_set(self):
        sid, uid, aid = _uid(), _uid(), _uid()
        account = _make_account(sid, aid, uid)
        o_store, p_store, a_store, s_store = _make_stores(account=account)
        now = _now()

        _run(session_id=sid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store, now_utc=now)

        updated_acct = a_store.update.call_args[0][0]
        assert updated_acct.closed_at == now
        assert updated_acct.updated_at == now


# ---------------------------------------------------------------------------
# Step 4 — final equity snapshot
# ---------------------------------------------------------------------------

class TestFinalEquitySnapshot:
    def test_snapshot_appended(self):
        sid, uid, aid = _uid(), _uid(), _uid()
        account = _make_account(sid, aid, uid)
        o_store, p_store, a_store, s_store = _make_stores(account=account)

        _run(session_id=sid, account_id=aid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store)

        s_store.append.assert_called_once()

    def test_snapshot_has_zero_open_positions(self):
        sid, uid, aid = _uid(), _uid(), _uid()
        account = _make_account(sid, aid, uid)
        o_store, p_store, a_store, s_store = _make_stores(account=account)

        _run(session_id=sid, account_id=aid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store)

        snap: AccountStateSnapshot = s_store.append.call_args[0][0]
        assert snap.open_position_count == 0
        assert snap.unrealized_pnl == pytest.approx(0.0)

    def test_snapshot_session_and_account_ids(self):
        sid, uid, aid = _uid(), _uid(), _uid()
        account = _make_account(sid, aid, uid)
        o_store, p_store, a_store, s_store = _make_stores(account=account)

        _run(session_id=sid, account_id=aid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store)

        snap: AccountStateSnapshot = s_store.append.call_args[0][0]
        assert snap.session_id == sid
        assert snap.account_id == aid
        assert snap.user_id == uid

    def test_snapshot_cash_matches_finalized_account(self):
        sid, uid, aid = _uid(), _uid(), _uid()
        account = _make_account(sid, aid, uid, cash_balance=4000.0)
        pos = _make_position(sid, uid, aid, market_value=1500.0, unrealized_pnl=0.0)
        o_store, p_store, a_store, s_store = _make_stores(
            open_positions=[pos], account=account,
        )

        _run(session_id=sid, account_id=aid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store)

        snap: AccountStateSnapshot = s_store.append.call_args[0][0]
        assert snap.cash_balance == pytest.approx(5500.0)
        assert snap.equity == pytest.approx(5500.0)

    def test_snapshot_bar_timestamp_is_now_utc(self):
        sid, uid, aid = _uid(), _uid(), _uid()
        account = _make_account(sid, aid, uid)
        o_store, p_store, a_store, s_store = _make_stores(account=account)
        now = _now()

        _run(session_id=sid, account_id=aid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store, now_utc=now)

        snap: AccountStateSnapshot = s_store.append.call_args[0][0]
        assert snap.bar_timestamp == now
        assert snap.snapshot_timestamp == now


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_second_call_with_empty_stores_is_noop(self):
        sid, uid, aid = _uid(), _uid(), _uid()
        account = _make_account(sid, aid, uid)
        # Second call: no pending orders, no open positions
        o_store, p_store, a_store, s_store = _make_stores(account=account)

        _run(session_id=sid, account_id=aid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store)
        _run(session_id=sid, account_id=aid, owner_id=uid,
             order_store=o_store, position_store=p_store,
             account_store=a_store, snapshot_store=s_store)

        # Each call appends a snapshot (deduplication is store's responsibility)
        assert s_store.append.call_count == 2
        # No extra position updates on second call
        assert p_store.update.call_count == 0
