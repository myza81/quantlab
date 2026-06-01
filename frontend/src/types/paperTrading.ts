/**
 * Paper Trading TypeScript types — Phase P3/P4.
 *
 * Mirror of backend/api/schemas/paper_trading.py.
 * No strategy_json. No user_id in list/summary types. No file_path. No secrets.
 */

export type PaperTradingSessionStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'terminated'

export interface PaperSimulationAssumptions {
  starting_cash: number
  currency: string
  fill_timing_model: string
  fee_mode: string
  fee_value: number
  slippage_mode: string
  slippage_value: number
  position_size_mode: string
  position_size_value: number
  max_concurrent_positions: number
  max_drawdown_stop_pct: number | null
  allow_short_selling: boolean
}

export interface PaperStrategySnapshot {
  draft_id: string
  display_name: string
  lifecycle_status: string
  snapshot_hash: string
}

export interface PaperTradingSessionSummary {
  session_id: string
  status: PaperTradingSessionStatus
  symbol: string
  timeframe: string
  source_mode: 'provider' | 'catalog'
  provider_name: string | null
  catalog_id: string | null
  exchange: string
  asset_class: string
  created_at: string
  updated_at: string
  last_processed_bar_timestamp: string | null
  strategy_snapshot: PaperStrategySnapshot
}

export interface PaperTradingSessionDetail extends PaperTradingSessionSummary {
  draft_id: string
  account_id: string
  forward_test_session_id: string | null
  lifecycle_status_at_activation: string
  activation_timestamp: string | null
  failure_reason: string | null
  simulation_assumptions: PaperSimulationAssumptions
}

export interface PaperAccount {
  account_id: string
  session_id: string
  currency: string
  starting_cash: number
  cash_balance: number
  equity: number
  available_cash: number
  peak_equity: number
  current_drawdown_pct: number
  total_realized_pnl: number
  total_fees_paid: number
  total_slippage_applied: number
  status: string
  created_at: string
  updated_at: string
  closed_at: string | null
}

export interface PaperOrder {
  order_id: string
  session_id: string
  symbol: string
  direction: string
  quantity: number
  status: string
  fill_timing_model: string
  signal_id: string | null
  signal_bar_timestamp: string | null
  target_fill_bar_timestamp: string | null
  created_at: string
  updated_at: string
  filled_at: string | null
  cancellation_reason: string | null
  rejection_reason: string | null
}

export interface PaperFill {
  fill_id: string
  order_id: string
  session_id: string
  symbol: string
  direction: string
  quantity: number
  gross_price: number
  slippage: number
  fill_price: number
  gross_value: number
  fee: number
  net_value: number
  fill_bar_timestamp: string
  created_at: string
  execution_reason: string | null
}

export interface PaperPosition {
  position_id: string
  session_id: string
  symbol: string
  quantity: number
  average_entry_price: number
  current_price: number | null
  market_value: number | null
  unrealized_pnl: number | null
  realized_pnl: number
  is_open: boolean
  opened_at: string
  last_updated_at: string
  closed_at: string | null
  opening_signal_id: string | null
  closing_signal_id: string | null
}

export interface PaperCycleResult {
  session_id: string
  status: string
  bars_fetched: number
  bars_processed: number
  warmup_bars_processed: number
  signal_eligible_bars_processed: number
  signals_generated: number
  signals_suppressed: number
  pending_orders_resolved: number
  orders_created: number
  orders_rejected: number
  fills_created: number
  positions_opened: number
  positions_closed: number
  account_snapshot_created: boolean
  last_processed_bar_timestamp: string | null
  gap_detected: boolean
  provider_failure: boolean
  activated: boolean
  drawdown_stop_triggered: boolean
  message: string | null
}

export interface PaperEquitySnapshot {
  snapshot_id: string
  session_id: string
  bar_timestamp: string
  snapshot_timestamp: string
  cash_balance: number
  equity: number
  available_cash: number
  peak_equity: number
  current_drawdown_pct: number
  open_position_count: number
  realized_pnl: number
  unrealized_pnl: number
  created_at: string
}

export interface CreatePaperTradingSessionRequest {
  draft_id: string
  symbol: string
  timeframe: string
  source_mode: 'provider' | 'catalog'
  provider_name?: string | null
  catalog_id?: string | null
  credential_id?: string | null
  exchange?: string
  asset_class?: string
  forward_test_session_id?: string | null
  simulation_assumptions?: {
    starting_cash?: number
    currency?: string
    fill_timing_model?: string
    fee_mode?: string
    fee_value?: number
    slippage_mode?: string
    slippage_value?: number
    position_size_mode?: string
    position_size_value?: number
    max_concurrent_positions?: number
    max_drawdown_stop_pct?: number | null
    allow_short_selling?: boolean
  }
}
