/**
 * BacktestHistoryPanel — browse prior backtest runs.
 *
 * Phase 3S-C: closes the "refresh = report gone forever" gap.
 * Fetches GET /backtests/runs (ownership-scoped, newest-first).
 * Each row shows lightweight metadata; "Reopen" loads the full report.
 */
import { useEffect, useState } from 'react'
import type { BacktestRunListItem } from '../types/backtestRuns'
import { listBacktestRuns, fetchBacktestReport } from '../api/backtestRuns'
import type { BacktestReport } from '../types/backtestRuns'
import { isAuthError, isSubscriptionExpiredError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { STAGE_LABELS } from '../lib/lifecycleGuidance'

interface Props {
  onReportLoaded: (report: BacktestReport) => void
}

const pct = (v: number | null | undefined) =>
  v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`

const pctColor = (v: number | null | undefined) =>
  v == null ? '#4a5568' : v > 0 ? '#66bb6a' : v < 0 ? '#ef5350' : '#4a5568'

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}

export function BacktestHistoryPanel({ onReportLoaded }: Props) {
  const { logout, refreshUser } = useAuth()
  const [items,     setItems]     = useState<BacktestRunListItem[]>([])
  const [status,    setStatus]    = useState<'loading' | 'success' | 'error'>('loading')
  const [error,     setError]     = useState<string | null>(null)
  const [reopening, setReopening] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const data = await listBacktestRuns(50)
        if (!cancelled) { setItems(data); setStatus('success') }
      } catch (err) {
        if (cancelled) return
        if (isAuthError(err)) { logout(); return }
        if (isSubscriptionExpiredError(err)) { await refreshUser(); return }
        setError(err instanceof Error ? err.message : 'Failed to load history')
        setStatus('error')
      }
    }
    load()
    return () => { cancelled = true }
  }, [logout, refreshUser])

  async function handleReopen(runId: string) {
    setReopening(runId)
    try {
      const report = await fetchBacktestReport(runId)
      onReportLoaded(report)
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setError(err instanceof Error ? err.message : 'Failed to load report')
    } finally {
      setReopening(null)
    }
  }

  if (status === 'loading') {
    return (
      <div style={s.panel}>
        <div style={s.heading}>Backtest History</div>
        <div style={s.state}>Loading…</div>
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div style={s.panel}>
        <div style={s.heading}>Backtest History</div>
        <div style={s.stateError}>{error}</div>
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div style={s.panel}>
        <div style={s.heading}>Backtest History</div>
        <div style={s.state}>
          No backtest runs yet.<br />
          Run a backtest from the Composer tab to see results here.
        </div>
      </div>
    )
  }

  return (
    <div style={s.panel}>
      <div style={s.heading}>Backtest History <span style={s.count}>({items.length})</span></div>
      <div style={s.list}>
        {items.map(item => (
          <div key={item.run_id} data-testid="history-run-row" style={s.row}>
            <div style={s.rowMeta}>
              <span style={s.symbol}>{item.symbol}</span>
              <span style={s.sep}>·</span>
              <span style={s.tf}>{item.timeframe}</span>
              <span style={s.sep}>·</span>
              <span style={s.draft}>{item.draft_name}</span>
            </div>
            <div style={s.rowStats}>
              <span style={{ ...s.stat, color: pctColor(item.total_return_pct) }}>
                {pct(item.total_return_pct)}
              </span>
              <span style={s.statLabel}>return</span>
              {item.trade_count != null && (
                <>
                  <span style={s.sep}>·</span>
                  <span style={s.stat}>{item.trade_count}</span>
                  <span style={s.statLabel}>trades</span>
                </>
              )}
              {item.max_drawdown_pct != null && (
                <>
                  <span style={s.sep}>·</span>
                  <span style={{ ...s.stat, color: '#ef5350' }}>
                    -{item.max_drawdown_pct.toFixed(1)}%
                  </span>
                  <span style={s.statLabel}>dd</span>
                </>
              )}
            </div>
            <div style={s.rowProvenance}>
              {item.dataset_provenance?.source_mode && (
                <span style={s.badge}>{item.dataset_provenance.source_mode}</span>
              )}
              {item.draft_provenance?.lifecycle_status_at_run && (
                <span style={s.badge}>{STAGE_LABELS[item.draft_provenance.lifecycle_status_at_run] ?? item.draft_provenance.lifecycle_status_at_run}</span>
              )}
              <span style={s.ts}>{fmtDate(item.run_timestamp)}</span>
            </div>
            <button
              data-testid="reopen-run-btn"
              style={s.reopenBtn}
              disabled={reopening === item.run_id}
              onClick={() => handleReopen(item.run_id)}
            >
              {reopening === item.run_id ? '…' : 'Reopen'}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  panel: {
    flex:          1,
    display:       'flex',
    flexDirection: 'column',
    overflow:      'hidden',
    padding:       '16px 20px',
    gap:           12,
  },
  heading: {
    fontSize:      13,
    fontWeight:    600,
    color:         '#8892a4',
    letterSpacing: '0.04em',
    fontFamily:    'monospace',
    flexShrink:    0,
  },
  count: {
    fontWeight: 400,
    color:      '#4a5568',
  },
  state: {
    flex:           1,
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'center',
    color:          '#4a5568',
    fontSize:       12,
    textAlign:      'center' as const,
    lineHeight:     1.6,
  },
  stateError: {
    color:     '#ef5350',
    fontSize:  12,
    padding:   8,
    fontFamily: 'monospace',
  },
  list: {
    flex:      1,
    overflowY: 'auto' as const,
    display:   'flex',
    flexDirection: 'column' as const,
    gap:       8,
  },
  row: {
    display:       'grid',
    gridTemplateColumns: '1fr auto auto',
    gridTemplateRows:    'auto auto',
    gap:           '2px 8px',
    background:    '#0c0c18',
    border:        '1px solid #1a1a28',
    borderRadius:  4,
    padding:       '8px 10px',
    alignItems:    'center',
  },
  rowMeta: {
    display:    'flex',
    alignItems: 'center',
    gap:        4,
    gridColumn: '1',
    gridRow:    '1',
  },
  rowStats: {
    display:    'flex',
    alignItems: 'center',
    gap:        4,
    gridColumn: '2',
    gridRow:    '1',
  },
  rowProvenance: {
    display:    'flex',
    alignItems: 'center',
    gap:        4,
    gridColumn: '1 / 3',
    gridRow:    '2',
  },
  symbol: { fontSize: 12, fontWeight: 600, color: '#d1d4dc', fontFamily: 'monospace' },
  tf:     { fontSize: 11, color: '#4a5568', fontFamily: 'monospace' },
  draft:  { fontSize: 11, color: '#4a5568', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const, maxWidth: 160 },
  sep:    { fontSize: 10, color: '#2a2d3e' },
  stat:   { fontSize: 11, fontFamily: 'monospace', fontWeight: 600 },
  statLabel: { fontSize: 10, color: '#4a5568' },
  badge: {
    fontSize:     9,
    fontFamily:   'monospace',
    color:        '#4a5568',
    background:   '#141420',
    border:       '1px solid #1a1a28',
    borderRadius: 3,
    padding:      '1px 4px',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.04em',
  },
  ts:  { fontSize: 10, color: '#3a4050', fontFamily: 'monospace', marginLeft: 4 },
  reopenBtn: {
    gridColumn:    '3',
    gridRow:       '1 / 3',
    background:    'transparent',
    border:        '1px solid #26a69a',
    borderRadius:  4,
    color:         '#26a69a',
    cursor:        'pointer',
    fontSize:      11,
    fontFamily:    'monospace',
    padding:       '4px 10px',
    whiteSpace:    'nowrap' as const,
    alignSelf:     'center',
  },
}
