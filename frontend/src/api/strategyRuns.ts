export interface StrategyRunRequest {
  strategy_id: string
  provider: string
  symbol: string
  timeframe: string
  start: string
  end: string
  asset_class?: string
  exchange?: string
  parameters?: Record<string, unknown>
}

export interface SignalResponse {
  strategy_id: string
  timestamp: string
  symbol: string
  timeframe: string
  signal_type: 'long' | 'short' | 'exit' | 'reduce'
  entry_reference: number
  invalidation_level: number
  confidence: number | null
  reasoning: string | null
}

export interface ForecastResponse {
  generated_at: string
  target_timestamp: string
  target_price: number
  direction: 'long' | 'short' | 'neutral'
  confidence: number
  invalidation_price: number | null
  reason: string | null
}

export interface IndicatorPoint {
  timestamp: string
  value: number
}

export interface IndicatorSeries {
  name: string
  kind: string
  pane: string
  color: string | null
  points: IndicatorPoint[]
}

export interface StrategyRunResponse {
  strategy_id: string
  status: 'success' | 'empty' | 'failed'
  candles_received: number
  signals: SignalResponse[]
  forecasts: ForecastResponse[]
  indicators: IndicatorSeries[]
  warnings: string[]
  error: string | null
}

import { authedFetch } from './client'

export async function runStrategy(req: StrategyRunRequest): Promise<StrategyRunResponse> {
  const resp = await authedFetch('/strategy-runs/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail ?? `HTTP ${resp.status}`)
  }
  return resp.json()
}
