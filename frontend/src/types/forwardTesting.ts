/**
 * Forward Testing TypeScript types — Phase 4C.5.
 *
 * Mirror of backend/api/schemas/forward_testing.py.
 * No strategy_json exposed. No user_id in list/summary types.
 * No file_path. No credential secrets.
 */

export type ForwardTestSessionStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'terminated'

export interface ForwardTestStrategySnapshot {
  draft_id: string
  display_name: string
  lifecycle_status: string
  snapshot_hash: string
}

export interface ForwardTestSessionSummary {
  session_id: string
  status: ForwardTestSessionStatus
  symbol: string
  timeframe: string
  source_mode: 'provider' | 'catalog'
  provider_name: string | null
  catalog_id: string | null
  created_at: string
  updated_at: string
  last_processed_bar_timestamp: string | null
  bars_evaluated: number
  signal_eligible_bars_processed: number
  signals_recorded: number
  strategy_snapshot: ForwardTestStrategySnapshot
}

export interface ForwardTestSessionDetail extends ForwardTestSessionSummary {
  draft_id: string
  lifecycle_status_at_activation: string
  warmup_bars_required: number
  warmup_bars_processed: number
  activation_timestamp: string | null
  failure_reason: string | null
  error_category: string | null
  exchange: string
  asset_class: string
  /** Set by the FT-2 scheduler; null until the scheduler has run at least once. */
  last_cycle_attempted_at: string | null
}

export interface ForwardTestCycleResult {
  session_id: string
  status: ForwardTestSessionStatus
  bars_fetched: number
  bars_processed: number
  warmup_bars_processed: number
  signal_eligible_bars_processed: number
  signals_generated: number
  signals_suppressed: number
  last_processed_bar_timestamp: string | null
  gap_detected: boolean
  provider_failure: boolean
  activated: boolean
  message: string | null
}

export interface ForwardTestSignal {
  signal_id: string
  session_id: string
  bar_timestamp: string
  signal_timestamp: string
  signal_direction: 'entry_long' | 'entry_short' | 'exit_long' | 'exit_short' | 'no_action'
  rule_id: string
  bar_open: number
  bar_high: number
  bar_low: number
  bar_close: number
  bar_volume: number
  feature_values_at_signal: Record<string, number>
  warmup_satisfied: boolean
  strategy_snapshot_hash: string
  symbol: string
  timeframe: string
  provider_name: string | null
  catalog_id: string | null
  created_at: string
  /** Timestamp of the next bar after signal bar; null when signal fires on the final bar in the cycle. */
  actionable_from_bar_timestamp: string | null
}

export interface ForwardTestBar {
  bar_index: number
  bar_timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  is_warmup_bar: boolean
  processed_at: string
}

export interface CreateForwardTestSessionRequest {
  draft_id: string
  symbol: string
  timeframe: string
  source_mode: 'provider' | 'catalog'
  provider_name?: string | null
  catalog_id?: string | null
  credential_id?: string | null
  exchange?: string
  asset_class?: string
}

/** Context extracted from a backtest report to prefill forward-test session creation. */
export interface ForwardTestPrefill {
  draft_id:       string
  draft_name?:    string
  symbol?:        string
  timeframe?:     string
  provider_name?: string
  exchange?:      string
  asset_class?:   string
}
