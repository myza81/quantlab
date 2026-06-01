"""
Paper Trading API routes — Phase 4E.4.

Protected routes under /paper-trading/sessions. All routes require an active
subscription. user_id is ALWAYS sourced from the JWT (current_user.user_id) —
never from client payloads. Wrong-owner access returns HTTP 404 (information
hiding).

Routes:
    POST   /paper-trading/sessions                                — create session + account
    GET    /paper-trading/sessions                                — list own sessions
    GET    /paper-trading/sessions/{session_id}                   — session detail
    POST   /paper-trading/sessions/{session_id}/run-cycle        — one cycle (activate or poll)
    POST   /paper-trading/sessions/{session_id}/pause            — pause
    POST   /paper-trading/sessions/{session_id}/resume           — resume
    POST   /paper-trading/sessions/{session_id}/terminate        — terminate
    GET    /paper-trading/sessions/{session_id}/signals          — signal history
    GET    /paper-trading/sessions/{session_id}/orders           — order history
    GET    /paper-trading/sessions/{session_id}/fills            — fill history
    GET    /paper-trading/sessions/{session_id}/positions        — position history
    GET    /paper-trading/sessions/{session_id}/account          — current account state
    GET    /paper-trading/sessions/{session_id}/equity-curve     — per-bar equity snapshots
    GET    /paper-trading/sessions/{session_id}/bars             — bar history
    POST   /paper-trading/sessions/{session_id}/promote-draft    — promote draft to paper_tested

Security invariants:
    - No file_path in any response
    - No credential secrets in any response
    - No strategy_json in list or summary responses
    - user_id never in list responses (bulk PII reduction)
    - catalog source mode rejected for run-cycle (static dataset, not live)
    - No broker account identifiers in any response

No scheduler. No background polling. No automated daemon. One cycle per call.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

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
from backend.api.schemas.drafts import DraftResponse
from backend.api.schemas.paper_trading import (
    AccountStateSnapshotResponse,
    CreatePaperTradingSessionRequest,
    PaperAccountResponse,
    PaperBarResponse,
    PaperCycleResultResponse,
    PaperFillResponse,
    PaperOrderResponse,
    PaperPositionResponse,
    PromoteDraftToPaperTestedRequest,
    PaperSignalResponse,
    PaperStrategySnapshotResponse,
    PaperTradingSessionDetailResponse,
    PaperTradingSessionSummaryResponse,
    SimulationAssumptionsResponse,
)
from backend.api.services.draft_service import (
    PaperTestPromotionError,
    promote_draft_to_paper_tested,
)
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event
from backend.core.request_validation import validate_uuid_id
from backend.data.models.dataset import DatasetIdentity
from backend.data.models.instrument import AdjustmentMode, Instrument
from backend.data_providers.provider_factory import (
    ProviderAdapterFactory,
    ProviderBuildError,
    UnknownProviderError,
)
from backend.forward_testing.exceptions import ForwardTestSessionNotFoundError
from backend.forward_testing.repository import ForwardTestRepository
from backend.forward_testing.stores import ForwardTestBarStore, ForwardTestSignalStore
from backend.paper_trading.exceptions import (
    PaperTradingInvalidTransitionError,
    PaperTradingSessionAlreadyExistsError,
    PaperTradingSessionNotFoundError,
)
from backend.paper_trading.models import (
    AccountStateSnapshot,
    PaperAccount,
    PaperAccountStatus,
    PaperStrategySnapshot,
    PaperTradingSession,
    PaperTradingSessionStatus,
    SimulationAssumptions,
    validate_pt_session_transition,
)
from backend.paper_trading.repository import PaperTradingRepository
from backend.paper_trading.service import PaperCycleResult, PaperTradingService
from backend.paper_trading.stores import AccountStateSnapshotStore, PaperAccountStore
from backend.paper_trading.terminal import apply_terminal_cleanup
from backend.paper_trading.execution_stores import (
    PaperFillStore,
    PaperOrderStore,
    PaperPositionStore,
)
from backend.services.ohlcv_service import OHLCVService
from backend.strategy_registry.draft_repository import DraftNotFoundError, DraftRepository
from backend.strategy_registry.lifecycle import StrategyLifecycleStatus
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/paper-trading/sessions", tags=["paper-trading"])

# Paper trading requires forward-test evidence (Phase P2).
# BACKTESTED is explicitly excluded — a draft must complete forward testing first.
_PT_ELIGIBLE_STATUSES: frozenset[str] = frozenset({
    StrategyLifecycleStatus.FORWARD_TESTED.value,
    StrategyLifecycleStatus.PAPER_TESTED.value,
    StrategyLifecycleStatus.APPROVED_FOR_LIVE.value,
})

_WARMUP_SAFETY_BUFFER = 20


# ---------------------------------------------------------------------------
# Response builders — no strategy_json; no user_id in summary
# ---------------------------------------------------------------------------

def _snapshot_to_response(snapshot: PaperStrategySnapshot) -> PaperStrategySnapshotResponse:
    return PaperStrategySnapshotResponse(
        draft_id=snapshot.draft_id,
        display_name=snapshot.display_name,
        lifecycle_status=snapshot.lifecycle_status,
        snapshot_hash=snapshot.snapshot_hash,
    )


def _assumptions_to_response(a: SimulationAssumptions) -> SimulationAssumptionsResponse:
    return SimulationAssumptionsResponse(
        starting_cash=a.starting_cash,
        currency=a.currency,
        fill_timing_model=a.fill_timing_model.value,
        fee_mode=a.fee_mode.value,
        fee_value=a.fee_value,
        slippage_mode=a.slippage_mode.value,
        slippage_value=a.slippage_value,
        position_size_mode=a.position_size_mode.value,
        position_size_value=a.position_size_value,
        max_concurrent_positions=a.max_concurrent_positions,
        max_drawdown_stop_pct=a.max_drawdown_stop_pct,
        allow_short_selling=a.allow_short_selling,
    )


def _session_to_summary(session: PaperTradingSession) -> PaperTradingSessionSummaryResponse:
    return PaperTradingSessionSummaryResponse(
        session_id=session.session_id,
        status=session.status.value,
        symbol=session.symbol,
        timeframe=session.timeframe,
        source_mode=session.source_mode,
        provider_name=session.provider_name,
        catalog_id=session.catalog_id,
        exchange=session.exchange,
        asset_class=session.asset_class,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        last_processed_bar_timestamp=(
            session.last_processed_bar_timestamp.isoformat()
            if session.last_processed_bar_timestamp is not None else None
        ),
        strategy_snapshot=_snapshot_to_response(session.strategy_snapshot),
    )


def _session_to_detail(session: PaperTradingSession) -> PaperTradingSessionDetailResponse:
    return PaperTradingSessionDetailResponse(
        **_session_to_summary(session).model_dump(),
        draft_id=session.draft_id,
        account_id=session.account_id,
        forward_test_session_id=session.forward_test_session_id,
        lifecycle_status_at_activation=session.lifecycle_status_at_activation,
        activation_timestamp=(
            session.activation_timestamp.isoformat()
            if session.activation_timestamp is not None else None
        ),
        failure_reason=session.failure_reason,
        simulation_assumptions=_assumptions_to_response(session.simulation_assumptions),
    )


def _cycle_result_to_response(result: PaperCycleResult) -> PaperCycleResultResponse:
    return PaperCycleResultResponse(
        session_id=result.session_id,
        status=result.status,
        bars_fetched=result.bars_fetched,
        bars_processed=result.bars_processed,
        warmup_bars_processed=result.warmup_bars_processed,
        signal_eligible_bars_processed=result.signal_eligible_bars_processed,
        signals_generated=result.signals_generated,
        signals_suppressed=result.signals_suppressed,
        pending_orders_resolved=result.pending_orders_resolved,
        orders_created=result.orders_created,
        orders_rejected=result.orders_rejected,
        fills_created=result.fills_created,
        positions_opened=result.positions_opened,
        positions_closed=result.positions_closed,
        account_snapshot_created=result.account_snapshot_created,
        last_processed_bar_timestamp=(
            result.last_processed_bar_timestamp.isoformat()
            if result.last_processed_bar_timestamp is not None else None
        ),
        gap_detected=result.gap_detected,
        provider_failure=result.provider_failure,
        activated=result.activated,
        drawdown_stop_triggered=result.drawdown_stop_triggered,
        message=result.message,
    )


# ---------------------------------------------------------------------------
# Credential resolution (mirrors forward_testing pattern)
# ---------------------------------------------------------------------------

def _resolve_provider_api_key(
    *,
    provider: str,
    credential_id: str | None,
    user_id: str,
) -> str | None:
    """
    Resolve a vault-backed API key for a provider.

    Returns None when credential_id is absent — factory falls back to ENV resolver.
    Raw key must NEVER be stored, logged, or included in any response.
    """
    if not credential_id:
        return None

    from backend.core.config import settings
    from backend.vault.crypto import VaultCryptoError
    from backend.vault.repository import CredentialRepository
    from backend.vault.service import (
        CredentialAccessDeniedError,
        CredentialDisabledError,
        CredentialProviderMismatchError,
        VaultService,
    )

    repo = CredentialRepository(settings.credentials_file_path)
    vault = VaultService(repo)

    try:
        return vault.resolve_secret(
            credential_id=credential_id,
            requesting_user_id=user_id,
            provider_name=provider,
        )
    except CredentialAccessDeniedError:
        raise HTTPException(
            status_code=400, detail="Provider credential not found or access denied"
        )
    except CredentialDisabledError:
        raise HTTPException(status_code=400, detail="Provider credential is disabled")
    except CredentialProviderMismatchError:
        raise HTTPException(
            status_code=400, detail="Credential is not registered for this provider"
        )
    except VaultCryptoError:
        raise HTTPException(
            status_code=400, detail="Provider credential could not be resolved"
        )


# ---------------------------------------------------------------------------
# UUID path guard helper
# ---------------------------------------------------------------------------

def _check_uuid(session_id: str) -> None:
    try:
        validate_uuid_id(session_id, "session_id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _load_session(
    session_id: str,
    owner_id: str,
    repository: PaperTradingRepository,
) -> PaperTradingSession:
    try:
        return repository.load(session_id, owner_id=owner_id)
    except PaperTradingSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# POST /paper-trading/sessions — create session + account
# ---------------------------------------------------------------------------

@router.post("", response_model=PaperTradingSessionDetailResponse, status_code=201)
def create_session(
    request: CreatePaperTradingSessionRequest,
    draft_repository: DraftRepository = Depends(get_draft_repository),
    ft_repository: ForwardTestRepository = Depends(get_forward_test_repository),
    pt_repository: PaperTradingRepository = Depends(get_paper_trading_repository),
    account_store: PaperAccountStore = Depends(get_paper_account_store),
    tool_registry: ToolRegistry = Depends(get_tool_registry),
    current_user: User = Depends(require_active_subscription),
) -> PaperTradingSessionDetailResponse:
    # ── 1. Load draft (ownership enforced; wrong-owner → 404) ─────────────────
    try:
        draft = draft_repository.load(request.draft_id, owner_id=current_user.user_id)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # ── 2. Lifecycle gate: draft must be forward-tested ───────────────────────
    if draft.lifecycle_status.value not in _PT_ELIGIBLE_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Draft must be forward-tested before paper trading. "
                f"Current lifecycle status is '{draft.lifecycle_status.value}'; "
                "complete forward testing and promote the draft to 'forward_tested' first."
            ),
        )

    # ── 3. Forward-test session validation (P2.1 / P2.3 / P2.4) ─────────────
    #    Optional but if provided all checks must pass before any write.
    if request.forward_test_session_id is not None:
        try:
            validate_uuid_id(request.forward_test_session_id, "forward_test_session_id")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        # Existence + ownership (wrong-owner → 404, information hiding)
        try:
            ft_session = ft_repository.load(
                request.forward_test_session_id,
                owner_id=current_user.user_id,
            )
        except ForwardTestSessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        # Draft linkage: session must have been created for this exact draft
        if ft_session.draft_id != request.draft_id:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Forward-test session does not reference this draft. "
                    f"Session was created for draft '{ft_session.draft_id}', "
                    f"not '{request.draft_id}'."
                ),
            )

        # Evidence gate: at least one signal-eligible bar must have been evaluated
        if ft_session.signal_eligible_bars_processed < 1:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Forward-test session is not eligible for paper trading. "
                    "Run at least one complete forward-test cycle "
                    "(warmup completed + one live bar evaluated) before creating a paper-trading session."
                ),
            )

    # ── 4. Build simulation assumptions (validate before any write) ───────────
    req_assumptions = request.simulation_assumptions
    try:
        assumptions = SimulationAssumptions(
            starting_cash=req_assumptions.starting_cash,
            currency=req_assumptions.currency,
            fill_timing_model=req_assumptions.fill_timing_model,
            fee_mode=req_assumptions.fee_mode,
            fee_value=req_assumptions.fee_value,
            slippage_mode=req_assumptions.slippage_mode,
            slippage_value=req_assumptions.slippage_value,
            position_size_mode=req_assumptions.position_size_mode,
            position_size_value=req_assumptions.position_size_value,
            max_concurrent_positions=req_assumptions.max_concurrent_positions,
            max_drawdown_stop_pct=req_assumptions.max_drawdown_stop_pct,
            allow_short_selling=req_assumptions.allow_short_selling,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid simulation_assumptions: {exc}"
        ) from exc

    # ── 5. Build domain objects ───────────────────────────────────────────────
    now_utc = datetime.now(timezone.utc)
    strategy_json = draft.model_dump_json()
    snapshot_hash = hashlib.sha256(strategy_json.encode()).hexdigest()

    snapshot = PaperStrategySnapshot(
        draft_id=draft.draft_id,
        display_name=draft.display_name,
        description=draft.description,
        lifecycle_status=draft.lifecycle_status.value,
        snapshot_hash=snapshot_hash,
        captured_at=now_utc,
        strategy_json=strategy_json,
    )

    session_id = str(uuid.uuid4())
    account_id = str(uuid.uuid4())
    starting_cash = assumptions.starting_cash

    account = PaperAccount(
        account_id=account_id,
        session_id=session_id,
        user_id=current_user.user_id,
        currency=assumptions.currency,
        starting_cash=starting_cash,
        cash_balance=starting_cash,
        equity=starting_cash,
        available_cash=starting_cash,
        peak_equity=starting_cash,
        current_drawdown_pct=0.0,
        total_realized_pnl=0.0,
        total_fees_paid=0.0,
        total_slippage_applied=0.0,
        status=PaperAccountStatus.ACTIVE,
        created_at=now_utc,
        updated_at=now_utc,
    )

    session = PaperTradingSession(
        session_id=session_id,
        user_id=current_user.user_id,
        draft_id=draft.draft_id,
        forward_test_session_id=request.forward_test_session_id,
        strategy_snapshot_hash=snapshot_hash,
        strategy_snapshot=snapshot,
        lifecycle_status_at_activation=draft.lifecycle_status.value,
        account_id=account_id,
        simulation_assumptions=assumptions,
        source_mode=request.source_mode,
        provider_name=request.provider_name,
        catalog_id=request.catalog_id,
        credential_id=request.credential_id,
        symbol=request.symbol,
        timeframe=request.timeframe,
        exchange=request.exchange,
        asset_class=request.asset_class,
        status=PaperTradingSessionStatus.PENDING,
        created_at=now_utc,
        updated_at=now_utc,
    )

    # ── 6. Persist — account first, session second (P2.5 atomicity) ──────────
    #    Saving account first means that if account save succeeds but session
    #    save fails, an orphan account exists but no session is created — the
    #    user never sees the account (no session → no access path).  This is
    #    preferable to the reverse order where an orphan session would exist
    #    with a missing account, causing 500s on any subsequent operation.
    try:
        account_store.save(account)
    except Exception as exc:
        logger.error(
            "paper_trading: account save failed for candidate session %s: %s",
            session_id, exc,
        )
        raise HTTPException(status_code=500, detail="Account creation failed") from exc

    try:
        pt_repository.save(session)
    except PaperTradingSessionAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.PT_SESSION_CREATED,
        details={
            "session_id": session_id,
            "account_id": account_id,
            "draft_id": draft.draft_id,
            "forward_test_session_id": request.forward_test_session_id,
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "source_mode": request.source_mode,
            "lifecycle_at_creation": draft.lifecycle_status.value,
            "fill_timing_model": assumptions.fill_timing_model.value,
            "starting_cash": starting_cash,
        },
    ))

    logger.info(
        "paper_trading: session %s created for draft %s (%s %s, cash=%.2f)",
        session_id, draft.draft_id, request.symbol, request.timeframe, starting_cash,
    )

    return _session_to_detail(session)


# ---------------------------------------------------------------------------
# GET /paper-trading/sessions — list own sessions
# ---------------------------------------------------------------------------

@router.get("", response_model=list[PaperTradingSessionSummaryResponse])
def list_sessions(
    pt_repository: PaperTradingRepository = Depends(get_paper_trading_repository),
    current_user: User = Depends(require_active_subscription),
) -> list[PaperTradingSessionSummaryResponse]:
    sessions = pt_repository.list_all(owner_id=current_user.user_id)
    return [_session_to_summary(s) for s in sessions]


# ---------------------------------------------------------------------------
# GET /paper-trading/sessions/{session_id} — session detail
# ---------------------------------------------------------------------------

@router.get("/{session_id}", response_model=PaperTradingSessionDetailResponse)
def get_session(
    session_id: str,
    pt_repository: PaperTradingRepository = Depends(get_paper_trading_repository),
    current_user: User = Depends(require_active_subscription),
) -> PaperTradingSessionDetailResponse:
    _check_uuid(session_id)
    session = _load_session(session_id, current_user.user_id, pt_repository)
    return _session_to_detail(session)


# ---------------------------------------------------------------------------
# POST /paper-trading/sessions/{session_id}/run-cycle
# One cycle only — no loop, no scheduler, no background polling.
# Dispatches: PENDING → _activate(); RUNNING → _poll_cycle(); else → no-op.
# ---------------------------------------------------------------------------

@router.post("/{session_id}/run-cycle", response_model=PaperCycleResultResponse)
def run_cycle(
    session_id: str,
    pt_repository: PaperTradingRepository = Depends(get_paper_trading_repository),
    account_store: PaperAccountStore = Depends(get_paper_account_store),
    snapshot_store: AccountStateSnapshotStore = Depends(get_account_state_snapshot_store),
    order_store: PaperOrderStore = Depends(get_paper_order_store),
    fill_store: PaperFillStore = Depends(get_paper_fill_store),
    position_store: PaperPositionStore = Depends(get_paper_position_store),
    bar_store: ForwardTestBarStore = Depends(get_forward_test_bar_store),
    signal_store: ForwardTestSignalStore = Depends(get_forward_test_signal_store),
    ohlcv_service: OHLCVService = Depends(get_ohlcv_service),
    tool_registry: ToolRegistry = Depends(get_tool_registry),
    factory: ProviderAdapterFactory = Depends(get_provider_factory),
    current_user: User = Depends(require_active_subscription),
) -> PaperCycleResultResponse:
    _check_uuid(session_id)
    session = _load_session(session_id, current_user.user_id, pt_repository)

    # Catalog datasets are static — not suitable for live polling
    if session.source_mode == "catalog":
        raise HTTPException(
            status_code=422,
            detail="catalog source mode does not support live polling cycles",
        )

    provider_name = session.provider_name or ""
    api_key = _resolve_provider_api_key(
        provider=provider_name,
        credential_id=session.credential_id,
        user_id=current_user.user_id,
    )

    try:
        provider = factory.build(
            provider_name,
            symbol=session.symbol,
            asset_class=session.asset_class,
            venue=session.exchange,
            timeframe=session.timeframe,
            api_key=api_key,
        )
    except UnknownProviderError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {exc}") from exc
    except ProviderBuildError as exc:
        raise HTTPException(
            status_code=400, detail=f"Provider configuration error: {exc}"
        ) from exc

    instrument = Instrument(
        symbol=session.symbol,
        asset_class=session.asset_class,
        exchange=session.exchange,
    )
    identity = DatasetIdentity(
        instrument=instrument,
        provider=provider_name,
        timeframe=session.timeframe,
        adjustment_mode=AdjustmentMode.RAW,
    )

    service = PaperTradingService(
        repository=pt_repository,
        account_store=account_store,
        snapshot_store=snapshot_store,
        order_store=order_store,
        fill_store=fill_store,
        position_store=position_store,
        bar_store=bar_store,
        signal_store=signal_store,
        ohlcv_service=ohlcv_service,
        tool_registry=tool_registry,
    )

    result = service.run_cycle(
        session_id=session_id,
        owner_id=current_user.user_id,
        identity=identity,
        provider=provider,
    )

    return _cycle_result_to_response(result)


# ---------------------------------------------------------------------------
# POST /paper-trading/sessions/{session_id}/pause
# ---------------------------------------------------------------------------

@router.post("/{session_id}/pause", response_model=PaperTradingSessionDetailResponse)
def pause_session(
    session_id: str,
    pt_repository: PaperTradingRepository = Depends(get_paper_trading_repository),
    current_user: User = Depends(require_active_subscription),
) -> PaperTradingSessionDetailResponse:
    _check_uuid(session_id)
    session = _load_session(session_id, current_user.user_id, pt_repository)

    try:
        validate_pt_session_transition(session.status, PaperTradingSessionStatus.PAUSED)
    except PaperTradingInvalidTransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    now_utc = datetime.now(timezone.utc)
    updated = session.model_copy(update={
        "status": PaperTradingSessionStatus.PAUSED,
        "updated_at": now_utc,
    })
    pt_repository.update(updated, owner_id=current_user.user_id)

    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.PT_SESSION_PAUSED,
        details={"session_id": session_id},
    ))

    return _session_to_detail(updated)


# ---------------------------------------------------------------------------
# POST /paper-trading/sessions/{session_id}/resume
# ---------------------------------------------------------------------------

@router.post("/{session_id}/resume", response_model=PaperTradingSessionDetailResponse)
def resume_session(
    session_id: str,
    pt_repository: PaperTradingRepository = Depends(get_paper_trading_repository),
    current_user: User = Depends(require_active_subscription),
) -> PaperTradingSessionDetailResponse:
    _check_uuid(session_id)
    session = _load_session(session_id, current_user.user_id, pt_repository)

    # Resume is only valid from PAUSED
    if session.status != PaperTradingSessionStatus.PAUSED:
        raise HTTPException(
            status_code=422,
            detail=(
                f"resume requires status 'paused'; "
                f"current status is '{session.status.value}'"
            ),
        )

    try:
        validate_pt_session_transition(session.status, PaperTradingSessionStatus.RUNNING)
    except PaperTradingInvalidTransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    now_utc = datetime.now(timezone.utc)
    updated = session.model_copy(update={
        "status": PaperTradingSessionStatus.RUNNING,
        "updated_at": now_utc,
    })
    pt_repository.update(updated, owner_id=current_user.user_id)

    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.PT_SESSION_RESUMED,
        details={"session_id": session_id},
    ))

    return _session_to_detail(updated)


# ---------------------------------------------------------------------------
# POST /paper-trading/sessions/{session_id}/terminate
# ---------------------------------------------------------------------------

@router.post("/{session_id}/terminate", response_model=PaperTradingSessionDetailResponse)
def terminate_session(
    session_id: str,
    pt_repository: PaperTradingRepository = Depends(get_paper_trading_repository),
    order_store: PaperOrderStore = Depends(get_paper_order_store),
    position_store: PaperPositionStore = Depends(get_paper_position_store),
    account_store: PaperAccountStore = Depends(get_paper_account_store),
    snapshot_store: AccountStateSnapshotStore = Depends(get_account_state_snapshot_store),
    current_user: User = Depends(require_active_subscription),
) -> PaperTradingSessionDetailResponse:
    _check_uuid(session_id)
    session = _load_session(session_id, current_user.user_id, pt_repository)

    try:
        validate_pt_session_transition(session.status, PaperTradingSessionStatus.TERMINATED)
    except PaperTradingInvalidTransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    now_utc = datetime.now(timezone.utc)

    apply_terminal_cleanup(
        session_id=session_id,
        account_id=session.account_id,
        owner_id=current_user.user_id,
        order_store=order_store,
        position_store=position_store,
        account_store=account_store,
        snapshot_store=snapshot_store,
        now_utc=now_utc,
    )

    updated = session.model_copy(update={
        "status": PaperTradingSessionStatus.TERMINATED,
        "updated_at": now_utc,
    })
    pt_repository.update(updated, owner_id=current_user.user_id)

    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.PT_SESSION_TERMINATED,
        details={"session_id": session_id},
    ))

    return _session_to_detail(updated)


# ---------------------------------------------------------------------------
# GET /paper-trading/sessions/{session_id}/signals
# ---------------------------------------------------------------------------

@router.get("/{session_id}/signals", response_model=list[PaperSignalResponse])
def list_signals(
    session_id: str,
    pt_repository: PaperTradingRepository = Depends(get_paper_trading_repository),
    signal_store: ForwardTestSignalStore = Depends(get_forward_test_signal_store),
    current_user: User = Depends(require_active_subscription),
) -> list[PaperSignalResponse]:
    _check_uuid(session_id)
    # Ownership gate: wrong-owner → 404
    _load_session(session_id, current_user.user_id, pt_repository)

    signals = signal_store.list_signals(session_id)
    return [
        PaperSignalResponse(
            signal_id=sig.signal_id,
            session_id=sig.session_id,
            bar_timestamp=sig.bar_timestamp.isoformat(),
            signal_timestamp=sig.signal_timestamp.isoformat(),
            signal_direction=sig.signal_direction,
            rule_id=sig.rule_id,
            bar_open=sig.bar_open,
            bar_high=sig.bar_high,
            bar_low=sig.bar_low,
            bar_close=sig.bar_close,
            bar_volume=sig.bar_volume,
            feature_values_at_signal=sig.feature_values_at_signal,
            warmup_satisfied=sig.warmup_satisfied,
            strategy_snapshot_hash=sig.strategy_snapshot_hash,
            symbol=sig.symbol,
            timeframe=sig.timeframe,
            provider_name=sig.provider_name,
            catalog_id=sig.catalog_id,
            created_at=sig.created_at.isoformat(),
        )
        for sig in signals
    ]


# ---------------------------------------------------------------------------
# GET /paper-trading/sessions/{session_id}/orders
# ---------------------------------------------------------------------------

@router.get("/{session_id}/orders", response_model=list[PaperOrderResponse])
def list_orders(
    session_id: str,
    pt_repository: PaperTradingRepository = Depends(get_paper_trading_repository),
    order_store: PaperOrderStore = Depends(get_paper_order_store),
    current_user: User = Depends(require_active_subscription),
) -> list[PaperOrderResponse]:
    _check_uuid(session_id)
    _load_session(session_id, current_user.user_id, pt_repository)

    owner_id = current_user.user_id
    # Aggregate all order states (pending + filled + cancelled + rejected)
    orders = (
        order_store.load_pending(session_id, owner_id=owner_id)
        + order_store.list_filled(session_id, owner_id=owner_id)
        + order_store.list_cancelled(session_id, owner_id=owner_id)
        + order_store.list_rejected(session_id, owner_id=owner_id)
    )

    return [
        PaperOrderResponse(
            order_id=o.order_id,
            session_id=o.session_id,
            symbol=o.symbol,
            direction=o.direction.value,
            quantity=o.quantity,
            status=o.status.value,
            fill_timing_model=o.fill_timing_model.value,
            signal_id=o.signal_id,
            signal_bar_timestamp=o.signal_bar_timestamp.isoformat(),
            target_fill_bar_timestamp=(
                o.target_fill_bar_timestamp.isoformat()
                if o.target_fill_bar_timestamp is not None else None
            ),
            created_at=o.created_at.isoformat(),
            updated_at=o.updated_at.isoformat(),
            filled_at=o.filled_at.isoformat() if o.filled_at is not None else None,
            cancellation_reason=o.cancellation_reason,
            rejection_reason=o.rejection_reason,
        )
        for o in orders
    ]


# ---------------------------------------------------------------------------
# GET /paper-trading/sessions/{session_id}/fills
# ---------------------------------------------------------------------------

@router.get("/{session_id}/fills", response_model=list[PaperFillResponse])
def list_fills(
    session_id: str,
    pt_repository: PaperTradingRepository = Depends(get_paper_trading_repository),
    fill_store: PaperFillStore = Depends(get_paper_fill_store),
    current_user: User = Depends(require_active_subscription),
) -> list[PaperFillResponse]:
    _check_uuid(session_id)
    _load_session(session_id, current_user.user_id, pt_repository)

    fills = fill_store.list_fills(session_id, owner_id=current_user.user_id)
    return [
        PaperFillResponse(
            fill_id=f.fill_id,
            order_id=f.order_id,
            session_id=f.session_id,
            symbol=f.symbol,
            direction=f.direction.value,
            quantity=f.quantity,
            gross_price=f.gross_price,
            slippage=f.slippage,
            fill_price=f.fill_price,
            gross_value=f.gross_value,
            fee=f.fee,
            net_value=f.net_value,
            fill_bar_timestamp=f.fill_bar_timestamp.isoformat(),
            created_at=f.created_at.isoformat(),
            execution_reason=f.execution_reason.value if f.execution_reason else None,
        )
        for f in fills
    ]


# ---------------------------------------------------------------------------
# GET /paper-trading/sessions/{session_id}/positions
# ---------------------------------------------------------------------------

@router.get("/{session_id}/positions", response_model=list[PaperPositionResponse])
def list_positions(
    session_id: str,
    pt_repository: PaperTradingRepository = Depends(get_paper_trading_repository),
    position_store: PaperPositionStore = Depends(get_paper_position_store),
    current_user: User = Depends(require_active_subscription),
) -> list[PaperPositionResponse]:
    _check_uuid(session_id)
    _load_session(session_id, current_user.user_id, pt_repository)

    positions = position_store.list_positions(session_id, owner_id=current_user.user_id)
    return [
        PaperPositionResponse(
            position_id=p.position_id,
            session_id=p.session_id,
            symbol=p.symbol,
            quantity=p.quantity,
            average_entry_price=p.average_entry_price,
            current_price=p.current_price,
            market_value=p.market_value,
            unrealized_pnl=p.unrealized_pnl,
            realized_pnl=p.realized_pnl,
            is_open=p.is_open,
            opened_at=p.opened_at.isoformat(),
            last_updated_at=p.last_updated_at.isoformat(),
            closed_at=p.closed_at.isoformat() if p.closed_at is not None else None,
            opening_signal_id=p.opening_signal_id,
            closing_signal_id=p.closing_signal_id,
        )
        for p in positions
    ]


# ---------------------------------------------------------------------------
# GET /paper-trading/sessions/{session_id}/account
# ---------------------------------------------------------------------------

@router.get("/{session_id}/account", response_model=PaperAccountResponse)
def get_account(
    session_id: str,
    pt_repository: PaperTradingRepository = Depends(get_paper_trading_repository),
    account_store: PaperAccountStore = Depends(get_paper_account_store),
    current_user: User = Depends(require_active_subscription),
) -> PaperAccountResponse:
    _check_uuid(session_id)
    _load_session(session_id, current_user.user_id, pt_repository)

    try:
        account = account_store.load_by_session_id(session_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Account not found for session") from exc

    return PaperAccountResponse(
        account_id=account.account_id,
        session_id=account.session_id,
        currency=account.currency,
        starting_cash=account.starting_cash,
        cash_balance=account.cash_balance,
        equity=account.equity,
        available_cash=account.available_cash,
        peak_equity=account.peak_equity,
        current_drawdown_pct=account.current_drawdown_pct,
        total_realized_pnl=account.total_realized_pnl,
        total_fees_paid=account.total_fees_paid,
        total_slippage_applied=account.total_slippage_applied,
        status=account.status.value,
        created_at=account.created_at.isoformat(),
        updated_at=account.updated_at.isoformat(),
        closed_at=account.closed_at.isoformat() if account.closed_at is not None else None,
    )


# ---------------------------------------------------------------------------
# GET /paper-trading/sessions/{session_id}/equity-curve
# ---------------------------------------------------------------------------

@router.get("/{session_id}/equity-curve", response_model=list[AccountStateSnapshotResponse])
def get_equity_curve(
    session_id: str,
    pt_repository: PaperTradingRepository = Depends(get_paper_trading_repository),
    snapshot_store: AccountStateSnapshotStore = Depends(get_account_state_snapshot_store),
    current_user: User = Depends(require_active_subscription),
) -> list[AccountStateSnapshotResponse]:
    _check_uuid(session_id)
    _load_session(session_id, current_user.user_id, pt_repository)

    snapshots = snapshot_store.list_snapshots(session_id)
    return [
        AccountStateSnapshotResponse(
            snapshot_id=s.snapshot_id,
            session_id=s.session_id,
            bar_timestamp=s.bar_timestamp.isoformat(),
            snapshot_timestamp=s.snapshot_timestamp.isoformat(),
            cash_balance=s.cash_balance,
            equity=s.equity,
            available_cash=s.available_cash,
            peak_equity=s.peak_equity,
            current_drawdown_pct=s.current_drawdown_pct,
            open_position_count=s.open_position_count,
            realized_pnl=s.realized_pnl,
            unrealized_pnl=s.unrealized_pnl,
            created_at=s.created_at.isoformat(),
        )
        for s in snapshots
    ]


# ---------------------------------------------------------------------------
# GET /paper-trading/sessions/{session_id}/bars
# ---------------------------------------------------------------------------

@router.get("/{session_id}/bars", response_model=list[PaperBarResponse])
def list_bars(
    session_id: str,
    pt_repository: PaperTradingRepository = Depends(get_paper_trading_repository),
    bar_store: ForwardTestBarStore = Depends(get_forward_test_bar_store),
    current_user: User = Depends(require_active_subscription),
) -> list[PaperBarResponse]:
    _check_uuid(session_id)
    _load_session(session_id, current_user.user_id, pt_repository)

    bars = bar_store.list_bars(session_id)
    return [
        PaperBarResponse(
            bar_index=b.bar_index,
            bar_timestamp=b.bar_timestamp.isoformat(),
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume=b.volume,
            is_warmup_bar=b.is_warmup_bar,
            processed_at=b.processed_at.isoformat(),
        )
        for b in bars
    ]


# ---------------------------------------------------------------------------
# POST /paper-trading/sessions/{session_id}/promote-draft — Phase P7/P8C
# Evidence-gated promotion: forward_tested → paper_tested.
# P8C gates: bar processed + session terminated/completed + ≥1 equity snapshot.
# ---------------------------------------------------------------------------

@router.post("/{session_id}/promote-draft", response_model=DraftResponse)
def promote_draft(
    session_id: str,
    request: PromoteDraftToPaperTestedRequest,
    pt_repository: PaperTradingRepository = Depends(get_paper_trading_repository),
    draft_repository: DraftRepository = Depends(get_draft_repository),
    snapshot_store: AccountStateSnapshotStore = Depends(get_account_state_snapshot_store),
    current_user: User = Depends(require_active_subscription),
) -> DraftResponse:
    _check_uuid(session_id)
    try:
        validate_uuid_id(request.draft_id, "draft_id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return promote_draft_to_paper_tested(
            session_id=session_id,
            draft_id=request.draft_id,
            pt_repository=pt_repository,
            draft_repository=draft_repository,
            snapshot_store=snapshot_store,
            owner_id=current_user.user_id,
            notes=request.notes,
        )
    except PaperTradingSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PaperTestPromotionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
