/**
 * TypeScript types mirroring backend/api/schemas/backtest_runs.py
 */

export interface BacktestRunConfig {
  initial_equity:     number
  position_size_mode: 'equity_fraction' | 'fixed_quantity'
  equity_fraction:    number | null
  fixed_quantity:     number
  commission_mode:    'none' | 'fixed' | 'percentage'
  commission_value:   number
  slippage_mode:      'none' | 'fixed' | 'percentage'
  slippage_value:     number
}

export const DEFAULT_BACKTEST_CONFIG: BacktestRunConfig = {
  initial_equity:     10000,
  position_size_mode: 'equity_fraction',
  equity_fraction:    0.95,
  fixed_quantity:     1,
  commission_mode:    'none',
  commission_value:   0,
  slippage_mode:      'none',
  slippage_value:     0,
}

export interface BacktestEquityRecord {
  bar_index:         number
  timestamp:         string | null
  cash:              number
  position_quantity: number
  market_value:      number
  realized_pnl:      number
  unrealized_pnl:    number
  equity:            number
}

export interface BacktestDrawdownRecord {
  bar_index:    number
  timestamp:    string | null
  drawdown_pct: number
}

export interface TradeRecord {
  trade_num:        number
  entry_bar_index:  number
  exit_bar_index:   number | null
  entry_timestamp:  string | null
  exit_timestamp:   string | null
  side:             'long'
  quantity:         number
  entry_price:      number
  exit_price:       number | null
  entry_commission: number
  exit_commission:  number | null
  entry_slippage:   number
  exit_slippage:    number | null
  gross_pnl:        number | null
  net_pnl:          number | null
  return_pct:       number | null
  holding_bars:     number | null
  equity_after:     number | null
  // Audit traceability
  entry_rule_id:         string | null
  exit_rule_id:          string | null
  entry_signal_event_id: string | null
  exit_signal_event_id:  string | null
}

export interface BacktestRejectionRecord {
  rejection_id: string
  intent_id:    string
  bar_index:    number
  timestamp:    string | null
  reason:       string
  detail:       string
}

export interface BacktestMetrics {
  initial_equity:   number
  final_equity:     number
  total_net_profit: number
  total_return_pct: number
  gross_profit:     number
  gross_loss:       number
  total_commission: number
  total_slippage:   number
  total_cost:       number
  trade_count:      number
  win_count:        number
  loss_count:       number
  breakeven_count:  number
  win_rate:         number | null
  avg_win:          number | null
  avg_loss:         number | null
  profit_factor:    number | null
  best_trade_pnl:   number | null
  worst_trade_pnl:  number | null
  max_drawdown_pct: number
  peak_equity:      number
  trough_equity:    number
  total_bars:       number
  total_rejections: number
}

export interface BacktestRunSummary {
  run_id:        string
  draft_id:      string
  draft_name:    string
  symbol:        string
  timeframe:     string
  bars_count:    number
  run_timestamp: string
  status:        string
  config:        BacktestRunConfig
  // Reproducibility metadata
  dataset_start:  string | null
  dataset_end:    string | null
  engine_version: string
}

export interface BacktestReport {
  run:            BacktestRunSummary
  metrics:        BacktestMetrics
  equity_curve:   BacktestEquityRecord[]
  drawdown_curve: BacktestDrawdownRecord[]
  trades:         TradeRecord[]
  open_position:  TradeRecord | null
  rejections:     BacktestRejectionRecord[]
}

export interface BacktestRunResponse {
  run_id:  string
  status:  string
  report:  BacktestReport
}
