"""
Forward Testing API route tests — Phase 4C.5.

Coverage:
 1.  POST /forward-tests — happy path: session created in PENDING
 2.  POST /forward-tests — draft not found → 404
 3.  POST /forward-tests — wrong draft owner → 404
 4.  POST /forward-tests — lifecycle too low (draft) → 422
 5.  POST /forward-tests — lifecycle too low (validated) → 422
 6.  GET  /forward-tests — returns own sessions only
 7.  GET  /forward-tests — other user sessions absent
 8.  GET  /forward-tests/{id} — happy path returns detail
 9.  GET  /forward-tests/{id} — wrong owner → 404
10.  GET  /forward-tests/{id} — invalid UUID → 400
11.  POST /forward-tests/{id}/run-cycle — catalog mode → 422
12.  POST /forward-tests/{id}/run-cycle — wrong owner → 404
13.  POST /forward-tests/{id}/run-cycle — happy path (patches ForwardTestService)
14.  POST /forward-tests/{id}/run-cycle — invalid UUID → 400
15.  POST /forward-tests/{id}/pause — happy path from RUNNING
16.  POST /forward-tests/{id}/pause — invalid transition from PENDING → 422
17.  POST /forward-tests/{id}/resume — happy path from PAUSED
18.  POST /forward-tests/{id}/resume — invalid transition from PENDING → 422
19.  POST /forward-tests/{id}/terminate — happy path from RUNNING
20.  POST /forward-tests/{id}/terminate — terminal state → 422
21.  GET  /forward-tests/{id}/signals — happy path (empty list)
22.  GET  /forward-tests/{id}/signals — wrong owner → 404
23.  GET  /forward-tests/{id}/bars — happy path (empty list)
24.  GET  /forward-tests/{id}/bars — wrong owner → 404
25.  Security: no strategy_json in list response
26.  Security: no user_id in list response
27.  Security: no file_path in any response
28.  Security: unauthenticated → 403 (no active subscription override)
29.  POST /forward-tests — response contains detail fields (not just summary)
30.  GET  /forward-tests/{id} — snapshot fields visible; strategy_json absent
"""
from __future__ import annotations

import hashlib
import uuid
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
from backend.forward_testing.models import (
    ForwardTestSession,
    ForwardTestSessionStatus,
    StrategySnapshot,
)
from backend.forward_testing.repository import ForwardTestRepository
from backend.forward_testing.service import CycleResult
from backend.forward_testing.stores import ForwardTestBarStore, ForwardTestSignalStore
from backend.strategy_registry.draft_repository import DraftRepository
from backend.strategy_registry.drafts import StrategyDraft
from backend.strategy_registry.lifecycle import StrategyLifecycleStatus
from backend.tools.registry import ToolRegistry
from backend.tools.toolset import StrategyToolSet

_UTC = timezone.utc
_NOW = datetime(2026, 5, 30, 12, 0, 0, tzinfo=_UTC)

# Must be valid UUIDs — ForwardTestSession validates user_id as UUID
_OWNER_ID      = "aaaaaaaa-0001-0001-0001-000000000001"
_OTHER_ID      = "bbbbbbbb-0002-0002-0002-000000000002"
_DRAFT_ID      = str(uuid.uuid4())
_SESSION_ID    = str(uuid.uuid4())
_OTHER_SESSION = str(uuid.uuid4())

_OWNER_USER = User(
    user_id=_OWNER_ID,
    username="owneruser",
    email="owner@example.com",
    password_hash="x",
    created_at="2024-01-01T00:00:00Z",
    role="user",
    subscription_status="active",
)

_OTHER_USER = User(
    user_id=_OTHER_ID,
    username="otheruser",
    email="other@example.com",
    password_hash="x",
    created_at="2024-01-01T00:00:00Z",
    role="user",
    subscription_status="active",
)


# ---------------------------------------------------------------------------
# Domain object builders
# ---------------------------------------------------------------------------

def _make_draft(
    draft_id: str = _DRAFT_ID,
    user_id: str = _OWNER_ID,
    lifecycle: StrategyLifecycleStatus = StrategyLifecycleStatus.BACKTESTED,
) -> StrategyDraft:
    return StrategyDraft(
        draft_id=draft_id,
        display_name="Unit Test Strategy",
        toolset=StrategyToolSet(toolset_id="ts_test", tools=()),
        created_at=_NOW,
        updated_at=_NOW,
        user_id=user_id,
        lifecycle_status=lifecycle,
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
) -> ForwardTestSession:
    draft = _make_draft(draft_id=draft_id, user_id=user_id)
    snapshot = _make_snapshot(draft)
    return ForwardTestSession(
        session_id=session_id,
        user_id=user_id,
        draft_id=draft_id,
        strategy_snapshot=snapshot,
        lifecycle_status_at_activation="backtested",
        source_mode=source_mode,
        provider_name="yahoo" if source_mode == "provider" else None,
        catalog_id="cat-001" if source_mode == "catalog" else None,
        symbol="AAPL",
        timeframe="1d",
        exchange="NASDAQ",
        asset_class="equity",
        warmup_bars_required=0,
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_cycle_result(session_id: str, activated: bool = True) -> CycleResult:
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repos(tmp_path: Path):
    """Real repositories backed by tmp_path."""
    draft_repo    = DraftRepository(tmp_path / "drafts")
    ft_repo       = ForwardTestRepository(tmp_path / "ft")
    signal_store  = ForwardTestSignalStore(tmp_path / "ft")
    bar_store     = ForwardTestBarStore(tmp_path / "ft")
    return draft_repo, ft_repo, signal_store, bar_store


@pytest.fixture
def client(repos):
    draft_repo, ft_repo, signal_store, bar_store = repos

    overrides = {
        get_draft_repository:          lambda: draft_repo,
        get_forward_test_repository:   lambda: ft_repo,
        get_forward_test_signal_store: lambda: signal_store,
        get_forward_test_bar_store:    lambda: bar_store,
        get_ohlcv_service:             lambda: MagicMock(),
        get_tool_registry:             lambda: ToolRegistry(),
        get_provider_factory:          lambda: MagicMock(),
        # Must use UUID-format user_id — ForwardTestSession.user_id is UUID-validated
        require_active_subscription:   lambda: _OWNER_USER,
    }
    app.dependency_overrides.update(overrides)
    yield TestClient(app), draft_repo, ft_repo, signal_store, bar_store
    for key in overrides:
        app.dependency_overrides.pop(key, None)


# ---------------------------------------------------------------------------
# 1. POST /forward-tests — happy path
# ---------------------------------------------------------------------------

class TestCreateSession:

    def test_create_happy_path(self, client):
        tc, draft_repo, ft_repo, *_ = client
        draft_repo.save(_make_draft())

        resp = tc.post("/forward-tests", json={
            "draft_id": _DRAFT_ID,
            "symbol": "AAPL",
            "timeframe": "1d",
            "source_mode": "provider",
            "provider_name": "yahoo",
            "exchange": "NASDAQ",
            "asset_class": "equity",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "pending"
        assert body["symbol"] == "AAPL"
        assert body["timeframe"] == "1d"
        assert body["source_mode"] == "provider"
        assert body["warmup_bars_required"] == 0
        assert "session_id" in body

    def test_create_response_has_detail_fields(self, client):
        tc, draft_repo, *_ = client
        draft_repo.save(_make_draft())

        resp = tc.post("/forward-tests", json={
            "draft_id": _DRAFT_ID,
            "symbol": "MSFT",
            "timeframe": "1h",
            "source_mode": "provider",
            "provider_name": "yahoo",
        })
        assert resp.status_code == 201
        body = resp.json()
        # Detail fields present
        assert "warmup_bars_required" in body
        assert "exchange" in body
        assert "asset_class" in body
        assert "lifecycle_status_at_activation" in body

    def test_create_draft_not_found(self, client):
        tc, *_ = client
        missing_id = str(uuid.uuid4())
        resp = tc.post("/forward-tests", json={
            "draft_id": missing_id,
            "symbol": "AAPL",
            "timeframe": "1d",
            "source_mode": "provider",
            "provider_name": "yahoo",
        })
        assert resp.status_code == 404

    def test_create_wrong_draft_owner(self, client):
        tc, draft_repo, *_ = client
        # Draft owned by OTHER user
        draft_repo.save(_make_draft(user_id=_OTHER_ID))

        resp = tc.post("/forward-tests", json={
            "draft_id": _DRAFT_ID,
            "symbol": "AAPL",
            "timeframe": "1d",
            "source_mode": "provider",
            "provider_name": "yahoo",
        })
        # Wrong-owner appears as 404 (information hiding)
        assert resp.status_code == 404

    def test_create_lifecycle_too_low_draft(self, client):
        tc, draft_repo, *_ = client
        draft_repo.save(_make_draft(lifecycle=StrategyLifecycleStatus.DRAFT))

        resp = tc.post("/forward-tests", json={
            "draft_id": _DRAFT_ID,
            "symbol": "AAPL",
            "timeframe": "1d",
            "source_mode": "provider",
            "provider_name": "yahoo",
        })
        assert resp.status_code == 422
        assert "lifecycle" in resp.json()["detail"].lower()

    def test_create_lifecycle_too_low_validated(self, client):
        tc, draft_repo, *_ = client
        draft_repo.save(_make_draft(lifecycle=StrategyLifecycleStatus.VALIDATED))

        resp = tc.post("/forward-tests", json={
            "draft_id": _DRAFT_ID,
            "symbol": "AAPL",
            "timeframe": "1d",
            "source_mode": "provider",
            "provider_name": "yahoo",
        })
        assert resp.status_code == 422

    def test_create_no_strategy_json_in_response(self, client):
        tc, draft_repo, *_ = client
        draft_repo.save(_make_draft())

        resp = tc.post("/forward-tests", json={
            "draft_id": _DRAFT_ID,
            "symbol": "AAPL",
            "timeframe": "1d",
            "source_mode": "provider",
            "provider_name": "yahoo",
        })
        assert resp.status_code == 201
        body_str = resp.text
        assert "strategy_json" not in body_str


# ---------------------------------------------------------------------------
# 2. GET /forward-tests — list sessions
# ---------------------------------------------------------------------------

class TestListSessions:

    def test_list_own_sessions(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session())

        resp = tc.get("/forward-tests")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["session_id"] == _SESSION_ID

    def test_list_cross_user_invisible(self, client):
        tc, _, ft_repo, *_ = client
        # Save a session owned by OTHER user
        ft_repo.save(_make_session(user_id=_OTHER_ID))

        resp = tc.get("/forward-tests")
        assert resp.status_code == 200
        # The default test user (_OWNER_ID) sees nothing
        assert resp.json() == []

    def test_list_no_user_id_in_response(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session())

        resp = tc.get("/forward-tests")
        assert resp.status_code == 200
        body_str = resp.text
        assert "user_id" not in body_str

    def test_list_no_strategy_json_in_response(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session())

        resp = tc.get("/forward-tests")
        assert resp.status_code == 200
        body_str = resp.text
        assert "strategy_json" not in body_str

    def test_list_no_file_path_in_response(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session())

        resp = tc.get("/forward-tests")
        assert resp.status_code == 200
        body_str = resp.text
        assert "file_path" not in body_str


# ---------------------------------------------------------------------------
# 3. GET /forward-tests/{session_id} — detail
# ---------------------------------------------------------------------------

class TestGetSession:

    def test_get_happy_path(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session())

        resp = tc.get(f"/forward-tests/{_SESSION_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == _SESSION_ID
        assert "warmup_bars_required" in body
        assert "exchange" in body

    def test_get_snapshot_fields_visible(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session())

        resp = tc.get(f"/forward-tests/{_SESSION_ID}")
        assert resp.status_code == 200
        snap = resp.json()["strategy_snapshot"]
        assert "snapshot_hash" in snap
        assert "display_name" in snap
        assert "strategy_json" not in snap

    def test_get_wrong_owner_404(self, client):
        tc, _, ft_repo, *_ = client
        # Session belongs to OTHER
        ft_repo.save(_make_session(user_id=_OTHER_ID))

        resp = tc.get(f"/forward-tests/{_SESSION_ID}")
        assert resp.status_code == 404

    def test_get_invalid_uuid_400(self, client):
        tc, *_ = client
        resp = tc.get("/forward-tests/not-a-valid-uuid")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 4. POST /forward-tests/{session_id}/run-cycle
# ---------------------------------------------------------------------------

class TestRunCycle:

    def test_run_cycle_catalog_rejected(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(source_mode="catalog"))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/run-cycle")
        assert resp.status_code == 422
        assert "catalog" in resp.json()["detail"].lower()

    def test_run_cycle_wrong_owner_404(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(user_id=_OTHER_ID, source_mode="provider"))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/run-cycle")
        assert resp.status_code == 404

    def test_run_cycle_invalid_uuid_400(self, client):
        tc, *_ = client
        resp = tc.post("/forward-tests/bad-uuid/run-cycle")
        assert resp.status_code == 400

    def test_run_cycle_happy_path(self, client):
        tc, _, ft_repo, *_ = client
        session = _make_session(source_mode="provider")
        ft_repo.save(session)

        fake_result = _make_cycle_result(_SESSION_ID, activated=True)

        with patch(
            "backend.api.routes.forward_testing.ForwardTestService.run_cycle",
            return_value=fake_result,
        ):
            resp = tc.post(f"/forward-tests/{_SESSION_ID}/run-cycle")

        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == _SESSION_ID
        assert body["activated"] is True
        assert body["status"] == "running"
        assert body["bars_fetched"] == 0


# ---------------------------------------------------------------------------
# 5. POST /forward-tests/{session_id}/pause
# ---------------------------------------------------------------------------

class TestPauseSession:

    def test_pause_happy_path_from_running(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.RUNNING))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/pause")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

    def test_pause_invalid_from_pending_422(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.PENDING))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/pause")
        assert resp.status_code == 422

    def test_pause_wrong_owner_404(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(user_id=_OTHER_ID, status=ForwardTestSessionStatus.RUNNING))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/pause")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. POST /forward-tests/{session_id}/resume
# ---------------------------------------------------------------------------

class TestResumeSession:

    def test_resume_happy_path_from_paused(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.PAUSED))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/resume")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_resume_invalid_from_pending_422(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.PENDING))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/resume")
        assert resp.status_code == 422

    def test_resume_wrong_owner_404(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(user_id=_OTHER_ID, status=ForwardTestSessionStatus.PAUSED))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/resume")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 7. POST /forward-tests/{session_id}/terminate
# ---------------------------------------------------------------------------

class TestTerminateSession:

    def test_terminate_happy_path_from_running(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.RUNNING))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/terminate")
        assert resp.status_code == 200
        assert resp.json()["status"] == "terminated"

    def test_terminate_happy_path_from_paused(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.PAUSED))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/terminate")
        assert resp.status_code == 200
        assert resp.json()["status"] == "terminated"

    def test_terminate_terminal_state_422(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(status=ForwardTestSessionStatus.TERMINATED))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/terminate")
        assert resp.status_code == 422

    def test_terminate_wrong_owner_404(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(user_id=_OTHER_ID, status=ForwardTestSessionStatus.RUNNING))

        resp = tc.post(f"/forward-tests/{_SESSION_ID}/terminate")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8. GET /forward-tests/{session_id}/signals
# ---------------------------------------------------------------------------

class TestListSignals:

    def test_signals_happy_path_empty(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session())

        resp = tc.get(f"/forward-tests/{_SESSION_ID}/signals")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_signals_wrong_owner_404(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(user_id=_OTHER_ID))

        resp = tc.get(f"/forward-tests/{_SESSION_ID}/signals")
        assert resp.status_code == 404

    def test_signals_invalid_uuid_400(self, client):
        tc, *_ = client
        resp = tc.get("/forward-tests/not-uuid/signals")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 9. GET /forward-tests/{session_id}/bars
# ---------------------------------------------------------------------------

class TestListBars:

    def test_bars_happy_path_empty(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session())

        resp = tc.get(f"/forward-tests/{_SESSION_ID}/bars")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_bars_wrong_owner_404(self, client):
        tc, _, ft_repo, *_ = client
        ft_repo.save(_make_session(user_id=_OTHER_ID))

        resp = tc.get(f"/forward-tests/{_SESSION_ID}/bars")
        assert resp.status_code == 404

    def test_bars_invalid_uuid_400(self, client):
        tc, *_ = client
        resp = tc.get("/forward-tests/not-uuid/bars")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 10. Authentication / entitlement
# ---------------------------------------------------------------------------

class TestAuthentication:

    def test_no_active_subscription_403(self, repos):
        """When the active-subscription dependency is not satisfied, return 403."""
        draft_repo, ft_repo, *_ = repos

        overrides = {
            get_draft_repository:          lambda: draft_repo,
            get_forward_test_repository:   lambda: ft_repo,
            get_forward_test_signal_store: lambda: ForwardTestSignalStore(Path("/tmp")),
            get_forward_test_bar_store:    lambda: ForwardTestBarStore(Path("/tmp")),
            get_ohlcv_service:             lambda: MagicMock(),
            get_tool_registry:             lambda: ToolRegistry(),
            get_provider_factory:          lambda: MagicMock(),
            # Override subscription to raise SubscriptionExpiredError
            require_active_subscription:   _raise_expired,
        }
        app.dependency_overrides.update(overrides)
        try:
            tc = TestClient(app, raise_server_exceptions=False)
            resp = tc.get("/forward-tests")
            assert resp.status_code in (401, 403)
        finally:
            for key in overrides:
                app.dependency_overrides.pop(key, None)


def _raise_expired():
    from fastapi import HTTPException
    raise HTTPException(status_code=403, detail="subscription_required")


# ---------------------------------------------------------------------------
# EXEC-2B: actionable_from_bar_timestamp in signal API response
# ---------------------------------------------------------------------------

class TestSignalsActionableFromBarTimestamp:
    """EXEC-2B: actionable_from_bar_timestamp is serialized in GET /signals responses."""

    def _write_signal(self, signal_store, session_id: str, actionable_ts=None):
        from backend.forward_testing.models import ForwardTestSignal
        import uuid as _uuid_mod

        now = datetime(2026, 5, 29, 0, 0, 0, tzinfo=_UTC)
        sig = ForwardTestSignal(
            signal_id=str(_uuid_mod.uuid4()),
            session_id=session_id,
            user_id=_OWNER_ID,
            bar_timestamp=now,
            signal_timestamp=now,
            signal_direction="entry_long",
            rule_id="entry_rule_1",
            bar_open=100.0,
            bar_high=105.0,
            bar_low=99.0,
            bar_close=103.0,
            bar_volume=1_000_000.0,
            warmup_satisfied=True,
            strategy_snapshot_hash="a" * 64,
            symbol="AAPL",
            timeframe="1d",
            provider_name="yahoo",
            created_at=now,
            actionable_from_bar_timestamp=actionable_ts,
        )
        signal_store.append_signal(sig)
        return sig

    def test_signal_response_includes_actionable_field(self, client):
        """Signal response always has actionable_from_bar_timestamp key."""
        tc, draft_repo, ft_repo, signal_store, bar_store = client
        ft_repo.save(_make_session())
        self._write_signal(signal_store, _SESSION_ID)

        resp = tc.get(f"/forward-tests/{_SESSION_ID}/signals")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert "actionable_from_bar_timestamp" in data[0]

    def test_signal_response_actionable_none_when_final_bar(self, client):
        """actionable_from_bar_timestamp is null in JSON when signal was on the final bar."""
        tc, draft_repo, ft_repo, signal_store, bar_store = client
        ft_repo.save(_make_session())
        self._write_signal(signal_store, _SESSION_ID, actionable_ts=None)

        resp = tc.get(f"/forward-tests/{_SESSION_ID}/signals")
        data = resp.json()
        assert data[0]["actionable_from_bar_timestamp"] is None

    def test_signal_response_actionable_iso_string_when_set(self, client):
        """actionable_from_bar_timestamp is an ISO-8601 string when set."""
        tc, draft_repo, ft_repo, signal_store, bar_store = client
        ft_repo.save(_make_session())
        next_ts = datetime(2026, 5, 30, 0, 0, 0, tzinfo=_UTC)
        self._write_signal(signal_store, _SESSION_ID, actionable_ts=next_ts)

        resp = tc.get(f"/forward-tests/{_SESSION_ID}/signals")
        data = resp.json()
        assert data[0]["actionable_from_bar_timestamp"] == next_ts.isoformat()


# ---------------------------------------------------------------------------
# 11. POST /forward-tests/{session_id}/promote-draft — Phase P1
# ---------------------------------------------------------------------------

def _make_session_with_evidence(
    session_id: str = _SESSION_ID,
    user_id: str = _OWNER_ID,
    draft_id: str = _DRAFT_ID,
    signal_eligible_bars_processed: int = 1,
    signals_recorded: int = 0,
    status: ForwardTestSessionStatus = ForwardTestSessionStatus.RUNNING,
) -> ForwardTestSession:
    """Session that has completed at least one evaluation cycle."""
    draft = _make_draft(draft_id=draft_id, user_id=user_id)
    snapshot = _make_snapshot(draft)
    return ForwardTestSession(
        session_id=session_id,
        user_id=user_id,
        draft_id=draft_id,
        strategy_snapshot=snapshot,
        lifecycle_status_at_activation="backtested",
        source_mode="provider",
        provider_name="yahoo",
        symbol="AAPL",
        timeframe="1d",
        exchange="NASDAQ",
        asset_class="equity",
        warmup_bars_required=0,
        status=status,
        signal_eligible_bars_processed=signal_eligible_bars_processed,
        signals_recorded=signals_recorded,
        bars_evaluated=signal_eligible_bars_processed,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _write_eligible_bars(
    bar_store: ForwardTestBarStore,
    session_id: str,
    count: int,
    *,
    start: datetime | None = None,
    same_day: bool = False,
) -> None:
    """
    Write `count` non-warmup bars into bar_store for session_id.

    By default each bar gets a distinct UTC date so calendar-day gate is satisfied.
    Pass same_day=True to put all bars on the same calendar date.
    """
    import json as _json
    from datetime import timedelta as _timedelta
    from backend.forward_testing.models import ForwardTestBar

    base = start or datetime(2026, 1, 2, 12, 0, 0, tzinfo=_UTC)
    bars_dir = bar_store._bars_dir
    bars_dir.mkdir(parents=True, exist_ok=True)
    bar_file = bars_dir / f"{session_id}.json"
    existing = _json.loads(bar_file.read_text()) if bar_file.exists() else []

    for i in range(count):
        ts = base + (_timedelta(minutes=i) if same_day else _timedelta(days=i))
        bar = ForwardTestBar(
            session_id=session_id,
            bar_index=len(existing) + i,
            bar_timestamp=ts,
            open=100.0, high=105.0, low=95.0, close=102.0, volume=1e6,
            source_mode="provider",
            provider_name="yahoo",
            is_warmup_bar=False,
            processed_at=base,
        )
        existing.append(_json.loads(bar.model_dump_json()))
    bar_file.write_text(_json.dumps(existing), encoding="utf-8")


class TestPromoteDraftToForwardTested:
    """
    Coverage (9 cases — Phase P1 + FT-2B hardening):

    1.  Happy path: backtested draft + 20 bars / 20 days → 200 (forward_tested)
    2.  Reject: 0 eligible bars → 422 (bar gate)
    3.  Reject: draft in 'validated' (not backtested) → 422
    4.  Reject: draft already 'forward_tested' → 422
    5.  Reject: session owned by other user → 404
    6.  Reject: session.draft_id != request draft_id → 422
    7.  Confirm: PUT /drafts/{id} cannot set lifecycle_status to forward_tested
    8.  Confirm: audit event emitted with evidence metadata (eligible_bars + calendar_days)
    9.  Notes passed through to updated draft
    """

    def test_happy_path_promotes_to_forward_tested(self, client):
        """Valid evidence (20 bars / 20 days) + backtested draft → forward_tested."""
        tc, draft_repo, ft_repo, signal_store, bar_store = client
        draft_repo.save(_make_draft(lifecycle=StrategyLifecycleStatus.BACKTESTED))
        ft_repo.save(_make_session_with_evidence(signal_eligible_bars_processed=20))
        _write_eligible_bars(bar_store, _SESSION_ID, 20)

        resp = tc.post(
            f"/forward-tests/{_SESSION_ID}/promote-draft",
            json={"draft_id": _DRAFT_ID},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["lifecycle_status"] == "forward_tested"
        assert body["draft_id"] == _DRAFT_ID

    def test_reject_no_evidence_zero_eligible_bars(self, client):
        """Session with 0 bars in bar store → 422 (bar gate)."""
        tc, draft_repo, ft_repo, *_ = client
        draft_repo.save(_make_draft(lifecycle=StrategyLifecycleStatus.BACKTESTED))
        ft_repo.save(_make_session_with_evidence(signal_eligible_bars_processed=0))
        # bar_store left empty — 0 eligible bars

        resp = tc.post(
            f"/forward-tests/{_SESSION_ID}/promote-draft",
            json={"draft_id": _DRAFT_ID},
        )

        assert resp.status_code == 422
        assert "0" in resp.json()["detail"]

    def test_reject_draft_not_backtested_validated(self, client):
        """Draft in 'validated' status (not backtested) → 422."""
        tc, draft_repo, ft_repo, signal_store, bar_store = client
        draft_repo.save(_make_draft(lifecycle=StrategyLifecycleStatus.VALIDATED))
        ft_repo.save(_make_session_with_evidence(signal_eligible_bars_processed=20))
        _write_eligible_bars(bar_store, _SESSION_ID, 20)

        resp = tc.post(
            f"/forward-tests/{_SESSION_ID}/promote-draft",
            json={"draft_id": _DRAFT_ID},
        )

        assert resp.status_code == 422
        assert "backtested" in resp.json()["detail"].lower()

    def test_reject_draft_already_forward_tested(self, client):
        """Draft already at 'forward_tested' → 422 (lifecycle transition not permitted)."""
        tc, draft_repo, ft_repo, signal_store, bar_store = client
        draft_repo.save(_make_draft(lifecycle=StrategyLifecycleStatus.FORWARD_TESTED))
        ft_repo.save(_make_session_with_evidence(signal_eligible_bars_processed=20))
        _write_eligible_bars(bar_store, _SESSION_ID, 20)

        resp = tc.post(
            f"/forward-tests/{_SESSION_ID}/promote-draft",
            json={"draft_id": _DRAFT_ID},
        )

        assert resp.status_code == 422

    def test_reject_cross_user_session_404(self, client):
        """Session owned by a different user → 404 (information hiding)."""
        tc, draft_repo, ft_repo, *_ = client
        draft_repo.save(_make_draft(lifecycle=StrategyLifecycleStatus.BACKTESTED))
        ft_repo.save(_make_session_with_evidence(user_id=_OTHER_ID))

        resp = tc.post(
            f"/forward-tests/{_SESSION_ID}/promote-draft",
            json={"draft_id": _DRAFT_ID},
        )

        assert resp.status_code == 404

    def test_reject_session_draft_id_mismatch(self, client):
        """Session was created for a different draft → 422."""
        tc, draft_repo, ft_repo, *_ = client
        different_draft_id = str(uuid.uuid4())
        draft_repo.save(_make_draft(lifecycle=StrategyLifecycleStatus.BACKTESTED))
        ft_repo.save(_make_session_with_evidence(draft_id=different_draft_id))

        resp = tc.post(
            f"/forward-tests/{_SESSION_ID}/promote-draft",
            json={"draft_id": _DRAFT_ID},
        )

        assert resp.status_code == 422
        assert _DRAFT_ID in resp.json()["detail"] or different_draft_id in resp.json()["detail"]

    def test_put_drafts_cannot_set_forward_tested(self, client):
        """PUT /drafts/{id} body with lifecycle_status='forward_tested' → 422."""
        tc, draft_repo, *_ = client
        draft_repo.save(_make_draft(lifecycle=StrategyLifecycleStatus.BACKTESTED))

        resp = tc.put(
            f"/drafts/{_DRAFT_ID}",
            json={"lifecycle_status": "forward_tested"},
        )

        assert resp.status_code == 422

    def test_audit_event_emitted_with_evidence_metadata(self, client):
        """Promotion emits a GOV_PROMOTION_REQUESTED audit event with FT-2B fields."""
        tc, draft_repo, ft_repo, signal_store, bar_store = client
        draft_repo.save(_make_draft(lifecycle=StrategyLifecycleStatus.BACKTESTED))
        ft_repo.save(_make_session_with_evidence(signal_eligible_bars_processed=20, signals_recorded=2))
        _write_eligible_bars(bar_store, _SESSION_ID, 20)

        captured: list = []
        with patch("backend.api.services.draft_service.emit_audit_event", side_effect=captured.append):
            resp = tc.post(
                f"/forward-tests/{_SESSION_ID}/promote-draft",
                json={"draft_id": _DRAFT_ID},
            )

        assert resp.status_code == 200
        assert len(captured) == 1
        evt = captured[0]
        assert evt.details["from_status"] == "backtested"
        assert evt.details["to_status"] == "forward_tested"
        assert evt.details["eligible_bars"] == 20
        assert evt.details["calendar_days"] == 20
        assert evt.details["signals_recorded"] == 2
        assert evt.details["session_id"] == _SESSION_ID
        assert evt.details["draft_id"] == _DRAFT_ID

    def test_notes_passed_through_to_draft(self, client):
        """Optional notes field is persisted to the updated draft."""
        tc, draft_repo, ft_repo, signal_store, bar_store = client
        draft_repo.save(_make_draft(lifecycle=StrategyLifecycleStatus.BACKTESTED))
        ft_repo.save(_make_session_with_evidence(signal_eligible_bars_processed=20))
        _write_eligible_bars(bar_store, _SESSION_ID, 20)

        resp = tc.post(
            f"/forward-tests/{_SESSION_ID}/promote-draft",
            json={"draft_id": _DRAFT_ID, "notes": "forward test passed on 2026-05-31"},
        )

        assert resp.status_code == 200
        assert resp.json()["notes"] == "forward test passed on 2026-05-31"
