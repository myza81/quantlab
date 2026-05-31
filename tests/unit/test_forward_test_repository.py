"""
Tests for Phase 4C.1 — ForwardTestRepository.

Covers:
  - save / load / update round-trip
  - ForwardTestSessionAlreadyExistsError on duplicate save
  - ForwardTestSessionNotFoundError on missing load
  - wrong-owner load returns NotFoundError (information hiding)
  - invalid session_id (non-UUID) rejected before path construction
  - list_all returns only sessions owned by requested user
  - list_all returns empty list when directory does not exist
  - list_all returns sessions sorted by created_at
  - list_active filters to pending/running/paused only
  - update overwrites existing session
  - update with wrong owner raises NotFoundError
  - exists() returns True for saved session, False for missing
  - storage directory created on first save
  - config-driven path: storage path comes from base_path, not hardcoded
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.forward_testing.exceptions import (
    ForwardTestPersistenceError,
    ForwardTestSessionAlreadyExistsError,
    ForwardTestSessionNotFoundError,
)
from backend.forward_testing.models import (
    ForwardTestSession,
    ForwardTestSessionStatus,
    StrategySnapshot,
)
from backend.forward_testing.repository import ForwardTestRepository

_UTC = timezone.utc
_NOW = datetime(2026, 5, 29, 12, 0, 0, tzinfo=_UTC)
_LATER = datetime(2026, 5, 29, 13, 0, 0, tzinfo=_UTC)
_EARLIEST = datetime(2026, 5, 29, 10, 0, 0, tzinfo=_UTC)

_USER_A = str(uuid.uuid4())
_USER_B = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _snapshot() -> StrategySnapshot:
    return StrategySnapshot(
        draft_id=str(uuid.uuid4()),
        display_name="Test Strategy",
        lifecycle_status="backtested",
        snapshot_hash="abc123" * 10,
        captured_at=_NOW,
        strategy_json='{"draft_id": "test"}',
    )


def _session(
    user_id: str = _USER_A,
    session_id: str | None = None,
    status: ForwardTestSessionStatus = ForwardTestSessionStatus.PENDING,
    created_at: datetime = _NOW,
    **kw,
) -> ForwardTestSession:
    if session_id is None:
        session_id = str(uuid.uuid4())
    return ForwardTestSession(
        session_id=session_id,
        user_id=user_id,
        draft_id=str(uuid.uuid4()),
        strategy_snapshot=_snapshot(),
        lifecycle_status_at_activation="backtested",
        source_mode="provider",
        provider_name="yahoo",
        symbol="AAPL",
        timeframe="1d",
        warmup_bars_required=20,
        status=status,
        created_at=created_at,
        updated_at=created_at,
        **kw,
    )


def _repo(tmp_path: Path) -> ForwardTestRepository:
    return ForwardTestRepository(tmp_path)


# ---------------------------------------------------------------------------
# TestForwardTestRepositorySave
# ---------------------------------------------------------------------------

class TestForwardTestRepositorySave:
    def test_save_creates_file(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        session = _session()
        repo.save(session)
        assert (tmp_path / "sessions" / f"{session.session_id}.json").exists()

    def test_save_creates_storage_directory(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        assert not (tmp_path / "sessions").exists()
        repo.save(_session())
        assert (tmp_path / "sessions").exists()

    def test_save_duplicate_raises_already_exists_error(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        session = _session()
        repo.save(session)
        with pytest.raises(ForwardTestSessionAlreadyExistsError, match="already exists"):
            repo.save(session)

    def test_save_different_session_ids_both_persist(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        s1 = _session()
        s2 = _session()
        repo.save(s1)
        repo.save(s2)
        assert (tmp_path / "sessions" / f"{s1.session_id}.json").exists()
        assert (tmp_path / "sessions" / f"{s2.session_id}.json").exists()

    def test_saved_file_is_utf8(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        session = _session()
        repo.save(session)
        path = tmp_path / "sessions" / f"{session.session_id}.json"
        content = path.read_bytes()
        assert content.decode("utf-8")

    def test_storage_path_is_config_driven_not_hardcoded(self, tmp_path: Path) -> None:
        custom_base = tmp_path / "custom_storage"
        repo = ForwardTestRepository(custom_base)
        session = _session()
        repo.save(session)
        assert (custom_base / "sessions" / f"{session.session_id}.json").exists()
        # Default path must NOT be used
        assert not (tmp_path / "storage").exists()


# ---------------------------------------------------------------------------
# TestForwardTestRepositoryLoad
# ---------------------------------------------------------------------------

class TestForwardTestRepositoryLoad:
    def test_load_roundtrip(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        original = _session()
        repo.save(original)
        loaded = repo.load(original.session_id, owner_id=_USER_A)
        assert loaded.session_id == original.session_id
        assert loaded.user_id == original.user_id
        assert loaded.symbol == original.symbol

    def test_load_missing_session_raises_not_found(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        with pytest.raises(ForwardTestSessionNotFoundError):
            repo.load(str(uuid.uuid4()), owner_id=_USER_A)

    def test_load_wrong_owner_raises_not_found(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        session = _session(user_id=_USER_A)
        repo.save(session)
        with pytest.raises(ForwardTestSessionNotFoundError):
            repo.load(session.session_id, owner_id=_USER_B)

    def test_wrong_owner_error_indistinguishable_from_not_found(
        self, tmp_path: Path
    ) -> None:
        repo = _repo(tmp_path)
        session = _session(user_id=_USER_A)
        repo.save(session)
        try:
            repo.load(session.session_id, owner_id=_USER_B)
        except ForwardTestSessionNotFoundError:
            pass  # expected — same exception type as not-found
        else:
            pytest.fail("Expected ForwardTestSessionNotFoundError for wrong owner")

    def test_invalid_session_id_rejected_before_path_construction(
        self, tmp_path: Path
    ) -> None:
        repo = _repo(tmp_path)
        with pytest.raises(ForwardTestSessionNotFoundError):
            repo.load("../../etc/passwd", owner_id=_USER_A)

    def test_non_uuid_session_id_rejected(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        with pytest.raises(ForwardTestSessionNotFoundError):
            repo.load("not-a-uuid", owner_id=_USER_A)

    def test_strategy_snapshot_survives_roundtrip(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        session = _session()
        repo.save(session)
        loaded = repo.load(session.session_id, owner_id=_USER_A)
        assert loaded.strategy_snapshot.snapshot_hash == session.strategy_snapshot.snapshot_hash
        assert loaded.strategy_snapshot.strategy_json == session.strategy_snapshot.strategy_json


# ---------------------------------------------------------------------------
# TestForwardTestRepositoryListAll
# ---------------------------------------------------------------------------

class TestForwardTestRepositoryListAll:
    def test_list_all_empty_when_no_sessions(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        assert repo.list_all(owner_id=_USER_A) == []

    def test_list_all_empty_directory_returns_empty(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        result = repo.list_all(owner_id=_USER_A)
        assert result == []

    def test_list_all_returns_only_user_sessions(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        s_a1 = _session(user_id=_USER_A)
        s_a2 = _session(user_id=_USER_A)
        s_b = _session(user_id=_USER_B)
        repo.save(s_a1)
        repo.save(s_a2)
        repo.save(s_b)
        result = repo.list_all(owner_id=_USER_A)
        ids = {s.session_id for s in result}
        assert s_a1.session_id in ids
        assert s_a2.session_id in ids
        assert s_b.session_id not in ids

    def test_list_all_sorted_by_created_at(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        s_latest = _session(user_id=_USER_A, created_at=_LATER)
        s_earliest = _session(user_id=_USER_A, created_at=_EARLIEST)
        repo.save(s_latest)
        repo.save(s_earliest)
        result = repo.list_all(owner_id=_USER_A)
        assert result[0].session_id == s_earliest.session_id
        assert result[1].session_id == s_latest.session_id


# ---------------------------------------------------------------------------
# TestForwardTestRepositoryListActive
# ---------------------------------------------------------------------------

class TestForwardTestRepositoryListActive:
    def test_list_active_returns_pending_and_running_and_paused(
        self, tmp_path: Path
    ) -> None:
        repo = _repo(tmp_path)
        s_pending = _session(status=ForwardTestSessionStatus.PENDING)
        s_running = _session(
            status=ForwardTestSessionStatus.RUNNING,
            activation_timestamp=_NOW,
        )
        s_paused = _session(
            status=ForwardTestSessionStatus.PAUSED,
            activation_timestamp=_NOW,
        )
        s_completed = _session(status=ForwardTestSessionStatus.COMPLETED)
        s_failed = _session(status=ForwardTestSessionStatus.FAILED)
        for s in (s_pending, s_running, s_paused, s_completed, s_failed):
            repo.save(s)
        result = repo.list_active(owner_id=_USER_A)
        result_ids = {s.session_id for s in result}
        assert s_pending.session_id in result_ids
        assert s_running.session_id in result_ids
        assert s_paused.session_id in result_ids
        assert s_completed.session_id not in result_ids
        assert s_failed.session_id not in result_ids


# ---------------------------------------------------------------------------
# TestForwardTestRepositoryUpdate
# ---------------------------------------------------------------------------

class TestForwardTestRepositoryUpdate:
    def test_update_overwrites_session(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        session = _session()
        repo.save(session)
        updated = session.model_copy(update={
            "status": ForwardTestSessionStatus.RUNNING,
            "activation_timestamp": _LATER,
            "updated_at": _LATER,
        })
        repo.update(updated, owner_id=_USER_A)
        loaded = repo.load(session.session_id, owner_id=_USER_A)
        assert loaded.status == ForwardTestSessionStatus.RUNNING
        assert loaded.activation_timestamp == _LATER

    def test_update_wrong_owner_raises_not_found(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        session = _session(user_id=_USER_A)
        repo.save(session)
        updated = session.model_copy(update={"updated_at": _LATER})
        with pytest.raises(ForwardTestSessionNotFoundError):
            repo.update(updated, owner_id=_USER_B)

    def test_update_missing_session_raises_not_found(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        session = _session()
        with pytest.raises(ForwardTestSessionNotFoundError):
            repo.update(session, owner_id=_USER_A)


# ---------------------------------------------------------------------------
# TestForwardTestRepositoryExists
# ---------------------------------------------------------------------------

class TestForwardTestRepositoryExists:
    def test_exists_true_after_save(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        session = _session()
        repo.save(session)
        assert repo.exists(session.session_id) is True

    def test_exists_false_for_missing(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        assert repo.exists(str(uuid.uuid4())) is False

    def test_exists_raises_for_non_uuid(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        with pytest.raises(ForwardTestSessionNotFoundError):
            repo.exists("../../etc/passwd")
