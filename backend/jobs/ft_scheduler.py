"""
ForwardTestSchedulerJob — FT-2 autonomous forward-test scheduler.

Runs on a configurable interval inside the FastAPI lifespan context.
Each tick scans all RUNNING forward-test sessions across all users and
calls ForwardTestService.run_cycle() for sessions whose cycle_interval has
elapsed.

Architecture invariants:
  - This module MUST NOT import from backend.strategy_registry (strategy logic
    stays in ForwardTestService).
  - This module MUST NOT import from backend.api (no HTTP coupling).
  - This module MUST NOT import from backend.execution (no broker logic).
  - Provider adapters are built via ProviderAdapterFactory only.
  - Vault credentials are resolved server-side only; the raw key is never
    logged, stored, or returned.
  - No live trading behavior. No order placement. No broker execution.
  - Disabled when settings.ft_scheduler_enabled is False.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event
from backend.core.config import settings
from backend.data.models.dataset import DatasetIdentity
from backend.data.models.instrument import AdjustmentMode, Instrument
from backend.data_providers.provider_factory import (
    ProviderAdapterFactory,
    ProviderBuildError,
    UnknownProviderError,
)
from backend.forward_testing.models import (
    ForwardTestSession,
    ForwardTestSessionStatus,
)
from backend.forward_testing.repository import ForwardTestRepository
from backend.forward_testing.service import ForwardTestService
from backend.forward_testing.stores import ForwardTestBarStore, ForwardTestSignalStore
from backend.services.ohlcv_service import OHLCVService
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ForwardTestSchedulerJob:
    """
    Scheduler job for autonomous forward-test evaluation.

    Constructed once at startup with all required service dependencies.
    run_tick() is called on the configured interval by APScheduler.
    """

    def __init__(
        self,
        repository: ForwardTestRepository,
        bar_store: ForwardTestBarStore,
        signal_store: ForwardTestSignalStore,
        ohlcv_service: OHLCVService,
        tool_registry: ToolRegistry,
        provider_factory: ProviderAdapterFactory,
    ) -> None:
        self._repository     = repository
        self._bar_store      = bar_store
        self._signal_store   = signal_store
        self._ohlcv_service  = ohlcv_service
        self._tool_registry  = tool_registry
        self._factory        = provider_factory

    # ------------------------------------------------------------------
    # Public entry point — called by APScheduler on each interval tick
    # ------------------------------------------------------------------

    def run_tick(self) -> None:
        """
        Execute one scheduler tick.

        Scans all RUNNING sessions globally, skips those whose
        cycle_interval has not yet elapsed, and calls run_cycle() for
        the rest.  Provider failures increment a per-session counter and
        trigger auto-pause after the configured threshold.

        Never raises — all exceptions are caught and logged so that a
        single bad session cannot crash the scheduler or the FastAPI process.
        """
        if not settings.ft_scheduler_enabled:
            return

        now_utc = datetime.now(timezone.utc)

        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.FT_SCHEDULER_TICK_STARTED,
            details={"tick_utc": now_utc.isoformat()},
        ))

        sessions_evaluated = 0
        sessions_skipped   = 0
        sessions_failed    = 0

        try:
            running_sessions = self._repository.list_all_running_globally()
        except Exception as exc:
            logger.error("ft_scheduler: failed to list running sessions: %s", exc)
            return

        # Emit recovery event when sessions are found on first tick (restart recovery)
        if running_sessions:
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.FT_SCHEDULER_RECOVERY,
                details={
                    "running_session_count": len(running_sessions),
                    "tick_utc": now_utc.isoformat(),
                },
            ))

        for session in running_sessions:
            try:
                skipped, reason = self._should_skip(session, now_utc)
                if skipped:
                    sessions_skipped += 1
                    emit_audit_event(AuditEvent(
                        event_kind=AuditEventKind.FT_SCHEDULER_SESSION_SKIPPED,
                        details={
                            "session_id": session.session_id,
                            "reason": reason,
                        },
                    ))
                    continue

                self._evaluate_session(session, now_utc)
                sessions_evaluated += 1

            except Exception as exc:
                sessions_failed += 1
                logger.error(
                    "ft_scheduler: unhandled error for session %s: %s",
                    session.session_id,
                    exc,
                )

        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.FT_SCHEDULER_TICK_COMPLETED,
            details={
                "tick_utc": now_utc.isoformat(),
                "sessions_evaluated": sessions_evaluated,
                "sessions_skipped":   sessions_skipped,
                "sessions_failed":    sessions_failed,
            },
        ))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _should_skip(
        self,
        session: ForwardTestSession,
        now_utc: datetime,
    ) -> tuple[bool, str]:
        """
        Return (True, reason) if this session should be skipped this tick.

        Reasons:
          - "not_running": status changed between list and here
          - "interval_not_elapsed": cycle_interval_seconds not yet elapsed
        """
        if session.status != ForwardTestSessionStatus.RUNNING:
            return True, "not_running"

        if session.last_cycle_attempted_at is not None:
            elapsed = (now_utc - session.last_cycle_attempted_at).total_seconds()
            if elapsed < session.cycle_interval_seconds:
                return True, "interval_not_elapsed"

        return False, ""

    def _evaluate_session(
        self,
        session: ForwardTestSession,
        now_utc: datetime,
    ) -> None:
        """
        Run one cycle for a RUNNING session and handle the result.

        last_cycle_attempted_at is written once in the single post-cycle update
        (either _handle_provider_failure or _reset_failure_counter / success path).
        There is no pre-cycle write — removing that write eliminates the stale-
        snapshot race where the pre-cycle update overwrote a concurrent update from
        the service layer and lost counter increments.

        Increments consecutive_provider_failures on failure; resets on success.
        Auto-pauses the session when the failure threshold is reached.
        """
        session_id = session.session_id

        # Build provider adapter from session metadata
        try:
            provider = _build_provider_for_session(session, self._factory)
        except Exception as exc:
            logger.error(
                "ft_scheduler: provider build failed for session %s: %s",
                session_id,
                exc,
            )
            self._handle_provider_failure(session, now_utc)
            return

        # Reconstruct DatasetIdentity
        instrument = Instrument(
            symbol=session.symbol,
            asset_class=session.asset_class,
            exchange=session.exchange,
        )
        identity = DatasetIdentity(
            instrument=instrument,
            provider=session.provider_name or "",
            timeframe=session.timeframe,
            adjustment_mode=AdjustmentMode.RAW,
        )

        # Call the evaluation engine
        service = ForwardTestService(
            repository=self._repository,
            signal_store=self._signal_store,
            bar_store=self._bar_store,
            ohlcv_service=self._ohlcv_service,
            tool_registry=self._tool_registry,
        )

        try:
            result = service.run_cycle(
                session_id=session_id,
                owner_id=session.user_id,
                identity=identity,
                provider=provider,
                now_utc=now_utc,
            )
        except Exception as exc:
            logger.error(
                "ft_scheduler: run_cycle raised for session %s: %s",
                session_id,
                exc,
            )
            self._handle_provider_failure(session, now_utc)
            return

        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.FT_SCHEDULER_SESSION_EVALUATED,
            details={
                "session_id":      session_id,
                "status":          result.status,
                "bars_processed":  result.bars_processed,
                "signals_generated": result.signals_generated,
                "gap_detected":    result.gap_detected,
                "provider_failure": result.provider_failure,
                "activated":       result.activated,
                "message":         result.message,
            },
        ))

        if result.provider_failure:
            self._handle_provider_failure(session, now_utc)
        else:
            # Success — reset the consecutive failure counter
            self._reset_failure_counter(session, now_utc)

    def _handle_provider_failure(
        self,
        session: ForwardTestSession,
        now_utc: datetime,
    ) -> None:
        """Increment failure counter; auto-pause when threshold is reached."""
        new_count = session.consecutive_provider_failures + 1
        threshold = settings.ft_scheduler_max_consecutive_failures

        if new_count >= threshold:
            # Auto-pause to prevent a permanently-failing session from cluttering the scan
            updated = session.model_copy(update={
                "status":                       ForwardTestSessionStatus.PAUSED,
                "consecutive_provider_failures": new_count,
                "last_cycle_attempted_at":       now_utc,
                "updated_at":                    now_utc,
                "failure_reason":
                    f"scheduler_auto_pause: {new_count} consecutive provider failures",
                "error_category": "provider_failure",
            })
            try:
                self._repository.update(updated, owner_id=session.user_id)
            except Exception as exc:
                logger.error(
                    "ft_scheduler: could not auto-pause session %s: %s",
                    session.session_id,
                    exc,
                )
                return

            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.FT_SCHEDULER_SESSION_AUTO_PAUSED,
                details={
                    "session_id":                    session.session_id,
                    "consecutive_provider_failures": new_count,
                    "threshold":                     threshold,
                },
            ))
            logger.warning(
                "ft_scheduler: auto-paused session %s after %d consecutive failures",
                session.session_id,
                new_count,
            )
        else:
            # Below threshold — just persist the incremented counter
            updated = session.model_copy(update={
                "consecutive_provider_failures": new_count,
                "last_cycle_attempted_at":       now_utc,
                "updated_at":                    now_utc,
            })
            try:
                self._repository.update(updated, owner_id=session.user_id)
            except Exception as exc:
                logger.warning(
                    "ft_scheduler: could not persist failure counter for %s: %s",
                    session.session_id,
                    exc,
                )

    def _reset_failure_counter(
        self,
        session: ForwardTestSession,
        now_utc: datetime,
    ) -> None:
        """Reset consecutive_provider_failures to 0 after a successful cycle."""
        if session.consecutive_provider_failures == 0:
            return  # Nothing to reset — avoid unnecessary write

        updated = session.model_copy(update={
            "consecutive_provider_failures": 0,
            "last_cycle_attempted_at":       now_utc,
            "updated_at":                    now_utc,
        })
        try:
            self._repository.update(updated, owner_id=session.user_id)
        except Exception as exc:
            logger.warning(
                "ft_scheduler: could not reset failure counter for %s: %s",
                session.session_id,
                exc,
            )


# ---------------------------------------------------------------------------
# Module-level provider builder (no HTTP, no vault — ENV fallback or no key)
# ---------------------------------------------------------------------------

def _build_provider_for_session(
    session: ForwardTestSession,
    factory: ProviderAdapterFactory,
) -> object:
    """
    Construct a RangeProviderAdapter for a session.

    Credential resolution: if session.credential_id is set, resolve the raw
    API key from the vault.  Returns None (ENV fallback) when credential_id
    is absent — identical to the behaviour in the route layer.

    Raw key is NEVER logged, stored, or included in any response.

    Raises:
        UnknownProviderError — provider_name not registered
        ProviderBuildError   — provider config invalid
        Any vault exception  — credential could not be resolved
    """
    provider_name = session.provider_name or ""
    api_key: str | None = None

    if session.credential_id:
        from backend.vault.repository import CredentialRepository
        from backend.vault.service import VaultService

        repo  = CredentialRepository(settings.credentials_file_path)
        vault = VaultService(repo)
        # resolve_secret raises on access-denied, disabled, or mismatch —
        # caller (_evaluate_session) catches all exceptions.
        api_key = vault.resolve_secret(
            credential_id=session.credential_id,
            requesting_user_id=session.user_id,
            provider_name=provider_name,
        )

    return factory.build(
        provider_name,
        symbol=session.symbol,
        asset_class=session.asset_class,
        venue=session.exchange,
        timeframe=session.timeframe,
        api_key=api_key,
    )


# ---------------------------------------------------------------------------
# Factory function — used by main.py lifespan
# ---------------------------------------------------------------------------

def create_ft_scheduler_job() -> ForwardTestSchedulerJob:
    """
    Instantiate a ForwardTestSchedulerJob with all production dependencies.

    Called once at FastAPI startup from the lifespan context.
    """
    from backend.api.dependencies import (
        get_forward_test_bar_store,
        get_forward_test_repository,
        get_forward_test_signal_store,
        get_ohlcv_service,
        get_provider_factory,
        get_tool_registry,
    )

    return ForwardTestSchedulerJob(
        repository=get_forward_test_repository(),
        bar_store=get_forward_test_bar_store(),
        signal_store=get_forward_test_signal_store(),
        ohlcv_service=get_ohlcv_service(),
        tool_registry=get_tool_registry(),
        provider_factory=get_provider_factory(),
    )
