"""
Forward Testing domain models — Phase 4C.1.

All models are frozen (immutable after creation).  State transitions on
ForwardTestSession produce new instances via model_copy(update={...}).

Provenance invariants (must never be violated):
  - No file_path in any model
  - No encrypted_secret, decrypted credentials, or raw API keys
  - No fill, position, equity, or P&L fields
  - user_id is set at creation from JWT — never accepted from client payload
  - strategy_snapshot is sealed at session activation — never mutable

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.backtesting
    backend.api
    backend.data_providers
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from backend.forward_testing.exceptions import ForwardTestInvalidTransitionError


# ---------------------------------------------------------------------------
# Session status state machine
# ---------------------------------------------------------------------------

class ForwardTestSessionStatus(str, Enum):
    """
    Lifecycle states for a ForwardTestSession.

    Allowed transitions:
        pending    → running    (user activates the session)
        running    → paused     (user pauses)
        running    → completed  (user stops gracefully, or natural end)
        running    → failed     (unrecoverable error)
        running    → terminated (administrative action)
        paused     → running    (user resumes)
        paused     → completed  (user stops from paused state)
        paused     → terminated (administrative action)

    Terminal states (no further transitions): completed, failed, terminated.

    Correspondence with FORWARD_TESTING_ARCHITECTURE.md §5:
        pending    = "pending" (session record created; not yet activated)
        running    = "running"
        paused     = "paused"
        completed  = "completed" (graceful user stop OR natural session end)
        failed     = "failed"
        terminated = "terminated"
    """
    PENDING    = "pending"
    RUNNING    = "running"
    PAUSED     = "paused"
    COMPLETED  = "completed"
    FAILED     = "failed"
    TERMINATED = "terminated"


_TERMINAL_STATUSES: frozenset[ForwardTestSessionStatus] = frozenset({
    ForwardTestSessionStatus.COMPLETED,
    ForwardTestSessionStatus.FAILED,
    ForwardTestSessionStatus.TERMINATED,
})

_ALLOWED_TRANSITIONS: dict[ForwardTestSessionStatus, frozenset[ForwardTestSessionStatus]] = {
    ForwardTestSessionStatus.PENDING: frozenset({
        ForwardTestSessionStatus.RUNNING,
    }),
    ForwardTestSessionStatus.RUNNING: frozenset({
        ForwardTestSessionStatus.PAUSED,
        ForwardTestSessionStatus.COMPLETED,
        ForwardTestSessionStatus.FAILED,
        ForwardTestSessionStatus.TERMINATED,
    }),
    ForwardTestSessionStatus.PAUSED: frozenset({
        ForwardTestSessionStatus.RUNNING,
        ForwardTestSessionStatus.COMPLETED,
        ForwardTestSessionStatus.TERMINATED,
    }),
    ForwardTestSessionStatus.COMPLETED: frozenset(),
    ForwardTestSessionStatus.FAILED:    frozenset(),
    ForwardTestSessionStatus.TERMINATED: frozenset(),
}


def validate_session_transition(
    current: ForwardTestSessionStatus,
    target: ForwardTestSessionStatus,
) -> None:
    """
    Assert that the transition current → target is allowed.

    Raises ForwardTestInvalidTransitionError for disallowed transitions,
    including attempts to leave terminal states.
    """
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        allowed_str = sorted(s.value for s in allowed) or ["(terminal — no transitions allowed)"]
        raise ForwardTestInvalidTransitionError(
            f"Session transition '{current.value}' → '{target.value}' is not permitted. "
            f"Allowed from '{current.value}': {allowed_str}"
        )


def is_terminal_status(status: ForwardTestSessionStatus) -> bool:
    """Return True if status is a terminal state (no further transitions)."""
    return status in _TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# StrategySnapshot — sealed copy of strategy at session activation
# ---------------------------------------------------------------------------

class StrategySnapshot(BaseModel):
    """
    Immutable snapshot of a strategy definition captured at session activation.

    Sealed at activation time.  Changes to the underlying StrategyDraft after
    session creation do not affect the snapshot or its signals.

    strategy_json holds the complete StrategyDraft.model_dump_json() output,
    enabling Phase 4C.4 to deserialize and execute the exact strategy.

    No file_path.  No credential fields.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    draft_id: str
    display_name: str
    description: str | None = None
    lifecycle_status: str
    semantics_hash: str | None = None
    toolset_hash: str | None = None
    snapshot_hash: str     # SHA-256 of strategy_json
    captured_at: datetime
    strategy_json: str     # full StrategyDraft.model_dump_json() output

    @field_validator("captured_at")
    @classmethod
    def _must_be_utc_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("captured_at must be UTC-aware; naive datetime rejected")
        return v.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# ForwardTestSession
# ---------------------------------------------------------------------------

class ForwardTestSession(BaseModel):
    """
    Durable, ownership-scoped container for a single forward testing activation.

    Ownership rules:
      - user_id is always set from JWT at creation; never accepted from client payload
      - Wrong-owner repository access raises ForwardTestSessionNotFoundError
        (indistinguishable from not-found; information hiding)

    Immutable core fields: session_id, user_id, draft_id, strategy_snapshot,
        symbol, timeframe, source_mode, provider_name, catalog_id,
        warmup_bars_required, lifecycle_status_at_activation, created_at.

    Mutable (via model_copy(update={...})): status, updated_at,
        activation_timestamp, last_processed_bar_timestamp, bars_evaluated,
        warmup_bars_processed, signal_eligible_bars_processed,
        signals_recorded, failure_reason, error_category.

    No fill, position, equity, P&L, or order fields — ever.
    No file_path.  No credential secrets.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    # ── Identity ──────────────────────────────────────────────────────────
    session_id: str                        # UUID4, server-generated
    user_id: str                           # UUID, from JWT
    draft_id: str                          # UUID, strategy under test

    # ── Strategy provenance (sealed at activation) ────────────────────────
    strategy_snapshot: StrategySnapshot
    lifecycle_status_at_activation: str    # StrategyLifecycleStatus.value at start

    # ── Data source ───────────────────────────────────────────────────────
    source_mode: Literal["provider", "catalog"]
    provider_name: str | None = None       # required when source_mode="provider"
    catalog_id: str | None = None          # required when source_mode="catalog"
    credential_id: str | None = None       # vault credential_id for polygon; never the raw key

    # ── Instrument ────────────────────────────────────────────────────────
    symbol: str
    timeframe: str
    exchange: str = "NASDAQ"               # for DatasetIdentity reconstruction in run-cycle
    asset_class: str = "equity"            # for DatasetIdentity reconstruction in run-cycle

    # ── Evaluation parameters ─────────────────────────────────────────────
    warmup_bars_required: int

    # ── Session lifecycle ─────────────────────────────────────────────────
    status: ForwardTestSessionStatus = ForwardTestSessionStatus.PENDING

    # ── Timestamps ───────────────────────────────────────────────────────
    created_at: datetime
    updated_at: datetime
    activation_timestamp: datetime | None = None
    last_processed_bar_timestamp: datetime | None = None

    # ── Counters (updated on each poll cycle) ─────────────────────────────
    bars_evaluated: int = 0
    warmup_bars_processed: int = 0
    signal_eligible_bars_processed: int = 0
    signals_recorded: int = 0

    # ── Error state ───────────────────────────────────────────────────────
    failure_reason: str | None = None      # sanitized error category, not raw message
    error_category: str | None = None

    # ── Validators ────────────────────────────────────────────────────────

    @field_validator("session_id", "user_id", "draft_id")
    @classmethod
    def _must_be_valid_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(
                f"value must be a valid UUID (8-4-4-4-12 hex); got '{v}'"
            ) from exc
        return v

    @field_validator("created_at", "updated_at")
    @classmethod
    def _must_be_utc_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("datetime fields must be UTC-aware; naive datetime rejected")
        return v.astimezone(timezone.utc)

    @field_validator("activation_timestamp", "last_processed_bar_timestamp")
    @classmethod
    def _optional_utc_aware(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return v
        if v.tzinfo is None:
            raise ValueError("datetime fields must be UTC-aware; naive datetime rejected")
        return v.astimezone(timezone.utc)

    @field_validator("symbol")
    @classmethod
    def _symbol_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("symbol must not be empty or whitespace")
        return v.strip().upper()

    @field_validator("timeframe")
    @classmethod
    def _timeframe_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("timeframe must not be empty or whitespace")
        return v.strip()

    @field_validator("warmup_bars_required")
    @classmethod
    def _warmup_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("warmup_bars_required must be >= 0")
        return v

    @field_validator("bars_evaluated", "warmup_bars_processed",
                     "signal_eligible_bars_processed", "signals_recorded")
    @classmethod
    def _counters_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("counter fields must be >= 0")
        return v

    @model_validator(mode="after")
    def _validate_source_consistency(self) -> "ForwardTestSession":
        if self.source_mode == "provider" and not self.provider_name:
            raise ValueError(
                "provider_name is required when source_mode is 'provider'"
            )
        if self.source_mode == "catalog" and not self.catalog_id:
            raise ValueError(
                "catalog_id is required when source_mode is 'catalog'"
            )
        return self


# ---------------------------------------------------------------------------
# ForwardTestSignal
# ---------------------------------------------------------------------------

class ForwardTestSignal(BaseModel):
    """
    Immutable record of a strategy rule firing during a forward test session.

    The single output of forward testing.  No fill, order, position, equity,
    or P&L fields — those belong to paper trading.

    Provenance: every signal carries strategy_snapshot_hash, session_id,
    bar_timestamp (market time), and signal_timestamp (wall-clock time).
    These two timestamps may differ significantly for daily bars.

    No file_path.  No credential secrets.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    # ── Identity ──────────────────────────────────────────────────────────
    signal_id: str          # UUID4, server-generated
    session_id: str         # UUID of the owning session
    user_id: str            # UUID of the session owner

    # ── Timing (both required — they may differ) ──────────────────────────
    bar_timestamp: datetime     # market-data timestamp of the triggering bar
    signal_timestamp: datetime  # wall-clock time when the evaluator processed this bar

    # ── Signal content ────────────────────────────────────────────────────
    signal_direction: Literal[
        "entry_long", "entry_short", "exit_long", "exit_short", "no_action"
    ]
    rule_id: str            # identifier of the rule (entry/exit) that fired

    # ── Bar snapshot at signal time ───────────────────────────────────────
    bar_open: float
    bar_high: float
    bar_low: float
    bar_close: float
    bar_volume: float

    # ── Feature context ───────────────────────────────────────────────────
    feature_values_at_signal: dict[str, float] = {}  # tool outputs at signal bar

    # ── Integrity flags ───────────────────────────────────────────────────
    warmup_satisfied: bool  # must be True for a valid signal

    # ── Provenance ────────────────────────────────────────────────────────
    strategy_snapshot_hash: str
    symbol: str
    timeframe: str
    provider_name: str | None = None   # None when source_mode="catalog"
    catalog_id: str | None = None      # None when source_mode="provider"

    # ── Record timestamp ──────────────────────────────────────────────────
    created_at: datetime

    # ── Validators ────────────────────────────────────────────────────────

    @field_validator("signal_id", "session_id", "user_id")
    @classmethod
    def _must_be_valid_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(
                f"value must be a valid UUID (8-4-4-4-12 hex); got '{v}'"
            ) from exc
        return v

    @field_validator("bar_timestamp", "signal_timestamp", "created_at")
    @classmethod
    def _must_be_utc_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("datetime fields must be UTC-aware; naive datetime rejected")
        return v.astimezone(timezone.utc)

    @field_validator("symbol")
    @classmethod
    def _symbol_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("symbol must not be empty or whitespace")
        return v.strip().upper()

    @field_validator("timeframe")
    @classmethod
    def _timeframe_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("timeframe must not be empty or whitespace")
        return v.strip()


# ---------------------------------------------------------------------------
# ForwardTestBar
# ---------------------------------------------------------------------------

class ForwardTestBar(BaseModel):
    """
    Record of a single bar processed during a forward test session.

    Bars are stored in the ForwardTestBarStore to support:
      - catch-up evaluation on session resume
      - duplicate-bar detection via (session_id, bar_timestamp)
      - warmup context tracking (is_warmup_bar flag)
      - last-processed-bar cursor

    bar_index: 0-based index within the session's accumulated bar window.
    Warmup bars occupy indices 0 through (warmup_bars_required - 1).
    Signal-eligible bars start at warmup_bars_required.

    No file_path.  No credential secrets.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str          # UUID of the owning session
    bar_index: int           # 0-based index within session window
    bar_timestamp: datetime  # market-data timestamp (completed bar)
    open: float
    high: float
    low: float
    close: float
    volume: float
    source_mode: Literal["provider", "catalog"]
    provider_name: str | None = None
    catalog_id: str | None = None
    is_warmup_bar: bool      # True → warmup context; False → signal-eligible
    processed_at: datetime   # wall-clock time the bar was processed

    @field_validator("session_id")
    @classmethod
    def _must_be_valid_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(
                f"session_id must be a valid UUID; got '{v}'"
            ) from exc
        return v

    @field_validator("bar_timestamp", "processed_at")
    @classmethod
    def _must_be_utc_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("datetime fields must be UTC-aware; naive datetime rejected")
        return v.astimezone(timezone.utc)

    @field_validator("bar_index")
    @classmethod
    def _bar_index_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("bar_index must be >= 0")
        return v
