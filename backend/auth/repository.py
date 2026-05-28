"""
JSON-backed UserRepository.

Thread-safety: uses a threading.Lock for all reads and writes.
Persistence: atomic write via temp-file rename to prevent partial-write corruption.

INVARIANTS:
  - username lookups are case-insensitive (stored and queried lowercased)
  - email lookups are case-insensitive
  - user_id is the primary key; username and email are unique secondary keys
  - the JSON file is the sole persistent store; in-memory dict is a write-through cache
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Optional

from backend.auth.models import User


class DuplicateUsernameError(Exception):
    pass


class DuplicateEmailError(Exception):
    pass


class UserRepository:
    def __init__(self, file_path: Path) -> None:
        self._path = Path(file_path)
        self._lock = threading.Lock()
        self._users: dict[str, User] = {}  # user_id → User
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def save(self, user: User) -> None:
        with self._lock:
            if self._find_by_username_unsafe(user.username) is not None:
                raise DuplicateUsernameError(f"Username already taken: {user.username}")
            if self._find_by_email_unsafe(user.email) is not None:
                raise DuplicateEmailError(f"Email already registered: {user.email}")
            self._users[user.user_id] = user
            self._persist()

    def get_by_username(self, username: str) -> Optional[User]:
        with self._lock:
            return self._find_by_username_unsafe(username.strip().lower())

    def get_by_email(self, email: str) -> Optional[User]:
        with self._lock:
            return self._find_by_email_unsafe(email.strip().lower())

    def get_by_id(self, user_id: str) -> Optional[User]:
        with self._lock:
            return self._users.get(user_id)

    def update(self, user: User) -> None:
        """Replace an existing user record. Raises KeyError if user_id not found."""
        with self._lock:
            if user.user_id not in self._users:
                raise KeyError(f"User not found: {user.user_id}")
            self._users[user.user_id] = user
            self._persist()

    def list_all(self) -> list[User]:
        with self._lock:
            return list(self._users.values())

    def count(self) -> int:
        with self._lock:
            return len(self._users)

    # ------------------------------------------------------------------
    # Internal helpers (must be called with lock held)
    # ------------------------------------------------------------------

    def _find_by_username_unsafe(self, username: str) -> Optional[User]:
        for u in self._users.values():
            if u.username == username:
                return u
        return None

    def _find_by_email_unsafe(self, email: str) -> Optional[User]:
        for u in self._users.values():
            if u.email == email:
                return u
        return None

    def _load(self) -> None:
        if not self._path.exists():
            self._users = {}
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._users = {entry["user_id"]: User.from_dict(entry) for entry in data}
        except (json.JSONDecodeError, KeyError):
            self._users = {}

    def _persist(self) -> None:
        payload = json.dumps(
            [u.to_dict() for u in self._users.values()],
            indent=2,
        )
        # Atomic write: write to temp file in same directory, then rename
        dir_ = self._path.parent
        fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp_path, self._path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
