"""
Paper Trading API route tests — Phase 4E.4.

Coverage:
 1.  POST /paper-trading/sessions — happy path: session + account created (PENDING)
 2.  POST /paper-trading/sessions — response has detail fields (account_id, simulation_assumptions)
 3.  POST /paper-trading/sessions — no strategy_json in response
 4.  POST /paper-trading/sessions — draft not found → 404
 5.  POST /paper-trading/sessions — wrong draft owner → 404 (information hiding)
 6.  POST /paper-trading/sessions — lifecycle too low (draft) → 422
 7.  POST /paper-trading/sessions — lifecycle too low (validated) → 422
 8.  POST /paper-trading/sessions — custom simulation_assumptions applied
 9.  GET  /paper-trading/sessions — returns own sessions only
10.  GET  /paper-trading/sessions — cross-user sessions invisible
11.  GET  /paper-trading/sessions — no user_id in response
12.  GET  /paper-trading/sessions — no strategy_json in response
13.  GET  /paper-trading/sessions/{id} — happy path returns detail
14.  GET  /paper-trading/sessions/{id} — snapshot fields visible; strategy_json absent
15.  GET  /paper-trading/sessions/{id} — wrong owner → 404
16.  GET  /paper-trading/sessions/{id} — invalid UUID → 400
17.  POST /paper-trading/sessions/{id}/run-cycle — catalog mode → 422
18.  POST /paper-trading/sessions/{id}/run-cycle — wrong owner → 404
19.  POST /paper-trading/sessions/{id}/run-cycle — invalid UUID → 400
20.  POST /paper-trading/sessions/{id}/run-cycle — happy path (patches PaperTradingService)
21.  POST /paper-trading/sessions/{id}/pause — happy path from RUNNING
22.  POST /paper-trading/sessions/{id}/pause — invalid transition from PENDING → 422
23.  POST /paper-trading/sessions/{id}/pause — wrong owner → 404
24.  POST /paper-trading/sessions/{id}/resume — happy path from PAUSED
25.  POST /paper-trading/sessions/{id}/resume — non-paused status → 422
26.  POST /paper-trading/sessions/{id}/resume — wrong owner → 404
27.  POST /paper-trading/sessions/{id}/terminate — happy path from RUNNING
28.  POST /paper-trading/sessions/{id}/terminate — terminal state → 422
29.  POST /paper-trading/sessions/{id}/terminate — wrong owner → 404
30.  GET  /paper-trading/sessions/{id}/signals — happy path (empty list)
31.  GET  /paper-trading/sessions/{id}/signals — wrong owner → 404
32.  GET  /paper-trading/sessions/{id}/orders — happy path (empty list)
33.  GET  /paper-trading/sessions/{id}/orders — wrong owner → 404
34.  GET  /paper-trading/sessions/{id}/fills — happy path (empty list)
35.  GET  /paper-trading/sessions/{id}/fills — wrong owner → 404
36.  GET  /paper-trading/sessions/{id}/positions — happy path (empty list)
37.  GET  /paper-trading/sessions/{id}/positions — wrong owner → 404
38.  GET  /paper-trading/sessions/{id}/account — happy path
39.  GET  /paper-trading/sessions/{id}/account — wrong owner → 404
40.  GET  /paper-trading/sessions/{id}/equity-curve — happy path (empty list)
41.  GET  /paper-trading/sessions/{id}/equity-curve — wrong owner → 404
42.  GET  /paper-trading/sessions/{id}/bars — happy path (empty list)
43.  GET  /paper-trading/sessions/{id}/bars — wrong owner → 404
44.  Security: no file_path in any response
45.  Security: unauthenticated → 403
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
    get_account_state_snapshot_store,
    get_draft_repository,
    get_forward_test_bar_store,
    get_forward_test_repository,
    get_forward_test_signal_store,
    get_ohlcv_service,
    get_paper_account_store,
    get_paper_fill_store,
    get_paper_order_store,
    get_paper_position_store,
    get_paper_trading_repository,
    get_provider_factory,
    get_tool_registry,
)
from backend.api.main import app
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.paper_trading.execution_stores import (
    PaperFillStore,
    PaperOrderStore,
    PaperPositionStore,
)
from backend.paper_trading.models import (
    PaperAccount,
    PaperAccountStatus,
    PaperStrategySnapshot,
    PaperTradingSession,
    PaperTradingSessionStatus,
    SimulationAssumptions,
)
from backend.paper_trading.repository import PaperTradingRepository
from backend.paper_trading.service import PaperCycleResult
from backend.paper_trading.stores import AccountStateSnapshotStore, PaperAccountStore
from backend.strategy_registry.draft_repository import DraftRepository
from backend.strategy_registry.drafts import StrategyDraft
from backend.strategy_registry.lifecycle import StrategyLifecycleStatus
from backend.tools.toolset import StrategyToolSet
from backend.forward_testing.models import (
    ForwardTestSession,
    ForwardTestSessionStatus,
    StrategySnapshot as FTStrategySnapshot,
)
from backend.forward_testing.repository import ForwardTestRepository
from backend.forward_testing.stores import ForwardTestBarStore, ForwardTestSignalStore

_UTC = timezone.utc
_NOW = datetime(2026, 5, 31, 12, 0, 0, tzinfo=_UTC)

_OWNER_ID        = "aaaaaaaa-0001-0001-0001-000000000001"
_OTHER_ID        = "bbbbbbbb-0002-0002-0002-000000000002"
_DRAFT_ID        = str(uuid.uuid4())
_SESSION_ID      = str(uuid.uuid4())
_ACCOUNT_ID      = str(uuid.uuid4())
_OTHER_SESSION   = str(uuid.uuid4())
_FT_SESSION_ID   = str(uuid.uuid4())

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
    lifecycle: StrategyLifecycleStatus = StrategyLifecycleStatus.FORWARD_TESTED,
) -> StrategyDraft:
    return StrategyDraft(
        draft_id=draft_id,
        display_name="PT Unit Test Strategy",
        toolset=StrategyToolSet(toolset_id="ts_pt_test", tools=()),
        created_at=_NOW,
        updated_at=_NOW,
        user_id=user_id,
        lifecycle_status=lifecycle,
    )


def _make_pt_session(
    session_id: str = _SESSION_ID,
    account_id: str = _ACCOUNT_ID,
    user_id: str = _OWNER_ID,
    draft_id: str = _DRAFT_ID,
    status: PaperTradingSessionStatus = PaperTradingSessionStatus.PENDING,
    source_mode: str = "provider",
    last_processed_bar_timestamp: datetime | None = None,
) -> PaperTradingSession:
    draft = _make_draft(draft_id=draft_id, user_id=user_id)
    strategy_json = draft.model_dump_json()
    snapshot_hash = hashlib.sha256(strategy_json.encode()).hexdigest()
    snapshot = PaperStrategySnapshot(
        draft_id=draft.draft_id,
        display_name=draft.display_name,
        lifecycle_status=draft.lifecycle_status.value,
        snapshot_hash=snapshot_hash,
        captured_at=_NOW,
        strategy_json=strategy_json,
    )
    assumptions = SimulationAssumptions(starting_cash=10_000.0)
    return PaperTradingSession(
        session_id=session_id,
        user_id=user_id,
        draft_id=draft_id,
        strategy_snapshot_hash=snapshot_hash,
        strategy_snapshot=snapshot,
        lifecycle_status_at_activation=draft.lifecycle_status.value,
        account_id=account_id,
        simulation_assumptions=assumptions,
        source_mode=source_mode,
        provider_name="yahoo" if source_mode == "provider" else None,
        catalog_id="cat-001" if source_mode == "catalog" else None,
        symbol="AAPL",
        timeframe="1d",
        exchange="NASDAQ",
        asset_class="equity",
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
        last_processed_bar_timestamp=last_processed_bar_timestamp,
    )


def _make_account(
    account_id: str = _ACCOUNT_ID,
    session_id: str = _SESSION_ID,
    user_id: str = _OWNER_ID,
) -> PaperAccount:
    return PaperAccount(
        account_id=account_id,
        session_id=session_id,
        user_id=user_id,
        currency="USD",
        starting_cash=10_000.0,
        cash_balance=10_000.0,
        equity=10_000.0,
        available_cash=10_000.0,
        peak_equity=10_000.0,
        current_drawdown_pct=0.0,
        status=PaperAccountStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_ft_session(
    session_id: str = _FT_SESSION_ID,
    user_id: str = _OWNER_ID,
    draft_id: str = _DRAFT_ID,
    signal_eligible_bars_processed: int = 5,
    status: ForwardTestSessionStatus = ForwardTestSessionStatus.RUNNING,
) -> ForwardTestSession:
    """Forward-test session with default evidence (5 eligible bars processed)."""
    draft = _make_draft(draft_id=draft_id, user_id=user_id)
    strategy_json = draft.model_dump_json()
    snapshot = FTStrategySnapshot(
        draft_id=draft.draft_id,
        display_name=draft.display_name,
        lifecycle_status=draft.lifecycle_status.value,
        snapshot_hash=hashlib.sha256(strategy_json.encode()).hexdigest(),
        captured_at=_NOW,
        strategy_json=strategy_json,
    )
    return ForwardTestSession(
        session_id=session_id,
        user_id=user_id,
        draft_id=draft_id,
        strategy_snapshot=snapshot,
        lifecycle_status_at_activation="forward_tested",
        source_mode="provider",
        provider_name="yahoo",
        symbol="AAPL",
        timeframe="1d",
        exchange="NASDAQ",
        asset_class="equity",
        warmup_bars_required=0,
        status=status,
        signal_eligible_bars_processed=signal_eligible_bars_processed,
        bars_evaluated=signal_eligible_bars_processed,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_cycle_result(
    session_id: str = _SESSION_ID,
    activated: bool = False,
) -> PaperCycleResult:
    return PaperCycleResult(
        session_id=session_id,
        status="running",
        bars_fetched=1,
        bars_processed=1,
        warmup_bars_processed=0,
        signal_eligible_bars_processed=1,
        signals_generated=0,
        signals_suppressed=0,
        pending_orders_resolved=0,
        orders_created=0,
        orders_rejected=0,
        fills_created=0,
        positions_opened=0,
        positions_closed=0,
        account_snapshot_created=True,
        last_processed_bar_timestamp=_NOW,
        gap_detected=False,
        provider_failure=False,
        activated=activated,
        drawdown_stop_triggered=False,
        message=None,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def stores(tmp_path: Path):
    """Real stores backed by tmp_path; mock for execution stores."""
    pt_repo        = PaperTradingRepository(tmp_path / "pt")
    account_store  = PaperAccountStore(tmp_path / "pt")
    snapshot_store = AccountStateSnapshotStore(tmp_path / "pt")
    order_store    = PaperOrderStore(tmp_path / "pt")
    fill_store     = PaperFillStore(tmp_path / "pt")
    position_store = PaperPositionStore(tmp_path / "pt")
    bar_store      = ForwardTestBarStore(tmp_path / "pt")
    signal_store   = ForwardTestSignalStore(tmp_path / "pt")
    draft_repo     = DraftRepository(tmp_path / "drafts")
    ft_repo        = ForwardTestRepository(tmp_path / "ft")
    return (
        pt_repo, account_store, snapshot_store,
        order_store, fill_store, position_store,
        bar_store, signal_store, draft_repo, ft_repo,
    )


@pytest.fixture
def client(stores):
    (
        pt_repo, account_store, snapshot_store,
        order_store, fill_store, position_store,
        bar_store, signal_store, draft_repo, ft_repo,
    ) = stores

    overrides = {
        get_draft_repository:               lambda: draft_repo,
        get_forward_test_repository:        lambda: ft_repo,
        get_paper_trading_repository:       lambda: pt_repo,
        get_paper_account_store:            lambda: account_store,
        get_account_state_snapshot_store:   lambda: snapshot_store,
        get_paper_order_store:              lambda: order_store,
        get_paper_fill_store:               lambda: fill_store,
        get_paper_position_store:           lambda: position_store,
        get_forward_test_bar_store:         lambda: bar_store,
        get_forward_test_signal_store:      lambda: signal_store,
        get_ohlcv_service:                  lambda: MagicMock(),
        get_tool_registry:                  lambda: MagicMock(),
        get_provider_factory:               lambda: MagicMock(),
        require_active_subscription:        lambda: _OWNER_USER,
    }
    app.dependency_overrides.update(overrides)
    yield (
        TestClient(app),
        pt_repo, account_store, snapshot_store,
        order_store, fill_store, position_store,
        bar_store, signal_store, draft_repo, ft_repo,
    )
    for key in overrides:
        app.dependency_overrides.pop(key, None)


# Convenience unpacker
def _tc(client_fixture):
    return client_fixture[0]


def _repo(client_fixture):
    return client_fixture[1]


def _accounts(client_fixture):
    return client_fixture[2]


def _drafts(client_fixture):
    return client_fixture[9]


def _ft_repo(client_fixture):
    return client_fixture[10]


_BASE = "/paper-trading/sessions"

_CREATE_BODY = {
    "draft_id": _DRAFT_ID,
    "symbol": "AAPL",
    "timeframe": "1d",
    "source_mode": "provider",
    "provider_name": "yahoo",
    "exchange": "NASDAQ",
    "asset_class": "equity",
}


# ---------------------------------------------------------------------------
# 1–8. POST /paper-trading/sessions
# ---------------------------------------------------------------------------

class TestCreateSession:

    def test_create_happy_path(self, client):
        tc = _tc(client)
        _drafts(client).save(_make_draft())

        resp = tc.post(_BASE, json=_CREATE_BODY)
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "pending"
        assert body["symbol"] == "AAPL"
        assert body["timeframe"] == "1d"
        assert "session_id" in body
        assert "account_id" in body

    def test_create_response_has_detail_fields(self, client):
        tc = _tc(client)
        _drafts(client).save(_make_draft())

        resp = tc.post(_BASE, json=_CREATE_BODY)
        assert resp.status_code == 201
        body = resp.json()
        assert "account_id" in body
        assert "simulation_assumptions" in body
        assert "lifecycle_status_at_activation" in body
        assert "forward_test_session_id" in body

    def test_create_no_strategy_json_in_response(self, client):
        tc = _tc(client)
        _drafts(client).save(_make_draft())

        resp = tc.post(_BASE, json=_CREATE_BODY)
        assert resp.status_code == 201
        assert "strategy_json" not in resp.text

    def test_create_draft_not_found(self, client):
        tc = _tc(client)
        missing_id = str(uuid.uuid4())
        resp = tc.post(_BASE, json={**_CREATE_BODY, "draft_id": missing_id})
        assert resp.status_code == 404

    def test_create_wrong_draft_owner(self, client):
        tc = _tc(client)
        _drafts(client).save(_make_draft(user_id=_OTHER_ID))

        resp = tc.post(_BASE, json=_CREATE_BODY)
        assert resp.status_code == 404

    def test_create_lifecycle_too_low_draft(self, client):
        tc = _tc(client)
        _drafts(client).save(_make_draft(lifecycle=StrategyLifecycleStatus.DRAFT))

        resp = tc.post(_BASE, json=_CREATE_BODY)
        assert resp.status_code == 422
        assert "lifecycle" in resp.json()["detail"].lower()

    def test_create_lifecycle_too_low_validated(self, client):
        tc = _tc(client)
        _drafts(client).save(_make_draft(lifecycle=StrategyLifecycleStatus.VALIDATED))

        resp = tc.post(_BASE, json=_CREATE_BODY)
        assert resp.status_code == 422

    def test_create_lifecycle_too_low_backtested(self, client):
        """BACKTESTED is no longer sufficient — draft must be forward_tested (Phase P2)."""
        tc = _tc(client)
        _drafts(client).save(_make_draft(lifecycle=StrategyLifecycleStatus.BACKTESTED))

        resp = tc.post(_BASE, json=_CREATE_BODY)
        assert resp.status_code == 422
        detail = resp.json()["detail"].lower()
        assert "forward-tested" in detail or "forward_tested" in detail

    def test_create_custom_assumptions_applied(self, client):
        tc = _tc(client)
        _drafts(client).save(_make_draft())

        body = {
            **_CREATE_BODY,
            "simulation_assumptions": {
                "starting_cash": 25_000.0,
                "fill_timing_model": "signal_bar_close",
                "fee_mode": "flat",
                "fee_value": 5.0,
                "position_size_mode": "fixed_quantity",
                "position_size_value": 50.0,
                "max_concurrent_positions": 3,
            },
        }
        resp = tc.post(_BASE, json=body)
        assert resp.status_code == 201
        sa = resp.json()["simulation_assumptions"]
        assert sa["starting_cash"] == 25_000.0
        assert sa["fill_timing_model"] == "signal_bar_close"
        assert sa["fee_mode"] == "flat"
        assert sa["fee_value"] == 5.0
        assert sa["max_concurrent_positions"] == 3


# ---------------------------------------------------------------------------
# P2 — Eligibility Gate, FT Session Validation, Ownership, Atomicity
# ---------------------------------------------------------------------------

class TestCreateSessionP2:
    """
    Phase P2 hardening tests.

    Coverage:
     P2.1  — forward_test_session_id: not found → 404
     P2.2  — forward_test_session_id: wrong owner → 404
     P2.3  — forward_test_session_id: draft mismatch → 422
     P2.4  — forward_test_session_id: no evidence (0 eligible bars) → 422
     P2.5  — forward_test_session_id present and valid → 201
     P2.6  — forward_test_session_id not required (None → still creates)
     P2.7  — forward_test_session_id stored in response detail
     P2.8  — atomicity: account save failure leaves no orphan session
     P2.9  — error message mentions 'forward_tested' on lifecycle rejection
     P2.10 — cross-user draft → 404 (not 422)
    """

    def test_ft_session_not_found_404(self, client):
        """forward_test_session_id that doesn't exist → 404."""
        tc = _tc(client)
        _drafts(client).save(_make_draft())  # forward_tested by default
        missing_ft_id = str(uuid.uuid4())

        resp = tc.post(_BASE, json={
            **_CREATE_BODY,
            "forward_test_session_id": missing_ft_id,
        })
        assert resp.status_code == 404

    def test_ft_session_wrong_owner_404(self, client):
        """FT session owned by another user → 404 (information hiding)."""
        tc = _tc(client)
        _drafts(client).save(_make_draft())
        _ft_repo(client).save(_make_ft_session(user_id=_OTHER_ID))

        resp = tc.post(_BASE, json={
            **_CREATE_BODY,
            "forward_test_session_id": _FT_SESSION_ID,
        })
        assert resp.status_code == 404

    def test_ft_session_draft_mismatch_422(self, client):
        """FT session references a different draft → 422."""
        tc = _tc(client)
        _drafts(client).save(_make_draft())
        different_draft_id = str(uuid.uuid4())
        _ft_repo(client).save(_make_ft_session(draft_id=different_draft_id))

        resp = tc.post(_BASE, json={
            **_CREATE_BODY,
            "forward_test_session_id": _FT_SESSION_ID,
        })
        assert resp.status_code == 422
        assert "does not reference this draft" in resp.json()["detail"]

    def test_ft_session_no_evidence_422(self, client):
        """FT session with 0 signal_eligible_bars_processed → 422."""
        tc = _tc(client)
        _drafts(client).save(_make_draft())
        _ft_repo(client).save(_make_ft_session(signal_eligible_bars_processed=0))

        resp = tc.post(_BASE, json={
            **_CREATE_BODY,
            "forward_test_session_id": _FT_SESSION_ID,
        })
        assert resp.status_code == 422
        detail = resp.json()["detail"].lower()
        assert "eligible" in detail or "evidence" in detail

    def test_ft_session_valid_creates_session(self, client):
        """Valid FT session with evidence → 201, ft session ID in response."""
        tc = _tc(client)
        _drafts(client).save(_make_draft())
        _ft_repo(client).save(_make_ft_session(signal_eligible_bars_processed=3))

        resp = tc.post(_BASE, json={
            **_CREATE_BODY,
            "forward_test_session_id": _FT_SESSION_ID,
        })
        assert resp.status_code == 201
        assert resp.json()["forward_test_session_id"] == _FT_SESSION_ID

    def test_ft_session_id_optional_none_still_creates(self, client):
        """forward_test_session_id is optional — omitting it still succeeds."""
        tc = _tc(client)
        _drafts(client).save(_make_draft())

        resp = tc.post(_BASE, json=_CREATE_BODY)
        assert resp.status_code == 201
        assert resp.json()["forward_test_session_id"] is None

    def test_ft_session_id_stored_in_detail_response(self, client):
        """FT session ID is recorded in the created session detail."""
        tc = _tc(client)
        _drafts(client).save(_make_draft())
        _ft_repo(client).save(_make_ft_session())

        resp = tc.post(_BASE, json={
            **_CREATE_BODY,
            "forward_test_session_id": _FT_SESSION_ID,
        })
        assert resp.status_code == 201
        assert resp.json()["forward_test_session_id"] == _FT_SESSION_ID

    def test_atomicity_account_save_failure_no_orphan_session(self, client):
        """
        If account save fails, no orphan session should remain in the repository.

        With account-first ordering (P2.5): account fails → session is never
        written → pt_repository stays empty.
        """
        tc = _tc(client)
        pt_repo = _repo(client)
        _drafts(client).save(_make_draft())

        with patch.object(_accounts(client), "save", side_effect=RuntimeError("disk full")):
            resp = tc.post(_BASE, json=_CREATE_BODY)

        assert resp.status_code == 500
        # No orphan session in repository
        sessions = pt_repo.list_all(owner_id=_OWNER_ID)
        assert sessions == []

    def test_lifecycle_error_message_mentions_forward_tested(self, client):
        """Lifecycle rejection message guides user toward 'forward_tested'."""
        tc = _tc(client)
        _drafts(client).save(_make_draft(lifecycle=StrategyLifecycleStatus.BACKTESTED))

        resp = tc.post(_BASE, json=_CREATE_BODY)
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "forward_tested" in detail or "forward-tested" in detail.lower()

    def test_cross_user_draft_returns_404_not_422(self, client):
        """Cross-user draft access must return 404, not 422 (no lifecycle info leakage)."""
        tc = _tc(client)
        _drafts(client).save(_make_draft(user_id=_OTHER_ID))

        resp = tc.post(_BASE, json=_CREATE_BODY)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 9–12. GET /paper-trading/sessions
# ---------------------------------------------------------------------------

class TestListSessions:

    def test_list_own_sessions(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session())

        resp = tc.get(_BASE)
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["session_id"] == _SESSION_ID

    def test_list_cross_user_invisible(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(user_id=_OTHER_ID))

        resp = tc.get(_BASE)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_no_user_id_in_response(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session())

        resp = tc.get(_BASE)
        assert resp.status_code == 200
        assert "user_id" not in resp.text

    def test_list_no_strategy_json_in_response(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session())

        resp = tc.get(_BASE)
        assert resp.status_code == 200
        assert "strategy_json" not in resp.text


# ---------------------------------------------------------------------------
# 13–16. GET /paper-trading/sessions/{session_id}
# ---------------------------------------------------------------------------

class TestGetSession:

    def test_get_happy_path(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session())

        resp = tc.get(f"{_BASE}/{_SESSION_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == _SESSION_ID
        assert "account_id" in body
        assert "simulation_assumptions" in body

    def test_get_snapshot_fields_visible_strategy_json_absent(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session())

        resp = tc.get(f"{_BASE}/{_SESSION_ID}")
        assert resp.status_code == 200
        snap = resp.json()["strategy_snapshot"]
        assert "snapshot_hash" in snap
        assert "display_name" in snap
        assert "strategy_json" not in snap

    def test_get_wrong_owner_404(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(user_id=_OTHER_ID))

        resp = tc.get(f"{_BASE}/{_SESSION_ID}")
        assert resp.status_code == 404

    def test_get_invalid_uuid_400(self, client):
        tc = _tc(client)
        resp = tc.get(f"{_BASE}/not-a-uuid")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 17–20. POST /paper-trading/sessions/{session_id}/run-cycle
# ---------------------------------------------------------------------------

class TestRunCycle:

    def test_run_cycle_catalog_mode_422(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(source_mode="catalog"))

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/run-cycle")
        assert resp.status_code == 422
        assert "catalog" in resp.json()["detail"].lower()

    def test_run_cycle_wrong_owner_404(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(user_id=_OTHER_ID))

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/run-cycle")
        assert resp.status_code == 404

    def test_run_cycle_invalid_uuid_400(self, client):
        tc = _tc(client)
        resp = tc.post(f"{_BASE}/not-a-uuid/run-cycle")
        assert resp.status_code == 400

    def test_run_cycle_happy_path(self, client):
        tc = _tc(client)
        session = _make_pt_session(status=PaperTradingSessionStatus.RUNNING)
        _repo(client).save(session)

        mock_result = _make_cycle_result(activated=False)

        with patch(
            "backend.api.routes.paper_trading.PaperTradingService"
        ) as MockService:
            instance = MockService.return_value
            instance.run_cycle.return_value = mock_result

            # Need provider factory to not raise
            with patch(
                "backend.api.routes.paper_trading._resolve_provider_api_key",
                return_value=None,
            ):
                mock_factory = MagicMock()
                mock_factory.build.return_value = MagicMock()

                # Override factory in app
                app.dependency_overrides[get_provider_factory] = lambda: mock_factory

                resp = tc.post(f"{_BASE}/{_SESSION_ID}/run-cycle")

        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == _SESSION_ID
        assert body["bars_fetched"] == 1
        assert body["activated"] is False
        assert body["drawdown_stop_triggered"] is False


# ---------------------------------------------------------------------------
# 21–23. POST /paper-trading/sessions/{session_id}/pause
# ---------------------------------------------------------------------------

class TestPauseSession:

    def test_pause_from_running(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(status=PaperTradingSessionStatus.RUNNING))

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/pause")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

    def test_pause_from_pending_422(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(status=PaperTradingSessionStatus.PENDING))

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/pause")
        assert resp.status_code == 422

    def test_pause_wrong_owner_404(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(
            user_id=_OTHER_ID,
            status=PaperTradingSessionStatus.RUNNING,
        ))

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/pause")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 24–26. POST /paper-trading/sessions/{session_id}/resume
# ---------------------------------------------------------------------------

class TestResumeSession:

    def test_resume_from_paused(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(status=PaperTradingSessionStatus.PAUSED))

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/resume")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_resume_from_pending_422(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(status=PaperTradingSessionStatus.PENDING))

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/resume")
        assert resp.status_code == 422
        assert "paused" in resp.json()["detail"].lower()

    def test_resume_wrong_owner_404(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(
            user_id=_OTHER_ID,
            status=PaperTradingSessionStatus.PAUSED,
        ))

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/resume")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 27–29. POST /paper-trading/sessions/{session_id}/terminate
# ---------------------------------------------------------------------------

class TestTerminateSession:

    def test_terminate_from_running(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(status=PaperTradingSessionStatus.RUNNING))

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/terminate")
        assert resp.status_code == 200
        assert resp.json()["status"] == "terminated"

    def test_terminate_from_terminal_422(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(status=PaperTradingSessionStatus.TERMINATED))

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/terminate")
        assert resp.status_code == 422

    def test_terminate_wrong_owner_404(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(
            user_id=_OTHER_ID,
            status=PaperTradingSessionStatus.RUNNING,
        ))

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/terminate")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 30–31. GET /paper-trading/sessions/{session_id}/signals
# ---------------------------------------------------------------------------

class TestListSignals:

    def test_signals_empty(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session())

        resp = tc.get(f"{_BASE}/{_SESSION_ID}/signals")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_signals_wrong_owner_404(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(user_id=_OTHER_ID))

        resp = tc.get(f"{_BASE}/{_SESSION_ID}/signals")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 32–33. GET /paper-trading/sessions/{session_id}/orders
# ---------------------------------------------------------------------------

class TestListOrders:

    def test_orders_empty(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session())

        resp = tc.get(f"{_BASE}/{_SESSION_ID}/orders")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_orders_wrong_owner_404(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(user_id=_OTHER_ID))

        resp = tc.get(f"{_BASE}/{_SESSION_ID}/orders")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 34–35. GET /paper-trading/sessions/{session_id}/fills
# ---------------------------------------------------------------------------

class TestListFills:

    def test_fills_empty(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session())

        resp = tc.get(f"{_BASE}/{_SESSION_ID}/fills")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_fills_wrong_owner_404(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(user_id=_OTHER_ID))

        resp = tc.get(f"{_BASE}/{_SESSION_ID}/fills")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 36–37. GET /paper-trading/sessions/{session_id}/positions
# ---------------------------------------------------------------------------

class TestListPositions:

    def test_positions_empty(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session())

        resp = tc.get(f"{_BASE}/{_SESSION_ID}/positions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_positions_wrong_owner_404(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(user_id=_OTHER_ID))

        resp = tc.get(f"{_BASE}/{_SESSION_ID}/positions")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 38–39. GET /paper-trading/sessions/{session_id}/account
# ---------------------------------------------------------------------------

class TestGetAccount:

    def test_account_happy_path(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session())
        _accounts(client).save(_make_account())

        resp = tc.get(f"{_BASE}/{_SESSION_ID}/account")
        assert resp.status_code == 200
        body = resp.json()
        assert body["account_id"] == _ACCOUNT_ID
        assert body["session_id"] == _SESSION_ID
        assert body["currency"] == "USD"
        assert body["starting_cash"] == 10_000.0
        assert body["equity"] == 10_000.0
        assert body["current_drawdown_pct"] == 0.0
        assert "user_id" not in resp.text

    def test_account_wrong_owner_404(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(user_id=_OTHER_ID))

        resp = tc.get(f"{_BASE}/{_SESSION_ID}/account")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 40–41. GET /paper-trading/sessions/{session_id}/equity-curve
# ---------------------------------------------------------------------------

class TestGetEquityCurve:

    def test_equity_curve_empty(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session())

        resp = tc.get(f"{_BASE}/{_SESSION_ID}/equity-curve")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_equity_curve_wrong_owner_404(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(user_id=_OTHER_ID))

        resp = tc.get(f"{_BASE}/{_SESSION_ID}/equity-curve")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 42–43. GET /paper-trading/sessions/{session_id}/bars
# ---------------------------------------------------------------------------

class TestListBars:

    def test_bars_empty(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session())

        resp = tc.get(f"{_BASE}/{_SESSION_ID}/bars")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_bars_wrong_owner_404(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(user_id=_OTHER_ID))

        resp = tc.get(f"{_BASE}/{_SESSION_ID}/bars")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 44–45. Security invariants
# ---------------------------------------------------------------------------

class TestSecurity:

    def test_no_file_path_in_response(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session())

        resp = tc.get(f"{_BASE}/{_SESSION_ID}")
        assert resp.status_code == 200
        assert "file_path" not in resp.text

    def test_unauthenticated_403(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session())

        # Override subscription requirement to simulate unauthenticated access
        from fastapi import HTTPException

        def _deny():
            raise HTTPException(status_code=403, detail="no subscription")

        app.dependency_overrides[require_active_subscription] = _deny
        try:
            resp = tc.get(_BASE)
            assert resp.status_code == 403
        finally:
            app.dependency_overrides[require_active_subscription] = lambda: _OWNER_USER


# ---------------------------------------------------------------------------
# P7. POST /paper-trading/sessions/{session_id}/promote-draft
# ---------------------------------------------------------------------------

def _save_promotion_snapshot(client_fixture) -> None:
    """Write a minimal AccountStateSnapshot to satisfy P8C snapshot evidence gate."""
    from backend.paper_trading.models import AccountStateSnapshot
    snap = AccountStateSnapshot(
        snapshot_id=str(uuid.uuid4()),
        session_id=_SESSION_ID,
        account_id=_ACCOUNT_ID,
        user_id=_OWNER_ID,
        bar_timestamp=_NOW,
        snapshot_timestamp=_NOW,
        cash_balance=10_000.0,
        equity=10_000.0,
        available_cash=10_000.0,
        peak_equity=10_000.0,
        current_drawdown_pct=0.0,
        open_position_count=0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        created_at=_NOW,
    )
    _snapshot_store(client_fixture).append(snap)


class TestPromoteDraftToPaperTested:

    _PROMOTE_BODY = {"draft_id": _DRAFT_ID}

    def test_happy_path_returns_paper_tested(self, client):
        """Session terminated + bar processed + snapshot → 200, paper_tested."""
        tc = _tc(client)
        _drafts(client).save(_make_draft(lifecycle=StrategyLifecycleStatus.FORWARD_TESTED))
        _repo(client).save(_make_pt_session(
            status=PaperTradingSessionStatus.TERMINATED,
            last_processed_bar_timestamp=_NOW,
        ))
        _save_promotion_snapshot(client)

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/promote-draft", json=self._PROMOTE_BODY)
        assert resp.status_code == 200
        assert resp.json()["lifecycle_status"] == "paper_tested"

    def test_session_never_run_returns_422(self, client):
        """Session.last_processed_bar_timestamp is None → 422 (no bar evidence)."""
        tc = _tc(client)
        _drafts(client).save(_make_draft(lifecycle=StrategyLifecycleStatus.FORWARD_TESTED))
        _repo(client).save(_make_pt_session(
            status=PaperTradingSessionStatus.TERMINATED,
            last_processed_bar_timestamp=None,
        ))

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/promote-draft", json=self._PROMOTE_BODY)
        assert resp.status_code == 422
        assert "bars" in resp.json()["detail"].lower()

    def test_draft_not_found_returns_404(self, client):
        """Draft absent → 404."""
        tc = _tc(client)
        _repo(client).save(_make_pt_session(
            status=PaperTradingSessionStatus.TERMINATED,
            last_processed_bar_timestamp=_NOW,
        ))

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/promote-draft", json=self._PROMOTE_BODY)
        assert resp.status_code == 404

    def test_draft_wrong_owner_returns_404(self, client):
        """Draft exists but belongs to a different user → 404 (information hiding)."""
        tc = _tc(client)
        _drafts(client).save(_make_draft(user_id=_OTHER_ID, lifecycle=StrategyLifecycleStatus.FORWARD_TESTED))
        _repo(client).save(_make_pt_session(
            status=PaperTradingSessionStatus.TERMINATED,
            last_processed_bar_timestamp=_NOW,
        ))

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/promote-draft", json=self._PROMOTE_BODY)
        assert resp.status_code == 404

    def test_draft_not_forward_tested_returns_422(self, client):
        """Draft is backtested (not forward_tested) → 422."""
        tc = _tc(client)
        _drafts(client).save(_make_draft(lifecycle=StrategyLifecycleStatus.BACKTESTED))
        _repo(client).save(_make_pt_session(
            status=PaperTradingSessionStatus.TERMINATED,
            last_processed_bar_timestamp=_NOW,
        ))

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/promote-draft", json=self._PROMOTE_BODY)
        assert resp.status_code == 422
        assert "forward_tested" in resp.json()["detail"].lower()

    def test_draft_already_paper_tested_returns_422(self, client):
        """Draft already paper_tested → lifecycle transition invalid → 422."""
        tc = _tc(client)
        _drafts(client).save(_make_draft(lifecycle=StrategyLifecycleStatus.PAPER_TESTED))
        _repo(client).save(_make_pt_session(
            status=PaperTradingSessionStatus.TERMINATED,
            last_processed_bar_timestamp=_NOW,
        ))

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/promote-draft", json=self._PROMOTE_BODY)
        assert resp.status_code == 422

    def test_session_wrong_owner_returns_404(self, client):
        """Session belongs to a different user → 404 (information hiding)."""
        tc = _tc(client)
        _drafts(client).save(_make_draft(lifecycle=StrategyLifecycleStatus.FORWARD_TESTED))
        _repo(client).save(_make_pt_session(
            user_id=_OTHER_ID,
            status=PaperTradingSessionStatus.TERMINATED,
            last_processed_bar_timestamp=_NOW,
        ))

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/promote-draft", json=self._PROMOTE_BODY)
        assert resp.status_code == 404

    def test_session_draft_mismatch_returns_422(self, client):
        """Session references a different draft → 422."""
        tc = _tc(client)
        other_draft_id = str(uuid.uuid4())
        _drafts(client).save(_make_draft(lifecycle=StrategyLifecycleStatus.FORWARD_TESTED))
        _repo(client).save(_make_pt_session(
            draft_id=other_draft_id,
            status=PaperTradingSessionStatus.TERMINATED,
            last_processed_bar_timestamp=_NOW,
        ))

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/promote-draft", json=self._PROMOTE_BODY)
        assert resp.status_code == 422
        assert "draft" in resp.json()["detail"].lower()

    def test_notes_stored_in_draft(self, client):
        """notes field is persisted and returned in the response."""
        tc = _tc(client)
        _drafts(client).save(_make_draft(lifecycle=StrategyLifecycleStatus.FORWARD_TESTED))
        _repo(client).save(_make_pt_session(
            status=PaperTradingSessionStatus.TERMINATED,
            last_processed_bar_timestamp=_NOW,
        ))
        _save_promotion_snapshot(client)

        body = {"draft_id": _DRAFT_ID, "notes": "paper cycle complete, all checks pass"}
        resp = tc.post(f"{_BASE}/{_SESSION_ID}/promote-draft", json=body)
        assert resp.status_code == 200
        assert resp.json()["notes"] == "paper cycle complete, all checks pass"

    def test_response_has_no_strategy_json(self, client):
        """Response must not contain strategy_json (security invariant)."""
        tc = _tc(client)
        _drafts(client).save(_make_draft(lifecycle=StrategyLifecycleStatus.FORWARD_TESTED))
        _repo(client).save(_make_pt_session(
            status=PaperTradingSessionStatus.TERMINATED,
            last_processed_bar_timestamp=_NOW,
        ))
        _save_promotion_snapshot(client)

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/promote-draft", json=self._PROMOTE_BODY)
        assert resp.status_code == 200
        assert "strategy_json" not in resp.text

    # P8C — hardened evidence gate tests

    def test_running_session_rejected_422(self, client):
        """Session status RUNNING → not finalized → 422."""
        tc = _tc(client)
        _drafts(client).save(_make_draft(lifecycle=StrategyLifecycleStatus.FORWARD_TESTED))
        _repo(client).save(_make_pt_session(
            status=PaperTradingSessionStatus.RUNNING,
            last_processed_bar_timestamp=_NOW,
        ))
        _save_promotion_snapshot(client)

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/promote-draft", json=self._PROMOTE_BODY)
        assert resp.status_code == 422
        assert "terminated" in resp.json()["detail"].lower() or "completed" in resp.json()["detail"].lower()

    def test_paused_session_rejected_422(self, client):
        """Session status PAUSED → not finalized → 422."""
        tc = _tc(client)
        _drafts(client).save(_make_draft(lifecycle=StrategyLifecycleStatus.FORWARD_TESTED))
        _repo(client).save(_make_pt_session(
            status=PaperTradingSessionStatus.PAUSED,
            last_processed_bar_timestamp=_NOW,
        ))
        _save_promotion_snapshot(client)

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/promote-draft", json=self._PROMOTE_BODY)
        assert resp.status_code == 422
        assert "terminated" in resp.json()["detail"].lower() or "completed" in resp.json()["detail"].lower()

    def test_failed_session_rejected_422(self, client):
        """Session status FAILED → excluded from promotion → 422."""
        tc = _tc(client)
        _drafts(client).save(_make_draft(lifecycle=StrategyLifecycleStatus.FORWARD_TESTED))
        _repo(client).save(_make_pt_session(
            status=PaperTradingSessionStatus.FAILED,
            last_processed_bar_timestamp=_NOW,
        ))
        _save_promotion_snapshot(client)

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/promote-draft", json=self._PROMOTE_BODY)
        assert resp.status_code == 422
        assert "terminated" in resp.json()["detail"].lower() or "completed" in resp.json()["detail"].lower()

    def test_no_snapshots_rejected_422(self, client):
        """Session has bars processed but zero equity snapshots → 422."""
        tc = _tc(client)
        _drafts(client).save(_make_draft(lifecycle=StrategyLifecycleStatus.FORWARD_TESTED))
        _repo(client).save(_make_pt_session(
            status=PaperTradingSessionStatus.TERMINATED,
            last_processed_bar_timestamp=_NOW,
        ))
        # No snapshot saved

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/promote-draft", json=self._PROMOTE_BODY)
        assert resp.status_code == 422
        assert "snapshot" in resp.json()["detail"].lower()

    def test_completed_session_accepted(self, client):
        """Session status COMPLETED (natural end) is also promotion-eligible."""
        tc = _tc(client)
        _drafts(client).save(_make_draft(lifecycle=StrategyLifecycleStatus.FORWARD_TESTED))
        _repo(client).save(_make_pt_session(
            status=PaperTradingSessionStatus.COMPLETED,
            last_processed_bar_timestamp=_NOW,
        ))
        _save_promotion_snapshot(client)

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/promote-draft", json=self._PROMOTE_BODY)
        assert resp.status_code == 200
        assert resp.json()["lifecycle_status"] == "paper_tested"


# ---------------------------------------------------------------------------
# P8B. POST /{session_id}/terminate — terminal cleanup integration
# ---------------------------------------------------------------------------

def _order_store(client_fixture) -> PaperOrderStore:
    return client_fixture[4]


def _position_store(client_fixture) -> PaperPositionStore:
    return client_fixture[6]


def _snapshot_store(client_fixture) -> AccountStateSnapshotStore:
    return client_fixture[3]


def _make_pending_order(
    session_id: str = _SESSION_ID,
    user_id: str = _OWNER_ID,
) -> "PaperOrder":
    from backend.paper_trading.execution_models import OrderDirection, PaperOrder, PaperOrderStatus
    from backend.paper_trading.models import FillTimingModel
    return PaperOrder(
        order_id=str(uuid.uuid4()),
        session_id=session_id,
        account_id=_ACCOUNT_ID,
        user_id=user_id,
        symbol="AAPL",
        direction=OrderDirection.BUY,
        quantity=5.0,
        fill_timing_model=FillTimingModel.NEXT_BAR_OPEN,
        signal_bar_timestamp=_NOW,
        status=PaperOrderStatus.PENDING_FILL,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_open_position(
    session_id: str = _SESSION_ID,
    user_id: str = _OWNER_ID,
) -> "PaperPosition":
    from backend.paper_trading.execution_models import PaperPosition
    return PaperPosition(
        position_id=str(uuid.uuid4()),
        session_id=session_id,
        account_id=_ACCOUNT_ID,
        user_id=user_id,
        symbol="AAPL",
        quantity=5.0,
        average_entry_price=100.0,
        current_price=110.0,
        market_value=550.0,
        unrealized_pnl=50.0,
        realized_pnl=0.0,
        is_open=True,
        opened_at=_NOW,
        last_updated_at=_NOW,
    )


class TestTerminateTerminalCleanup:
    """Route-level integration: terminate calls apply_terminal_cleanup."""

    def test_pending_orders_cancelled_on_terminate(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(status=PaperTradingSessionStatus.RUNNING))
        _accounts(client).save(_make_account())
        order = _make_pending_order()
        _order_store(client).save_pending(order)

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/terminate")
        assert resp.status_code == 200

        from backend.paper_trading.execution_models import PaperOrderStatus
        cancelled = _order_store(client).list_cancelled(_SESSION_ID, owner_id=_OWNER_ID)
        assert len(cancelled) == 1
        assert cancelled[0].status == PaperOrderStatus.CANCELLED
        assert cancelled[0].cancellation_reason == "session_terminated"

    def test_open_positions_closed_on_terminate(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(status=PaperTradingSessionStatus.RUNNING))
        _accounts(client).save(_make_account())
        pos = _make_open_position()
        _position_store(client).save(pos)

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/terminate")
        assert resp.status_code == 200

        from backend.paper_trading.execution_stores import PaperPositionStore
        all_pos = _position_store(client).list_positions(_SESSION_ID, owner_id=_OWNER_ID)
        assert len(all_pos) == 1
        assert all_pos[0].is_open is False
        assert all_pos[0].closed_at is not None

    def test_account_status_closed_on_terminate(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(status=PaperTradingSessionStatus.RUNNING))
        _accounts(client).save(_make_account())

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/terminate")
        assert resp.status_code == 200

        updated_acct = _accounts(client).load_by_session_id(_SESSION_ID)
        assert updated_acct.status == PaperAccountStatus.CLOSED
        assert updated_acct.closed_at is not None

    def test_equity_snapshot_written_on_terminate(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(status=PaperTradingSessionStatus.RUNNING))
        _accounts(client).save(_make_account())

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/terminate")
        assert resp.status_code == 200

        snapshots = _snapshot_store(client).list_snapshots(_SESSION_ID)
        assert len(snapshots) == 1
        snap = snapshots[0]
        assert snap.open_position_count == 0
        assert snap.unrealized_pnl == 0.0

    def test_terminate_without_account_still_returns_200(self, client):
        """Session with no PaperAccount (never activated) terminates gracefully."""
        tc = _tc(client)
        _repo(client).save(_make_pt_session(status=PaperTradingSessionStatus.RUNNING))

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/terminate")
        assert resp.status_code == 200
        assert resp.json()["status"] == "terminated"

    def test_session_status_is_terminated_after_cleanup(self, client):
        tc = _tc(client)
        _repo(client).save(_make_pt_session(status=PaperTradingSessionStatus.RUNNING))
        _accounts(client).save(_make_account())

        resp = tc.post(f"{_BASE}/{_SESSION_ID}/terminate")
        assert resp.status_code == 200
        assert resp.json()["status"] == "terminated"
