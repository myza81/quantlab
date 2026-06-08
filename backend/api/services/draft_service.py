"""
Draft service — Phase 2N.9 / Phase R3.

Thin orchestration layer between the /drafts routes and DraftRepository.
Responsibilities: timestamp injection, schema conversion, repository delegation.
No business logic beyond coordinating its dependencies.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from backend.api.schemas.drafts import (
    DraftCreateRequest,
    DraftListResponse,
    DraftResponse,
    DraftUpdateRequest,
)
from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event
from backend.strategy_registry.draft_repository import DraftRepository
from backend.strategy_registry.drafts import StrategyDraft
from backend.strategy_registry.lifecycle import (
    StrategyLifecycleStatus,
    validate_lifecycle_transition,
)

_UTC = timezone.utc


def _to_response(draft: StrategyDraft) -> DraftResponse:
    """Convert a StrategyDraft domain object to its API response schema."""
    return DraftResponse.model_validate(draft.model_dump())


def create_draft(
    request: DraftCreateRequest,
    repository: DraftRepository,
    user_id: str | None = None,
) -> DraftResponse:
    """Build and persist a new StrategyDraft from the create request."""
    now = datetime.now(_UTC)
    draft = StrategyDraft(
        draft_id=request.draft_id,
        display_name=request.display_name,
        description=request.description,
        toolset=request.toolset,
        created_at=now,
        updated_at=now,
        enabled=request.enabled,
        tags=tuple(request.tags),
        notes=request.notes,
        user_id=user_id,
        lifecycle_status=StrategyLifecycleStatus.DRAFT,
    )
    repository.save(draft)
    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.DRAFT_CREATED,
        details={"draft_id": draft.draft_id, "user_id": user_id},
    ))
    return _to_response(draft)


def get_draft(
    draft_id: str,
    repository: DraftRepository,
    owner_id: str | None = None,
) -> DraftResponse:
    """Load and return a single active draft."""
    draft = repository.load(draft_id, owner_id=owner_id)
    return _to_response(draft)


def list_drafts(
    repository: DraftRepository,
    user_id: str | None = None,
) -> DraftListResponse:
    """Return all active drafts sorted by draft_id."""
    drafts = repository.list_all(user_id=user_id)
    return DraftListResponse(
        drafts=[_to_response(d) for d in drafts],
        count=len(drafts),
    )


def update_draft(
    draft_id: str,
    request: DraftUpdateRequest,
    repository: DraftRepository,
    owner_id: str | None = None,
) -> DraftResponse:
    """
    Apply partial updates to an existing draft and persist.

    Only fields explicitly set in the request body are applied.
    Omitted fields retain their existing values.
    updated_at is always refreshed.
    """
    existing = repository.load(draft_id, owner_id=owner_id)
    existing_data = existing.model_dump()

    updates = request.model_dump(exclude_unset=True)

    if "tags" in updates and isinstance(updates["tags"], list):
        updates["tags"] = tuple(updates["tags"])
    existing_data.update(updates)
    existing_data["updated_at"] = datetime.now(_UTC)

    updated = StrategyDraft.model_validate(existing_data)
    repository.update(updated, owner_id=owner_id)
    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.DRAFT_UPDATED,
        details={"draft_id": draft_id, "user_id": owner_id},
    ))
    return _to_response(updated)


def archive_draft(
    draft_id: str,
    repository: DraftRepository,
    owner_id: str | None = None,
) -> None:
    """Move a draft to the archive. It is removed from active listing."""
    repository.archive(draft_id, owner_id=owner_id)
    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.DRAFT_ARCHIVED,
        details={"draft_id": draft_id, "user_id": owner_id},
    ))


def delete_draft(
    draft_id: str,
    repository: DraftRepository,
    owner_id: str | None = None,
) -> None:
    """Hard-delete a draft."""
    repository.delete(draft_id, owner_id=owner_id)
    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.DRAFT_DELETED,
        details={"draft_id": draft_id, "user_id": owner_id},
    ))


# ---------------------------------------------------------------------------
# Lifecycle promotion — Phase R3
# ---------------------------------------------------------------------------

class LifecyclePromotionError(Exception):
    """Raised when backtest evidence fails to satisfy the promotion gate."""


class ForwardTestPromotionError(Exception):
    """Raised when forward-test evidence fails to satisfy the forward-test promotion gate."""




def promote_draft_to_backtested(
    draft_id: str,
    run_id: str,
    repository: DraftRepository,
    storage: Path,
    owner_id: str,
    *,
    notes: str | None = None,
) -> DraftResponse:
    """
    Promote a draft to 'backtested' status, gated by valid backtest evidence.

    Requirements (all must hold; any failure raises before mutating state):
      - draft exists and is owned by owner_id
      - backtest run exists and is owned by owner_id
      - report.run.draft_id == draft_id  (run was produced from this exact draft)
      - report.run.status == "completed" (not failed, not partial)
      - validate_lifecycle_transition(current, BACKTESTED) succeeds

    Raises:
        DraftNotFoundError: draft absent or wrong owner.
        BacktestRunError: run file missing.
        BacktestAccessDeniedError: run owned by a different user.
        LifecyclePromotionError: run/draft mismatch or run not completed.
        ValueError: lifecycle transition not permitted from current status.
    """
    # Deferred import avoids a circular dependency at module parse time while
    # keeping the call inside the service (not pushed up to the route layer).
    from backend.api.services.backtest_run_service import (  # noqa: PLC0415
        BacktestAccessDeniedError,
        BacktestRunError,
        load_backtest_report,
    )

    # 1 — load draft; raises DraftNotFoundError for missing/wrong-owner
    draft = repository.load(draft_id, owner_id=owner_id)

    # 2 — load report; raises BacktestRunError or BacktestAccessDeniedError
    report = load_backtest_report(run_id, storage=storage, owner_user_id=owner_id)

    # 3 — evidence: run must have been executed against THIS draft
    if report.run.draft_id != draft_id:
        raise LifecyclePromotionError(
            f"Backtest run '{run_id}' was produced for draft "
            f"'{report.run.draft_id}', not '{draft_id}'."
        )

    # 4 — evidence: run must have completed successfully
    if report.run.status != "completed":
        raise LifecyclePromotionError(
            f"Backtest run '{run_id}' has status '{report.run.status}'; "
            "only 'completed' runs qualify as promotion evidence."
        )

    # 5 — state machine: current → backtested must be allowed
    validate_lifecycle_transition(draft.lifecycle_status, StrategyLifecycleStatus.BACKTESTED)

    # 6 — mutate and persist
    existing_data = draft.model_dump()
    existing_data["lifecycle_status"] = StrategyLifecycleStatus.BACKTESTED
    existing_data["updated_at"] = datetime.now(_UTC)
    if notes is not None:
        existing_data["notes"] = notes

    updated = StrategyDraft.model_validate(existing_data)
    repository.update(updated, owner_id=owner_id)

    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.GOV_PROMOTION_REQUESTED,
        details={
            "draft_id": draft_id,
            "run_id": run_id,
            "from_status": draft.lifecycle_status.value,
            "to_status": StrategyLifecycleStatus.BACKTESTED.value,
            "user_id": owner_id,
        },
    ))

    return _to_response(updated)


# ---------------------------------------------------------------------------
# Lifecycle promotion — Phase P1
# ---------------------------------------------------------------------------

def promote_draft_to_forward_tested(
    session_id: str,
    draft_id: str,
    ft_repository,  # ForwardTestRepository — deferred to avoid circular imports
    draft_repository: DraftRepository,
    owner_id: str,
    *,
    ft_bar_store,   # ForwardTestBarStore — deferred; used for calendar-day count
    notes: str | None = None,
) -> DraftResponse:
    """
    Promote a draft to 'forward_tested' status, gated by hardened evidence (FT-2B).

    Evidence gates (all must pass; evaluated in order; any failure raises):
      1. session exists and is owned by owner_id
      2. draft exists and is owned by owner_id
      3. session.draft_id == draft_id  (session was created for this exact draft)
      4. draft.lifecycle_status == BACKTESTED (only backtested drafts can advance)
      5. signal-eligible bars >= settings.ft_min_eligible_bars  (default 20)
      6. distinct UTC calendar days from those bars >= settings.ft_min_calendar_days
         (default 5)
      7. validate_lifecycle_transition(BACKTESTED, FORWARD_TESTED) succeeds

    Gates 5–6 are evaluated via assess_ft_promotion_readiness(), which reads bar
    timestamps from the bar store.  Both thresholds are configurable through
    settings (FT_MIN_ELIGIBLE_BARS / FT_MIN_CALENDAR_DAYS env vars).

    Raises:
        ForwardTestSessionNotFoundError: session absent or wrong owner.
        DraftNotFoundError: draft absent or wrong owner.
        ForwardTestPromotionError: session/draft mismatch or evidence gate failure.
        ValueError: lifecycle transition not permitted from current status.
    """
    from backend.core.config import settings as _settings  # noqa: PLC0415
    from backend.forward_testing.evidence import (  # noqa: PLC0415
        assess_ft_promotion_readiness,
    )
    from backend.forward_testing.exceptions import (  # noqa: PLC0415
        ForwardTestSessionNotFoundError as _ForwardTestSessionNotFoundError,  # noqa: F401
    )

    # 1 — load session; raises ForwardTestSessionNotFoundError for missing/wrong-owner
    session = ft_repository.load(session_id, owner_id=owner_id)

    # 2 — load draft; raises DraftNotFoundError for missing/wrong-owner
    draft = draft_repository.load(draft_id, owner_id=owner_id)

    # 3 — structural: session must have been created against THIS draft
    if session.draft_id != draft_id:
        raise ForwardTestPromotionError(
            f"Forward-test session '{session_id}' was created for draft "
            f"'{session.draft_id}', not '{draft_id}'."
        )

    # 4 — lifecycle gate: draft must currently be at BACKTESTED
    if draft.lifecycle_status != StrategyLifecycleStatus.BACKTESTED:
        raise ForwardTestPromotionError(
            f"Draft '{draft_id}' is currently '{draft.lifecycle_status.value}'; "
            "only 'backtested' drafts can be promoted to 'forward_tested'."
        )

    # 5–6 — evidence gates: minimum eligible bars AND minimum calendar days
    readiness = assess_ft_promotion_readiness(
        session=session,
        bar_store=ft_bar_store,
        min_eligible_bars=_settings.ft_min_eligible_bars,
        min_calendar_days=_settings.ft_min_calendar_days,
    )
    if not readiness.eligible:
        raise ForwardTestPromotionError(readiness.blocker or "Insufficient evidence.")

    # 7 — state machine: BACKTESTED → FORWARD_TESTED must be allowed
    validate_lifecycle_transition(draft.lifecycle_status, StrategyLifecycleStatus.FORWARD_TESTED)

    # 8 — mutate and persist
    existing_data = draft.model_dump()
    existing_data["lifecycle_status"] = StrategyLifecycleStatus.FORWARD_TESTED
    existing_data["updated_at"] = datetime.now(_UTC)
    if notes is not None:
        existing_data["notes"] = notes

    updated = StrategyDraft.model_validate(existing_data)
    draft_repository.update(updated, owner_id=owner_id)

    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.GOV_PROMOTION_REQUESTED,
        details={
            "draft_id":          draft_id,
            "session_id":        session_id,
            "from_status":       draft.lifecycle_status.value,
            "to_status":         StrategyLifecycleStatus.FORWARD_TESTED.value,
            "eligible_bars":     readiness.eligible_bars,
            "calendar_days":     readiness.calendar_days,
            "signals_recorded":  session.signals_recorded,
            "user_id":           owner_id,
        },
    ))

    return _to_response(updated)


# ---------------------------------------------------------------------------
# Lifecycle promotion — Phase P7
# ---------------------------------------------------------------------------

class PaperTestPromotionError(Exception):
    """Raised when paper-trading evidence fails to satisfy the paper-tested promotion gate."""


def promote_draft_to_paper_tested(
    session_id: str,
    draft_id: str,
    pt_repository,  # PaperTradingRepository — deferred to avoid circular imports
    draft_repository: DraftRepository,
    snapshot_store,  # AccountStateSnapshotStore — deferred to avoid circular imports
    owner_id: str,
    *,
    notes: str | None = None,
) -> DraftResponse:
    """
    Promote a draft to 'paper_tested' status, gated by hardened paper-trading evidence.

    Evidence requirements (P8C — all must hold):
      1. session.last_processed_bar_timestamp is not None — at least one bar was processed,
         proving a real paper cycle ran (data fetched, signals evaluated, orders managed).
      2. session.status in {TERMINATED, COMPLETED} — session is in a clean terminal state.
         Promotes only finalized sessions; running/paused sessions are mid-cycle.
         FAILED sessions are excluded (failed evidence is not promotion evidence).
      3. At least one AccountStateSnapshot exists — equity evidence is recorded and
         the paper runtime left an observable state trail.

    These three gates together ensure promotion evidence reflects a complete,
    committed paper-trading run rather than a partially-executed or failed session.

    Structural requirements (also checked; any failure raises before mutating state):
      - session exists and is owned by owner_id
      - draft exists and is owned by owner_id
      - session.draft_id == draft_id  (session was created for this exact draft)
      - draft.lifecycle_status == FORWARD_TESTED (only forward-tested drafts can advance)
      - validate_lifecycle_transition(FORWARD_TESTED, PAPER_TESTED) succeeds

    Raises:
        PaperTradingSessionNotFoundError: session absent or wrong owner.
        DraftNotFoundError: draft absent or wrong owner.
        PaperTestPromotionError: structural mismatch or any evidence gate failure.
        ValueError: lifecycle transition not permitted from current status.
    """
    from backend.paper_trading.exceptions import (  # noqa: PLC0415
        PaperTradingSessionNotFoundError as _PaperTradingSessionNotFoundError,  # noqa: F401
    )
    from backend.paper_trading.models import PaperTradingSessionStatus  # noqa: PLC0415

    _PROMOTION_ELIGIBLE_STATUSES = frozenset({
        PaperTradingSessionStatus.TERMINATED,
        PaperTradingSessionStatus.COMPLETED,
    })

    # 1 — load session; raises PaperTradingSessionNotFoundError for missing/wrong-owner
    session = pt_repository.load(session_id, owner_id=owner_id)

    # 2 — load draft; raises DraftNotFoundError for missing/wrong-owner
    draft = draft_repository.load(draft_id, owner_id=owner_id)

    # 3 — structural: session must have been created against THIS draft
    if session.draft_id != draft_id:
        raise PaperTestPromotionError(
            f"Paper-trading session '{session_id}' was created for draft "
            f"'{session.draft_id}', not '{draft_id}'."
        )

    # 4 — structural: draft must currently be at FORWARD_TESTED to advance
    if draft.lifecycle_status != StrategyLifecycleStatus.FORWARD_TESTED:
        raise PaperTestPromotionError(
            f"Draft '{draft_id}' is currently '{draft.lifecycle_status.value}'; "
            "only 'forward_tested' drafts can be promoted to 'paper_tested'."
        )

    # 5 — evidence gate 1: at least one bar was processed
    if session.last_processed_bar_timestamp is None:
        raise PaperTestPromotionError(
            f"Session '{session_id}' has not processed any bars. "
            "Run at least one complete paper-trading cycle before promotion."
        )

    # 6 — evidence gate 2: session must be in a finalized terminal state
    if session.status not in _PROMOTION_ELIGIBLE_STATUSES:
        raise PaperTestPromotionError(
            f"Session '{session_id}' has status '{session.status.value}'. "
            "Only terminated or completed sessions can be promoted. "
            "Terminate the session before requesting promotion."
        )

    # 7 — evidence gate 3: at least one equity snapshot must exist
    snapshot_count = snapshot_store.count(session_id)
    if snapshot_count < 1:
        raise PaperTestPromotionError(
            f"Session '{session_id}' has no equity snapshots. "
            "At least one equity snapshot is required to prove observable paper runtime state."
        )

    # 8 — state machine: FORWARD_TESTED → PAPER_TESTED must be allowed
    validate_lifecycle_transition(draft.lifecycle_status, StrategyLifecycleStatus.PAPER_TESTED)

    # 9 — mutate and persist
    existing_data = draft.model_dump()
    existing_data["lifecycle_status"] = StrategyLifecycleStatus.PAPER_TESTED
    existing_data["updated_at"] = datetime.now(_UTC)
    if notes is not None:
        existing_data["notes"] = notes

    updated = StrategyDraft.model_validate(existing_data)
    draft_repository.update(updated, owner_id=owner_id)

    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.GOV_PROMOTION_REQUESTED,
        details={
            "draft_id": draft_id,
            "session_id": session_id,
            "from_status": draft.lifecycle_status.value,
            "to_status": StrategyLifecycleStatus.PAPER_TESTED.value,
            "session_status": session.status.value,
            "last_bar_timestamp": session.last_processed_bar_timestamp.isoformat(),
            "equity_snapshot_count": snapshot_count,
            "user_id": owner_id,
        },
    ))

    return _to_response(updated)
