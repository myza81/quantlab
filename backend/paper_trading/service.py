"""
PaperTradingService — Phase 4E.3.

Single-cycle execution engine for paper trading.

Executes EXACTLY ONE cycle per explicit call:
    PENDING  → activate (transition to RUNNING, fetch warmup bars)
    RUNNING  → poll (resolve pending orders, get new bars, evaluate, fill)
    PAUSED / terminal → no-op (returns PaperCycleResult with message)

Cycle execution order (per bar, ascending):
    1. Resolve NEXT_BAR_OPEN pending orders at bar.open
    2. Compute tool outputs (full window)
    3. Evaluate strategy signal (if bar is signal-eligible)
    4. Process signal: SIGNAL_BAR_CLOSE fills immediately; NEXT_BAR_OPEN creates pending order
    5. Mark open positions to bar.close
    6. Recalculate equity and drawdown
    7. Check drawdown stop (pause session if threshold exceeded)
    8. Append AccountStateSnapshot
    9. Advance cursor

No scheduler. No polling loop. No background workers. No API routes.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.backtesting
    backend.api
    backend.data_providers
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from backend.data_providers.range_provider import RangeProviderAdapter

from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event
from backend.core.config import settings
from backend.data.models.dataset import DatasetIdentity
from backend.forward_testing.models import ForwardTestBar, ForwardTestSignal
from backend.forward_testing.stores import ForwardTestBarStore, ForwardTestSignalStore
from backend.market_calendar import TradingCalendar, get_calendar
from backend.market_calendar.policy import is_bar_expected as _calendar_is_bar_expected
from backend.paper_trading.broker_adapter import PaperBrokerAdapter
from backend.paper_trading.exceptions import (
    PaperTradingInvalidTransitionError,
    PaperTradingSessionNotFoundError,
)
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
    AccountStateSnapshot,
    FillTimingModel,
    PaperAccount,
    PaperTradingSession,
    PaperTradingSessionStatus,
    is_pt_terminal_status,
    validate_pt_session_transition,
)
from backend.paper_trading.repository import PaperTradingRepository
from backend.paper_trading.stores import AccountStateSnapshotStore, PaperAccountStore
from backend.services.ohlcv_service import OHLCVService, timeframe_to_timedelta
from backend.strategy_registry.drafts import StrategyDraft
from backend.strategy_registry.historical_evaluator import (
    HistoricalBarContext,
    HistoricalEvaluationInput,
    evaluate_history,
)
from backend.strategy_registry.semantic_compiler import compile_semantics
from backend.tools.historical_computation import (
    ToolComputationBarInput,
    build_bar_tool_outputs,
    compute_tool_outputs_for_history,
    derive_warmup_bars_required,
)
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cycle result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PaperCycleResult:
    """
    Summary of one paper trading cycle.

    activated:              True when a PENDING session was transitioned to RUNNING.
    gap_detected:           True when an expected bar was absent (market closure excluded).
    provider_failure:       True when the data provider raised an error during the cycle.
    drawdown_stop_triggered: True when the drawdown threshold was exceeded.
    """
    session_id: str
    status: str
    bars_fetched: int
    bars_processed: int
    warmup_bars_processed: int
    signal_eligible_bars_processed: int
    signals_generated: int
    signals_suppressed: int
    pending_orders_resolved: int
    orders_created: int
    orders_rejected: int
    fills_created: int
    positions_opened: int
    positions_closed: int
    account_snapshot_created: bool
    last_processed_bar_timestamp: datetime | None
    gap_detected: bool
    provider_failure: bool
    activated: bool
    drawdown_stop_triggered: bool = False
    message: str | None = None


# ---------------------------------------------------------------------------
# PaperTradingService
# ---------------------------------------------------------------------------

class PaperTradingService:
    """
    Single-cycle execution engine for paper trading.

    Each call to run_cycle() executes exactly one cycle — caller is responsible
    for scheduling repeated calls via whatever mechanism suits their runtime.

    Execution contract:
      PENDING  → _activate()   (fetch warmup bars, transition to RUNNING)
      RUNNING  → _poll_cycle() (resolve pending, evaluate signal, fill, snapshot)
      PAUSED   → no-op
      terminal → no-op

    Pending order resolution ordering (mandatory, per directive):
      1. Load pending orders
      2. Resolve eligible pending orders using current bar open
      3. Create fills
      4. Update positions
      5. Update account
      6. Move orders from pending to filled/rejected/cancelled
      7. Emit audit events
      8. Only then evaluate new strategy signal
    """

    def __init__(
        self,
        repository: PaperTradingRepository,
        account_store: PaperAccountStore,
        snapshot_store: AccountStateSnapshotStore,
        order_store: PaperOrderStore,
        fill_store: PaperFillStore,
        position_store: PaperPositionStore,
        bar_store: ForwardTestBarStore,
        signal_store: ForwardTestSignalStore,
        ohlcv_service: OHLCVService,
        tool_registry: ToolRegistry,
    ) -> None:
        self._repository     = repository
        self._account_store  = account_store
        self._snapshot_store = snapshot_store
        self._order_store    = order_store
        self._fill_store     = fill_store
        self._position_store = position_store
        self._bar_store      = bar_store
        self._signal_store   = signal_store
        self._ohlcv_service  = ohlcv_service
        self._tool_registry  = tool_registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_cycle(
        self,
        session_id: str,
        owner_id: str,
        identity: DatasetIdentity,
        provider: "RangeProviderAdapter",
        *,
        now_utc: Optional[datetime] = None,
    ) -> PaperCycleResult:
        """
        Execute one paper trading cycle for the given session.

        PENDING → activation (warmup fetch, transition to RUNNING)
        RUNNING → poll cycle (resolve pending, get new bars, evaluate, fill, snapshot)
        PAUSED / terminal → no-op

        Args:
            session_id: UUID of the paper trading session.
            owner_id:   User ID from JWT; ownership enforced by the repository.
            identity:   Dataset identity (symbol, timeframe, provider, instrument).
            provider:   Market data provider adapter. Never stored or exposed.
            now_utc:    Reference "now" for bar finalization. Defaults to
                        datetime.now(timezone.utc). Pass explicitly in tests.

        Returns:
            PaperCycleResult describing what occurred during this cycle.
        """
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)

        session = self._repository.load(session_id, owner_id=owner_id)

        if is_pt_terminal_status(session.status):
            return PaperCycleResult(
                session_id=session_id,
                status=session.status.value,
                bars_fetched=0,
                bars_processed=0,
                warmup_bars_processed=0,
                signal_eligible_bars_processed=0,
                signals_generated=0,
                signals_suppressed=0,
                pending_orders_resolved=0,
                orders_created=0,
                orders_rejected=0,
                fills_created=0,
                positions_opened=0,
                positions_closed=0,
                account_snapshot_created=False,
                last_processed_bar_timestamp=session.last_processed_bar_timestamp,
                gap_detected=False,
                provider_failure=False,
                activated=False,
                message=(
                    f"session is in terminal state '{session.status.value}'; "
                    "no cycle performed"
                ),
            )

        if session.status == PaperTradingSessionStatus.PAUSED:
            return PaperCycleResult(
                session_id=session_id,
                status=session.status.value,
                bars_fetched=0,
                bars_processed=0,
                warmup_bars_processed=0,
                signal_eligible_bars_processed=0,
                signals_generated=0,
                signals_suppressed=0,
                pending_orders_resolved=0,
                orders_created=0,
                orders_rejected=0,
                fills_created=0,
                positions_opened=0,
                positions_closed=0,
                account_snapshot_created=False,
                last_processed_bar_timestamp=session.last_processed_bar_timestamp,
                gap_detected=False,
                provider_failure=False,
                activated=False,
                message="session is paused; no cycle performed",
            )

        if session.status == PaperTradingSessionStatus.PENDING:
            return self._activate(session, owner_id, identity, provider, now_utc)

        # RUNNING — deserialize strategy, compile semantics, then poll
        draft, plan, warmup_bars_required, compile_error = self._prepare_strategy(session)
        if compile_error is not None:
            return PaperCycleResult(
                session_id=session_id,
                status=session.status.value,
                bars_fetched=0,
                bars_processed=0,
                warmup_bars_processed=0,
                signal_eligible_bars_processed=0,
                signals_generated=0,
                signals_suppressed=0,
                pending_orders_resolved=0,
                orders_created=0,
                orders_rejected=0,
                fills_created=0,
                positions_opened=0,
                positions_closed=0,
                account_snapshot_created=False,
                last_processed_bar_timestamp=session.last_processed_bar_timestamp,
                gap_detected=False,
                provider_failure=True,
                activated=False,
                message=compile_error,
            )

        calendar = get_calendar(
            identity.instrument.asset_class,
            provider_name=identity.provider,
            symbol=identity.instrument.symbol,
        )

        return self._poll_cycle(
            session=session,
            owner_id=owner_id,
            identity=identity,
            provider=provider,
            plan=plan,
            draft=draft,
            warmup_bars_required=warmup_bars_required,
            calendar=calendar,
            now_utc=now_utc,
        )

    # ------------------------------------------------------------------
    # Activation (PENDING → RUNNING)
    # ------------------------------------------------------------------

    def _activate(
        self,
        session: PaperTradingSession,
        owner_id: str,
        identity: DatasetIdentity,
        provider: "RangeProviderAdapter",
        now_utc: datetime,
    ) -> PaperCycleResult:
        """Activate a PENDING session: fetch warmup bars and transition to RUNNING."""
        session_id = session.session_id
        account_id = session.account_id

        try:
            validate_pt_session_transition(
                PaperTradingSessionStatus.PENDING,
                PaperTradingSessionStatus.RUNNING,
            )
        except PaperTradingInvalidTransitionError as exc:
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.PT_ACTIVATION_DENIED,
                details={
                    "session_id": session_id,
                    "account_id": account_id,
                    "reason": "invalid_transition",
                    "detail": str(exc),
                },
            ))
            return PaperCycleResult(
                session_id=session_id,
                status=session.status.value,
                bars_fetched=0,
                bars_processed=0,
                warmup_bars_processed=0,
                signal_eligible_bars_processed=0,
                signals_generated=0,
                signals_suppressed=0,
                pending_orders_resolved=0,
                orders_created=0,
                orders_rejected=0,
                fills_created=0,
                positions_opened=0,
                positions_closed=0,
                account_snapshot_created=False,
                last_processed_bar_timestamp=session.last_processed_bar_timestamp,
                gap_detected=False,
                provider_failure=False,
                activated=False,
                message=f"activation denied: {exc}",
            )

        # Derive warmup from strategy
        _, _, warmup_bars_required, _ = self._prepare_strategy(session)

        # Fetch warmup bars
        warmup_bars = []
        provider_failure = False
        if warmup_bars_required > 0:
            try:
                warmup_bars = self._ohlcv_service.get_recent_bars(
                    identity=identity,
                    limit=warmup_bars_required,
                    provider=provider,
                    reference_time=now_utc,
                    bar_finalization_buffer_seconds=(
                        settings.forward_test_bar_finalization_buffer_seconds
                    ),
                )
            except Exception as exc:
                logger.error(
                    "PaperTradingService: warmup fetch failed for session %s: %s",
                    session_id,
                    exc,
                )
                emit_audit_event(AuditEvent(
                    event_kind=AuditEventKind.PT_PROVIDER_FAILURE,
                    details={
                        "session_id": session_id,
                        "account_id": account_id,
                        "phase": "warmup",
                        "error_category": "provider_fetch_error",
                    },
                ))
                provider_failure = True

        # Persist warmup bars
        existing_count = self._bar_store.count_bars(session_id)
        warmup_stored = 0
        last_warmup_ts: datetime | None = None

        for i, bar in enumerate(warmup_bars):
            ft_bar = ForwardTestBar(
                session_id=session_id,
                bar_index=existing_count + i,
                bar_timestamp=bar.timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                source_mode=session.source_mode,
                provider_name=session.provider_name,
                catalog_id=session.catalog_id,
                is_warmup_bar=True,
                processed_at=now_utc,
            )
            was_new = self._bar_store.append_bar(ft_bar)
            if was_new:
                warmup_stored += 1
            last_warmup_ts = bar.timestamp

        cursor = last_warmup_ts if last_warmup_ts is not None else now_utc

        # Transition PENDING → RUNNING
        updated_session = session.model_copy(update={
            "status": PaperTradingSessionStatus.RUNNING,
            "updated_at": now_utc,
            "activation_timestamp": now_utc,
            "last_processed_bar_timestamp": cursor,
        })
        self._repository.update(updated_session, owner_id=owner_id)

        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.PT_SESSION_ACTIVATED,
            details={
                "session_id": session_id,
                "account_id": account_id,
                "warmup_bars_required": warmup_bars_required,
                "warmup_bars_fetched": len(warmup_bars),
                "warmup_bars_stored": warmup_stored,
                "cursor": cursor.isoformat(),
            },
        ))

        return PaperCycleResult(
            session_id=session_id,
            status=PaperTradingSessionStatus.RUNNING.value,
            bars_fetched=len(warmup_bars),
            bars_processed=warmup_stored,
            warmup_bars_processed=warmup_stored,
            signal_eligible_bars_processed=0,
            signals_generated=0,
            signals_suppressed=0,
            pending_orders_resolved=0,
            orders_created=0,
            orders_rejected=0,
            fills_created=0,
            positions_opened=0,
            positions_closed=0,
            account_snapshot_created=False,
            last_processed_bar_timestamp=cursor,
            gap_detected=False,
            provider_failure=provider_failure,
            activated=True,
        )

    # ------------------------------------------------------------------
    # Poll cycle (RUNNING)
    # ------------------------------------------------------------------

    def _poll_cycle(
        self,
        session: PaperTradingSession,
        owner_id: str,
        identity: DatasetIdentity,
        provider: "RangeProviderAdapter",
        plan: object,
        draft: StrategyDraft,
        warmup_bars_required: int,
        calendar: TradingCalendar,
        now_utc: datetime,
    ) -> PaperCycleResult:
        """Execute one poll cycle for a RUNNING session."""
        session_id  = session.session_id
        account_id  = session.account_id
        assumptions = session.simulation_assumptions

        # Determine cursor
        cursor = session.last_processed_bar_timestamp or session.activation_timestamp
        if cursor is None:
            return PaperCycleResult(
                session_id=session_id,
                status=session.status.value,
                bars_fetched=0,
                bars_processed=0,
                warmup_bars_processed=0,
                signal_eligible_bars_processed=0,
                signals_generated=0,
                signals_suppressed=0,
                pending_orders_resolved=0,
                orders_created=0,
                orders_rejected=0,
                fills_created=0,
                positions_opened=0,
                positions_closed=0,
                account_snapshot_created=False,
                last_processed_bar_timestamp=None,
                gap_detected=False,
                provider_failure=False,
                activated=False,
                message="no cursor available; session was not properly activated",
            )

        # Fetch new finalized bars since cursor
        new_bars = []
        provider_failure = False
        try:
            new_bars = self._ohlcv_service.get_bars_since(
                identity=identity,
                since_timestamp=cursor,
                provider=provider,
                reference_time=now_utc,
                bar_finalization_buffer_seconds=(
                    settings.forward_test_bar_finalization_buffer_seconds
                ),
            )
        except Exception as exc:
            logger.error(
                "PaperTradingService: poll fetch failed for session %s: %s",
                session_id,
                exc,
            )
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.PT_PROVIDER_FAILURE,
                details={
                    "session_id": session_id,
                    "account_id": account_id,
                    "phase": "poll",
                    "error_category": "provider_fetch_error",
                },
            ))
            provider_failure = True

        # Gap detection
        gap_detected = False
        if new_bars and not provider_failure:
            try:
                tf_delta = timeframe_to_timedelta(session.timeframe)
                expected_next_ts = cursor + tf_delta
                first_bar_ts = new_bars[0].timestamp
                if (
                    _calendar_is_bar_expected(expected_next_ts, session.timeframe, calendar)
                    and expected_next_ts < first_bar_ts
                ):
                    gap_detected = True
                    emit_audit_event(AuditEvent(
                        event_kind=AuditEventKind.PT_GAP_DETECTED,
                        details={
                            "session_id": session_id,
                            "account_id": account_id,
                            "expected_next_bar": expected_next_ts.isoformat(),
                            "first_actual_bar": first_bar_ts.isoformat(),
                        },
                    ))
            except Exception as exc:
                logger.warning(
                    "PaperTradingService: gap detection error for session %s: %s",
                    session_id,
                    exc,
                )

        if not new_bars:
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.PT_POLL_COMPLETED,
                details={
                    "session_id": session_id,
                    "account_id": account_id,
                    "bars_fetched": 0,
                    "bars_processed": 0,
                    "signals_generated": 0,
                    "gap_detected": gap_detected,
                    "provider_failure": provider_failure,
                },
            ))
            return PaperCycleResult(
                session_id=session_id,
                status=session.status.value,
                bars_fetched=0,
                bars_processed=0,
                warmup_bars_processed=0,
                signal_eligible_bars_processed=0,
                signals_generated=0,
                signals_suppressed=0,
                pending_orders_resolved=0,
                orders_created=0,
                orders_rejected=0,
                fills_created=0,
                positions_opened=0,
                positions_closed=0,
                account_snapshot_created=False,
                last_processed_bar_timestamp=session.last_processed_bar_timestamp,
                gap_detected=gap_detected,
                provider_failure=provider_failure,
                activated=False,
                message="no new finalized bars",
            )

        # Load stored bars for full-window recomputation
        stored_bars = self._bar_store.list_bars(session_id)
        stored_ts_set = {sb.bar_timestamp for sb in stored_bars}

        # Deduplicate new bars against stored
        next_bar_index = len(stored_bars)
        indexed_new_bars: list[tuple[int, object]] = []
        for bar in new_bars:
            if bar.timestamp not in stored_ts_set:
                indexed_new_bars.append((next_bar_index, bar))
                next_bar_index += 1

        # Counters
        bars_processed            = 0
        signal_eligible_count     = 0
        signals_generated         = 0
        signals_suppressed        = 0
        pending_orders_resolved   = 0
        orders_created            = 0
        orders_rejected           = 0
        fills_created             = 0
        positions_opened          = 0
        positions_closed          = 0
        account_snapshot_created  = False
        drawdown_stop_triggered   = False
        last_new_bar_ts: datetime | None = None

        # Process each new bar
        for bar_index, bar in indexed_new_bars:
            is_warmup = bar_index < warmup_bars_required
            is_signal_eligible = not is_warmup

            # ── Step 1: Resolve NEXT_BAR_OPEN pending orders at bar.open ──────
            account = self._account_store.load_by_session_id(session_id)
            pending = self._order_store.load_pending(session_id, owner_id)
            for porder in pending:
                r, a, fo, pc = self._resolve_pending_order(
                    session=session,
                    account=account,
                    pending_order=porder,
                    bar_open=bar.open,  # type: ignore[union-attr]
                    bar_timestamp=bar.timestamp,  # type: ignore[union-attr]
                    now_utc=now_utc,
                )
                if r == "filled":
                    pending_orders_resolved += 1
                    fills_created += 1
                    if fo == "opened":
                        positions_opened += 1
                    elif fo == "closed":
                        positions_closed += 1
                elif r == "rejected" or r == "cancelled":
                    orders_rejected += 1
                account = a  # carry updated account forward

            # ── Step 2: Full-window tool computation ──────────────────────────
            all_comp_bars = self._build_computation_inputs(
                stored_bars=stored_bars,
                bar_index=bar_index,
                bar=bar,
            )

            bar_tool_outputs: dict[int, dict[str, float]] = {}
            if all_comp_bars and draft is not None:
                try:
                    comp_result = compute_tool_outputs_for_history(
                        draft.toolset, all_comp_bars, self._tool_registry
                    )
                    bar_tool_outputs = build_bar_tool_outputs(comp_result)
                except Exception as exc:
                    logger.error(
                        "PaperTradingService: tool computation failed for session %s: %s",
                        session_id,
                        exc,
                    )

            # ── Step 3: Evaluate strategy signal ──────────────────────────────
            if is_signal_eligible and plan is not None:
                all_contexts = self._build_evaluation_contexts(
                    stored_bars=stored_bars,
                    bar_index=bar_index,
                    bar=bar,
                    bar_tool_outputs=bar_tool_outputs,
                )
                bar_result = None
                if all_contexts:
                    try:
                        eval_result = evaluate_history(HistoricalEvaluationInput(
                            plan=plan,  # type: ignore[arg-type]
                            bars=tuple(all_contexts),
                        ))
                        for r in eval_result.bar_results:
                            if r.bar_index == bar_index:
                                bar_result = r
                                break
                    except Exception as exc:
                        logger.error(
                            "PaperTradingService: evaluation failed for session %s: %s",
                            session_id,
                            exc,
                        )

                # ── Step 4: Process signals ───────────────────────────────────���
                account = self._account_store.load_by_session_id(session_id)
                if bar_result is not None:
                    if getattr(bar_result, "entry_triggered", False):
                        rule_id = _get_triggered_rule_id(bar_result, "entry")
                        sig_id = str(uuid.uuid4())
                        was_new = self._signal_store.append_signal(ForwardTestSignal(
                            signal_id=sig_id,
                            session_id=session_id,
                            user_id=owner_id,
                            bar_timestamp=bar.timestamp,  # type: ignore[union-attr]
                            signal_timestamp=now_utc,
                            signal_direction="entry_long",
                            rule_id=rule_id,
                            bar_open=bar.open,  # type: ignore[union-attr]
                            bar_high=bar.high,  # type: ignore[union-attr]
                            bar_low=bar.low,  # type: ignore[union-attr]
                            bar_close=bar.close,  # type: ignore[union-attr]
                            bar_volume=bar.volume,  # type: ignore[union-attr]
                            feature_values_at_signal=bar_tool_outputs.get(bar_index, {}),
                            warmup_satisfied=True,
                            strategy_snapshot_hash=session.strategy_snapshot.snapshot_hash,
                            symbol=session.symbol,
                            timeframe=session.timeframe,
                            provider_name=session.provider_name,
                            catalog_id=session.catalog_id,
                            created_at=now_utc,
                        ))
                        if was_new:
                            signals_generated += 1
                            oc, rej, account, n_open, n_close = self._process_entry_signal(
                                session=session,
                                account=account,
                                bar=bar,
                                signal_id=sig_id,
                                now_utc=now_utc,
                            )
                            orders_created  += oc
                            orders_rejected += rej
                            fills_created   += oc if assumptions.fill_timing_model == FillTimingModel.SIGNAL_BAR_CLOSE else 0
                            positions_opened += n_open
                            positions_closed += n_close
                        else:
                            signals_suppressed += 1

                    if getattr(bar_result, "exit_triggered", False):
                        rule_id = _get_triggered_rule_id(bar_result, "exit")
                        sig_id = str(uuid.uuid4())
                        was_new = self._signal_store.append_signal(ForwardTestSignal(
                            signal_id=sig_id,
                            session_id=session_id,
                            user_id=owner_id,
                            bar_timestamp=bar.timestamp,  # type: ignore[union-attr]
                            signal_timestamp=now_utc,
                            signal_direction="exit_long",
                            rule_id=rule_id,
                            bar_open=bar.open,  # type: ignore[union-attr]
                            bar_high=bar.high,  # type: ignore[union-attr]
                            bar_low=bar.low,  # type: ignore[union-attr]
                            bar_close=bar.close,  # type: ignore[union-attr]
                            bar_volume=bar.volume,  # type: ignore[union-attr]
                            feature_values_at_signal=bar_tool_outputs.get(bar_index, {}),
                            warmup_satisfied=True,
                            strategy_snapshot_hash=session.strategy_snapshot.snapshot_hash,
                            symbol=session.symbol,
                            timeframe=session.timeframe,
                            provider_name=session.provider_name,
                            catalog_id=session.catalog_id,
                            created_at=now_utc,
                        ))
                        if was_new:
                            signals_generated += 1
                            oc, rej, account, n_open, n_close = self._process_exit_signal(
                                session=session,
                                account=account,
                                bar=bar,
                                signal_id=sig_id,
                                now_utc=now_utc,
                            )
                            orders_created  += oc
                            orders_rejected += rej
                            fills_created   += oc if assumptions.fill_timing_model == FillTimingModel.SIGNAL_BAR_CLOSE else 0
                            positions_opened += n_open
                            positions_closed += n_close
                        else:
                            signals_suppressed += 1

                signal_eligible_count += 1

            # ── Step 5+6: Mark-to-market + equity/drawdown recalculation ──────
            account = self._account_store.load_by_session_id(session_id)
            account = self._mark_to_market(
                session_id=session_id,
                account=account,
                bar_close=bar.close,  # type: ignore[union-attr]
                now_utc=now_utc,
            )
            self._account_store.update(account)

            # ── Step 7: Drawdown stop check ───────────────────────────────────
            if (
                assumptions.max_drawdown_stop_pct is not None
                and account.current_drawdown_pct >= assumptions.max_drawdown_stop_pct
            ):
                drawdown_stop_triggered = True
                emit_audit_event(AuditEvent(
                    event_kind=AuditEventKind.PT_DRAWDOWN_STOP_TRIGGERED,
                    details={
                        "session_id": session_id,
                        "account_id": account_id,
                        "current_drawdown_pct": account.current_drawdown_pct,
                        "threshold_pct": assumptions.max_drawdown_stop_pct,
                    },
                ))
                # Transition session to PAUSED
                paused_session = session.model_copy(update={
                    "status": PaperTradingSessionStatus.PAUSED,
                    "updated_at": now_utc,
                    "last_processed_bar_timestamp": bar.timestamp,  # type: ignore[union-attr]
                })
                self._repository.update(paused_session, owner_id=owner_id)
                emit_audit_event(AuditEvent(
                    event_kind=AuditEventKind.PT_SESSION_PAUSED_DRAWDOWN_STOP,
                    details={
                        "session_id": session_id,
                        "account_id": account_id,
                        "drawdown_pct": account.current_drawdown_pct,
                    },
                ))
                # Stop processing further bars this cycle
                bars_processed += 1
                last_new_bar_ts = bar.timestamp  # type: ignore[union-attr]
                break

            # ── Step 8: Account state snapshot ───────────────────────────────
            if is_signal_eligible:
                open_positions = self._position_store.list_open_positions(session_id)
                total_unrealized = sum(p.unrealized_pnl for p in open_positions)
                snapshot = AccountStateSnapshot(
                    snapshot_id=str(uuid.uuid4()),
                    session_id=session_id,
                    account_id=account_id,
                    user_id=owner_id,
                    bar_timestamp=bar.timestamp,  # type: ignore[union-attr]
                    snapshot_timestamp=now_utc,
                    cash_balance=account.cash_balance,
                    equity=account.equity,
                    available_cash=account.available_cash,
                    peak_equity=account.peak_equity,
                    current_drawdown_pct=account.current_drawdown_pct,
                    open_position_count=len(open_positions),
                    realized_pnl=account.total_realized_pnl,
                    unrealized_pnl=total_unrealized,
                    created_at=now_utc,
                )
                self._snapshot_store.append(snapshot)
                account_snapshot_created = True

            # ── Step 9: Persist bar + advance cursor ──────────────────────────
            ft_bar = ForwardTestBar(
                session_id=session_id,
                bar_index=bar_index,
                bar_timestamp=bar.timestamp,  # type: ignore[union-attr]
                open=bar.open,  # type: ignore[union-attr]
                high=bar.high,  # type: ignore[union-attr]
                low=bar.low,  # type: ignore[union-attr]
                close=bar.close,  # type: ignore[union-attr]
                volume=bar.volume,  # type: ignore[union-attr]
                source_mode=session.source_mode,
                provider_name=session.provider_name,
                catalog_id=session.catalog_id,
                is_warmup_bar=is_warmup,
                processed_at=now_utc,
            )
            was_new_bar = self._bar_store.append_bar(ft_bar)
            if was_new_bar:
                bars_processed += 1
                last_new_bar_ts = bar.timestamp  # type: ignore[union-attr]

        # Update session cursor (only bars processed this cycle)
        new_cursor = last_new_bar_ts or session.last_processed_bar_timestamp
        final_status = (
            PaperTradingSessionStatus.PAUSED.value if drawdown_stop_triggered
            else session.status.value
        )

        if not drawdown_stop_triggered and bars_processed > 0:
            updated_session = session.model_copy(update={
                "updated_at": now_utc,
                "last_processed_bar_timestamp": new_cursor,
            })
            self._repository.update(updated_session, owner_id=owner_id)

        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.PT_POLL_COMPLETED,
            details={
                "session_id": session_id,
                "account_id": account_id,
                "bars_fetched": len(new_bars),
                "bars_processed": bars_processed,
                "signal_eligible_bars_processed": signal_eligible_count,
                "signals_generated": signals_generated,
                "fills_created": fills_created,
                "gap_detected": gap_detected,
                "provider_failure": provider_failure,
                "cursor": new_cursor.isoformat() if new_cursor else None,
            },
        ))

        return PaperCycleResult(
            session_id=session_id,
            status=final_status,
            bars_fetched=len(new_bars),
            bars_processed=bars_processed,
            warmup_bars_processed=0,
            signal_eligible_bars_processed=signal_eligible_count,
            signals_generated=signals_generated,
            signals_suppressed=signals_suppressed,
            pending_orders_resolved=pending_orders_resolved,
            orders_created=orders_created,
            orders_rejected=orders_rejected,
            fills_created=fills_created,
            positions_opened=positions_opened,
            positions_closed=positions_closed,
            account_snapshot_created=account_snapshot_created,
            last_processed_bar_timestamp=new_cursor,
            gap_detected=gap_detected,
            provider_failure=provider_failure,
            activated=False,
            drawdown_stop_triggered=drawdown_stop_triggered,
        )

    # ------------------------------------------------------------------
    # Pending order resolution (NEXT_BAR_OPEN)
    # ------------------------------------------------------------------

    def _resolve_pending_order(
        self,
        session: PaperTradingSession,
        account: PaperAccount,
        pending_order: PaperOrder,
        bar_open: float,
        bar_timestamp: datetime,
        now_utc: datetime,
    ) -> tuple[str, PaperAccount, str | None, str | None]:
        """
        Resolve one NEXT_BAR_OPEN pending order at bar.open.

        Returns:
            (result, updated_account, filled_order_event, position_event)
            result: "filled" | "cancelled" | "rejected"
            position_event: "opened" | "closed" | "scaled" | None
        """
        session_id  = session.session_id
        account_id  = session.account_id
        assumptions = session.simulation_assumptions
        correlation_id = str(uuid.uuid4())

        # Build fill (slippage and fee applied)
        exec_reason = (
            ExecutionReason.SIGNAL_ENTRY if pending_order.direction == OrderDirection.BUY
            else ExecutionReason.SIGNAL_EXIT
        )
        filled_order, fill = PaperBrokerAdapter.build_fill(
            order=pending_order,
            gross_price=bar_open,
            fill_bar_timestamp=bar_timestamp,
            assumptions=assumptions,
            execution_reason=exec_reason,
            fill_timestamp=now_utc,
        )

        # For BUY: check cash sufficiency at fill time
        if pending_order.direction == OrderDirection.BUY:
            required_cash = fill.net_value + fill.fee
            if account.cash_balance < required_cash:
                cancelled_order = pending_order.model_copy(update={
                    "status": PaperOrderStatus.CANCELLED,
                    "cancellation_reason": "insufficient_cash_at_fill",
                    "updated_at": now_utc,
                })
                self._order_store.mark_cancelled(cancelled_order, "insufficient_cash_at_fill")
                emit_audit_event(AuditEvent(
                    event_kind=AuditEventKind.PT_ORDER_CANCELLED,
                    correlation_id=correlation_id,
                    details={
                        "session_id": session_id,
                        "account_id": account_id,
                        "order_id": pending_order.order_id,
                        "reason": "insufficient_cash_at_fill",
                        "cash_available": account.cash_balance,
                        "cash_required": required_cash,
                    },
                ))
                return "cancelled", account, None, None

        # For SELL: verify open position still exists
        if pending_order.direction == OrderDirection.SELL:
            position = self._find_open_position(session_id, session.symbol)
            if position is None:
                cancelled_order = pending_order.model_copy(update={
                    "status": PaperOrderStatus.CANCELLED,
                    "cancellation_reason": "no_position_to_close",
                    "updated_at": now_utc,
                })
                self._order_store.mark_cancelled(cancelled_order, "no_position_to_close")
                emit_audit_event(AuditEvent(
                    event_kind=AuditEventKind.PT_ORDER_CANCELLED,
                    correlation_id=correlation_id,
                    details={
                        "session_id": session_id,
                        "account_id": account_id,
                        "order_id": pending_order.order_id,
                        "reason": "no_position_to_close",
                    },
                ))
                return "cancelled", account, None, None

        # Apply fill
        updated_account, position_event = self._apply_fill(
            session=session,
            account=account,
            fill=fill,
            now_utc=now_utc,
            correlation_id=correlation_id,
        )

        # Persist order state change + fill
        self._order_store.mark_filled(filled_order, fill)
        self._fill_store.append(fill)
        self._account_store.update(updated_account)

        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.PT_FILL_GENERATED,
            correlation_id=correlation_id,
            details={
                "session_id": session_id,
                "account_id": account_id,
                "fill_id": fill.fill_id,
                "order_id": pending_order.order_id,
                "direction": fill.direction.value,
                "fill_price": fill.fill_price,
                "quantity": fill.quantity,
                "gross_value": fill.gross_value,
                "fee": fill.fee,
                "net_value": fill.net_value,
            },
        ))

        return "filled", updated_account, None, position_event

    # ------------------------------------------------------------------
    # Signal processing
    # ------------------------------------------------------------------

    def _process_entry_signal(
        self,
        session: PaperTradingSession,
        account: PaperAccount,
        bar: object,
        signal_id: str,
        now_utc: datetime,
    ) -> tuple[int, int, PaperAccount, int, int]:
        """
        Process an entry (BUY) signal.

        Returns (orders_created, orders_rejected, updated_account, positions_opened, positions_closed).
        """
        session_id  = session.session_id
        account_id  = session.account_id
        assumptions = session.simulation_assumptions
        correlation_id = str(uuid.uuid4())

        bar_close: float = bar.close  # type: ignore[union-attr]

        # Validate intent: max_positions check
        existing_pos = self._find_open_position(session_id, session.symbol)
        if existing_pos is None:
            open_count = self._position_store.count_open(session_id)
            if open_count >= assumptions.max_concurrent_positions:
                rejected_order = PaperBrokerAdapter.reject_order(
                    session_id=session_id,
                    account_id=account_id,
                    user_id=session.user_id,
                    symbol=session.symbol,
                    direction=OrderDirection.BUY,
                    quantity=1,  # placeholder; real qty unknown at rejection
                    fill_timing_model=assumptions.fill_timing_model,
                    signal_bar_timestamp=bar.timestamp,  # type: ignore[union-attr]
                    rejection_reason=RejectionReason.MAX_POSITIONS_EXCEEDED.value,
                    signal_id=signal_id,
                )
                self._order_store.mark_rejected(rejected_order, RejectionReason.MAX_POSITIONS_EXCEEDED.value)
                emit_audit_event(AuditEvent(
                    event_kind=AuditEventKind.PT_ORDER_REJECTED,
                    correlation_id=correlation_id,
                    details={
                        "session_id": session_id,
                        "account_id": account_id,
                        "rejection_reason": RejectionReason.MAX_POSITIONS_EXCEEDED.value,
                        "open_count": open_count,
                        "max_positions": assumptions.max_concurrent_positions,
                    },
                ))
                return 0, 1, account, 0, 0

        # Compute quantity
        qty = PaperBrokerAdapter.compute_quantity(
            assumptions=assumptions,
            fill_price=bar_close,
            current_equity=account.equity,
        )
        if qty == 0:
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.PT_ORDER_REJECTED,
                correlation_id=correlation_id,
                details={
                    "session_id": session_id,
                    "account_id": account_id,
                    "rejection_reason": "quantity_resolved_to_zero",
                    "equity": account.equity,
                    "bar_close": bar_close,
                },
            ))
            return 0, 1, account, 0, 0

        # Check cash sufficiency (estimate using bar.close)
        _, slippage_estimate = PaperBrokerAdapter.compute_fill_price(
            direction=OrderDirection.BUY,
            gross_price=bar_close,
            assumptions=assumptions,
        )
        estimated_fill_price = bar_close + slippage_estimate
        fee_estimate = PaperBrokerAdapter.compute_fee(qty, bar_close, assumptions)
        required_cash = qty * estimated_fill_price + fee_estimate

        if account.cash_balance < required_cash:
            rejected_order = PaperBrokerAdapter.reject_order(
                session_id=session_id,
                account_id=account_id,
                user_id=session.user_id,
                symbol=session.symbol,
                direction=OrderDirection.BUY,
                quantity=qty,
                fill_timing_model=assumptions.fill_timing_model,
                signal_bar_timestamp=bar.timestamp,  # type: ignore[union-attr]
                rejection_reason=RejectionReason.INSUFFICIENT_CASH.value,
                signal_id=signal_id,
            )
            self._order_store.mark_rejected(rejected_order, RejectionReason.INSUFFICIENT_CASH.value)
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.PT_ORDER_REJECTED,
                correlation_id=correlation_id,
                details={
                    "session_id": session_id,
                    "account_id": account_id,
                    "rejection_reason": RejectionReason.INSUFFICIENT_CASH.value,
                    "cash_available": account.cash_balance,
                    "cash_required": required_cash,
                },
            ))
            return 0, 1, account, 0, 0

        # Create order
        order = PaperBrokerAdapter.create_pending_order(
            session_id=session_id,
            account_id=account_id,
            user_id=session.user_id,
            symbol=session.symbol,
            direction=OrderDirection.BUY,
            quantity=qty,
            fill_timing_model=assumptions.fill_timing_model,
            signal_bar_timestamp=bar.timestamp,  # type: ignore[union-attr]
            signal_id=signal_id,
        )

        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.PT_ORDER_CREATED,
            correlation_id=correlation_id,
            details={
                "session_id": session_id,
                "account_id": account_id,
                "order_id": order.order_id,
                "direction": OrderDirection.BUY.value,
                "quantity": qty,
                "fill_timing_model": assumptions.fill_timing_model.value,
            },
        ))

        if assumptions.fill_timing_model == FillTimingModel.SIGNAL_BAR_CLOSE:
            # Fill immediately at bar.close
            filled_order, fill = PaperBrokerAdapter.build_fill(
                order=order,
                gross_price=bar_close,
                fill_bar_timestamp=bar.timestamp,  # type: ignore[union-attr]
                assumptions=assumptions,
                execution_reason=ExecutionReason.SIGNAL_ENTRY,
                fill_timestamp=now_utc,
            )
            updated_account, position_event = self._apply_fill(
                session=session,
                account=account,
                fill=fill,
                now_utc=now_utc,
                correlation_id=correlation_id,
            )
            self._order_store.mark_filled(filled_order, fill)
            self._fill_store.append(fill)
            self._account_store.update(updated_account)
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.PT_FILL_GENERATED,
                correlation_id=correlation_id,
                details={
                    "session_id": session_id,
                    "account_id": account_id,
                    "fill_id": fill.fill_id,
                    "order_id": order.order_id,
                    "fill_price": fill.fill_price,
                    "quantity": fill.quantity,
                    "net_value": fill.net_value,
                },
            ))
            n_open = 1 if position_event == "opened" else 0
            n_close = 1 if position_event == "closed" else 0
            return 1, 0, updated_account, n_open, n_close
        else:
            # NEXT_BAR_OPEN: persist pending order; fill at next bar open
            self._order_store.save_pending(order)
            return 1, 0, account, 0, 0

    def _process_exit_signal(
        self,
        session: PaperTradingSession,
        account: PaperAccount,
        bar: object,
        signal_id: str,
        now_utc: datetime,
    ) -> tuple[int, int, PaperAccount, int, int]:
        """
        Process an exit (SELL) signal.

        Returns (orders_created, orders_rejected, updated_account, positions_opened, positions_closed).
        """
        session_id  = session.session_id
        account_id  = session.account_id
        assumptions = session.simulation_assumptions
        correlation_id = str(uuid.uuid4())

        bar_close: float = bar.close  # type: ignore[union-attr]

        # Find open position
        position = self._find_open_position(session_id, session.symbol)
        if position is None:
            rejected_order = PaperBrokerAdapter.reject_order(
                session_id=session_id,
                account_id=account_id,
                user_id=session.user_id,
                symbol=session.symbol,
                direction=OrderDirection.SELL,
                quantity=1,
                fill_timing_model=assumptions.fill_timing_model,
                signal_bar_timestamp=bar.timestamp,  # type: ignore[union-attr]
                rejection_reason=RejectionReason.NO_POSITION_TO_CLOSE.value,
                signal_id=signal_id,
            )
            self._order_store.mark_rejected(rejected_order, RejectionReason.NO_POSITION_TO_CLOSE.value)
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.PT_ORDER_REJECTED,
                correlation_id=correlation_id,
                details={
                    "session_id": session_id,
                    "account_id": account_id,
                    "rejection_reason": RejectionReason.NO_POSITION_TO_CLOSE.value,
                    "symbol": session.symbol,
                },
            ))
            return 0, 1, account, 0, 0

        # Use position quantity as sell quantity
        qty = int(position.quantity)
        if qty == 0:
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.PT_ORDER_REJECTED,
                correlation_id=correlation_id,
                details={
                    "session_id": session_id,
                    "account_id": account_id,
                    "rejection_reason": "position_quantity_zero",
                },
            ))
            return 0, 1, account, 0, 0

        # Create order
        order = PaperBrokerAdapter.create_pending_order(
            session_id=session_id,
            account_id=account_id,
            user_id=session.user_id,
            symbol=session.symbol,
            direction=OrderDirection.SELL,
            quantity=qty,
            fill_timing_model=assumptions.fill_timing_model,
            signal_bar_timestamp=bar.timestamp,  # type: ignore[union-attr]
            signal_id=signal_id,
        )

        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.PT_ORDER_CREATED,
            correlation_id=correlation_id,
            details={
                "session_id": session_id,
                "account_id": account_id,
                "order_id": order.order_id,
                "direction": OrderDirection.SELL.value,
                "quantity": qty,
                "fill_timing_model": assumptions.fill_timing_model.value,
            },
        ))

        if assumptions.fill_timing_model == FillTimingModel.SIGNAL_BAR_CLOSE:
            filled_order, fill = PaperBrokerAdapter.build_fill(
                order=order,
                gross_price=bar_close,
                fill_bar_timestamp=bar.timestamp,  # type: ignore[union-attr]
                assumptions=assumptions,
                execution_reason=ExecutionReason.SIGNAL_EXIT,
                fill_timestamp=now_utc,
            )
            updated_account, position_event = self._apply_fill(
                session=session,
                account=account,
                fill=fill,
                now_utc=now_utc,
                correlation_id=correlation_id,
            )
            self._order_store.mark_filled(filled_order, fill)
            self._fill_store.append(fill)
            self._account_store.update(updated_account)
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.PT_FILL_GENERATED,
                correlation_id=correlation_id,
                details={
                    "session_id": session_id,
                    "account_id": account_id,
                    "fill_id": fill.fill_id,
                    "order_id": order.order_id,
                    "fill_price": fill.fill_price,
                    "quantity": fill.quantity,
                    "net_value": fill.net_value,
                },
            ))
            n_open = 1 if position_event == "opened" else 0
            n_close = 1 if position_event == "closed" else 0
            return 1, 0, updated_account, n_open, n_close
        else:
            self._order_store.save_pending(order)
            return 1, 0, account, 0, 0

    # ------------------------------------------------------------------
    # Fill application: position + account update
    # ------------------------------------------------------------------

    def _apply_fill(
        self,
        session: PaperTradingSession,
        account: PaperAccount,
        fill: PaperFill,
        now_utc: datetime,
        correlation_id: str | None = None,
    ) -> tuple[PaperAccount, str | None]:
        """
        Apply a fill to positions and account state.

        Returns (updated_account, position_event) where position_event is
        "opened" | "closed" | "scaled" | None.
        """
        if fill.direction == OrderDirection.BUY:
            return self._apply_buy_fill(session, account, fill, now_utc, correlation_id)
        return self._apply_sell_fill(session, account, fill, now_utc, correlation_id)

    def _apply_buy_fill(
        self,
        session: PaperTradingSession,
        account: PaperAccount,
        fill: PaperFill,
        now_utc: datetime,
        correlation_id: str | None,
    ) -> tuple[PaperAccount, str | None]:
        session_id = session.session_id
        account_id = session.account_id
        qty = float(fill.quantity)

        existing_pos = self._find_open_position(session_id, session.symbol)

        if existing_pos is not None:
            # Scale in: update average entry price
            old_qty   = existing_pos.quantity
            old_avg   = existing_pos.average_entry_price
            new_qty   = old_qty + qty
            new_avg   = (old_qty * old_avg + qty * fill.fill_price) / new_qty
            market_val   = new_qty * existing_pos.current_price
            unrealized   = (existing_pos.current_price - new_avg) * new_qty

            updated_pos = existing_pos.model_copy(update={
                "quantity":            new_qty,
                "average_entry_price": new_avg,
                "market_value":        market_val,
                "unrealized_pnl":      unrealized,
                "last_updated_at":     now_utc,
            })
            self._position_store.update(updated_pos)
            position_event = "scaled"
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.PT_POSITION_SCALED,
                correlation_id=correlation_id,
                details={
                    "session_id": session_id,
                    "account_id": account_id,
                    "position_id": existing_pos.position_id,
                    "symbol": session.symbol,
                    "new_quantity": new_qty,
                    "new_avg_entry_price": new_avg,
                },
            ))
        else:
            # Open new position
            new_pos = PaperPosition(
                position_id=str(uuid.uuid4()),
                session_id=session_id,
                account_id=account_id,
                user_id=session.user_id,
                symbol=session.symbol,
                quantity=qty,
                average_entry_price=fill.fill_price,
                current_price=fill.fill_price,
                market_value=qty * fill.fill_price,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                is_open=True,
                opened_at=now_utc,
                last_updated_at=now_utc,
                opening_signal_id=fill.order_id,
            )
            self._position_store.save(new_pos)
            position_event = "opened"
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.PT_POSITION_OPENED,
                correlation_id=correlation_id,
                details={
                    "session_id": session_id,
                    "account_id": account_id,
                    "position_id": new_pos.position_id,
                    "symbol": session.symbol,
                    "quantity": qty,
                    "entry_price": fill.fill_price,
                },
            ))

        # Account: deduct cash
        cash_out = fill.net_value + fill.fee
        new_cash   = account.cash_balance - cash_out
        new_equity = self._compute_equity(session_id, new_cash)
        new_peak   = max(account.peak_equity, new_equity)
        new_drawdown = _compute_drawdown(new_equity, new_peak)

        updated_account = account.model_copy(update={
            "cash_balance":            max(0.0, new_cash),
            "equity":                  new_equity,
            "available_cash":          max(0.0, new_cash),
            "peak_equity":             new_peak,
            "current_drawdown_pct":    new_drawdown,
            "total_fees_paid":         account.total_fees_paid + fill.fee,
            "total_slippage_applied":  account.total_slippage_applied + (fill.slippage * qty),
            "updated_at":              now_utc,
        })
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.PT_ACCOUNT_UPDATED,
            correlation_id=correlation_id,
            details={
                "session_id": session_id,
                "account_id": account_id,
                "trigger": "buy_fill",
                "cash_delta": -cash_out,
                "new_cash_balance": updated_account.cash_balance,
                "new_equity": updated_account.equity,
            },
        ))
        return updated_account, position_event

    def _apply_sell_fill(
        self,
        session: PaperTradingSession,
        account: PaperAccount,
        fill: PaperFill,
        now_utc: datetime,
        correlation_id: str | None,
    ) -> tuple[PaperAccount, str | None]:
        session_id = session.session_id
        account_id = session.account_id
        qty = float(fill.quantity)

        position = self._find_open_position(session_id, session.symbol)
        if position is None:
            # No open position — this shouldn't happen if validation ran correctly
            logger.warning(
                "PaperTradingService: sell fill for session %s has no open position",
                session_id,
            )
            return account, None

        # Realized P&L per unit
        realized_pnl_per_unit = fill.fill_price - position.average_entry_price
        realized_pnl = realized_pnl_per_unit * qty
        new_qty = position.quantity - qty

        if new_qty <= 0:
            # Close position fully
            closed_pos = position.model_copy(update={
                "is_open":          False,
                "quantity":         0.0,
                "market_value":     0.0,
                "unrealized_pnl":   0.0,
                "realized_pnl":     position.realized_pnl + realized_pnl,
                "closed_at":        now_utc,
                "last_updated_at":  now_utc,
                "current_price":    fill.fill_price,
            })
            self._position_store.update(closed_pos)
            position_event = "closed"
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.PT_POSITION_CLOSED,
                correlation_id=correlation_id,
                details={
                    "session_id": session_id,
                    "account_id": account_id,
                    "position_id": position.position_id,
                    "symbol": session.symbol,
                    "realized_pnl": realized_pnl,
                    "fill_price": fill.fill_price,
                },
            ))
        else:
            # Partial close
            market_val  = new_qty * position.current_price
            unrealized  = (position.current_price - position.average_entry_price) * new_qty
            partial_pos = position.model_copy(update={
                "quantity":         new_qty,
                "market_value":     market_val,
                "unrealized_pnl":   unrealized,
                "realized_pnl":     position.realized_pnl + realized_pnl,
                "last_updated_at":  now_utc,
            })
            self._position_store.update(partial_pos)
            position_event = "reduced"

        # Account: add cash
        cash_in = fill.net_value - fill.fee
        new_cash   = account.cash_balance + cash_in
        new_equity = self._compute_equity(session_id, new_cash)
        new_peak   = max(account.peak_equity, new_equity)
        new_drawdown = _compute_drawdown(new_equity, new_peak)

        updated_account = account.model_copy(update={
            "cash_balance":          new_cash,
            "equity":                new_equity,
            "available_cash":        new_cash,
            "peak_equity":           new_peak,
            "current_drawdown_pct":  new_drawdown,
            "total_realized_pnl":    account.total_realized_pnl + realized_pnl,
            "total_fees_paid":       account.total_fees_paid + fill.fee,
            "total_slippage_applied": account.total_slippage_applied + (fill.slippage * qty),
            "updated_at":            now_utc,
        })
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.PT_ACCOUNT_UPDATED,
            correlation_id=correlation_id,
            details={
                "session_id": session_id,
                "account_id": account_id,
                "trigger": "sell_fill",
                "cash_delta": cash_in,
                "realized_pnl": realized_pnl,
                "new_cash_balance": updated_account.cash_balance,
                "new_equity": updated_account.equity,
            },
        ))
        return updated_account, position_event

    # ------------------------------------------------------------------
    # Mark-to-market
    # ------------------------------------------------------------------

    def _mark_to_market(
        self,
        session_id: str,
        account: PaperAccount,
        bar_close: float,
        now_utc: datetime,
    ) -> PaperAccount:
        """
        Update all open positions with current close price; recalculate equity.
        """
        open_positions = self._position_store.list_open_positions(session_id)
        total_market_value = 0.0

        for pos in open_positions:
            market_val  = pos.quantity * bar_close
            unrealized  = (bar_close - pos.average_entry_price) * pos.quantity
            updated_pos = pos.model_copy(update={
                "current_price":    bar_close,
                "market_value":     market_val,
                "unrealized_pnl":   unrealized,
                "last_updated_at":  now_utc,
            })
            self._position_store.update(updated_pos)
            total_market_value += market_val

        new_equity   = account.cash_balance + total_market_value
        new_peak     = max(account.peak_equity, new_equity)
        new_drawdown = _compute_drawdown(new_equity, new_peak)

        return account.model_copy(update={
            "equity":               new_equity,
            "peak_equity":          new_peak,
            "current_drawdown_pct": new_drawdown,
            "available_cash":       account.cash_balance,
            "updated_at":           now_utc,
        })

    # ------------------------------------------------------------------
    # Position lookup
    # ------------------------------------------------------------------

    def _find_open_position(
        self,
        session_id: str,
        symbol: str,
    ) -> PaperPosition | None:
        """Return the first open position for this symbol in this session, or None."""
        open_positions = self._position_store.list_open_positions(session_id)
        for pos in open_positions:
            if pos.symbol == symbol.upper():
                return pos
        return None

    # ------------------------------------------------------------------
    # Equity computation
    # ------------------------------------------------------------------

    def _compute_equity(self, session_id: str, cash_balance: float) -> float:
        """Compute current equity: cash + sum of open position market values."""
        open_positions = self._position_store.list_open_positions(session_id)
        return max(0.0, cash_balance + sum(p.market_value for p in open_positions))

    # ------------------------------------------------------------------
    # Bar context builders
    # ------------------------------------------------------------------

    def _build_computation_inputs(
        self,
        stored_bars: list,
        bar_index: int,
        bar: object,
    ) -> list[ToolComputationBarInput]:
        result: list[ToolComputationBarInput] = [
            ToolComputationBarInput(
                bar_index=sb.bar_index,
                timestamp=sb.bar_timestamp,
                price_fields={
                    "close": sb.close,
                    "open": sb.open,
                    "high": sb.high,
                    "low": sb.low,
                    "volume": sb.volume,
                },
            )
            for sb in stored_bars
        ]
        result.append(ToolComputationBarInput(
            bar_index=bar_index,
            timestamp=bar.timestamp,  # type: ignore[union-attr]
            price_fields={
                "close": bar.close,  # type: ignore[union-attr]
                "open": bar.open,  # type: ignore[union-attr]
                "high": bar.high,  # type: ignore[union-attr]
                "low": bar.low,  # type: ignore[union-attr]
                "volume": bar.volume,  # type: ignore[union-attr]
            },
        ))
        return result

    def _build_evaluation_contexts(
        self,
        stored_bars: list,
        bar_index: int,
        bar: object,
        bar_tool_outputs: dict[int, dict[str, float]],
    ) -> list[HistoricalBarContext]:
        result: list[HistoricalBarContext] = [
            HistoricalBarContext(
                bar_index=sb.bar_index,
                timestamp=sb.bar_timestamp,
                price_fields={
                    "close": sb.close,
                    "open": sb.open,
                    "high": sb.high,
                    "low": sb.low,
                    "volume": sb.volume,
                },
                tool_outputs=bar_tool_outputs.get(sb.bar_index, {}),
            )
            for sb in stored_bars
        ]
        result.append(HistoricalBarContext(
            bar_index=bar_index,
            timestamp=bar.timestamp,  # type: ignore[union-attr]
            price_fields={
                "close": bar.close,  # type: ignore[union-attr]
                "open": bar.open,  # type: ignore[union-attr]
                "high": bar.high,  # type: ignore[union-attr]
                "low": bar.low,  # type: ignore[union-attr]
                "volume": bar.volume,  # type: ignore[union-attr]
            },
            tool_outputs=bar_tool_outputs.get(bar_index, {}),
        ))
        return result

    # ------------------------------------------------------------------
    # Strategy preparation
    # ------------------------------------------------------------------

    def _prepare_strategy(
        self,
        session: PaperTradingSession,
    ) -> tuple[StrategyDraft | None, object, int, str | None]:
        """
        Deserialize strategy snapshot and compile semantics.

        Returns:
            (draft, plan, warmup_bars_required, error_message)
            error_message is None on success.
        """
        try:
            draft = StrategyDraft.model_validate_json(
                session.strategy_snapshot.strategy_json
            )
        except Exception as exc:
            logger.error(
                "PaperTradingService: strategy deserialization failed for session %s: %s",
                session.session_id,
                exc,
            )
            return None, None, 0, "strategy snapshot deserialization failed"

        warmup_bars_required = self._compute_warmup_for_draft(draft)

        if draft.semantics is None:
            return draft, None, warmup_bars_required, "strategy snapshot has no semantics; cannot evaluate"

        compilation = compile_semantics(draft.semantics, draft_id=session.draft_id)
        if not compilation.compiled or compilation.evaluation_plan is None:
            errors = "; ".join(compilation.errors) if compilation.errors else "unknown"
            return draft, None, warmup_bars_required, f"strategy compilation failed: {errors}"

        return draft, compilation.evaluation_plan, warmup_bars_required, None

    def _compute_warmup_for_draft(self, draft: StrategyDraft) -> int:
        """Derive warmup_bars_required from the draft's toolset."""
        if draft.toolset is None or not draft.toolset.tools:
            return 0
        max_warmup = 0
        for tool_config in draft.toolset.tools:
            try:
                metadata = self._tool_registry.get(tool_config.tool_id)
                w = derive_warmup_bars_required(tool_config, metadata)
                max_warmup = max(max_warmup, w)
            except Exception as exc:
                logger.warning(
                    "PaperTradingService: warmup derivation failed for tool %s: %s",
                    tool_config.tool_id,
                    exc,
                )
        return max_warmup


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _compute_drawdown(equity: float, peak_equity: float) -> float:
    """Compute current drawdown as percentage in [0, 100]."""
    if peak_equity <= 0:
        return 0.0
    drawdown = (peak_equity - equity) / peak_equity * 100.0
    return max(0.0, min(100.0, drawdown))


def _get_triggered_rule_id(bar_result: object, kind: str) -> str:
    """Extract rule_id from the first triggered rule of the given kind."""
    trace = getattr(bar_result, "trace", None)
    for rule_result in getattr(trace, "rule_results", ()):
        if (
            getattr(rule_result, "kind", None) == kind
            and getattr(rule_result, "triggered", None) is True
        ):
            rid = getattr(rule_result, "rule_id", None)
            return rid if rid else kind
    return kind
