"""
PaperTradingRepository — Phase 4E.1.

JSON-backed filesystem repository for PaperTradingSession artifacts.

Storage layout:
    {base_path}/sessions/{session_id}.json      — all sessions (all statuses)

All sessions (pending, running, paused, completed, failed, terminated) reside
in the same directory.  Status is recorded in the session JSON and filters
are applied in memory.  No file moves occur on status transition.

Ownership is enforced on every read operation:
    wrong-owner → PaperTradingSessionNotFoundError (same as not-found)

This module handles persistence only.  Lifecycle validation is the
responsibility of the service layer (Phase 4E.3).
"""
from __future__ import annotations

import logging
from pathlib import Path

from backend.core.request_validation import validate_uuid_id
from backend.paper_trading.exceptions import (
    PaperTradingPersistenceError,
    PaperTradingSessionAlreadyExistsError,
    PaperTradingSessionNotFoundError,
)
from backend.paper_trading.models import PaperTradingSession, PaperTradingSessionStatus

logger = logging.getLogger(__name__)


class PaperTradingRepository:
    """
    Filesystem-backed repository for PaperTradingSession records.

    All public methods raise typed exceptions instead of returning sentinels.
    session_id is validated as a UUID before any path construction to prevent
    path traversal.
    """

    def __init__(self, base_path: Path) -> None:
        self._sessions_dir: Path = base_path / "sessions"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        return self._sessions_dir / f"{session_id}.json"

    @staticmethod
    def _serialize(session: PaperTradingSession) -> str:
        return session.model_dump_json() + "\n"

    @staticmethod
    def _deserialize(content: str, path: Path) -> PaperTradingSession:
        try:
            return PaperTradingSession.model_validate_json(content)
        except Exception as exc:
            raise PaperTradingPersistenceError(
                f"failed to deserialize session from '{path.name}': {exc}"
            ) from exc

    def _validate_id(self, session_id: str) -> None:
        """Guard against path traversal: reject non-UUID session_id."""
        try:
            validate_uuid_id(session_id, "session_id")
        except ValueError as exc:
            raise PaperTradingSessionNotFoundError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, session: PaperTradingSession) -> None:
        """
        Persist a new session record.

        Raises PaperTradingSessionAlreadyExistsError if session_id already exists.
        Raises PaperTradingPersistenceError on I/O failure.
        """
        self._ensure_dirs()
        path = self._session_path(session.session_id)
        if path.exists():
            raise PaperTradingSessionAlreadyExistsError(
                f"session '{session.session_id}' already exists; "
                "use update() to overwrite"
            )
        try:
            path.write_text(self._serialize(session), encoding="utf-8")
        except OSError as exc:
            raise PaperTradingPersistenceError(
                f"failed to save session '{session.session_id}': {exc}"
            ) from exc

    def load(self, session_id: str, owner_id: str) -> PaperTradingSession:
        """
        Load a session by id, enforcing ownership.

        Raises PaperTradingSessionNotFoundError when:
          - session_id is not a valid UUID (path traversal guard)
          - no file exists for session_id
          - the session's user_id does not match owner_id (information hiding)

        Raises PaperTradingPersistenceError on I/O or parse failure.
        """
        self._validate_id(session_id)
        path = self._session_path(session_id)
        if not path.exists():
            raise PaperTradingSessionNotFoundError(
                f"session '{session_id}' not found"
            )
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PaperTradingPersistenceError(
                f"failed to read session '{session_id}': {exc}"
            ) from exc
        session = self._deserialize(content, path)
        if session.user_id != owner_id:
            raise PaperTradingSessionNotFoundError(
                f"session '{session_id}' not found"
            )
        return session

    def update(self, session: PaperTradingSession, owner_id: str) -> None:
        """
        Overwrite an existing session record.

        Performs ownership check via load() before writing.

        Raises PaperTradingSessionNotFoundError if session_id is missing or
        belongs to a different user.
        Raises PaperTradingPersistenceError on I/O failure.
        """
        self.load(session.session_id, owner_id=owner_id)  # ownership check
        try:
            self._session_path(session.session_id).write_text(
                self._serialize(session), encoding="utf-8"
            )
        except OSError as exc:
            raise PaperTradingPersistenceError(
                f"failed to update session '{session.session_id}': {exc}"
            ) from exc

    def list_all(self, owner_id: str) -> list[PaperTradingSession]:
        """
        Return all sessions owned by owner_id, sorted by created_at ascending.

        Sessions belonging to other users are silently excluded.
        Returns empty list when the storage directory does not exist.
        Raises PaperTradingPersistenceError if any file cannot be read or parsed.
        """
        if not self._sessions_dir.exists():
            return []
        paths = sorted(
            p for p in self._sessions_dir.iterdir()
            if p.is_file() and p.suffix == ".json"
        )
        sessions: list[PaperTradingSession] = []
        for path in paths:
            try:
                content = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise PaperTradingPersistenceError(
                    f"failed to read session file '{path.name}': {exc}"
                ) from exc
            session = self._deserialize(content, path)
            if session.user_id != owner_id:
                continue
            sessions.append(session)
        sessions.sort(key=lambda s: s.created_at)
        return sessions

    def list_active(self, owner_id: str) -> list[PaperTradingSession]:
        """
        Return sessions in PENDING, RUNNING, or PAUSED status for owner_id.

        Convenience filter over list_all().  Preserves created_at sort order.
        """
        active_statuses = {
            PaperTradingSessionStatus.PENDING,
            PaperTradingSessionStatus.RUNNING,
            PaperTradingSessionStatus.PAUSED,
        }
        return [
            s for s in self.list_all(owner_id)
            if s.status in active_statuses
        ]

    def exists(self, session_id: str) -> bool:
        """Return True if a session file exists for session_id (any owner)."""
        self._validate_id(session_id)
        return self._session_path(session_id).exists()
