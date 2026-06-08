"""
ForwardTestService — Phase 4C.4.

Single-cycle evaluation engine for forward testing.

Executes EXACTLY ONE cycle per explicit call:
    PENDING  → activate (transition to RUNNING, fetch warmup bars)
    RUNNING  → poll (get new finalized bars, evaluate, record signals)
    PAUSED / terminal → no-op (returns CycleResult with message)

No scheduler. No polling loop. No background workers.

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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from backend.data_providers.range_provider import RangeProviderAdapter

from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event
from backend.core.config import settings
from backend.data.models.dataset import DatasetIdentity
from backend.forward_testing.exceptions import ForwardTestInvalidTransitionError
from backend.forward_testing.models import (
    ForwardTestBar,
    ForwardTestSession,
    ForwardTestSessionStatus,
    ForwardTestSignal,
    is_terminal_status,
    validate_session_transition,
)
from backend.forward_testing.repository import ForwardTestRepository
from backend.forward_testing.stores import ForwardTestBarStore, ForwardTestSignalStore
from backend.market_calendar import TradingCalendar, get_calendar
from backend.market_calendar.policy import is_bar_expected as _calendar_is_bar_expected
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
)
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cycle result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CycleResult:
    """
    Summary of one forward-test cycle.

    activated:      True when a PENDING session was transitioned to RUNNING.
    gap_detected:   True when an expected bar was absent (market closure excluded).
    provider_failure: True when the data provider raised an error during the cycle.
    """
    session_id: str
    status: str
    bars_fetched: int
    bars_processed: int
    warmup_bars_processed: int
    signal_eligible_bars_processed: int
    signals_generated: int
    signals_suppressed: int
    last_processed_bar_timestamp: datetime | None
    gap_detected: bool
    provider_failure: bool
    activated: bool
    message: str | None = None


# ---------------------------------------------------------------------------
# ForwardTestService
# ---------------------------------------------------------------------------

class ForwardTestService:
    """
    Single-cycle evaluation engine for forward testing.

    Each call to run_cycle() executes exactly one cycle — caller is responsible
    for scheduling repeated calls via whatever mechanism suits their runtime.
    """

    def __init__(
        self,
        repository: ForwardTestRepository,
        signal_store: ForwardTestSignalStore,
        bar_store: ForwardTestBarStore,
        ohlcv_service: OHLCVService,
        tool_registry: ToolRegistry,
    ) -> None:
        self._repository = repository
        self._signal_store = signal_store
        self._bar_store = bar_store
        self._ohlcv_service = ohlcv_service
        self._tool_registry = tool_registry

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
    ) -> CycleResult:
        """
        Execute one forward-test cycle for the given session.

        PENDING → activation (warmup fetch, transition to RUNNING)
        RUNNING → poll cycle (get new bars, evaluate, emit signals)
        PAUSED / terminal → no-op

        Args:
            session_id: UUID of the forward test session.
            owner_id:   User ID from JWT; ownership enforced by the repository.
            identity:   Dataset identity (symbol, timeframe, provider, instrument).
                        Caller constructs this from session metadata + route context.
            provider:   Market data provider adapter. Never stored or exposed.
            now_utc:    Reference "now" for bar finalization. Defaults to
                        datetime.now(timezone.utc). Pass explicitly in tests.

        Returns:
            CycleResult describing what occurred during this cycle.
        """
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)

        session = self._repository.load(session_id, owner_id=owner_id)

        if is_terminal_status(session.status):
            return CycleResult(
                session_id=session_id,
                status=session.status.value,
                bars_fetched=0,
                bars_processed=0,
                warmup_bars_processed=0,
                signal_eligible_bars_processed=0,
                signals_generated=0,
                signals_suppressed=0,
                last_processed_bar_timestamp=session.last_processed_bar_timestamp,
                gap_detected=False,
                provider_failure=False,
                activated=False,
                message=(
                    f"session is in terminal state '{session.status.value}'; "
                    "no cycle performed"
                ),
            )

        if session.status == ForwardTestSessionStatus.PAUSED:
            return CycleResult(
                session_id=session_id,
                status=session.status.value,
                bars_fetched=0,
                bars_processed=0,
                warmup_bars_processed=0,
                signal_eligible_bars_processed=0,
                signals_generated=0,
                signals_suppressed=0,
                last_processed_bar_timestamp=session.last_processed_bar_timestamp,
                gap_detected=False,
                provider_failure=False,
                activated=False,
                message="session is paused; no cycle performed",
            )

        if session.status == ForwardTestSessionStatus.PENDING:
            return self._activate(session, owner_id, identity, provider, now_utc)

        # RUNNING — deserialize strategy, compile semantics, then poll
        draft, plan, compile_error = self._prepare_strategy(session)
        if compile_error is not None:
            return CycleResult(
                session_id=session_id,
                status=session.status.value,
                bars_fetched=0,
                bars_processed=0,
                warmup_bars_processed=0,
                signal_eligible_bars_processed=0,
                signals_generated=0,
                signals_suppressed=0,
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
            calendar=calendar,
            now_utc=now_utc,
        )

    # ------------------------------------------------------------------
    # Activation (PENDING → RUNNING)
    # ------------------------------------------------------------------

    def _activate(
        self,
        session: ForwardTestSession,
        owner_id: str,
        identity: DatasetIdentity,
        provider: "RangeProviderAdapter",
        now_utc: datetime,
    ) -> CycleResult:
        """Activate a PENDING session: fetch warmup bars and transition to RUNNING."""
        session_id = session.session_id

        try:
            validate_session_transition(
                ForwardTestSessionStatus.PENDING,
                ForwardTestSessionStatus.RUNNING,
            )
        except ForwardTestInvalidTransitionError as exc:
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.FT_ACTIVATION_DENIED,
                details={
                    "session_id": session_id,
                    "reason": "invalid_transition",
                    "detail": str(exc),
                },
            ))
            return CycleResult(
                session_id=session_id,
                status=session.status.value,
                bars_fetched=0,
                bars_processed=0,
                warmup_bars_processed=0,
                signal_eligible_bars_processed=0,
                signals_generated=0,
                signals_suppressed=0,
                last_processed_bar_timestamp=session.last_processed_bar_timestamp,
                gap_detected=False,
                provider_failure=False,
                activated=False,
                message=f"activation denied: {exc}",
            )

        # Fetch warmup bars
        warmup_bars = []
        provider_failure = False
        if session.warmup_bars_required > 0:
            try:
                warmup_bars = self._ohlcv_service.get_recent_bars(
                    identity=identity,
                    limit=session.warmup_bars_required,
                    provider=provider,
                    reference_time=now_utc,
                    bar_finalization_buffer_seconds=(
                        settings.forward_test_bar_finalization_buffer_seconds
                    ),
                )
            except Exception as exc:
                logger.error(
                    "ForwardTestService: warmup fetch failed for session %s: %s",
                    session_id,
                    exc,
                )
                emit_audit_event(AuditEvent(
                    event_kind=AuditEventKind.FT_PROVIDER_FAILURE,
                    details={
                        "session_id": session_id,
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

        # Cursor: last warmup bar timestamp; fallback to now_utc for no-warmup sessions
        cursor = last_warmup_ts if last_warmup_ts is not None else now_utc

        # Transition PENDING → RUNNING
        updated_session = session.model_copy(update={
            "status": ForwardTestSessionStatus.RUNNING,
            "updated_at": now_utc,
            "activation_timestamp": now_utc,
            "last_processed_bar_timestamp": cursor,
            "warmup_bars_processed": session.warmup_bars_processed + warmup_stored,
            "bars_evaluated": session.bars_evaluated + warmup_stored,
        })
        self._repository.update(updated_session, owner_id=owner_id)

        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.FT_SESSION_ACTIVATED,
            details={
                "session_id": session_id,
                "warmup_bars_required": session.warmup_bars_required,
                "warmup_bars_fetched": len(warmup_bars),
                "warmup_bars_stored": warmup_stored,
                "cursor": cursor.isoformat(),
            },
        ))

        return CycleResult(
            session_id=session_id,
            status=ForwardTestSessionStatus.RUNNING.value,
            bars_fetched=len(warmup_bars),
            bars_processed=warmup_stored,
            warmup_bars_processed=warmup_stored,
            signal_eligible_bars_processed=0,
            signals_generated=0,
            signals_suppressed=0,
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
        session: ForwardTestSession,
        owner_id: str,
        identity: DatasetIdentity,
        provider: "RangeProviderAdapter",
        plan: object,
        draft: StrategyDraft,
        calendar: TradingCalendar,
        now_utc: datetime,
    ) -> CycleResult:
        """Execute one poll cycle for a RUNNING session."""
        session_id = session.session_id

        # Determine cursor
        cursor = session.last_processed_bar_timestamp or session.activation_timestamp
        if cursor is None:
            return CycleResult(
                session_id=session_id,
                status=session.status.value,
                bars_fetched=0,
                bars_processed=0,
                warmup_bars_processed=0,
                signal_eligible_bars_processed=0,
                signals_generated=0,
                signals_suppressed=0,
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
                "ForwardTestService: poll fetch failed for session %s: %s",
                session_id,
                exc,
            )
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.FT_PROVIDER_FAILURE,
                details={
                    "session_id": session_id,
                    "phase": "poll",
                    "error_category": "provider_fetch_error",
                },
            ))
            provider_failure = True

        # Gap detection: check for expected bars absent between cursor and first new bar
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
                        event_kind=AuditEventKind.FT_GAP_DETECTED,
                        details={
                            "session_id": session_id,
                            "expected_next_bar": expected_next_ts.isoformat(),
                            "first_actual_bar": first_bar_ts.isoformat(),
                        },
                    ))
            except Exception as exc:
                logger.warning(
                    "ForwardTestService: gap detection error for session %s: %s",
                    session_id,
                    exc,
                )

        if not new_bars:
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.FT_POLL_COMPLETED,
                details={
                    "session_id": session_id,
                    "bars_fetched": 0,
                    "bars_processed": 0,
                    "signals_generated": 0,
                    "gap_detected": gap_detected,
                    "provider_failure": provider_failure,
                },
            ))
            return CycleResult(
                session_id=session_id,
                status=session.status.value,
                bars_fetched=0,
                bars_processed=0,
                warmup_bars_processed=0,
                signal_eligible_bars_processed=0,
                signals_generated=0,
                signals_suppressed=0,
                last_processed_bar_timestamp=session.last_processed_bar_timestamp,
                gap_detected=gap_detected,
                provider_failure=provider_failure,
                activated=False,
                message="no new finalized bars",
            )

        # Load stored bars for full-window recomputation
        stored_bars = self._bar_store.list_bars(session_id)
        stored_ts_set = {sb.bar_timestamp for sb in stored_bars}

        # Only process truly new bars (deduplicate against store)
        next_bar_index = len(stored_bars)
        indexed_new_bars: list[tuple[int, object]] = []
        for bar in new_bars:
            if bar.timestamp not in stored_ts_set:
                indexed_new_bars.append((next_bar_index, bar))
                next_bar_index += 1

        # All provider bars were already stored (provider re-delivered) — no work needed
        if not indexed_new_bars:
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.FT_POLL_COMPLETED,
                details={
                    "session_id": session_id,
                    "bars_fetched": len(new_bars),
                    "bars_processed": 0,
                    "signal_eligible_bars_processed": 0,
                    "signals_generated": 0,
                    "signals_suppressed": 0,
                    "gap_detected": gap_detected,
                    "provider_failure": provider_failure,
                    "cursor": session.last_processed_bar_timestamp.isoformat()
                    if session.last_processed_bar_timestamp else None,
                    "last_computed_bar_index": session.last_computed_bar_index,
                },
            ))
            return CycleResult(
                session_id=session_id,
                status=session.status.value,
                bars_fetched=len(new_bars),
                bars_processed=0,
                warmup_bars_processed=0,
                signal_eligible_bars_processed=0,
                signals_generated=0,
                signals_suppressed=0,
                last_processed_bar_timestamp=session.last_processed_bar_timestamp,
                gap_detected=gap_detected,
                provider_failure=provider_failure,
                activated=False,
                message="all fetched bars already stored (provider re-delivered)",
            )

        # Determine safe watermark: the highest bar_index already evaluated.
        # Clamp to max available bar index to guard against watermark inconsistency
        # (e.g. bars were externally cleared or session was migrated).
        watermark = session.last_computed_bar_index  # may be None
        if watermark is not None and stored_bars:
            max_stored_index = max(sb.bar_index for sb in stored_bars)
            if watermark > max_stored_index:
                # Watermark is ahead of available bars — reset and recompute safely
                watermark = None
        # bars_to_evaluate: new bars that have NOT yet been evaluated for signals.
        # Full historical context is still passed to tool computation + evaluate_history
        # to preserve indicator warmup correctness (EMA/RSI depend on earlier bars).
        bars_to_evaluate_indices: set[int] = {
            bar_index
            for bar_index, _ in indexed_new_bars
            if watermark is None or bar_index > watermark
        }

        # Full-window tool computation (stored + new)
        all_comp_bars: list[ToolComputationBarInput] = [
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
        ] + [
            ToolComputationBarInput(
                bar_index=bar_index,
                timestamp=bar.timestamp,  # type: ignore[union-attr]
                price_fields={
                    "close": bar.close,  # type: ignore[union-attr]
                    "open": bar.open,  # type: ignore[union-attr]
                    "high": bar.high,  # type: ignore[union-attr]
                    "low": bar.low,  # type: ignore[union-attr]
                    "volume": bar.volume,  # type: ignore[union-attr]
                },
            )
            for bar_index, bar in indexed_new_bars
        ]

        bar_tool_outputs: dict[int, dict[str, float]] = {}
        if all_comp_bars:
            try:
                comp_result = compute_tool_outputs_for_history(
                    draft.toolset, all_comp_bars, self._tool_registry
                )
                bar_tool_outputs = build_bar_tool_outputs(comp_result)
            except Exception as exc:
                logger.error(
                    "ForwardTestService: tool computation failed for session %s: %s",
                    session_id,
                    exc,
                )

        # Build HistoricalBarContext for ALL bars (stored + new)
        all_contexts: list[HistoricalBarContext] = [
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
        ] + [
            HistoricalBarContext(
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
            )
            for bar_index, bar in indexed_new_bars
        ]

        # Evaluate ALL bars; filter results to bars that need evaluation this cycle.
        # bars_to_evaluate_indices are new bars with bar_index > watermark.
        # Passing full all_contexts preserves indicator warmup for stateful tools.
        new_bar_result_map: dict[int, object] = {}
        if all_contexts:
            try:
                eval_result = evaluate_history(HistoricalEvaluationInput(
                    plan=plan,  # type: ignore[arg-type]
                    bars=tuple(all_contexts),
                ))
                new_bar_result_map = {
                    r.bar_index: r
                    for r in eval_result.bar_results
                    if r.bar_index in bars_to_evaluate_indices
                }
            except Exception as exc:
                logger.error(
                    "ForwardTestService: evaluation failed for session %s: %s",
                    session_id,
                    exc,
                )

        # Persist new bars + generate signals
        bars_processed = 0
        signal_eligible_count = 0
        signals_generated = 0
        signals_suppressed = 0
        last_new_bar_ts: datetime | None = None

        for _bar_pos, (bar_index, bar) in enumerate(indexed_new_bars):
            is_signal_eligible = (bar_index >= session.warmup_bars_required)
            # Only emit signals and count eligible bars for bars above the watermark
            is_new_for_evaluation = (bar_index in bars_to_evaluate_indices)
            # EXEC-2B: next bar's timestamp from actual data; None on final bar
            _next_bar_ts: datetime | None = (
                indexed_new_bars[_bar_pos + 1][1].timestamp  # type: ignore[union-attr]
                if _bar_pos + 1 < len(indexed_new_bars)
                else None
            )

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
                is_warmup_bar=not is_signal_eligible,
                processed_at=now_utc,
            )
            was_new_bar = self._bar_store.append_bar(ft_bar)
            if was_new_bar:
                bars_processed += 1
                last_new_bar_ts = bar.timestamp  # type: ignore[union-attr]
                # Only count signal-eligible bars that are new for evaluation
                if is_signal_eligible and is_new_for_evaluation:
                    signal_eligible_count += 1

            if not is_signal_eligible or not is_new_for_evaluation:
                continue

            bar_result = new_bar_result_map.get(bar_index)
            if bar_result is None:
                continue

            if getattr(bar_result, "entry_triggered", None) is True:
                rule_id = _get_triggered_rule_id(bar_result, "entry")
                was_new_sig = self._signal_store.append_signal(ForwardTestSignal(
                    signal_id=str(uuid.uuid4()),
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
                    actionable_from_bar_timestamp=_next_bar_ts,
                ))
                _emit_signal_event(session_id, "entry_long", bar.timestamp, rule_id, was_new_sig)  # type: ignore[union-attr]
                if was_new_sig:
                    signals_generated += 1
                else:
                    signals_suppressed += 1

            if getattr(bar_result, "exit_triggered", None) is True:
                rule_id = _get_triggered_rule_id(bar_result, "exit")
                was_new_sig = self._signal_store.append_signal(ForwardTestSignal(
                    signal_id=str(uuid.uuid4()),
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
                    actionable_from_bar_timestamp=_next_bar_ts,
                ))
                _emit_signal_event(session_id, "exit_long", bar.timestamp, rule_id, was_new_sig)  # type: ignore[union-attr]
                if was_new_sig:
                    signals_generated += 1
                else:
                    signals_suppressed += 1

        # Advance cursor only to bars actually processed this cycle
        new_cursor = last_new_bar_ts or session.last_processed_bar_timestamp

        # Advance watermark to the highest bar_index processed this cycle.
        # Uses the locally-clamped `watermark` (not session.last_computed_bar_index)
        # so an inconsistency reset propagates correctly into the new value.
        # indexed_new_bars is guaranteed non-empty here (empty case returned above).
        max_new_index = max(bi for bi, _ in indexed_new_bars)
        new_watermark: int | None = (
            max_new_index
            if watermark is None
            else max(watermark, max_new_index)
        )

        # Update session counters + cursor + watermark atomically in one locked write
        updated_session = session.model_copy(update={
            "updated_at": now_utc,
            "last_processed_bar_timestamp": new_cursor,
            "bars_evaluated": session.bars_evaluated + bars_processed,
            "signal_eligible_bars_processed": (
                session.signal_eligible_bars_processed + signal_eligible_count
            ),
            "signals_recorded": session.signals_recorded + signals_generated,
            "last_computed_bar_index": new_watermark,
        })
        self._repository.update(updated_session, owner_id=owner_id)

        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.FT_POLL_COMPLETED,
            details={
                "session_id": session_id,
                "bars_fetched": len(new_bars),
                "bars_processed": bars_processed,
                "signal_eligible_bars_processed": signal_eligible_count,
                "signals_generated": signals_generated,
                "signals_suppressed": signals_suppressed,
                "gap_detected": gap_detected,
                "provider_failure": provider_failure,
                "cursor": new_cursor.isoformat() if new_cursor else None,
                "last_computed_bar_index": new_watermark,
            },
        ))

        return CycleResult(
            session_id=session_id,
            status=session.status.value,
            bars_fetched=len(new_bars),
            bars_processed=bars_processed,
            warmup_bars_processed=0,
            signal_eligible_bars_processed=signal_eligible_count,
            signals_generated=signals_generated,
            signals_suppressed=signals_suppressed,
            last_processed_bar_timestamp=new_cursor,
            gap_detected=gap_detected,
            provider_failure=provider_failure,
            activated=False,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _prepare_strategy(
        session: ForwardTestSession,
    ) -> tuple[StrategyDraft | None, object, str | None]:
        """
        Deserialize strategy snapshot and compile semantics.

        Returns:
            (draft, plan, error_message) — error_message is None on success.
        """
        try:
            draft = StrategyDraft.model_validate_json(
                session.strategy_snapshot.strategy_json
            )
        except Exception as exc:
            logger.error(
                "ForwardTestService: strategy deserialization failed: %s", exc
            )
            return None, None, "strategy snapshot deserialization failed"

        if draft.semantics is None:
            return draft, None, "strategy snapshot has no semantics; cannot evaluate"

        compilation = compile_semantics(draft.semantics, draft_id=session.draft_id)
        if not compilation.compiled or compilation.evaluation_plan is None:
            errors = "; ".join(compilation.errors) if compilation.errors else "unknown"
            return draft, None, f"strategy compilation failed: {errors}"

        return draft, compilation.evaluation_plan, None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

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


def _emit_signal_event(
    session_id: str,
    signal_direction: str,
    bar_timestamp: datetime,
    rule_id: str,
    was_new: bool,
) -> None:
    """Emit FT_SIGNAL_GENERATED or FT_SIGNAL_SUPPRESSED audit event."""
    event_kind = (
        AuditEventKind.FT_SIGNAL_GENERATED if was_new
        else AuditEventKind.FT_SIGNAL_SUPPRESSED
    )
    details: dict = {
        "session_id": session_id,
        "signal_direction": signal_direction,
        "bar_timestamp": bar_timestamp.isoformat(),
        "rule_id": rule_id,
    }
    if not was_new:
        details["reason"] = "duplicate"
    emit_audit_event(AuditEvent(event_kind=event_kind, details=details))
