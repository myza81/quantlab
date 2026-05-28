"""
JSON-backed CredentialRepository.

Thread-safety: all reads and writes serialized via threading.Lock.
Persistence: atomic write via temp-file rename to prevent partial-write corruption.

INVARIANTS:
  - only `encrypted_secret` (ciphertext) is persisted — never plaintext
  - credential_id is the primary key
  - lookups by user_id return only that user's records
  - a deleted credential is removed entirely from the file
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Optional

from backend.vault.models import ProviderCredential


class CredentialRepository:
    def __init__(self, file_path: Path) -> None:
        self._path = Path(file_path)
        self._lock = threading.Lock()
        self._store: dict[str, ProviderCredential] = {}  # credential_id → record
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def save(self, credential: ProviderCredential) -> None:
        """Insert a new credential record. Raises ValueError on duplicate credential_id."""
        with self._lock:
            if credential.credential_id in self._store:
                raise ValueError(f"Credential already exists: {credential.credential_id}")
            self._store[credential.credential_id] = credential
            self._persist()

    def update(self, credential: ProviderCredential) -> None:
        """Replace an existing credential record. Raises ValueError if not found."""
        with self._lock:
            if credential.credential_id not in self._store:
                raise ValueError(f"Credential not found: {credential.credential_id}")
            self._store[credential.credential_id] = credential
            self._persist()

    def delete(self, credential_id: str) -> bool:
        """Remove a credential record. Returns True if deleted, False if not found."""
        with self._lock:
            if credential_id not in self._store:
                return False
            del self._store[credential_id]
            self._persist()
            return True

    def get_by_id(self, credential_id: str) -> Optional[ProviderCredential]:
        with self._lock:
            return self._store.get(credential_id)

    def list_by_user(self, user_id: str) -> list[ProviderCredential]:
        """Return all credentials owned by *user_id*, ordered by created_at."""
        with self._lock:
            owned = [c for c in self._store.values() if c.user_id == user_id]
            return sorted(owned, key=lambda c: c.created_at)

    def count(self) -> int:
        with self._lock:
            return len(self._store)

    # ------------------------------------------------------------------
    # Internal helpers (must be called with lock held)
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            self._store = {}
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._store = {
                entry["credential_id"]: ProviderCredential.from_dict(entry)
                for entry in data
            }
        except (json.JSONDecodeError, KeyError):
            self._store = {}

    def _persist(self) -> None:
        payload = json.dumps(
            [c.to_dict() for c in self._store.values()],
            indent=2,
        )
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
