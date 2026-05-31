"""
ForwardTestRepository — Phase 4C.1.

JSON-backed filesystem repository for ForwardTestSession artifacts.

Storage layout:
    {base_path}/sessions/{session_id}.json      — all sessions (all statuses)

All sessions (pending, running, paused, completed, failed, terminated) reside
in the same directory.  Status is recorded in the session JSON and filters
are applied in memory.  No file moves occur on status transition.

Ownership is enforced on every read operation:
    wrong-owner → ForwardTestSessionNotFoundError (same as not-found)

This module handles persistence only.  Lifecycle validation is the
responsibility of the service layer (Phase 4C.4).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.core.request_validation import validate_uuid_id
from backend.forward_testing.exceptions import (
    ForwardTestPersistenceError,
    ForwardTestSessionAlreadyExistsError,
    ForwardTestSessionNotFoundError,
)
from backend.forward_testing.models import ForwardTestSession, ForwardTestSessionStatus

logger = logging.getLogger(__name__)


class ForwardTestRepository:
    """
    Filesystem-backed repository for ForwardTestSession artifacts.

    All public methods raise typed errors instead of returning sentinels.
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
    def _serialize(session: ForwardTestSession) -> str:
        return session.model_dump_json() + "\n"

    @staticmethod
    def _deserialize(content: str, path: Path) -> ForwardTestSession:
        try:
            return ForwardTestSession.model_validate_json(content)
        except Exception as exc:
            raise ForwardTestPersistenceError(
                f"failed to deserialize session from '{path.name}': {exc}"
            ) from exc

    def _validate_id(self, session_id: str) -> None:
        """Guard against path traversal: reject non-UUID session_id."""
        try:
            validate_uuid_id(session_id, "session_id")
        except ValueError as exc:
            raise ForwardTestSessionNotFoundError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, session: ForwardTestSession) -> None:
        """
        Persist a new session record.

        Raises ForwardTestSessionAlreadyExistsError if session_id already exists.
        Raises ForwardTestPersistenceError on I/O failure.
        """
        self._ensure_dirs()
        path = self._session_path(session.session_id)
        if path.exists():
            raise ForwardTestSessionAlreadyExistsError(
                f"session '{session.session_id}' already exists; "
                "use update() to overwrite"
            )
        try:
            path.write_text(self._serialize(session), encoding="utf-8")
        except OSError as exc:
            raise ForwardTestPersistenceError(
                f"failed to save session '{session.session_id}': {exc}"
            ) from exc

    def load(self, session_id: str, owner_id: str) -> ForwardTestSession:
        """
        Load a session by id, enforcing ownership.

        Raises ForwardTestSessionNotFoundError when:
          - session_id is not a valid UUID (path traversal guard)
          - no file exists for session_id
          - the session's user_id does not match owner_id (information hiding)

        Raises ForwardTestPersistenceError on I/O or parse failure.
        """
        self._validate_id(session_id)
        path = self._session_path(session_id)
        if not path.exists():
            raise ForwardTestSessionNotFoundError(
                f"session '{session_id}' not found"
            )
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ForwardTestPersistenceError(
                f"failed to read session '{session_id}': {exc}"
            ) from exc
        session = self._deserialize(content, path)
        if session.user_id != owner_id:
            raise ForwardTestSessionNotFoundError(
                f"session '{session_id}' not found"
            )
        return session

    def update(self, session: ForwardTestSession, owner_id: str) -> None:
        """
        Overwrite an existing session record.

        Performs ownership check via load() before writing.

        Raises ForwardTestSessionNotFoundError if session_id is missing or
        belongs to a different user.
        Raises ForwardTestPersistenceError on I/O failure.
        """
        self.load(session.session_id, owner_id=owner_id)  # ownership check
        try:
            self._session_path(session.session_id).write_text(
                self._serialize(session), encoding="utf-8"
            )
        except OSError as exc:
            raise ForwardTestPersistenceError(
                f"failed to update session '{session.session_id}': {exc}"
            ) from exc

    def list_all(self, owner_id: str) -> list[ForwardTestSession]:
        """
        Return all sessions owned by owner_id, sorted by created_at ascending.

        Legacy sessions (user_id missing) are never returned.
        Returns empty list when the storage directory does not exist.
        Raises ForwardTestPersistenceError if any file cannot be read or parsed.
        """
        if not self._sessions_dir.exists():
            return []
        paths = sorted(
            p for p in self._sessions_dir.iterdir()
            if p.is_file() and p.suffix == ".json"
        )
        sessions: list[ForwardTestSession] = []
        for path in paths:
            try:
                content = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise ForwardTestPersistenceError(
                    f"failed to read session file '{path.name}': {exc}"
                ) from exc
            session = self._deserialize(content, path)
            if session.user_id != owner_id:
                continue
            sessions.append(session)
        sessions.sort(key=lambda s: s.created_at)
        return sessions

    def list_active(self, owner_id: str) -> list[ForwardTestSession]:
        """
        Return sessions in PENDING, RUNNING, or PAUSED status for owner_id.

        Convenience filter over list_all(). Preserves created_at sort order.
        """
        active_statuses = {
            ForwardTestSessionStatus.PENDING,
            ForwardTestSessionStatus.RUNNING,
            ForwardTestSessionStatus.PAUSED,
        }
        return [
            s for s in self.list_all(owner_id)
            if s.status in active_statuses
        ]

    def exists(self, session_id: str) -> bool:
        """Return True if a session file exists for session_id (any owner)."""
        self._validate_id(session_id)
        return self._session_path(session_id).exists()
