/**
 * Typed API client for POST /strategy-runs/run-composition.
 *
 * Sends already-loaded chart candles + a draft_id to the backend.
 * Backend computes tool outputs, evaluates semantics, returns signals + indicators.
 */
import type { OHLCVCandle } from './marketData'
import { authedFetch } from './client'

export interface CompositionSignal {
  timestamp: string | null
  symbol:    string
  timeframe: string
  signal_type: 'long' | 'exit'
  bar_index: number
  rule_id:   string | null
}

export interface CompositionIndicatorPoint {
  timestamp: string | null
  value:     number
}

export interface CompositionIndicatorSeries {
  name:   string
  kind:   string
  pane:   string
  color:  string | null
  points: CompositionIndicatorPoint[]
}

export interface CompositionRunResponse {
  draft_id:         string
  draft_name:       string
  status:           'success' | 'empty' | 'failed'
  candles_received: number
  signals:          CompositionSignal[]
  indicators:       CompositionIndicatorSeries[]
  warnings:         string[]
  error:            string | null
}

export async function runComposition(
  draftId:  string,
  symbol:   string,
  timeframe: string,
  candles:  OHLCVCandle[],
): Promise<CompositionRunResponse> {
  const bars = candles.map((c, i) => ({
    bar_index: i,
    timestamp: c.timestamp,
    open:      c.open,
    high:      c.high,
    low:       c.low,
    close:     c.close,
    volume:    c.volume,
  }))

  const resp = await authedFetch('/strategy-runs/run-composition', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ draft_id: draftId, symbol, timeframe, bars }),
  })

  const data = await resp.json().catch(() => ({ detail: resp.statusText }))
  if (!resp.ok) {
    const detail = (data as { detail?: unknown }).detail
    const msg = typeof detail === 'string' ? detail : JSON.stringify(detail ?? `HTTP ${resp.status}`)
    throw new Error(msg)
  }
  return data as CompositionRunResponse
}
