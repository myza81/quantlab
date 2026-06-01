"""
Paper Trading API schemas — Phase 4E.4.

Request/response models for:
    POST   /paper-trading/sessions
    GET    /paper-trading/sessions
    GET    /paper-trading/sessions/{session_id}
    POST   /paper-trading/sessions/{session_id}/run-cycle
    POST   /paper-trading/sessions/{session_id}/pause
    POST   /paper-trading/sessions/{session_id}/resume
    POST   /paper-trading/sessions/{session_id}/terminate
    GET    /paper-trading/sessions/{session_id}/signals
    GET    /paper-trading/sessions/{session_id}/orders
    GET    /paper-trading/sessions/{session_id}/fills
    GET    /paper-trading/sessions/{session_id}/positions
    GET    /paper-trading/sessions/{session_id}/account
    GET    /paper-trading/sessions/{session_id}/equity-curve
    GET    /paper-trading/sessions/{session_id}/bars

Security invariants (enforced at this layer):
    - No file_path in any response
    - No credential secrets (credential_id metadata is safe; raw key is never surfaced)
    - No strategy_json in list or summary responses
    - user_id never in list responses (bulk PII reduction)
    - No broker account identifiers
    - rejection_reason uses structured codes (not raw exception text)
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Sub-schemas: simulation assumptions (request + response)
# ---------------------------------------------------------------------------

class SimulationAssumptionsRequest(BaseModel):
    """
    Execution mechanics declared at session creation.

    Mirrors backend.paper_trading.models.SimulationAssumptions.
    All fields are optional with defaults so the request body can be minimal.
    """
    model_config = ConfigDict(frozen=True)

    starting_cash: float = 10_000.0
    currency: str = "USD"
    fill_timing_model: str = "next_bar_open"
    fee_mode: str = "none"
    fee_value: float = 0.0
    slippage_mode: str = "none"
    slippage_value: float = 0.0
    position_size_mode: str = "fixed_quantity"
    position_size_value: float = 1.0
    max_concurrent_positions: int = 1
    max_drawdown_stop_pct: float | None = None
    allow_short_selling: bool = False


class SimulationAssumptionsResponse(BaseModel):
    """Safe SimulationAssumptions representation for API responses."""
    model_config = ConfigDict(frozen=True)

    starting_cash: float
    currency: str
    fill_timing_model: str
    fee_mode: str
    fee_value: float
    slippage_mode: str
    slippage_value: float
    position_size_mode: str
    position_size_value: float
    max_concurrent_positions: int
    max_drawdown_stop_pct: float | None
    allow_short_selling: bool


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class CreatePaperTradingSessionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    draft_id: str
    symbol: str
    timeframe: str
    source_mode: Literal["provider", "catalog"]
    provider_name: str | None = None        # required when source_mode="provider"
    catalog_id: str | None = None           # required when source_mode="catalog"
    credential_id: str | None = None        # vault credential_id; never the raw key
    exchange: str = "NASDAQ"
    asset_class: str = "equity"
    forward_test_session_id: str | None = None  # optional: FT session this extends
    simulation_assumptions: SimulationAssumptionsRequest = SimulationAssumptionsRequest()


# ---------------------------------------------------------------------------
# Strategy snapshot (no strategy_json — never expose in responses)
# ---------------------------------------------------------------------------

class PaperStrategySnapshotResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    draft_id: str
    display_name: str
    lifecycle_status: str
    snapshot_hash: str
    # description omitted; strategy_json NEVER returned


# ---------------------------------------------------------------------------
# Session summary — lightweight list item
# ---------------------------------------------------------------------------

class PaperTradingSessionSummaryResponse(BaseModel):
    """
    Lightweight session record for list views.

    No strategy_json.  No user_id.  No file_path.  No secrets.
    No broker account identifiers.
    """
    model_config = ConfigDict(frozen=True)

    session_id: str
    status: str
    symbol: str
    timeframe: str
    source_mode: str
    provider_name: str | None
    catalog_id: str | None
    exchange: str
    asset_class: str
    created_at: str
    updated_at: str
    last_processed_bar_timestamp: str | None
    strategy_snapshot: PaperStrategySnapshotResponse


# ---------------------------------------------------------------------------
# Session detail — full metadata, still no strategy_json or user_id
# ---------------------------------------------------------------------------

class PaperTradingSessionDetailResponse(PaperTradingSessionSummaryResponse):
    """
    Full session detail for GET /paper-trading/sessions/{session_id}.

    Extends summary with draft provenance, account binding, and
    simulation assumptions.  Never contains strategy_json or user_id.
    """
    draft_id: str
    account_id: str
    forward_test_session_id: str | None
    lifecycle_status_at_activation: str
    activation_timestamp: str | None
    failure_reason: str | None
    simulation_assumptions: SimulationAssumptionsResponse


# ---------------------------------------------------------------------------
# Cycle result — returned by run-cycle
# ---------------------------------------------------------------------------

class PaperCycleResultResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

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
    last_processed_bar_timestamp: str | None
    gap_detected: bool
    provider_failure: bool
    activated: bool
    drawdown_stop_triggered: bool
    message: str | None


# ---------------------------------------------------------------------------
# Order response — safe subset, structured rejection_reason
# ---------------------------------------------------------------------------

class PaperOrderResponse(BaseModel):
    """
    Safe order record.

    rejection_reason is a structured code (not raw exception text).
    No broker-native IDs.  No file_path.  No user_id.
    """
    model_config = ConfigDict(frozen=True)

    order_id: str
    session_id: str
    symbol: str
    direction: str
    quantity: float
    status: str
    fill_timing_model: str
    signal_id: str | None
    signal_bar_timestamp: str
    target_fill_bar_timestamp: str | None
    created_at: str
    updated_at: str
    filled_at: str | None
    cancellation_reason: str | None
    rejection_reason: str | None


# ---------------------------------------------------------------------------
# Fill response — self-documenting, no secrets
# ---------------------------------------------------------------------------

class PaperFillResponse(BaseModel):
    """
    Safe fill record.

    All price computation fields included so reviewers can verify the fill.
    No broker-native fill IDs.  No file_path.  No user_id.
    """
    model_config = ConfigDict(frozen=True)

    fill_id: str
    order_id: str
    session_id: str
    symbol: str
    direction: str
    quantity: float
    gross_price: float
    slippage: float
    fill_price: float
    gross_value: float
    fee: float
    net_value: float
    fill_bar_timestamp: str
    created_at: str
    execution_reason: str | None


# ---------------------------------------------------------------------------
# Position response — current mark-to-market state
# ---------------------------------------------------------------------------

class PaperPositionResponse(BaseModel):
    """
    Safe position record.

    No broker-native IDs.  No file_path.  No user_id.
    """
    model_config = ConfigDict(frozen=True)

    position_id: str
    session_id: str
    symbol: str
    quantity: float
    average_entry_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    is_open: bool
    opened_at: str
    last_updated_at: str
    closed_at: str | None
    opening_signal_id: str | None
    closing_signal_id: str | None


# ---------------------------------------------------------------------------
# Account response — current financial state
# ---------------------------------------------------------------------------

class PaperAccountResponse(BaseModel):
    """
    Current paper account state.

    No file_path.  No encrypted_secret.  No broker account identifiers.
    """
    model_config = ConfigDict(frozen=True)

    account_id: str
    session_id: str
    currency: str
    starting_cash: float
    cash_balance: float
    equity: float
    available_cash: float
    peak_equity: float
    current_drawdown_pct: float
    total_realized_pnl: float
    total_fees_paid: float
    total_slippage_applied: float
    status: str
    created_at: str
    updated_at: str
    closed_at: str | None


# ---------------------------------------------------------------------------
# Equity curve — per-bar account snapshots
# ---------------------------------------------------------------------------

class AccountStateSnapshotResponse(BaseModel):
    """
    Single equity curve data point (one per signal-eligible bar).

    No user_id.  No file_path.  No secrets.
    """
    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    session_id: str
    bar_timestamp: str
    snapshot_timestamp: str
    cash_balance: float
    equity: float
    available_cash: float
    peak_equity: float
    current_drawdown_pct: float
    open_position_count: int
    realized_pnl: float
    unrealized_pnl: float
    created_at: str


# ---------------------------------------------------------------------------
# Bar response — safe OHLCV record for warmup/signal bar history
# ---------------------------------------------------------------------------

class PaperBarResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    bar_index: int
    bar_timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_warmup_bar: bool
    processed_at: str


# ---------------------------------------------------------------------------
# Signal response — re-exported from forward_testing schemas (identical schema)
# ---------------------------------------------------------------------------

class PaperSignalResponse(BaseModel):
    """
    Signal record for paper trading session.

    Paper trading reuses ForwardTestSignal records; this schema mirrors
    ForwardTestSignalResponse to avoid cross-module schema coupling.

    No file_path.  No credential secrets.  No fill or position fields.
    """
    model_config = ConfigDict(frozen=True)

    signal_id: str
    session_id: str
    bar_timestamp: str
    signal_timestamp: str
    signal_direction: str
    rule_id: str
    bar_open: float
    bar_high: float
    bar_low: float
    bar_close: float
    bar_volume: float
    feature_values_at_signal: dict[str, float]
    warmup_satisfied: bool
    strategy_snapshot_hash: str
    symbol: str
    timeframe: str
    provider_name: str | None
    catalog_id: str | None
    created_at: str


# ---------------------------------------------------------------------------
# Promotion request — Phase P7
# ---------------------------------------------------------------------------

class PromoteDraftToPaperTestedRequest(BaseModel):
    """Request body for POST /paper-trading/sessions/{session_id}/promote-draft."""
    model_config = ConfigDict(extra="forbid")
    draft_id: str
    notes: str | None = None
