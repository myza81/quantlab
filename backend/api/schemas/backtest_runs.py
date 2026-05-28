"""
Backtest runs API schemas — Phase 2P.9.

Request/response schemas for:
    POST /backtests/runs
    GET  /backtests/runs/{run_id}/report
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.api.schemas.composition_run import CompositionRunBar
from backend.backtesting.cost_model import CommissionMode, SlippageMode
from backend.backtesting.models import PositionSizeMode


# ---------------------------------------------------------------------------
# Simulation config (user-facing)
# ---------------------------------------------------------------------------

class BacktestRunConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    initial_equity:     float            = 10_000.0
    position_size_mode: PositionSizeMode = PositionSizeMode.EQUITY_FRACTION
    equity_fraction:    float | None     = 0.95
    fixed_quantity:     float            = 1.0
    commission_mode:    CommissionMode   = CommissionMode.NONE
    commission_value:   float            = 0.0
    slippage_mode:      SlippageMode     = SlippageMode.NONE
    slippage_value:     float            = 0.0


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class BacktestRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    draft_id:  str
    symbol:    str
    timeframe: str
    bars:      list[CompositionRunBar]
    config:    BacktestRunConfig = BacktestRunConfig()


# ---------------------------------------------------------------------------
# Equity curve record
# ---------------------------------------------------------------------------

class BacktestEquityRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    bar_index:         int
    timestamp:         str | None
    cash:              float
    position_quantity: float
    market_value:      float
    realized_pnl:      float
    unrealized_pnl:    float
    equity:            float


# ---------------------------------------------------------------------------
# Drawdown curve record
# ---------------------------------------------------------------------------

class BacktestDrawdownRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    bar_index:    int
    timestamp:    str | None
    drawdown_pct: float  # 0.0–100.0


# ---------------------------------------------------------------------------
# Trade ledger record (one closed round-trip; exit fields None for open positions)
# ---------------------------------------------------------------------------

class TradeRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    trade_num:        int
    entry_bar_index:  int
    exit_bar_index:   int | None
    entry_timestamp:  str | None
    exit_timestamp:   str | None
    side:             Literal["long"]
    quantity:         float
    entry_price:      float
    exit_price:       float | None
    entry_commission: float
    exit_commission:  float | None
    entry_slippage:   float
    exit_slippage:    float | None
    gross_pnl:        float | None
    net_pnl:          float | None
    return_pct:       float | None
    holding_bars:     int | None
    equity_after:     float | None

    # Audit / traceability — links back to originating signal events and rules
    entry_rule_id:          str | None = None  # rule_id from entry TradeIntent source
    exit_rule_id:           str | None = None  # rule_id from exit TradeIntent source
    entry_signal_event_id:  str | None = None  # event_id from entry SignalEvent
    exit_signal_event_id:   str | None = None  # event_id from exit SignalEvent


# ---------------------------------------------------------------------------
# Rejection record
# ---------------------------------------------------------------------------

class BacktestRejectionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    rejection_id: str
    intent_id:    str
    bar_index:    int
    timestamp:    str | None
    reason:       str
    detail:       str


# ---------------------------------------------------------------------------
# Metrics summary
# ---------------------------------------------------------------------------

class BacktestMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    initial_equity:   float
    final_equity:     float
    total_net_profit: float
    total_return_pct: float
    gross_profit:     float
    gross_loss:       float
    total_commission: float
    total_slippage:   float
    total_cost:       float
    trade_count:      int           # closed round-trips
    win_count:        int
    loss_count:       int
    breakeven_count:  int
    win_rate:         float | None
    avg_win:          float | None
    avg_loss:         float | None
    profit_factor:    float | None
    best_trade_pnl:   float | None
    worst_trade_pnl:  float | None
    max_drawdown_pct: float
    peak_equity:      float
    trough_equity:    float
    total_bars:       int
    total_rejections: int


# ---------------------------------------------------------------------------
# Run summary
# ---------------------------------------------------------------------------

class BacktestRunSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id:        str
    draft_id:      str
    draft_name:    str
    symbol:        str
    timeframe:     str
    bars_count:    int
    run_timestamp: str
    status:        str
    config:        BacktestRunConfig

    # Reproducibility metadata — enables re-running from stored context
    dataset_start:  str | None = None  # ISO timestamp of first bar
    dataset_end:    str | None = None  # ISO timestamp of last bar
    engine_version: str        = "2P.9"  # backtesting engine version tag
    # Ownership — stored in run JSON for access control; only readable by the owner
    owner_user_id:  str | None = None


# ---------------------------------------------------------------------------
# Full report
# ---------------------------------------------------------------------------

class BacktestReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    run:            BacktestRunSummary
    metrics:        BacktestMetrics
    equity_curve:   list[BacktestEquityRecord]
    drawdown_curve: list[BacktestDrawdownRecord]
    trades:         list[TradeRecord]
    open_position:  TradeRecord | None
    rejections:     list[BacktestRejectionRecord]


# ---------------------------------------------------------------------------
# API response
# ---------------------------------------------------------------------------

class BacktestRunResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    status: str
    report: BacktestReport
