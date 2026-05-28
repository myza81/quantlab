"""
Backtest run service — Phase 2P.9.

Full pipeline: fetch draft → compile semantics → compute tool outputs
→ evaluate history → extract signal events → extract trade intents
→ run simulation → compute analytics → build and persist report.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.api.schemas.backtest_runs import (
    BacktestDrawdownRecord,
    BacktestEquityRecord,
    BacktestMetrics,
    BacktestRejectionRecord,
    BacktestReport,
    BacktestRunConfig,
    BacktestRunRequest,
    BacktestRunResponse,
    BacktestRunSummary,
    TradeRecord,
)
from backend.backtesting.analytics import compute_analytics
from backend.backtesting.models import (
    BacktestSimulationConfig,
    SimulatedTrade,
    SimulationPriceBar,
)
from backend.backtesting.simulator import run_simulation
from backend.strategy_registry.draft_repository import DraftRepository
from backend.strategy_registry.trade_intents import TradeIntent, TradeIntentBatch
from backend.strategy_registry.historical_evaluator import (
    HistoricalBarContext,
    HistoricalEvaluationInput,
    evaluate_history,
)
from backend.strategy_registry.semantic_compiler import compile_semantics
from backend.strategy_registry.signal_event_extractor import extract_signal_events
from backend.strategy_registry.trade_intent_extractor import extract_trade_intents
from backend.tools import create_default_registry
from backend.tools.historical_computation import (
    ToolComputationBarInput,
    ToolComputationError,
    build_bar_tool_outputs,
    compute_tool_outputs_for_history,
)

logger = logging.getLogger(__name__)

_DEFAULT_STORAGE = Path("storage/backtest_runs")


class BacktestRunError(Exception):
    """Raised for recoverable pipeline failures."""


class BacktestAccessDeniedError(Exception):
    """Raised when a user tries to access a backtest report they don't own."""


def create_backtest_run(
    request:    BacktestRunRequest,
    repository: DraftRepository,
    storage:    Path = _DEFAULT_STORAGE,
    user_id:    str | None = None,
) -> BacktestRunResponse:
    """
    Execute the full backtest pipeline for a saved strategy draft.

    Steps:
      1. Load draft from repository.
      2. Validate semantics present.
      3. Compile semantics → evaluation plan.
      4. Compute tool outputs for all bars.
      5. Evaluate semantics bar-by-bar.
      6. Extract signal events from evaluation.
      7. Extract trade intents from signal events.
      8. Run simulation (position sizing, cost model, equity curve).
      9. Compute advanced analytics (drawdown, win rate, etc.).
     10. Build BacktestReport.
     11. Persist report to filesystem.
     12. Return BacktestRunResponse with embedded report.

    Raises:
        BacktestRunError: for any recoverable pipeline failure.
    """
    # Step 1 — load draft (DraftNotFoundError propagates to route — maps to 404)
    draft = repository.load(request.draft_id, owner_id=user_id)

    if draft.semantics is None:
        raise BacktestRunError(
            f"Draft '{request.draft_id}' has no semantics. Define entry/exit rules first."
        )
    if not request.bars:
        raise BacktestRunError("No price bars supplied.")
    bars = _sort_and_validate_bars(request.bars)

    # Step 2 — compile semantics
    compile_result = compile_semantics(draft.semantics, draft_id=request.draft_id)
    if not compile_result.compiled or compile_result.evaluation_plan is None:
        raise BacktestRunError(
            f"Semantics compilation failed: {'; '.join(compile_result.errors)}"
        )
    plan = compile_result.evaluation_plan

    # Step 3 — compute tool outputs
    computation_bars = [
        ToolComputationBarInput(
            bar_index=b.bar_index,
            timestamp=b.timestamp,
            price_fields={"open": b.open, "high": b.high, "low": b.low,
                          "close": b.close, "volume": b.volume},
        )
        for b in bars
    ]
    registry = create_default_registry()

    if draft.toolset.tools:
        try:
            computation_result = compute_tool_outputs_for_history(
                toolset=draft.toolset,
                bars=computation_bars,
                registry=registry,
            )
            bar_tool_outputs = build_bar_tool_outputs(computation_result)
        except ToolComputationError as exc:
            raise BacktestRunError(f"Tool computation failed: {exc}") from exc
    else:
        bar_tool_outputs = {}

    # Step 4 — evaluate history
    bar_contexts = tuple(
        HistoricalBarContext(
            bar_index=b.bar_index,
            timestamp=b.timestamp,
            price_fields={"open": b.open, "high": b.high, "low": b.low,
                          "close": b.close, "volume": b.volume},
            tool_outputs=bar_tool_outputs.get(b.bar_index, {}),
        )
        for b in bars
    )
    try:
        eval_result = evaluate_history(HistoricalEvaluationInput(plan=plan, bars=bar_contexts))
    except ValueError as exc:
        raise BacktestRunError(str(exc)) from exc

    # Step 5 — extract signal events
    signal_batch = extract_signal_events(eval_result)

    # Step 6 — extract trade intents
    intent_batch = extract_trade_intents(signal_batch)

    # Step 7 — run simulation
    sim_config = _build_sim_config(request.config)
    price_bars = [
        SimulationPriceBar(
            bar_index=b.bar_index,
            timestamp=b.timestamp,
            close=b.close,
        )
        for b in bars
    ]
    sim_result = run_simulation(intent_batch, price_bars, sim_config)

    # Step 8 — compute analytics
    analytics = compute_analytics(sim_result)

    # Step 9 — build report
    run_id        = str(uuid.uuid4())
    run_timestamp = datetime.now(timezone.utc).isoformat()

    equity_curve = [
        BacktestEquityRecord(
            bar_index=pt.bar_index,
            timestamp=pt.timestamp.isoformat() if pt.timestamp else None,
            cash=pt.cash,
            position_quantity=pt.position_quantity,
            market_value=pt.market_value,
            realized_pnl=pt.realized_pnl,
            unrealized_pnl=pt.unrealized_pnl,
            equity=pt.equity,
        )
        for pt in sim_result.equity_curve
    ]

    drawdown_curve = [
        BacktestDrawdownRecord(
            bar_index=pt.bar_index,
            timestamp=pt.timestamp.isoformat() if pt.timestamp else None,
            drawdown_pct=pt.drawdown_pct,
        )
        for pt in analytics.drawdown_curve
    ]

    trade_records, open_position = _build_trade_records(
        sim_result.trades, sim_result.equity_curve, intent_batch
    )

    rejections = [
        BacktestRejectionRecord(
            rejection_id=r.rejection_id,
            intent_id=r.intent_id,
            bar_index=r.bar_index,
            timestamp=r.timestamp.isoformat() if r.timestamp else None,
            reason=r.reason.value,
            detail=r.detail,
        )
        for r in sim_result.rejections
    ]

    s = sim_result.summary
    metrics = BacktestMetrics(
        initial_equity=s.initial_cash,
        final_equity=s.final_equity,
        total_net_profit=s.total_realized_pnl,
        total_return_pct=analytics.total_return_pct,
        gross_profit=analytics.gross_profit,
        gross_loss=analytics.gross_loss,
        total_commission=s.total_commission_paid,
        total_slippage=s.total_slippage_paid,
        total_cost=s.total_cost_paid,
        trade_count=len(trade_records),
        win_count=analytics.win_count,
        loss_count=analytics.loss_count,
        breakeven_count=analytics.breakeven_count,
        win_rate=analytics.win_rate,
        avg_win=analytics.avg_win,
        avg_loss=analytics.avg_loss,
        profit_factor=analytics.profit_factor,
        best_trade_pnl=analytics.best_trade_pnl,
        worst_trade_pnl=analytics.worst_trade_pnl,
        max_drawdown_pct=analytics.max_drawdown_pct,
        peak_equity=s.peak_equity,
        trough_equity=s.trough_equity,
        total_bars=s.total_bars,
        total_rejections=s.total_rejections,
    )

    dataset_start = (
        bars[0].timestamp.isoformat() if bars[0].timestamp else None
    )
    dataset_end = (
        bars[-1].timestamp.isoformat() if bars[-1].timestamp else None
    )

    run_summary = BacktestRunSummary(
        run_id=run_id,
        draft_id=request.draft_id,
        draft_name=draft.display_name,
        symbol=request.symbol,
        timeframe=request.timeframe,
        bars_count=len(bars),
        run_timestamp=run_timestamp,
        status="completed",
        config=request.config,
        dataset_start=dataset_start,
        dataset_end=dataset_end,
        owner_user_id=user_id,
    )

    report = BacktestReport(
        run=run_summary,
        metrics=metrics,
        equity_curve=equity_curve,
        drawdown_curve=drawdown_curve,
        trades=trade_records,
        open_position=open_position,
        rejections=rejections,
    )

    # Step 10 — persist
    storage.mkdir(parents=True, exist_ok=True)
    (storage / f"{run_id}.json").write_text(report.model_dump_json(), encoding="utf-8")

    logger.info(
        "backtest_run: run_id=%s draft=%s bars=%d signals=%d trades=%d",
        run_id, request.draft_id, len(bars),
        signal_batch.summary.total_events, len(trade_records),
    )

    return BacktestRunResponse(run_id=run_id, status="completed", report=report)


def load_backtest_report(
    run_id: str,
    storage: Path = _DEFAULT_STORAGE,
    owner_user_id: str | None = None,
) -> BacktestReport:
    """Load a previously persisted backtest report by run_id.

    If owner_user_id is provided, raises BacktestAccessDeniedError when
    the report's owner_user_id does not match — information hiding: callers
    should map this to HTTP 404 to avoid existence leakage.
    """
    path = storage / f"{run_id}.json"
    if not path.exists():
        raise BacktestRunError(f"Backtest run '{run_id}' not found.")
    report = BacktestReport.model_validate(json.loads(path.read_text(encoding="utf-8")))
    if owner_user_id is not None and report.run.owner_user_id != owner_user_id:
        raise BacktestAccessDeniedError(f"Backtest run '{run_id}' not found.")
    return report


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_sim_config(cfg: BacktestRunConfig) -> BacktestSimulationConfig:
    return BacktestSimulationConfig(
        initial_cash=cfg.initial_equity,
        position_size_mode=cfg.position_size_mode,
        fixed_quantity=cfg.fixed_quantity,
        equity_fraction=cfg.equity_fraction,
        commission_mode=cfg.commission_mode,
        commission_value=cfg.commission_value,
        slippage_mode=cfg.slippage_mode,
        slippage_value=cfg.slippage_value,
    )


def _sort_and_validate_bars(bars: list) -> list:
    sorted_bars = sorted(bars, key=lambda b: b.bar_index)
    seen: set[int] = set()
    previous_timestamp = None

    for bar in sorted_bars:
        if bar.bar_index in seen:
            raise BacktestRunError(
                f"duplicate bar_index={bar.bar_index} in backtest run input"
            )
        seen.add(bar.bar_index)

        if bar.timestamp is not None and previous_timestamp is not None:
            if bar.timestamp < previous_timestamp:
                raise BacktestRunError(
                    "bar timestamps must be non-decreasing when ordered by bar_index"
                )
        if bar.timestamp is not None:
            previous_timestamp = bar.timestamp

    return sorted_bars


def _build_trade_records(
    trades:       tuple[SimulatedTrade, ...],
    equity_curve: tuple,
    intent_batch: TradeIntentBatch,
) -> tuple[list[TradeRecord], TradeRecord | None]:
    """Match open/close pairs into round-trip TradeRecords (FIFO).

    Enriches each TradeRecord with rule_id and signal_event_id from the
    originating TradeIntent, enabling full audit traceability back to
    the semantic rule that triggered entry or exit.
    """
    equity_map  = {pt.bar_index: pt.equity for pt in equity_curve}
    intent_map: dict[str, TradeIntent] = {i.intent_id: i for i in intent_batch.intents}

    open_stack: list[SimulatedTrade] = []
    records:    list[TradeRecord]    = []
    trade_num   = 0

    for trade in trades:
        if trade.action == "open_long":
            open_stack.append(trade)
        elif trade.action == "close_long" and open_stack:
            entry     = open_stack.pop(0)
            trade_num += 1
            entry_val = entry.price * entry.quantity
            gross_pnl = (trade.price - entry.price) * entry.quantity
            net_pnl   = trade.realized_pnl  # all-in PnL including both commissions
            ret_pct   = (
                net_pnl / entry_val * 100.0
                if entry_val > 0 and net_pnl is not None else None
            )

            entry_intent = intent_map.get(entry.source_intent_id)
            exit_intent  = intent_map.get(trade.source_intent_id)

            records.append(TradeRecord(
                trade_num=trade_num,
                entry_bar_index=entry.bar_index,
                exit_bar_index=trade.bar_index,
                entry_timestamp=entry.timestamp.isoformat() if entry.timestamp else None,
                exit_timestamp=trade.timestamp.isoformat() if trade.timestamp else None,
                side="long",
                quantity=entry.quantity,
                entry_price=entry.price,
                exit_price=trade.price,
                entry_commission=entry.cost_breakdown.commission_paid,
                exit_commission=trade.cost_breakdown.commission_paid,
                entry_slippage=entry.cost_breakdown.slippage_paid,
                exit_slippage=trade.cost_breakdown.slippage_paid,
                gross_pnl=gross_pnl,
                net_pnl=net_pnl,
                return_pct=ret_pct,
                holding_bars=trade.bar_index - entry.bar_index,
                equity_after=equity_map.get(trade.bar_index),
                entry_rule_id=entry_intent.source.rule_id if entry_intent else None,
                exit_rule_id=exit_intent.source.rule_id   if exit_intent  else None,
                entry_signal_event_id=entry_intent.source.signal_event_id if entry_intent else None,
                exit_signal_event_id=exit_intent.source.signal_event_id   if exit_intent  else None,
            ))

    open_position: TradeRecord | None = None
    if open_stack:
        entry     = open_stack[0]
        trade_num += 1
        entry_intent = intent_map.get(entry.source_intent_id)
        open_position = TradeRecord(
            trade_num=trade_num,
            entry_bar_index=entry.bar_index,
            exit_bar_index=None,
            entry_timestamp=entry.timestamp.isoformat() if entry.timestamp else None,
            exit_timestamp=None,
            side="long",
            quantity=entry.quantity,
            entry_price=entry.price,
            exit_price=None,
            entry_commission=entry.cost_breakdown.commission_paid,
            exit_commission=None,
            entry_slippage=entry.cost_breakdown.slippage_paid,
            exit_slippage=None,
            gross_pnl=None,
            net_pnl=None,
            return_pct=None,
            holding_bars=None,
            equity_after=None,
            entry_rule_id=entry_intent.source.rule_id if entry_intent else None,
            exit_rule_id=None,
            entry_signal_event_id=entry_intent.source.signal_event_id if entry_intent else None,
            exit_signal_event_id=None,
        )

    return records, open_position
