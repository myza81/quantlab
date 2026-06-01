"""
Paper Trading terminal cleanup — Phase P8B.

Applies ordered cleanup steps when a session transitions to a terminal state
(TERMINATED, COMPLETED, FAILED).  Called by route handlers immediately before
the session status is flipped, so the stored record reflects a consistent
end-state.

Cleanup sequence:
    1. Cancel all PENDING_FILL orders (they cannot be filled once the session ends).
    2. Mark open positions as closed at their last known (mark-to-market) price.
       No fill record is generated; this is an administrative mark-down.
    3. Finalize the account: return position cash to cash_balance, mark CLOSED.
    4. Append a final equity snapshot (open_position_count=0, unrealized_pnl=0).

Idempotency characteristics:
    - Pending orders: mark_cancelled is idempotent if the order is no longer in
      pending.json (silently skipped).
    - Positions: list_open_positions returns only is_open=True records, so a
      second cleanup call finds no open positions to process.
    - Snapshots: AccountStateSnapshotStore.append() deduplicates by
      (session_id, bar_timestamp); a second call at the same timestamp is a no-op.
    - Account: model_copy + update is safe to re-apply; values converge.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.backtesting
    backend.api
    backend.data_providers
"""
from __future__ import annotations

import uuid
from datetime import datetime

from backend.paper_trading.execution_models import (
    OrderDirection,
    PaperOrderStatus,
)
from backend.paper_trading.execution_stores import (
    PaperOrderStore,
    PaperPositionStore,
)
from backend.paper_trading.models import (
    AccountStateSnapshot,
    PaperAccount,
    PaperAccountStatus,
)
from backend.paper_trading.stores import (
    AccountStateSnapshotStore,
    PaperAccountStore,
)


def apply_terminal_cleanup(
    *,
    session_id: str,
    account_id: str,
    owner_id: str,
    order_store: PaperOrderStore,
    position_store: PaperPositionStore,
    account_store: PaperAccountStore,
    snapshot_store: AccountStateSnapshotStore,
    now_utc: datetime,
) -> None:
    """
    Apply terminal cleanup steps before a session status flip to a terminal state.

    Steps are applied in dependency order: orders → positions → account → snapshot.
    Each step is individually idempotent (safe to call multiple times).

    No fill records are generated for forced position closes.
    No broker concepts are introduced.
    Does not raise on missing account (graceful degradation for sessions that
    never activated and therefore have no positions or fills).

    Parameters
    ----------
    session_id:     UUID of the paper trading session.
    account_id:     UUID of the associated PaperAccount (from session.account_id).
    owner_id:       user_id of the session owner — used for ownership-filtered
                    store queries only; never written to records.
    order_store:    store for pending/filled/cancelled/rejected orders.
    position_store: store for open/closed positions.
    account_store:  store for the PaperAccount record.
    snapshot_store: store for AccountStateSnapshot (equity curve) records.
    now_utc:        wall-clock time used as the closure timestamp for all records.
    """
    # ------------------------------------------------------------------
    # Step 1 — cancel all pending orders
    # ------------------------------------------------------------------
    pending_orders = order_store.load_pending(session_id, owner_id=owner_id)
    for order in pending_orders:
        cancelled = order.model_copy(update={
            "status": PaperOrderStatus.CANCELLED,
            "cancellation_reason": "session_terminated",
            "updated_at": now_utc,
        })
        order_store.mark_cancelled(cancelled, "session_terminated")

    # ------------------------------------------------------------------
    # Step 2 — close open positions at last known (mark-to-market) price
    # ------------------------------------------------------------------
    open_positions = position_store.list_open_positions(session_id, owner_id=owner_id)
    recovered_cash: float = 0.0
    net_realized_delta: float = 0.0

    for pos in open_positions:
        # Recover the notional sale proceeds at last-known mark price.
        # Mark-to-market unrealized P&L is recognized as realized P&L.
        recovered_cash += pos.market_value
        net_realized_delta += pos.unrealized_pnl

        closed_pos = pos.model_copy(update={
            "is_open":        False,
            "closed_at":      now_utc,
            "last_updated_at": now_utc,
            "realized_pnl":   pos.realized_pnl + pos.unrealized_pnl,
            "unrealized_pnl": 0.0,
            "market_value":   0.0,
        })
        position_store.update(closed_pos)

    # ------------------------------------------------------------------
    # Step 3 — finalize account state
    # ------------------------------------------------------------------
    try:
        account = account_store.load_by_session_id(session_id)
    except Exception:
        # Session never activated (no account) or account load failure.
        # Snapshot step is skipped since account metadata is required.
        return

    new_cash = account.cash_balance + recovered_cash
    new_equity = new_cash  # no open positions; equity equals cash
    new_peak = max(account.peak_equity, new_equity)
    new_dd_pct = (
        (new_peak - new_equity) / new_peak * 100.0 if new_peak > 0.0 else 0.0
    )
    new_realized = account.total_realized_pnl + net_realized_delta

    closed_account = account.model_copy(update={
        "cash_balance":        new_cash,
        "equity":              new_equity,
        "available_cash":      new_cash,
        "peak_equity":         new_peak,
        "current_drawdown_pct": new_dd_pct,
        "total_realized_pnl":  new_realized,
        "status":              PaperAccountStatus.CLOSED,
        "closed_at":           now_utc,
        "updated_at":          now_utc,
    })
    account_store.update(closed_account)

    # ------------------------------------------------------------------
    # Step 4 — final equity snapshot
    # ------------------------------------------------------------------
    snapshot = AccountStateSnapshot(
        snapshot_id=str(uuid.uuid4()),
        session_id=session_id,
        account_id=account_id,
        user_id=owner_id,
        bar_timestamp=now_utc,
        snapshot_timestamp=now_utc,
        cash_balance=new_cash,
        equity=new_equity,
        available_cash=new_cash,
        peak_equity=new_peak,
        current_drawdown_pct=new_dd_pct,
        open_position_count=0,
        realized_pnl=new_realized,
        unrealized_pnl=0.0,
        created_at=now_utc,
    )
    snapshot_store.append(snapshot)
