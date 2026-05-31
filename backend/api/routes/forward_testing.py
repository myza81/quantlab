"""
Forward Testing API routes — Phase 4C.5.

Protected routes under /forward-tests. All routes require an active subscription.
user_id is ALWAYS sourced from the JWT (current_user.user_id) — never from
client payloads.  Wrong-owner access returns HTTP 404 (information hiding).

Routes:
    POST   /forward-tests                               — create session (PENDING)
    GET    /forward-tests                               — list own sessions
    GET    /forward-tests/{session_id}                  — session detail
    POST   /forward-tests/{session_id}/run-cycle        — execute one cycle
    POST   /forward-tests/{session_id}/pause            — pause
    POST   /forward-tests/{session_id}/resume           — resume
    POST   /forward-tests/{session_id}/terminate        — terminate
    GET    /forward-tests/{session_id}/signals          — signal history
    GET    /forward-tests/{session_id}/bars             — bar history

Security invariants:
    - No file_path in any response
    - No credential secrets in any response
    - No strategy_json in list or summary responses
    - user_id never in list responses (bulk PII reduction)
    - catalog source mode rejected for run-cycle (static dataset, not live)

No scheduler. No background polling. No automated daemon. One cycle per call.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from backend.api.dependencies import (
    get_draft_repository,
    get_forward_test_bar_store,
    get_forward_test_repository,
    get_forward_test_signal_store,
    get_ohlcv_service,
    get_provider_factory,
    get_tool_registry,
)
from backend.api.schemas.forward_testing import (
    CreateForwardTestSessionRequest,
    ForwardTestBarResponse,
    ForwardTestCycleResultResponse,
    ForwardTestSessionDetailResponse,
    ForwardTestSessionSummaryResponse,
    ForwardTestSignalResponse,
    ForwardTestStrategySnapshotResponse,
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
from backend.forward_testing.exceptions import (
    ForwardTestInvalidTransitionError,
    ForwardTestSessionAlreadyExistsError,
    ForwardTestSessionNotFoundError,
)
from backend.forward_testing.models import (
    ForwardTestSession,
    ForwardTestSessionStatus,
    StrategySnapshot,
    validate_session_transition,
)
from backend.forward_testing.repository import ForwardTestRepository
from backend.forward_testing.service import ForwardTestService
from backend.forward_testing.stores import ForwardTestBarStore, ForwardTestSignalStore
from backend.services.ohlcv_service import OHLCVService
from backend.strategy_registry.draft_repository import DraftNotFoundError, DraftRepository
from backend.strategy_registry.lifecycle import StrategyLifecycleStatus
from backend.tools.historical_computation import derive_warmup_bars_required
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forward-tests", tags=["forward-tests"])

_FORWARD_TEST_ELIGIBLE_STATUSES: frozenset[str] = frozenset({
    StrategyLifecycleStatus.BACKTESTED.value,
    StrategyLifecycleStatus.FORWARD_TESTED.value,
    StrategyLifecycleStatus.PAPER_TESTED.value,
    StrategyLifecycleStatus.APPROVED_FOR_LIVE.value,
})

_WARMUP_SAFETY_BUFFER = 20


# ---------------------------------------------------------------------------
# Response builders (no strategy_json; no user_id in summary)
# ---------------------------------------------------------------------------

def _snapshot_to_response(snapshot: StrategySnapshot) -> ForwardTestStrategySnapshotResponse:
    return ForwardTestStrategySnapshotResponse(
        draft_id=snapshot.draft_id,
        display_name=snapshot.display_name,
        lifecycle_status=snapshot.lifecycle_status,
        snapshot_hash=snapshot.snapshot_hash,
    )


def _session_to_summary(session: ForwardTestSession) -> ForwardTestSessionSummaryResponse:
    return ForwardTestSessionSummaryResponse(
        session_id=session.session_id,
        status=session.status.value,
        symbol=session.symbol,
        timeframe=session.timeframe,
        source_mode=session.source_mode,
        provider_name=session.provider_name,
        catalog_id=session.catalog_id,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        last_processed_bar_timestamp=(
            session.last_processed_bar_timestamp.isoformat()
            if session.last_processed_bar_timestamp is not None else None
        ),
        bars_evaluated=session.bars_evaluated,
        signals_recorded=session.signals_recorded,
        strategy_snapshot=_snapshot_to_response(session.strategy_snapshot),
    )


def _session_to_detail(session: ForwardTestSession) -> ForwardTestSessionDetailResponse:
    return ForwardTestSessionDetailResponse(
        **_session_to_summary(session).model_dump(),
        draft_id=session.draft_id,
        lifecycle_status_at_activation=session.lifecycle_status_at_activation,
        warmup_bars_required=session.warmup_bars_required,
        warmup_bars_processed=session.warmup_bars_processed,
        signal_eligible_bars_processed=session.signal_eligible_bars_processed,
        activation_timestamp=(
            session.activation_timestamp.isoformat()
            if session.activation_timestamp is not None else None
        ),
        failure_reason=session.failure_reason,
        error_category=session.error_category,
        exchange=session.exchange,
        asset_class=session.asset_class,
    )


# ---------------------------------------------------------------------------
# Credential resolution (mirrors market_data_service._resolve_provider_api_key)
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
# POST /forward-tests — create session
# ---------------------------------------------------------------------------

@router.post("", response_model=ForwardTestSessionDetailResponse, status_code=201)
def create_session(
    request: CreateForwardTestSessionRequest,
    draft_repository: DraftRepository = Depends(get_draft_repository),
    ft_repository: ForwardTestRepository = Depends(get_forward_test_repository),
    tool_registry: ToolRegistry = Depends(get_tool_registry),
    current_user: User = Depends(require_active_subscription),
) -> ForwardTestSessionDetailResponse:
    # Load draft — ownership enforced (wrong-owner → same error as not-found)
    try:
        draft = draft_repository.load(request.draft_id, owner_id=current_user.user_id)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Lifecycle gate: strategy must be at least backtested
    if draft.lifecycle_status.value not in _FORWARD_TEST_ELIGIBLE_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"strategy lifecycle '{draft.lifecycle_status.value}' is not eligible for "
                "forward testing; strategy must be at least 'backtested'"
            ),
        )

    # Seal snapshot at creation time (strategy_json never changes after this)
    now_utc = datetime.now(timezone.utc)
    strategy_json = draft.model_dump_json()
    snapshot_hash = hashlib.sha256(strategy_json.encode()).hexdigest()

    snapshot = StrategySnapshot(
        draft_id=draft.draft_id,
        display_name=draft.display_name,
        description=draft.description,
        lifecycle_status=draft.lifecycle_status.value,
        snapshot_hash=snapshot_hash,
        captured_at=now_utc,
        strategy_json=strategy_json,
    )

    # Derive warmup bars required (max across all enabled tools + safety buffer)
    warmup_required = 0
    for tool_config in draft.toolset.enabled_tools():
        try:
            metadata = tool_registry.get(tool_config.tool_id)
            tool_warmup = derive_warmup_bars_required(tool_config, metadata)
            warmup_required = max(warmup_required, tool_warmup)
        except Exception:
            pass
    if warmup_required > 0:
        warmup_required += _WARMUP_SAFETY_BUFFER

    # Build session — starts in PENDING
    session_id = str(uuid.uuid4())
    session = ForwardTestSession(
        session_id=session_id,
        user_id=current_user.user_id,
        draft_id=draft.draft_id,
        strategy_snapshot=snapshot,
        lifecycle_status_at_activation=draft.lifecycle_status.value,
        source_mode=request.source_mode,
        provider_name=request.provider_name,
        catalog_id=request.catalog_id,
        credential_id=request.credential_id,
        symbol=request.symbol,
        timeframe=request.timeframe,
        exchange=request.exchange,
        asset_class=request.asset_class,
        warmup_bars_required=warmup_required,
        status=ForwardTestSessionStatus.PENDING,
        created_at=now_utc,
        updated_at=now_utc,
    )

    try:
        ft_repository.save(session)
    except ForwardTestSessionAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.FT_SESSION_CREATED,
        details={
            "session_id": session_id,
            "draft_id": draft.draft_id,
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "source_mode": request.source_mode,
            "warmup_bars_required": warmup_required,
        },
    ))

    logger.info(
        "forward_testing: session %s created for draft %s (%s %s, warmup=%d)",
        session_id, draft.draft_id, request.symbol, request.timeframe, warmup_required,
    )

    return _session_to_detail(session)


# ---------------------------------------------------------------------------
# GET /forward-tests — list own sessions (no user_id, no strategy_json)
# ---------------------------------------------------------------------------

@router.get("", response_model=list[ForwardTestSessionSummaryResponse])
def list_sessions(
    ft_repository: ForwardTestRepository = Depends(get_forward_test_repository),
    current_user: User = Depends(require_active_subscription),
) -> list[ForwardTestSessionSummaryResponse]:
    sessions = ft_repository.list_all(owner_id=current_user.user_id)
    return [_session_to_summary(s) for s in sessions]


# ---------------------------------------------------------------------------
# GET /forward-tests/{session_id} — session detail
# ---------------------------------------------------------------------------

@router.get("/{session_id}", response_model=ForwardTestSessionDetailResponse)
def get_session(
    session_id: str,
    ft_repository: ForwardTestRepository = Depends(get_forward_test_repository),
    current_user: User = Depends(require_active_subscription),
) -> ForwardTestSessionDetailResponse:
    try:
        validate_uuid_id(session_id, "session_id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        session = ft_repository.load(session_id, owner_id=current_user.user_id)
    except ForwardTestSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _session_to_detail(session)


# ---------------------------------------------------------------------------
# POST /forward-tests/{session_id}/run-cycle
# One cycle only — no loop, no scheduler, no background polling.
# ---------------------------------------------------------------------------

@router.post("/{session_id}/run-cycle", response_model=ForwardTestCycleResultResponse)
def run_cycle(
    session_id: str,
    ft_repository: ForwardTestRepository = Depends(get_forward_test_repository),
    ft_signal_store: ForwardTestSignalStore = Depends(get_forward_test_signal_store),
    ft_bar_store: ForwardTestBarStore = Depends(get_forward_test_bar_store),
    ohlcv_service: OHLCVService = Depends(get_ohlcv_service),
    tool_registry: ToolRegistry = Depends(get_tool_registry),
    factory: ProviderAdapterFactory = Depends(get_provider_factory),
    current_user: User = Depends(require_active_subscription),
) -> ForwardTestCycleResultResponse:
    try:
        validate_uuid_id(session_id, "session_id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        session = ft_repository.load(session_id, owner_id=current_user.user_id)
    except ForwardTestSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

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
        raise HTTPException(status_code=400, detail=f"Provider configuration error: {exc}") from exc

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

    service = ForwardTestService(
        repository=ft_repository,
        signal_store=ft_signal_store,
        bar_store=ft_bar_store,
        ohlcv_service=ohlcv_service,
        tool_registry=tool_registry,
    )

    result = service.run_cycle(
        session_id=session_id,
        owner_id=current_user.user_id,
        identity=identity,
        provider=provider,
    )

    return ForwardTestCycleResultResponse(
        session_id=result.session_id,
        status=result.status,
        bars_fetched=result.bars_fetched,
        bars_processed=result.bars_processed,
        warmup_bars_processed=result.warmup_bars_processed,
        signal_eligible_bars_processed=result.signal_eligible_bars_processed,
        signals_generated=result.signals_generated,
        signals_suppressed=result.signals_suppressed,
        last_processed_bar_timestamp=(
            result.last_processed_bar_timestamp.isoformat()
            if result.last_processed_bar_timestamp is not None else None
        ),
        gap_detected=result.gap_detected,
        provider_failure=result.provider_failure,
        activated=result.activated,
        message=result.message,
    )


# ---------------------------------------------------------------------------
# POST /forward-tests/{session_id}/pause
# ---------------------------------------------------------------------------

@router.post("/{session_id}/pause", response_model=ForwardTestSessionDetailResponse)
def pause_session(
    session_id: str,
    ft_repository: ForwardTestRepository = Depends(get_forward_test_repository),
    current_user: User = Depends(require_active_subscription),
) -> ForwardTestSessionDetailResponse:
    try:
        validate_uuid_id(session_id, "session_id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        session = ft_repository.load(session_id, owner_id=current_user.user_id)
    except ForwardTestSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        validate_session_transition(session.status, ForwardTestSessionStatus.PAUSED)
    except ForwardTestInvalidTransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    now_utc = datetime.now(timezone.utc)
    updated = session.model_copy(update={
        "status": ForwardTestSessionStatus.PAUSED,
        "updated_at": now_utc,
    })
    ft_repository.update(updated, owner_id=current_user.user_id)

    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.FT_SESSION_PAUSED,
        details={"session_id": session_id},
    ))

    return _session_to_detail(updated)


# ---------------------------------------------------------------------------
# POST /forward-tests/{session_id}/resume
# ---------------------------------------------------------------------------

@router.post("/{session_id}/resume", response_model=ForwardTestSessionDetailResponse)
def resume_session(
    session_id: str,
    ft_repository: ForwardTestRepository = Depends(get_forward_test_repository),
    current_user: User = Depends(require_active_subscription),
) -> ForwardTestSessionDetailResponse:
    try:
        validate_uuid_id(session_id, "session_id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        session = ft_repository.load(session_id, owner_id=current_user.user_id)
    except ForwardTestSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Resume is only valid from PAUSED — PENDING→RUNNING is the activation path (run-cycle)
    if session.status != ForwardTestSessionStatus.PAUSED:
        raise HTTPException(
            status_code=422,
            detail=(
                f"resume requires status 'paused'; "
                f"current status is '{session.status.value}'"
            ),
        )
    try:
        validate_session_transition(session.status, ForwardTestSessionStatus.RUNNING)
    except ForwardTestInvalidTransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    now_utc = datetime.now(timezone.utc)
    updated = session.model_copy(update={
        "status": ForwardTestSessionStatus.RUNNING,
        "updated_at": now_utc,
    })
    ft_repository.update(updated, owner_id=current_user.user_id)

    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.FT_SESSION_RESUMED,
        details={"session_id": session_id},
    ))

    return _session_to_detail(updated)


# ---------------------------------------------------------------------------
# POST /forward-tests/{session_id}/terminate
# ---------------------------------------------------------------------------

@router.post("/{session_id}/terminate", response_model=ForwardTestSessionDetailResponse)
def terminate_session(
    session_id: str,
    ft_repository: ForwardTestRepository = Depends(get_forward_test_repository),
    current_user: User = Depends(require_active_subscription),
) -> ForwardTestSessionDetailResponse:
    try:
        validate_uuid_id(session_id, "session_id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        session = ft_repository.load(session_id, owner_id=current_user.user_id)
    except ForwardTestSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        validate_session_transition(session.status, ForwardTestSessionStatus.TERMINATED)
    except ForwardTestInvalidTransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    now_utc = datetime.now(timezone.utc)
    updated = session.model_copy(update={
        "status": ForwardTestSessionStatus.TERMINATED,
        "updated_at": now_utc,
    })
    ft_repository.update(updated, owner_id=current_user.user_id)

    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.FT_SESSION_TERMINATED,
        details={"session_id": session_id},
    ))

    return _session_to_detail(updated)


# ---------------------------------------------------------------------------
# GET /forward-tests/{session_id}/signals
# ---------------------------------------------------------------------------

@router.get("/{session_id}/signals", response_model=list[ForwardTestSignalResponse])
def list_signals(
    session_id: str,
    ft_repository: ForwardTestRepository = Depends(get_forward_test_repository),
    ft_signal_store: ForwardTestSignalStore = Depends(get_forward_test_signal_store),
    current_user: User = Depends(require_active_subscription),
) -> list[ForwardTestSignalResponse]:
    try:
        validate_uuid_id(session_id, "session_id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Ownership enforced via repository load (wrong-owner → 404)
    try:
        ft_repository.load(session_id, owner_id=current_user.user_id)
    except ForwardTestSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    signals = ft_signal_store.list_signals(session_id)
    return [
        ForwardTestSignalResponse(
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
# GET /forward-tests/{session_id}/bars
# ---------------------------------------------------------------------------

@router.get("/{session_id}/bars", response_model=list[ForwardTestBarResponse])
def list_bars(
    session_id: str,
    ft_repository: ForwardTestRepository = Depends(get_forward_test_repository),
    ft_bar_store: ForwardTestBarStore = Depends(get_forward_test_bar_store),
    current_user: User = Depends(require_active_subscription),
) -> list[ForwardTestBarResponse]:
    try:
        validate_uuid_id(session_id, "session_id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Ownership enforced via repository load (wrong-owner → 404)
    try:
        ft_repository.load(session_id, owner_id=current_user.user_id)
    except ForwardTestSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    bars = ft_bar_store.list_bars(session_id)
    return [
        ForwardTestBarResponse(
            bar_index=bar.bar_index,
            bar_timestamp=bar.bar_timestamp.isoformat(),
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            is_warmup_bar=bar.is_warmup_bar,
            processed_at=bar.processed_at.isoformat(),
        )
        for bar in bars
    ]
