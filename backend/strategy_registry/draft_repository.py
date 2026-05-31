"""
DraftRepository — Phase 2N.9.

Filesystem-backed persistence for StrategyDraft artifacts.

Storage layout:
    {base_path}/strategy_drafts/{draft_id}.json     — active drafts
    {base_path}/strategy_drafts/archive/{draft_id}.json — archived drafts

Serialization uses StrategyDraft.model_dump_json() for deterministic UTF-8 output.
Identical draft inputs always produce identical file contents.

This module handles persistence only. Validation is delegated to StrategyDraft.
"""
from __future__ import annotations

from pathlib import Path

from backend.strategy_registry.drafts import StrategyDraft


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------

class DraftNotFoundError(Exception):
    """Raised when a draft does not exist at the expected path."""


class DraftAlreadyExistsError(Exception):
    """Raised when attempting to save a draft whose draft_id already exists."""


class DraftPersistenceError(Exception):
    """Raised on unexpected I/O or deserialization failures."""


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class DraftRepository:
    """
    Filesystem-backed repository for StrategyDraft artifacts.

    All public methods raise typed errors instead of returning sentinels.
    Active and archived drafts occupy separate subdirectories so listing
    only returns active drafts while archives remain explicitly retrievable.
    """

    def __init__(self, base_path: Path) -> None:
        self._active_dir: Path = base_path / "strategy_drafts"
        self._archive_dir: Path = base_path / "strategy_drafts" / "archive"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        self._active_dir.mkdir(parents=True, exist_ok=True)
        self._archive_dir.mkdir(parents=True, exist_ok=True)

    def _active_path(self, draft_id: str) -> Path:
        return self._active_dir / f"{draft_id}.json"

    def _archive_path(self, draft_id: str) -> Path:
        return self._archive_dir / f"{draft_id}.json"

    @staticmethod
    def _serialize(draft: StrategyDraft) -> str:
        return draft.model_dump_json() + "\n"

    @staticmethod
    def _deserialize(content: str, path: Path) -> StrategyDraft:
        try:
            return StrategyDraft.model_validate_json(content)
        except Exception as exc:
            raise DraftPersistenceError(
                f"failed to deserialize draft from '{path}': {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, draft: StrategyDraft) -> None:
        """
        Persist a new draft.

        Raises DraftAlreadyExistsError if draft_id already has an active file.
        Raises DraftPersistenceError on I/O failure.
        """
        self._ensure_dirs()
        path = self._active_path(draft.draft_id)
        if path.exists():
            raise DraftAlreadyExistsError(
                f"draft '{draft.draft_id}' already exists; use update() to overwrite"
            )
        try:
            path.write_text(self._serialize(draft), encoding="utf-8")
        except OSError as exc:
            raise DraftPersistenceError(
                f"failed to save draft '{draft.draft_id}': {exc}"
            ) from exc

    def load(self, draft_id: str, owner_id: str | None = None) -> StrategyDraft:
        """
        Load an active draft by id.

        If owner_id is provided, raises DraftNotFoundError (same error as not-found)
        when the draft's user_id does not match owner_id — information hiding.

        Raises DraftNotFoundError if no active file exists for draft_id.
        Raises DraftPersistenceError on I/O or parse failure.

        Note: callers that receive draft_id from URL path params must validate
        UUID format before calling (see routes/drafts.py).
        """
        path = self._active_path(draft_id)
        if not path.exists():
            raise DraftNotFoundError(f"draft '{draft_id}' not found")
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DraftPersistenceError(
                f"failed to read draft '{draft_id}': {exc}"
            ) from exc
        draft = self._deserialize(content, path)
        if owner_id is not None and draft.user_id != owner_id:
            raise DraftNotFoundError(f"draft '{draft_id}' not found")
        return draft

    def load_archived(self, draft_id: str) -> StrategyDraft:
        """
        Load an archived draft.

        Raises DraftNotFoundError if draft_id is not in the archive.
        """
        path = self._archive_path(draft_id)
        if not path.exists():
            raise DraftNotFoundError(f"archived draft '{draft_id}' not found")
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DraftPersistenceError(
                f"failed to read archived draft '{draft_id}': {exc}"
            ) from exc
        return self._deserialize(content, path)

    def exists(self, draft_id: str) -> bool:
        """Return True if draft_id has an active (non-archived) file."""
        return self._active_path(draft_id).exists()

    def list_all(self, user_id: str | None = None) -> list[StrategyDraft]:
        """
        Return all active drafts sorted by draft_id for determinism.

        If user_id is provided, only drafts whose user_id matches are returned.
        Legacy drafts (user_id=None) are NOT returned when user_id is provided.

        Returns an empty list if the storage directory does not yet exist.
        Raises DraftPersistenceError if any file cannot be read or parsed.
        """
        if not self._active_dir.exists():
            return []
        paths = sorted(
            p for p in self._active_dir.iterdir()
            if p.is_file() and p.suffix == ".json"
        )
        drafts: list[StrategyDraft] = []
        for path in paths:
            try:
                content = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise DraftPersistenceError(
                    f"failed to read draft file '{path.name}': {exc}"
                ) from exc
            draft = self._deserialize(content, path)
            if user_id is not None and draft.user_id != user_id:
                continue
            drafts.append(draft)
        return drafts

    def update(self, draft: StrategyDraft, owner_id: str | None = None) -> None:
        """
        Overwrite an existing draft.

        If owner_id is provided, raises DraftNotFoundError when the stored
        draft's user_id does not match owner_id — information hiding.

        Raises DraftNotFoundError if draft_id has no active file.
        Use save() when creating a new draft; use update() when replacing.
        """
        self.load(draft.draft_id, owner_id=owner_id)  # ownership check
        try:
            self._active_path(draft.draft_id).write_text(
                self._serialize(draft), encoding="utf-8"
            )
        except OSError as exc:
            raise DraftPersistenceError(
                f"failed to update draft '{draft.draft_id}': {exc}"
            ) from exc

    def archive(self, draft_id: str, owner_id: str | None = None) -> None:
        """
        Move an active draft to the archive directory.

        If owner_id is provided, raises DraftNotFoundError when the stored
        draft's user_id does not match owner_id — information hiding.

        The draft is preserved in archive/ and removed from active listing.
        It remains retrievable via load_archived(draft_id).

        Raises DraftNotFoundError if draft_id has no active file.
        """
        self._ensure_dirs()
        self.load(draft_id, owner_id=owner_id)  # ownership check
        try:
            self._active_path(draft_id).rename(self._archive_path(draft_id))
        except OSError as exc:
            raise DraftPersistenceError(
                f"failed to archive draft '{draft_id}': {exc}"
            ) from exc

    def delete(self, draft_id: str, owner_id: str | None = None) -> None:
        """
        Hard-delete an active draft.

        If owner_id is provided, raises DraftNotFoundError when the stored
        draft's user_id does not match owner_id — information hiding.

        Raises DraftNotFoundError if draft_id has no active file.
        """
        self.load(draft_id, owner_id=owner_id)  # ownership check
        try:
            self._active_path(draft_id).unlink()
        except OSError as exc:
            raise DraftPersistenceError(
                f"failed to delete draft '{draft_id}': {exc}"
            ) from exc
