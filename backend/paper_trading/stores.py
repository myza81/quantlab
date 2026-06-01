"""
PaperAccountStore and AccountStateSnapshotStore — Phase 4E.1.

JSON-backed per-session stores for paper account and equity curve snapshot records.

Storage layout (relative to base_path):
    accounts/{session_id}.json   — single PaperAccount record per session
    equity/{session_id}.json     — JSON array of AccountStateSnapshot records

PaperAccountStore:
    One account per session (1:1 enforced by save()).
    Primary lookup: session_id.
    Secondary lookup: account_id (linear scan; use sparingly).
    Ownership enforcement is the responsibility of the service layer.

AccountStateSnapshotStore:
    Append-only; records are never modified after creation.
    Deduplication key: (session_id, bar_timestamp).
    Duplicate appends are silently ignored.
    Records returned in ascending bar_timestamp order.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.backtesting
    backend.api
    backend.data_providers
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from backend.core.request_validation import validate_uuid_id
from backend.paper_trading.exceptions import (
    PaperAccountAlreadyExistsError,
    PaperAccountNotFoundError,
    PaperTradingPersistenceError,
)
from backend.paper_trading.models import AccountStateSnapshot, PaperAccount

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PaperAccountStore
# ---------------------------------------------------------------------------

class PaperAccountStore:
    """
    Filesystem-backed store for PaperAccount records.

    One account per session (1:1 binding).  The account file is keyed by
    session_id — the primary access pattern is load_by_session_id().

    The account record is mutable (updated after fills and bar marks in
    Phase 4E.2+).  update() overwrites the existing file.

    session_id is validated as a UUID before any path construction to
    prevent path traversal.
    """

    def __init__(self, base_path: Path) -> None:
        self._accounts_dir: Path = base_path / "accounts"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        self._accounts_dir.mkdir(parents=True, exist_ok=True)

    def _account_path(self, session_id: str) -> Path:
        return self._accounts_dir / f"{session_id}.json"

    @staticmethod
    def _serialize(account: PaperAccount) -> str:
        return account.model_dump_json() + "\n"

    @staticmethod
    def _deserialize(content: str, path: Path) -> PaperAccount:
        try:
            return PaperAccount.model_validate_json(content)
        except Exception as exc:
            raise PaperTradingPersistenceError(
                f"failed to deserialize account from '{path.name}': {exc}"
            ) from exc

    def _validate_session_id(self, session_id: str) -> None:
        try:
            validate_uuid_id(session_id, "session_id")
        except ValueError as exc:
            raise PaperAccountNotFoundError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, account: PaperAccount) -> None:
        """
        Persist a new PaperAccount record (keyed by session_id).

        Raises PaperAccountAlreadyExistsError if an account already exists
        for this session_id (enforces 1:1 session binding).
        Raises PaperTradingPersistenceError on I/O failure.
        """
        self._validate_session_id(account.session_id)
        self._ensure_dirs()
        path = self._account_path(account.session_id)
        if path.exists():
            raise PaperAccountAlreadyExistsError(
                f"account already exists for session '{account.session_id}'; "
                "use update() to overwrite"
            )
        try:
            path.write_text(self._serialize(account), encoding="utf-8")
        except OSError as exc:
            raise PaperTradingPersistenceError(
                f"failed to save account for session '{account.session_id}': {exc}"
            ) from exc

    def load_by_session_id(self, session_id: str) -> PaperAccount:
        """
        Load the PaperAccount for a given session_id.

        Raises PaperAccountNotFoundError when:
          - session_id is not a valid UUID
          - no account file exists for this session_id

        Raises PaperTradingPersistenceError on I/O or parse failure.
        """
        self._validate_session_id(session_id)
        path = self._account_path(session_id)
        if not path.exists():
            raise PaperAccountNotFoundError(
                f"no account found for session '{session_id}'"
            )
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PaperTradingPersistenceError(
                f"failed to read account for session '{session_id}': {exc}"
            ) from exc
        return self._deserialize(content, path)

    def update(self, account: PaperAccount) -> None:
        """
        Overwrite the existing PaperAccount record for its session_id.

        Used by the service layer (Phase 4E.3+) after fill processing and
        bar mark-to-market updates.

        Raises PaperAccountNotFoundError if no account exists for this session.
        Raises PaperTradingPersistenceError on I/O failure.
        """
        self._validate_session_id(account.session_id)
        path = self._account_path(account.session_id)
        if not path.exists():
            raise PaperAccountNotFoundError(
                f"no account found for session '{account.session_id}'; "
                "call save() first"
            )
        try:
            path.write_text(self._serialize(account), encoding="utf-8")
        except OSError as exc:
            raise PaperTradingPersistenceError(
                f"failed to update account for session '{account.session_id}': {exc}"
            ) from exc

    def exists_for_session(self, session_id: str) -> bool:
        """Return True if an account file exists for session_id."""
        self._validate_session_id(session_id)
        return self._account_path(session_id).exists()

    def load_by_account_id(self, account_id: str, session_id: str) -> PaperAccount:
        """
        Load a PaperAccount by account_id, verified against session_id.

        account_id is validated, then the account is loaded by session_id and
        verified to match.  Use sparingly — the primary access pattern is
        load_by_session_id().

        Raises PaperAccountNotFoundError when:
          - Either ID is not a valid UUID
          - No account file exists for session_id
          - The loaded account's account_id does not match the requested account_id

        Raises PaperTradingPersistenceError on I/O or parse failure.
        """
        try:
            validate_uuid_id(account_id, "account_id")
        except ValueError as exc:
            raise PaperAccountNotFoundError(str(exc)) from exc
        account = self.load_by_session_id(session_id)
        if account.account_id != account_id:
            raise PaperAccountNotFoundError(
                f"account_id mismatch for session '{session_id}'"
            )
        return account


# ---------------------------------------------------------------------------
# AccountStateSnapshotStore
# ---------------------------------------------------------------------------

class AccountStateSnapshotStore:
    """
    Append-only store for AccountStateSnapshot records (equity curve).

    Each session's snapshots are stored in a single JSON file (array of
    objects).  Records are appended; existing records are never modified
    or deleted.

    Deduplication key: (session_id, bar_timestamp).
    Duplicate appends are silently ignored.

    Records are returned in ascending bar_timestamp order.

    session_id is validated as a UUID before any path construction.
    """

    def __init__(self, base_path: Path) -> None:
        self._equity_dir: Path = base_path / "equity"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        self._equity_dir.mkdir(parents=True, exist_ok=True)

    def _snapshot_path(self, session_id: str) -> Path:
        return self._equity_dir / f"{session_id}.json"

    def _validate_session_id(self, session_id: str) -> None:
        try:
            validate_uuid_id(session_id, "session_id")
        except ValueError as exc:
            raise PaperTradingPersistenceError(str(exc)) from exc

    def _load_raw(self, session_id: str) -> list[dict]:
        path = self._snapshot_path(session_id)
        if not path.exists():
            return []
        try:
            content = path.read_text(encoding="utf-8")
            return json.loads(content)
        except (OSError, json.JSONDecodeError) as exc:
            raise PaperTradingPersistenceError(
                f"failed to read equity curve for session '{session_id}': {exc}"
            ) from exc

    def _save_raw(self, session_id: str, records: list[dict]) -> None:
        self._ensure_dirs()
        path = self._snapshot_path(session_id)
        try:
            path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            raise PaperTradingPersistenceError(
                f"failed to write equity curve for session '{session_id}': {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, snapshot: AccountStateSnapshot) -> bool:
        """
        Append a snapshot record for its session.

        Idempotent: if a record with the same (session_id, bar_timestamp)
        already exists, this call is a no-op.

        Returns:
            True  — snapshot was appended (new record)
            False — duplicate detected; no write performed
        """
        self._validate_session_id(snapshot.session_id)
        records = self._load_raw(snapshot.session_id)

        bar_ts = snapshot.bar_timestamp
        for existing in records:
            try:
                existing_ts = datetime.fromisoformat(existing.get("bar_timestamp", ""))
            except (ValueError, TypeError):
                continue
            if existing_ts == bar_ts:
                return False  # duplicate

        records.append(json.loads(snapshot.model_dump_json()))
        self._save_raw(snapshot.session_id, records)
        return True

    def list_snapshots(self, session_id: str) -> list[AccountStateSnapshot]:
        """
        Return all snapshots for a session, ordered by bar_timestamp ascending.

        Returns empty list when no snapshot file exists for the session.
        Raises PaperTradingPersistenceError on I/O or parse failure.
        """
        self._validate_session_id(session_id)
        raw = self._load_raw(session_id)
        snapshots: list[AccountStateSnapshot] = []
        for item in raw:
            try:
                snapshots.append(AccountStateSnapshot.model_validate(item))
            except Exception as exc:
                raise PaperTradingPersistenceError(
                    f"failed to deserialize snapshot in session '{session_id}': {exc}"
                ) from exc
        snapshots.sort(key=lambda s: s.bar_timestamp)
        return snapshots

    def count(self, session_id: str) -> int:
        """Return the total number of snapshot records for a session."""
        self._validate_session_id(session_id)
        return len(self._load_raw(session_id))
