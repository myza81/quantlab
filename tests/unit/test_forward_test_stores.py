"""
Tests for Phase 4C.1 — ForwardTestSignalStore and ForwardTestBarStore.

Covers:
  - ForwardTestSignalStore: append + list round-trip
  - ForwardTestSignalStore: duplicate idempotency (session_id + bar_timestamp + signal_direction)
  - ForwardTestSignalStore: list returns empty for new session
  - ForwardTestSignalStore: list ordered by bar_timestamp ascending
  - ForwardTestSignalStore: count_signals
  - ForwardTestSignalStore: invalid session_id raises PersistenceError

  - ForwardTestBarStore: append + list round-trip
  - ForwardTestBarStore: duplicate idempotency (session_id + bar_timestamp)
  - ForwardTestBarStore: list returns empty for new session
  - ForwardTestBarStore: list ordered by bar_index ascending
  - ForwardTestBarStore: get_last_bar_timestamp returns None when empty
  - ForwardTestBarStore: get_last_bar_timestamp returns max timestamp
  - ForwardTestBarStore: get_last_signal_eligible_bar_timestamp
  - ForwardTestBarStore: count_bars, count_warmup_bars, count_signal_eligible_bars
  - ForwardTestBarStore: invalid session_id raises PersistenceError
  - Storage directories are created on first write
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.forward_testing.exceptions import ForwardTestPersistenceError
from backend.forward_testing.models import ForwardTestBar, ForwardTestSignal
from backend.forward_testing.stores import ForwardTestBarStore, ForwardTestSignalStore

_UTC = timezone.utc
_T1  = datetime(2026, 5, 29, 9, 0, 0, tzinfo=_UTC)
_T2  = datetime(2026, 5, 29, 10, 0, 0, tzinfo=_UTC)
_T3  = datetime(2026, 5, 29, 11, 0, 0, tzinfo=_UTC)
_T_PROCESS = datetime(2026, 5, 29, 12, 0, 0, tzinfo=_UTC)

_SESSION_ID = str(uuid.uuid4())
_USER_ID    = str(uuid.uuid4())
_DRAFT_HASH = "abc123" * 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _signal(
    bar_timestamp: datetime = _T1,
    signal_direction: str = "entry_long",
    rule_id: str = "entry_rule_1",
    session_id: str = _SESSION_ID,
) -> ForwardTestSignal:
    return ForwardTestSignal(
        signal_id=str(uuid.uuid4()),
        session_id=session_id,
        user_id=_USER_ID,
        bar_timestamp=bar_timestamp,
        signal_timestamp=_T_PROCESS,
        signal_direction=signal_direction,  # type: ignore[arg-type]
        rule_id=rule_id,
        bar_open=100.0,
        bar_high=105.0,
        bar_low=99.0,
        bar_close=103.0,
        bar_volume=1_000_000.0,
        warmup_satisfied=True,
        strategy_snapshot_hash=_DRAFT_HASH,
        symbol="AAPL",
        timeframe="1d",
        created_at=_T_PROCESS,
    )


def _bar(
    bar_timestamp: datetime = _T1,
    bar_index: int = 0,
    is_warmup_bar: bool = True,
    session_id: str = _SESSION_ID,
) -> ForwardTestBar:
    return ForwardTestBar(
        session_id=session_id,
        bar_index=bar_index,
        bar_timestamp=bar_timestamp,
        open=100.0,
        high=105.0,
        low=99.0,
        close=103.0,
        volume=1_000_000.0,
        source_mode="provider",
        provider_name="yahoo",
        is_warmup_bar=is_warmup_bar,
        processed_at=_T_PROCESS,
    )


def _signal_store(tmp_path: Path) -> ForwardTestSignalStore:
    return ForwardTestSignalStore(tmp_path)


def _bar_store(tmp_path: Path) -> ForwardTestBarStore:
    return ForwardTestBarStore(tmp_path)


# ---------------------------------------------------------------------------
# ForwardTestSignalStore — basic operations
# ---------------------------------------------------------------------------

class TestForwardTestSignalStoreAppendAndList:
    def test_list_empty_for_new_session(self, tmp_path: Path) -> None:
        store = _signal_store(tmp_path)
        result = store.list_signals(_SESSION_ID)
        assert result == []

    def test_append_and_list_roundtrip(self, tmp_path: Path) -> None:
        store = _signal_store(tmp_path)
        sig = _signal(bar_timestamp=_T1)
        store.append_signal(sig)
        result = store.list_signals(_SESSION_ID)
        assert len(result) == 1
        assert result[0].signal_id == sig.signal_id
        assert result[0].bar_timestamp == _T1

    def test_multiple_signals_ordered_by_bar_timestamp(self, tmp_path: Path) -> None:
        store = _signal_store(tmp_path)
        sig_t3 = _signal(bar_timestamp=_T3)
        sig_t1 = _signal(bar_timestamp=_T1)
        sig_t2 = _signal(bar_timestamp=_T2)
        store.append_signal(sig_t3)
        store.append_signal(sig_t1)
        store.append_signal(sig_t2)
        result = store.list_signals(_SESSION_ID)
        timestamps = [s.bar_timestamp for s in result]
        assert timestamps == [_T1, _T2, _T3]

    def test_creates_signals_directory(self, tmp_path: Path) -> None:
        store = _signal_store(tmp_path)
        assert not (tmp_path / "signals").exists()
        store.append_signal(_signal())
        assert (tmp_path / "signals").exists()

    def test_count_signals_correct(self, tmp_path: Path) -> None:
        store = _signal_store(tmp_path)
        store.append_signal(_signal(bar_timestamp=_T1))
        store.append_signal(_signal(bar_timestamp=_T2))
        assert store.count_signals(_SESSION_ID) == 2

    def test_count_zero_for_new_session(self, tmp_path: Path) -> None:
        store = _signal_store(tmp_path)
        assert store.count_signals(_SESSION_ID) == 0


# ---------------------------------------------------------------------------
# ForwardTestSignalStore — idempotency
# ---------------------------------------------------------------------------

class TestForwardTestSignalStoreIdempotency:
    def test_duplicate_signal_not_written(self, tmp_path: Path) -> None:
        store = _signal_store(tmp_path)
        sig = _signal(bar_timestamp=_T1, signal_direction="entry_long")
        result1 = store.append_signal(sig)
        result2 = store.append_signal(sig)  # exact same object
        assert result1 is True
        assert result2 is False
        assert store.count_signals(_SESSION_ID) == 1

    def test_same_timestamp_same_direction_is_duplicate(self, tmp_path: Path) -> None:
        store = _signal_store(tmp_path)
        sig1 = _signal(bar_timestamp=_T1, signal_direction="entry_long")
        sig2 = _signal(bar_timestamp=_T1, signal_direction="entry_long")
        store.append_signal(sig1)
        result = store.append_signal(sig2)
        assert result is False
        assert store.count_signals(_SESSION_ID) == 1

    def test_same_timestamp_different_direction_is_not_duplicate(
        self, tmp_path: Path
    ) -> None:
        store = _signal_store(tmp_path)
        sig_entry = _signal(bar_timestamp=_T1, signal_direction="entry_long")
        sig_exit = _signal(bar_timestamp=_T1, signal_direction="exit_long")
        store.append_signal(sig_entry)
        result = store.append_signal(sig_exit)
        assert result is True
        assert store.count_signals(_SESSION_ID) == 2

    def test_different_timestamps_both_written(self, tmp_path: Path) -> None:
        store = _signal_store(tmp_path)
        store.append_signal(_signal(bar_timestamp=_T1))
        result = store.append_signal(_signal(bar_timestamp=_T2))
        assert result is True
        assert store.count_signals(_SESSION_ID) == 2


# ---------------------------------------------------------------------------
# ForwardTestSignalStore — session isolation
# ---------------------------------------------------------------------------

class TestForwardTestSignalStoreIsolation:
    def test_different_sessions_isolated(self, tmp_path: Path) -> None:
        store = _signal_store(tmp_path)
        session_a = str(uuid.uuid4())
        session_b = str(uuid.uuid4())
        store.append_signal(_signal(session_id=session_a))
        store.append_signal(_signal(session_id=session_b))
        assert store.count_signals(session_a) == 1
        assert store.count_signals(session_b) == 1

    def test_invalid_session_id_raises_persistence_error(
        self, tmp_path: Path
    ) -> None:
        store = _signal_store(tmp_path)
        with pytest.raises(ForwardTestPersistenceError):
            store.list_signals("not-a-uuid")


# ---------------------------------------------------------------------------
# ForwardTestBarStore — basic operations
# ---------------------------------------------------------------------------

class TestForwardTestBarStoreAppendAndList:
    def test_list_empty_for_new_session(self, tmp_path: Path) -> None:
        store = _bar_store(tmp_path)
        result = store.list_bars(_SESSION_ID)
        assert result == []

    def test_append_and_list_roundtrip(self, tmp_path: Path) -> None:
        store = _bar_store(tmp_path)
        b = _bar(bar_timestamp=_T1, bar_index=0)
        store.append_bar(b)
        result = store.list_bars(_SESSION_ID)
        assert len(result) == 1
        assert result[0].bar_index == 0
        assert result[0].bar_timestamp == _T1

    def test_multiple_bars_ordered_by_bar_index(self, tmp_path: Path) -> None:
        store = _bar_store(tmp_path)
        b2 = _bar(bar_timestamp=_T3, bar_index=2)
        b0 = _bar(bar_timestamp=_T1, bar_index=0)
        b1 = _bar(bar_timestamp=_T2, bar_index=1)
        store.append_bar(b2)
        store.append_bar(b0)
        store.append_bar(b1)
        result = store.list_bars(_SESSION_ID)
        indices = [b.bar_index for b in result]
        assert indices == [0, 1, 2]

    def test_creates_bars_directory(self, tmp_path: Path) -> None:
        store = _bar_store(tmp_path)
        assert not (tmp_path / "bars").exists()
        store.append_bar(_bar())
        assert (tmp_path / "bars").exists()

    def test_count_bars_correct(self, tmp_path: Path) -> None:
        store = _bar_store(tmp_path)
        store.append_bar(_bar(bar_timestamp=_T1, bar_index=0))
        store.append_bar(_bar(bar_timestamp=_T2, bar_index=1))
        assert store.count_bars(_SESSION_ID) == 2

    def test_count_warmup_bars(self, tmp_path: Path) -> None:
        store = _bar_store(tmp_path)
        store.append_bar(_bar(bar_index=0, is_warmup_bar=True))
        store.append_bar(_bar(bar_timestamp=_T2, bar_index=1, is_warmup_bar=True))
        store.append_bar(_bar(bar_timestamp=_T3, bar_index=2, is_warmup_bar=False))
        assert store.count_warmup_bars(_SESSION_ID) == 2
        assert store.count_signal_eligible_bars(_SESSION_ID) == 1

    def test_count_zero_for_new_session(self, tmp_path: Path) -> None:
        store = _bar_store(tmp_path)
        assert store.count_bars(_SESSION_ID) == 0


# ---------------------------------------------------------------------------
# ForwardTestBarStore — idempotency
# ---------------------------------------------------------------------------

class TestForwardTestBarStoreIdempotency:
    def test_duplicate_bar_not_written(self, tmp_path: Path) -> None:
        store = _bar_store(tmp_path)
        b = _bar(bar_timestamp=_T1, bar_index=0)
        result1 = store.append_bar(b)
        result2 = store.append_bar(b)
        assert result1 is True
        assert result2 is False
        assert store.count_bars(_SESSION_ID) == 1

    def test_same_timestamp_different_index_still_duplicate(
        self, tmp_path: Path
    ) -> None:
        store = _bar_store(tmp_path)
        b1 = _bar(bar_timestamp=_T1, bar_index=0)
        b2 = _bar(bar_timestamp=_T1, bar_index=99)  # same timestamp = duplicate
        store.append_bar(b1)
        result = store.append_bar(b2)
        assert result is False

    def test_different_timestamps_both_written(self, tmp_path: Path) -> None:
        store = _bar_store(tmp_path)
        result1 = store.append_bar(_bar(bar_timestamp=_T1, bar_index=0))
        result2 = store.append_bar(_bar(bar_timestamp=_T2, bar_index=1))
        assert result1 is True
        assert result2 is True
        assert store.count_bars(_SESSION_ID) == 2


# ---------------------------------------------------------------------------
# ForwardTestBarStore — last timestamp queries
# ---------------------------------------------------------------------------

class TestForwardTestBarStoreLastTimestamp:
    def test_get_last_bar_timestamp_returns_none_when_empty(
        self, tmp_path: Path
    ) -> None:
        store = _bar_store(tmp_path)
        result = store.get_last_bar_timestamp(_SESSION_ID)
        assert result is None

    def test_get_last_bar_timestamp_returns_max(self, tmp_path: Path) -> None:
        store = _bar_store(tmp_path)
        store.append_bar(_bar(bar_timestamp=_T1, bar_index=0))
        store.append_bar(_bar(bar_timestamp=_T3, bar_index=2))
        store.append_bar(_bar(bar_timestamp=_T2, bar_index=1))
        result = store.get_last_bar_timestamp(_SESSION_ID)
        assert result == _T3

    def test_get_last_signal_eligible_bar_timestamp_none_when_all_warmup(
        self, tmp_path: Path
    ) -> None:
        store = _bar_store(tmp_path)
        store.append_bar(_bar(bar_timestamp=_T1, bar_index=0, is_warmup_bar=True))
        store.append_bar(_bar(bar_timestamp=_T2, bar_index=1, is_warmup_bar=True))
        result = store.get_last_signal_eligible_bar_timestamp(_SESSION_ID)
        assert result is None

    def test_get_last_signal_eligible_bar_timestamp_correct(
        self, tmp_path: Path
    ) -> None:
        store = _bar_store(tmp_path)
        store.append_bar(_bar(bar_timestamp=_T1, bar_index=0, is_warmup_bar=True))
        store.append_bar(_bar(bar_timestamp=_T2, bar_index=1, is_warmup_bar=False))
        store.append_bar(_bar(bar_timestamp=_T3, bar_index=2, is_warmup_bar=False))
        result = store.get_last_signal_eligible_bar_timestamp(_SESSION_ID)
        assert result == _T3


# ---------------------------------------------------------------------------
# ForwardTestBarStore — session isolation and validation
# ---------------------------------------------------------------------------

class TestForwardTestBarStoreIsolationAndValidation:
    def test_different_sessions_isolated(self, tmp_path: Path) -> None:
        store = _bar_store(tmp_path)
        session_a = str(uuid.uuid4())
        session_b = str(uuid.uuid4())
        store.append_bar(_bar(session_id=session_a))
        store.append_bar(_bar(session_id=session_b))
        assert store.count_bars(session_a) == 1
        assert store.count_bars(session_b) == 1

    def test_invalid_session_id_raises_persistence_error(
        self, tmp_path: Path
    ) -> None:
        store = _bar_store(tmp_path)
        with pytest.raises(ForwardTestPersistenceError):
            store.list_bars("../../etc/passwd")

    def test_last_timestamp_invalid_session_id_raises(
        self, tmp_path: Path
    ) -> None:
        store = _bar_store(tmp_path)
        with pytest.raises(ForwardTestPersistenceError):
            store.get_last_bar_timestamp("not-a-uuid")
