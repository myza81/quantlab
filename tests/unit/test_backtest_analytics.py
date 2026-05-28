"""
Backtest Analytics — correctness and edge-case tests.

Coverage areas:
  1.  total_return_pct — basic positive return
  2.  total_return_pct — negative return
  3.  total_return_pct — zero return (flat equity)
  4.  total_return_pct — empty equity curve
  5.  max_drawdown_pct — single drawdown trough
  6.  max_drawdown_pct — multiple drawdown troughs (takes worst)
  7.  max_drawdown_pct — monotonically rising equity (no drawdown)
  8.  max_drawdown_pct — equity returns to peak (drawdown resets)
  9.  drawdown_curve — per-bar values match expected
  10. win / loss / breakeven classification
  11. win_rate — no trades → None
  12. win_rate — all winners → 1.0
  13. win_rate — all losers → 0.0
  14. win_rate — mixed → correct fraction
  15. gross_profit — sum of positive PnLs only
  16. gross_loss — sum of negative PnLs only (≤ 0)
  17. profit_factor — no losses → None
  18. profit_factor — no wins → None (or 0/|loss|)
  19. profit_factor — mixed trades → gross_profit / |gross_loss|
  20. avg_win / avg_loss — None when no winning / losing trades
  21. avg_win / avg_loss — correct averages
  22. best_trade_pnl / worst_trade_pnl — None when no closed trades
  23. best_trade_pnl / worst_trade_pnl — correct extremes
  24. open position does NOT count toward closed trade metrics
  25. breakeven_count — PnL == 0.0 exactly
  26. determinism — same input → same output
  27. immutability — result is frozen
  28. architecture guard — no forbidden imports in analytics module
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any

import pytest

from backend.backtesting.analytics import compute_analytics
from backend.backtesting.models import (
    BacktestEquityPoint,
    BacktestSimulationConfig,
    BacktestSimulationResult,
    BacktestSimulationSummary,
    PositionSizeMode,
    SimulatedTrade,
)
from backend.backtesting.cost_model import TradeCostBreakdown


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2024, 1, 1, tzinfo=timezone.utc)

_ZERO_COST = TradeCostBreakdown(
    raw_price=100.0,
    adjusted_price=100.0,
    gross_value=100.0,
    slippage_paid=0.0,
    commission_paid=0.0,
    total_cost=0.0,
    net_cash_impact=-100.0,
)


def _cfg(initial_cash: float = 10_000.0) -> BacktestSimulationConfig:
    return BacktestSimulationConfig(
        initial_cash=initial_cash,
        position_size_mode=PositionSizeMode.FIXED_QUANTITY,
        fixed_quantity=1.0,
    )


def _equity_pt(bar_index: int, equity: float, cash: float = 0.0) -> BacktestEquityPoint:
    return BacktestEquityPoint(
        bar_index=bar_index,
        timestamp=_TS,
        cash=cash,
        position_quantity=0.0,
        market_value=0.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        equity=equity,
    )


def _close_trade(intent_id: str, bar_index: int, realized_pnl: float) -> SimulatedTrade:
    return SimulatedTrade(
        trade_id=f"trade:{intent_id}",
        source_intent_id=intent_id,
        action="close_long",
        bar_index=bar_index,
        timestamp=_TS,
        quantity=1.0,
        price=100.0 + realized_pnl,
        cash_before=9_000.0,
        cash_after=9_000.0 + 100.0 + realized_pnl,
        realized_pnl=realized_pnl,
        position_after=0.0,
        cost_breakdown=_ZERO_COST,
        position_size_mode=PositionSizeMode.FIXED_QUANTITY,
        sizing_value=1.0,
    )


def _open_trade(intent_id: str, bar_index: int) -> SimulatedTrade:
    return SimulatedTrade(
        trade_id=f"trade:{intent_id}",
        source_intent_id=intent_id,
        action="open_long",
        bar_index=bar_index,
        timestamp=_TS,
        quantity=1.0,
        price=100.0,
        cash_before=10_000.0,
        cash_after=9_000.0,
        realized_pnl=None,
        position_after=1.0,
        cost_breakdown=_ZERO_COST,
        position_size_mode=PositionSizeMode.FIXED_QUANTITY,
        sizing_value=1.0,
    )


def _summary(**kwargs: Any) -> BacktestSimulationSummary:
    defaults: dict[str, Any] = dict(
        total_bars=5,
        total_trades=0,
        open_long_trades=0,
        close_long_trades=0,
        total_rejections=0,
        initial_cash=10_000.0,
        final_cash=10_000.0,
        final_equity=10_000.0,
        total_realized_pnl=0.0,
        final_unrealized_pnl=0.0,
        peak_equity=10_000.0,
        trough_equity=10_000.0,
        total_commission_paid=0.0,
        total_slippage_paid=0.0,
        total_cost_paid=0.0,
        average_cost_per_trade=0.0,
    )
    defaults.update(kwargs)
    return BacktestSimulationSummary(**defaults)


def _result(
    trades: tuple[SimulatedTrade, ...] = (),
    equity_curve: tuple[BacktestEquityPoint, ...] = (),
    initial_cash: float = 10_000.0,
) -> BacktestSimulationResult:
    return BacktestSimulationResult(
        plan_draft_id="test-draft",
        config=_cfg(initial_cash),
        trades=trades,
        equity_curve=equity_curve,
        rejections=(),
        summary=_summary(initial_cash=initial_cash),
    )


# ---------------------------------------------------------------------------
# 1–4. total_return_pct
# ---------------------------------------------------------------------------

def test_total_return_pct_positive():
    curve = (
        _equity_pt(0, 10_000.0),
        _equity_pt(1, 11_000.0),
    )
    result = _result(equity_curve=curve)
    analytics = compute_analytics(result)
    assert abs(analytics.total_return_pct - 10.0) < 1e-9


def test_total_return_pct_negative():
    curve = (
        _equity_pt(0, 10_000.0),
        _equity_pt(1, 9_500.0),
    )
    result = _result(equity_curve=curve)
    analytics = compute_analytics(result)
    assert abs(analytics.total_return_pct - (-5.0)) < 1e-9


def test_total_return_pct_zero():
    curve = (
        _equity_pt(0, 10_000.0),
        _equity_pt(1, 10_000.0),
    )
    result = _result(equity_curve=curve)
    analytics = compute_analytics(result)
    assert analytics.total_return_pct == 0.0


def test_total_return_pct_empty_equity_curve():
    result = _result(equity_curve=())
    analytics = compute_analytics(result)
    # No equity curve → final == initial → 0%
    assert analytics.total_return_pct == 0.0


# ---------------------------------------------------------------------------
# 5–8. max_drawdown_pct
# ---------------------------------------------------------------------------

def test_max_drawdown_single_trough():
    # Peak 10k, trough 8k → 20% drawdown
    curve = tuple(
        _equity_pt(i, v)
        for i, v in enumerate([10_000.0, 9_000.0, 8_000.0, 9_500.0])
    )
    result = _result(equity_curve=curve)
    analytics = compute_analytics(result)
    expected_dd = (10_000.0 - 8_000.0) / 10_000.0 * 100.0
    assert abs(analytics.max_drawdown_pct - expected_dd) < 1e-9


def test_max_drawdown_takes_worst():
    # Two troughs: first −10%, second −25% → max should be 25%
    curve = tuple(
        _equity_pt(i, v)
        for i, v in enumerate([10_000.0, 9_000.0, 11_000.0, 10_000.0, 8_250.0])
    )
    result = _result(equity_curve=curve)
    analytics = compute_analytics(result)
    expected_dd = (11_000.0 - 8_250.0) / 11_000.0 * 100.0
    assert abs(analytics.max_drawdown_pct - expected_dd) < 1e-9


def test_max_drawdown_monotonically_rising():
    curve = tuple(
        _equity_pt(i, 10_000.0 + i * 100.0) for i in range(5)
    )
    result = _result(equity_curve=curve)
    analytics = compute_analytics(result)
    assert analytics.max_drawdown_pct == 0.0


def test_max_drawdown_recovers_to_peak():
    # Drops to 8k then recovers to 10k; max drawdown is still 20%
    curve = tuple(
        _equity_pt(i, v)
        for i, v in enumerate([10_000.0, 8_000.0, 10_000.0])
    )
    result = _result(equity_curve=curve)
    analytics = compute_analytics(result)
    assert abs(analytics.max_drawdown_pct - 20.0) < 1e-9


# ---------------------------------------------------------------------------
# 9. drawdown_curve — per-bar values
# ---------------------------------------------------------------------------

def test_drawdown_curve_per_bar_values():
    curve = tuple(
        _equity_pt(i, v)
        for i, v in enumerate([10_000.0, 10_000.0, 9_000.0, 10_000.0, 8_000.0])
    )
    result = _result(equity_curve=curve, initial_cash=10_000.0)
    analytics = compute_analytics(result)
    dd = analytics.drawdown_curve

    assert len(dd) == 5
    assert dd[0].drawdown_pct == 0.0          # at peak
    assert dd[1].drawdown_pct == 0.0          # still at peak
    assert abs(dd[2].drawdown_pct - 10.0) < 1e-9  # (10k-9k)/10k*100
    assert dd[3].drawdown_pct == 0.0          # recovered to peak
    assert abs(dd[4].drawdown_pct - 20.0) < 1e-9  # (10k-8k)/10k*100


def test_drawdown_curve_bar_indices_preserved():
    bar_indices = [5, 10, 15]
    curve = tuple(_equity_pt(i, 10_000.0 - i * 100) for i in bar_indices)
    result = _result(equity_curve=curve)
    analytics = compute_analytics(result)
    dd_indices = [pt.bar_index for pt in analytics.drawdown_curve]
    assert dd_indices == bar_indices


# ---------------------------------------------------------------------------
# 10–14. win / loss / win_rate
# ---------------------------------------------------------------------------

def test_win_loss_classification_no_trades():
    result = _result()
    analytics = compute_analytics(result)
    assert analytics.win_count == 0
    assert analytics.loss_count == 0
    assert analytics.breakeven_count == 0
    assert analytics.win_rate is None


def test_win_rate_all_winners():
    trades = tuple(
        _close_trade(f"i{i}", i, 100.0)
        for i in range(5)
    )
    result = _result(trades=trades)
    analytics = compute_analytics(result)
    assert analytics.win_count == 5
    assert analytics.loss_count == 0
    assert analytics.win_rate == 1.0


def test_win_rate_all_losers():
    trades = tuple(
        _close_trade(f"i{i}", i, -50.0)
        for i in range(3)
    )
    result = _result(trades=trades)
    analytics = compute_analytics(result)
    assert analytics.win_count == 0
    assert analytics.loss_count == 3
    assert analytics.win_rate == 0.0


def test_win_rate_mixed():
    trades = (
        _close_trade("w1", 1, 200.0),
        _close_trade("w2", 2, 100.0),
        _close_trade("l1", 3, -50.0),
        _close_trade("l2", 4, -150.0),
        _close_trade("be", 5, 0.0),
    )
    result = _result(trades=trades)
    analytics = compute_analytics(result)
    assert analytics.win_count == 2
    assert analytics.loss_count == 2
    assert analytics.breakeven_count == 1
    assert abs(analytics.win_rate - (2 / 5)) < 1e-9


# ---------------------------------------------------------------------------
# 15–16. gross_profit / gross_loss
# ---------------------------------------------------------------------------

def test_gross_profit_sums_only_positive_pnls():
    trades = (
        _close_trade("w1", 1, 300.0),
        _close_trade("l1", 2, -100.0),
        _close_trade("w2", 3, 150.0),
    )
    result = _result(trades=trades)
    analytics = compute_analytics(result)
    assert abs(analytics.gross_profit - 450.0) < 1e-9


def test_gross_loss_sums_only_negative_pnls():
    trades = (
        _close_trade("w1", 1, 300.0),
        _close_trade("l1", 2, -100.0),
        _close_trade("l2", 3, -200.0),
    )
    result = _result(trades=trades)
    analytics = compute_analytics(result)
    assert abs(analytics.gross_loss - (-300.0)) < 1e-9


def test_gross_profit_zero_when_no_winners():
    trades = (
        _close_trade("l1", 1, -50.0),
    )
    result = _result(trades=trades)
    analytics = compute_analytics(result)
    assert analytics.gross_profit == 0.0


def test_gross_loss_zero_when_no_losers():
    trades = (
        _close_trade("w1", 1, 100.0),
    )
    result = _result(trades=trades)
    analytics = compute_analytics(result)
    assert analytics.gross_loss == 0.0


# ---------------------------------------------------------------------------
# 17–19. profit_factor
# ---------------------------------------------------------------------------

def test_profit_factor_no_losses_returns_none():
    trades = (_close_trade("w1", 1, 100.0),)
    result = _result(trades=trades)
    analytics = compute_analytics(result)
    # No losses → no meaningful profit factor
    assert analytics.profit_factor is None


def test_profit_factor_no_wins():
    trades = (_close_trade("l1", 1, -50.0),)
    result = _result(trades=trades)
    analytics = compute_analytics(result)
    # gross_profit = 0, gross_loss = -50 → profit_factor = 0 / 50 = 0.0
    assert analytics.profit_factor is not None
    assert analytics.profit_factor == 0.0


def test_profit_factor_mixed():
    trades = (
        _close_trade("w1", 1, 300.0),
        _close_trade("l1", 2, -100.0),
    )
    result = _result(trades=trades)
    analytics = compute_analytics(result)
    # 300 / 100 = 3.0
    assert abs(analytics.profit_factor - 3.0) < 1e-9


def test_profit_factor_no_trades():
    result = _result()
    analytics = compute_analytics(result)
    assert analytics.profit_factor is None


# ---------------------------------------------------------------------------
# 20–21. avg_win / avg_loss
# ---------------------------------------------------------------------------

def test_avg_win_none_when_no_wins():
    trades = (_close_trade("l1", 1, -20.0),)
    result = _result(trades=trades)
    analytics = compute_analytics(result)
    assert analytics.avg_win is None


def test_avg_loss_none_when_no_losses():
    trades = (_close_trade("w1", 1, 80.0),)
    result = _result(trades=trades)
    analytics = compute_analytics(result)
    assert analytics.avg_loss is None


def test_avg_win_correct():
    trades = (
        _close_trade("w1", 1, 100.0),
        _close_trade("w2", 2, 300.0),
    )
    result = _result(trades=trades)
    analytics = compute_analytics(result)
    assert abs(analytics.avg_win - 200.0) < 1e-9


def test_avg_loss_correct():
    trades = (
        _close_trade("l1", 1, -80.0),
        _close_trade("l2", 2, -160.0),
    )
    result = _result(trades=trades)
    analytics = compute_analytics(result)
    # avg_loss = (-80 + -160) / 2 = -120
    assert abs(analytics.avg_loss - (-120.0)) < 1e-9


# ---------------------------------------------------------------------------
# 22–23. best_trade_pnl / worst_trade_pnl
# ---------------------------------------------------------------------------

def test_best_worst_none_when_no_closed_trades():
    result = _result()
    analytics = compute_analytics(result)
    assert analytics.best_trade_pnl is None
    assert analytics.worst_trade_pnl is None


def test_best_worst_correct():
    trades = (
        _close_trade("a", 1, 500.0),
        _close_trade("b", 2, -200.0),
        _close_trade("c", 3, 100.0),
    )
    result = _result(trades=trades)
    analytics = compute_analytics(result)
    assert abs(analytics.best_trade_pnl - 500.0) < 1e-9
    assert abs(analytics.worst_trade_pnl - (-200.0)) < 1e-9


# ---------------------------------------------------------------------------
# 24. open position does NOT count toward closed trade metrics
# ---------------------------------------------------------------------------

def test_open_position_excluded_from_closed_metrics():
    # Only an open_long present — no closed trade metrics should be populated
    trades = (_open_trade("intent1", 1),)
    result = _result(trades=trades)
    analytics = compute_analytics(result)
    assert analytics.win_count == 0
    assert analytics.loss_count == 0
    assert analytics.win_rate is None
    assert analytics.profit_factor is None
    assert analytics.best_trade_pnl is None
    assert analytics.worst_trade_pnl is None


# ---------------------------------------------------------------------------
# 25. breakeven_count — PnL == 0.0 exactly
# ---------------------------------------------------------------------------

def test_breakeven_count_exact_zero():
    trades = (
        _close_trade("be1", 1, 0.0),
        _close_trade("be2", 2, 0.0),
        _close_trade("w1",  3, 50.0),
    )
    result = _result(trades=trades)
    analytics = compute_analytics(result)
    assert analytics.breakeven_count == 2
    assert analytics.win_count == 1
    assert analytics.loss_count == 0


# ---------------------------------------------------------------------------
# 26. determinism — same input → identical output
# ---------------------------------------------------------------------------

def test_determinism():
    trades = (
        _close_trade("t1", 1, 200.0),
        _close_trade("t2", 2, -100.0),
    )
    curve = tuple(_equity_pt(i, 10_000.0 + i * 50) for i in range(5))
    result = _result(trades=trades, equity_curve=curve)

    a1 = compute_analytics(result)
    a2 = compute_analytics(result)

    assert a1.total_return_pct == a2.total_return_pct
    assert a1.max_drawdown_pct == a2.max_drawdown_pct
    assert a1.win_count == a2.win_count
    assert a1.profit_factor == a2.profit_factor
    assert len(a1.drawdown_curve) == len(a2.drawdown_curve)
    for p1, p2 in zip(a1.drawdown_curve, a2.drawdown_curve):
        assert p1.bar_index == p2.bar_index
        assert p1.drawdown_pct == p2.drawdown_pct


# ---------------------------------------------------------------------------
# 27. immutability — BacktestAnalytics is a frozen dataclass
# ---------------------------------------------------------------------------

def test_analytics_is_immutable():
    result = _result()
    analytics = compute_analytics(result)
    with pytest.raises((AttributeError, TypeError)):
        analytics.win_count = 99  # type: ignore[misc]


def test_drawdown_point_is_immutable():
    result = _result(equity_curve=(_equity_pt(0, 10_000.0),))
    analytics = compute_analytics(result)
    pt = analytics.drawdown_curve[0]
    with pytest.raises((AttributeError, TypeError)):
        pt.drawdown_pct = 999.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 28. architecture guard
# ---------------------------------------------------------------------------

def test_no_forbidden_imports_in_analytics():
    import backend.backtesting.analytics as mod
    src = inspect.getsource(mod)
    # Only scan actual import lines; comments/docstrings deliberately list forbidden
    # modules to document the boundary and must not trigger this guard.
    import_lines = [
        line for line in src.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    import_src = "\n".join(import_lines)
    for forbidden in ("strategy_runtime", "execution", "forward_testing"):
        assert forbidden not in import_src, (
            f"analytics.py must not import from backend.{forbidden}"
        )


# ---------------------------------------------------------------------------
# Additional: profit_factor when gross_profit = 0 but losses exist
# ---------------------------------------------------------------------------

def test_profit_factor_zero_when_no_winners_but_losses():
    """gross_profit=0, gross_loss=-50 → profit_factor = 0.0 (not None)."""
    trades = (
        _close_trade("l1", 1, -50.0),
        _close_trade("be", 2, 0.0),
    )
    result = _result(trades=trades)
    analytics = compute_analytics(result)
    assert analytics.profit_factor is not None
    assert analytics.profit_factor == 0.0


# ---------------------------------------------------------------------------
# Drawdown: initial cash used as starting peak (not first bar equity)
# ---------------------------------------------------------------------------

def test_drawdown_initial_cash_as_starting_peak():
    """
    If first bar equity is BELOW initial cash, drawdown starts immediately.
    Ensures running_peak is initialized to initial_cash, not first bar.
    """
    # initial_cash = 10_000, but first bar equity already at 9_500 (paid commission)
    curve = tuple(
        _equity_pt(i, v)
        for i, v in enumerate([9_500.0, 9_000.0, 9_800.0])
    )
    result = _result(equity_curve=curve, initial_cash=10_000.0)
    analytics = compute_analytics(result)
    # peak is 10_000 (initial), worst is 9_000 → (10k-9k)/10k = 10%
    assert abs(analytics.max_drawdown_pct - 10.0) < 1e-9


def test_drawdown_curve_starts_from_initial_cash_peak():
    curve = (_equity_pt(0, 9_500.0),)
    result = _result(equity_curve=curve, initial_cash=10_000.0)
    analytics = compute_analytics(result)
    dd = analytics.drawdown_curve[0]
    expected = (10_000.0 - 9_500.0) / 10_000.0 * 100.0
    assert abs(dd.drawdown_pct - expected) < 1e-9
