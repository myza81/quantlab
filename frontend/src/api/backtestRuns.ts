/**
 * API client for backtest runs: execute, retrieve, and export.
 *
 * Endpoints:
 *   POST /backtests/runs                        — run backtest pipeline
 *   GET  /backtests/runs/{id}/report            — retrieve persisted report
 *   GET  /backtests/runs/{id}/export/trades     — download trade ledger CSV
 *   GET  /backtests/runs/{id}/export/equity     — download equity curve CSV
 *   GET  /backtests/runs/{id}/export/report     — download full report JSON
 */
import type { OHLCVCandle } from './marketData'
import type {
  BacktestRunConfig,
  BacktestRunResponse,
  BacktestReport,
} from '../types/backtestRuns'
import { authedFetch } from './client'

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

  const resp = await authedFetch('/backtests/runs', {
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
  const resp = await authedFetch(`/backtests/runs/${runId}/report`)
  const data = await resp.json().catch(() => ({ detail: resp.statusText }))
  if (!resp.ok) {
    const detail = (data as { detail?: unknown }).detail
    const msg = typeof detail === 'string' ? detail : JSON.stringify(detail ?? `HTTP ${resp.status}`)
    throw new Error(msg)
  }
  return data as BacktestReport
}

async function _authedDownload(url: string, filename: string): Promise<void> {
  const resp = await authedFetch(url)
  if (!resp.ok) throw new Error(`Download failed: HTTP ${resp.status}`)
  const blob = await resp.blob()
  const blobUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = blobUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(blobUrl)
}

/** Download trade ledger as CSV. */
export function downloadTradesCSV(runId: string): Promise<void> {
  return _authedDownload(`/backtests/runs/${runId}/export/trades`, `trades_${runId.slice(0, 8)}.csv`)
}

/** Download per-bar equity + drawdown curve as CSV. */
export function downloadEquityCSV(runId: string): Promise<void> {
  return _authedDownload(`/backtests/runs/${runId}/export/equity`, `equity_${runId.slice(0, 8)}.csv`)
}

/** Download full backtest report as JSON. */
export function downloadReportJSON(runId: string): Promise<void> {
  return _authedDownload(`/backtests/runs/${runId}/export/report`, `backtest_${runId.slice(0, 8)}.json`)
}
