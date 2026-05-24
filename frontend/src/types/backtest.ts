/**
 * Backtest pipeline TypeScript types.
 *
 * Mirrors backend models for:
 *   - BacktestSimulationConfig
 *   - BacktestSimulationResult (summary, trades, equity curve, rejections)
 *   - SignalEventBatch / TradeIntentBatch (pipeline intermediates)
 */

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

export type PositionSizeMode = 'fixed_quantity' | 'equity_fraction'
export type CommissionMode   = 'none' | 'fixed' | 'percentage'
export type SlippageMode     = 'none' | 'fixed' | 'percentage'

export interface BacktestConfig {
  initial_cash:       number
  position_size_mode: PositionSizeMode
  fixed_quantity:     number
  equity_fraction:    number | null
  commission_mode:    CommissionMode
  commission_value:   number
  slippage_mode:      SlippageMode
  slippage_value:     number
}

// ---------------------------------------------------------------------------
// Market data params (subset — what BacktestPanel needs)
// ---------------------------------------------------------------------------

export interface BacktestMarketParams {
  symbol:      string
  provider:    string
  asset_class: string
  exchange:    string
  timeframe:   string
  start:       string
  end:         string
}

// ---------------------------------------------------------------------------
// Result types
// ---------------------------------------------------------------------------

export interface TradeCostBreakdown {
  commission_paid: number
  slippage_paid:   number
  total_cost:      number
}

export interface SimulatedTrade {
  trade_id:           string
  source_intent_id:   string
  action:             'open_long' | 'close_long'
  bar_index:          number
  timestamp:          string | null
  quantity:           number
  price:              number
  cash_before:        number
  cash_after:         number
  realized_pnl:       number | null
  position_after:     number
  cost_breakdown:     TradeCostBreakdown
  position_size_mode: PositionSizeMode
  sizing_value:       number
}

export interface BacktestEquityPoint {
  bar_index:         number
  timestamp:         string | null
  cash:              number
  position_quantity: number
  market_value:      number
  realized_pnl:      number
  unrealized_pnl:    number
  equity:            number
}

export interface BacktestRejection {
  rejection_id: string
  intent_id:    string
  bar_index:    number
  timestamp:    string | null
  reason:       string
  detail:       string
}

export interface BacktestSummary {
  total_bars:             number
  total_trades:           number
  open_long_trades:       number
  close_long_trades:      number
  total_rejections:       number
  initial_cash:           number
  final_cash:             number
  final_equity:           number
  total_realized_pnl:     number
  final_unrealized_pnl:   number
  peak_equity:            number
  trough_equity:          number
  total_commission_paid:  number
  total_slippage_paid:    number
  total_cost_paid:        number
  average_cost_per_trade: number
}

export interface BacktestResult {
  trades:       SimulatedTrade[]
  equity_curve: BacktestEquityPoint[]
  rejections:   BacktestRejection[]
  summary:      BacktestSummary
}
