"""
Backtest Simulation Engine — Phase 2P.6 / updated Phase 2P.7 / updated Phase 2P.8 / updated EXEC-1.

Orchestrates sequential simulation of TradeIntents over historical price bars.
Phase 2P.7 adds deterministic cost modeling (commission + slippage).
Phase 2P.8 adds equity-fraction position sizing.
EXEC-1 adds NEXT_BAR_OPEN execution model (default) and SAME_BAR_CLOSE (explicit opt-in).

Pipeline:
    TradeIntentBatch + SimulationPriceBars + BacktestSimulationConfig
    → run_simulation()
    → BacktestSimulationResult

Key constraints:
    - Sequential and deterministic — no randomness
    - Long-only (no shorting, no leverage, no margin)
    - Single position, single instrument
    - Sizing: fixed_quantity (default) or equity_fraction
    - NEXT_BAR_OPEN (default): signal on Bar N → fill at Bar N+1 open ± slippage
    - SAME_BAR_CLOSE (explicit): signal on Bar N → fill at Bar N close ± slippage
    - Commission applied per trade
    - One equity point produced per price bar
    - Intents processed in input order (inherits TradeIntentBatch ordering)
    - No signal regeneration inside simulator
    - No indicator computation inside simulator
    - Final-bar NBO signals are rejected with FINAL_BAR_NO_FILL (no fabricated future price)

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

from collections import defaultdict

from backend.backtesting.models import (
    BacktestEquityPoint,
    BacktestExecutionModel,
    BacktestRejection,
    BacktestRejectionReason,
    BacktestSimulationConfig,
    BacktestSimulationResult,
    BacktestSimulationSummary,
    SimulatedTrade,
    SimulationPriceBar,
)
from backend.backtesting.position_tracker import PositionState, process_intent
from backend.strategy_registry.trade_intents import TradeIntent, TradeIntentAction, TradeIntentBatch


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

    Execution model (from config.execution_model):

        NEXT_BAR_OPEN (default):
            Intents generated at Bar N are deferred to Bar N+1.
            Fill price = Bar N+1 open ± slippage.
            If Bar N is the last bar in price_bars, the intent is rejected with
            FINAL_BAR_NO_FILL (no fabricated future price).
            Requires SimulationPriceBar.open to be populated for every bar
            that serves as an execution bar.

        SAME_BAR_CLOSE:
            Intents generated at Bar N are filled within the same bar.
            Fill price = Bar N close ± slippage.
            Provided for explicit research / backward-compatibility use only.

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
        config:       Simulation configuration (cash, quantity, cost model, execution model).

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
    equity_curve: list[BacktestEquityPoint] = []

    execution_model = config.execution_model

    if execution_model == BacktestExecutionModel.NEXT_BAR_OPEN:
        _run_next_bar_open(
            sorted_bars=sorted_bars,
            intent_map=intent_map,
            price_map=price_map,
            state=state,
            trades=trades,
            rejections=rejections,
            equity_curve=equity_curve,
            execution_model=execution_model,
        )
    else:
        _run_same_bar_close(
            sorted_bars=sorted_bars,
            intent_map=intent_map,
            state=state,
            trades=trades,
            rejections=rejections,
            equity_curve=equity_curve,
            execution_model=execution_model,
        )

    # Handle intents whose signal bar is not in price_bars at all (MISSING_PRICE).
    # These are never queued by either execution path.
    for intent in intent_batch.intents:
        if intent.source.bar_index not in price_map:
            _, rejection = process_intent(
                intent=intent,
                price=None,
                state=state,
                execution_model=execution_model,
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


# ---------------------------------------------------------------------------
# Execution path: NEXT_BAR_OPEN (default)
# ---------------------------------------------------------------------------

def _run_next_bar_open(
    sorted_bars:     list[SimulationPriceBar],
    intent_map:      dict[int, list[TradeIntent]],
    price_map:       dict[int, SimulationPriceBar],
    state:           PositionState,
    trades:          list[SimulatedTrade],
    rejections:      list[BacktestRejection],
    equity_curve:    list[BacktestEquityPoint],
    execution_model: BacktestExecutionModel,
) -> None:
    """
    Deferred-intent loop for NEXT_BAR_OPEN mode.

    Signal at Bar N → queued for Bar N+1.
    Bar N+1 open price is used as the raw fill price.
    If Bar N is the last bar (no N+1 exists), the intent is rejected immediately
    with FINAL_BAR_NO_FILL.
    """
    # Pre-compute signal_bar → next_bar mapping from sorted price bars.
    # If a bar has no successor in price_bars, it is not in this map.
    next_bar_map: dict[int, SimulationPriceBar] = {}
    for i in range(len(sorted_bars) - 1):
        next_bar_map[sorted_bars[i].bar_index] = sorted_bars[i + 1]

    # pending_nbo: execution_bar_index → list of intents to fill at that bar's open
    pending_nbo: dict[int, list[TradeIntent]] = defaultdict(list)

    for bar in sorted_bars:
        # Step 1: Resolve NBO fills scheduled for this bar (from previous bar's signals).
        for intent in pending_nbo.pop(bar.bar_index, []):
            open_price = bar.open
            if open_price is None:
                raise ValueError(
                    f"SimulationPriceBar at bar_index={bar.bar_index} is missing 'open' price, "
                    f"which is required for NEXT_BAR_OPEN execution. "
                    f"Populate SimulationPriceBar.open for all bars when using "
                    f"execution_model=NEXT_BAR_OPEN."
                )
            trade, rejection = process_intent(
                intent=intent,
                price=open_price,
                state=state,
                execution_bar_index=bar.bar_index,
                execution_timestamp=bar.timestamp,
                execution_model=execution_model,
            )
            if trade is not None:
                trades.append(trade)
            if rejection is not None:
                rejections.append(rejection)

        # Step 2: Queue new signals for next bar.
        # Conflict policy (EXEC-2D): capture position state at signal time (bar N).
        # Any CLOSE_LONG intent while flat is rejected here — a position only opened
        # by a same-bar OPEN_LONG does not exist yet at signal time (NBO defers fills).
        signal_time_is_flat = state.is_flat
        for intent in intent_map.get(bar.bar_index, []):
            next_bar = next_bar_map.get(bar.bar_index)
            if next_bar is None:
                # Signal on the last bar — no next bar to fill on.
                rejections.append(BacktestRejection(
                    rejection_id=f"rejection:{intent.intent_id}",
                    intent_id=intent.intent_id,
                    bar_index=intent.source.bar_index,
                    timestamp=intent.source.timestamp,
                    reason=BacktestRejectionReason.FINAL_BAR_NO_FILL,
                    detail=(
                        f"NEXT_BAR_OPEN: signal on final bar {intent.source.bar_index}; "
                        f"no subsequent bar available for fill"
                    ),
                ))
            elif intent.action == TradeIntentAction.CLOSE_LONG and signal_time_is_flat:
                # Exit signal on a bar where the position was flat at signal time.
                # Reject immediately — do not queue a CLOSE_LONG that would create a
                # wash trade by closing a position that only opens from a same-bar BUY.
                rejections.append(BacktestRejection(
                    rejection_id=f"rejection:{intent.intent_id}",
                    intent_id=intent.intent_id,
                    bar_index=intent.source.bar_index,
                    timestamp=intent.source.timestamp,
                    reason=BacktestRejectionReason.CONFLICT_EXIT_SUPPRESSED,
                    detail=(
                        f"NEXT_BAR_OPEN: close_long rejected at signal bar "
                        f"{intent.source.bar_index} — position was flat at signal time; "
                        f"exit suppressed by conflict policy"
                    ),
                ))
            else:
                pending_nbo[next_bar.bar_index].append(intent)

        # Step 3: Equity point for this bar (uses raw close for market value, always).
        _append_equity_point(bar, state, equity_curve)

    # pending_nbo is drained: every intent was either filled or FINAL_BAR_NO_FILL'd above.


# ---------------------------------------------------------------------------
# Execution path: SAME_BAR_CLOSE (explicit opt-in)
# ---------------------------------------------------------------------------

def _run_same_bar_close(
    sorted_bars:     list[SimulationPriceBar],
    intent_map:      dict[int, list[TradeIntent]],
    state:           PositionState,
    trades:          list[SimulatedTrade],
    rejections:      list[BacktestRejection],
    equity_curve:    list[BacktestEquityPoint],
    execution_model: BacktestExecutionModel,
) -> None:
    """
    Same-bar-close execution path.

    Signal at Bar N → fill at Bar N close ± slippage.
    Available for explicit research / backward-compatibility use only.
    """
    for bar in sorted_bars:
        bar_close = bar.close
        # Conflict policy (EXEC-2D): capture position state before processing any
        # intent on this bar. CLOSE_LONG is only valid if the position was already
        # open at bar start — a same-bar OPEN_LONG does not establish a closeable
        # position for a same-bar exit in the SAME_BAR_CLOSE path.
        was_flat_at_bar_start = state.is_flat

        for intent in intent_map.get(bar.bar_index, []):
            if intent.action == TradeIntentAction.CLOSE_LONG and was_flat_at_bar_start:
                rejections.append(BacktestRejection(
                    rejection_id=f"rejection:{intent.intent_id}",
                    intent_id=intent.intent_id,
                    bar_index=intent.source.bar_index,
                    timestamp=intent.source.timestamp,
                    reason=BacktestRejectionReason.CONFLICT_EXIT_SUPPRESSED,
                    detail=(
                        f"SAME_BAR_CLOSE: close_long rejected at bar "
                        f"{intent.source.bar_index} — position was flat at bar start; "
                        f"exit suppressed by conflict policy"
                    ),
                ))
            else:
                trade, rejection = process_intent(
                    intent=intent,
                    price=bar_close,
                    state=state,
                    execution_bar_index=bar.bar_index,
                    execution_timestamp=bar.timestamp,
                    execution_model=execution_model,
                )
                if trade is not None:
                    trades.append(trade)
                if rejection is not None:
                    rejections.append(rejection)

        _append_equity_point(bar, state, equity_curve)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _append_equity_point(
    bar:          SimulationPriceBar,
    state:        PositionState,
    equity_curve: list[BacktestEquityPoint],
) -> None:
    market_value   = state.position_quantity * bar.close
    unrealized_pnl = (
        (bar.close - state.average_entry_price) * state.position_quantity
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
