"""
Backtest Analytics — Phase 2P.9.

Derives advanced performance metrics and per-bar drawdown from a completed
BacktestSimulationResult. Pure computation from existing result data.

No simulation logic. No market data loading. No indicator computation.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.backtesting.models import BacktestEquityPoint, BacktestSimulationResult


@dataclass(frozen=True)
class DrawdownPoint:
    """Single point on the per-bar drawdown curve."""
    bar_index:    int
    timestamp:    datetime | None
    drawdown_pct: float  # 0.0 = no drawdown; 100.0 = full loss from peak


@dataclass(frozen=True)
class BacktestAnalytics:
    """Advanced analytics derived from a BacktestSimulationResult."""
    total_return_pct: float
    max_drawdown_pct: float
    win_count:        int
    loss_count:       int
    breakeven_count:  int
    win_rate:         float | None   # None if no closed trades
    gross_profit:     float          # sum of positive realized PnL
    gross_loss:       float          # sum of negative realized PnL (≤ 0)
    profit_factor:    float | None   # gross_profit / |gross_loss|; None if no losses
    avg_win:          float | None   # None if no winning trades
    avg_loss:         float | None   # None if no losing trades (≤ 0)
    best_trade_pnl:   float | None
    worst_trade_pnl:  float | None
    drawdown_curve:   tuple[DrawdownPoint, ...]


def compute_analytics(result: BacktestSimulationResult) -> BacktestAnalytics:
    """Compute advanced metrics from a completed BacktestSimulationResult."""
    initial = result.config.initial_cash
    final   = result.equity_curve[-1].equity if result.equity_curve else initial
    total_return_pct = (final - initial) / initial * 100.0 if initial > 0 else 0.0

    drawdown_curve, max_drawdown_pct = _compute_drawdown(result.equity_curve, initial)

    closed_pnls = [
        t.realized_pnl
        for t in result.trades
        if t.action == "close_long" and t.realized_pnl is not None
    ]
    win_pnls  = [p for p in closed_pnls if p > 0.0]
    loss_pnls = [p for p in closed_pnls if p < 0.0]
    be_count  = len(closed_pnls) - len(win_pnls) - len(loss_pnls)

    win_count    = len(win_pnls)
    loss_count   = len(loss_pnls)
    closed_count = len(closed_pnls)
    win_rate     = win_count / closed_count if closed_count > 0 else None

    gross_profit  = sum(win_pnls)
    gross_loss    = sum(loss_pnls)
    profit_factor = gross_profit / abs(gross_loss) if gross_loss < 0.0 else None
    avg_win       = gross_profit / win_count  if win_count  > 0 else None
    avg_loss      = gross_loss   / loss_count if loss_count > 0 else None

    return BacktestAnalytics(
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        win_count=win_count,
        loss_count=loss_count,
        breakeven_count=be_count,
        win_rate=win_rate,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
        avg_win=avg_win,
        avg_loss=avg_loss,
        best_trade_pnl=max(closed_pnls) if closed_pnls else None,
        worst_trade_pnl=min(closed_pnls) if closed_pnls else None,
        drawdown_curve=tuple(drawdown_curve),
    )


def _compute_drawdown(
    equity_curve: tuple[BacktestEquityPoint, ...],
    initial_cash: float,
) -> tuple[list[DrawdownPoint], float]:
    """Return (per-bar drawdown points, max_drawdown_pct)."""
    running_peak = initial_cash
    max_dd       = 0.0
    points: list[DrawdownPoint] = []

    for pt in equity_curve:
        if pt.equity > running_peak:
            running_peak = pt.equity
        dd = (running_peak - pt.equity) / running_peak * 100.0 if running_peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
        points.append(DrawdownPoint(
            bar_index=pt.bar_index,
            timestamp=pt.timestamp,
            drawdown_pct=dd,
        ))

    return points, max_dd
