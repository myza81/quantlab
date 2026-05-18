"""
Tests for Phase 2N.9 — DraftRepository.

Covers:
  - save / load / exists round-trip
  - DraftAlreadyExistsError on duplicate save
  - DraftNotFoundError on missing load / update / archive / delete
  - DraftPersistenceError on malformed file
  - update overwrites correctly
  - list_all returns sorted active drafts only
  - archive moves to archive dir; removed from active listing
  - load_archived retrieves from archive
  - delete removes file entirely
  - deterministic serialization: identical draft → identical file content
  - storage directory is created on first write
  - archived drafts are excluded from list_all
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.strategy_registry.draft_repository import (
    DraftAlreadyExistsError,
    DraftNotFoundError,
    DraftPersistenceError,
    DraftRepository,
)
from backend.strategy_registry.drafts import StrategyDraft
from backend.tools import StrategyToolSet, ToolConfiguration

_UTC = timezone.utc
_NOW = datetime(2026, 5, 18, 12, 0, 0, tzinfo=_UTC)
_LATER = datetime(2026, 5, 18, 13, 0, 0, tzinfo=_UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sma(instance_id: str, period: int) -> ToolConfiguration:
    return ToolConfiguration(
        instance_id=instance_id,
        tool_id="sma",
        parameters={"period": period},
    )


def _toolset(toolset_id: str = "ts1") -> StrategyToolSet:
    return StrategyToolSet(toolset_id=toolset_id, tools=(_sma("sma_fast", 20),))


def _draft(
    draft_id: str = "alpha",
    display_name: str = "Alpha Draft",
    **kw: object,
) -> StrategyDraft:
    return StrategyDraft(
        draft_id=draft_id,
        display_name=display_name,
        toolset=_toolset(),
        created_at=_NOW,
        updated_at=_NOW,
        **kw,
    )


def _repo(tmp_path: Path) -> DraftRepository:
    return DraftRepository(tmp_path)


# ---------------------------------------------------------------------------
# TestDraftRepositorySave
# ---------------------------------------------------------------------------

class TestDraftRepositorySave:
    def test_save_creates_file(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        draft = _draft()
        repo.save(draft)
        assert (tmp_path / "strategy_drafts" / "alpha.json").exists()

    def test_save_creates_storage_dir(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        assert not (tmp_path / "strategy_drafts").exists()
        repo.save(_draft())
        assert (tmp_path / "strategy_drafts").exists()

    def test_save_duplicate_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft())
        with pytest.raises(DraftAlreadyExistsError, match="already exists"):
            repo.save(_draft())

    def test_save_different_ids_both_persist(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        repo.save(_draft("beta"))
        assert (tmp_path / "strategy_drafts" / "alpha.json").exists()
        assert (tmp_path / "strategy_drafts" / "beta.json").exists()

    def test_file_is_utf8(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", display_name="Ünïcödé Draft"))
        content = (tmp_path / "strategy_drafts" / "alpha.json").read_bytes()
        assert content.decode("utf-8")  # must be valid UTF-8


# ---------------------------------------------------------------------------
# TestDraftRepositoryLoad
# ---------------------------------------------------------------------------

class TestDraftRepositoryLoad:
    def test_load_roundtrip(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        original = _draft("alpha", display_name="My Draft")
        repo.save(original)
        loaded = repo.load("alpha")
        assert loaded.draft_id == "alpha"
        assert loaded.display_name == "My Draft"

    def test_load_preserves_toolset(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft())
        loaded = repo.load("alpha")
        assert len(loaded.toolset) == 1
        assert loaded.toolset.tools[0].instance_id == "sma_fast"

    def test_load_preserves_timestamps(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft())
        loaded = repo.load("alpha")
        assert loaded.created_at.tzinfo == _UTC
        assert loaded.updated_at.tzinfo == _UTC

    def test_load_missing_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        with pytest.raises(DraftNotFoundError, match="not found"):
            repo.load("ghost")

    def test_load_malformed_json_raises_persistence_error(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo._ensure_dirs()
        (tmp_path / "strategy_drafts" / "bad.json").write_text("{bad json", encoding="utf-8")
        with pytest.raises(DraftPersistenceError):
            repo.load("bad")


# ---------------------------------------------------------------------------
# TestDraftRepositoryExists
# ---------------------------------------------------------------------------

class TestDraftRepositoryExists:
    def test_exists_after_save(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        assert repo.exists("alpha") is True

    def test_exists_missing_returns_false(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        assert repo.exists("ghost") is False

    def test_exists_false_before_any_save(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        assert repo.exists("alpha") is False

    def test_exists_false_after_delete(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        repo.delete("alpha")
        assert repo.exists("alpha") is False

    def test_exists_false_after_archive(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        repo.archive("alpha")
        assert repo.exists("alpha") is False


# ---------------------------------------------------------------------------
# TestDraftRepositoryListAll
# ---------------------------------------------------------------------------

class TestDraftRepositoryListAll:
    def test_empty_list_when_no_storage_dir(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        assert repo.list_all() == []

    def test_empty_list_when_dir_exists_but_empty(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo._ensure_dirs()
        assert repo.list_all() == []

    def test_list_returns_saved_drafts(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        result = repo.list_all()
        assert len(result) == 1
        assert result[0].draft_id == "alpha"

    def test_list_sorted_by_draft_id(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("zeta"))
        repo.save(_draft("alpha"))
        repo.save(_draft("mu"))
        ids = [d.draft_id for d in repo.list_all()]
        assert ids == ["alpha", "mu", "zeta"]

    def test_list_excludes_archived_drafts(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        repo.save(_draft("beta"))
        repo.archive("alpha")
        ids = [d.draft_id for d in repo.list_all()]
        assert ids == ["beta"]
        assert "alpha" not in ids


# ---------------------------------------------------------------------------
# TestDraftRepositoryUpdate
# ---------------------------------------------------------------------------

class TestDraftRepositoryUpdate:
    def test_update_overwrites(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", display_name="Original"))
        updated = StrategyDraft(
            draft_id="alpha",
            display_name="Updated",
            toolset=_toolset(),
            created_at=_NOW,
            updated_at=_LATER,
        )
        repo.update(updated)
        loaded = repo.load("alpha")
        assert loaded.display_name == "Updated"

    def test_update_missing_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        with pytest.raises(DraftNotFoundError):
            repo.update(_draft("ghost"))

    def test_update_does_not_create_new_file(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        with pytest.raises(DraftNotFoundError):
            repo.update(_draft("new_draft"))
        assert not (tmp_path / "strategy_drafts" / "new_draft.json").exists()


# ---------------------------------------------------------------------------
# TestDraftRepositoryArchive
# ---------------------------------------------------------------------------

class TestDraftRepositoryArchive:
    def test_archive_moves_to_archive_dir(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        repo.archive("alpha")
        assert (tmp_path / "strategy_drafts" / "archive" / "alpha.json").exists()
        assert not (tmp_path / "strategy_drafts" / "alpha.json").exists()

    def test_archive_missing_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        with pytest.raises(DraftNotFoundError, match="not found"):
            repo.archive("ghost")

    def test_load_archived_retrieves_from_archive(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha", display_name="Archived Draft"))
        repo.archive("alpha")
        loaded = repo.load_archived("alpha")
        assert loaded.draft_id == "alpha"
        assert loaded.display_name == "Archived Draft"

    def test_load_archived_missing_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        with pytest.raises(DraftNotFoundError):
            repo.load_archived("ghost")


# ---------------------------------------------------------------------------
# TestDraftRepositoryDelete
# ---------------------------------------------------------------------------

class TestDraftRepositoryDelete:
    def test_delete_removes_file(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        repo.delete("alpha")
        assert not (tmp_path / "strategy_drafts" / "alpha.json").exists()

    def test_delete_missing_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        with pytest.raises(DraftNotFoundError, match="not found"):
            repo.delete("ghost")

    def test_load_after_delete_raises(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        repo.delete("alpha")
        with pytest.raises(DraftNotFoundError):
            repo.load("alpha")


# ---------------------------------------------------------------------------
# TestSerializationDeterminism
# ---------------------------------------------------------------------------

class TestSerializationDeterminism:
    def test_same_draft_same_file_content(self, tmp_path: Path) -> None:
        repo1 = DraftRepository(tmp_path / "r1")
        repo2 = DraftRepository(tmp_path / "r2")
        draft = _draft("alpha")
        repo1.save(draft)
        repo2.save(draft)
        content1 = (tmp_path / "r1" / "strategy_drafts" / "alpha.json").read_text()
        content2 = (tmp_path / "r2" / "strategy_drafts" / "alpha.json").read_text()
        assert content1 == content2

    def test_repeated_saves_of_same_draft_produce_same_content(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        draft = _draft("alpha")
        repo.save(draft)
        first_content = (tmp_path / "strategy_drafts" / "alpha.json").read_text()
        repo.update(draft)
        second_content = (tmp_path / "strategy_drafts" / "alpha.json").read_text()
        assert first_content == second_content

    def test_file_ends_with_newline(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        repo.save(_draft("alpha"))
        content = (tmp_path / "strategy_drafts" / "alpha.json").read_text(encoding="utf-8")
        assert content.endswith("\n")
