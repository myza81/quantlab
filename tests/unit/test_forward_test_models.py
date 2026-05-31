"""
Tests for Phase 4C.1 — ForwardTestSession, ForwardTestSignal, ForwardTestBar,
StrategySnapshot, and the session status state machine.

Covers:
  - ForwardTestSessionStatus enum values
  - valid and invalid status transitions
  - terminal state detection
  - StrategySnapshot model validation and immutability
  - ForwardTestSession UUID validation (session_id, user_id, draft_id)
  - ForwardTestSession UTC timestamp enforcement
  - ForwardTestSession source_mode consistency (provider ↔ provider_name, catalog ↔ catalog_id)
  - ForwardTestSession immutability (frozen)
  - ForwardTestSession symbol normalization (uppercase)
  - ForwardTestSession has no file_path or credential fields
  - ForwardTestSignal UUID validation
  - ForwardTestSignal UTC timestamp enforcement
  - ForwardTestSignal immutability
  - ForwardTestSignal has no fill / position / equity / P&L / file_path fields
  - ForwardTestBar UTC timestamp enforcement
  - ForwardTestBar bar_index >= 0
  - ForwardTestBar immutability
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.forward_testing.exceptions import ForwardTestInvalidTransitionError
from backend.forward_testing.models import (
    ForwardTestBar,
    ForwardTestSession,
    ForwardTestSessionStatus,
    ForwardTestSignal,
    StrategySnapshot,
    is_terminal_status,
    validate_session_transition,
)

_UTC = timezone.utc
_NOW = datetime(2026, 5, 29, 12, 0, 0, tzinfo=_UTC)
_LATER = datetime(2026, 5, 29, 13, 0, 0, tzinfo=_UTC)

_SESSION_ID = str(uuid.uuid4())
_USER_ID    = str(uuid.uuid4())
_DRAFT_ID   = str(uuid.uuid4())
_SIGNAL_ID  = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _snapshot(**kw) -> StrategySnapshot:
    base = dict(
        draft_id=_DRAFT_ID,
        display_name="Test Strategy",
        lifecycle_status="backtested",
        snapshot_hash="abc123" * 10,
        captured_at=_NOW,
        strategy_json='{"draft_id": "test"}',
    )
    base.update(kw)
    return StrategySnapshot(**base)


def _session(**kw) -> ForwardTestSession:
    base = dict(
        session_id=_SESSION_ID,
        user_id=_USER_ID,
        draft_id=_DRAFT_ID,
        strategy_snapshot=_snapshot(),
        lifecycle_status_at_activation="backtested",
        source_mode="provider",
        provider_name="yahoo",
        symbol="AAPL",
        timeframe="1d",
        warmup_bars_required=20,
        created_at=_NOW,
        updated_at=_NOW,
    )
    base.update(kw)
    return ForwardTestSession(**base)


def _signal(**kw) -> ForwardTestSignal:
    base = dict(
        signal_id=_SIGNAL_ID,
        session_id=_SESSION_ID,
        user_id=_USER_ID,
        bar_timestamp=_NOW,
        signal_timestamp=_LATER,
        signal_direction="entry_long",
        rule_id="entry_rule_1",
        bar_open=100.0,
        bar_high=105.0,
        bar_low=99.0,
        bar_close=103.0,
        bar_volume=1_000_000.0,
        warmup_satisfied=True,
        strategy_snapshot_hash="abc123" * 10,
        symbol="AAPL",
        timeframe="1d",
        created_at=_LATER,
    )
    base.update(kw)
    return ForwardTestSignal(**base)


def _bar(**kw) -> ForwardTestBar:
    base = dict(
        session_id=_SESSION_ID,
        bar_index=0,
        bar_timestamp=_NOW,
        open=100.0,
        high=105.0,
        low=99.0,
        close=103.0,
        volume=1_000_000.0,
        source_mode="provider",
        provider_name="yahoo",
        is_warmup_bar=True,
        processed_at=_LATER,
    )
    base.update(kw)
    return ForwardTestBar(**base)


# ---------------------------------------------------------------------------
# ForwardTestSessionStatus — enum values
# ---------------------------------------------------------------------------

class TestForwardTestSessionStatusValues:
    def test_all_expected_states_exist(self) -> None:
        expected = {"pending", "running", "paused", "completed", "failed", "terminated"}
        actual = {s.value for s in ForwardTestSessionStatus}
        assert actual == expected

    def test_enum_is_str_subclass(self) -> None:
        assert isinstance(ForwardTestSessionStatus.PENDING, str)


# ---------------------------------------------------------------------------
# validate_session_transition
# ---------------------------------------------------------------------------

class TestValidateSessionTransition:
    def test_pending_to_running_allowed(self) -> None:
        validate_session_transition(
            ForwardTestSessionStatus.PENDING, ForwardTestSessionStatus.RUNNING
        )

    def test_running_to_paused_allowed(self) -> None:
        validate_session_transition(
            ForwardTestSessionStatus.RUNNING, ForwardTestSessionStatus.PAUSED
        )

    def test_running_to_completed_allowed(self) -> None:
        validate_session_transition(
            ForwardTestSessionStatus.RUNNING, ForwardTestSessionStatus.COMPLETED
        )

    def test_running_to_failed_allowed(self) -> None:
        validate_session_transition(
            ForwardTestSessionStatus.RUNNING, ForwardTestSessionStatus.FAILED
        )

    def test_running_to_terminated_allowed(self) -> None:
        validate_session_transition(
            ForwardTestSessionStatus.RUNNING, ForwardTestSessionStatus.TERMINATED
        )

    def test_paused_to_running_allowed(self) -> None:
        validate_session_transition(
            ForwardTestSessionStatus.PAUSED, ForwardTestSessionStatus.RUNNING
        )

    def test_paused_to_completed_allowed(self) -> None:
        validate_session_transition(
            ForwardTestSessionStatus.PAUSED, ForwardTestSessionStatus.COMPLETED
        )

    def test_paused_to_terminated_allowed(self) -> None:
        validate_session_transition(
            ForwardTestSessionStatus.PAUSED, ForwardTestSessionStatus.TERMINATED
        )

    def test_pending_to_paused_raises(self) -> None:
        with pytest.raises(ForwardTestInvalidTransitionError, match="pending"):
            validate_session_transition(
                ForwardTestSessionStatus.PENDING, ForwardTestSessionStatus.PAUSED
            )

    def test_pending_to_completed_raises(self) -> None:
        with pytest.raises(ForwardTestInvalidTransitionError):
            validate_session_transition(
                ForwardTestSessionStatus.PENDING, ForwardTestSessionStatus.COMPLETED
            )

    def test_completed_to_running_raises(self) -> None:
        with pytest.raises(ForwardTestInvalidTransitionError, match="terminal"):
            validate_session_transition(
                ForwardTestSessionStatus.COMPLETED, ForwardTestSessionStatus.RUNNING
            )

    def test_failed_to_running_raises(self) -> None:
        with pytest.raises(ForwardTestInvalidTransitionError):
            validate_session_transition(
                ForwardTestSessionStatus.FAILED, ForwardTestSessionStatus.RUNNING
            )

    def test_terminated_to_running_raises(self) -> None:
        with pytest.raises(ForwardTestInvalidTransitionError):
            validate_session_transition(
                ForwardTestSessionStatus.TERMINATED, ForwardTestSessionStatus.RUNNING
            )

    def test_running_to_pending_raises(self) -> None:
        with pytest.raises(ForwardTestInvalidTransitionError):
            validate_session_transition(
                ForwardTestSessionStatus.RUNNING, ForwardTestSessionStatus.PENDING
            )


# ---------------------------------------------------------------------------
# is_terminal_status
# ---------------------------------------------------------------------------

class TestIsTerminalStatus:
    def test_completed_is_terminal(self) -> None:
        assert is_terminal_status(ForwardTestSessionStatus.COMPLETED) is True

    def test_failed_is_terminal(self) -> None:
        assert is_terminal_status(ForwardTestSessionStatus.FAILED) is True

    def test_terminated_is_terminal(self) -> None:
        assert is_terminal_status(ForwardTestSessionStatus.TERMINATED) is True

    def test_pending_is_not_terminal(self) -> None:
        assert is_terminal_status(ForwardTestSessionStatus.PENDING) is False

    def test_running_is_not_terminal(self) -> None:
        assert is_terminal_status(ForwardTestSessionStatus.RUNNING) is False

    def test_paused_is_not_terminal(self) -> None:
        assert is_terminal_status(ForwardTestSessionStatus.PAUSED) is False


# ---------------------------------------------------------------------------
# StrategySnapshot
# ---------------------------------------------------------------------------

class TestStrategySnapshot:
    def test_valid_snapshot(self) -> None:
        s = _snapshot()
        assert s.draft_id == _DRAFT_ID
        assert s.lifecycle_status == "backtested"

    def test_naive_captured_at_raises(self) -> None:
        with pytest.raises(ValidationError, match="UTC-aware"):
            _snapshot(captured_at=datetime(2026, 1, 1))

    def test_frozen_cannot_mutate(self) -> None:
        s = _snapshot()
        with pytest.raises(Exception):
            s.display_name = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ForwardTestSession — creation
# ---------------------------------------------------------------------------

class TestForwardTestSessionCreation:
    def test_valid_session(self) -> None:
        s = _session()
        assert s.session_id == _SESSION_ID
        assert s.status == ForwardTestSessionStatus.PENDING

    def test_symbol_normalized_to_uppercase(self) -> None:
        s = _session(symbol="aapl")
        assert s.symbol == "AAPL"

    def test_symbol_with_whitespace_stripped(self) -> None:
        s = _session(symbol=" msft ")
        assert s.symbol == "MSFT"

    def test_warmup_bars_required_zero_is_valid(self) -> None:
        s = _session(warmup_bars_required=0)
        assert s.warmup_bars_required == 0

    def test_warmup_bars_required_negative_raises(self) -> None:
        with pytest.raises(ValidationError, match="warmup_bars_required"):
            _session(warmup_bars_required=-1)

    def test_defaults_counters_are_zero(self) -> None:
        s = _session()
        assert s.bars_evaluated == 0
        assert s.warmup_bars_processed == 0
        assert s.signal_eligible_bars_processed == 0
        assert s.signals_recorded == 0

    def test_activation_timestamp_defaults_none(self) -> None:
        s = _session()
        assert s.activation_timestamp is None

    def test_last_processed_bar_timestamp_defaults_none(self) -> None:
        s = _session()
        assert s.last_processed_bar_timestamp is None


# ---------------------------------------------------------------------------
# ForwardTestSession — UUID validation
# ---------------------------------------------------------------------------

class TestForwardTestSessionUUIDValidation:
    def test_invalid_session_id_raises(self) -> None:
        with pytest.raises(ValidationError, match="valid UUID"):
            _session(session_id="not-a-uuid")

    def test_invalid_user_id_raises(self) -> None:
        with pytest.raises(ValidationError, match="valid UUID"):
            _session(user_id="not-a-uuid")

    def test_invalid_draft_id_raises(self) -> None:
        with pytest.raises(ValidationError, match="valid UUID"):
            _session(draft_id="not-a-uuid")

    def test_path_traversal_session_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            _session(session_id="../../etc/passwd")


# ---------------------------------------------------------------------------
# ForwardTestSession — UTC timestamp enforcement
# ---------------------------------------------------------------------------

class TestForwardTestSessionTimestamps:
    def test_naive_created_at_raises(self) -> None:
        with pytest.raises(ValidationError, match="UTC-aware"):
            _session(created_at=datetime(2026, 1, 1))

    def test_naive_updated_at_raises(self) -> None:
        with pytest.raises(ValidationError, match="UTC-aware"):
            _session(updated_at=datetime(2026, 1, 1))

    def test_naive_activation_timestamp_raises(self) -> None:
        with pytest.raises(ValidationError, match="UTC-aware"):
            _session(activation_timestamp=datetime(2026, 1, 1))

    def test_aware_activation_timestamp_accepted(self) -> None:
        s = _session(activation_timestamp=_NOW)
        assert s.activation_timestamp is not None

    def test_none_activation_timestamp_accepted(self) -> None:
        s = _session(activation_timestamp=None)
        assert s.activation_timestamp is None


# ---------------------------------------------------------------------------
# ForwardTestSession — source_mode consistency
# ---------------------------------------------------------------------------

class TestForwardTestSessionSourceMode:
    def test_provider_mode_without_provider_name_raises(self) -> None:
        with pytest.raises(ValidationError, match="provider_name"):
            _session(source_mode="provider", provider_name=None)

    def test_catalog_mode_without_catalog_id_raises(self) -> None:
        with pytest.raises(ValidationError, match="catalog_id"):
            _session(source_mode="catalog", provider_name=None, catalog_id=None)

    def test_catalog_mode_with_catalog_id_valid(self) -> None:
        s = _session(
            source_mode="catalog",
            provider_name=None,
            catalog_id=str(uuid.uuid4()),
        )
        assert s.source_mode == "catalog"

    def test_invalid_source_mode_raises(self) -> None:
        with pytest.raises(ValidationError):
            _session(source_mode="websocket")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ForwardTestSession — immutability and field safety
# ---------------------------------------------------------------------------

class TestForwardTestSessionFieldSafety:
    def test_frozen_cannot_mutate_status(self) -> None:
        s = _session()
        with pytest.raises(Exception):
            s.status = ForwardTestSessionStatus.RUNNING  # type: ignore[misc]

    def test_no_file_path_field(self) -> None:
        s = _session()
        assert not hasattr(s, "file_path")

    def test_no_encrypted_secret_field(self) -> None:
        s = _session()
        assert not hasattr(s, "encrypted_secret")

    def test_no_password_hash_field(self) -> None:
        s = _session()
        assert not hasattr(s, "password_hash")

    def test_no_fill_field(self) -> None:
        assert not hasattr(ForwardTestSession.model_fields, "fills")
        assert not hasattr(ForwardTestSession.model_fields, "fill_price")

    def test_no_equity_field(self) -> None:
        assert not hasattr(ForwardTestSession.model_fields, "equity")
        assert not hasattr(ForwardTestSession.model_fields, "pnl")

    def test_serialized_json_no_file_path(self) -> None:
        s = _session()
        json_str = s.model_dump_json()
        assert "file_path" not in json_str

    def test_serialized_json_no_encrypted_secret(self) -> None:
        s = _session()
        json_str = s.model_dump_json()
        assert "encrypted_secret" not in json_str


# ---------------------------------------------------------------------------
# ForwardTestSignal
# ---------------------------------------------------------------------------

class TestForwardTestSignal:
    def test_valid_signal(self) -> None:
        sig = _signal()
        assert sig.signal_id == _SIGNAL_ID
        assert sig.signal_direction == "entry_long"
        assert sig.warmup_satisfied is True

    def test_symbol_normalized_uppercase(self) -> None:
        sig = _signal(symbol="aapl")
        assert sig.symbol == "AAPL"

    def test_invalid_signal_id_raises(self) -> None:
        with pytest.raises(ValidationError, match="valid UUID"):
            _signal(signal_id="not-a-uuid")

    def test_naive_bar_timestamp_raises(self) -> None:
        with pytest.raises(ValidationError, match="UTC-aware"):
            _signal(bar_timestamp=datetime(2026, 1, 1))

    def test_naive_signal_timestamp_raises(self) -> None:
        with pytest.raises(ValidationError, match="UTC-aware"):
            _signal(signal_timestamp=datetime(2026, 1, 1))

    def test_frozen_cannot_mutate(self) -> None:
        sig = _signal()
        with pytest.raises(Exception):
            sig.rule_id = "other"  # type: ignore[misc]

    def test_no_file_path_field(self) -> None:
        assert not hasattr(ForwardTestSignal.model_fields, "file_path")

    def test_no_fill_fields(self) -> None:
        assert not hasattr(ForwardTestSignal.model_fields, "fill_price")
        assert not hasattr(ForwardTestSignal.model_fields, "position_size")
        assert not hasattr(ForwardTestSignal.model_fields, "equity")
        assert not hasattr(ForwardTestSignal.model_fields, "pnl")

    def test_feature_values_defaults_empty_dict(self) -> None:
        sig = _signal()
        assert sig.feature_values_at_signal == {}

    def test_feature_values_populated(self) -> None:
        sig = _signal(feature_values_at_signal={"sma_fast.sma": 101.5})
        assert sig.feature_values_at_signal["sma_fast.sma"] == 101.5


# ---------------------------------------------------------------------------
# ForwardTestBar
# ---------------------------------------------------------------------------

class TestForwardTestBar:
    def test_valid_bar(self) -> None:
        b = _bar()
        assert b.session_id == _SESSION_ID
        assert b.bar_index == 0
        assert b.is_warmup_bar is True

    def test_signal_eligible_bar(self) -> None:
        b = _bar(is_warmup_bar=False, bar_index=20)
        assert b.is_warmup_bar is False

    def test_naive_bar_timestamp_raises(self) -> None:
        with pytest.raises(ValidationError, match="UTC-aware"):
            _bar(bar_timestamp=datetime(2026, 1, 1))

    def test_naive_processed_at_raises(self) -> None:
        with pytest.raises(ValidationError, match="UTC-aware"):
            _bar(processed_at=datetime(2026, 1, 1))

    def test_negative_bar_index_raises(self) -> None:
        with pytest.raises(ValidationError, match="bar_index"):
            _bar(bar_index=-1)

    def test_frozen_cannot_mutate(self) -> None:
        b = _bar()
        with pytest.raises(Exception):
            b.bar_index = 5  # type: ignore[misc]

    def test_invalid_session_id_raises(self) -> None:
        with pytest.raises(ValidationError, match="valid UUID"):
            _bar(session_id="../../etc/passwd")

    def test_no_file_path_field(self) -> None:
        assert not hasattr(ForwardTestBar.model_fields, "file_path")
