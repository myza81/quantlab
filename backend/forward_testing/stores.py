"""
ForwardTestSignalStore and ForwardTestBarStore — Phase 4C.1.

JSON-backed per-session stores for signal and bar records.

Storage layout (relative to base_path):
    signals/{session_id}.json    — JSON array of ForwardTestSignal records
    bars/{session_id}.json       — JSON array of ForwardTestBar records

Idempotency:
    ForwardTestSignalStore: deduplication key = (session_id, bar_timestamp, signal_direction)
    ForwardTestBarStore:    deduplication key = (session_id, bar_timestamp)

    Duplicate appends are silently ignored (no error, no duplicate record).

Cross-user isolation:
    These stores contain session_id-scoped files.  Ownership enforcement
    is the responsibility of the service layer (which first checks session
    ownership via ForwardTestRepository before reading/writing stores).
    The stores do not enforce ownership themselves.

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
import os
from datetime import datetime
from pathlib import Path

from backend.core.request_validation import validate_uuid_id
from backend.forward_testing.exceptions import ForwardTestPersistenceError
from backend.forward_testing.models import ForwardTestBar, ForwardTestSignal

logger = logging.getLogger(__name__)


def _atomic_write(path: Path, content: str) -> None:
    """
    Write content to path via temp-file + os.replace() (atomic on POSIX).

    Crash between write and replace leaves a harmless .tmp file that is
    ignored on next read. The target file is never partially written.
    """
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# ForwardTestSignalStore
# ---------------------------------------------------------------------------

class ForwardTestSignalStore:
    """
    Append-only store for ForwardTestSignal records.

    Each session's signals are stored in a single JSON file (array of objects).
    Signals are appended; existing records are never modified or deleted.
    """

    def __init__(self, base_path: Path) -> None:
        self._signals_dir: Path = base_path / "signals"

    def _ensure_dirs(self) -> None:
        self._signals_dir.mkdir(parents=True, exist_ok=True)

    def _signal_path(self, session_id: str) -> Path:
        return self._signals_dir / f"{session_id}.json"

    def _validate_session_id(self, session_id: str) -> None:
        try:
            validate_uuid_id(session_id, "session_id")
        except ValueError as exc:
            raise ForwardTestPersistenceError(str(exc)) from exc

    def _load_raw(self, session_id: str) -> list[dict]:
        path = self._signal_path(session_id)
        if not path.exists():
            return []
        try:
            content = path.read_text(encoding="utf-8")
            return json.loads(content)
        except (OSError, json.JSONDecodeError) as exc:
            raise ForwardTestPersistenceError(
                f"failed to read signal file for session '{session_id}': {exc}"
            ) from exc

    def _save_raw(self, session_id: str, records: list[dict]) -> None:
        self._ensure_dirs()
        path = self._signal_path(session_id)
        try:
            _atomic_write(path, json.dumps(records, ensure_ascii=False))
        except OSError as exc:
            raise ForwardTestPersistenceError(
                f"failed to write signal file for session '{session_id}': {exc}"
            ) from exc

    def append_signal(self, signal: ForwardTestSignal) -> bool:
        """
        Append a signal record for its session.

        Idempotent: if a record with the same (session_id, bar_timestamp,
        signal_direction) already exists, this call is a no-op.

        Returns:
            True  — signal was appended (new record)
            False — duplicate detected; no write performed
        """
        self._validate_session_id(signal.session_id)
        records = self._load_raw(signal.session_id)

        bar_ts = signal.bar_timestamp
        for existing in records:
            try:
                existing_ts = datetime.fromisoformat(existing.get("bar_timestamp", ""))
            except (ValueError, TypeError):
                continue
            if (
                existing_ts == bar_ts
                and existing.get("signal_direction") == signal.signal_direction
            ):
                return False  # duplicate

        records.append(json.loads(signal.model_dump_json()))
        self._save_raw(signal.session_id, records)
        return True

    def list_signals(self, session_id: str) -> list[ForwardTestSignal]:
        """
        Return all signals for a session, ordered by bar_timestamp ascending.

        Returns empty list when no signal file exists for the session.
        Raises ForwardTestPersistenceError on I/O or parse failure.
        """
        self._validate_session_id(session_id)
        raw = self._load_raw(session_id)
        signals: list[ForwardTestSignal] = []
        for item in raw:
            try:
                signals.append(ForwardTestSignal.model_validate(item))
            except Exception as exc:
                raise ForwardTestPersistenceError(
                    f"failed to deserialize signal record in session '{session_id}': {exc}"
                ) from exc
        signals.sort(key=lambda s: s.bar_timestamp)
        return signals

    def count_signals(self, session_id: str) -> int:
        """Return the total number of signal records for a session."""
        self._validate_session_id(session_id)
        return len(self._load_raw(session_id))


# ---------------------------------------------------------------------------
# ForwardTestBarStore
# ---------------------------------------------------------------------------

class ForwardTestBarStore:
    """
    Append-only store for ForwardTestBar records.

    Each session's bars are stored in a single JSON file (array of objects).
    Bars are appended in processing order; existing records are never modified.

    Supports:
      - Duplicate detection by (session_id, bar_timestamp)
      - Last-processed-bar timestamp query
      - Warmup-bar / signal-eligible-bar distinction
    """

    def __init__(self, base_path: Path) -> None:
        self._bars_dir: Path = base_path / "bars"

    def _ensure_dirs(self) -> None:
        self._bars_dir.mkdir(parents=True, exist_ok=True)

    def _bar_path(self, session_id: str) -> Path:
        return self._bars_dir / f"{session_id}.json"

    def _validate_session_id(self, session_id: str) -> None:
        try:
            validate_uuid_id(session_id, "session_id")
        except ValueError as exc:
            raise ForwardTestPersistenceError(str(exc)) from exc

    def _load_raw(self, session_id: str) -> list[dict]:
        path = self._bar_path(session_id)
        if not path.exists():
            return []
        try:
            content = path.read_text(encoding="utf-8")
            return json.loads(content)
        except (OSError, json.JSONDecodeError) as exc:
            raise ForwardTestPersistenceError(
                f"failed to read bar file for session '{session_id}': {exc}"
            ) from exc

    def _save_raw(self, session_id: str, records: list[dict]) -> None:
        self._ensure_dirs()
        path = self._bar_path(session_id)
        try:
            _atomic_write(path, json.dumps(records, ensure_ascii=False))
        except OSError as exc:
            raise ForwardTestPersistenceError(
                f"failed to write bar file for session '{session_id}': {exc}"
            ) from exc

    def append_bar(self, bar: ForwardTestBar) -> bool:
        """
        Append a bar record for its session.

        Idempotent: if a record with the same (session_id, bar_timestamp)
        already exists, this call is a no-op.

        Returns:
            True  — bar was appended (new record)
            False — duplicate detected by bar_timestamp; no write performed
        """
        self._validate_session_id(bar.session_id)
        records = self._load_raw(bar.session_id)

        bar_ts = bar.bar_timestamp
        for existing in records:
            try:
                existing_ts = datetime.fromisoformat(existing.get("bar_timestamp", ""))
            except (ValueError, TypeError):
                continue
            if existing_ts == bar_ts:
                return False  # duplicate

        records.append(json.loads(bar.model_dump_json()))
        self._save_raw(bar.session_id, records)
        return True

    def list_bars(self, session_id: str) -> list[ForwardTestBar]:
        """
        Return all bars for a session, ordered by bar_index ascending.

        Returns empty list when no bar file exists for the session.
        Raises ForwardTestPersistenceError on I/O or parse failure.
        """
        self._validate_session_id(session_id)
        raw = self._load_raw(session_id)
        bars: list[ForwardTestBar] = []
        for item in raw:
            try:
                bars.append(ForwardTestBar.model_validate(item))
            except Exception as exc:
                raise ForwardTestPersistenceError(
                    f"failed to deserialize bar record in session '{session_id}': {exc}"
                ) from exc
        bars.sort(key=lambda b: b.bar_index)
        return bars

    def get_last_bar_timestamp(self, session_id: str) -> datetime | None:
        """
        Return the timestamp of the most recently processed bar, or None.

        Considers all bars (warmup and signal-eligible).  This is the cursor
        used to detect unseen bars on the next poll cycle.
        """
        self._validate_session_id(session_id)
        raw = self._load_raw(session_id)
        if not raw:
            return None
        bars = self.list_bars(session_id)
        return max(b.bar_timestamp for b in bars)

    def get_last_signal_eligible_bar_timestamp(
        self, session_id: str
    ) -> datetime | None:
        """
        Return the timestamp of the most recently processed signal-eligible bar.

        Returns None when no signal-eligible bars have been processed yet
        (session still in warmup or no bars at all).
        """
        self._validate_session_id(session_id)
        bars = self.list_bars(session_id)
        eligible = [b for b in bars if not b.is_warmup_bar]
        if not eligible:
            return None
        return max(b.bar_timestamp for b in eligible)

    def count_bars(self, session_id: str) -> int:
        """Return the total number of bar records for a session."""
        self._validate_session_id(session_id)
        return len(self._load_raw(session_id))

    def count_warmup_bars(self, session_id: str) -> int:
        """Return the number of warmup bars stored for a session."""
        self._validate_session_id(session_id)
        return sum(1 for r in self._load_raw(session_id) if r.get("is_warmup_bar"))

    def count_signal_eligible_bars(self, session_id: str) -> int:
        """Return the number of signal-eligible (non-warmup) bars for a session."""
        self._validate_session_id(session_id)
        return sum(
            1 for r in self._load_raw(session_id) if not r.get("is_warmup_bar")
        )
