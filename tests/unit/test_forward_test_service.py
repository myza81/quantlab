"""
Phase 4C.4 — ForwardTestService tests.

Coverage:
- PENDING session activation: warmup fetch, transition to RUNNING, cursor set
- PENDING with zero warmup: cursor defaults to activation_timestamp
- PENDING provider failure: activation still completes
- RUNNING poll cycle: get_bars_since, evaluate, signal generation
- RUNNING with no new bars: no-op, cursor unchanged
- RUNNING entry signal generation + FT_SIGNAL_GENERATED audit
- RUNNING exit signal generation
- RUNNING duplicate signal suppression + FT_SIGNAL_SUPPRESSED audit
- RUNNING gap detection + FT_GAP_DETECTED audit
- RUNNING provider failure: handled gracefully
- RUNNING cursor advancement after successful cycle
- RUNNING session counter updates
- Terminal session guard (COMPLETED, FAILED, TERMINATED) → no-op
- PAUSED session guard → no-op
- Strategy deserialization failure → provider_failure=True
- No semantics in snapshot → provider_failure=True
- Compilation failure → provider_failure=True
- Warmup bars flagged is_warmup_bar=True
- Signal-eligible bars not flagged as warmup
- Ownership enforcement: repository.load with owner_id
- CycleResult fields for activation
- CycleResult fields for poll
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from unittest.mock import ANY, MagicMock, call, patch

import pytest

from backend.data.models.dataset import DatasetIdentity
from backend.data.models.instrument import Instrument
from backend.data.schemas import NormalizedOHLCV
from backend.forward_testing.exceptions import ForwardTestSessionNotFoundError
from backend.forward_testing.models import (
    ForwardTestBar,
    ForwardTestSession,
    ForwardTestSessionStatus,
    StrategySnapshot,
)
from backend.forward_testing.repository import ForwardTestRepository
from backend.forward_testing.service import CycleResult, ForwardTestService
from backend.forward_testing.stores import ForwardTestBarStore, ForwardTestSignalStore
from backend.services.ohlcv_service import OHLCVService
from backend.strategy_registry.drafts import StrategyDraft
from backend.strategy_registry.semantics import (
    Condition,
    ConditionGroup,
    ConditionOperator,
    EntryRule,
    ExitRule,
    LogicalOperator,
    OperandKind,
    OperandReference,
    StrategySemantics,
)
from backend.tools.registry import ToolRegistry
from backend.tools.toolset import StrategyToolSet

_UTC = timezone.utc
_NOW = datetime(2026, 5, 30, 10, 0, 0, tzinfo=_UTC)  # Saturday — for reference

# Finalized daily bar timestamps (all well before _NOW to pass finalization check)
_T1 = datetime(2026, 5, 29, 0, 0, 0, tzinfo=_UTC)  # Friday
_T2 = datetime(2026, 5, 28, 0, 0, 0, tzinfo=_UTC)  # Thursday
_T3 = datetime(2026, 5, 27, 0, 0, 0, tzinfo=_UTC)  # Wednesday
_T_WARMUP_LAST = datetime(2026, 5, 26, 0, 0, 0, tzinfo=_UTC)  # Tuesday (last warmup)

_DRAFT_ID   = str(uuid.uuid4())
_SESSION_ID = str(uuid.uuid4())
_USER_ID    = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Helpers — semantic factories
# ---------------------------------------------------------------------------

def _close_gt_zero() -> Condition:
    """Condition that evaluates True for any bar with close > 0."""
    return Condition(
        left=OperandReference(kind=OperandKind.PRICE, ref="close"),
        operator=ConditionOperator.GT,
        right=OperandReference(kind=OperandKind.CONSTANT, ref="0"),
    )


def _close_lt_zero() -> Condition:
    """Condition that evaluates False for positive close prices."""
    return Condition(
        left=OperandReference(kind=OperandKind.PRICE, ref="close"),
        operator=ConditionOperator.LT,
        right=OperandReference(kind=OperandKind.CONSTANT, ref="0"),
    )


def _always_entry_semantics() -> StrategySemantics:
    return StrategySemantics(
        entry_rules=(
            EntryRule(
                rule_id="entry_1",
                condition_group=ConditionGroup(
                    operator=LogicalOperator.AND,
                    conditions=(_close_gt_zero(),),
                ),
            ),
        ),
        exit_rules=(),
    )


def _always_exit_semantics() -> StrategySemantics:
    return StrategySemantics(
        entry_rules=(),
        exit_rules=(
            ExitRule(
                rule_id="exit_1",
                condition_group=ConditionGroup(
                    operator=LogicalOperator.AND,
                    conditions=(_close_gt_zero(),),
                ),
            ),
        ),
    )


def _no_trigger_semantics() -> StrategySemantics:
    return StrategySemantics(
        entry_rules=(
            EntryRule(
                rule_id="entry_never",
                condition_group=ConditionGroup(
                    operator=LogicalOperator.AND,
                    conditions=(_close_lt_zero(),),
                ),
            ),
        ),
        exit_rules=(),
    )


def _empty_semantics() -> StrategySemantics:
    return StrategySemantics(entry_rules=(), exit_rules=())


# ---------------------------------------------------------------------------
# Helpers — domain object builders
# ---------------------------------------------------------------------------

def _build_draft(semantics: StrategySemantics | None = None) -> StrategyDraft:
    return StrategyDraft(
        draft_id=_DRAFT_ID,
        display_name="Test Strategy",
        toolset=StrategyToolSet(toolset_id="test_ts", tools=()),
        created_at=_NOW,
        updated_at=_NOW,
        semantics=semantics,
    )


def _build_snapshot(draft: StrategyDraft) -> StrategySnapshot:
    strategy_json = draft.model_dump_json()
    return StrategySnapshot(
        draft_id=draft.draft_id,
        display_name=draft.display_name,
        lifecycle_status="draft",
        snapshot_hash=hashlib.sha256(strategy_json.encode()).hexdigest(),
        captured_at=_NOW,
        strategy_json=strategy_json,
    )


def _build_session(
    status: ForwardTestSessionStatus = ForwardTestSessionStatus.PENDING,
    warmup_bars_required: int = 3,
    semantics: StrategySemantics | None = None,
    last_processed_bar_timestamp: datetime | None = None,
    activation_timestamp: datetime | None = None,
    bars_evaluated: int = 0,
    warmup_bars_processed: int = 0,
    signal_eligible_bars_processed: int = 0,
    signals_recorded: int = 0,
) -> ForwardTestSession:
    draft = _build_draft(semantics or _always_entry_semantics())
    snapshot = _build_snapshot(draft)
    return ForwardTestSession(
        session_id=_SESSION_ID,
        user_id=_USER_ID,
        draft_id=_DRAFT_ID,
        strategy_snapshot=snapshot,
        lifecycle_status_at_activation="draft",
        source_mode="provider",
        provider_name="yahoo",
        symbol="AAPL",
        timeframe="1d",
        warmup_bars_required=warmup_bars_required,
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
        activation_timestamp=activation_timestamp,
        last_processed_bar_timestamp=last_processed_bar_timestamp,
        bars_evaluated=bars_evaluated,
        warmup_bars_processed=warmup_bars_processed,
        signal_eligible_bars_processed=signal_eligible_bars_processed,
        signals_recorded=signals_recorded,
    )


def _build_ohlcv(timestamp: datetime, close: float = 150.0) -> NormalizedOHLCV:
    return NormalizedOHLCV(
        timestamp=timestamp,
        symbol="AAPL",
        asset_class="equity",
        venue="NASDAQ",
        timeframe="1d",
        source="yahoo",
        open=148.0,
        high=152.0,
        low=147.0,
        close=close,
        volume=1_000_000.0,
    )


def _make_identity() -> DatasetIdentity:
    return DatasetIdentity(
        instrument=Instrument(symbol="AAPL", asset_class="equity", exchange="NASDAQ"),
        provider="yahoo",
        timeframe="1d",
    )


def _make_service(
    repo: ForwardTestRepository | None = None,
    signal_store: ForwardTestSignalStore | None = None,
    bar_store: ForwardTestBarStore | None = None,
    ohlcv_service: OHLCVService | None = None,
    tool_registry: ToolRegistry | None = None,
) -> ForwardTestService:
    return ForwardTestService(
        repository=repo or MagicMock(spec=ForwardTestRepository),
        signal_store=signal_store or MagicMock(spec=ForwardTestSignalStore),
        bar_store=bar_store or MagicMock(spec=ForwardTestBarStore),
        ohlcv_service=ohlcv_service or MagicMock(spec=OHLCVService),
        tool_registry=tool_registry or MagicMock(spec=ToolRegistry),
    )


def _mock_repo(session: ForwardTestSession) -> MagicMock:
    repo = MagicMock(spec=ForwardTestRepository)
    repo.load.return_value = session
    return repo


def _mock_bar_store(
    stored_bars: list[ForwardTestBar] | None = None,
    count: int | None = None,
) -> MagicMock:
    store = MagicMock(spec=ForwardTestBarStore)
    bars = stored_bars or []
    store.list_bars.return_value = bars
    store.count_bars.return_value = count if count is not None else len(bars)
    store.append_bar.return_value = True
    return store


def _build_stored_bar(bar_index: int, timestamp: datetime) -> ForwardTestBar:
    return ForwardTestBar(
        session_id=_SESSION_ID,
        bar_index=bar_index,
        bar_timestamp=timestamp,
        open=148.0,
        high=152.0,
        low=147.0,
        close=150.0,
        volume=1_000_000.0,
        source_mode="provider",
        provider_name="yahoo",
        catalog_id=None,
        is_warmup_bar=True,
        processed_at=_NOW,
    )


# ============================================================================
# PENDING activation
# ============================================================================

class TestActivation:
    """ForwardTestService: PENDING → RUNNING activation."""

    def test_pending_session_transitions_to_running(self):
        """Activation transitions session status to RUNNING."""
        session = _build_session(status=ForwardTestSessionStatus.PENDING, warmup_bars_required=1)
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_recent_bars.return_value = [_build_ohlcv(_T1)]
        bar_store = _mock_bar_store()
        svc = _make_service(repo=repo, bar_store=bar_store, ohlcv_service=ohlcv)

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.activated is True
        assert result.status == ForwardTestSessionStatus.RUNNING.value

    def test_activation_updates_session_in_repository(self):
        """Repository.update is called with status=RUNNING."""
        session = _build_session(status=ForwardTestSessionStatus.PENDING, warmup_bars_required=1)
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_recent_bars.return_value = [_build_ohlcv(_T1)]
        bar_store = _mock_bar_store()
        svc = _make_service(repo=repo, bar_store=bar_store, ohlcv_service=ohlcv)

        svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        repo.update.assert_called_once()
        updated_session = repo.update.call_args[0][0]
        assert updated_session.status == ForwardTestSessionStatus.RUNNING

    def test_activation_warmup_bars_stored(self):
        """Warmup bars are stored in the bar store with is_warmup_bar=True."""
        warmup_bar = _build_ohlcv(_T1)
        session = _build_session(status=ForwardTestSessionStatus.PENDING, warmup_bars_required=1)
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_recent_bars.return_value = [warmup_bar]
        bar_store = _mock_bar_store()
        svc = _make_service(repo=repo, bar_store=bar_store, ohlcv_service=ohlcv)

        svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        bar_store.append_bar.assert_called_once()
        stored = bar_store.append_bar.call_args[0][0]
        assert stored.is_warmup_bar is True
        assert stored.bar_timestamp == _T1

    def test_activation_sets_cursor_to_last_warmup_bar(self):
        """Cursor (last_processed_bar_timestamp) is set to last warmup bar timestamp."""
        bars = [_build_ohlcv(_T3), _build_ohlcv(_T2), _build_ohlcv(_T1)]
        session = _build_session(status=ForwardTestSessionStatus.PENDING, warmup_bars_required=3)
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_recent_bars.return_value = bars
        bar_store = _mock_bar_store()
        svc = _make_service(repo=repo, bar_store=bar_store, ohlcv_service=ohlcv)

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.last_processed_bar_timestamp == _T1
        updated_session = repo.update.call_args[0][0]
        assert updated_session.last_processed_bar_timestamp == _T1

    def test_activation_with_zero_warmup_cursor_is_now_utc(self):
        """Zero warmup: cursor defaults to activation time (now_utc)."""
        session = _build_session(status=ForwardTestSessionStatus.PENDING, warmup_bars_required=0)
        repo = _mock_repo(session)
        bar_store = _mock_bar_store()
        svc = _make_service(repo=repo, bar_store=bar_store)

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.activated is True
        assert result.last_processed_bar_timestamp == _NOW

    def test_activation_with_zero_warmup_does_not_call_get_recent_bars(self):
        """Zero warmup: OHLCVService.get_recent_bars is not called."""
        session = _build_session(status=ForwardTestSessionStatus.PENDING, warmup_bars_required=0)
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        bar_store = _mock_bar_store()
        svc = _make_service(repo=repo, bar_store=bar_store, ohlcv_service=ohlcv)

        svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        ohlcv.get_recent_bars.assert_not_called()

    def test_activation_sets_activation_timestamp(self):
        """Activation sets activation_timestamp to now_utc in the updated session."""
        session = _build_session(status=ForwardTestSessionStatus.PENDING, warmup_bars_required=0)
        repo = _mock_repo(session)
        bar_store = _mock_bar_store()
        svc = _make_service(repo=repo, bar_store=bar_store)

        svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        updated = repo.update.call_args[0][0]
        assert updated.activation_timestamp == _NOW

    def test_activation_provider_failure_still_completes(self):
        """Provider failure during warmup fetch: session still activates."""
        session = _build_session(status=ForwardTestSessionStatus.PENDING, warmup_bars_required=3)
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_recent_bars.side_effect = ConnectionError("provider unavailable")
        bar_store = _mock_bar_store()
        svc = _make_service(repo=repo, bar_store=bar_store, ohlcv_service=ohlcv)

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.activated is True
        assert result.provider_failure is True
        assert result.bars_fetched == 0
        assert result.status == ForwardTestSessionStatus.RUNNING.value

    def test_activation_cycle_result_fields(self):
        """CycleResult fields are correct after activation with warmup bars."""
        bars = [_build_ohlcv(_T3), _build_ohlcv(_T2), _build_ohlcv(_T1)]
        session = _build_session(status=ForwardTestSessionStatus.PENDING, warmup_bars_required=3)
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_recent_bars.return_value = bars
        bar_store = _mock_bar_store()
        svc = _make_service(repo=repo, bar_store=bar_store, ohlcv_service=ohlcv)

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.activated is True
        assert result.bars_fetched == 3
        assert result.bars_processed == 3
        assert result.warmup_bars_processed == 3
        assert result.signal_eligible_bars_processed == 0
        assert result.signals_generated == 0
        assert result.gap_detected is False
        assert result.provider_failure is False

    def test_activation_emits_ft_session_activated(self):
        """FT_SESSION_ACTIVATED audit event is emitted on activation."""
        session = _build_session(status=ForwardTestSessionStatus.PENDING, warmup_bars_required=1)
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_recent_bars.return_value = [_build_ohlcv(_T1)]
        bar_store = _mock_bar_store()
        svc = _make_service(repo=repo, bar_store=bar_store, ohlcv_service=ohlcv)

        with patch("backend.forward_testing.service.emit_audit_event") as mock_emit:
            svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        emitted_kinds = [c.args[0].event_kind.value for c in mock_emit.call_args_list]
        assert "ft_session_activated" in emitted_kinds

    def test_activation_uses_owner_id_for_repository_update(self):
        """Repository.update is called with the correct owner_id."""
        session = _build_session(status=ForwardTestSessionStatus.PENDING, warmup_bars_required=0)
        repo = _mock_repo(session)
        bar_store = _mock_bar_store()
        svc = _make_service(repo=repo, bar_store=bar_store)

        svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        repo.update.assert_called_once()
        update_kwargs = repo.update.call_args[1]
        assert update_kwargs["owner_id"] == _USER_ID


# ============================================================================
# RUNNING poll cycle
# ============================================================================

class TestPollCycle:
    """ForwardTestService: RUNNING session poll cycle."""

    def test_no_new_bars_returns_zero_counts(self):
        """No new bars: cycle result has all-zero counts."""
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T1,
            activation_timestamp=_NOW,
            warmup_bars_required=0,
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_bars_since.return_value = []
        svc = _make_service(repo=repo, ohlcv_service=ohlcv)

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.bars_fetched == 0
        assert result.bars_processed == 0
        assert result.signals_generated == 0
        assert result.activated is False

    def test_no_new_bars_cursor_unchanged(self):
        """No new bars: session last_processed_bar_timestamp is not advanced."""
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T1,
            activation_timestamp=_NOW,
            warmup_bars_required=0,
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_bars_since.return_value = []
        svc = _make_service(repo=repo, ohlcv_service=ohlcv)

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.last_processed_bar_timestamp == _T1

    def test_new_bars_processed_and_stored(self):
        """New bars: bar_store.append_bar called for each new bar."""
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T2,
            activation_timestamp=_NOW,
            warmup_bars_required=0,
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_bars_since.return_value = [_build_ohlcv(_T1)]
        bar_store = _mock_bar_store()
        svc = _make_service(repo=repo, bar_store=bar_store, ohlcv_service=ohlcv)

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.bars_fetched == 1
        assert result.bars_processed == 1
        bar_store.append_bar.assert_called_once()

    def test_entry_signal_generated_when_triggered(self):
        """Entry triggered: ForwardTestSignal with direction=entry_long is created."""
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T2,
            activation_timestamp=_NOW,
            warmup_bars_required=0,
            semantics=_always_entry_semantics(),
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_bars_since.return_value = [_build_ohlcv(_T1, close=150.0)]
        bar_store = _mock_bar_store()
        signal_store = MagicMock(spec=ForwardTestSignalStore)
        signal_store.append_signal.return_value = True
        svc = _make_service(
            repo=repo, bar_store=bar_store, signal_store=signal_store,
            ohlcv_service=ohlcv,
        )

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.signals_generated == 1
        signal_store.append_signal.assert_called_once()
        created_signal = signal_store.append_signal.call_args[0][0]
        assert created_signal.signal_direction == "entry_long"
        assert created_signal.warmup_satisfied is True

    def test_exit_signal_generated_when_triggered(self):
        """Exit triggered: ForwardTestSignal with direction=exit_long is created."""
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T2,
            activation_timestamp=_NOW,
            warmup_bars_required=0,
            semantics=_always_exit_semantics(),
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_bars_since.return_value = [_build_ohlcv(_T1, close=150.0)]
        bar_store = _mock_bar_store()
        signal_store = MagicMock(spec=ForwardTestSignalStore)
        signal_store.append_signal.return_value = True
        svc = _make_service(
            repo=repo, bar_store=bar_store, signal_store=signal_store,
            ohlcv_service=ohlcv,
        )

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.signals_generated == 1
        created_signal = signal_store.append_signal.call_args[0][0]
        assert created_signal.signal_direction == "exit_long"

    def test_no_trigger_no_signal(self):
        """Condition never satisfied: no signal created."""
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T2,
            activation_timestamp=_NOW,
            warmup_bars_required=0,
            semantics=_no_trigger_semantics(),
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_bars_since.return_value = [_build_ohlcv(_T1, close=150.0)]
        bar_store = _mock_bar_store()
        signal_store = MagicMock(spec=ForwardTestSignalStore)
        svc = _make_service(
            repo=repo, bar_store=bar_store, signal_store=signal_store,
            ohlcv_service=ohlcv,
        )

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.signals_generated == 0
        signal_store.append_signal.assert_not_called()

    def test_duplicate_signal_suppressed(self):
        """Duplicate signal: append_signal returns False → signals_suppressed incremented."""
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T2,
            activation_timestamp=_NOW,
            warmup_bars_required=0,
            semantics=_always_entry_semantics(),
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_bars_since.return_value = [_build_ohlcv(_T1)]
        bar_store = _mock_bar_store()
        signal_store = MagicMock(spec=ForwardTestSignalStore)
        signal_store.append_signal.return_value = False  # duplicate
        svc = _make_service(
            repo=repo, bar_store=bar_store, signal_store=signal_store,
            ohlcv_service=ohlcv,
        )

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.signals_generated == 0
        assert result.signals_suppressed == 1

    def test_cursor_advanced_to_last_new_bar(self):
        """After processing new bars, cursor advances to the last new bar timestamp."""
        bars = [_build_ohlcv(_T2), _build_ohlcv(_T1)]
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T3,
            activation_timestamp=_NOW,
            warmup_bars_required=0,
            semantics=_empty_semantics(),
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_bars_since.return_value = bars
        bar_store = _mock_bar_store()
        svc = _make_service(repo=repo, bar_store=bar_store, ohlcv_service=ohlcv)

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.last_processed_bar_timestamp == _T1

    def test_session_counters_updated(self):
        """Session bars_evaluated and signal_eligible_bars_processed incremented."""
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T2,
            activation_timestamp=_NOW,
            warmup_bars_required=0,
            semantics=_empty_semantics(),
            bars_evaluated=5,
            signal_eligible_bars_processed=2,
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_bars_since.return_value = [_build_ohlcv(_T1)]
        bar_store = _mock_bar_store()
        svc = _make_service(repo=repo, bar_store=bar_store, ohlcv_service=ohlcv)

        svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        updated = repo.update.call_args[0][0]
        assert updated.bars_evaluated == 6
        assert updated.signal_eligible_bars_processed == 3

    def test_provider_failure_handled_gracefully(self):
        """Provider failure during poll: cycle returns provider_failure=True, no crash."""
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T1,
            activation_timestamp=_NOW,
            warmup_bars_required=0,
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_bars_since.side_effect = ConnectionError("timeout")
        svc = _make_service(repo=repo, ohlcv_service=ohlcv)

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.provider_failure is True
        assert result.bars_fetched == 0

    def test_gap_detected_emits_ft_gap_detected(self):
        """Gap detected: FT_GAP_DETECTED audit event emitted, gap_detected=True."""
        # Cursor is at T3 (Wednesday); next expected bar T2 (Thursday);
        # but first actual bar returned is T1 (Friday) → gap.
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T3,  # Wednesday
            activation_timestamp=_NOW,
            warmup_bars_required=0,
            semantics=_empty_semantics(),
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        # T1 = Friday, but next expected bar after T3 = T2 = Thursday
        ohlcv.get_bars_since.return_value = [_build_ohlcv(_T1)]
        bar_store = _mock_bar_store()
        svc = _make_service(repo=repo, bar_store=bar_store, ohlcv_service=ohlcv)

        with patch("backend.forward_testing.service.emit_audit_event") as mock_emit:
            result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.gap_detected is True
        emitted_kinds = [c.args[0].event_kind.value for c in mock_emit.call_args_list]
        assert "ft_gap_detected" in emitted_kinds

    def test_no_gap_when_consecutive_bars(self):
        """No gap when consecutive expected bar arrives exactly as expected."""
        # Cursor at T2 (Thursday); next expected bar T1 (Friday) = first actual bar.
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T2,
            activation_timestamp=_NOW,
            warmup_bars_required=0,
            semantics=_empty_semantics(),
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_bars_since.return_value = [_build_ohlcv(_T1)]
        bar_store = _mock_bar_store()
        svc = _make_service(repo=repo, bar_store=bar_store, ohlcv_service=ohlcv)

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.gap_detected is False

    def test_poll_emits_ft_poll_completed(self):
        """FT_POLL_COMPLETED audit event emitted after every RUNNING cycle."""
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T1,
            activation_timestamp=_NOW,
            warmup_bars_required=0,
            semantics=_empty_semantics(),
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_bars_since.return_value = []
        svc = _make_service(repo=repo, ohlcv_service=ohlcv)

        with patch("backend.forward_testing.service.emit_audit_event") as mock_emit:
            svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        emitted_kinds = [c.args[0].event_kind.value for c in mock_emit.call_args_list]
        assert "ft_poll_completed" in emitted_kinds

    def test_signal_emits_ft_signal_generated(self):
        """FT_SIGNAL_GENERATED emitted for new signal."""
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T2,
            activation_timestamp=_NOW,
            warmup_bars_required=0,
            semantics=_always_entry_semantics(),
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_bars_since.return_value = [_build_ohlcv(_T1)]
        bar_store = _mock_bar_store()
        signal_store = MagicMock(spec=ForwardTestSignalStore)
        signal_store.append_signal.return_value = True
        svc = _make_service(
            repo=repo, bar_store=bar_store, signal_store=signal_store,
            ohlcv_service=ohlcv,
        )

        with patch("backend.forward_testing.service.emit_audit_event") as mock_emit:
            svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        emitted_kinds = [c.args[0].event_kind.value for c in mock_emit.call_args_list]
        assert "ft_signal_generated" in emitted_kinds

    def test_duplicate_signal_emits_ft_signal_suppressed(self):
        """FT_SIGNAL_SUPPRESSED emitted when signal is a duplicate."""
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T2,
            activation_timestamp=_NOW,
            warmup_bars_required=0,
            semantics=_always_entry_semantics(),
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_bars_since.return_value = [_build_ohlcv(_T1)]
        bar_store = _mock_bar_store()
        signal_store = MagicMock(spec=ForwardTestSignalStore)
        signal_store.append_signal.return_value = False  # duplicate
        svc = _make_service(
            repo=repo, bar_store=bar_store, signal_store=signal_store,
            ohlcv_service=ohlcv,
        )

        with patch("backend.forward_testing.service.emit_audit_event") as mock_emit:
            svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        emitted_kinds = [c.args[0].event_kind.value for c in mock_emit.call_args_list]
        assert "ft_signal_suppressed" in emitted_kinds

    def test_warmup_bars_in_store_not_re_processed_as_new(self):
        """Bars already in the store (same timestamp) are not double-counted."""
        # Simulate a bar already stored from a previous partial cycle
        existing_bar = _build_stored_bar(bar_index=0, timestamp=_T1)
        bar_store = _mock_bar_store(stored_bars=[existing_bar])
        # get_bars_since returns the same bar (cursor not advanced from partial run)
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T2,
            activation_timestamp=_NOW,
            warmup_bars_required=0,
            semantics=_empty_semantics(),
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_bars_since.return_value = [_build_ohlcv(_T1)]
        svc = _make_service(repo=repo, bar_store=bar_store, ohlcv_service=ohlcv)

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        # Bar was already stored; no new bar appended
        bar_store.append_bar.assert_not_called()
        assert result.bars_processed == 0

    def test_running_cursor_none_uses_activation_timestamp(self):
        """When last_processed_bar_timestamp is None, activation_timestamp is used as cursor."""
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=None,
            activation_timestamp=_T2,  # fallback cursor
            warmup_bars_required=0,
            semantics=_empty_semantics(),
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_bars_since.return_value = []
        svc = _make_service(repo=repo, ohlcv_service=ohlcv)

        svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        # get_bars_since called with activation_timestamp as since_timestamp
        ohlcv.get_bars_since.assert_called_once()
        call_kwargs = ohlcv.get_bars_since.call_args
        assert call_kwargs.kwargs.get("since_timestamp") == _T2 or \
               call_kwargs.args[1] == _T2


# ============================================================================
# Status guards
# ============================================================================

class TestStatusGuards:
    """ForwardTestService: terminal and paused session guards."""

    @pytest.mark.parametrize("status", [
        ForwardTestSessionStatus.COMPLETED,
        ForwardTestSessionStatus.FAILED,
        ForwardTestSessionStatus.TERMINATED,
    ])
    def test_terminal_session_returns_no_op(self, status: ForwardTestSessionStatus):
        """Terminal sessions return a no-op CycleResult without any processing."""
        session = _build_session(status=status)
        repo = _mock_repo(session)
        svc = _make_service(repo=repo)

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.activated is False
        assert result.bars_fetched == 0
        assert result.signals_generated == 0
        assert status.value in result.status

    def test_paused_session_returns_no_op(self):
        """PAUSED session returns a no-op CycleResult without any processing."""
        session = _build_session(status=ForwardTestSessionStatus.PAUSED)
        repo = _mock_repo(session)
        svc = _make_service(repo=repo)

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.activated is False
        assert result.bars_fetched == 0
        assert result.status == ForwardTestSessionStatus.PAUSED.value

    def test_paused_session_message_explains_status(self):
        """PAUSED no-op result includes a descriptive message."""
        session = _build_session(status=ForwardTestSessionStatus.PAUSED)
        repo = _mock_repo(session)
        svc = _make_service(repo=repo)

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.message is not None
        assert "paused" in result.message.lower()

    def test_terminal_session_message_explains_status(self):
        """Terminal no-op result includes a message describing the terminal state."""
        session = _build_session(status=ForwardTestSessionStatus.COMPLETED)
        repo = _mock_repo(session)
        svc = _make_service(repo=repo)

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.message is not None
        assert "terminal" in result.message.lower() or "completed" in result.message.lower()


# ============================================================================
# Strategy deserialization / compilation errors
# ============================================================================

class TestStrategyErrors:
    """ForwardTestService: strategy-level error handling for RUNNING cycles."""

    def test_bad_strategy_json_returns_provider_failure(self):
        """Corrupt strategy_json: cycle returns provider_failure=True."""
        draft = _build_draft(_always_entry_semantics())
        snapshot = StrategySnapshot(
            draft_id=draft.draft_id,
            display_name=draft.display_name,
            lifecycle_status="draft",
            snapshot_hash="a" * 64,
            captured_at=_NOW,
            strategy_json="{invalid json",  # corrupt
        )
        session = ForwardTestSession(
            session_id=_SESSION_ID,
            user_id=_USER_ID,
            draft_id=_DRAFT_ID,
            strategy_snapshot=snapshot,
            lifecycle_status_at_activation="draft",
            source_mode="provider",
            provider_name="yahoo",
            symbol="AAPL",
            timeframe="1d",
            warmup_bars_required=0,
            status=ForwardTestSessionStatus.RUNNING,
            created_at=_NOW,
            updated_at=_NOW,
            activation_timestamp=_NOW,
            last_processed_bar_timestamp=_T1,
        )
        repo = _mock_repo(session)
        svc = _make_service(repo=repo)

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.provider_failure is True
        assert result.bars_fetched == 0

    def test_no_semantics_returns_provider_failure(self):
        """strategy_json with no semantics: cycle returns provider_failure=True."""
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            semantics=None,  # no semantics in draft
            last_processed_bar_timestamp=_T1,
            activation_timestamp=_NOW,
            warmup_bars_required=0,
        )
        # Patch the snapshot to use a draft with no semantics
        draft_no_sem = _build_draft(semantics=None)
        snapshot = _build_snapshot(draft_no_sem)
        session = session.model_copy(update={"strategy_snapshot": snapshot})
        repo = _mock_repo(session)
        svc = _make_service(repo=repo)

        result = svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        assert result.provider_failure is True
        assert result.message is not None
        assert "semantics" in result.message.lower()


# ============================================================================
# Ownership enforcement
# ============================================================================

class TestOwnership:
    """ForwardTestService: ownership enforcement via repository."""

    def test_wrong_owner_raises_not_found(self):
        """Repository raises ForwardTestSessionNotFoundError for wrong owner."""
        repo = MagicMock(spec=ForwardTestRepository)
        repo.load.side_effect = ForwardTestSessionNotFoundError("session not found")
        svc = _make_service(repo=repo)

        with pytest.raises(ForwardTestSessionNotFoundError):
            svc.run_cycle(
                _SESSION_ID, "wrong-owner-id", _make_identity(), MagicMock(), now_utc=_NOW
            )

    def test_repository_load_called_with_owner_id(self):
        """Repository.load is always called with the provided owner_id."""
        session = _build_session(status=ForwardTestSessionStatus.PAUSED)
        repo = _mock_repo(session)
        svc = _make_service(repo=repo)

        svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        repo.load.assert_called_once_with(_SESSION_ID, owner_id=_USER_ID)


# ============================================================================
# Signal field integrity
# ============================================================================

class TestSignalFields:
    """ForwardTestService: signal content and provenance fields."""

    def test_signal_carries_snapshot_hash(self):
        """Signal includes strategy_snapshot_hash from the session snapshot."""
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T2,
            activation_timestamp=_NOW,
            warmup_bars_required=0,
            semantics=_always_entry_semantics(),
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_bars_since.return_value = [_build_ohlcv(_T1)]
        bar_store = _mock_bar_store()
        signal_store = MagicMock(spec=ForwardTestSignalStore)
        signal_store.append_signal.return_value = True
        svc = _make_service(
            repo=repo, bar_store=bar_store, signal_store=signal_store,
            ohlcv_service=ohlcv,
        )

        svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        created_signal = signal_store.append_signal.call_args[0][0]
        assert created_signal.strategy_snapshot_hash == session.strategy_snapshot.snapshot_hash

    def test_signal_carries_bar_ohlcv(self):
        """Signal bar_open/high/low/close/volume match the triggering bar."""
        bar = _build_ohlcv(_T1, close=200.0)
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T2,
            activation_timestamp=_NOW,
            warmup_bars_required=0,
            semantics=_always_entry_semantics(),
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_bars_since.return_value = [bar]
        bar_store = _mock_bar_store()
        signal_store = MagicMock(spec=ForwardTestSignalStore)
        signal_store.append_signal.return_value = True
        svc = _make_service(
            repo=repo, bar_store=bar_store, signal_store=signal_store,
            ohlcv_service=ohlcv,
        )

        svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        created_signal = signal_store.append_signal.call_args[0][0]
        assert created_signal.bar_close == 200.0
        assert created_signal.bar_open == bar.open
        assert created_signal.bar_high == bar.high
        assert created_signal.bar_low == bar.low
        assert created_signal.bar_volume == bar.volume

    def test_signal_warmup_satisfied_true(self):
        """Signal produced during RUNNING poll always has warmup_satisfied=True."""
        session = _build_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T2,
            activation_timestamp=_NOW,
            warmup_bars_required=0,
            semantics=_always_entry_semantics(),
        )
        repo = _mock_repo(session)
        ohlcv = MagicMock(spec=OHLCVService)
        ohlcv.get_bars_since.return_value = [_build_ohlcv(_T1)]
        bar_store = _mock_bar_store()
        signal_store = MagicMock(spec=ForwardTestSignalStore)
        signal_store.append_signal.return_value = True
        svc = _make_service(
            repo=repo, bar_store=bar_store, signal_store=signal_store,
            ohlcv_service=ohlcv,
        )

        svc.run_cycle(_SESSION_ID, _USER_ID, _make_identity(), MagicMock(), now_utc=_NOW)

        created_signal = signal_store.append_signal.call_args[0][0]
        assert created_signal.warmup_satisfied is True
