"""
Paper Trading domain models — Phase 4E.1.

All models are frozen (immutable after creation).  State transitions on
PaperTradingSession and PaperAccount produce new instances via
model_copy(update={...}).

Provenance invariants (must never be violated):
  - No file_path in any model
  - No encrypted_secret, decrypted credentials, or raw API keys
  - No broker account identifiers
  - user_id is set at creation from JWT — never accepted from client payload
  - strategy_snapshot is sealed at session activation — immutable thereafter
  - simulation_assumptions are declared at creation and immutable after
    session activation

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

from backend.paper_trading.exceptions import PaperTradingInvalidTransitionError


# ---------------------------------------------------------------------------
# Session status state machine
# ---------------------------------------------------------------------------

class PaperTradingSessionStatus(str, Enum):
    """
    Lifecycle states for a PaperTradingSession.

    Allowed transitions:
        pending    → running    (user activates the session)
        running    → paused     (user pauses, or drawdown stop triggered)
        running    → completed  (user stops gracefully)
        running    → failed     (unrecoverable error)
        running    → terminated (administrative action)
        paused     → running    (user resumes)
        paused     → completed  (user stops from paused state)
        paused     → terminated (administrative action)

    Terminal states (no further transitions): completed, failed, terminated.

    Correspondence with PAPER_TRADING_ARCHITECTURE.md §5:
        pending    = "pending"   (session and account configured; not yet activated)
        running    = "running"   (actively polling; evaluating strategy; routing intents)
        paused     = "paused"    (polling suspended; open positions frozen)
        completed  = "completed" (graceful stop; all open positions force-closed)
        failed     = "failed"    (unrecoverable error; session record preserved)
        terminated = "terminated" (forcibly stopped; positions closed at last known price)
    """
    PENDING    = "pending"
    RUNNING    = "running"
    PAUSED     = "paused"
    COMPLETED  = "completed"
    FAILED     = "failed"
    TERMINATED = "terminated"


_PT_TERMINAL_STATUSES: frozenset[PaperTradingSessionStatus] = frozenset({
    PaperTradingSessionStatus.COMPLETED,
    PaperTradingSessionStatus.FAILED,
    PaperTradingSessionStatus.TERMINATED,
})

_PT_ALLOWED_TRANSITIONS: dict[
    PaperTradingSessionStatus, frozenset[PaperTradingSessionStatus]
] = {
    PaperTradingSessionStatus.PENDING: frozenset({
        PaperTradingSessionStatus.RUNNING,
    }),
    PaperTradingSessionStatus.RUNNING: frozenset({
        PaperTradingSessionStatus.PAUSED,
        PaperTradingSessionStatus.COMPLETED,
        PaperTradingSessionStatus.FAILED,
        PaperTradingSessionStatus.TERMINATED,
    }),
    PaperTradingSessionStatus.PAUSED: frozenset({
        PaperTradingSessionStatus.RUNNING,
        PaperTradingSessionStatus.COMPLETED,
        PaperTradingSessionStatus.TERMINATED,
    }),
    PaperTradingSessionStatus.COMPLETED: frozenset(),
    PaperTradingSessionStatus.FAILED:    frozenset(),
    PaperTradingSessionStatus.TERMINATED: frozenset(),
}


def validate_pt_session_transition(
    current: PaperTradingSessionStatus,
    target: PaperTradingSessionStatus,
) -> None:
    """
    Assert that the transition current → target is allowed.

    Raises PaperTradingInvalidTransitionError for disallowed transitions,
    including attempts to leave terminal states.
    """
    allowed = _PT_ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        allowed_str = sorted(s.value for s in allowed) or [
            "(terminal — no transitions allowed)"
        ]
        raise PaperTradingInvalidTransitionError(
            f"Session transition '{current.value}' → '{target.value}' is not permitted. "
            f"Allowed from '{current.value}': {allowed_str}"
        )


def is_pt_terminal_status(status: PaperTradingSessionStatus) -> bool:
    """Return True if status is a terminal state (no further transitions)."""
    return status in _PT_TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# SimulationAssumptions — declared execution parameters
# ---------------------------------------------------------------------------

class FillTimingModel(str, Enum):
    """
    When a fill is applied relative to the signal bar.

    SIGNAL_BAR_CLOSE: fill at close of the bar on which the signal fired.
        Optimistic; assumes instantaneous execution at bar close.

    NEXT_BAR_OPEN: fill at open of the bar following the signal bar.
        Conservative; the recommended default.
    """
    SIGNAL_BAR_CLOSE = "signal_bar_close"
    NEXT_BAR_OPEN    = "next_bar_open"


class FeeMode(str, Enum):
    """Fee schedule applied per fill."""
    NONE       = "none"
    FLAT       = "flat"        # fixed currency amount per trade
    PERCENTAGE = "percentage"  # fraction of gross fill value


class SlippageMode(str, Enum):
    """Slippage applied to the gross fill price."""
    NONE       = "none"
    FIXED      = "fixed"       # fixed price units (adverse direction)
    PERCENTAGE = "percentage"  # fraction of gross fill price


class PositionSizeMode(str, Enum):
    """How the fill quantity is computed from the ExecutionIntent."""
    EQUITY_FRACTION = "equity_fraction"  # fraction of current equity
    FIXED_QUANTITY  = "fixed_quantity"   # fixed number of units
    FIXED_CASH      = "fixed_cash"       # fixed cash amount → quantity = floor(cash/price)


class SimulationAssumptions(BaseModel):
    """
    Immutable, declared execution mechanics for a PaperTradingSession.

    Must be declared completely before session activation.
    Must not be modified after session transitions to running.

    Changing execution assumptions mid-session would make the session's
    execution record incoherent — fills before and after the change would
    have been computed under different assumptions.

    No broker fields.  No file_path.  No credential secrets.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    # ── Capital ───────────────────────────────────────────────────────────
    starting_cash: float        # initial cash balance of the paper account
    currency: str = "USD"       # declared currency denomination; immutable

    # ── Fill timing ───────────────────────────────────────────────────────
    fill_timing_model: FillTimingModel = FillTimingModel.NEXT_BAR_OPEN

    # ── Fees ──────────────────────────────────────────────────────────────
    fee_mode: FeeMode   = FeeMode.NONE
    fee_value: float    = 0.0   # currency units (flat) or decimal fraction (percentage)

    # ── Slippage ──────────────────────────────────────────────────────────
    slippage_mode: SlippageMode = SlippageMode.NONE
    slippage_value: float       = 0.0  # price units (fixed) or decimal fraction (percentage)

    # ── Position sizing ───────────────────────────────────────────────────
    position_size_mode: PositionSizeMode = PositionSizeMode.FIXED_QUANTITY
    position_size_value: float           = 1.0  # units, fraction, or cash depending on mode

    # ── Risk constraints ──────────────────────────────────────────────────
    max_concurrent_positions: int       = 1     # maximum simultaneously open positions
    max_drawdown_stop_pct: float | None = None  # session pauses if drawdown exceeds this

    # ── Short selling ─────────────────────────────────────────────────────
    # Long-only by default.  Short selling is disabled unless explicitly enabled
    # by a future asset-specific policy layer (Phase 4F+).
    allow_short_selling: bool = False

    # ── Validators ────────────────────────────────────────────────────────

    @field_validator("starting_cash")
    @classmethod
    def _starting_cash_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("starting_cash must be > 0")
        return v

    @field_validator("fee_value", "slippage_value")
    @classmethod
    def _non_negative_cost(cls, v: float) -> float:
        if v < 0:
            raise ValueError("fee_value and slippage_value must be >= 0")
        return v

    @field_validator("position_size_value")
    @classmethod
    def _position_size_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("position_size_value must be > 0")
        return v

    @field_validator("max_concurrent_positions")
    @classmethod
    def _max_positions_at_least_one(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_concurrent_positions must be >= 1")
        return v

    @field_validator("max_drawdown_stop_pct")
    @classmethod
    def _drawdown_range(cls, v: float | None) -> float | None:
        if v is None:
            return v
        if not (0 < v <= 100):
            raise ValueError("max_drawdown_stop_pct must be in range (0, 100]")
        return v

    @field_validator("currency")
    @classmethod
    def _currency_safe(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("currency must not be empty or whitespace")
        # Reject characters that could appear in filesystem paths or injection vectors.
        for char in ("/", "\\", "\x00", "."):
            if char in stripped:
                raise ValueError(
                    f"currency contains forbidden character '{char}'"
                )
        return stripped.upper()


# ---------------------------------------------------------------------------
# PaperStrategySnapshot — sealed strategy copy at session creation
# ---------------------------------------------------------------------------

class PaperStrategySnapshot(BaseModel):
    """
    Immutable snapshot of a strategy definition captured at session creation.

    Sealed at creation time.  Changes to the underlying StrategyDraft after
    session creation do not affect the snapshot.

    strategy_json holds the complete StrategyDraft.model_dump_json() output,
    enabling Phase 4E.3 to deserialize and execute the exact strategy.

    Defined independently from ForwardTestSession's StrategySnapshot to
    maintain clean module boundaries between forward_testing and paper_trading.

    No file_path.  No credential fields.  No broker fields.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    draft_id: str
    display_name: str
    description: str | None = None
    lifecycle_status: str               # StrategyLifecycleStatus.value at capture time
    semantics_hash: str | None = None
    toolset_hash: str | None = None
    snapshot_hash: str                  # SHA-256 of strategy_json
    captured_at: datetime
    strategy_json: str                  # full StrategyDraft.model_dump_json() output

    @field_validator("captured_at")
    @classmethod
    def _must_be_utc_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("captured_at must be UTC-aware; naive datetime rejected")
        return v.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# PaperTradingSession
# ---------------------------------------------------------------------------

class PaperTradingSession(BaseModel):
    """
    Durable, ownership-scoped container for a single paper trading activation.

    Ownership rules:
      - user_id is always set from JWT at creation; never accepted from client payload
      - Wrong-owner repository access raises PaperTradingSessionNotFoundError
        (indistinguishable from not-found; information hiding)

    Immutable core fields: session_id, user_id, draft_id, forward_test_session_id,
        strategy_snapshot_hash, strategy_snapshot, lifecycle_status_at_activation,
        account_id, simulation_assumptions, source_mode, provider_name, catalog_id,
        credential_id, exchange, asset_class, symbol, timeframe, created_at.

    Mutable (via model_copy(update={...})): status, updated_at,
        activation_timestamp, last_processed_bar_timestamp, failure_reason.

    No fill, position, equity, P&L, or order fields — those are owned by the
    execution layer (Phase 4E.2+).
    No file_path.  No credential secrets.  No broker account identifiers.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    # ── Identity ──────────────────────────────────────────────────────────
    session_id: str                     # UUID4, server-generated
    user_id: str                        # UUID, from JWT
    draft_id: str                       # UUID, strategy under test
    forward_test_session_id: str | None = None  # optional: FT session this extends

    # ── Strategy provenance (sealed at creation) ──────────────────────────
    strategy_snapshot_hash: str         # SHA-256; denormalized from snapshot for fast access
    strategy_snapshot: PaperStrategySnapshot
    lifecycle_status_at_activation: str  # StrategyLifecycleStatus.value at session creation

    # ── Account binding (1:1) ─────────────────────────────────────────────
    account_id: str                     # UUID of the associated PaperAccount

    # ── Simulation assumptions (immutable after activation) ───────────────
    simulation_assumptions: SimulationAssumptions

    # ── Data source ───────────────────────────────────────────────────────
    source_mode: Literal["provider", "catalog"]
    provider_name: str | None = None    # required when source_mode="provider"
    catalog_id: str | None = None       # required when source_mode="catalog"
    credential_id: str | None = None    # vault credential_id; never the raw key

    # ── Instrument ────────────────────────────────────────────────────────
    symbol: str
    timeframe: str
    exchange: str = "NASDAQ"
    asset_class: str = "equity"

    # ── Session lifecycle ─────────────────────────────────────────────────
    status: PaperTradingSessionStatus = PaperTradingSessionStatus.PENDING

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at: datetime
    updated_at: datetime
    activation_timestamp: datetime | None = None
    last_processed_bar_timestamp: datetime | None = None

    # ── Error state ───────────────────────────────────────────────────────
    failure_reason: str | None = None   # sanitized error category; not a raw exception

    # ── Validators ────────────────────────────────────────────────────────

    @field_validator("session_id", "user_id", "draft_id", "account_id")
    @classmethod
    def _must_be_valid_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(
                f"value must be a valid UUID (8-4-4-4-12 hex); got '{v}'"
            ) from exc
        return v

    @field_validator("forward_test_session_id", "credential_id")
    @classmethod
    def _optional_uuid(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(
                f"value must be a valid UUID (8-4-4-4-12 hex) or None; got '{v}'"
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

    @field_validator("lifecycle_status_at_activation")
    @classmethod
    def _lifecycle_status_valid(cls, v: str) -> str:
        # Import here to avoid a module-level dependency; lifecycle is a pure enum.
        from backend.strategy_registry.lifecycle import StrategyLifecycleStatus
        valid = {s.value for s in StrategyLifecycleStatus}
        if v not in valid:
            raise ValueError(
                f"lifecycle_status_at_activation '{v}' is not a valid "
                f"StrategyLifecycleStatus value. Valid: {sorted(valid)}"
            )
        return v

    @model_validator(mode="after")
    def _validate_source_consistency(self) -> "PaperTradingSession":
        if self.source_mode == "provider" and not self.provider_name:
            raise ValueError(
                "provider_name is required when source_mode is 'provider'"
            )
        if self.source_mode == "catalog" and not self.catalog_id:
            raise ValueError(
                "catalog_id is required when source_mode is 'catalog'"
            )
        return self

    @model_validator(mode="after")
    def _validate_snapshot_hash_consistency(self) -> "PaperTradingSession":
        if self.strategy_snapshot_hash != self.strategy_snapshot.snapshot_hash:
            raise ValueError(
                "strategy_snapshot_hash must match strategy_snapshot.snapshot_hash"
            )
        return self


# ---------------------------------------------------------------------------
# PaperAccount
# ---------------------------------------------------------------------------

class PaperAccountStatus(str, Enum):
    """
    Lifecycle status of a PaperAccount.

    ACTIVE: account is live; session is pending, running, or paused.
    CLOSED: account is closed; session has reached completed, failed, or terminated.
    """
    ACTIVE = "active"
    CLOSED = "closed"


class PaperAccount(BaseModel):
    """
    Simulated financial account associated with a PaperTradingSession.

    1:1 relationship with PaperTradingSession (enforced by PaperAccountStore).

    Ownership rules:
      - Owned by exactly one user; no shared accounts
      - owner_user_id is derived from the owning session's user_id at creation
      - Never accepted from client-supplied payload

    Account rules (from PAPER_TRADING_ARCHITECTURE.md §6):
      - starting_cash is immutable after account creation
      - cash_balance, equity, available_cash updated only via service layer (Phase 4E.3+)
      - No real broker account reference; no deposits/withdrawals
      - Every state change must be traceable to a specific fill or bar evaluation event

    Mutable fields (via model_copy(update={...})): cash_balance, equity,
        available_cash, peak_equity, current_drawdown_pct, total_realized_pnl,
        total_fees_paid, total_slippage_applied, status, updated_at, closed_at.

    No file_path.  No encrypted_secret.  No broker account identifiers.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    # ── Identity ──────────────────────────────────────────────────────────
    account_id: str     # UUID4, server-generated
    session_id: str     # UUID of the owning PaperTradingSession (1:1 binding)
    user_id: str        # UUID of the owner (from session's user_id)

    # ── Capital configuration (immutable after creation) ──────────────────
    currency: str       # declared currency denomination (e.g. "USD")
    starting_cash: float  # initial cash balance; immutable

    # ── Running state (updated by service layer after fills and bar marks) ─
    cash_balance: float   # current available cash (after deducting open position cost)
    equity: float         # cash_balance + current marked value of all open positions
    available_cash: float # cash not committed to pending orders or open positions

    # ── Performance tracking ──────────────────────────────────────────────
    peak_equity: float               # highest equity achieved in this session
    current_drawdown_pct: float = 0.0  # (peak_equity − equity) / peak_equity × 100
    total_realized_pnl: float = 0.0
    total_fees_paid: float    = 0.0
    total_slippage_applied: float = 0.0

    # ── Lifecycle ─────────────────────────────────────────────────────────
    status: PaperAccountStatus = PaperAccountStatus.ACTIVE

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None  # set when status transitions to CLOSED

    # ── Validators ────────────────────────────────────────────────────────

    @field_validator("account_id", "session_id", "user_id")
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

    @field_validator("closed_at")
    @classmethod
    def _closed_at_utc_aware(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return v
        if v.tzinfo is None:
            raise ValueError("closed_at must be UTC-aware; naive datetime rejected")
        return v.astimezone(timezone.utc)

    @field_validator("starting_cash")
    @classmethod
    def _starting_cash_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("starting_cash must be > 0")
        return v

    @field_validator("cash_balance", "equity", "available_cash", "peak_equity")
    @classmethod
    def _balances_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("cash_balance, equity, available_cash, and peak_equity must be >= 0")
        return v

    @field_validator("current_drawdown_pct")
    @classmethod
    def _drawdown_range(cls, v: float) -> float:
        if not (0 <= v <= 100):
            raise ValueError("current_drawdown_pct must be in range [0, 100]")
        return v

    @field_validator("total_fees_paid", "total_slippage_applied")
    @classmethod
    def _costs_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("total_fees_paid and total_slippage_applied must be >= 0")
        return v

    @field_validator("currency")
    @classmethod
    def _currency_safe(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("currency must not be empty or whitespace")
        for char in ("/", "\\", "\x00", "."):
            if char in stripped:
                raise ValueError(f"currency contains forbidden character '{char}'")
        return stripped.upper()


# ---------------------------------------------------------------------------
# AccountStateSnapshot — equity curve data point
# ---------------------------------------------------------------------------

class AccountStateSnapshot(BaseModel):
    """
    Immutable per-bar snapshot of paper account state.

    Produced after every bar is processed (even bars with no fills).
    Forms the equity curve for the paper trading session.

    One snapshot per processed bar is the minimum required cadence.
    The equity curve is a primary result artifact for the session,
    analogous to the equity curve in backtesting results.

    Append-only.  Never modified after creation.
    No file_path.  No credential secrets.  No broker fields.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    # ── Identity ──────────────────────────────────────────────────────────
    snapshot_id: str    # UUID4, server-generated
    session_id: str     # UUID of the owning PaperTradingSession
    account_id: str     # UUID of the owning PaperAccount
    user_id: str        # UUID of the owner

    # ── Timing ────────────────────────────────────────────────────────────
    bar_timestamp: datetime      # market-data timestamp of the bar that triggered this snapshot
    snapshot_timestamp: datetime # wall-clock time when the snapshot was recorded

    # ── Account state at this bar ─────────────────────────────────────────
    cash_balance: float
    equity: float
    available_cash: float
    peak_equity: float
    current_drawdown_pct: float

    # ── Position summary ──────────────────────────────────────────────────
    open_position_count: int

    # ── P&L summary ───────────────────────────────────────────────────────
    realized_pnl: float
    unrealized_pnl: float

    # ── Record timestamp ──────────────────────────────────────────────────
    created_at: datetime

    # ── Validators ────────────────────────────────────────────────────────

    @field_validator("snapshot_id", "session_id", "account_id", "user_id")
    @classmethod
    def _must_be_valid_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(
                f"value must be a valid UUID (8-4-4-4-12 hex); got '{v}'"
            ) from exc
        return v

    @field_validator("bar_timestamp", "snapshot_timestamp", "created_at")
    @classmethod
    def _must_be_utc_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("datetime fields must be UTC-aware; naive datetime rejected")
        return v.astimezone(timezone.utc)

    @field_validator("open_position_count")
    @classmethod
    def _count_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("open_position_count must be >= 0")
        return v

    @field_validator("current_drawdown_pct")
    @classmethod
    def _drawdown_range(cls, v: float) -> float:
        if not (0 <= v <= 100):
            raise ValueError("current_drawdown_pct must be in range [0, 100]")
        return v
