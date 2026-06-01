"""
Unit tests for backend/paper_trading/models.py — Phase 4E.1.

Coverage targets:
  - PaperTradingSessionStatus state machine + helpers
  - SimulationAssumptions field validation
  - PaperStrategySnapshot field validation
  - PaperTradingSession field validation + model validators
  - PaperAccount field validation
  - AccountStateSnapshot field validation
  - Frozen behavior (immutability)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from pydantic import ValidationError

from backend.paper_trading.exceptions import PaperTradingInvalidTransitionError
from backend.paper_trading.models import (
    AccountStateSnapshot,
    FeeMode,
    FillTimingModel,
    PaperAccount,
    PaperAccountStatus,
    PaperStrategySnapshot,
    PaperTradingSession,
    PaperTradingSessionStatus,
    PositionSizeMode,
    SimulationAssumptions,
    SlippageMode,
    is_pt_terminal_status,
    validate_pt_session_transition,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_strategy_snapshot(**overrides) -> PaperStrategySnapshot:
    snapshot_hash = overrides.pop("snapshot_hash", "abc123")
    defaults = {
        "draft_id": _uuid(),
        "display_name": "Test Strategy",
        "lifecycle_status": "draft",
        "snapshot_hash": snapshot_hash,
        "captured_at": _now(),
        "strategy_json": '{"name": "test"}',
    }
    defaults.update(overrides)
    return PaperStrategySnapshot(**defaults)


def _make_simulation_assumptions(**overrides) -> SimulationAssumptions:
    defaults = {"starting_cash": 10_000.0}
    defaults.update(overrides)
    return SimulationAssumptions(**defaults)


def _make_session(**overrides) -> PaperTradingSession:
    snap = _make_strategy_snapshot()
    defaults = {
        "session_id": _uuid(),
        "user_id": _uuid(),
        "draft_id": _uuid(),
        "strategy_snapshot_hash": snap.snapshot_hash,
        "strategy_snapshot": snap,
        "lifecycle_status_at_activation": "draft",
        "account_id": _uuid(),
        "simulation_assumptions": _make_simulation_assumptions(),
        "source_mode": "provider",
        "provider_name": "yahoo",
        "symbol": "AAPL",
        "timeframe": "1d",
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    return PaperTradingSession(**defaults)


def _make_account(**overrides) -> PaperAccount:
    defaults = {
        "account_id": _uuid(),
        "session_id": _uuid(),
        "user_id": _uuid(),
        "currency": "USD",
        "starting_cash": 10_000.0,
        "cash_balance": 10_000.0,
        "equity": 10_000.0,
        "available_cash": 10_000.0,
        "peak_equity": 10_000.0,
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    return PaperAccount(**defaults)


def _make_snapshot(**overrides) -> AccountStateSnapshot:
    defaults = {
        "snapshot_id": _uuid(),
        "session_id": _uuid(),
        "account_id": _uuid(),
        "user_id": _uuid(),
        "bar_timestamp": _now(),
        "snapshot_timestamp": _now(),
        "cash_balance": 10_000.0,
        "equity": 10_000.0,
        "available_cash": 10_000.0,
        "peak_equity": 10_000.0,
        "current_drawdown_pct": 0.0,
        "open_position_count": 0,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "created_at": _now(),
    }
    defaults.update(overrides)
    return AccountStateSnapshot(**defaults)


# ===========================================================================
# PaperTradingSessionStatus state machine
# ===========================================================================

class TestSessionStatusTransitions:
    def test_pending_to_running_allowed(self):
        validate_pt_session_transition(
            PaperTradingSessionStatus.PENDING,
            PaperTradingSessionStatus.RUNNING,
        )

    def test_running_to_paused(self):
        validate_pt_session_transition(
            PaperTradingSessionStatus.RUNNING,
            PaperTradingSessionStatus.PAUSED,
        )

    def test_running_to_completed(self):
        validate_pt_session_transition(
            PaperTradingSessionStatus.RUNNING,
            PaperTradingSessionStatus.COMPLETED,
        )

    def test_running_to_failed(self):
        validate_pt_session_transition(
            PaperTradingSessionStatus.RUNNING,
            PaperTradingSessionStatus.FAILED,
        )

    def test_running_to_terminated(self):
        validate_pt_session_transition(
            PaperTradingSessionStatus.RUNNING,
            PaperTradingSessionStatus.TERMINATED,
        )

    def test_paused_to_running(self):
        validate_pt_session_transition(
            PaperTradingSessionStatus.PAUSED,
            PaperTradingSessionStatus.RUNNING,
        )

    def test_paused_to_completed(self):
        validate_pt_session_transition(
            PaperTradingSessionStatus.PAUSED,
            PaperTradingSessionStatus.COMPLETED,
        )

    def test_paused_to_terminated(self):
        validate_pt_session_transition(
            PaperTradingSessionStatus.PAUSED,
            PaperTradingSessionStatus.TERMINATED,
        )

    def test_pending_to_completed_denied(self):
        with pytest.raises(PaperTradingInvalidTransitionError):
            validate_pt_session_transition(
                PaperTradingSessionStatus.PENDING,
                PaperTradingSessionStatus.COMPLETED,
            )

    def test_pending_to_paused_denied(self):
        with pytest.raises(PaperTradingInvalidTransitionError):
            validate_pt_session_transition(
                PaperTradingSessionStatus.PENDING,
                PaperTradingSessionStatus.PAUSED,
            )

    def test_completed_no_further_transitions(self):
        for target in PaperTradingSessionStatus:
            with pytest.raises(PaperTradingInvalidTransitionError):
                validate_pt_session_transition(
                    PaperTradingSessionStatus.COMPLETED, target
                )

    def test_failed_no_further_transitions(self):
        for target in PaperTradingSessionStatus:
            with pytest.raises(PaperTradingInvalidTransitionError):
                validate_pt_session_transition(
                    PaperTradingSessionStatus.FAILED, target
                )

    def test_terminated_no_further_transitions(self):
        for target in PaperTradingSessionStatus:
            with pytest.raises(PaperTradingInvalidTransitionError):
                validate_pt_session_transition(
                    PaperTradingSessionStatus.TERMINATED, target
                )

    def test_is_terminal_completed(self):
        assert is_pt_terminal_status(PaperTradingSessionStatus.COMPLETED) is True

    def test_is_terminal_failed(self):
        assert is_pt_terminal_status(PaperTradingSessionStatus.FAILED) is True

    def test_is_terminal_terminated(self):
        assert is_pt_terminal_status(PaperTradingSessionStatus.TERMINATED) is True

    def test_not_terminal_pending(self):
        assert is_pt_terminal_status(PaperTradingSessionStatus.PENDING) is False

    def test_not_terminal_running(self):
        assert is_pt_terminal_status(PaperTradingSessionStatus.RUNNING) is False

    def test_not_terminal_paused(self):
        assert is_pt_terminal_status(PaperTradingSessionStatus.PAUSED) is False


# ===========================================================================
# SimulationAssumptions
# ===========================================================================

class TestSimulationAssumptions:
    def test_defaults(self):
        sa = SimulationAssumptions(starting_cash=5_000.0)
        assert sa.currency == "USD"
        assert sa.fill_timing_model == FillTimingModel.NEXT_BAR_OPEN
        assert sa.fee_mode == FeeMode.NONE
        assert sa.fee_value == 0.0
        assert sa.slippage_mode == SlippageMode.NONE
        assert sa.slippage_value == 0.0
        assert sa.position_size_mode == PositionSizeMode.FIXED_QUANTITY
        assert sa.position_size_value == 1.0
        assert sa.max_concurrent_positions == 1
        assert sa.max_drawdown_stop_pct is None
        assert sa.allow_short_selling is False

    def test_starting_cash_zero_rejected(self):
        with pytest.raises(ValidationError, match="starting_cash must be > 0"):
            SimulationAssumptions(starting_cash=0.0)

    def test_starting_cash_negative_rejected(self):
        with pytest.raises(ValidationError, match="starting_cash must be > 0"):
            SimulationAssumptions(starting_cash=-1.0)

    def test_fee_value_negative_rejected(self):
        with pytest.raises(ValidationError):
            SimulationAssumptions(starting_cash=1000.0, fee_value=-0.1)

    def test_slippage_value_negative_rejected(self):
        with pytest.raises(ValidationError):
            SimulationAssumptions(starting_cash=1000.0, slippage_value=-0.01)

    def test_position_size_zero_rejected(self):
        with pytest.raises(ValidationError, match="position_size_value must be > 0"):
            SimulationAssumptions(starting_cash=1000.0, position_size_value=0.0)

    def test_max_concurrent_positions_zero_rejected(self):
        with pytest.raises(ValidationError, match="max_concurrent_positions must be >= 1"):
            SimulationAssumptions(starting_cash=1000.0, max_concurrent_positions=0)

    def test_max_drawdown_stop_zero_rejected(self):
        with pytest.raises(ValidationError, match="max_drawdown_stop_pct must be in range"):
            SimulationAssumptions(starting_cash=1000.0, max_drawdown_stop_pct=0.0)

    def test_max_drawdown_stop_100_allowed(self):
        sa = SimulationAssumptions(starting_cash=1000.0, max_drawdown_stop_pct=100.0)
        assert sa.max_drawdown_stop_pct == 100.0

    def test_max_drawdown_stop_over_100_rejected(self):
        with pytest.raises(ValidationError, match="max_drawdown_stop_pct must be in range"):
            SimulationAssumptions(starting_cash=1000.0, max_drawdown_stop_pct=100.01)

    def test_currency_uppercased(self):
        sa = SimulationAssumptions(starting_cash=1000.0, currency="usd")
        assert sa.currency == "USD"

    def test_currency_empty_rejected(self):
        with pytest.raises(ValidationError, match="currency must not be empty"):
            SimulationAssumptions(starting_cash=1000.0, currency="  ")

    def test_currency_with_slash_rejected(self):
        with pytest.raises(ValidationError, match="forbidden character"):
            SimulationAssumptions(starting_cash=1000.0, currency="US/D")

    def test_currency_with_backslash_rejected(self):
        with pytest.raises(ValidationError, match="forbidden character"):
            SimulationAssumptions(starting_cash=1000.0, currency="US\\D")

    def test_frozen(self):
        sa = SimulationAssumptions(starting_cash=1000.0)
        with pytest.raises(ValidationError):
            sa.starting_cash = 9000.0  # type: ignore[misc]

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            SimulationAssumptions(starting_cash=1000.0, unknown_field="x")  # type: ignore[call-arg]


# ===========================================================================
# PaperStrategySnapshot
# ===========================================================================

class TestPaperStrategySnapshot:
    def test_valid_minimal(self):
        snap = _make_strategy_snapshot()
        assert snap.snapshot_hash == "abc123"
        assert snap.description is None
        assert snap.semantics_hash is None
        assert snap.toolset_hash is None

    def test_captured_at_must_be_utc_aware(self):
        with pytest.raises(ValidationError, match="UTC-aware"):
            _make_strategy_snapshot(captured_at=datetime(2024, 1, 1))

    def test_captured_at_normalized_to_utc(self):
        aware = datetime(2024, 1, 1, tzinfo=timezone(timedelta(hours=5)))
        snap = _make_strategy_snapshot(captured_at=aware)
        assert snap.captured_at.tzinfo == timezone.utc

    def test_frozen(self):
        snap = _make_strategy_snapshot()
        with pytest.raises(ValidationError):
            snap.snapshot_hash = "new"  # type: ignore[misc]

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            _make_strategy_snapshot(unknown="x")


# ===========================================================================
# PaperTradingSession
# ===========================================================================

class TestPaperTradingSession:
    def test_valid_provider_mode(self):
        s = _make_session()
        assert s.status == PaperTradingSessionStatus.PENDING
        assert s.source_mode == "provider"

    def test_valid_catalog_mode(self):
        s = _make_session(source_mode="catalog", catalog_id=_uuid(), provider_name=None)
        assert s.source_mode == "catalog"

    def test_provider_mode_requires_provider_name(self):
        with pytest.raises(ValidationError, match="provider_name is required"):
            _make_session(source_mode="provider", provider_name=None)

    def test_catalog_mode_requires_catalog_id(self):
        with pytest.raises(ValidationError, match="catalog_id is required"):
            _make_session(source_mode="catalog", catalog_id=None, provider_name=None)

    def test_snapshot_hash_mismatch_rejected(self):
        snap = _make_strategy_snapshot(snapshot_hash="real_hash")
        with pytest.raises(ValidationError, match="strategy_snapshot_hash must match"):
            _make_session(strategy_snapshot_hash="wrong_hash", strategy_snapshot=snap)

    def test_invalid_session_id_rejected(self):
        with pytest.raises(ValidationError, match="valid UUID"):
            _make_session(session_id="not-a-uuid")

    def test_invalid_user_id_rejected(self):
        with pytest.raises(ValidationError, match="valid UUID"):
            _make_session(user_id="bad")

    def test_optional_credential_id_must_be_uuid_if_set(self):
        with pytest.raises(ValidationError, match="valid UUID"):
            _make_session(credential_id="not-a-uuid")

    def test_optional_credential_id_none_allowed(self):
        s = _make_session(credential_id=None)
        assert s.credential_id is None

    def test_symbol_empty_rejected(self):
        with pytest.raises(ValidationError, match="symbol must not be empty"):
            _make_session(symbol="  ")

    def test_symbol_uppercased(self):
        s = _make_session(symbol="aapl")
        assert s.symbol == "AAPL"

    def test_timeframe_empty_rejected(self):
        with pytest.raises(ValidationError, match="timeframe must not be empty"):
            _make_session(timeframe="  ")

    def test_created_at_naive_rejected(self):
        with pytest.raises(ValidationError, match="UTC-aware"):
            _make_session(created_at=datetime(2024, 1, 1))

    def test_invalid_lifecycle_status_rejected(self):
        with pytest.raises(ValidationError, match="not a valid StrategyLifecycleStatus"):
            _make_session(lifecycle_status_at_activation="nonexistent_status_xyz")

    def test_valid_lifecycle_status(self):
        s = _make_session(lifecycle_status_at_activation="paper_tested")
        assert s.lifecycle_status_at_activation == "paper_tested"

    def test_frozen(self):
        s = _make_session()
        with pytest.raises(ValidationError):
            s.status = PaperTradingSessionStatus.RUNNING  # type: ignore[misc]

    def test_model_copy_update_status(self):
        s = _make_session()
        now = _now()
        s2 = s.model_copy(update={"status": PaperTradingSessionStatus.RUNNING, "updated_at": now})
        assert s2.status == PaperTradingSessionStatus.RUNNING
        assert s.status == PaperTradingSessionStatus.PENDING  # original unchanged

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            _make_session(unknown_field="x")  # type: ignore[call-arg]

    def test_forward_test_session_id_uuid_validated(self):
        with pytest.raises(ValidationError, match="valid UUID"):
            _make_session(forward_test_session_id="bad-id")

    def test_forward_test_session_id_none_allowed(self):
        s = _make_session(forward_test_session_id=None)
        assert s.forward_test_session_id is None


# ===========================================================================
# PaperAccount
# ===========================================================================

class TestPaperAccount:
    def test_valid_minimal(self):
        a = _make_account()
        assert a.status == PaperAccountStatus.ACTIVE
        assert a.current_drawdown_pct == 0.0
        assert a.closed_at is None

    def test_starting_cash_zero_rejected(self):
        with pytest.raises(ValidationError, match="starting_cash must be > 0"):
            _make_account(starting_cash=0.0)

    def test_cash_balance_negative_rejected(self):
        with pytest.raises(ValidationError):
            _make_account(cash_balance=-1.0)

    def test_equity_negative_rejected(self):
        with pytest.raises(ValidationError):
            _make_account(equity=-0.01)

    def test_available_cash_negative_rejected(self):
        with pytest.raises(ValidationError):
            _make_account(available_cash=-0.01)

    def test_peak_equity_negative_rejected(self):
        with pytest.raises(ValidationError):
            _make_account(peak_equity=-0.01)

    def test_drawdown_out_of_range_rejected(self):
        with pytest.raises(ValidationError, match="current_drawdown_pct must be in range"):
            _make_account(current_drawdown_pct=100.01)

    def test_drawdown_negative_rejected(self):
        with pytest.raises(ValidationError, match="current_drawdown_pct must be in range"):
            _make_account(current_drawdown_pct=-0.01)

    def test_total_fees_paid_negative_rejected(self):
        with pytest.raises(ValidationError):
            _make_account(total_fees_paid=-1.0)

    def test_total_slippage_negative_rejected(self):
        with pytest.raises(ValidationError):
            _make_account(total_slippage_applied=-1.0)

    def test_currency_uppercased(self):
        a = _make_account(currency="eur")
        assert a.currency == "EUR"

    def test_currency_forbidden_chars_rejected(self):
        with pytest.raises(ValidationError, match="forbidden character"):
            _make_account(currency="U/S")

    def test_invalid_account_id_rejected(self):
        with pytest.raises(ValidationError, match="valid UUID"):
            _make_account(account_id="not-a-uuid")

    def test_closed_at_naive_rejected(self):
        with pytest.raises(ValidationError, match="UTC-aware"):
            _make_account(closed_at=datetime(2024, 6, 1))

    def test_frozen(self):
        a = _make_account()
        with pytest.raises(ValidationError):
            a.cash_balance = 9999.0  # type: ignore[misc]

    def test_model_copy_update(self):
        a = _make_account()
        a2 = a.model_copy(update={"cash_balance": 8000.0, "equity": 8000.0})
        assert a2.cash_balance == 8000.0
        assert a.cash_balance == 10_000.0  # original unchanged

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            _make_account(unknown_field="x")  # type: ignore[call-arg]


# ===========================================================================
# AccountStateSnapshot
# ===========================================================================

class TestAccountStateSnapshot:
    def test_valid_minimal(self):
        snap = _make_snapshot()
        assert snap.open_position_count == 0
        assert snap.realized_pnl == 0.0
        assert snap.unrealized_pnl == 0.0

    def test_open_position_count_negative_rejected(self):
        with pytest.raises(ValidationError, match="open_position_count must be >= 0"):
            _make_snapshot(open_position_count=-1)

    def test_drawdown_out_of_range_rejected(self):
        with pytest.raises(ValidationError, match="current_drawdown_pct must be in range"):
            _make_snapshot(current_drawdown_pct=100.01)

    def test_bar_timestamp_naive_rejected(self):
        with pytest.raises(ValidationError, match="UTC-aware"):
            _make_snapshot(bar_timestamp=datetime(2024, 1, 1))

    def test_snapshot_timestamp_naive_rejected(self):
        with pytest.raises(ValidationError, match="UTC-aware"):
            _make_snapshot(snapshot_timestamp=datetime(2024, 1, 1))

    def test_created_at_naive_rejected(self):
        with pytest.raises(ValidationError, match="UTC-aware"):
            _make_snapshot(created_at=datetime(2024, 1, 1))

    def test_invalid_snapshot_id_rejected(self):
        with pytest.raises(ValidationError, match="valid UUID"):
            _make_snapshot(snapshot_id="bad")

    def test_frozen(self):
        snap = _make_snapshot()
        with pytest.raises(ValidationError):
            snap.equity = 0.0  # type: ignore[misc]

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            _make_snapshot(unknown_field="x")  # type: ignore[call-arg]

    def test_timestamps_normalized_to_utc(self):
        offset_tz = timezone(timedelta(hours=3))
        ts = datetime(2024, 6, 1, 12, 0, 0, tzinfo=offset_tz)
        snap = _make_snapshot(bar_timestamp=ts)
        assert snap.bar_timestamp.tzinfo == timezone.utc
        assert snap.bar_timestamp.hour == 9  # 12:00+03:00 = 09:00 UTC
