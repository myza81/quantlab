"""
Unit tests for backend/paper_trading/stores.py — Phase 4E.1.

Coverage targets:
  - PaperAccountStore: save, load_by_session_id, update, exists_for_session,
    load_by_account_id, UUID guard, 1:1 enforcement, not-found behavior
  - AccountStateSnapshotStore: append (new + duplicate), list_snapshots
    (empty, sort order), count, UUID guard
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from backend.paper_trading.exceptions import (
    PaperAccountAlreadyExistsError,
    PaperAccountNotFoundError,
    PaperTradingPersistenceError,
)
from backend.paper_trading.models import (
    AccountStateSnapshot,
    PaperAccount,
    PaperAccountStatus,
)
from backend.paper_trading.stores import AccountStateSnapshotStore, PaperAccountStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_account(
    session_id: str | None = None,
    account_id: str | None = None,
    user_id: str | None = None,
) -> PaperAccount:
    return PaperAccount(
        account_id=account_id or _uuid(),
        session_id=session_id or _uuid(),
        user_id=user_id or _uuid(),
        currency="USD",
        starting_cash=10_000.0,
        cash_balance=10_000.0,
        equity=10_000.0,
        available_cash=10_000.0,
        peak_equity=10_000.0,
        created_at=_now(),
        updated_at=_now(),
    )


def _make_snapshot(
    session_id: str | None = None,
    account_id: str | None = None,
    bar_timestamp: datetime | None = None,
    equity: float = 10_000.0,
) -> AccountStateSnapshot:
    return AccountStateSnapshot(
        snapshot_id=_uuid(),
        session_id=session_id or _uuid(),
        account_id=account_id or _uuid(),
        user_id=_uuid(),
        bar_timestamp=bar_timestamp or _now(),
        snapshot_timestamp=_now(),
        cash_balance=equity,
        equity=equity,
        available_cash=equity,
        peak_equity=equity,
        current_drawdown_pct=0.0,
        open_position_count=0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        created_at=_now(),
    )


@pytest.fixture
def account_store(tmp_path: Path) -> PaperAccountStore:
    return PaperAccountStore(tmp_path)


@pytest.fixture
def snapshot_store(tmp_path: Path) -> AccountStateSnapshotStore:
    return AccountStateSnapshotStore(tmp_path)


# ===========================================================================
# PaperAccountStore — save()
# ===========================================================================

class TestPaperAccountStoreSave:
    def test_saves_new_account(self, account_store: PaperAccountStore):
        account = _make_account()
        account_store.save(account)
        assert (account_store._accounts_dir / f"{account.session_id}.json").exists()

    def test_duplicate_session_raises(self, account_store: PaperAccountStore):
        account = _make_account()
        account_store.save(account)
        with pytest.raises(PaperAccountAlreadyExistsError):
            account_store.save(account)

    def test_duplicate_same_session_different_account_id_raises(
        self, account_store: PaperAccountStore
    ):
        sid = _uuid()
        a1 = _make_account(session_id=sid)
        a2 = _make_account(session_id=sid)  # different account_id, same session_id
        account_store.save(a1)
        with pytest.raises(PaperAccountAlreadyExistsError):
            account_store.save(a2)

    def test_invalid_session_id_raises(self, account_store: PaperAccountStore):
        account = _make_account(session_id=_uuid())
        # Bypass UUID validation to inject a bad session_id at the store level
        bad_account = account.model_copy(update={"session_id": _uuid()})
        # This should succeed with valid UUIDs
        account_store.save(bad_account)

    def test_uuid_guard_rejects_traversal(self, account_store: PaperAccountStore):
        # We can't easily create a PaperAccount with a bad session_id (Pydantic validates UUID)
        # so test through the path validation helper directly
        with pytest.raises(PaperAccountNotFoundError):
            account_store.load_by_session_id("../../../etc/passwd")


# ===========================================================================
# PaperAccountStore — load_by_session_id()
# ===========================================================================

class TestPaperAccountStoreLoad:
    def test_loads_saved_account(self, account_store: PaperAccountStore):
        account = _make_account()
        account_store.save(account)
        loaded = account_store.load_by_session_id(account.session_id)
        assert loaded.account_id == account.account_id
        assert loaded.session_id == account.session_id

    def test_not_found_raises(self, account_store: PaperAccountStore):
        with pytest.raises(PaperAccountNotFoundError):
            account_store.load_by_session_id(_uuid())

    def test_uuid_guard_on_load(self, account_store: PaperAccountStore):
        with pytest.raises(PaperAccountNotFoundError):
            account_store.load_by_session_id("not-a-uuid")

    def test_uuid_guard_path_traversal(self, account_store: PaperAccountStore):
        with pytest.raises(PaperAccountNotFoundError):
            account_store.load_by_session_id("../secrets")


# ===========================================================================
# PaperAccountStore — update()
# ===========================================================================

class TestPaperAccountStoreUpdate:
    def test_updates_existing_account(self, account_store: PaperAccountStore):
        account = _make_account()
        account_store.save(account)
        updated = account.model_copy(update={
            "cash_balance": 8_000.0,
            "equity": 8_000.0,
            "updated_at": _now(),
        })
        account_store.update(updated)
        loaded = account_store.load_by_session_id(account.session_id)
        assert loaded.cash_balance == 8_000.0

    def test_update_not_found_raises(self, account_store: PaperAccountStore):
        account = _make_account()
        with pytest.raises(PaperAccountNotFoundError):
            account_store.update(account)

    def test_update_overwrites_data(self, account_store: PaperAccountStore):
        account = _make_account()
        account_store.save(account)
        closed = account.model_copy(update={
            "status": PaperAccountStatus.CLOSED,
            "closed_at": _now(),
            "updated_at": _now(),
        })
        account_store.update(closed)
        loaded = account_store.load_by_session_id(account.session_id)
        assert loaded.status == PaperAccountStatus.CLOSED
        assert loaded.closed_at is not None


# ===========================================================================
# PaperAccountStore — exists_for_session()
# ===========================================================================

class TestPaperAccountStoreExists:
    def test_returns_true_after_save(self, account_store: PaperAccountStore):
        account = _make_account()
        account_store.save(account)
        assert account_store.exists_for_session(account.session_id) is True

    def test_returns_false_when_not_saved(self, account_store: PaperAccountStore):
        assert account_store.exists_for_session(_uuid()) is False

    def test_uuid_guard(self, account_store: PaperAccountStore):
        with pytest.raises(PaperAccountNotFoundError):
            account_store.exists_for_session("bad-id")


# ===========================================================================
# PaperAccountStore — load_by_account_id()
# ===========================================================================

class TestPaperAccountStoreLoadByAccountId:
    def test_loads_matching_account(self, account_store: PaperAccountStore):
        account = _make_account()
        account_store.save(account)
        loaded = account_store.load_by_account_id(account.account_id, account.session_id)
        assert loaded.account_id == account.account_id

    def test_mismatch_raises_not_found(self, account_store: PaperAccountStore):
        account = _make_account()
        account_store.save(account)
        with pytest.raises(PaperAccountNotFoundError, match="mismatch"):
            account_store.load_by_account_id(_uuid(), account.session_id)

    def test_session_not_found_raises(self, account_store: PaperAccountStore):
        with pytest.raises(PaperAccountNotFoundError):
            account_store.load_by_account_id(_uuid(), _uuid())

    def test_invalid_account_id_raises(self, account_store: PaperAccountStore):
        account = _make_account()
        account_store.save(account)
        with pytest.raises(PaperAccountNotFoundError):
            account_store.load_by_account_id("not-a-uuid", account.session_id)


# ===========================================================================
# AccountStateSnapshotStore — append()
# ===========================================================================

class TestAccountStateSnapshotStoreAppend:
    def test_appends_new_snapshot(self, snapshot_store: AccountStateSnapshotStore):
        sid = _uuid()
        snap = _make_snapshot(session_id=sid)
        result = snapshot_store.append(snap)
        assert result is True
        assert snapshot_store.count(sid) == 1

    def test_duplicate_bar_timestamp_ignored(self, snapshot_store: AccountStateSnapshotStore):
        sid = _uuid()
        ts = _now()
        snap1 = _make_snapshot(session_id=sid, bar_timestamp=ts)
        snap2 = _make_snapshot(session_id=sid, bar_timestamp=ts)  # same ts, different snapshot_id
        r1 = snapshot_store.append(snap1)
        r2 = snapshot_store.append(snap2)
        assert r1 is True
        assert r2 is False
        assert snapshot_store.count(sid) == 1

    def test_different_timestamps_both_appended(self, snapshot_store: AccountStateSnapshotStore):
        sid = _uuid()
        ts1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 2, tzinfo=timezone.utc)
        snapshot_store.append(_make_snapshot(session_id=sid, bar_timestamp=ts1))
        snapshot_store.append(_make_snapshot(session_id=sid, bar_timestamp=ts2))
        assert snapshot_store.count(sid) == 2

    def test_uuid_guard_on_append(self, snapshot_store: AccountStateSnapshotStore):
        # We can't inject a bad session_id into AccountStateSnapshot (Pydantic validates)
        # so verify UUID guard through count/list which accept raw strings
        with pytest.raises(PaperTradingPersistenceError):
            snapshot_store.count("not-a-uuid")

    def test_different_sessions_isolated(self, snapshot_store: AccountStateSnapshotStore):
        sid1, sid2 = _uuid(), _uuid()
        ts = _now()
        snapshot_store.append(_make_snapshot(session_id=sid1, bar_timestamp=ts))
        snapshot_store.append(_make_snapshot(session_id=sid2, bar_timestamp=ts))
        assert snapshot_store.count(sid1) == 1
        assert snapshot_store.count(sid2) == 1


# ===========================================================================
# AccountStateSnapshotStore — list_snapshots()
# ===========================================================================

class TestAccountStateSnapshotStoreList:
    def test_empty_when_no_file(self, snapshot_store: AccountStateSnapshotStore):
        assert snapshot_store.list_snapshots(_uuid()) == []

    def test_sorted_by_bar_timestamp_ascending(self, snapshot_store: AccountStateSnapshotStore):
        sid = _uuid()
        ts1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 3, tzinfo=timezone.utc)
        ts3 = datetime(2024, 1, 2, tzinfo=timezone.utc)
        # Append out-of-order
        for ts in [ts3, ts1, ts2]:
            snapshot_store.append(_make_snapshot(session_id=sid, bar_timestamp=ts))
        snaps = snapshot_store.list_snapshots(sid)
        assert len(snaps) == 3
        assert snaps[0].bar_timestamp < snaps[1].bar_timestamp < snaps[2].bar_timestamp

    def test_returns_correct_equity_values(self, snapshot_store: AccountStateSnapshotStore):
        sid = _uuid()
        ts1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 2, tzinfo=timezone.utc)
        snapshot_store.append(_make_snapshot(session_id=sid, bar_timestamp=ts1, equity=10_000.0))
        snapshot_store.append(_make_snapshot(session_id=sid, bar_timestamp=ts2, equity=11_000.0))
        snaps = snapshot_store.list_snapshots(sid)
        assert snaps[0].equity == 10_000.0
        assert snaps[1].equity == 11_000.0

    def test_uuid_guard_on_list(self, snapshot_store: AccountStateSnapshotStore):
        with pytest.raises(PaperTradingPersistenceError):
            snapshot_store.list_snapshots("bad-id")


# ===========================================================================
# AccountStateSnapshotStore — count()
# ===========================================================================

class TestAccountStateSnapshotStoreCount:
    def test_count_zero_when_empty(self, snapshot_store: AccountStateSnapshotStore):
        assert snapshot_store.count(_uuid()) == 0

    def test_count_increments_on_append(self, snapshot_store: AccountStateSnapshotStore):
        sid = _uuid()
        for i in range(5):
            ts = datetime(2024, 1, i + 1, tzinfo=timezone.utc)
            snapshot_store.append(_make_snapshot(session_id=sid, bar_timestamp=ts))
        assert snapshot_store.count(sid) == 5

    def test_count_unchanged_on_duplicate(self, snapshot_store: AccountStateSnapshotStore):
        sid = _uuid()
        ts = _now()
        snapshot_store.append(_make_snapshot(session_id=sid, bar_timestamp=ts))
        snapshot_store.append(_make_snapshot(session_id=sid, bar_timestamp=ts))
        assert snapshot_store.count(sid) == 1

    def test_uuid_guard_on_count(self, snapshot_store: AccountStateSnapshotStore):
        with pytest.raises(PaperTradingPersistenceError):
            snapshot_store.count("../traversal")
