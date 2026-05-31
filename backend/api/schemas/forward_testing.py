"""
Forward Testing API schemas — Phase 4C.5.

Request/response models for:
    POST   /forward-tests
    GET    /forward-tests
    GET    /forward-tests/{session_id}
    POST   /forward-tests/{session_id}/run-cycle
    POST   /forward-tests/{session_id}/pause
    POST   /forward-tests/{session_id}/resume
    POST   /forward-tests/{session_id}/terminate
    GET    /forward-tests/{session_id}/signals
    GET    /forward-tests/{session_id}/bars

Security invariants (enforced at this layer):
    - No file_path in any response
    - No credential secrets (credential_id metadata is safe; raw key is never surfaced)
    - No strategy_json in list or summary responses
    - user_id never in list responses (bulk PII reduction)
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class CreateForwardTestSessionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    draft_id: str
    symbol: str
    timeframe: str
    source_mode: Literal["provider", "catalog"]
    provider_name: str | None = None   # required when source_mode="provider"
    catalog_id: str | None = None      # required when source_mode="catalog"
    credential_id: str | None = None   # vault credential_id for polygon; never raw key
    exchange: str = "NASDAQ"           # needed to build Instrument / DatasetIdentity
    asset_class: str = "equity"        # needed to build Instrument / DatasetIdentity


# ---------------------------------------------------------------------------
# Strategy snapshot summary (no strategy_json — never expose in responses)
# ---------------------------------------------------------------------------

class ForwardTestStrategySnapshotResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    draft_id: str
    display_name: str
    lifecycle_status: str
    snapshot_hash: str
    # description and semantics_hash omitted; captured_at omitted from summary


# ---------------------------------------------------------------------------
# Session summary — lightweight list item
# ---------------------------------------------------------------------------

class ForwardTestSessionSummaryResponse(BaseModel):
    """
    Lightweight session record for list views.

    No strategy_json.  No user_id.  No file_path.  No secrets.
    """
    model_config = ConfigDict(frozen=True)

    session_id: str
    status: str
    symbol: str
    timeframe: str
    source_mode: str
    provider_name: str | None
    catalog_id: str | None
    created_at: str
    updated_at: str
    last_processed_bar_timestamp: str | None
    bars_evaluated: int
    signals_recorded: int
    strategy_snapshot: ForwardTestStrategySnapshotResponse


# ---------------------------------------------------------------------------
# Session detail — full metadata, still no strategy_json or user_id
# ---------------------------------------------------------------------------

class ForwardTestSessionDetailResponse(ForwardTestSessionSummaryResponse):
    """
    Full session detail for GET /forward-tests/{session_id}.

    Extends the summary with lifecycle and evaluation metadata.
    """
    draft_id: str
    lifecycle_status_at_activation: str
    warmup_bars_required: int
    warmup_bars_processed: int
    signal_eligible_bars_processed: int
    activation_timestamp: str | None
    failure_reason: str | None
    error_category: str | None
    exchange: str
    asset_class: str


# ---------------------------------------------------------------------------
# Cycle result — returned by run-cycle
# ---------------------------------------------------------------------------

class ForwardTestCycleResultResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str
    status: str
    bars_fetched: int
    bars_processed: int
    warmup_bars_processed: int
    signal_eligible_bars_processed: int
    signals_generated: int
    signals_suppressed: int
    last_processed_bar_timestamp: str | None
    gap_detected: bool
    provider_failure: bool
    activated: bool
    message: str | None


# ---------------------------------------------------------------------------
# Signal response — immutable record, no secrets
# ---------------------------------------------------------------------------

class ForwardTestSignalResponse(BaseModel):
    """
    Safe signal record for API responses.

    No file_path.  No credential secrets.  No raw provider error messages.
    No fill, position, equity, or P&L fields.
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
# Bar response — optional endpoint, safe subset
# ---------------------------------------------------------------------------

class ForwardTestBarResponse(BaseModel):
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
