/**
 * API client for backtest runs: execute, retrieve, list history, export, and promote.
 *
 * Endpoints:
 *   POST /backtests/runs                            — run backtest pipeline
 *   GET  /backtests/runs                            — list run history (Phase 3S-C)
 *   GET  /backtests/runs/{id}/report                — retrieve persisted report
 *   POST /backtests/runs/{id}/promote-draft         — promote draft to 'backtested' (Phase R3/R4)
 *   GET  /backtests/runs/{id}/export/trades         — download trade ledger CSV
 *   GET  /backtests/runs/{id}/export/equity         — download equity curve CSV
 *   GET  /backtests/runs/{id}/export/report         — download full report JSON
 */
import type { OHLCVCandle } from './marketData'
import type {
  BacktestRunConfig,
  BacktestRunListItem,
  BacktestRunResponse,
  BacktestReport,
} from '../types/backtestRuns'
import type { StrategyDraftData } from '../types/drafts'
import { authedFetch } from './client'

export type { BacktestRunConfig, BacktestRunListItem, BacktestRunResponse, BacktestReport }

export async function runBacktest(
  draftId:      string,
  symbol:       string,
  timeframe:    string,
  candles:      OHLCVCandle[],
  config:       BacktestRunConfig,
  provenance?:  { source_mode?: string; provider_name?: string; catalog_id?: string },
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
    body:    JSON.stringify({
      draft_id:      draftId,
      symbol,
      timeframe,
      bars,
      config,
      source_mode:   provenance?.source_mode   ?? null,
      provider_name: provenance?.provider_name ?? null,
      catalog_id:    provenance?.catalog_id    ?? null,
    }),
  })

  const data = await resp.json().catch(() => ({ detail: resp.statusText }))
  if (!resp.ok) {
    const detail = (data as { detail?: unknown }).detail
    const msg = typeof detail === 'string' ? detail : JSON.stringify(detail ?? `HTTP ${resp.status}`)
    throw new Error(msg)
  }
  return data as BacktestRunResponse
}

export async function listBacktestRuns(limit = 50): Promise<BacktestRunListItem[]> {
  const resp = await authedFetch(`/backtests/runs?limit=${limit}`)
  const data = await resp.json().catch(() => ({ detail: resp.statusText }))
  if (!resp.ok) {
    const detail = (data as { detail?: unknown }).detail
    const msg = typeof detail === 'string' ? detail : JSON.stringify(detail ?? `HTTP ${resp.status}`)
    throw new Error(msg)
  }
  return data as BacktestRunListItem[]
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

/**
 * Promote a strategy draft to 'backtested' lifecycle status using a completed
 * backtest run as evidence.
 *
 * POST /backtests/runs/{run_id}/promote-draft
 *
 * The backend validates:
 *   - draft ownership
 *   - run ownership
 *   - run.draft_id === draft_id
 *   - run.status === 'completed'
 *   - lifecycle transition is permitted
 *
 * Returns the updated DraftResponse.
 * Throws Error with backend detail message on failure.
 */
export async function promoteDraftToBacktested(
  runId:   string,
  draftId: string,
  notes?:  string,
): Promise<StrategyDraftData> {
  const body: Record<string, unknown> = { draft_id: draftId }
  if (notes != null) body.notes = notes

  const resp = await authedFetch(`/backtests/runs/${runId}/promote-draft`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(body),
  })

  const data = await resp.json().catch(() => ({ detail: resp.statusText }))
  if (!resp.ok) {
    const detail = (data as { detail?: unknown }).detail
    const msg = typeof detail === 'string' ? detail : JSON.stringify(detail ?? `HTTP ${resp.status}`)
    throw new Error(msg)
  }
  return data as StrategyDraftData
}
