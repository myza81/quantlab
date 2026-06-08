"""
tests/unit/test_paper_trading_service.py — Phase 4E.3.

Unit tests for PaperTradingService — single-cycle execution engine.

Mocking strategy:
  - All 10 external dependencies (stores, repository, OHLCV service) use MagicMock.
  - Module-level subsystems (evaluate_history, compute_tool_outputs_for_history,
    get_calendar, emit_audit_event) are patched via their import path in
    backend.paper_trading.service.
  - Factory helpers build minimal valid Pydantic models without any database,
    filesystem, or provider access.
  - _prepare_strategy is patched via patch.object for all run_cycle/poll-cycle
    tests to avoid requiring a real serializable StrategyDraft.

Bar evaluation: HistoricalEvaluationInput(plan=MagicMock(), ...) raises a
ValidationError inside the try/except in _poll_cycle. The exception is caught
silently, bar_result stays None, and signal-processing is skipped. This is
acceptable for tests focused on bar-processing mechanics, not signal logic.
Signal processing (entry/exit) is exercised directly via _process_entry_signal
and _process_exit_signal unit tests.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from backend.forward_testing.stores import ForwardTestBarStore, ForwardTestSignalStore
from backend.paper_trading.execution_models import (
    ExecutionReason,
    OrderDirection,
    PaperFill,
    PaperOrder,
    PaperOrderStatus,
    PaperPosition,
    RejectionReason,
)
from backend.paper_trading.execution_stores import (
    PaperFillStore,
    PaperOrderStore,
    PaperPositionStore,
)
from backend.paper_trading.models import (
    FeeMode,
    FillTimingModel,
    PaperAccount,
    PaperStrategySnapshot,
    PaperTradingSession,
    PaperTradingSessionStatus,
    PositionSizeMode,
    SimulationAssumptions,
    SlippageMode,
)
from backend.paper_trading.repository import PaperTradingRepository
from backend.paper_trading.service import (
    PaperCycleResult,
    PaperTradingService,
    _compute_drawdown,
    _get_triggered_rule_id,
)
from backend.paper_trading.stores import AccountStateSnapshotStore, PaperAccountStore
from backend.services.ohlcv_service import OHLCVService
from backend.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Patch target prefix
# ---------------------------------------------------------------------------

_SVC = "backend.paper_trading.service"


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


def _ts(offset_days: int = 0) -> datetime:
    return datetime(2025, 1, 10, 12, 0, 0, tzinfo=timezone.utc) + timedelta(days=offset_days)


def _make_assumptions(**overrides) -> SimulationAssumptions:
    defaults: dict = {
        "starting_cash": 10_000.0,
        "fill_timing_model": FillTimingModel.NEXT_BAR_OPEN,
        "fee_mode": FeeMode.NONE,
        "fee_value": 0.0,
        "slippage_mode": SlippageMode.NONE,
        "slippage_value": 0.0,
        "position_size_mode": PositionSizeMode.FIXED_QUANTITY,
        "position_size_value": 10.0,
        "max_concurrent_positions": 3,
        "max_drawdown_stop_pct": None,
    }
    defaults.update(overrides)
    return SimulationAssumptions(**defaults)


def _make_snapshot(draft_id: str | None = None) -> tuple[str, PaperStrategySnapshot]:
    djid = draft_id or _uid()
    content = '{"draft_id":"placeholder"}'
    snap_hash = hashlib.sha256(content.encode()).hexdigest()
    return snap_hash, PaperStrategySnapshot(
        draft_id=djid,
        display_name="Test Strategy",
        lifecycle_status="validated",
        snapshot_hash=snap_hash,
        captured_at=_ts(),
        strategy_json=content,
    )


def _make_session(
    status: PaperTradingSessionStatus = PaperTradingSessionStatus.PENDING,
    **overrides,
) -> PaperTradingSession:
    did = overrides.pop("draft_id", _uid())
    snap_hash, snap = _make_snapshot(draft_id=did)
    base: dict = {
        "session_id": _uid(),
        "user_id": _uid(),
        "draft_id": did,
        "strategy_snapshot_hash": snap_hash,
        "strategy_snapshot": snap,
        "lifecycle_status_at_activation": "validated",
        "account_id": _uid(),
        "simulation_assumptions": _make_assumptions(),
        "source_mode": "provider",
        "provider_name": "yahoo",
        "symbol": "AAPL",
        "timeframe": "1d",
        "status": status,
        "created_at": _ts(),
        "updated_at": _ts(),
    }
    base.update(overrides)
    return PaperTradingSession(**base)


def _make_account(
    session_id: str,
    user_id: str,
    *,
    cash: float = 10_000.0,
    **overrides,
) -> PaperAccount:
    # starting_cash must be > 0; when cash is 0 (fully-invested test), use a minimum.
    sc = overrides.pop("starting_cash", max(cash, 1_000.0))
    pk = overrides.pop("peak_equity", max(cash, sc))
    base: dict = {
        "account_id": _uid(),
        "session_id": session_id,
        "user_id": user_id,
        "currency": "USD",
        "starting_cash": sc,
        "cash_balance": cash,
        "equity": cash,
        "available_cash": cash,
        "peak_equity": pk,
        "created_at": _ts(),
        "updated_at": _ts(),
    }
    base.update(overrides)
    return PaperAccount(**base)


def _make_position(
    session_id: str,
    user_id: str,
    account_id: str,
    *,
    symbol: str = "AAPL",
    quantity: float = 10.0,
    entry_price: float = 100.0,
    current_price: float = 100.0,
) -> PaperPosition:
    now = _ts()
    return PaperPosition(
        position_id=_uid(),
        session_id=session_id,
        account_id=account_id,
        user_id=user_id,
        symbol=symbol,
        quantity=quantity,
        average_entry_price=entry_price,
        current_price=current_price,
        market_value=quantity * current_price,
        unrealized_pnl=(current_price - entry_price) * quantity,
        realized_pnl=0.0,
        is_open=True,
        opened_at=now,
        last_updated_at=now,
    )


def _make_fill(
    session_id: str,
    user_id: str,
    account_id: str,
    *,
    direction: OrderDirection = OrderDirection.BUY,
    price: float = 100.0,
    qty: float = 10.0,
    fee: float = 0.0,
) -> PaperFill:
    now = _ts()
    return PaperFill(
        fill_id=_uid(),
        order_id=_uid(),
        session_id=session_id,
        account_id=account_id,
        user_id=user_id,
        symbol="AAPL",
        direction=direction,
        quantity=qty,
        gross_price=price,
        slippage=0.0,
        fill_price=price,
        gross_value=qty * price,
        fee=fee,
        net_value=qty * price,
        fill_bar_timestamp=now,
        created_at=now,
        execution_reason=ExecutionReason.SIGNAL_ENTRY,
    )


def _make_pending_order(
    session: PaperTradingSession,
    direction: OrderDirection = OrderDirection.BUY,
    qty: float = 10.0,
) -> PaperOrder:
    now = _ts()
    return PaperOrder(
        order_id=_uid(),
        session_id=session.session_id,
        account_id=session.account_id,
        user_id=session.user_id,
        symbol=session.symbol,
        direction=direction,
        quantity=qty,
        status=PaperOrderStatus.PENDING_FILL,
        fill_timing_model=FillTimingModel.NEXT_BAR_OPEN,
        signal_bar_timestamp=now,
        created_at=now,
        updated_at=now,
    )


def _make_bar(
    offset_days: int = 0,
    *,
    open_: float = 100.0,
    high: float = 105.0,
    low: float = 95.0,
    close: float = 102.0,
    volume: float = 10_000.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        timestamp=_ts(offset_days),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _make_service() -> tuple[PaperTradingService, dict]:
    mocks = {
        "repository":     MagicMock(spec=PaperTradingRepository),
        "account_store":  MagicMock(spec=PaperAccountStore),
        "snapshot_store": MagicMock(spec=AccountStateSnapshotStore),
        "order_store":    MagicMock(spec=PaperOrderStore),
        "fill_store":     MagicMock(spec=PaperFillStore),
        "position_store": MagicMock(spec=PaperPositionStore),
        "bar_store":      MagicMock(spec=ForwardTestBarStore),
        "signal_store":   MagicMock(spec=ForwardTestSignalStore),
        "ohlcv_service":  MagicMock(spec=OHLCVService),
        "tool_registry":  MagicMock(spec=ToolRegistry),
    }
    return PaperTradingService(**mocks), mocks


def _fake_result(**overrides) -> PaperCycleResult:
    defaults: dict = {
        "session_id": _uid(),
        "status": "running",
        "bars_fetched": 0,
        "bars_processed": 0,
        "warmup_bars_processed": 0,
        "signal_eligible_bars_processed": 0,
        "signals_generated": 0,
        "signals_suppressed": 0,
        "pending_orders_resolved": 0,
        "orders_created": 0,
        "orders_rejected": 0,
        "fills_created": 0,
        "positions_opened": 0,
        "positions_closed": 0,
        "account_snapshot_created": False,
        "last_processed_bar_timestamp": None,
        "gap_detected": False,
        "provider_failure": False,
        "activated": False,
    }
    defaults.update(overrides)
    return PaperCycleResult(**defaults)


# ---------------------------------------------------------------------------
# TestPaperCycleResult — dataclass contract
# ---------------------------------------------------------------------------

class TestPaperCycleResultDataclass:
    def test_all_fields_accessible(self):
        r = _fake_result(session_id=_uid(), status="running", bars_fetched=2, bars_processed=2)
        assert r.bars_fetched == 2
        assert r.bars_processed == 2
        assert r.status == "running"

    def test_is_frozen(self):
        r = _fake_result()
        with pytest.raises((FrozenInstanceError, TypeError)):
            r.bars_fetched = 99  # type: ignore[misc]

    def test_defaults_for_optional_fields(self):
        r = _fake_result()
        assert r.drawdown_stop_triggered is False
        assert r.message is None


# ---------------------------------------------------------------------------
# TestRunCycleRoutingTerminal
# ---------------------------------------------------------------------------

class TestRunCycleRoutingTerminal:
    @pytest.mark.parametrize("status", [
        PaperTradingSessionStatus.COMPLETED,
        PaperTradingSessionStatus.FAILED,
        PaperTradingSessionStatus.TERMINATED,
    ])
    def test_terminal_returns_no_op(self, status):
        svc, mocks = _make_service()
        session = _make_session(status=status)
        mocks["repository"].load.return_value = session

        result = svc.run_cycle(session.session_id, session.user_id, MagicMock(), MagicMock(), now_utc=_ts())

        assert result.activated is False
        assert result.bars_fetched == 0
        assert result.bars_processed == 0
        assert result.fills_created == 0

    @pytest.mark.parametrize("status", [
        PaperTradingSessionStatus.COMPLETED,
        PaperTradingSessionStatus.FAILED,
        PaperTradingSessionStatus.TERMINATED,
    ])
    def test_terminal_message_names_state(self, status):
        svc, mocks = _make_service()
        session = _make_session(status=status)
        mocks["repository"].load.return_value = session

        result = svc.run_cycle(session.session_id, session.user_id, MagicMock(), MagicMock(), now_utc=_ts())

        assert result.message is not None
        assert "terminal" in result.message

    def test_terminal_status_in_result_matches_session(self):
        svc, mocks = _make_service()
        session = _make_session(status=PaperTradingSessionStatus.FAILED)
        mocks["repository"].load.return_value = session

        result = svc.run_cycle(session.session_id, session.user_id, MagicMock(), MagicMock(), now_utc=_ts())

        assert result.status == "failed"


# ---------------------------------------------------------------------------
# TestRunCycleRoutingPaused
# ---------------------------------------------------------------------------

class TestRunCycleRoutingPaused:
    def test_paused_returns_no_op(self):
        svc, mocks = _make_service()
        session = _make_session(status=PaperTradingSessionStatus.PAUSED)
        mocks["repository"].load.return_value = session

        result = svc.run_cycle(session.session_id, session.user_id, MagicMock(), MagicMock(), now_utc=_ts())

        assert result.activated is False
        assert result.bars_fetched == 0
        assert result.fills_created == 0

    def test_paused_message_says_paused(self):
        svc, mocks = _make_service()
        session = _make_session(status=PaperTradingSessionStatus.PAUSED)
        mocks["repository"].load.return_value = session

        result = svc.run_cycle(session.session_id, session.user_id, MagicMock(), MagicMock(), now_utc=_ts())

        assert result.message is not None
        assert "paused" in result.message


# ---------------------------------------------------------------------------
# TestRunCycleRoutingPending
# ---------------------------------------------------------------------------

class TestRunCycleRoutingPending:
    def test_pending_activates_and_returns_activated(self):
        svc, mocks = _make_service()
        session = _make_session(status=PaperTradingSessionStatus.PENDING)
        mocks["repository"].load.return_value = session

        fake = _fake_result(activated=True, status="running")
        with patch.object(svc, "_activate", return_value=fake) as mock_act:
            result = svc.run_cycle(session.session_id, session.user_id, MagicMock(), MagicMock(), now_utc=_ts())

        mock_act.assert_called_once()
        assert result.activated is True

    def test_ownership_enforced_on_repository_load(self):
        svc, mocks = _make_service()
        session = _make_session(status=PaperTradingSessionStatus.PAUSED)
        owner_id = session.user_id
        mocks["repository"].load.return_value = session

        svc.run_cycle(session.session_id, owner_id, MagicMock(), MagicMock(), now_utc=_ts())

        call_kwargs = mocks["repository"].load.call_args
        assert call_kwargs.kwargs.get("owner_id") == owner_id or (
            len(call_kwargs.args) > 1 and call_kwargs.args[1] == owner_id
        )

    def test_running_calls_poll_cycle(self):
        svc, mocks = _make_service()
        session = _make_session(
            status=PaperTradingSessionStatus.RUNNING,
            last_processed_bar_timestamp=_ts(-1),
        )
        mocks["repository"].load.return_value = session

        fake = _fake_result(status="running", bars_fetched=1)
        with patch.object(svc, "_prepare_strategy", return_value=(None, None, 0, None)):
            with patch.object(svc, "_poll_cycle", return_value=fake) as mock_poll:
                result = svc.run_cycle(session.session_id, session.user_id, MagicMock(), MagicMock(), now_utc=_ts())

        mock_poll.assert_called_once()
        assert result.bars_fetched == 1


# ---------------------------------------------------------------------------
# TestActivate
# ---------------------------------------------------------------------------

class TestActivate:
    def test_zero_warmup_activation_sets_activated_true(self):
        svc, mocks = _make_service()
        session = _make_session(status=PaperTradingSessionStatus.PENDING)

        with patch.object(svc, "_prepare_strategy", return_value=(None, None, 0, None)):
            with patch(f"{_SVC}.emit_audit_event"):
                mocks["ohlcv_service"].get_recent_bars.return_value = []
                mocks["bar_store"].count_bars.return_value = 0

                result = svc._activate(session, session.user_id, MagicMock(), MagicMock(), _ts())

        assert result.activated is True
        assert result.status == "running"
        assert result.warmup_bars_processed == 0

    def test_cursor_set_to_now_when_no_warmup_bars(self):
        svc, mocks = _make_service()
        session = _make_session(status=PaperTradingSessionStatus.PENDING)
        now = _ts(2)

        with patch.object(svc, "_prepare_strategy", return_value=(None, None, 0, None)):
            with patch(f"{_SVC}.emit_audit_event"):
                mocks["ohlcv_service"].get_recent_bars.return_value = []
                mocks["bar_store"].count_bars.return_value = 0

                result = svc._activate(session, session.user_id, MagicMock(), MagicMock(), now)

        assert result.last_processed_bar_timestamp == now

    def test_warmup_bars_stored(self):
        svc, mocks = _make_service()
        session = _make_session(status=PaperTradingSessionStatus.PENDING)
        bar1 = _make_bar(0)
        bar2 = _make_bar(1)

        with patch.object(svc, "_prepare_strategy", return_value=(None, None, 2, None)):
            with patch(f"{_SVC}.emit_audit_event"):
                mocks["ohlcv_service"].get_recent_bars.return_value = [bar1, bar2]
                mocks["bar_store"].count_bars.return_value = 0
                mocks["bar_store"].append_bar.return_value = True

                result = svc._activate(session, session.user_id, MagicMock(), MagicMock(), _ts(2))

        assert mocks["bar_store"].append_bar.call_count == 2
        assert result.warmup_bars_processed == 2

    def test_warmup_bars_stored_with_is_warmup_true(self):
        svc, mocks = _make_service()
        session = _make_session(status=PaperTradingSessionStatus.PENDING)
        bar1 = _make_bar(0)

        with patch.object(svc, "_prepare_strategy", return_value=(None, None, 1, None)):
            with patch(f"{_SVC}.emit_audit_event"):
                mocks["ohlcv_service"].get_recent_bars.return_value = [bar1]
                mocks["bar_store"].count_bars.return_value = 0
                mocks["bar_store"].append_bar.return_value = True

                svc._activate(session, session.user_id, MagicMock(), MagicMock(), _ts(1))

        stored_bar = mocks["bar_store"].append_bar.call_args.args[0]
        assert stored_bar.is_warmup_bar is True

    def test_cursor_set_to_last_warmup_bar_timestamp(self):
        svc, mocks = _make_service()
        session = _make_session(status=PaperTradingSessionStatus.PENDING)
        bar1 = _make_bar(0)
        bar2 = _make_bar(3)  # last warmup bar has ts at +3 days

        with patch.object(svc, "_prepare_strategy", return_value=(None, None, 2, None)):
            with patch(f"{_SVC}.emit_audit_event"):
                mocks["ohlcv_service"].get_recent_bars.return_value = [bar1, bar2]
                mocks["bar_store"].count_bars.return_value = 0
                mocks["bar_store"].append_bar.return_value = True

                result = svc._activate(session, session.user_id, MagicMock(), MagicMock(), _ts(5))

        assert result.last_processed_bar_timestamp == bar2.timestamp

    def test_session_transitioned_to_running(self):
        svc, mocks = _make_service()
        session = _make_session(status=PaperTradingSessionStatus.PENDING)

        with patch.object(svc, "_prepare_strategy", return_value=(None, None, 0, None)):
            with patch(f"{_SVC}.emit_audit_event"):
                mocks["ohlcv_service"].get_recent_bars.return_value = []
                mocks["bar_store"].count_bars.return_value = 0

                svc._activate(session, session.user_id, MagicMock(), MagicMock(), _ts())

        mocks["repository"].update.assert_called_once()
        updated_session = mocks["repository"].update.call_args.args[0]
        assert updated_session.status == PaperTradingSessionStatus.RUNNING

    def test_provider_failure_still_activates(self):
        svc, mocks = _make_service()
        session = _make_session(status=PaperTradingSessionStatus.PENDING)

        mocks["ohlcv_service"].get_recent_bars.side_effect = RuntimeError("provider down")

        with patch.object(svc, "_prepare_strategy", return_value=(None, None, 1, None)):
            with patch(f"{_SVC}.emit_audit_event"):
                mocks["bar_store"].count_bars.return_value = 0

                result = svc._activate(session, session.user_id, MagicMock(), MagicMock(), _ts())

        assert result.activated is True
        assert result.provider_failure is True
        assert result.status == "running"


# ---------------------------------------------------------------------------
# TestPollCycleNoBars
# ---------------------------------------------------------------------------

class TestPollCycleNoBars:
    def _run_with_no_bars(self, status=PaperTradingSessionStatus.RUNNING, last_ts=None):
        svc, mocks = _make_service()
        session = _make_session(
            status=status,
            last_processed_bar_timestamp=last_ts or _ts(-1),
        )
        mocks["repository"].load.return_value = session
        mocks["ohlcv_service"].get_bars_since.return_value = []

        with patch.object(svc, "_prepare_strategy", return_value=(None, None, 0, None)):
            with patch(f"{_SVC}.get_calendar", return_value=MagicMock()):
                with patch(f"{_SVC}.emit_audit_event"):
                    result = svc.run_cycle(
                        session.session_id, session.user_id, MagicMock(), MagicMock(), now_utc=_ts()
                    )
        return result

    def test_no_new_bars_returns_zero_bars_fetched(self):
        result = self._run_with_no_bars()
        assert result.bars_fetched == 0
        assert result.bars_processed == 0

    def test_no_new_bars_returns_descriptive_message(self):
        result = self._run_with_no_bars()
        assert result.message is not None
        assert "no new" in result.message.lower() or "finalized" in result.message.lower()

    def test_provider_failure_during_poll_returns_failure_flag(self):
        svc, mocks = _make_service()
        session = _make_session(
            status=PaperTradingSessionStatus.RUNNING,
            last_processed_bar_timestamp=_ts(-1),
        )
        mocks["repository"].load.return_value = session
        mocks["ohlcv_service"].get_bars_since.side_effect = RuntimeError("provider error")

        with patch.object(svc, "_prepare_strategy", return_value=(None, None, 0, None)):
            with patch(f"{_SVC}.get_calendar", return_value=MagicMock()):
                with patch(f"{_SVC}.emit_audit_event"):
                    result = svc.run_cycle(
                        session.session_id, session.user_id, MagicMock(), MagicMock(), now_utc=_ts()
                    )

        assert result.provider_failure is True
        assert result.bars_fetched == 0


# ---------------------------------------------------------------------------
# TestPollCycleWithBars — one bar, no signals (eval path fails silently)
# ---------------------------------------------------------------------------

class TestPollCycleWithBars:
    def _run_one_bar(self, **session_kwargs):
        svc, mocks = _make_service()
        session = _make_session(
            status=PaperTradingSessionStatus.RUNNING,
            last_processed_bar_timestamp=_ts(-1),
            **session_kwargs,
        )
        account = _make_account(session.session_id, session.user_id)
        bar = _make_bar(0)

        mocks["repository"].load.return_value = session
        mocks["ohlcv_service"].get_bars_since.return_value = [bar]
        mocks["bar_store"].list_bars.return_value = []
        mocks["bar_store"].append_bar.return_value = True
        mocks["order_store"].load_pending.return_value = []
        mocks["account_store"].load_by_session_id.return_value = account
        mocks["position_store"].list_open_positions.return_value = []

        with patch.object(svc, "_prepare_strategy", return_value=(MagicMock(), MagicMock(), 0, None)):
            with patch(f"{_SVC}.get_calendar", return_value=MagicMock()):
                with patch(f"{_SVC}.timeframe_to_timedelta", return_value=timedelta(days=1)):
                    with patch(f"{_SVC}._calendar_is_bar_expected", return_value=False):
                        with patch(f"{_SVC}.compute_tool_outputs_for_history", return_value=MagicMock()):
                            with patch(f"{_SVC}.build_bar_tool_outputs", return_value={}):
                                with patch(f"{_SVC}.emit_audit_event"):
                                    result = svc.run_cycle(
                                        session.session_id,
                                        session.user_id,
                                        MagicMock(),
                                        MagicMock(),
                                        now_utc=_ts(1),
                                    )
        return result, mocks

    def test_one_bar_processed_increments_counter(self):
        result, _ = self._run_one_bar()
        assert result.bars_processed == 1

    def test_bar_persisted_to_bar_store(self):
        result, mocks = self._run_one_bar()
        mocks["bar_store"].append_bar.assert_called()

    def test_cursor_advances_to_bar_timestamp(self):
        result, _ = self._run_one_bar()
        assert result.last_processed_bar_timestamp == _ts(0)

    def test_account_snapshot_appended_for_signal_eligible_bar(self):
        # warmup=0 → bar_index=0 is signal-eligible → snapshot appended
        result, mocks = self._run_one_bar()
        mocks["snapshot_store"].append.assert_called_once()
        assert result.account_snapshot_created is True

    def test_no_snapshot_for_warmup_bar(self):
        # warmup=5 → bar_index=0 is a warmup bar → no snapshot
        result, mocks = self._run_one_bar(
            simulation_assumptions=_make_assumptions(),  # won't matter; warmup comes from strategy
        )
        # With warmup_bars_required=5 (patched _prepare_strategy returns 5), bar_index=0 → warmup
        svc, mocks = _make_service()
        session = _make_session(
            status=PaperTradingSessionStatus.RUNNING,
            last_processed_bar_timestamp=_ts(-1),
        )
        account = _make_account(session.session_id, session.user_id)
        bar = _make_bar(0)

        mocks["repository"].load.return_value = session
        mocks["ohlcv_service"].get_bars_since.return_value = [bar]
        mocks["bar_store"].list_bars.return_value = []
        mocks["bar_store"].append_bar.return_value = True
        mocks["order_store"].load_pending.return_value = []
        mocks["account_store"].load_by_session_id.return_value = account
        mocks["position_store"].list_open_positions.return_value = []

        with patch.object(svc, "_prepare_strategy", return_value=(MagicMock(), MagicMock(), 5, None)):
            with patch(f"{_SVC}.get_calendar", return_value=MagicMock()):
                with patch(f"{_SVC}.timeframe_to_timedelta", return_value=timedelta(days=1)):
                    with patch(f"{_SVC}._calendar_is_bar_expected", return_value=False):
                        with patch(f"{_SVC}.compute_tool_outputs_for_history", return_value=MagicMock()):
                            with patch(f"{_SVC}.build_bar_tool_outputs", return_value={}):
                                with patch(f"{_SVC}.emit_audit_event"):
                                    result = svc.run_cycle(
                                        session.session_id,
                                        session.user_id,
                                        MagicMock(),
                                        MagicMock(),
                                        now_utc=_ts(1),
                                    )

        mocks["snapshot_store"].append.assert_not_called()
        assert result.account_snapshot_created is False


# ---------------------------------------------------------------------------
# TestProcessEntrySignal — _process_entry_signal unit tests
# ---------------------------------------------------------------------------

class TestProcessEntrySignal:
    def test_reject_when_max_positions_exceeded(self):
        svc, mocks = _make_service()
        assumptions = _make_assumptions(max_concurrent_positions=1)
        session = _make_session(simulation_assumptions=assumptions)
        account = _make_account(session.session_id, session.user_id)
        bar = _make_bar()

        mocks["position_store"].list_open_positions.return_value = []
        mocks["position_store"].count_open.return_value = 1  # already at max

        with patch(f"{_SVC}.emit_audit_event"):
            oc, rej, _, n_open, n_close = svc._process_entry_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        assert oc == 0
        assert rej == 1
        assert n_open == 0
        mocks["order_store"].mark_rejected.assert_called_once()

    def test_reject_when_insufficient_cash(self):
        svc, mocks = _make_service()
        # 10 units * 102 close ≈ 1020 required; we only have 5.0
        assumptions = _make_assumptions(position_size_value=10.0)
        session = _make_session(simulation_assumptions=assumptions)
        account = _make_account(session.session_id, session.user_id, cash=5.0)
        bar = _make_bar(close=102.0)

        mocks["position_store"].list_open_positions.return_value = []
        mocks["position_store"].count_open.return_value = 0

        with patch(f"{_SVC}.emit_audit_event"):
            oc, rej, _, n_open, _ = svc._process_entry_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        assert oc == 0
        assert rej == 1
        assert n_open == 0
        mocks["order_store"].mark_rejected.assert_called_once()

    def test_reject_when_quantity_resolves_to_zero(self):
        svc, mocks = _make_service()
        # FIXED_QUANTITY with 0.5 → int(0.5) = 0
        assumptions = _make_assumptions(position_size_value=0.5)
        session = _make_session(simulation_assumptions=assumptions)
        account = _make_account(session.session_id, session.user_id)
        bar = _make_bar()

        mocks["position_store"].list_open_positions.return_value = []
        mocks["position_store"].count_open.return_value = 0

        with patch(f"{_SVC}.emit_audit_event"):
            oc, rej, _, _, _ = svc._process_entry_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        assert oc == 0
        assert rej == 1

    def test_nbo_creates_pending_order_only(self):
        svc, mocks = _make_service()
        assumptions = _make_assumptions(fill_timing_model=FillTimingModel.NEXT_BAR_OPEN)
        session = _make_session(simulation_assumptions=assumptions)
        account = _make_account(session.session_id, session.user_id, cash=10_000.0)
        bar = _make_bar()

        mocks["position_store"].list_open_positions.return_value = []
        mocks["position_store"].count_open.return_value = 0

        with patch(f"{_SVC}.emit_audit_event"):
            oc, rej, _, n_open, n_close = svc._process_entry_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        assert oc == 1
        assert rej == 0
        assert n_open == 0  # fill deferred to next bar
        mocks["order_store"].save_pending.assert_called_once()
        mocks["fill_store"].append.assert_not_called()

    def test_sbc_fills_immediately_and_opens_position(self):
        svc, mocks = _make_service()
        assumptions = _make_assumptions(fill_timing_model=FillTimingModel.SIGNAL_BAR_CLOSE)
        session = _make_session(simulation_assumptions=assumptions)
        account = _make_account(session.session_id, session.user_id, cash=10_000.0)
        bar = _make_bar(close=100.0)

        mocks["position_store"].list_open_positions.return_value = []
        mocks["position_store"].count_open.return_value = 0

        with patch(f"{_SVC}.emit_audit_event"):
            oc, rej, _, n_open, n_close = svc._process_entry_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        assert oc == 1
        assert rej == 0
        assert n_open == 1
        mocks["fill_store"].append.assert_called_once()
        mocks["order_store"].mark_filled.assert_called_once()
        mocks["position_store"].save.assert_called_once()

    def test_sbc_entry_deducts_cash_from_account(self):
        svc, mocks = _make_service()
        assumptions = _make_assumptions(
            fill_timing_model=FillTimingModel.SIGNAL_BAR_CLOSE,
            position_size_value=10.0,
        )
        session = _make_session(simulation_assumptions=assumptions)
        account = _make_account(session.session_id, session.user_id, cash=5_000.0)
        bar = _make_bar(close=100.0)  # 10 * 100 = 1000 cash out

        mocks["position_store"].list_open_positions.return_value = []
        mocks["position_store"].count_open.return_value = 0

        with patch(f"{_SVC}.emit_audit_event"):
            _, _, updated_account, _, _ = svc._process_entry_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        # cash_out = net_value + fee = (10*100) + 0 = 1000
        assert updated_account.cash_balance == pytest.approx(4_000.0)

    # ── EXEC-2A: Duplicate long entry rejection ────────────────────────────

    def test_reject_when_open_position_exists_duplicate_long_entry(self):
        """BUY while an open position exists → DUPLICATE_LONG_ENTRY (matches backtest ALREADY_LONG)."""
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id)
        position = _make_position(session.session_id, session.user_id, session.account_id)
        bar = _make_bar()

        mocks["position_store"].list_open_positions.return_value = [position]

        with patch(f"{_SVC}.emit_audit_event"):
            oc, rej, _, n_open, n_close = svc._process_entry_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        assert oc == 0
        assert rej == 1
        assert n_open == 0
        mocks["order_store"].mark_rejected.assert_called_once()
        rejected_order = mocks["order_store"].mark_rejected.call_args.args[0]
        assert rejected_order.rejection_reason == RejectionReason.DUPLICATE_LONG_ENTRY.value

    def test_duplicate_long_entry_emits_audit_event(self):
        """DUPLICATE_LONG_ENTRY rejection must emit a PT_ORDER_REJECTED audit event."""
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id)
        position = _make_position(session.session_id, session.user_id, session.account_id)
        bar = _make_bar()

        mocks["position_store"].list_open_positions.return_value = [position]

        audit_calls = []
        with patch(f"{_SVC}.emit_audit_event", side_effect=audit_calls.append):
            svc._process_entry_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        assert len(audit_calls) == 1
        details = audit_calls[0].details
        assert details["rejection_reason"] == RejectionReason.DUPLICATE_LONG_ENTRY.value

    def test_duplicate_long_entry_no_fill_or_position_change(self):
        """DUPLICATE_LONG_ENTRY: no fill, no position change, no cash deducted."""
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id, cash=5_000.0)
        position = _make_position(session.session_id, session.user_id, session.account_id)
        bar = _make_bar()

        mocks["position_store"].list_open_positions.return_value = [position]

        with patch(f"{_SVC}.emit_audit_event"):
            oc, rej, returned_account, n_open, n_close = svc._process_entry_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        assert oc == 0
        assert rej == 1
        assert n_open == 0
        assert n_close == 0
        assert returned_account.cash_balance == pytest.approx(5_000.0)
        mocks["fill_store"].append.assert_not_called()
        mocks["position_store"].save.assert_not_called()
        mocks["position_store"].update.assert_not_called()

    def test_duplicate_guard_fires_before_max_positions_check(self):
        """DUPLICATE_LONG_ENTRY is checked before max_concurrent_positions guard."""
        svc, mocks = _make_service()
        assumptions = _make_assumptions(max_concurrent_positions=1)
        session = _make_session(simulation_assumptions=assumptions)
        account = _make_account(session.session_id, session.user_id)
        position = _make_position(session.session_id, session.user_id, session.account_id)
        bar = _make_bar()

        mocks["position_store"].list_open_positions.return_value = [position]
        mocks["position_store"].count_open.return_value = 1

        with patch(f"{_SVC}.emit_audit_event"):
            oc, rej, _, _, _ = svc._process_entry_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        # Must reject with DUPLICATE_LONG_ENTRY, not MAX_POSITIONS_EXCEEDED
        assert rej == 1
        rejected_order = mocks["order_store"].mark_rejected.call_args.args[0]
        assert rejected_order.rejection_reason == RejectionReason.DUPLICATE_LONG_ENTRY.value

    # ── EXEC-2A: Pending entry exists rejection ────────────────────────────

    def test_reject_when_pending_buy_exists(self):
        """BUY while a pending BUY order is unresolved → PENDING_ENTRY_EXISTS."""
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id)
        pending_buy = _make_pending_order(session, direction=OrderDirection.BUY)
        bar = _make_bar()

        mocks["position_store"].list_open_positions.return_value = []
        mocks["order_store"].load_pending.return_value = [pending_buy]

        with patch(f"{_SVC}.emit_audit_event"):
            oc, rej, _, n_open, n_close = svc._process_entry_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        assert oc == 0
        assert rej == 1
        assert n_open == 0
        mocks["order_store"].mark_rejected.assert_called_once()
        rejected_order = mocks["order_store"].mark_rejected.call_args.args[0]
        assert rejected_order.rejection_reason == RejectionReason.PENDING_ENTRY_EXISTS.value

    def test_pending_entry_exists_emits_audit_event(self):
        """PENDING_ENTRY_EXISTS rejection must emit a PT_ORDER_REJECTED audit event."""
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id)
        pending_buy = _make_pending_order(session, direction=OrderDirection.BUY)
        bar = _make_bar()

        mocks["position_store"].list_open_positions.return_value = []
        mocks["order_store"].load_pending.return_value = [pending_buy]

        audit_calls = []
        with patch(f"{_SVC}.emit_audit_event", side_effect=audit_calls.append):
            svc._process_entry_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        assert len(audit_calls) == 1
        details = audit_calls[0].details
        assert details["rejection_reason"] == RejectionReason.PENDING_ENTRY_EXISTS.value

    def test_pending_sell_does_not_block_new_buy(self):
        """A pending SELL order does NOT trigger PENDING_ENTRY_EXISTS for a new BUY."""
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id, cash=10_000.0)
        pending_sell = _make_pending_order(session, direction=OrderDirection.SELL)
        bar = _make_bar()

        mocks["position_store"].list_open_positions.return_value = []
        mocks["order_store"].load_pending.return_value = [pending_sell]
        mocks["position_store"].count_open.return_value = 0

        with patch(f"{_SVC}.emit_audit_event"):
            oc, rej, _, _, _ = svc._process_entry_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        # Pending SELL should not block a new BUY; entry proceeds normally
        assert oc == 1
        assert rej == 0

    def test_pending_buy_guard_fires_before_max_positions_check(self):
        """PENDING_ENTRY_EXISTS is checked before max_concurrent_positions guard."""
        svc, mocks = _make_service()
        assumptions = _make_assumptions(max_concurrent_positions=1)
        session = _make_session(simulation_assumptions=assumptions)
        account = _make_account(session.session_id, session.user_id)
        pending_buy = _make_pending_order(session, direction=OrderDirection.BUY)
        bar = _make_bar()

        mocks["position_store"].list_open_positions.return_value = []
        mocks["order_store"].load_pending.return_value = [pending_buy]
        mocks["position_store"].count_open.return_value = 1

        with patch(f"{_SVC}.emit_audit_event"):
            oc, rej, _, _, _ = svc._process_entry_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        assert rej == 1
        rejected_order = mocks["order_store"].mark_rejected.call_args.args[0]
        assert rejected_order.rejection_reason == RejectionReason.PENDING_ENTRY_EXISTS.value

    def test_normal_entry_unaffected_when_no_position_and_no_pending(self):
        """NBO entry still succeeds when no open position and no pending BUY."""
        svc, mocks = _make_service()
        assumptions = _make_assumptions(fill_timing_model=FillTimingModel.NEXT_BAR_OPEN)
        session = _make_session(simulation_assumptions=assumptions)
        account = _make_account(session.session_id, session.user_id, cash=10_000.0)
        bar = _make_bar()

        mocks["position_store"].list_open_positions.return_value = []
        mocks["order_store"].load_pending.return_value = []
        mocks["position_store"].count_open.return_value = 0

        with patch(f"{_SVC}.emit_audit_event"):
            oc, rej, _, n_open, _ = svc._process_entry_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        assert oc == 1
        assert rej == 0
        mocks["order_store"].save_pending.assert_called_once()


# ---------------------------------------------------------------------------
# TestProcessExitSignal — _process_exit_signal unit tests
# ---------------------------------------------------------------------------

class TestProcessExitSignal:
    def test_reject_when_no_open_position(self):
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id)
        bar = _make_bar()

        mocks["position_store"].list_open_positions.return_value = []

        with patch(f"{_SVC}.emit_audit_event"):
            oc, rej, _, _, _ = svc._process_exit_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        assert oc == 0
        assert rej == 1
        mocks["order_store"].mark_rejected.assert_called_once()

    def test_nbo_exit_creates_pending_order(self):
        svc, mocks = _make_service()
        assumptions = _make_assumptions(fill_timing_model=FillTimingModel.NEXT_BAR_OPEN)
        session = _make_session(simulation_assumptions=assumptions)
        account = _make_account(session.session_id, session.user_id)
        position = _make_position(session.session_id, session.user_id, session.account_id)
        bar = _make_bar()

        mocks["position_store"].list_open_positions.return_value = [position]

        with patch(f"{_SVC}.emit_audit_event"):
            oc, rej, _, n_open, n_close = svc._process_exit_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        assert oc == 1
        assert rej == 0
        assert n_close == 0  # deferred fill
        mocks["order_store"].save_pending.assert_called_once()
        mocks["fill_store"].append.assert_not_called()

    def test_sbc_exit_closes_position_immediately(self):
        svc, mocks = _make_service()
        assumptions = _make_assumptions(fill_timing_model=FillTimingModel.SIGNAL_BAR_CLOSE)
        session = _make_session(simulation_assumptions=assumptions)
        account = _make_account(session.session_id, session.user_id, cash=0.0)
        position = _make_position(session.session_id, session.user_id, session.account_id,
                                  quantity=10.0, entry_price=100.0, current_price=100.0)
        bar = _make_bar(close=110.0)

        mocks["position_store"].list_open_positions.return_value = [position]

        with patch(f"{_SVC}.emit_audit_event"):
            oc, rej, _, n_open, n_close = svc._process_exit_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        assert oc == 1
        assert rej == 0
        assert n_close == 1
        mocks["fill_store"].append.assert_called_once()
        mocks["order_store"].mark_filled.assert_called_once()

    def test_sbc_exit_adds_cash_to_account(self):
        svc, mocks = _make_service()
        assumptions = _make_assumptions(fill_timing_model=FillTimingModel.SIGNAL_BAR_CLOSE)
        session = _make_session(simulation_assumptions=assumptions)
        account = _make_account(session.session_id, session.user_id, cash=0.0)
        position = _make_position(session.session_id, session.user_id, session.account_id,
                                  quantity=10.0, entry_price=100.0, current_price=100.0)
        bar = _make_bar(close=110.0)  # 10 * 110 = 1100 cash in

        mocks["position_store"].list_open_positions.return_value = [position]

        with patch(f"{_SVC}.emit_audit_event"):
            _, _, updated_account, _, _ = svc._process_exit_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        assert updated_account.cash_balance == pytest.approx(1_100.0)

    # ── EXEC-2D: PENDING_EXIT_EXISTS guard ────────────────────────────────

    def test_reject_when_pending_sell_exists(self):
        """SELL while a pending SELL is already in the queue → PENDING_EXIT_EXISTS rejection."""
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id)
        position = _make_position(session.session_id, session.user_id, session.account_id)
        bar = _make_bar()
        pending_sell = _make_pending_order(session, direction=OrderDirection.SELL)

        mocks["position_store"].list_open_positions.return_value = [position]
        mocks["order_store"].load_pending.return_value = [pending_sell]

        with patch(f"{_SVC}.emit_audit_event"):
            oc, rej, _, n_open, n_close = svc._process_exit_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        assert oc == 0
        assert rej == 1
        assert n_close == 0
        mocks["order_store"].mark_rejected.assert_called_once()
        rejected_order = mocks["order_store"].mark_rejected.call_args.args[0]
        assert rejected_order.rejection_reason == RejectionReason.PENDING_EXIT_EXISTS.value

    def test_pending_exit_rejection_emits_audit_event(self):
        """PENDING_EXIT_EXISTS rejection must emit a PT_ORDER_REJECTED audit event."""
        from backend.core.audit import AuditEventKind

        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id)
        position = _make_position(session.session_id, session.user_id, session.account_id)
        bar = _make_bar()
        pending_sell = _make_pending_order(session, direction=OrderDirection.SELL)

        mocks["position_store"].list_open_positions.return_value = [position]
        mocks["order_store"].load_pending.return_value = [pending_sell]

        audit_calls = []
        with patch(f"{_SVC}.emit_audit_event", side_effect=audit_calls.append):
            svc._process_exit_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        assert len(audit_calls) == 1
        assert audit_calls[0].event_kind == AuditEventKind.PT_ORDER_REJECTED
        assert audit_calls[0].details["rejection_reason"] == RejectionReason.PENDING_EXIT_EXISTS.value
        assert "pending_order_id" in audit_calls[0].details

    def test_pending_buy_does_not_trigger_pending_exit_guard(self):
        """A pending BUY order must NOT trigger the PENDING_EXIT_EXISTS guard for a SELL signal."""
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id)
        position = _make_position(session.session_id, session.user_id, session.account_id)
        bar = _make_bar()
        pending_buy = _make_pending_order(session, direction=OrderDirection.BUY)

        mocks["position_store"].list_open_positions.return_value = [position]
        mocks["order_store"].load_pending.return_value = [pending_buy]

        with patch(f"{_SVC}.emit_audit_event"):
            oc, rej, _, _, _ = svc._process_exit_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        # Should NOT be rejected by PENDING_EXIT_EXISTS — pending BUY is irrelevant
        # (NBO creates pending order; actual assertion: order was created, not rejected by this guard)
        assert oc == 1
        assert rej == 0

    def test_no_pending_orders_allows_exit_to_proceed(self):
        """When no pending orders exist, exit proceeds normally (baseline check)."""
        svc, mocks = _make_service()
        assumptions = _make_assumptions(fill_timing_model=FillTimingModel.NEXT_BAR_OPEN)
        session = _make_session(simulation_assumptions=assumptions)
        account = _make_account(session.session_id, session.user_id)
        position = _make_position(session.session_id, session.user_id, session.account_id)
        bar = _make_bar()

        mocks["position_store"].list_open_positions.return_value = [position]
        mocks["order_store"].load_pending.return_value = []

        with patch(f"{_SVC}.emit_audit_event"):
            oc, rej, _, _, _ = svc._process_exit_signal(
                session=session, account=account, bar=bar, signal_id=_uid(), now_utc=_ts()
            )

        assert oc == 1
        assert rej == 0
        mocks["order_store"].save_pending.assert_called_once()

    def test_pending_exit_rejection_reason_value(self):
        """PENDING_EXIT_EXISTS has the expected string value."""
        assert RejectionReason.PENDING_EXIT_EXISTS.value == "pending_exit_exists"


# ---------------------------------------------------------------------------
# TestApplyBuyFill — _apply_buy_fill unit tests
# ---------------------------------------------------------------------------

class TestApplyBuyFill:
    def test_buy_opens_new_position(self):
        svc, mocks = _make_service()
        session = _make_session(status=PaperTradingSessionStatus.RUNNING)
        account = _make_account(session.session_id, session.user_id, cash=10_000.0)
        fill = _make_fill(session.session_id, session.user_id, session.account_id,
                          direction=OrderDirection.BUY, price=100.0, qty=10.0)

        mocks["position_store"].list_open_positions.return_value = []

        with patch(f"{_SVC}.emit_audit_event"):
            _, pos_event = svc._apply_buy_fill(session, account, fill, _ts(), None)

        assert pos_event == "opened"
        mocks["position_store"].save.assert_called_once()
        saved_pos = mocks["position_store"].save.call_args.args[0]
        assert saved_pos.is_open is True
        assert saved_pos.quantity == pytest.approx(10.0)
        assert saved_pos.average_entry_price == pytest.approx(100.0)

    def test_buy_deducts_cash_from_account(self):
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id, cash=10_000.0)
        fill = _make_fill(session.session_id, session.user_id, session.account_id,
                          direction=OrderDirection.BUY, price=100.0, qty=10.0, fee=5.0)
        # cash_out = net_value + fee = 1000 + 5 = 1005

        mocks["position_store"].list_open_positions.return_value = []

        with patch(f"{_SVC}.emit_audit_event"):
            updated_account, _ = svc._apply_buy_fill(session, account, fill, _ts(), None)

        assert updated_account.cash_balance == pytest.approx(8_995.0)

    def test_buy_scales_existing_position(self):
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id, cash=10_000.0)
        existing_pos = _make_position(
            session.session_id, session.user_id, session.account_id,
            quantity=10.0, entry_price=100.0, current_price=100.0,
        )
        fill = _make_fill(session.session_id, session.user_id, session.account_id,
                          direction=OrderDirection.BUY, price=110.0, qty=10.0)
        # avg = (10*100 + 10*110) / 20 = 105.0

        mocks["position_store"].list_open_positions.return_value = [existing_pos]

        with patch(f"{_SVC}.emit_audit_event"):
            _, pos_event = svc._apply_buy_fill(session, account, fill, _ts(), None)

        assert pos_event == "scaled"
        mocks["position_store"].update.assert_called_once()
        updated_pos = mocks["position_store"].update.call_args.args[0]
        assert updated_pos.average_entry_price == pytest.approx(105.0)
        assert updated_pos.quantity == pytest.approx(20.0)

    def test_buy_updates_fees_on_account(self):
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id, cash=10_000.0)
        fill = _make_fill(session.session_id, session.user_id, session.account_id,
                          direction=OrderDirection.BUY, price=100.0, qty=10.0, fee=2.50)

        mocks["position_store"].list_open_positions.return_value = []

        with patch(f"{_SVC}.emit_audit_event"):
            updated_account, _ = svc._apply_buy_fill(session, account, fill, _ts(), None)

        assert updated_account.total_fees_paid == pytest.approx(2.50)

    def test_buy_position_uses_correct_symbol(self):
        svc, mocks = _make_service()
        session = _make_session(symbol="MSFT")
        account = _make_account(session.session_id, session.user_id, cash=10_000.0)
        fill = _make_fill(session.session_id, session.user_id, session.account_id,
                          direction=OrderDirection.BUY, price=200.0, qty=5.0)
        # Override fill symbol — it's already validated as "AAPL" in _make_fill;
        # since session.symbol = "MSFT", the service creates the position with session.symbol
        # We test symbol from the new position:

        mocks["position_store"].list_open_positions.return_value = []

        with patch(f"{_SVC}.emit_audit_event"):
            svc._apply_buy_fill(session, account, fill, _ts(), None)

        saved_pos = mocks["position_store"].save.call_args.args[0]
        assert saved_pos.symbol == "MSFT"


# ---------------------------------------------------------------------------
# TestApplySellFill — _apply_sell_fill unit tests
# ---------------------------------------------------------------------------

class TestApplySellFill:
    def test_sell_closes_position_fully(self):
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id, cash=0.0)
        position = _make_position(session.session_id, session.user_id, session.account_id,
                                  quantity=10.0, entry_price=100.0)
        fill = _make_fill(session.session_id, session.user_id, session.account_id,
                          direction=OrderDirection.SELL, price=110.0, qty=10.0)

        mocks["position_store"].list_open_positions.return_value = [position]

        with patch(f"{_SVC}.emit_audit_event"):
            _, pos_event = svc._apply_sell_fill(session, account, fill, _ts(), None)

        assert pos_event == "closed"
        mocks["position_store"].update.assert_called_once()
        closed_pos = mocks["position_store"].update.call_args.args[0]
        assert closed_pos.is_open is False
        assert closed_pos.quantity == pytest.approx(0.0)

    def test_sell_adds_cash_to_account(self):
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id, cash=0.0)
        position = _make_position(session.session_id, session.user_id, session.account_id,
                                  quantity=10.0, entry_price=100.0)
        fill = _make_fill(session.session_id, session.user_id, session.account_id,
                          direction=OrderDirection.SELL, price=110.0, qty=10.0)
        # cash_in = net_value - fee = 1100 - 0 = 1100

        mocks["position_store"].list_open_positions.return_value = [position]

        with patch(f"{_SVC}.emit_audit_event"):
            updated_account, _ = svc._apply_sell_fill(session, account, fill, _ts(), None)

        assert updated_account.cash_balance == pytest.approx(1_100.0)

    def test_sell_realizes_pnl(self):
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id, cash=0.0)
        position = _make_position(session.session_id, session.user_id, session.account_id,
                                  quantity=10.0, entry_price=100.0)
        fill = _make_fill(session.session_id, session.user_id, session.account_id,
                          direction=OrderDirection.SELL, price=110.0, qty=10.0)
        # realized_pnl = (110 - 100) * 10 = 100

        mocks["position_store"].list_open_positions.return_value = [position]

        with patch(f"{_SVC}.emit_audit_event"):
            updated_account, _ = svc._apply_sell_fill(session, account, fill, _ts(), None)

        assert updated_account.total_realized_pnl == pytest.approx(100.0)

    def test_partial_sell_reduces_position(self):
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id, cash=0.0)
        position = _make_position(session.session_id, session.user_id, session.account_id,
                                  quantity=10.0, entry_price=100.0)
        fill = _make_fill(session.session_id, session.user_id, session.account_id,
                          direction=OrderDirection.SELL, price=110.0, qty=5.0)

        mocks["position_store"].list_open_positions.return_value = [position]

        with patch(f"{_SVC}.emit_audit_event"):
            _, pos_event = svc._apply_sell_fill(session, account, fill, _ts(), None)

        assert pos_event == "reduced"
        updated_pos = mocks["position_store"].update.call_args.args[0]
        assert updated_pos.quantity == pytest.approx(5.0)
        assert updated_pos.is_open is True

    def test_sell_with_no_position_returns_unchanged_account(self):
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id, cash=5_000.0)
        fill = _make_fill(session.session_id, session.user_id, session.account_id,
                          direction=OrderDirection.SELL, price=100.0, qty=10.0)

        mocks["position_store"].list_open_positions.return_value = []

        with patch(f"{_SVC}.emit_audit_event"):
            returned_account, pos_event = svc._apply_sell_fill(session, account, fill, _ts(), None)

        assert pos_event is None
        assert returned_account.cash_balance == pytest.approx(5_000.0)


# ---------------------------------------------------------------------------
# TestMarkToMarket — _mark_to_market unit tests
# ---------------------------------------------------------------------------

class TestMarkToMarket:
    def test_updates_position_current_price(self):
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id, cash=5_000.0)
        position = _make_position(session.session_id, session.user_id, session.account_id,
                                  quantity=10.0, entry_price=100.0, current_price=100.0)
        mocks["position_store"].list_open_positions.return_value = [position]

        svc._mark_to_market(session.session_id, account, 115.0, _ts())

        updated_pos = mocks["position_store"].update.call_args.args[0]
        assert updated_pos.current_price == pytest.approx(115.0)
        assert updated_pos.market_value == pytest.approx(10.0 * 115.0)
        assert updated_pos.unrealized_pnl == pytest.approx((115.0 - 100.0) * 10.0)

    def test_equity_equals_cash_plus_market_value(self):
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id, cash=5_000.0)
        position = _make_position(session.session_id, session.user_id, session.account_id,
                                  quantity=10.0, current_price=100.0)
        mocks["position_store"].list_open_positions.return_value = [position]

        updated_account = svc._mark_to_market(session.session_id, account, 120.0, _ts())

        # equity = 5000 + 10*120 = 6200
        assert updated_account.equity == pytest.approx(6_200.0)

    def test_no_positions_equity_equals_cash(self):
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id, cash=10_000.0)
        mocks["position_store"].list_open_positions.return_value = []

        updated_account = svc._mark_to_market(session.session_id, account, 100.0, _ts())

        assert updated_account.equity == pytest.approx(10_000.0)
        mocks["position_store"].update.assert_not_called()


# ---------------------------------------------------------------------------
# TestResolvePendingOrder — _resolve_pending_order unit tests
# ---------------------------------------------------------------------------

class TestResolvePendingOrder:
    def test_buy_pending_resolved_as_filled(self):
        svc, mocks = _make_service()
        session = _make_session(status=PaperTradingSessionStatus.RUNNING)
        account = _make_account(session.session_id, session.user_id, cash=10_000.0)
        order = _make_pending_order(session, direction=OrderDirection.BUY, qty=10.0)

        mocks["position_store"].list_open_positions.return_value = []

        with patch(f"{_SVC}.emit_audit_event"):
            result, updated_acct, _, pos_event = svc._resolve_pending_order(
                session=session,
                account=account,
                pending_order=order,
                bar_open=100.0,
                bar_timestamp=_ts(1),
                now_utc=_ts(1),
            )

        assert result == "filled"
        assert pos_event == "opened"
        mocks["fill_store"].append.assert_called_once()
        mocks["order_store"].mark_filled.assert_called_once()

    def test_buy_cancelled_when_insufficient_cash_at_fill(self):
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id, cash=1.0)  # tiny cash
        order = _make_pending_order(session, direction=OrderDirection.BUY, qty=10.0)
        # cost = 10 * 100 = 1000 >> 1.0

        with patch(f"{_SVC}.emit_audit_event"):
            result, _, _, _ = svc._resolve_pending_order(
                session=session,
                account=account,
                pending_order=order,
                bar_open=100.0,
                bar_timestamp=_ts(1),
                now_utc=_ts(1),
            )

        assert result == "cancelled"
        mocks["order_store"].mark_cancelled.assert_called_once()
        mocks["fill_store"].append.assert_not_called()

    def test_sell_cancelled_when_no_open_position(self):
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id)
        order = _make_pending_order(session, direction=OrderDirection.SELL, qty=10.0)

        mocks["position_store"].list_open_positions.return_value = []

        with patch(f"{_SVC}.emit_audit_event"):
            result, _, _, _ = svc._resolve_pending_order(
                session=session,
                account=account,
                pending_order=order,
                bar_open=100.0,
                bar_timestamp=_ts(1),
                now_utc=_ts(1),
            )

        assert result == "cancelled"
        mocks["order_store"].mark_cancelled.assert_called_once()

    def test_sell_pending_resolved_as_filled_when_position_exists(self):
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id, cash=0.0)
        position = _make_position(session.session_id, session.user_id, session.account_id,
                                  quantity=10.0, entry_price=100.0)
        order = _make_pending_order(session, direction=OrderDirection.SELL, qty=10.0)

        mocks["position_store"].list_open_positions.return_value = [position]

        with patch(f"{_SVC}.emit_audit_event"):
            result, _, _, pos_event = svc._resolve_pending_order(
                session=session,
                account=account,
                pending_order=order,
                bar_open=105.0,
                bar_timestamp=_ts(1),
                now_utc=_ts(1),
            )

        assert result == "filled"
        assert pos_event == "closed"

    def test_correlation_id_present_in_audit_on_fill(self):
        svc, mocks = _make_service()
        session = _make_session()
        account = _make_account(session.session_id, session.user_id, cash=10_000.0)
        order = _make_pending_order(session, direction=OrderDirection.BUY, qty=10.0)

        mocks["position_store"].list_open_positions.return_value = []
        audit_calls = []

        with patch(f"{_SVC}.emit_audit_event", side_effect=audit_calls.append):
            svc._resolve_pending_order(
                session=session,
                account=account,
                pending_order=order,
                bar_open=100.0,
                bar_timestamp=_ts(1),
                now_utc=_ts(1),
            )

        fill_events = [e for e in audit_calls if "fill" in e.event_kind.value.lower()]
        assert all(e.correlation_id is not None for e in fill_events)


# ---------------------------------------------------------------------------
# TestDrawdownStop
# ---------------------------------------------------------------------------

class TestDrawdownStop:
    def _run_with_drawdown(self, drawdown_pct: float, threshold: float):
        svc, mocks = _make_service()
        assumptions = _make_assumptions(max_drawdown_stop_pct=threshold)
        session = _make_session(
            status=PaperTradingSessionStatus.RUNNING,
            simulation_assumptions=assumptions,
            last_processed_bar_timestamp=_ts(-1),
        )
        account = _make_account(session.session_id, session.user_id)
        account_with_dd = account.model_copy(update={
            "current_drawdown_pct": drawdown_pct,
            "equity": max(0.0, account.equity * (1 - drawdown_pct / 100)),
        })
        bar = _make_bar(0)

        mocks["repository"].load.return_value = session
        mocks["ohlcv_service"].get_bars_since.return_value = [bar]
        mocks["bar_store"].list_bars.return_value = []
        mocks["bar_store"].append_bar.return_value = True
        mocks["order_store"].load_pending.return_value = []
        mocks["account_store"].load_by_session_id.return_value = account

        with patch.object(svc, "_prepare_strategy", return_value=(MagicMock(), MagicMock(), 0, None)):
            with patch.object(svc, "_mark_to_market", return_value=account_with_dd):
                with patch(f"{_SVC}.get_calendar", return_value=MagicMock()):
                    with patch(f"{_SVC}.timeframe_to_timedelta", return_value=timedelta(days=1)):
                        with patch(f"{_SVC}._calendar_is_bar_expected", return_value=False):
                            with patch(f"{_SVC}.compute_tool_outputs_for_history", return_value=MagicMock()):
                                with patch(f"{_SVC}.build_bar_tool_outputs", return_value={}):
                                    with patch(f"{_SVC}.emit_audit_event"):
                                        result = svc.run_cycle(
                                            session.session_id,
                                            session.user_id,
                                            MagicMock(),
                                            MagicMock(),
                                            now_utc=_ts(1),
                                        )
        return result, mocks

    def test_drawdown_stop_triggers_when_threshold_exceeded(self):
        result, _ = self._run_with_drawdown(drawdown_pct=25.0, threshold=20.0)
        assert result.drawdown_stop_triggered is True

    def test_drawdown_stop_pauses_session(self):
        result, mocks = self._run_with_drawdown(drawdown_pct=25.0, threshold=20.0)
        assert result.status == "paused"
        mocks["repository"].update.assert_called()
        last_update = mocks["repository"].update.call_args_list[-1].args[0]
        assert last_update.status == PaperTradingSessionStatus.PAUSED

    def test_no_drawdown_stop_when_threshold_not_set(self):
        result, _ = self._run_with_drawdown(drawdown_pct=50.0, threshold=100.0)
        # 50 < 100, so no stop
        assert result.drawdown_stop_triggered is False


# ---------------------------------------------------------------------------
# TestComputeDrawdown — module helper
# ---------------------------------------------------------------------------

class TestComputeDrawdown:
    def test_zero_peak_returns_zero(self):
        assert _compute_drawdown(1_000.0, 0.0) == 0.0

    def test_equity_equals_peak_returns_zero(self):
        assert _compute_drawdown(10_000.0, 10_000.0) == pytest.approx(0.0)

    def test_drawdown_computed_correctly(self):
        # (10000 - 8000) / 10000 * 100 = 20.0
        assert _compute_drawdown(8_000.0, 10_000.0) == pytest.approx(20.0)

    def test_equity_above_peak_clamped_to_zero(self):
        assert _compute_drawdown(12_000.0, 10_000.0) == 0.0

    def test_equity_zero_returns_100(self):
        assert _compute_drawdown(0.0, 10_000.0) == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# TestGetTriggeredRuleId — module helper
# ---------------------------------------------------------------------------

class TestGetTriggeredRuleId:
    def test_returns_rule_id_from_first_matching_triggered_rule(self):
        rule_result = MagicMock()
        rule_result.kind = "entry"
        rule_result.triggered = True
        rule_result.rule_id = "rule_ema_cross"

        trace = MagicMock()
        trace.rule_results = [rule_result]
        bar_result = MagicMock()
        bar_result.trace = trace

        assert _get_triggered_rule_id(bar_result, "entry") == "rule_ema_cross"

    def test_returns_kind_as_fallback_when_no_match(self):
        bar_result = MagicMock()
        bar_result.trace = None

        assert _get_triggered_rule_id(bar_result, "exit") == "exit"

    def test_skips_non_triggered_rules(self):
        rule_not_triggered = MagicMock()
        rule_not_triggered.kind = "entry"
        rule_not_triggered.triggered = False

        trace = MagicMock()
        trace.rule_results = [rule_not_triggered]
        bar_result = MagicMock()
        bar_result.trace = trace

        # No triggered rule → falls back to kind
        assert _get_triggered_rule_id(bar_result, "entry") == "entry"
