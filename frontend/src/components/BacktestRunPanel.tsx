/**
 * BacktestRunPanel — NAV-UX-3D / NAV-UX-3D.1 (stabilization).
 *
 * Self-contained "Run Backtest" form for the Backtest section.
 * Reads the active strategy from StrategyContext so the user doesn't need to
 * re-select a strategy — the context bar selection drives it.
 *
 * State machine:
 *   idle → fetching (fetchOHLCV) → running (runBacktest) → success | error
 *
 * On success: calls onSuccess(report) so the parent can open the report and
 * refresh the evidence list.
 * On cancel: calls onCancel().
 *
 * NAV-UX-3D.1 stabilization fixes:
 *   - initial_equity: step=100 (default 10000 now valid: (10000-100)%100=0 ✓)
 *   - equity_fraction: step=1 (default 95 now valid: (95-1)%1=0 ✓)
 *   - commission_value input shown when mode is non-none
 *   - exchange NOT hardcoded — omitted so backend defaults to 'unknown'
 *   - asset class values match backend enums (fx, future — not forex, futures)
 *   - csv / parquet removed from provider dropdown (require catalog flow)
 *   - date cross-validation: start > end is caught before fetchOHLCV
 */
import { useEffect, useState } from 'react'
import { useStrategyContext } from '../context/StrategyContext'
import { fetchOHLCV } from '../api/marketData'
import { runBacktest } from '../api/backtestRuns'
import { fetchCredentials } from '../api/credentials'
import { isAuthError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { BacktestReport, BacktestRunConfig } from '../types/backtestRuns'
import type { CredentialMetadata } from '../types/credentials'
import { DEFAULT_BACKTEST_CONFIG } from '../types/backtestRuns'

interface Props {
  onSuccess: (report: BacktestReport) => void
  onCancel:  () => void
}

type Phase = 'idle' | 'fetching' | 'running' | 'success' | 'error'

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10)
}

function defaultStart(): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() - 1)
  return isoDate(d)
}

function defaultEnd(): string {
  return isoDate(new Date())
}

export function BacktestRunPanel({ onSuccess, onCancel }: Props) {
  const { logout } = useAuth()
  const { draftId, displayName } = useStrategyContext()

  // Market data params
  const [symbol,     setSymbol]     = useState('AAPL')
  const [assetClass, setAssetClass] = useState('equity')
  const [timeframe,  setTimeframe]  = useState('1d')
  const [provider,   setProvider]   = useState('yahoo')
  const [startDate,  setStartDate]  = useState(defaultStart)
  const [endDate,    setEndDate]    = useState(defaultEnd)
  const [credId,     setCredId]     = useState('')
  const [credentials, setCredentials] = useState<CredentialMetadata[]>([])

  // Backtest config
  const [btConfig, setBtConfig] = useState<BacktestRunConfig>(DEFAULT_BACKTEST_CONFIG)

  // Execution state
  const [phase,   setPhase]   = useState<Phase>('idle')
  const [error,   setError]   = useState<string | null>(null)
  const [barCount, setBarCount] = useState<number | null>(null)

  const busy = phase === 'fetching' || phase === 'running'

  useEffect(() => {
    fetchCredentials()
      .then(r => setCredentials(r.credentials))
      .catch(() => { /* Non-fatal: picker degrades gracefully */ })
  }, [])

  // Filter credentials to the selected provider
  const filteredCreds = provider
    ? credentials.filter(c => c.provider_name.toLowerCase() === provider.toLowerCase())
    : credentials

  async function handleRun(e: React.FormEvent) {
    e.preventDefault()
    if (!draftId) return
    setError(null)
    setBarCount(null)

    // Date range validation — must happen before any API call
    if (startDate > endDate) {
      setError('Start date must be before or equal to end date.')
      return
    }

    // Step 1 — fetch market data
    // exchange is intentionally omitted: the backend normalises it to 'unknown'
    // so no hardcoded venue leaks into the run provenance.
    setPhase('fetching')
    let candles
    try {
      const resp = await fetchOHLCV({
        provider,
        symbol:      symbol.trim().toUpperCase(),
        asset_class: assetClass,
        timeframe,
        start:       startDate,
        end:         endDate,
        credential_id: credId || undefined,
      })
      candles = resp.candles
      setBarCount(candles.length)
    } catch (e) {
      if (isAuthError(e)) { logout(); return }
      setError(e instanceof Error ? e.message : 'Failed to fetch market data')
      setPhase('error')
      return
    }

    if (candles.length === 0) {
      setError('No candles returned for this symbol / timeframe / date range.')
      setPhase('error')
      return
    }

    // Step 2 — run backtest
    setPhase('running')
    try {
      const resp = await runBacktest(
        draftId,
        symbol.trim().toUpperCase(),
        timeframe,
        candles,
        btConfig,
        { source_mode: 'provider', provider_name: provider },
      )
      setPhase('success')
      onSuccess(resp.report)
    } catch (e) {
      if (isAuthError(e)) { logout(); return }
      setError(e instanceof Error ? e.message : 'Backtest failed')
      setPhase('error')
    }
  }

  // No strategy selected
  if (!draftId) {
    return (
      <div data-testid="bt-run-panel" style={s.panel}>
        <div style={s.header}>
          <span style={s.title}>Run Backtest</span>
          <button style={s.cancelBtn} onClick={onCancel}>✕</button>
        </div>
        <div data-testid="bt-run-no-strategy" style={s.blocked}>
          Select a strategy from the context bar before running a backtest.
        </div>
      </div>
    )
  }

  return (
    <div data-testid="bt-run-panel" style={s.panel}>
      <div style={s.header}>
        <span style={s.title}>Run Backtest</span>
        <span style={s.strategyLabel}>{displayName}</span>
        <button style={s.cancelBtn} onClick={onCancel} disabled={busy}>✕</button>
      </div>

      <form data-testid="bt-run-form" onSubmit={handleRun} style={s.form}>
        {/* ── Market data params ── */}
        <div style={s.sectionLabel}>Market Data</div>

        <div style={s.row}>
          <Field label="Symbol">
            <input
              data-testid="bt-symbol-input"
              style={s.input}
              value={symbol}
              onChange={e => setSymbol(e.target.value.toUpperCase())}
              required
              placeholder="AAPL"
            />
          </Field>
          <Field label="Timeframe">
            <select
              data-testid="bt-timeframe-select"
              style={s.input}
              value={timeframe}
              onChange={e => setTimeframe(e.target.value)}
            >
              {['1m','5m','15m','30m','1h','4h','1d','1w','1M'].map(tf => (
                <option key={tf} value={tf}>{tf}</option>
              ))}
            </select>
          </Field>
        </div>

        <div style={s.row}>
          <Field label="Provider">
            <select
              data-testid="bt-provider-select"
              style={s.input}
              value={provider}
              onChange={e => { setProvider(e.target.value); setCredId('') }}
            >
              <option value="yahoo">Yahoo Finance</option>
              <option value="polygon">Polygon.io</option>
            </select>
          </Field>
          <Field label="Asset Class">
            <select
              data-testid="bt-asset-class-select"
              style={s.input}
              value={assetClass}
              onChange={e => setAssetClass(e.target.value)}
            >
              <option value="equity">Equity</option>
              <option value="crypto">Crypto</option>
              <option value="fx">FX / Forex</option>
              <option value="future">Futures</option>
              <option value="etf">ETF</option>
              <option value="index">Index</option>
            </select>
          </Field>
        </div>

        <div style={s.row}>
          <Field label="Start">
            <input
              data-testid="bt-start-input"
              style={s.input}
              type="date"
              value={startDate}
              max={endDate}
              onChange={e => setStartDate(e.target.value)}
              required
            />
          </Field>
          <Field label="End">
            <input
              data-testid="bt-end-input"
              style={s.input}
              type="date"
              value={endDate}
              min={startDate}
              onChange={e => setEndDate(e.target.value)}
              required
            />
          </Field>
        </div>

        {/* Credential picker */}
        <Field label="Credential (optional)">
          <select
            data-testid="bt-credential-select"
            style={s.input}
            value={credId}
            onChange={e => setCredId(e.target.value)}
          >
            <option value="">None</option>
            {filteredCreds.map(c => (
              <option key={c.credential_id} value={c.credential_id}>
                {c.credential_label}
              </option>
            ))}
          </select>
        </Field>

        {/* ── Backtest config ── */}
        <div style={{ ...s.sectionLabel, marginTop: 12 }}>Backtest Config</div>

        <div style={s.row}>
          <Field label="Initial Equity ($)">
            <input
              data-testid="bt-equity-input"
              style={s.input}
              type="number"
              min={100}
              step={100}
              value={btConfig.initial_equity}
              onChange={e => setBtConfig(c => ({ ...c, initial_equity: parseFloat(e.target.value) || 10000 }))}
            />
          </Field>
          <Field label="Position Size">
            <select
              data-testid="bt-position-mode-select"
              style={s.input}
              value={btConfig.position_size_mode}
              onChange={e => setBtConfig(c => ({
                ...c,
                position_size_mode: e.target.value as BacktestRunConfig['position_size_mode'],
              }))}
            >
              <option value="equity_fraction">% of Equity</option>
              <option value="fixed_quantity">Fixed Units</option>
            </select>
          </Field>
        </div>

        <div style={s.row}>
          <Field label={btConfig.position_size_mode === 'equity_fraction' ? 'Fraction %' : 'Units'}>
            {btConfig.position_size_mode === 'equity_fraction' ? (
              <input
                data-testid="bt-fraction-input"
                style={s.input}
                type="number"
                min={1} max={100} step={1}
                value={Math.round((btConfig.equity_fraction ?? 0.95) * 100)}
                onChange={e => setBtConfig(c => ({
                  ...c,
                  equity_fraction: (parseFloat(e.target.value) || 95) / 100,
                }))}
              />
            ) : (
              <input
                data-testid="bt-units-input"
                style={s.input}
                type="number"
                min={1} step={1}
                value={btConfig.fixed_quantity}
                onChange={e => setBtConfig(c => ({
                  ...c,
                  fixed_quantity: parseFloat(e.target.value) || 1,
                }))}
              />
            )}
          </Field>

          <Field label="Commission">
            <select
              data-testid="bt-commission-select"
              style={s.input}
              value={btConfig.commission_mode}
              onChange={e => setBtConfig(c => ({
                ...c,
                commission_mode: e.target.value as BacktestRunConfig['commission_mode'],
                // Reset value when mode changes to avoid stale non-zero defaults
                commission_value: 0,
              }))}
            >
              <option value="none">None</option>
              <option value="percentage">% per trade</option>
              <option value="fixed">Fixed $</option>
            </select>
          </Field>
        </div>

        {/* Commission value — only shown when a mode is selected */}
        {btConfig.commission_mode !== 'none' && (
          <Field label={btConfig.commission_mode === 'percentage' ? 'Commission (%)' : 'Commission ($)'}>
            <input
              data-testid="bt-commission-value-input"
              style={s.input}
              type="number"
              min={0}
              step={btConfig.commission_mode === 'percentage' ? 0.001 : 0.01}
              value={btConfig.commission_value}
              onChange={e => setBtConfig(c => ({
                ...c,
                commission_value: parseFloat(e.target.value) || 0,
              }))}
            />
          </Field>
        )}

        {/* ── Status / error ── */}
        {phase === 'fetching' && (
          <div data-testid="bt-run-fetching" style={s.status}>
            Fetching market data…
          </div>
        )}
        {phase === 'running' && (
          <div data-testid="bt-run-running" style={s.status}>
            Running backtest{barCount != null ? ` on ${barCount.toLocaleString()} bars` : ''}…
          </div>
        )}
        {phase === 'success' && (
          <div data-testid="bt-run-success" style={{ ...s.status, color: '#48bb78' }}>
            Backtest complete. Opening report…
          </div>
        )}
        {error && (
          <div data-testid="bt-run-error" style={s.error}>{error}</div>
        )}

        {/* ── Actions ── */}
        <div style={s.actions}>
          <button
            data-testid="bt-run-submit"
            type="submit"
            style={{ ...s.btn, ...s.primaryBtn, opacity: busy ? 0.5 : 1 }}
            disabled={busy}
          >
            {phase === 'fetching' ? 'Fetching…' : phase === 'running' ? 'Running…' : '▶ Run Backtest'}
          </button>
          <button
            type="button"
            style={{ ...s.btn, ...s.secondaryBtn }}
            onClick={onCancel}
            disabled={busy}
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3, flex: 1 }}>
      <span style={{ fontSize: 10, color: '#4a5568', letterSpacing: '0.04em' }}>{label}</span>
      {children}
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  panel: {
    background:    '#0a0e1a',
    border:        '1px solid #1e2a3a',
    borderRadius:  6,
    padding:       '14px 16px',
    display:       'flex',
    flexDirection: 'column',
    gap:           10,
    flexShrink:    0,
  },
  header: {
    display:    'flex',
    alignItems: 'center',
    gap:        8,
  },
  title: {
    fontSize:      12,
    fontWeight:    700,
    color:         '#7eb8f7',
    fontFamily:    'monospace',
    letterSpacing: '0.04em',
    flexShrink:    0,
  },
  strategyLabel: {
    flex:         1,
    fontSize:     11,
    color:        '#4a6080',
    fontFamily:   'monospace',
    overflow:     'hidden',
    textOverflow: 'ellipsis',
    whiteSpace:   'nowrap',
  },
  cancelBtn: {
    background:   'transparent',
    border:       'none',
    color:        '#4a5568',
    cursor:       'pointer',
    fontFamily:   'monospace',
    fontSize:     14,
    padding:      '0 4px',
    flexShrink:   0,
  },
  blocked: {
    color:    '#4a5568',
    fontSize: 12,
    padding:  '8px 0',
  },
  form: {
    display:       'flex',
    flexDirection: 'column',
    gap:           8,
  },
  sectionLabel: {
    fontSize:      10,
    fontWeight:    600,
    color:         '#3a4a5a',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    fontFamily:    'monospace',
  },
  row: {
    display: 'flex',
    gap:     8,
  },
  input: {
    background:   '#0d1220',
    border:       '1px solid #1e2a3a',
    borderRadius: 3,
    color:        '#c0c8dc',
    fontFamily:   'monospace',
    fontSize:     11,
    padding:      '5px 7px',
    width:        '100%',
    boxSizing:    'border-box' as const,
  },
  status: {
    fontSize:   11,
    color:      '#7a8598',
    fontFamily: 'monospace',
  },
  error: {
    background:   '#1a0f0f',
    border:       '1px solid #3a1e1e',
    borderRadius: 3,
    color:        '#ef5350',
    fontSize:     11,
    padding:      '6px 8px',
    whiteSpace:   'pre-wrap' as const,
    fontFamily:   'monospace',
  },
  actions: {
    display:   'flex',
    gap:       8,
    marginTop: 4,
  },
  btn: {
    border:        '1px solid',
    borderRadius:  3,
    cursor:        'pointer',
    fontFamily:    'monospace',
    fontSize:      11,
    fontWeight:    600,
    letterSpacing: '0.04em',
    padding:       '6px 14px',
  },
  primaryBtn: {
    background:  '#0d1e2e',
    borderColor: '#1e3a5a',
    color:       '#7eb8f7',
  },
  secondaryBtn: {
    background:  'transparent',
    borderColor: '#2a2d3e',
    color:       '#4a5568',
  },
}
