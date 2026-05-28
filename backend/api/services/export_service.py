"""
Backtest Export Service.

Produces downloadable artifacts from a BacktestReport:
    - trade ledger CSV  (all closed + open positions)
    - equity curve CSV  (per-bar equity and drawdown)
    - full report JSON  (complete payload, schema-stable)

Architecture boundary — no simulation logic, no indicator computation.
Pure serialization of an already-computed BacktestReport.
"""
from __future__ import annotations

import csv
import io
import json

from backend.api.schemas.backtest_runs import BacktestReport, TradeRecord


# ---------------------------------------------------------------------------
# Trade ledger CSV
# ---------------------------------------------------------------------------

_TRADE_HEADERS = [
    "trade_num",
    "status",
    "entry_bar_index",
    "exit_bar_index",
    "entry_timestamp",
    "exit_timestamp",
    "side",
    "quantity",
    "entry_price",
    "exit_price",
    "entry_commission",
    "exit_commission",
    "entry_slippage",
    "exit_slippage",
    "gross_pnl",
    "net_pnl",
    "return_pct",
    "holding_bars",
    "equity_after",
    "entry_rule_id",
    "exit_rule_id",
    "entry_signal_event_id",
    "exit_signal_event_id",
]


def _trade_row(trade: TradeRecord, status: str) -> dict:
    return {
        "trade_num":             trade.trade_num,
        "status":                status,
        "entry_bar_index":       trade.entry_bar_index,
        "exit_bar_index":        trade.exit_bar_index   if trade.exit_bar_index  is not None else "",
        "entry_timestamp":       trade.entry_timestamp  or "",
        "exit_timestamp":        trade.exit_timestamp   or "",
        "side":                  trade.side,
        "quantity":              trade.quantity,
        "entry_price":           trade.entry_price,
        "exit_price":            trade.exit_price       if trade.exit_price      is not None else "",
        "entry_commission":      trade.entry_commission,
        "exit_commission":       trade.exit_commission  if trade.exit_commission is not None else "",
        "entry_slippage":        trade.entry_slippage,
        "exit_slippage":         trade.exit_slippage    if trade.exit_slippage   is not None else "",
        "gross_pnl":             trade.gross_pnl        if trade.gross_pnl       is not None else "",
        "net_pnl":               trade.net_pnl          if trade.net_pnl         is not None else "",
        "return_pct":            trade.return_pct       if trade.return_pct      is not None else "",
        "holding_bars":          trade.holding_bars     if trade.holding_bars    is not None else "",
        "equity_after":          trade.equity_after     if trade.equity_after    is not None else "",
        "entry_rule_id":         trade.entry_rule_id    or "",
        "exit_rule_id":          trade.exit_rule_id     or "",
        "entry_signal_event_id": trade.entry_signal_event_id or "",
        "exit_signal_event_id":  trade.exit_signal_event_id  or "",
    }


def export_trade_ledger_csv(report: BacktestReport) -> str:
    """
    Serialize the trade ledger (closed + open) to CSV text.

    Columns include all cost breakdown fields, audit rule IDs, and
    signal event IDs for full traceability.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_TRADE_HEADERS, lineterminator="\n")
    writer.writeheader()

    for trade in report.trades:
        writer.writerow(_trade_row(trade, "closed"))

    if report.open_position is not None:
        writer.writerow(_trade_row(report.open_position, "open"))

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Equity curve CSV
# ---------------------------------------------------------------------------

_EQUITY_HEADERS = [
    "bar_index",
    "timestamp",
    "cash",
    "position_quantity",
    "market_value",
    "realized_pnl",
    "unrealized_pnl",
    "equity",
    "drawdown_pct",
]


def export_equity_curve_csv(report: BacktestReport) -> str:
    """
    Serialize the per-bar equity curve joined with drawdown percentage to CSV.

    Bars present in equity_curve but absent from drawdown_curve get an
    empty drawdown_pct cell (should never happen for a well-formed report).
    """
    dd_map = {pt.bar_index: pt.drawdown_pct for pt in report.drawdown_curve}

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_EQUITY_HEADERS, lineterminator="\n")
    writer.writeheader()

    for pt in report.equity_curve:
        dd = dd_map.get(pt.bar_index)
        writer.writerow({
            "bar_index":         pt.bar_index,
            "timestamp":         pt.timestamp or "",
            "cash":              pt.cash,
            "position_quantity": pt.position_quantity,
            "market_value":      pt.market_value,
            "realized_pnl":      pt.realized_pnl,
            "unrealized_pnl":    pt.unrealized_pnl,
            "equity":            pt.equity,
            "drawdown_pct":      dd if dd is not None else "",
        })

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Full report JSON
# ---------------------------------------------------------------------------

def export_report_json(report: BacktestReport) -> str:
    """
    Serialize the full BacktestReport to canonical JSON (schema-stable).

    Uses Pydantic's model_dump_json() to guarantee field ordering and
    type serialization matching the stored report format.
    """
    return report.model_dump_json(indent=2)
