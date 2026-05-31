/**
 * ForwardTestPanel — Phase 4C.5.
 *
 * MVP forward testing UI:
 *   - Create a new forward test session from a draft
 *   - List all sessions with status badges
 *   - Run one cycle manually (no auto-polling, no setInterval)
 *   - Pause / Resume / Terminate session
 *   - Drill into a session to view signal history
 *
 * No scheduler. No automatic polling. Every cycle is triggered explicitly.
 */
import { useEffect, useState } from 'react'
import { isAuthError, isSubscriptionExpiredError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import {
  createForwardTestSession,
  listForwardTestSessions,
  runForwardTestCycle,
  pauseForwardTestSession,
  resumeForwardTestSession,
  terminateForwardTestSession,
  listForwardTestSignals,
} from '../api/forwardTests'
import type {
  ForwardTestSessionSummary,
  ForwardTestSessionDetail,
  ForwardTestCycleResult,
  ForwardTestSignal,
  CreateForwardTestSessionRequest,
} from '../types/forwardTesting'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtTs(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('en-US', {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}

const STATUS_COLORS: Record<string, string> = {
  pending:    '#ffa726',
  running:    '#66bb6a',
  paused:     '#42a5f5',
  completed:  '#9e9e9e',
  failed:     '#ef5350',
  terminated: '#757575',
}

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? '#4a5568'
  return (
    <span style={{
      display: 'inline-block',
      padding: '1px 7px',
      borderRadius: 10,
      fontSize: 11,
      fontWeight: 600,
      background: color + '22',
      color,
      border: `1px solid ${color}66`,
      textTransform: 'uppercase',
    }}>
      {status}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Session list row
// ---------------------------------------------------------------------------

function SessionRow({
  session,
  onSelect,
  onRunCycle,
  onPause,
  onResume,
  onTerminate,
  busy,
}: {
  session: ForwardTestSessionSummary
  onSelect: () => void
  onRunCycle: () => void
  onPause: () => void
  onResume: () => void
  onTerminate: () => void
  busy: boolean
}) {
  const s = session
  const isTerminal = ['completed', 'failed', 'terminated'].includes(s.status)
  const canRunCycle = s.status === 'pending' || s.status === 'running'
  const canPause = s.status === 'running'
  const canResume = s.status === 'paused'
  const canTerminate = !isTerminal

  return (
    <tr style={{ borderBottom: '1px solid #2d3748' }}>
      <td style={td}>
        <button
          style={{ ...btnLink, fontSize: 11 }}
          onClick={onSelect}
          title={s.session_id}
        >
          {s.session_id.slice(0, 8)}…
        </button>
      </td>
      <td style={td}><StatusBadge status={s.status} /></td>
      <td style={td}>{s.strategy_snapshot.display_name}</td>
      <td style={td}>{s.symbol} / {s.timeframe}</td>
      <td style={td}>{s.bars_evaluated}</td>
      <td style={td}>{s.signals_recorded}</td>
      <td style={td}>{fmtTs(s.last_processed_bar_timestamp)}</td>
      <td style={{ ...td, whiteSpace: 'nowrap' }}>
        {canRunCycle && (
          <button style={btnSm} onClick={onRunCycle} disabled={busy}>
            {s.status === 'pending' ? 'Activate' : 'Run Cycle'}
          </button>
        )}
        {canPause && (
          <button style={{ ...btnSm, marginLeft: 4 }} onClick={onPause} disabled={busy}>
            Pause
          </button>
        )}
        {canResume && (
          <button style={{ ...btnSm, marginLeft: 4 }} onClick={onResume} disabled={busy}>
            Resume
          </button>
        )}
        {canTerminate && (
          <button
            style={{ ...btnSm, marginLeft: 4, color: '#ef5350', borderColor: '#ef535066' }}
            onClick={onTerminate}
            disabled={busy}
          >
            Terminate
          </button>
        )}
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Create form
// ---------------------------------------------------------------------------

function CreateForm({
  onCreated,
  onCancel,
}: {
  onCreated: (session: ForwardTestSessionDetail) => void
  onCancel: () => void
}) {
  const { logout, refreshUser } = useAuth()
  const [draftId,      setDraftId]      = useState('')
  const [symbol,       setSymbol]       = useState('AAPL')
  const [timeframe,    setTimeframe]    = useState('1d')
  const [providerName, setProviderName] = useState('yahoo')
  const [exchange,     setExchange]     = useState('NASDAQ')
  const [assetClass,   setAssetClass]   = useState('equity')
  const [credentialId, setCredentialId] = useState('')
  const [busy,         setBusy]         = useState(false)
  const [error,        setError]        = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    const req: CreateForwardTestSessionRequest = {
      draft_id:      draftId.trim(),
      symbol:        symbol.trim().toUpperCase(),
      timeframe:     timeframe.trim(),
      source_mode:   'provider',
      provider_name: providerName.trim() || null,
      exchange:      exchange.trim() || 'NASDAQ',
      asset_class:   assetClass.trim() || 'equity',
      credential_id: credentialId.trim() || null,
    }
    try {
      const session = await createForwardTestSession(req)
      onCreated(session)
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      if (isSubscriptionExpiredError(err)) { await refreshUser(); return }
      setError(err instanceof Error ? err.message : 'Failed to create session')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} style={s.form}>
      <div style={s.formRow}>
        <label style={s.label}>Draft ID *</label>
        <input
          style={s.input}
          value={draftId}
          onChange={e => setDraftId(e.target.value)}
          placeholder="UUID of a backtested draft"
          required
        />
      </div>
      <div style={s.formRow}>
        <label style={s.label}>Symbol *</label>
        <input style={s.input} value={symbol} onChange={e => setSymbol(e.target.value)} required />
      </div>
      <div style={s.formRow}>
        <label style={s.label}>Timeframe *</label>
        <input style={s.input} value={timeframe} onChange={e => setTimeframe(e.target.value)} placeholder="1d, 1h, 15m…" required />
      </div>
      <div style={s.formRow}>
        <label style={s.label}>Provider</label>
        <input style={s.input} value={providerName} onChange={e => setProviderName(e.target.value)} placeholder="yahoo" />
      </div>
      <div style={s.formRow}>
        <label style={s.label}>Exchange</label>
        <input style={s.input} value={exchange} onChange={e => setExchange(e.target.value)} />
      </div>
      <div style={s.formRow}>
        <label style={s.label}>Asset class</label>
        <input style={s.input} value={assetClass} onChange={e => setAssetClass(e.target.value)} />
      </div>
      <div style={s.formRow}>
        <label style={s.label}>Credential ID</label>
        <input style={s.input} value={credentialId} onChange={e => setCredentialId(e.target.value)} placeholder="Optional vault credential_id" />
      </div>
      {error && <div style={s.error}>{error}</div>}
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button type="submit" style={s.btnPrimary} disabled={busy}>
          {busy ? 'Creating…' : 'Create Session'}
        </button>
        <button type="button" style={s.btnSecondary} onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Signal detail view
// ---------------------------------------------------------------------------

function SignalList({ sessionId, onBack }: { sessionId: string; onBack: () => void }) {
  const { logout, refreshUser } = useAuth()
  const [signals, setSignals] = useState<ForwardTestSignal[]>([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const data = await listForwardTestSignals(sessionId)
        if (!cancelled) { setSignals(data); setLoading(false) }
      } catch (err) {
        if (cancelled) return
        if (isAuthError(err)) { logout(); return }
        if (isSubscriptionExpiredError(err)) { await refreshUser(); return }
        setError(err instanceof Error ? err.message : 'Failed to load signals')
        setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [sessionId, logout, refreshUser])

  return (
    <div style={s.panel}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <button style={btnLink} onClick={onBack}>← Back</button>
        <span style={s.heading}>Signals for {sessionId.slice(0, 8)}…</span>
      </div>
      {loading && <div style={s.state}>Loading signals…</div>}
      {error && <div style={s.error}>{error}</div>}
      {!loading && signals.length === 0 && (
        <div style={s.state}>No signals recorded yet.</div>
      )}
      {signals.length > 0 && (
        <div style={s.tableWrap}>
          <table style={s.table}>
            <thead>
              <tr>
                {['Bar time', 'Direction', 'Rule', 'Close', 'Warmup OK', 'Signal time'].map(h => (
                  <th key={h} style={th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {signals.map(sig => (
                <tr key={sig.signal_id} style={{ borderBottom: '1px solid #2d3748' }}>
                  <td style={td}>{fmtTs(sig.bar_timestamp)}</td>
                  <td style={td}><span style={{ color: sig.signal_direction.startsWith('entry') ? '#66bb6a' : '#ef5350' }}>{sig.signal_direction}</span></td>
                  <td style={td}>{sig.rule_id}</td>
                  <td style={td}>{sig.bar_close.toFixed(2)}</td>
                  <td style={td}>{sig.warmup_satisfied ? '✓' : '✗'}</td>
                  <td style={td}>{fmtTs(sig.signal_timestamp)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export function ForwardTestPanel() {
  const { logout, refreshUser } = useAuth()
  const [sessions,     setSessions]     = useState<ForwardTestSessionSummary[]>([])
  const [loading,      setLoading]      = useState(true)
  const [error,        setError]        = useState<string | null>(null)
  const [showCreate,   setShowCreate]   = useState(false)
  const [busyId,       setBusyId]       = useState<string | null>(null)
  const [cycleResult,  setCycleResult]  = useState<ForwardTestCycleResult | null>(null)
  const [signalView,   setSignalView]   = useState<string | null>(null)

  async function loadSessions() {
    setError(null)
    try {
      const data = await listForwardTestSessions()
      setSessions(data)
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      if (isSubscriptionExpiredError(err)) { await refreshUser(); return }
      setError(err instanceof Error ? err.message : 'Failed to load sessions')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    listForwardTestSessions()
      .then(data => { if (!cancelled) { setSessions(data); setLoading(false) } })
      .catch(err => {
        if (cancelled) return
        if (isAuthError(err)) { logout(); return }
        setError(err instanceof Error ? err.message : 'Failed to load sessions')
        setLoading(false)
      })
    return () => { cancelled = true }
  }, [logout]) // eslint-disable-line react-hooks/exhaustive-deps

  function refreshSession(updated: ForwardTestSessionSummary) {
    setSessions(prev => prev.map(s => s.session_id === updated.session_id ? updated : s))
  }

  async function handleRunCycle(sessionId: string) {
    setBusyId(sessionId)
    setCycleResult(null)
    try {
      const result = await runForwardTestCycle(sessionId)
      setCycleResult(result)
      // Refresh the single session in the list
      await loadSessions()
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      if (isSubscriptionExpiredError(err)) { await refreshUser(); return }
      setError(err instanceof Error ? err.message : 'Cycle failed')
    } finally {
      setBusyId(null)
    }
  }

  async function handlePause(sessionId: string) {
    setBusyId(sessionId)
    try {
      const updated = await pauseForwardTestSession(sessionId)
      refreshSession(updated)
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setError(err instanceof Error ? err.message : 'Pause failed')
    } finally {
      setBusyId(null)
    }
  }

  async function handleResume(sessionId: string) {
    setBusyId(sessionId)
    try {
      const updated = await resumeForwardTestSession(sessionId)
      refreshSession(updated)
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setError(err instanceof Error ? err.message : 'Resume failed')
    } finally {
      setBusyId(null)
    }
  }

  async function handleTerminate(sessionId: string) {
    if (!window.confirm('Terminate this session? This cannot be undone.')) return
    setBusyId(sessionId)
    try {
      const updated = await terminateForwardTestSession(sessionId)
      refreshSession(updated)
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setError(err instanceof Error ? err.message : 'Terminate failed')
    } finally {
      setBusyId(null)
    }
  }

  if (signalView) {
    return <SignalList sessionId={signalView} onBack={() => setSignalView(null)} />
  }

  if (showCreate) {
    return (
      <div style={s.panel}>
        <div style={s.heading}>New Forward Test Session</div>
        <CreateForm
          onCreated={(session) => {
            setSessions(prev => [session, ...prev])
            setShowCreate(false)
          }}
          onCancel={() => setShowCreate(false)}
        />
      </div>
    )
  }

  return (
    <div style={s.panel}>
      <div style={s.topBar}>
        <span style={s.heading}>Forward Testing</span>
        <button style={s.btnPrimary} onClick={() => setShowCreate(true)}>
          + New Session
        </button>
      </div>

      {error && (
        <div style={s.error}>
          {error}
          <button style={{ ...btnLink, marginLeft: 8, color: '#4a5568' }} onClick={() => setError(null)}>
            ×
          </button>
        </div>
      )}

      {cycleResult && (
        <div style={s.cycleBox}>
          <strong>Last cycle result:</strong>{' '}
          {cycleResult.activated ? 'Activated' : 'Polled'} ·{' '}
          bars={cycleResult.bars_processed} ·{' '}
          signals={cycleResult.signals_generated} ·{' '}
          {cycleResult.gap_detected ? '⚠ gap detected' : ''}{' '}
          {cycleResult.provider_failure ? '⚠ provider failure' : ''}{' '}
          {cycleResult.message ? `· ${cycleResult.message}` : ''}
          <button style={{ ...btnLink, marginLeft: 8, fontSize: 11, color: '#4a5568' }} onClick={() => setCycleResult(null)}>
            ×
          </button>
        </div>
      )}

      {loading && <div style={s.state}>Loading sessions…</div>}
      {!loading && sessions.length === 0 && (
        <div style={s.state}>No forward test sessions yet. Create one to get started.</div>
      )}
      {!loading && sessions.length > 0 && (
        <div style={s.tableWrap}>
          <table style={s.table}>
            <thead>
              <tr>
                {['Session', 'Status', 'Strategy', 'Symbol/TF', 'Bars', 'Signals', 'Last Bar', 'Actions'].map(h => (
                  <th key={h} style={th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sessions.map(session => (
                <SessionRow
                  key={session.session_id}
                  session={session}
                  onSelect={() => setSignalView(session.session_id)}
                  onRunCycle={() => handleRunCycle(session.session_id)}
                  onPause={() => handlePause(session.session_id)}
                  onResume={() => handleResume(session.session_id)}
                  onTerminate={() => handleTerminate(session.session_id)}
                  busy={busyId === session.session_id}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const s = {
  panel: {
    padding: '24px 28px',
    color: '#e2e8f0',
    fontFamily: 'monospace',
    fontSize: 13,
    background: '#1a202c',
    minHeight: '100%',
  } as React.CSSProperties,
  topBar: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
  } as React.CSSProperties,
  heading: {
    fontSize: 16,
    fontWeight: 600,
    color: '#e2e8f0',
  } as React.CSSProperties,
  state: {
    color: '#718096',
    padding: '24px 0',
  } as React.CSSProperties,
  error: {
    color: '#ef5350',
    background: '#2d1515',
    border: '1px solid #ef535033',
    borderRadius: 6,
    padding: '8px 12px',
    marginBottom: 12,
    display: 'flex',
    alignItems: 'center',
  } as React.CSSProperties,
  cycleBox: {
    color: '#a0aec0',
    background: '#2d3748',
    border: '1px solid #4a5568',
    borderRadius: 6,
    padding: '8px 12px',
    marginBottom: 12,
    display: 'flex',
    alignItems: 'center',
    flexWrap: 'wrap' as const,
    gap: 4,
  } as React.CSSProperties,
  tableWrap: {
    overflowX: 'auto' as const,
  } as React.CSSProperties,
  table: {
    width: '100%',
    borderCollapse: 'collapse' as const,
    fontSize: 12,
  } as React.CSSProperties,
  form: {
    maxWidth: 500,
    marginTop: 16,
  } as React.CSSProperties,
  formRow: {
    display: 'flex',
    flexDirection: 'column' as const,
    marginBottom: 10,
  } as React.CSSProperties,
  label: {
    fontSize: 11,
    color: '#718096',
    marginBottom: 4,
  } as React.CSSProperties,
  input: {
    background: '#2d3748',
    border: '1px solid #4a5568',
    borderRadius: 4,
    padding: '6px 10px',
    color: '#e2e8f0',
    fontFamily: 'monospace',
    fontSize: 13,
  } as React.CSSProperties,
  btnPrimary: {
    background: '#3182ce',
    color: '#fff',
    border: 'none',
    borderRadius: 5,
    padding: '6px 14px',
    cursor: 'pointer',
    fontSize: 12,
    fontFamily: 'monospace',
  } as React.CSSProperties,
  btnSecondary: {
    background: 'transparent',
    color: '#a0aec0',
    border: '1px solid #4a5568',
    borderRadius: 5,
    padding: '6px 14px',
    cursor: 'pointer',
    fontSize: 12,
    fontFamily: 'monospace',
  } as React.CSSProperties,
}

const td: React.CSSProperties = {
  padding: '7px 10px',
  color: '#cbd5e0',
  verticalAlign: 'middle',
}

const th: React.CSSProperties = {
  padding: '8px 10px',
  color: '#718096',
  textAlign: 'left',
  borderBottom: '1px solid #2d3748',
  fontSize: 11,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
}

const btnSm: React.CSSProperties = {
  background: 'transparent',
  color: '#a0aec0',
  border: '1px solid #4a5568',
  borderRadius: 4,
  padding: '2px 8px',
  cursor: 'pointer',
  fontSize: 11,
  fontFamily: 'monospace',
}

const btnLink: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: '#63b3ed',
  cursor: 'pointer',
  fontSize: 13,
  padding: 0,
  fontFamily: 'monospace',
}
