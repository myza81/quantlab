"""
Backtest Simulation Engine — Phase 2P.6 / updated Phase 2P.7 / updated Phase 2P.8.

Orchestrates sequential simulation of TradeIntents over historical price bars.
Phase 2P.7 adds deterministic cost modeling (commission + slippage).
Phase 2P.8 adds equity-fraction position sizing.

Pipeline:
    TradeIntentBatch + SimulationPriceBars + BacktestSimulationConfig
    → run_simulation()
    → BacktestSimulationResult

Key constraints:
    - Sequential and deterministic — no randomness
    - Long-only (no shorting, no leverage, no margin)
    - Single position, single instrument
    - Sizing: fixed_quantity (default) or equity_fraction
    - Execution price = bar close ± slippage (direction-aware)
    - Commission applied per trade
    - One equity point produced per price bar
    - Intents processed in input order (inherits TradeIntentBatch ordering)
    - No signal regeneration inside simulator
    - No indicator computation inside simulator

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

from collections import defaultdict

from backend.backtesting.models import (
    BacktestEquityPoint,
    BacktestRejection,
    BacktestSimulationConfig,
    BacktestSimulationResult,
    BacktestSimulationSummary,
    SimulatedTrade,
    SimulationPriceBar,
)
from backend.backtesting.position_tracker import PositionState, process_intent
from backend.strategy_registry.trade_intents import TradeIntent, TradeIntentBatch


# ---------------------------------------------------------------------------
# Public simulation entry point
# ---------------------------------------------------------------------------

def run_simulation(
    intent_batch: TradeIntentBatch,
    price_bars:   list[SimulationPriceBar],
    config:       BacktestSimulationConfig,
) -> BacktestSimulationResult:
    """
    Run a deterministic long-only backtest simulation.

    Processes TradeIntents sequentially over price bars.
    Produces a SimulatedTrade for each successful position change,
    a BacktestRejection for each invalid intent, and one equity point per bar.

    Intent ordering follows TradeIntentBatch ordering (inherited from SignalEventBatch).
    Bar ordering follows price_bars list order (caller must provide sorted bars).

    Phase 2P.7 additions:
        - Slippage applied to execution price at trade time
        - Commission deducted from cash at trade time
        - Realized PnL is all-in net (includes both commissions + slippage)
        - Summary includes aggregate cost totals

    This function does NOT:
        - generate signals
        - compute indicators
        - place broker orders
        - perform compliance decisions
        - apply stochastic or random fills

    Args:
        intent_batch: Ordered intent batch from extract_trade_intents().
        price_bars:   All price bars for the simulation period, sorted by bar_index.
        config:       Simulation configuration (cash, quantity, cost model).

    Returns:
        BacktestSimulationResult with full trade log, equity curve, rejections, summary.
    """
    sorted_bars = _sort_and_validate_price_bars(price_bars)

    # Build bar_index → price map
    price_map: dict[int, SimulationPriceBar] = {bar.bar_index: bar for bar in sorted_bars}
    _validate_intent_timestamps(intent_batch, price_map)

    # Build bar_index → list[TradeIntent] (preserves input order per bar)
    intent_map: dict[int, list[TradeIntent]] = defaultdict(list)
    for intent in intent_batch.intents:
        intent_map[intent.source.bar_index].append(intent)

    # Initialize mutable simulation state with cost model + sizing config
    state = PositionState(
        cash=config.initial_cash,
        fixed_quantity=config.fixed_quantity,
        commission_mode=config.commission_mode,
        commission_value=config.commission_value,
        slippage_mode=config.slippage_mode,
        slippage_value=config.slippage_value,
        position_size_mode=config.position_size_mode,
        equity_fraction=config.equity_fraction or 0.0,
    )

    trades:     list[SimulatedTrade]    = []
    rejections: list[BacktestRejection] = []

    # Process bars in sorted order (one equity point per bar)
    equity_curve: list[BacktestEquityPoint] = []

    for bar in sorted_bars:
        bar_close = bar.close

        # Process all intents for this bar (in intent batch order)
        for intent in intent_map.get(bar.bar_index, []):
            trade, rejection = process_intent(
                intent=intent,
                price=bar_close,
                state=state,
            )
            if trade is not None:
                trades.append(trade)
            if rejection is not None:
                rejections.append(rejection)

        # Compute equity point for this bar (uses raw close for market value)
        market_value   = state.position_quantity * bar_close
        unrealized_pnl = (
            (bar_close - state.average_entry_price) * state.position_quantity
            if state.is_long else 0.0
        )
        equity = state.cash + market_value

        equity_curve.append(BacktestEquityPoint(
            bar_index=bar.bar_index,
            timestamp=bar.timestamp,
            cash=state.cash,
            position_quantity=state.position_quantity,
            market_value=market_value,
            realized_pnl=state.cumulative_realized_pnl,
            unrealized_pnl=unrealized_pnl,
            equity=equity,
        ))

    # Handle intents whose bar_index is not in price_bars (missing price)
    for intent in intent_batch.intents:
        if intent.source.bar_index not in price_map:
            _, rejection = process_intent(
                intent=intent,
                price=None,
                state=state,
            )
            if rejection is not None:
                rejections.append(rejection)

    summary = _compute_summary(
        config=config,
        trades=trades,
        rejections=rejections,
        equity_curve=equity_curve,
        state=state,
    )

    return BacktestSimulationResult(
        plan_draft_id=intent_batch.plan_draft_id,
        config=config,
        trades=tuple(trades),
        equity_curve=tuple(equity_curve),
        rejections=tuple(rejections),
        summary=summary,
    )


def _sort_and_validate_price_bars(
    price_bars: list[SimulationPriceBar],
) -> list[SimulationPriceBar]:
    sorted_bars = sorted(price_bars, key=lambda b: b.bar_index)
    seen: set[int] = set()
    previous_timestamp = None

    for bar in sorted_bars:
        if bar.bar_index in seen:
            raise ValueError(f"duplicate bar_index={bar.bar_index} in simulation price bars")
        seen.add(bar.bar_index)

        if bar.timestamp is not None and previous_timestamp is not None:
            if bar.timestamp < previous_timestamp:
                raise ValueError(
                    "price bar timestamps must be non-decreasing when ordered by bar_index"
                )
        if bar.timestamp is not None:
            previous_timestamp = bar.timestamp

    return sorted_bars


def _validate_intent_timestamps(
    intent_batch: TradeIntentBatch,
    price_map: dict[int, SimulationPriceBar],
) -> None:
    for intent in intent_batch.intents:
        price_bar = price_map.get(intent.source.bar_index)
        if price_bar is None:
            continue
        if intent.source.timestamp is None or price_bar.timestamp is None:
            continue
        if intent.source.timestamp != price_bar.timestamp:
            raise ValueError(
                f"intent '{intent.intent_id}' timestamp does not match "
                f"price bar timestamp at bar_index={intent.source.bar_index}"
            )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_summary(
    config:       BacktestSimulationConfig,
    trades:       list[SimulatedTrade],
    rejections:   list[BacktestRejection],
    equity_curve: list[BacktestEquityPoint],
    state:        PositionState,
) -> BacktestSimulationSummary:
    open_long_count  = sum(1 for t in trades if t.action == "open_long")
    close_long_count = sum(1 for t in trades if t.action == "close_long")

    # Aggregate cost totals
    total_commission = sum(t.cost_breakdown.commission_paid for t in trades)
    total_slippage   = sum(t.cost_breakdown.slippage_paid   for t in trades)
    total_cost       = total_commission + total_slippage
    avg_cost         = total_cost / len(trades) if trades else 0.0

    if equity_curve:
        final_point      = equity_curve[-1]
        final_cash       = final_point.cash
        final_equity     = final_point.equity
        final_unrealized = final_point.unrealized_pnl
        all_equities     = [p.equity for p in equity_curve]
        peak_equity      = max(all_equities)
        trough_equity    = min(all_equities)
    else:
        final_cash       = config.initial_cash
        final_equity     = config.initial_cash
        final_unrealized = 0.0
        peak_equity      = config.initial_cash
        trough_equity    = config.initial_cash

    return BacktestSimulationSummary(
        total_bars=len(equity_curve),
        total_trades=len(trades),
        open_long_trades=open_long_count,
        close_long_trades=close_long_count,
        total_rejections=len(rejections),
        initial_cash=config.initial_cash,
        final_cash=final_cash,
        final_equity=final_equity,
        total_realized_pnl=state.cumulative_realized_pnl,
        final_unrealized_pnl=final_unrealized,
        peak_equity=peak_equity,
        trough_equity=trough_equity,
        total_commission_paid=total_commission,
        total_slippage_paid=total_slippage,
        total_cost_paid=total_cost,
        average_cost_per_trade=avg_cost,
    )
