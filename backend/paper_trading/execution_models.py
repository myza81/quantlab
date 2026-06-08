"""
Paper Trading execution domain models — Phase 4E.2.

PaperOrder, PaperFill, PaperPosition and their supporting enums.

All models are frozen (immutable after creation).  State transitions produce
new instances via model_copy(update={...}).

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.backtesting
    backend.api
    backend.data_providers

Security invariants:
  - No broker-native order IDs, fill IDs, or account identifiers
  - No real financial values; all values are simulation constructs
  - user_id always set from session at creation — never from client payload
  - file_path never present in any field
  - No short-selling: long-only workflow enforced (direction=BUY opens, SELL closes)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from backend.paper_trading.models import FillTimingModel


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class OrderDirection(str, Enum):
    """
    Direction of a paper order.

    BUY  — opens or increases a long position
    SELL — reduces or closes an existing long position

    Short-selling (SELL without an existing long) is disallowed in the current
    long-only workflow.  Enforcement is at the service layer (Phase 4E.3);
    the model accepts both values for representational completeness.
    """
    BUY  = "buy"
    SELL = "sell"


class PaperOrderStatus(str, Enum):
    """
    Lifecycle status of a PaperOrder.

    PENDING_FILL — order created; waiting for fill price (NEXT_BAR_OPEN timing)
    FILLED       — order filled; PaperFill record exists
    CANCELLED    — order cancelled before fill (session pause/terminate, limit expiry)
    REJECTED     — intent validation failed before order could be filled
    """
    PENDING_FILL = "pending_fill"
    FILLED       = "filled"
    CANCELLED    = "cancelled"
    REJECTED     = "rejected"


class ExecutionReason(str, Enum):
    """
    Why a fill was generated.  Stored on PaperFill for audit traceability.

    SIGNAL_ENTRY      — entry signal fired by strategy rule
    SIGNAL_EXIT       — exit signal fired by strategy rule
    SESSION_END_CLOSE — session transitioning to completed; force-close all positions
    DRAWDOWN_STOP_CLOSE — drawdown stop threshold triggered; force-close all positions
    """
    SIGNAL_ENTRY        = "signal_entry"
    SIGNAL_EXIT         = "signal_exit"
    SESSION_END_CLOSE   = "session_end_close"
    DRAWDOWN_STOP_CLOSE = "drawdown_stop_close"


class RejectionReason(str, Enum):
    """
    Structured rejection reason codes stored on rejected PaperOrders.

    Using structured codes (not raw exception messages) ensures audit records
    are machine-readable and never leak internal error details.
    """
    INSUFFICIENT_CASH      = "insufficient_cash"
    MAX_POSITIONS_EXCEEDED = "max_positions_exceeded"
    NO_POSITION_TO_CLOSE   = "no_position_to_close"
    SHORT_SELLING_DISABLED = "short_selling_disabled"
    # Execution-contract alignment (EXEC-2A): match backtest ALREADY_LONG behavior
    DUPLICATE_LONG_ENTRY   = "duplicate_long_entry"   # BUY while position already open
    PENDING_ENTRY_EXISTS   = "pending_entry_exists"    # BUY while pending BUY order unresolved
    # Conflict policy (EXEC-2D): duplicate exit guard
    PENDING_EXIT_EXISTS    = "pending_exit_exists"     # SELL while pending SELL order unresolved


# ---------------------------------------------------------------------------
# PaperOrder
# ---------------------------------------------------------------------------

class PaperOrder(BaseModel):
    """
    Record of a simulated order instruction produced by the PaperBrokerAdapter.

    PaperOrder is an execution-layer artifact.  It is never produced by strategy
    logic; it is produced when an ExecutionIntent is translated into an order.

    For NEXT_BAR_OPEN timing: order is created with status=PENDING_FILL and
    persisted across the poll cycle boundary.  Filled when bar N+1 open arrives.

    For SIGNAL_BAR_CLOSE timing: order is created and immediately transitioned to
    FILLED within the same poll cycle.

    State transitions via model_copy(update={...}):
        PENDING_FILL → FILLED      (build_fill called with bar N+1 open)
        PENDING_FILL → CANCELLED   (session paused/terminated before fill)
        Any          → REJECTED    (intent validation failed; order never pending)

    No broker-native IDs.  No real account references.  No file_path.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    # ── Identity ──────────────────────────────────────────────────────────
    order_id:   str
    session_id: str
    account_id: str
    user_id:    str

    # ── Instrument ────────────────────────────────────────────────────────
    symbol: str

    # ── Order parameters ─────────────────────────────────────────────────
    direction:         OrderDirection
    quantity:          float               # > 0; whole units only
    status:            PaperOrderStatus = PaperOrderStatus.PENDING_FILL
    fill_timing_model: FillTimingModel

    # ── Signal provenance ─────────────────────────────────────────────────
    signal_id: str | None = None           # UUID of triggering ForwardTestSignal

    # ── Timestamps ────────────────────────────────────────────────────────
    signal_bar_timestamp:        datetime        # bar N (signal bar)
    target_fill_bar_timestamp:   datetime | None = None  # bar N+1 for NEXT_BAR_OPEN
    created_at:  datetime
    updated_at:  datetime
    filled_at:   datetime | None = None

    # ── Outcome ───────────────────────────────────────────────────────────
    cancellation_reason: str | None = None  # free text; set on CANCELLED
    rejection_reason:    str | None = None  # structured code; set on REJECTED

    # ── Validators ────────────────────────────────────────────────────────

    @field_validator("order_id", "session_id", "account_id", "user_id")
    @classmethod
    def _must_be_valid_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(
                f"value must be a valid UUID (8-4-4-4-12 hex); got '{v}'"
            ) from exc
        return v

    @field_validator("signal_id")
    @classmethod
    def _optional_uuid(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(
                f"signal_id must be a valid UUID or None; got '{v}'"
            ) from exc
        return v

    @field_validator("quantity")
    @classmethod
    def _quantity_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("quantity must be > 0")
        return v

    @field_validator("symbol")
    @classmethod
    def _symbol_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("symbol must not be empty or whitespace")
        return stripped.upper()

    @field_validator(
        "signal_bar_timestamp", "created_at", "updated_at"
    )
    @classmethod
    def _must_be_utc_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("datetime fields must be UTC-aware; naive datetime rejected")
        return v.astimezone(timezone.utc)

    @field_validator("target_fill_bar_timestamp", "filled_at")
    @classmethod
    def _optional_utc_aware(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return v
        if v.tzinfo is None:
            raise ValueError("datetime fields must be UTC-aware; naive datetime rejected")
        return v.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# PaperFill
# ---------------------------------------------------------------------------

class PaperFill(BaseModel):
    """
    Immutable record that a paper order was executed at a specific price.

    Stores every input used to compute the fill so a reviewer can verify the
    result from the fill record alone without external reference:
      gross_price   — the raw bar price (close or next-bar open)
      slippage      — adverse slippage applied, in price units (>= 0)
      fill_price    — net fill price after slippage
      gross_value   — quantity × gross_price
      fee           — fee in currency units (>= 0)
      net_value     — quantity × fill_price

    Cash impact interpretation (service layer, not enforced here):
      BUY:  cash out = net_value + fee
      SELL: cash in  = net_value − fee

    No broker-native fill IDs.  No real account references.  Immutable.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    # ── Identity ──────────────────────────────────────────────────────────
    fill_id:    str
    order_id:   str
    session_id: str
    account_id: str
    user_id:    str

    # ── Instrument ────────────────────────────────────────────────────────
    symbol:    str
    direction: OrderDirection

    # ── Execution quantities ───────────────────────────────────────────────
    quantity: float   # > 0

    # ── Price computation (fully self-documenting) ─────────────────────────
    gross_price: float  # bar close / next-bar open; before slippage; >= 0
    slippage:    float  # price units applied adversely; >= 0
    fill_price:  float  # net fill price after slippage; >= 0

    # ── Value computation ─────────────────────────────────────────────────
    gross_value: float  # quantity × gross_price; >= 0
    fee:         float  # fee in currency units; >= 0
    net_value:   float  # quantity × fill_price; >= 0 (fee handled separately)

    # ── Timing ────────────────────────────────────────────────────────────
    fill_bar_timestamp: datetime  # bar timestamp that determined the fill price
    created_at:         datetime

    # ── Context ───────────────────────────────────────────────────────────
    execution_reason: ExecutionReason | None = None

    # ── Validators ────────────────────────────────────────────────────────

    @field_validator("fill_id", "order_id", "session_id", "account_id", "user_id")
    @classmethod
    def _must_be_valid_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(
                f"value must be a valid UUID (8-4-4-4-12 hex); got '{v}'"
            ) from exc
        return v

    @field_validator("quantity")
    @classmethod
    def _quantity_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("quantity must be > 0")
        return v

    @field_validator("gross_price", "fill_price")
    @classmethod
    def _price_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("gross_price and fill_price must be >= 0")
        return v

    @field_validator("slippage", "fee")
    @classmethod
    def _cost_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("slippage and fee must be >= 0")
        return v

    @field_validator("gross_value", "net_value")
    @classmethod
    def _value_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("gross_value and net_value must be >= 0")
        return v

    @field_validator("symbol")
    @classmethod
    def _symbol_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("symbol must not be empty or whitespace")
        return stripped.upper()

    @field_validator("fill_bar_timestamp", "created_at")
    @classmethod
    def _must_be_utc_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("datetime fields must be UTC-aware; naive datetime rejected")
        return v.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# PaperPosition
# ---------------------------------------------------------------------------

class PaperPosition(BaseModel):
    """
    Simulated position within a paper trading session.

    Long-only: BUY fills open/scale positions; SELL fills reduce/close them.
    Short positions are not supported.

    The execution environment (PaperBrokerAdapter / PaperTradingService) owns
    all position state.  Strategy logic must never read or write PaperPosition.

    State transitions via model_copy(update={...}):
        OPEN  → OPEN   (scale-in or mark-to-market price update)
        OPEN  → CLOSED (position fully sold; is_open=False, closed_at set)

    Model invariants:
        is_open=True  → quantity > 0, closed_at is None
        is_open=False → closed_at must be set

    No broker-native IDs.  No short positions.  Immutable records.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    # ── Identity ──────────────────────────────────────────────────────────
    position_id: str
    session_id:  str
    account_id:  str
    user_id:     str

    # ── Instrument ────────────────────────────────────────────────────────
    symbol: str

    # ── Holding (>= 0; must be > 0 when is_open=True) ─────────────────────
    quantity: float

    # ── Pricing ───────────────────────────────────────────────────────────
    average_entry_price: float  # >= 0
    current_price:       float  # >= 0; most recent mark price

    # ── Value ─────────────────────────────────────────────────────────────
    market_value:   float  # quantity × current_price; >= 0
    unrealized_pnl: float  # can be negative
    realized_pnl:   float  # cumulative from partial closes; can be negative

    # ── Lifecycle ─────────────────────────────────────────────────────────
    is_open:        bool
    opened_at:      datetime
    last_updated_at: datetime
    closed_at:      datetime | None = None

    # ── Signal provenance (optional) ──────────────────────────────────────
    opening_signal_id: str | None = None  # UUID of entry ForwardTestSignal
    closing_signal_id: str | None = None  # UUID of exit signal; None for forced closes

    # ── Validators ────────────────────────────────────────────────────────

    @field_validator("position_id", "session_id", "account_id", "user_id")
    @classmethod
    def _must_be_valid_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(
                f"value must be a valid UUID (8-4-4-4-12 hex); got '{v}'"
            ) from exc
        return v

    @field_validator("opening_signal_id", "closing_signal_id")
    @classmethod
    def _optional_uuid(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(
                f"value must be a valid UUID or None; got '{v}'"
            ) from exc
        return v

    @field_validator("quantity")
    @classmethod
    def _quantity_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("quantity must be >= 0")
        return v

    @field_validator("average_entry_price", "current_price", "market_value")
    @classmethod
    def _non_negative_price_value(cls, v: float) -> float:
        if v < 0:
            raise ValueError("average_entry_price, current_price, and market_value must be >= 0")
        return v

    @field_validator("symbol")
    @classmethod
    def _symbol_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("symbol must not be empty or whitespace")
        return stripped.upper()

    @field_validator("opened_at", "last_updated_at")
    @classmethod
    def _must_be_utc_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("datetime fields must be UTC-aware; naive datetime rejected")
        return v.astimezone(timezone.utc)

    @field_validator("closed_at")
    @classmethod
    def _optional_utc_aware(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return v
        if v.tzinfo is None:
            raise ValueError("closed_at must be UTC-aware; naive datetime rejected")
        return v.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _validate_open_position_invariants(self) -> "PaperPosition":
        if self.is_open:
            if self.quantity <= 0:
                raise ValueError(
                    "quantity must be > 0 when is_open=True"
                )
            if self.closed_at is not None:
                raise ValueError(
                    "closed_at must be None when is_open=True"
                )
        else:
            if self.closed_at is None:
                raise ValueError(
                    "closed_at must be set when is_open=False"
                )
        return self
