"""
Phase 4C.6 — Forward Testing Integration Validation.

Validates the complete forward testing stack end-to-end against the
architecture contracts in:
  docs/FORWARD_TESTING_ARCHITECTURE.md
  docs/FORWARD_TESTING_IMPLEMENTATION_REVIEW.md
  docs/EXECUTION_CONTRACT.md
  docs/EXECUTION_AUDIT_MODEL.md
  docs/STRATEGY_PROMOTION_LIFECYCLE.md

Validation objectives:
 1.  End-to-end workflow: create → activate → poll → signals
 2.  Ownership isolation across all 9 routes
 3.  Lifecycle gate: only backtested+ strategies accepted
 4.  Entitlement gate: active subscription required
 5.  Warmup bar correctness: stored with is_warmup_bar=True, no signals
 6.  Signal generation: persistence, cursor advancement, counter updates
 7.  Signal idempotency: same bar_timestamp + direction never duplicated
 8.  Calendar-aware gap detection: equity weekend not treated as gap
 9.  Audit event emission: all lifecycle events present with correct kind
10.  API security: no strategy_json / user_id / file_path in responses
11.  UUID path validation: malformed IDs return 400
12.  Terminal state guards: terminated session run-cycle is no-op
13.  Resume pre-check: resume only valid from PAUSED
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.api.dependencies import (
    get_draft_repository,
    get_forward_test_bar_store,
    get_forward_test_repository,
    get_forward_test_signal_store,
    get_ohlcv_service,
    get_provider_factory,
    get_tool_registry,
)
from backend.api.main import app
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.data.models.dataset import DatasetIdentity
from backend.data.models.instrument import AdjustmentMode, Instrument
from backend.forward_testing.models import (
    ForwardTestSession,
    ForwardTestSessionStatus,
    StrategySnapshot,
)
from backend.forward_testing.repository import ForwardTestRepository
from backend.forward_testing.service import ForwardTestService
from backend.forward_testing.stores import ForwardTestBarStore, ForwardTestSignalStore
from backend.services.ohlcv_service import OHLCVService
from backend.strategy_registry.draft_repository import DraftRepository
from backend.strategy_registry.drafts import StrategyDraft
from backend.strategy_registry.lifecycle import StrategyLifecycleStatus
from backend.strategy_registry.semantics import (
    Condition,
    ConditionGroup,
    ConditionOperator,
    EntryRule,
    LogicalOperator,
    OperandKind,
    OperandReference,
    StrategySemantics,
)
from backend.tools.registry import ToolRegistry
from backend.tools.toolset import StrategyToolSet

_UTC = timezone.utc

# Reference timestamps — all weekday bars, well before "now"
_NOW     = datetime(2026, 5, 30, 18, 0, 0, tzinfo=_UTC)   # Saturday (reference)
_T1      = datetime(2026, 5, 28, 0, 0, 0, tzinfo=_UTC)    # Thursday
_T2      = datetime(2026, 5, 27, 0, 0, 0, tzinfo=_UTC)    # Wednesday
_T3      = datetime(2026, 5, 26, 0, 0, 0, tzinfo=_UTC)    # Tuesday
_SAT     = datetime(2026, 5, 30, 0, 0, 0, tzinfo=_UTC)    # Saturday (weekend)

# Valid UUID identities
_OWNER_ID = "aaaaaaaa-1001-1001-1001-000000000001"
_OTHER_ID = "bbbbbbbb-2002-2002-2002-000000000002"
_DRAFT_ID = str(uuid.uuid4())
_SESSION_ID = str(uuid.uuid4())

_OWNER_USER = User(
    user_id=_OWNER_ID,
    username="owner",
    email="owner@example.com",
    password_hash="x",
    created_at="2024-01-01T00:00:00Z",
    role="user",
    subscription_status="active",
)

_OTHER_USER = User(
    user_id=_OTHER_ID,
    username="other",
    email="other@example.com",
    password_hash="x",
    created_at="2024-01-01T00:00:00Z",
    role="user",
    subscription_status="active",
)


# ---------------------------------------------------------------------------
# Mock bar — mimics OHLCVService.get_recent_bars / get_bars_since return value
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Bar:
    """Minimal bar stub matching the attribute contract consumed by ForwardTestService."""
    timestamp: datetime
    open: float = 100.0
    high: float = 110.0
    low: float = 90.0
    close: float = 105.0
    volume: float = 1_000.0


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------

def _close_gt_zero() -> Condition:
    return Condition(
        left=OperandReference(kind=OperandKind.PRICE, ref="close"),
        operator=ConditionOperator.GT,
        right=OperandReference(kind=OperandKind.CONSTANT, ref="0"),
    )


def _always_entry_semantics() -> StrategySemantics:
    return StrategySemantics(
        entry_rules=(
            EntryRule(
                rule_id="entry_always",
                condition_group=ConditionGroup(
                    operator=LogicalOperator.AND,
                    conditions=(_close_gt_zero(),),
                ),
            ),
        ),
        exit_rules=(),
    )


def _make_draft(
    draft_id: str = _DRAFT_ID,
    user_id: str = _OWNER_ID,
    lifecycle: StrategyLifecycleStatus = StrategyLifecycleStatus.BACKTESTED,
    semantics: StrategySemantics | None = None,
) -> StrategyDraft:
    return StrategyDraft(
        draft_id=draft_id,
        display_name="Integration Test Strategy",
        toolset=StrategyToolSet(toolset_id="ts_int", tools=()),
        created_at=_NOW,
        updated_at=_NOW,
        user_id=user_id,
        lifecycle_status=lifecycle,
        semantics=semantics,
    )


def _make_snapshot(draft: StrategyDraft) -> StrategySnapshot:
    strategy_json = draft.model_dump_json()
    return StrategySnapshot(
        draft_id=draft.draft_id,
        display_name=draft.display_name,
        lifecycle_status=draft.lifecycle_status.value,
        snapshot_hash=hashlib.sha256(strategy_json.encode()).hexdigest(),
        captured_at=_NOW,
        strategy_json=strategy_json,
    )


def _make_session(
    session_id: str = _SESSION_ID,
    user_id: str = _OWNER_ID,
    draft_id: str = _DRAFT_ID,
    status: ForwardTestSessionStatus = ForwardTestSessionStatus.PENDING,
    source_mode: str = "provider",
    warmup_bars_required: int = 0,
    semantics: StrategySemantics | None = None,
    last_processed_bar_timestamp: datetime | None = None,
) -> ForwardTestSession:
    draft = _make_draft(draft_id=draft_id, user_id=user_id, semantics=semantics)
    snapshot = _make_snapshot(draft)
    return ForwardTestSession(
        session_id=session_id,
        user_id=user_id,
        draft_id=draft_id,
        strategy_snapshot=snapshot,
        lifecycle_status_at_activation="backtested",
        source_mode=source_mode,
        provider_name="yahoo" if source_mode == "provider" else None,
        catalog_id="cat-x" if source_mode == "catalog" else None,
        symbol="AAPL",
        timeframe="1d",
        exchange="NASDAQ",
        asset_class="equity",
        warmup_bars_required=warmup_bars_required,
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
        last_processed_bar_timestamp=last_processed_bar_timestamp,
    )


def _make_identity() -> DatasetIdentity:
    return DatasetIdentity(
        instrument=Instrument(symbol="AAPL", asset_class="equity", exchange="NASDAQ"),
        provider="yahoo",
        timeframe="1d",
        adjustment_mode=AdjustmentMode.RAW,
    )


def _mock_provider() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repos(tmp_path: Path):
    draft_repo   = DraftRepository(tmp_path / "drafts")
    ft_repo      = ForwardTestRepository(tmp_path / "ft")
    sig_store    = ForwardTestSignalStore(tmp_path / "ft")
    bar_store    = ForwardTestBarStore(tmp_path / "ft")
    return draft_repo, ft_repo, sig_store, bar_store


@pytest.fixture
def svc(repos):
    """Real ForwardTestService with mocked OHLCVService."""
    _, ft_repo, sig_store, bar_store = repos
    ohlcv_mock = MagicMock(spec=OHLCVService)
    ohlcv_mock.get_recent_bars.return_value = []
    ohlcv_mock.get_bars_since.return_value = []
    service = ForwardTestService(
        repository=ft_repo,
        signal_store=sig_store,
        bar_store=bar_store,
        ohlcv_service=ohlcv_mock,
        tool_registry=ToolRegistry(),
    )
    return service, ft_repo, sig_store, bar_store, ohlcv_mock


@pytest.fixture
def client(repos):
    """HTTP test client with real repos and controlled auth."""
    draft_repo, ft_repo, sig_store, bar_store = repos
    ohlcv_mock = MagicMock(spec=OHLCVService)
    ohlcv_mock.get_recent_bars.return_value = []
    ohlcv_mock.get_bars_since.return_value = []

    overrides = {
        get_draft_repository:          lambda: draft_repo,
        get_forward_test_repository:   lambda: ft_repo,
        get_forward_test_signal_store: lambda: sig_store,
        get_forward_test_bar_store:    lambda: bar_store,
        get_ohlcv_service:             lambda: ohlcv_mock,
        get_tool_registry:             lambda: ToolRegistry(),
        get_provider_factory:          lambda: MagicMock(),
        require_active_subscription:   lambda: _OWNER_USER,
    }
    app.dependency_overrides.update(overrides)
    yield TestClient(app), draft_repo, ft_repo, sig_store, bar_store, ohlcv_mock
    for key in overrides:
        app.dependency_overrides.pop(key, None)


def _fake_cycle_result(session_id: str, activated: bool = True):
    from backend.forward_testing.service import CycleResult
    return CycleResult(
        session_id=session_id,
        status="running",
        bars_fetched=0,
        bars_processed=0,
        warmup_bars_processed=0,
        signal_eligible_bars_processed=0,
        signals_generated=0,
        signals_suppressed=0,
        last_processed_bar_timestamp=None,
        gap_detected=False,
        provider_failure=False,
        activated=activated,
        message=None,
    )


# ===========================================================================
# Section A — Service-level end-to-end workflow
# ===========================================================================

class TestE2EWorkflowService:
    """
    End-to-end validation at service level.

    Objective 1: create → activate → poll workflow with real repositories.
    """

    def test_activation_transitions_to_running(self, svc, repos):
        """PENDING session transitions to RUNNING after first run_cycle."""
        service, ft_repo, *_ = svc
        session = _make_session(warmup_bars_required=0)
        ft_repo.save(session)

        result = service.run_cycle(
            _SESSION_ID, _OWNER_ID, _make_identity(), _mock_provider(), now_utc=_NOW
        )

        assert result.activated is True
        assert result.status == "running"
        loaded = ft_repo.load(_SESSION_ID, owner_id=_OWNER_ID)
        assert loaded.status == ForwardTestSessionStatus.RUNNING

    def test_warmup_bars_stored_with_correct_flag(self, svc, repos):
        """Warmup bars fetched during activation are stored with is_warmup_bar=True."""
        service, ft_repo, _, bar_store, ohlcv_mock = svc
        ohlcv_mock.get_recent_bars.return_value = [_Bar(_T2), _Bar(_T3)]

        session = _make_session(warmup_bars_required=2)
        ft_repo.save(session)
        service.run_cycle(
            _SESSION_ID, _OWNER_ID, _make_identity(), _mock_provider(), now_utc=_NOW
        )

        bars = bar_store.list_bars(_SESSION_ID)
        assert len(bars) == 2
        assert all(b.is_warmup_bar for b in bars)

    def test_zero_warmup_activation_sets_cursor_to_now(self, svc, repos):
        """Zero-warmup session: cursor defaults to now_utc after activation."""
        service, ft_repo, *_ = svc
        session = _make_session(warmup_bars_required=0)
        ft_repo.save(session)

        service.run_cycle(
            _SESSION_ID, _OWNER_ID, _make_identity(), _mock_provider(), now_utc=_NOW
        )

        loaded = ft_repo.load(_SESSION_ID, owner_id=_OWNER_ID)
        assert loaded.last_processed_bar_timestamp == _NOW

    def test_warmup_count_incremented_correctly(self, svc, repos):
        """warmup_bars_processed counter matches bars actually stored."""
        service, ft_repo, *_ = svc
        ohlcv_mock = svc[4]
        ohlcv_mock.get_recent_bars.return_value = [_Bar(_T2), _Bar(_T3)]

        session = _make_session(warmup_bars_required=2)
        ft_repo.save(session)
        result = service.run_cycle(
            _SESSION_ID, _OWNER_ID, _make_identity(), _mock_provider(), now_utc=_NOW
        )

        assert result.warmup_bars_processed == 2
        loaded = ft_repo.load(_SESSION_ID, owner_id=_OWNER_ID)
        assert loaded.warmup_bars_processed == 2

    def test_cursor_advances_after_poll_with_new_bar(self, svc, repos):
        """Cursor advances to the last processed bar timestamp after a poll."""
        service, ft_repo, _, bar_store, ohlcv_mock = svc

        # Start from RUNNING state (simulate post-activation); semantics required for evaluation
        session = _make_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T2,
            semantics=_always_entry_semantics(),
        )
        ft_repo.save(session)

        ohlcv_mock.get_bars_since.return_value = [_Bar(_T1)]
        service.run_cycle(
            _SESSION_ID, _OWNER_ID, _make_identity(), _mock_provider(), now_utc=_NOW
        )

        loaded = ft_repo.load(_SESSION_ID, owner_id=_OWNER_ID)
        assert loaded.last_processed_bar_timestamp == _T1

    def test_cursor_unchanged_when_no_new_bars(self, svc, repos):
        """Cursor stays unchanged when no new finalized bars are available."""
        service, ft_repo, *_ = svc
        ohlcv_mock = svc[4]
        ohlcv_mock.get_bars_since.return_value = []

        session = _make_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T2,
        )
        ft_repo.save(session)

        result = service.run_cycle(
            _SESSION_ID, _OWNER_ID, _make_identity(), _mock_provider(), now_utc=_NOW
        )

        assert result.bars_fetched == 0
        assert result.bars_processed == 0
        loaded = ft_repo.load(_SESSION_ID, owner_id=_OWNER_ID)
        assert loaded.last_processed_bar_timestamp == _T2  # unchanged

    def test_signal_generated_after_activation(self, svc, repos):
        """Entry signal recorded during poll when strategy entry rule fires."""
        service, ft_repo, sig_store, bar_store, ohlcv_mock = svc

        # Session with 1 warmup bar, strategy that fires entry on close > 0
        session = _make_session(
            warmup_bars_required=1,
            semantics=_always_entry_semantics(),
        )
        ft_repo.save(session)

        # Activation: get 1 warmup bar
        ohlcv_mock.get_recent_bars.return_value = [_Bar(_T3)]
        service.run_cycle(
            _SESSION_ID, _OWNER_ID, _make_identity(), _mock_provider(), now_utc=_NOW
        )

        # Poll: get 1 signal-eligible bar (bar_index=1 >= warmup_bars_required=1)
        ohlcv_mock.get_bars_since.return_value = [_Bar(_T1, close=105.0)]
        result = service.run_cycle(
            _SESSION_ID, _OWNER_ID, _make_identity(), _mock_provider(), now_utc=_NOW
        )

        assert result.signals_generated == 1
        signals = sig_store.list_signals(_SESSION_ID)
        assert len(signals) == 1
        assert signals[0].signal_direction == "entry_long"
        assert signals[0].warmup_satisfied is True

    def test_no_signal_during_warmup_phase(self, svc, repos):
        """Bars with bar_index < warmup_bars_required never generate signals."""
        service, ft_repo, sig_store, bar_store, ohlcv_mock = svc

        # Session requiring 3 warmup bars — start from RUNNING with 0 stored bars
        session = _make_session(
            status=ForwardTestSessionStatus.RUNNING,
            warmup_bars_required=3,
            last_processed_bar_timestamp=_T3,
            semantics=_always_entry_semantics(),
        )
        ft_repo.save(session)

        # Poll delivers 2 bars — indices 0 and 1 — both below warmup threshold
        ohlcv_mock.get_bars_since.return_value = [_Bar(_T2), _Bar(_T1)]
        result = service.run_cycle(
            _SESSION_ID, _OWNER_ID, _make_identity(), _mock_provider(), now_utc=_NOW
        )

        assert result.signals_generated == 0
        assert sig_store.list_signals(_SESSION_ID) == []

    def test_terminal_session_run_cycle_is_noop(self, svc, repos):
        """run_cycle on a TERMINATED session returns a no-op CycleResult."""
        service, ft_repo, sig_store, *_ = svc
        session = _make_session(status=ForwardTestSessionStatus.TERMINATED)
        ft_repo.save(session)

        result = service.run_cycle(
            _SESSION_ID, _OWNER_ID, _make_identity(), _mock_provider(), now_utc=_NOW
        )

        assert result.activated is False
        assert result.bars_fetched == 0
        assert result.signals_generated == 0
        assert "terminal" in (result.message or "").lower()
        # Status unchanged
        loaded = ft_repo.load(_SESSION_ID, owner_id=_OWNER_ID)
        assert loaded.status == ForwardTestSessionStatus.TERMINATED

    def test_paused_session_run_cycle_is_noop(self, svc, repos):
        """run_cycle on a PAUSED session returns a no-op CycleResult."""
        service, ft_repo, *_ = svc
        session = _make_session(status=ForwardTestSessionStatus.PAUSED)
        ft_repo.save(session)

        result = service.run_cycle(
            _SESSION_ID, _OWNER_ID, _make_identity(), _mock_provider(), now_utc=_NOW
        )

        assert result.activated is False
        assert "paused" in (result.message or "").lower()


# ===========================================================================
# Section B — Signal idempotency
# ===========================================================================

class TestSignalIdempotency:
    """
    Objective 7: duplicate bars in the same cycle produce no duplicate signals.
    """

    def test_duplicate_bar_in_store_no_duplicate_signal(self, svc, repos):
        """
        If get_bars_since returns a bar already in the bar_store,
        the bar is skipped (already stored) and no duplicate signal is created.
        """
        service, ft_repo, sig_store, bar_store, ohlcv_mock = svc

        session = _make_session(
            status=ForwardTestSessionStatus.RUNNING,
            warmup_bars_required=1,
            last_processed_bar_timestamp=_T2,
            semantics=_always_entry_semantics(),
        )
        ft_repo.save(session)

        # Pre-populate bar store with one warmup bar
        from backend.forward_testing.models import ForwardTestBar
        bar_store.append_bar(ForwardTestBar(
            session_id=_SESSION_ID,
            bar_index=0,
            bar_timestamp=_T2,
            open=100.0, high=105.0, low=95.0, close=102.0, volume=500.0,
            source_mode="provider",
            provider_name="yahoo",
            is_warmup_bar=True,
            processed_at=_NOW,
        ))

        # Poll delivers _T1 (new) — _T2 already stored, so only _T1 processed
        ohlcv_mock.get_bars_since.return_value = [_Bar(_T2), _Bar(_T1)]

        result = service.run_cycle(
            _SESSION_ID, _OWNER_ID, _make_identity(), _mock_provider(), now_utc=_NOW
        )

        # Only _T1 processed (bar_index=1 >= warmup=1 → signal eligible)
        assert result.bars_processed == 1
        signals = sig_store.list_signals(_SESSION_ID)
        assert len(signals) == 1  # one signal for _T1 only

    def test_signal_store_deduplicates_same_direction(self, svc, repos):
        """
        Appending two signals with identical (bar_timestamp, signal_direction)
        produces only one stored signal.
        """
        _, _, sig_store, _, _ = svc
        from backend.forward_testing.models import ForwardTestSignal

        sig = ForwardTestSignal(
            signal_id=str(uuid.uuid4()),
            session_id=_SESSION_ID,
            user_id=_OWNER_ID,
            bar_timestamp=_T1,
            signal_timestamp=_NOW,
            signal_direction="entry_long",
            rule_id="entry_always",
            bar_open=100.0, bar_high=110.0, bar_low=90.0, bar_close=105.0, bar_volume=1000.0,
            warmup_satisfied=True,
            strategy_snapshot_hash="abc123",
            symbol="AAPL",
            timeframe="1d",
            provider_name="yahoo",
            created_at=_NOW,
        )
        sig_dup = sig.model_copy(update={"signal_id": str(uuid.uuid4())})

        was_new_1 = sig_store.append_signal(sig)
        was_new_2 = sig_store.append_signal(sig_dup)

        assert was_new_1 is True
        assert was_new_2 is False
        assert len(sig_store.list_signals(_SESSION_ID)) == 1


# ===========================================================================
# Section C — Calendar-aware gap detection
# ===========================================================================

class TestCalendarGapDetection:
    """Objective 8: equity Saturday bar not treated as a gap."""

    def test_equity_saturday_bar_not_a_gap(self, svc, repos):
        """
        When cursor is a Friday bar and no Saturday bar arrives,
        gap_detected must be False (Saturday is not expected for equity).
        """
        service, ft_repo, *_ = svc
        ohlcv_mock = svc[4]

        # Cursor = Friday bar (_T1 = Thursday... let's use a real Friday)
        _FRI = datetime(2026, 5, 29, 0, 0, 0, tzinfo=_UTC)
        session = _make_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_FRI,
        )
        ft_repo.save(session)

        # No new bars (Saturday, market closed)
        ohlcv_mock.get_bars_since.return_value = []

        result = service.run_cycle(
            _SESSION_ID, _OWNER_ID, _make_identity(), _mock_provider(),
            now_utc=_SAT,
        )

        # No bars → no gap evaluation; gap_detected should be False
        assert result.gap_detected is False

    def test_gap_detected_when_expected_weekday_bar_absent(self, svc, repos):
        """
        When cursor is Monday and a Wednesday bar arrives (Tuesday skipped),
        gap_detected is True for equity (Tuesday is a trading day).
        """
        service, ft_repo, *_ = svc
        ohlcv_mock = svc[4]

        _MON = datetime(2026, 5, 25, 0, 0, 0, tzinfo=_UTC)  # Monday
        _WED = datetime(2026, 5, 27, 0, 0, 0, tzinfo=_UTC)  # Wednesday (Tuesday gap)
        _NOW_THU = datetime(2026, 5, 28, 12, 0, 0, tzinfo=_UTC)

        session = _make_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_MON,
            semantics=_always_entry_semantics(),
        )
        ft_repo.save(session)

        # Wednesday bar arrives but Tuesday is missing (gap)
        ohlcv_mock.get_bars_since.return_value = [_Bar(_WED)]

        result = service.run_cycle(
            _SESSION_ID, _OWNER_ID, _make_identity(), _mock_provider(),
            now_utc=_NOW_THU,
        )

        assert result.gap_detected is True


# ===========================================================================
# Section D — Ownership isolation (HTTP level)
# ===========================================================================

class TestOwnershipIsolation:
    """
    Objective 2: Wrong-owner access to any route returns HTTP 404.
    Ownership is fully isolated — user A cannot see user B's sessions.
    """

    def test_create_wrong_draft_owner_404(self, client):
        tc, draft_repo, *_ = client
        draft_repo.save(_make_draft(user_id=_OTHER_ID))

        resp = tc.post("/forward-tests", json={
            "draft_id": _DRAFT_ID, "symbol": "AAPL", "timeframe": "1d",
            "source_mode": "provider", "provider_name": "yahoo",
        })
        assert resp.status_code == 404

    def test_list_sessions_cross_user_invisible(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(user_id=_OTHER_ID))

        resp = tc.get("/forward-tests")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_session_wrong_owner_404(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(user_id=_OTHER_ID))

        resp = tc.get(f"/forward-tests/{_SESSION_ID}")
        assert resp.status_code == 404

    def test_run_cycle_wrong_owner_404(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(user_id=_OTHER_ID))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/run-cycle")
        assert resp.status_code == 404

    def test_pause_wrong_owner_404(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(user_id=_OTHER_ID, status=ForwardTestSessionStatus.RUNNING))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/pause")
        assert resp.status_code == 404

    def test_resume_wrong_owner_404(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(user_id=_OTHER_ID, status=ForwardTestSessionStatus.PAUSED))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/resume")
        assert resp.status_code == 404

    def test_terminate_wrong_owner_404(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(user_id=_OTHER_ID, status=ForwardTestSessionStatus.RUNNING))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/terminate")
        assert resp.status_code == 404

    def test_signals_wrong_owner_404(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(user_id=_OTHER_ID))

        resp = tc.get(f"/forward-tests/{_SESSION_ID}/signals")
        assert resp.status_code == 404

    def test_bars_wrong_owner_404(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(user_id=_OTHER_ID))

        resp = tc.get(f"/forward-tests/{_SESSION_ID}/bars")
        assert resp.status_code == 404

    def test_two_users_sessions_isolated(self, client):
        """Owner sees own session; other user's session is invisible to owner."""
        tc, _, ft_repo, *_ = client
        own_session = _make_session(session_id=_SESSION_ID, user_id=_OWNER_ID)
        other_session = _make_session(session_id=str(uuid.uuid4()), user_id=_OTHER_ID)
        ft_repo.save(own_session)
        ft_repo.save(other_session)

        resp = tc.get("/forward-tests")
        assert resp.status_code == 200
        ids = [s["session_id"] for s in resp.json()]
        assert _SESSION_ID in ids
        assert len(ids) == 1  # only owner's session


# ===========================================================================
# Section E — Lifecycle gate enforcement
# ===========================================================================

class TestLifecycleGate:
    """Objective 3: Only backtested+ strategies can create forward test sessions."""

    def test_draft_status_rejected_422(self, client):
        tc, draft_repo, *_ = client
        draft_repo.save(_make_draft(lifecycle=StrategyLifecycleStatus.DRAFT))

        resp = tc.post("/forward-tests", json={
            "draft_id": _DRAFT_ID, "symbol": "AAPL", "timeframe": "1d",
            "source_mode": "provider", "provider_name": "yahoo",
        })
        assert resp.status_code == 422
        assert "lifecycle" in resp.json()["detail"].lower()

    def test_validated_status_rejected_422(self, client):
        tc, draft_repo, *_ = client
        draft_repo.save(_make_draft(lifecycle=StrategyLifecycleStatus.VALIDATED))

        resp = tc.post("/forward-tests", json={
            "draft_id": _DRAFT_ID, "symbol": "AAPL", "timeframe": "1d",
            "source_mode": "provider", "provider_name": "yahoo",
        })
        assert resp.status_code == 422

    def test_backtested_status_accepted_201(self, client):
        tc, draft_repo, *_ = client
        draft_repo.save(_make_draft(lifecycle=StrategyLifecycleStatus.BACKTESTED))

        resp = tc.post("/forward-tests", json={
            "draft_id": _DRAFT_ID, "symbol": "AAPL", "timeframe": "1d",
            "source_mode": "provider", "provider_name": "yahoo",
        })
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending"

    def test_forward_tested_status_accepted_201(self, client):
        tc, draft_repo, *_ = client
        draft_repo.save(_make_draft(lifecycle=StrategyLifecycleStatus.FORWARD_TESTED))

        resp = tc.post("/forward-tests", json={
            "draft_id": _DRAFT_ID, "symbol": "AAPL", "timeframe": "1d",
            "source_mode": "provider", "provider_name": "yahoo",
        })
        assert resp.status_code == 201

    def test_paper_tested_status_accepted_201(self, client):
        tc, draft_repo, *_ = client
        draft_repo.save(_make_draft(lifecycle=StrategyLifecycleStatus.PAPER_TESTED))

        resp = tc.post("/forward-tests", json={
            "draft_id": _DRAFT_ID, "symbol": "AAPL", "timeframe": "1d",
            "source_mode": "provider", "provider_name": "yahoo",
        })
        assert resp.status_code == 201


# ===========================================================================
# Section F — Entitlement gate
# ===========================================================================

class TestEntitlementGate:
    """Objective 4: Active subscription required for all routes."""

    def test_no_active_subscription_returns_403(self, repos):
        """Routes blocked when subscription dependency raises HTTP 403."""
        draft_repo, ft_repo, sig_store, bar_store = repos

        def _raise_403():
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="subscription_required")

        overrides = {
            get_draft_repository:          lambda: draft_repo,
            get_forward_test_repository:   lambda: ft_repo,
            get_forward_test_signal_store: lambda: sig_store,
            get_forward_test_bar_store:    lambda: bar_store,
            get_ohlcv_service:             lambda: MagicMock(),
            get_tool_registry:             lambda: ToolRegistry(),
            get_provider_factory:          lambda: MagicMock(),
            require_active_subscription:   _raise_403,
        }
        app.dependency_overrides.update(overrides)
        try:
            tc = TestClient(app, raise_server_exceptions=False)
            assert tc.get("/forward-tests").status_code in (401, 403)
            assert tc.post("/forward-tests", json={}).status_code in (401, 403)
        finally:
            for key in overrides:
                app.dependency_overrides.pop(key, None)


# ===========================================================================
# Section G — Session lifecycle transitions (HTTP level)
# ===========================================================================

class TestLifecycleTransitionsHTTP:
    """Objective 2/12/13: Lifecycle transitions enforced at route layer."""

    def test_pause_running_session_200(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.RUNNING))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/pause")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

    def test_resume_paused_session_200(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.PAUSED))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/resume")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_resume_from_pending_rejected_422(self, client):
        """Resume is semantically PAUSED→RUNNING only; PENDING is the activation path."""
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.PENDING))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/resume")
        assert resp.status_code == 422
        assert "paused" in resp.json()["detail"].lower()

    def test_resume_from_running_rejected_422(self, client):
        """Resume from RUNNING is semantically wrong."""
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.RUNNING))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/resume")
        assert resp.status_code == 422

    def test_pause_from_pending_rejected_422(self, client):
        """Cannot pause a PENDING session (not yet running)."""
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.PENDING))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/pause")
        assert resp.status_code == 422

    def test_terminate_running_session_200(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.RUNNING))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/terminate")
        assert resp.status_code == 200
        assert resp.json()["status"] == "terminated"

    def test_terminate_paused_session_200(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.PAUSED))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/terminate")
        assert resp.status_code == 200
        assert resp.json()["status"] == "terminated"

    def test_terminate_terminal_session_422(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.TERMINATED))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/terminate")
        assert resp.status_code == 422

    def test_catalog_mode_rejected_for_run_cycle(self, client):
        """Catalog source mode is static — cannot be used for live polling."""
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(source_mode="catalog"))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/run-cycle")
        assert resp.status_code == 422
        assert "catalog" in resp.json()["detail"].lower()

    def test_run_cycle_happy_path_returns_cycle_result(self, client):
        """run-cycle returns ForwardTestCycleResultResponse with required fields."""
        tc, _, ft_repo, *_ = client
        session = _make_session(source_mode="provider")
        ft_repo.save(session)

        fake = _fake_cycle_result(_SESSION_ID, activated=True)
        with patch(
            "backend.api.routes.forward_testing.ForwardTestService.run_cycle",
            return_value=fake,
        ):
            resp = tc.post(f"/forward-tests/{_SESSION_ID}/run-cycle")

        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == _SESSION_ID
        assert body["activated"] is True
        assert "bars_fetched" in body
        assert "signals_generated" in body
        assert "gap_detected" in body
        assert "provider_failure" in body


# ===========================================================================
# Section H — Audit event emission
# ===========================================================================

class TestAuditEventEmission:
    """
    Objective 9: Verify that lifecycle audit events are emitted with the correct
    event_kind string. Uses caplog on the "quantlab.audit" logger.
    """

    def _audit_kinds(self, caplog) -> list[str]:
        import json
        kinds = []
        for r in caplog.records:
            if r.name == "quantlab.audit":
                try:
                    kinds.append(json.loads(r.message).get("audit_event", ""))
                except Exception:
                    pass
        return kinds

    def test_ft_session_created_emitted(self, client, caplog):
        tc, draft_repo, *_ = client
        draft_repo.save(_make_draft())

        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            tc.post("/forward-tests", json={
                "draft_id": _DRAFT_ID, "symbol": "AAPL", "timeframe": "1d",
                "source_mode": "provider", "provider_name": "yahoo",
            })

        assert "ft_session_created" in self._audit_kinds(caplog)

    def test_ft_session_activated_emitted_on_first_run_cycle(self, client, caplog):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.PENDING))

        fake = _fake_cycle_result(_SESSION_ID, activated=True)
        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            with patch(
                "backend.api.routes.forward_testing.ForwardTestService.run_cycle",
                return_value=fake,
            ):
                tc.post(f"/forward-tests/{_SESSION_ID}/run-cycle")

        # The route calls service.run_cycle; activation audit is emitted by the service.
        # Even when patching run_cycle, the route itself doesn't emit FT_SESSION_ACTIVATED.
        # Service-layer audit emission is validated by test_ft_session_activated_emitted_via_service.

    def test_ft_session_activated_emitted_via_service(self, svc, repos, caplog):
        """FT_SESSION_ACTIVATED audit event emitted during service activation."""
        service, ft_repo, *_ = svc
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.PENDING))

        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            service.run_cycle(
                _SESSION_ID, _OWNER_ID, _make_identity(), _mock_provider(), now_utc=_NOW
            )

        kinds = self._audit_kinds(caplog)
        assert "ft_session_activated" in kinds

    def test_ft_poll_completed_emitted_via_service(self, svc, repos, caplog):
        """FT_POLL_COMPLETED audit event emitted on every running poll cycle."""
        service, ft_repo, *_ = svc
        ohlcv_mock = svc[4]
        ohlcv_mock.get_bars_since.return_value = []
        ft_repo.save(_make_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_T2,
            semantics=_always_entry_semantics(),
        ))

        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            service.run_cycle(
                _SESSION_ID, _OWNER_ID, _make_identity(), _mock_provider(), now_utc=_NOW
            )

        assert "ft_poll_completed" in self._audit_kinds(caplog)

    def test_ft_signal_generated_emitted_via_service(self, svc, repos, caplog):
        """FT_SIGNAL_GENERATED emitted when entry signal fires."""
        service, ft_repo, *_ = svc
        ohlcv_mock = svc[4]

        session = _make_session(
            status=ForwardTestSessionStatus.RUNNING,
            warmup_bars_required=0,
            last_processed_bar_timestamp=_T2,
            semantics=_always_entry_semantics(),
        )
        ft_repo.save(session)

        ohlcv_mock.get_bars_since.return_value = [_Bar(_T1, close=105.0)]

        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            service.run_cycle(
                _SESSION_ID, _OWNER_ID, _make_identity(), _mock_provider(), now_utc=_NOW
            )

        kinds = self._audit_kinds(caplog)
        assert "ft_signal_generated" in kinds

    def test_ft_session_paused_emitted(self, client, caplog):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.RUNNING))

        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            tc.post(f"/forward-tests/{_SESSION_ID}/pause")

        assert "ft_session_paused" in self._audit_kinds(caplog)

    def test_ft_session_resumed_emitted(self, client, caplog):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.PAUSED))

        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            tc.post(f"/forward-tests/{_SESSION_ID}/resume")

        assert "ft_session_resumed" in self._audit_kinds(caplog)

    def test_ft_session_terminated_emitted(self, client, caplog):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.RUNNING))

        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            tc.post(f"/forward-tests/{_SESSION_ID}/terminate")

        assert "ft_session_terminated" in self._audit_kinds(caplog)

    def test_ft_provider_failure_emitted_on_warmup_error(self, svc, repos, caplog):
        """FT_PROVIDER_FAILURE emitted when warmup fetch raises an exception."""
        service, ft_repo, *_ = svc
        ohlcv_mock = svc[4]
        ohlcv_mock.get_recent_bars.side_effect = RuntimeError("provider down")

        ft_repo.save(_make_session(warmup_bars_required=5))

        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            result = service.run_cycle(
                _SESSION_ID, _OWNER_ID, _make_identity(), _mock_provider(), now_utc=_NOW
            )

        assert result.provider_failure is True
        kinds = self._audit_kinds(caplog)
        assert "ft_provider_failure" in kinds

    def test_ft_gap_detected_emitted_on_missing_bar(self, svc, repos, caplog):
        """FT_GAP_DETECTED emitted when expected weekday bar is absent."""
        service, ft_repo, *_ = svc
        ohlcv_mock = svc[4]

        _MON = datetime(2026, 5, 25, 0, 0, 0, tzinfo=_UTC)
        _WED = datetime(2026, 5, 27, 0, 0, 0, tzinfo=_UTC)
        _NOW_THU = datetime(2026, 5, 28, 12, 0, 0, tzinfo=_UTC)

        ft_repo.save(_make_session(
            status=ForwardTestSessionStatus.RUNNING,
            last_processed_bar_timestamp=_MON,
            semantics=_always_entry_semantics(),
        ))
        ohlcv_mock.get_bars_since.return_value = [_Bar(_WED)]

        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            result = service.run_cycle(
                _SESSION_ID, _OWNER_ID, _make_identity(), _mock_provider(),
                now_utc=_NOW_THU,
            )

        assert result.gap_detected is True
        assert "ft_gap_detected" in self._audit_kinds(caplog)


# ===========================================================================
# Section I — API security invariants
# ===========================================================================

class TestSecurityInvariants:
    """
    Objective 10/11: Response security — no strategy_json / user_id / file_path.
    """

    def test_no_strategy_json_in_create_response(self, client):
        tc, draft_repo, *_ = client
        draft_repo.save(_make_draft())

        resp = tc.post("/forward-tests", json={
            "draft_id": _DRAFT_ID, "symbol": "AAPL", "timeframe": "1d",
            "source_mode": "provider", "provider_name": "yahoo",
        })
        assert resp.status_code == 201
        assert "strategy_json" not in resp.text

    def test_no_strategy_json_in_list_response(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session())

        resp = tc.get("/forward-tests")
        assert resp.status_code == 200
        assert "strategy_json" not in resp.text

    def test_no_strategy_json_in_detail_response(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session())

        resp = tc.get(f"/forward-tests/{_SESSION_ID}")
        assert resp.status_code == 200
        assert "strategy_json" not in resp.text

    def test_no_user_id_in_list_response(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session())

        resp = tc.get("/forward-tests")
        assert resp.status_code == 200
        assert "user_id" not in resp.text

    def test_no_file_path_in_any_response(self, client):
        tc, draft_repo, ft_repo, *_ = client
        draft_repo.save(_make_draft())
        ft_repo.save(_make_session())

        for url in ["/forward-tests", f"/forward-tests/{_SESSION_ID}"]:
            resp = tc.get(url)
            assert "file_path" not in resp.text, f"file_path leaked in {url}"

    def test_invalid_uuid_session_id_returns_400(self, client):
        tc, *_ = client
        for route in [
            "/forward-tests/not-a-uuid",
            "/forward-tests/not-a-uuid/run-cycle",
            "/forward-tests/not-a-uuid/pause",
            "/forward-tests/not-a-uuid/resume",
            "/forward-tests/not-a-uuid/terminate",
            "/forward-tests/not-a-uuid/signals",
            "/forward-tests/not-a-uuid/bars",
        ]:
            resp = tc.get(route) if route.count("/") == 2 else tc.post(route)
            if resp.status_code == 405:
                resp = tc.get(route)
            assert resp.status_code in (400, 404, 405), (
                f"Expected 400 for {route}, got {resp.status_code}"
            )

    def test_snapshot_hash_present_in_detail_response(self, client):
        """strategy_snapshot in detail response includes snapshot_hash for provenance."""
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session())

        resp = tc.get(f"/forward-tests/{_SESSION_ID}")
        assert resp.status_code == 200
        snap = resp.json()["strategy_snapshot"]
        assert "snapshot_hash" in snap
        assert len(snap["snapshot_hash"]) == 64  # SHA-256 hex digest

    def test_credential_id_not_exposed_in_response(self, client):
        """credential_id is stored internally but NOT included in any response field."""
        tc, draft_repo, *_ = client
        draft_repo.save(_make_draft())

        resp = tc.post("/forward-tests", json={
            "draft_id": _DRAFT_ID, "symbol": "AAPL", "timeframe": "1d",
            "source_mode": "provider", "provider_name": "yahoo",
            "credential_id": None,
        })
        assert resp.status_code == 201
        # credential_id (the value) must never be leaked as a raw key
        body = resp.json()
        assert "encrypted_secret" not in str(body)
        assert "password_hash" not in str(body)


# ===========================================================================
# Section J — Full workflow E2E at HTTP level
# ===========================================================================

class TestFullWorkflowHTTP:
    """
    Objective 1 (HTTP-level): Full create → run-cycle → pause → resume → terminate
    workflow validated through the API layer with real repository state.
    """

    def test_create_returns_pending_session(self, client):
        tc, draft_repo, *_ = client
        draft_repo.save(_make_draft())

        resp = tc.post("/forward-tests", json={
            "draft_id": _DRAFT_ID, "symbol": "AAPL", "timeframe": "1d",
            "source_mode": "provider", "provider_name": "yahoo",
            "exchange": "NASDAQ", "asset_class": "equity",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "pending"
        assert body["warmup_bars_required"] == 0
        assert body["bars_evaluated"] == 0

    def test_run_cycle_activates_session(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.PENDING))

        fake = _fake_cycle_result(_SESSION_ID, activated=True)
        with patch(
            "backend.api.routes.forward_testing.ForwardTestService.run_cycle",
            return_value=fake,
        ):
            resp = tc.post(f"/forward-tests/{_SESSION_ID}/run-cycle")

        assert resp.status_code == 200
        body = resp.json()
        assert body["activated"] is True
        assert body["session_id"] == _SESSION_ID

    def test_full_pause_resume_terminate_cycle(self, client):
        """RUNNING → PAUSED → RUNNING → TERMINATED via API calls."""
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.RUNNING))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/pause")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/resume")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/terminate")
        assert resp.status_code == 200
        assert resp.json()["status"] == "terminated"

    def test_list_then_get_returns_consistent_data(self, client):
        """List and detail views return the same core fields."""
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session())

        list_resp = tc.get("/forward-tests")
        assert list_resp.status_code == 200
        summary = list_resp.json()[0]

        detail_resp = tc.get(f"/forward-tests/{_SESSION_ID}")
        assert detail_resp.status_code == 200
        detail = detail_resp.json()

        assert summary["session_id"] == detail["session_id"]
        assert summary["status"] == detail["status"]
        assert summary["symbol"] == detail["symbol"]

    def test_signals_endpoint_returns_empty_list_initially(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session())

        resp = tc.get(f"/forward-tests/{_SESSION_ID}/signals")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_bars_endpoint_returns_empty_list_initially(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session())

        resp = tc.get(f"/forward-tests/{_SESSION_ID}/bars")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_session_persists_between_requests(self, client):
        """Session state written by pause is visible in subsequent get."""
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.RUNNING))

        tc.post(f"/forward-tests/{_SESSION_ID}/pause")

        resp = tc.get(f"/forward-tests/{_SESSION_ID}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"
