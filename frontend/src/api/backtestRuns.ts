/**
 * API client for POST /backtests/runs and GET /backtests/runs/{runId}/report.
 */
import type { OHLCVCandle } from './marketData'
import type {
  BacktestRunConfig,
  BacktestRunResponse,
  BacktestReport,
} from '../types/backtestRuns'

export type { BacktestRunConfig, BacktestRunResponse, BacktestReport }

export async function runBacktest(
  draftId:   string,
  symbol:    string,
  timeframe: string,
  candles:   OHLCVCandle[],
  config:    BacktestRunConfig,
): Promise<BacktestRunResponse> {
  const bars = candles.map((c, i) => ({
    bar_index: i,
    timestamp: c.timestamp,
    open:      c.open,
    high:      c.high,
    low:       c.low,
    close:     c.close,
    volume:    c.volume,
  }))

  const resp = await fetch('/backtests/runs', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ draft_id: draftId, symbol, timeframe, bars, config }),
  })

  const data = await resp.json().catch(() => ({ detail: resp.statusText }))
  if (!resp.ok) {
    const detail = (data as { detail?: unknown }).detail
    const msg = typeof detail === 'string' ? detail : JSON.stringify(detail ?? `HTTP ${resp.status}`)
    throw new Error(msg)
  }
  return data as BacktestRunResponse
}

export async function fetchBacktestReport(runId: string): Promise<BacktestReport> {
  const resp = await fetch(`/backtests/runs/${runId}/report`)
  const data = await resp.json().catch(() => ({ detail: resp.statusText }))
  if (!resp.ok) {
    const detail = (data as { detail?: unknown }).detail
    const msg = typeof detail === 'string' ? detail : JSON.stringify(detail ?? `HTTP ${resp.status}`)
    throw new Error(msg)
  }
  return data as BacktestReport
}
