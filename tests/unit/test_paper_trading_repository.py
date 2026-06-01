"""
Unit tests for backend/paper_trading/repository.py — Phase 4E.1.

Coverage targets:
  - save() — new record, duplicate detection
  - load() — happy path, not-found, wrong-owner (info hiding), UUID guard
  - update() — happy path, not-found, wrong-owner
  - list_all() — owner filtering, sort order, empty dir
  - list_active() — status filtering
  - exists() — UUID guard, present/absent
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.paper_trading.exceptions import (
    PaperTradingPersistenceError,
    PaperTradingSessionAlreadyExistsError,
    PaperTradingSessionNotFoundError,
)
from backend.paper_trading.models import (
    PaperStrategySnapshot,
    PaperTradingSession,
    PaperTradingSessionStatus,
    SimulationAssumptions,
)
from backend.paper_trading.repository import PaperTradingRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_snapshot(snapshot_hash: str = "h1") -> PaperStrategySnapshot:
    return PaperStrategySnapshot(
        draft_id=_uuid(),
        display_name="Test",
        lifecycle_status="draft",
        snapshot_hash=snapshot_hash,
        captured_at=_now(),
        strategy_json='{"name": "test"}',
    )


def _make_session(
    user_id: str | None = None,
    status: PaperTradingSessionStatus = PaperTradingSessionStatus.PENDING,
    created_at: datetime | None = None,
) -> PaperTradingSession:
    uid = user_id or _uuid()
    snap = _make_snapshot()
    return PaperTradingSession(
        session_id=_uuid(),
        user_id=uid,
        draft_id=_uuid(),
        strategy_snapshot_hash=snap.snapshot_hash,
        strategy_snapshot=snap,
        lifecycle_status_at_activation="draft",
        account_id=_uuid(),
        simulation_assumptions=SimulationAssumptions(starting_cash=10_000.0),
        source_mode="provider",
        provider_name="yahoo",
        symbol="AAPL",
        timeframe="1d",
        status=status,
        created_at=created_at or _now(),
        updated_at=_now(),
    )


@pytest.fixture
def repo(tmp_path: Path) -> PaperTradingRepository:
    return PaperTradingRepository(tmp_path)


# ===========================================================================
# save()
# ===========================================================================

class TestSave:
    def test_saves_new_session(self, repo: PaperTradingRepository):
        session = _make_session()
        repo.save(session)
        assert (repo._sessions_dir / f"{session.session_id}.json").exists()

    def test_duplicate_raises(self, repo: PaperTradingRepository):
        session = _make_session()
        repo.save(session)
        with pytest.raises(PaperTradingSessionAlreadyExistsError):
            repo.save(session)

    def test_different_sessions_both_saved(self, repo: PaperTradingRepository):
        s1, s2 = _make_session(), _make_session()
        repo.save(s1)
        repo.save(s2)
        assert repo.exists(s1.session_id)
        assert repo.exists(s2.session_id)


# ===========================================================================
# load()
# ===========================================================================

class TestLoad:
    def test_loads_saved_session(self, repo: PaperTradingRepository):
        session = _make_session()
        repo.save(session)
        loaded = repo.load(session.session_id, session.user_id)
        assert loaded.session_id == session.session_id

    def test_not_found_raises(self, repo: PaperTradingRepository):
        with pytest.raises(PaperTradingSessionNotFoundError):
            repo.load(_uuid(), _uuid())

    def test_wrong_owner_raises_not_found(self, repo: PaperTradingRepository):
        session = _make_session()
        repo.save(session)
        with pytest.raises(PaperTradingSessionNotFoundError):
            repo.load(session.session_id, owner_id=_uuid())

    def test_wrong_owner_indistinguishable_from_not_found(self, repo: PaperTradingRepository):
        session = _make_session()
        repo.save(session)
        exc_wrong_owner = None
        exc_not_found = None
        try:
            repo.load(session.session_id, owner_id=_uuid())
        except PaperTradingSessionNotFoundError as e:
            exc_wrong_owner = e
        try:
            repo.load(_uuid(), _uuid())
        except PaperTradingSessionNotFoundError as e:
            exc_not_found = e
        assert exc_wrong_owner is not None
        assert exc_not_found is not None

    def test_uuid_guard_rejects_traversal(self, repo: PaperTradingRepository):
        with pytest.raises(PaperTradingSessionNotFoundError):
            repo.load("../../../etc/passwd", _uuid())

    def test_uuid_guard_rejects_plain_string(self, repo: PaperTradingRepository):
        with pytest.raises(PaperTradingSessionNotFoundError):
            repo.load("not-a-uuid", _uuid())


# ===========================================================================
# update()
# ===========================================================================

class TestUpdate:
    def test_updates_existing_session(self, repo: PaperTradingRepository):
        session = _make_session()
        repo.save(session)
        updated = session.model_copy(update={
            "status": PaperTradingSessionStatus.RUNNING,
            "updated_at": _now(),
        })
        repo.update(updated, owner_id=session.user_id)
        loaded = repo.load(session.session_id, session.user_id)
        assert loaded.status == PaperTradingSessionStatus.RUNNING

    def test_update_not_found_raises(self, repo: PaperTradingRepository):
        session = _make_session()
        with pytest.raises(PaperTradingSessionNotFoundError):
            repo.update(session, owner_id=session.user_id)

    def test_update_wrong_owner_raises_not_found(self, repo: PaperTradingRepository):
        session = _make_session()
        repo.save(session)
        updated = session.model_copy(update={"updated_at": _now()})
        with pytest.raises(PaperTradingSessionNotFoundError):
            repo.update(updated, owner_id=_uuid())


# ===========================================================================
# list_all()
# ===========================================================================

class TestListAll:
    def test_returns_empty_when_no_dir(self, tmp_path: Path):
        repo = PaperTradingRepository(tmp_path / "nonexistent")
        assert repo.list_all(_uuid()) == []

    def test_returns_only_own_sessions(self, repo: PaperTradingRepository):
        uid = _uuid()
        s1 = _make_session(user_id=uid)
        s2 = _make_session(user_id=uid)
        other = _make_session()
        repo.save(s1)
        repo.save(s2)
        repo.save(other)
        results = repo.list_all(uid)
        assert len(results) == 2
        ids = {r.session_id for r in results}
        assert s1.session_id in ids
        assert s2.session_id in ids
        assert other.session_id not in ids

    def test_sorted_by_created_at(self, repo: PaperTradingRepository):
        uid = _uuid()
        import time
        s1 = _make_session(user_id=uid, created_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
        time.sleep(0.01)
        s2 = _make_session(user_id=uid, created_at=datetime(2024, 6, 1, tzinfo=timezone.utc))
        time.sleep(0.01)
        s3 = _make_session(user_id=uid, created_at=datetime(2024, 12, 1, tzinfo=timezone.utc))
        # Save in reverse order to confirm sort is by created_at, not file order
        repo.save(s3)
        repo.save(s1)
        repo.save(s2)
        results = repo.list_all(uid)
        assert [r.session_id for r in results] == [s1.session_id, s2.session_id, s3.session_id]

    def test_returns_all_statuses(self, repo: PaperTradingRepository):
        uid = _uuid()
        statuses = [
            PaperTradingSessionStatus.PENDING,
            PaperTradingSessionStatus.RUNNING,
            PaperTradingSessionStatus.COMPLETED,
        ]
        for st in statuses:
            repo.save(_make_session(user_id=uid, status=st))
        results = repo.list_all(uid)
        assert len(results) == 3


# ===========================================================================
# list_active()
# ===========================================================================

class TestListActive:
    def test_active_only_pending_running_paused(self, repo: PaperTradingRepository):
        uid = _uuid()
        pending = _make_session(user_id=uid, status=PaperTradingSessionStatus.PENDING)
        running = _make_session(user_id=uid, status=PaperTradingSessionStatus.RUNNING)
        paused = _make_session(user_id=uid, status=PaperTradingSessionStatus.PAUSED)
        completed = _make_session(user_id=uid, status=PaperTradingSessionStatus.COMPLETED)
        failed = _make_session(user_id=uid, status=PaperTradingSessionStatus.FAILED)
        for s in [pending, running, paused, completed, failed]:
            repo.save(s)
        active = repo.list_active(uid)
        active_ids = {s.session_id for s in active}
        assert pending.session_id in active_ids
        assert running.session_id in active_ids
        assert paused.session_id in active_ids
        assert completed.session_id not in active_ids
        assert failed.session_id not in active_ids

    def test_active_excludes_other_owners(self, repo: PaperTradingRepository):
        uid = _uuid()
        mine = _make_session(user_id=uid, status=PaperTradingSessionStatus.RUNNING)
        theirs = _make_session(status=PaperTradingSessionStatus.RUNNING)
        repo.save(mine)
        repo.save(theirs)
        active = repo.list_active(uid)
        assert len(active) == 1
        assert active[0].session_id == mine.session_id


# ===========================================================================
# exists()
# ===========================================================================

class TestExists:
    def test_returns_true_after_save(self, repo: PaperTradingRepository):
        session = _make_session()
        repo.save(session)
        assert repo.exists(session.session_id) is True

    def test_returns_false_when_not_saved(self, repo: PaperTradingRepository):
        assert repo.exists(_uuid()) is False

    def test_uuid_guard_on_exists(self, repo: PaperTradingRepository):
        with pytest.raises(PaperTradingSessionNotFoundError):
            repo.exists("not-a-uuid")

    def test_any_owner_visible(self, repo: PaperTradingRepository):
        session = _make_session()
        repo.save(session)
        # exists() does not enforce ownership — it is for internal checks only
        assert repo.exists(session.session_id) is True
