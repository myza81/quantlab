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
  getForwardTestSession,
  runForwardTestCycle,
  pauseForwardTestSession,
  resumeForwardTestSession,
  terminateForwardTestSession,
  listForwardTestSignals,
  listForwardTestBars,
  promoteDraftToForwardTested,
} from '../api/forwardTests'
import { fetchCredentials } from '../api/credentials'
import { fetchDrafts } from '../api/drafts'
import type {
  ForwardTestSessionSummary,
  ForwardTestSessionDetail,
  ForwardTestCycleResult,
  ForwardTestSignal,
  ForwardTestBar,
  CreateForwardTestSessionRequest,
  ForwardTestPrefill,
} from '../types/forwardTesting'
import type { CredentialMetadata } from '../types/credentials'
import type { StrategyDraftData } from '../types/drafts'
import { computeGuidance, STAGE_LABELS } from '../lib/lifecycleGuidance'
import { EvidenceReadinessPanel } from './EvidenceReadinessPanel'
import { LifecycleGuidanceCard } from './LifecycleGuidanceCard'

// Lifecycle statuses that qualify a draft for forward testing
const ELIGIBLE_FT_STATUSES = new Set(['backtested', 'forward_tested', 'paper_tested', 'approved_for_live'])

const SESSION_STATE_MESSAGES: Record<string, string> = {
  pending:    'Session created. Activate to start collecting bars.',
  running:    'Session is active and ready for cycle execution.',
  paused:     'Session is paused. No bars are processed until resumed.',
  completed:  'Session has completed its evaluation period.',
  failed:     'Session encountered an unrecoverable error.',
  terminated: 'Session was manually terminated.',
}

function noSignalExplanation(session: ForwardTestSessionDetail, signals: ForwardTestSignal[]): string {
  if (signals.length > 0) return ''
  switch (session.status) {
    case 'pending':
      return 'No cycle has run yet. Activate the session to start collecting bars.'
    case 'paused':
      return 'Session is paused. Resume to continue processing bars.'
    case 'failed':
      return `Session failed: ${session.failure_reason ?? 'unknown error'}`
    case 'terminated':
      return 'This session was terminated. No further cycles will run.'
    case 'completed':
      return 'Session completed with no strategy conditions met.'
    default: { // running
      if (session.warmup_bars_processed < session.warmup_bars_required) {
        return `Collecting warmup bars: ${session.warmup_bars_processed} of ${session.warmup_bars_required} processed. Signals become eligible after warmup completes.`
      }
      if (session.signal_eligible_bars_processed === 0) {
        return 'Warmup complete. Run a cycle to evaluate strategy conditions.'
      }
      const n = session.signal_eligible_bars_processed
      return `${n} eligible bar${n === 1 ? '' : 's'} evaluated — no strategy conditions met.`
    }
  }
}

function ConfigRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
      <span style={{ color: '#718096', fontSize: 11, minWidth: 190, flexShrink: 0 }}>{label}</span>
      <span style={{ color: '#e2e8f0', fontSize: 11, fontFamily: mono ? 'monospace' : 'inherit', wordBreak: 'break-all' }}>{value}</span>
    </div>
  )
}

interface ForwardTestPanelProps {
  prefill?: ForwardTestPrefill | null
  onPrefillConsumed?: () => void
}

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
            {s.status === 'pending' ? 'Activate' : 'Process Next Bar'}
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
  initialValues = null,
}: {
  onCreated: (session: ForwardTestSessionDetail) => void
  onCancel: () => void
  initialValues?: ForwardTestPrefill | null
}) {
  const { logout, refreshUser } = useAuth()
  const [draftId,        setDraftId]        = useState(initialValues?.draft_id      ?? '')
  const [symbol,         setSymbol]         = useState(initialValues?.symbol        ?? 'AAPL')
  const [timeframe,      setTimeframe]      = useState(initialValues?.timeframe     ?? '1d')
  const [providerName,   setProviderName]   = useState(initialValues?.provider_name ?? 'yahoo')
  const [exchange,       setExchange]       = useState(initialValues?.exchange      ?? 'NASDAQ')
  const [assetClass,     setAssetClass]     = useState(initialValues?.asset_class   ?? 'equity')
  const [credentialId,   setCredentialId]   = useState('')
  const [busy,           setBusy]           = useState(false)
  const [error,          setError]          = useState<string | null>(null)

  // Picker state: credentials and eligible draft list loaded on mount
  const [credentials,    setCredentials]    = useState<CredentialMetadata[]>([])
  const [eligibleDrafts, setEligibleDrafts] = useState<StrategyDraftData[]>([])
  const [loadingMeta,    setLoadingMeta]    = useState(true)

  useEffect(() => {
    let cancelled = false
    async function loadMeta() {
      try {
        const credResp = await fetchCredentials()
        if (!cancelled) setCredentials(credResp.credentials)
        // Only fetch draft list when no draft is already pre-selected from context
        if (!initialValues?.draft_id) {
          const draftResp = await fetchDrafts()
          if (!cancelled) {
            setEligibleDrafts(
              draftResp.drafts.filter(d => ELIGIBLE_FT_STATUSES.has(d.lifecycle_status ?? ''))
            )
          }
        }
      } catch {
        // Non-fatal: pickers degrade gracefully; form still fully usable
      } finally {
        if (!cancelled) setLoadingMeta(false)
      }
    }
    loadMeta()
    return () => { cancelled = true }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Credentials filtered to the selected provider (case-insensitive)
  const filteredCredentials = providerName.trim()
    ? credentials.filter(c => c.provider_name.toLowerCase() === providerName.trim().toLowerCase())
    : credentials

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
    <form data-testid="ft-create-form" onSubmit={handleSubmit} style={s.form}>
      {initialValues && (
        <div data-testid="prefill-notice" style={s.prefillNotice}>
          Pre-filled from backtest context.
          Review <strong>exchange</strong> and <strong>asset class</strong> before submitting.
        </div>
      )}

      {/* Draft — read-only display when pre-selected, select picker or raw input otherwise */}
      <div style={s.formRow}>
        <label style={s.label}>Draft *</label>
        {initialValues?.draft_id ? (
          <div data-testid="ft-draft-display" style={s.draftDisplay}>
            <span style={s.draftName}>{initialValues.draft_name ?? draftId}</span>
            <span style={s.draftUuid}>{draftId.slice(0, 8)}…</span>
            {/* Hidden input preserves test-id compatibility and form value */}
            <input type="hidden" data-testid="ft-draft-id-input" value={draftId} />
          </div>
        ) : !loadingMeta && eligibleDrafts.length > 0 ? (
          <select
            data-testid="ft-draft-select"
            style={s.select}
            value={draftId}
            onChange={e => setDraftId(e.target.value)}
            required
          >
            <option value="">— select a backtested draft —</option>
            {eligibleDrafts.map(d => (
              <option key={d.draft_id} value={d.draft_id}>
                {d.display_name} [{d.lifecycle_status ?? 'unknown'}]
              </option>
            ))}
          </select>
        ) : (
          // Fallback: raw UUID input (shown during loading or when no eligible drafts found)
          <input
            data-testid="ft-draft-id-input"
            style={{ ...s.input, opacity: loadingMeta ? 0.6 : 1 }}
            value={draftId}
            onChange={e => setDraftId(e.target.value)}
            placeholder="UUID of a backtested draft"
            disabled={loadingMeta}
            required
          />
        )}
      </div>

      {/* Symbol */}
      <div style={s.formRow}>
        <label style={s.label}>Symbol *</label>
        <input data-testid="ft-symbol-input" style={s.input} value={symbol} onChange={e => setSymbol(e.target.value)} required />
      </div>

      {/* Timeframe */}
      <div style={s.formRow}>
        <label style={s.label}>Timeframe *</label>
        <input style={s.input} value={timeframe} onChange={e => setTimeframe(e.target.value)} placeholder="1d, 1h, 15m…" required />
      </div>

      {/* Market Data Source */}
      <div style={s.formRow}>
        <label style={s.label}>Market Data Source</label>
        <input style={s.input} value={providerName} onChange={e => setProviderName(e.target.value)} placeholder="yahoo" />
      </div>

      {/* Exchange */}
      <div style={s.formRow}>
        <label style={s.label}>Exchange</label>
        <input style={s.input} value={exchange} onChange={e => setExchange(e.target.value)} />
      </div>

      {/* Asset class */}
      <div style={s.formRow}>
        <label style={s.label}>Asset class</label>
        <input style={s.input} value={assetClass} onChange={e => setAssetClass(e.target.value)} />
      </div>

      {/* Credential picker — replaces raw UUID input */}
      <div style={s.formRow}>
        <label style={s.label}>Credential</label>
        {loadingMeta ? (
          <div style={s.metaLoading}>Loading…</div>
        ) : (
          <>
            <select
              data-testid="ft-credential-select"
              style={s.select}
              value={credentialId}
              onChange={e => setCredentialId(e.target.value)}
            >
              <option value="">None (optional)</option>
              {filteredCredentials.map(cred => (
                <option key={cred.credential_id} value={cred.credential_id}>
                  {cred.credential_label} · {cred.provider_name}
                  {!cred.active ? ' (inactive)' : ''}
                </option>
              ))}
            </select>
            {filteredCredentials.length === 0 && (
              <div data-testid="no-credentials-notice" style={s.noCredNotice}>
                {credentials.length === 0
                  ? 'No credentials saved. Leave blank if not required.'
                  : `No credentials for "${providerName || 'this provider'}". Leave blank if not required.`}
              </div>
            )}
          </>
        )}
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
// Session Operator View — R7
// ---------------------------------------------------------------------------

function SessionOperatorView({ sessionId, onBack }: { sessionId: string; onBack: () => void }) {
  const { logout, refreshUser } = useAuth()
  const [session,        setSession]        = useState<ForwardTestSessionDetail | null>(null)
  const [signals,        setSignals]        = useState<ForwardTestSignal[]>([])
  const [bars,           setBars]           = useState<ForwardTestBar[]>([])
  const [loading,        setLoading]        = useState(true)
  const [error,          setError]          = useState<string | null>(null)
  const [promotionState, setPromotionState] = useState<'idle' | 'promoting' | 'success' | 'error'>('idle')
  const [promotionError, setPromotionError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [det, sigs, barList] = await Promise.all([
          getForwardTestSession(sessionId),
          listForwardTestSignals(sessionId),
          listForwardTestBars(sessionId),
        ])
        if (!cancelled) {
          setSession(det)
          setSignals(sigs)
          setBars(barList)
          setLoading(false)
        }
      } catch (err) {
        if (cancelled) return
        if (isAuthError(err)) { logout(); return }
        if (isSubscriptionExpiredError(err)) { await refreshUser(); return }
        setError(err instanceof Error ? err.message : 'Failed to load session')
        setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [sessionId, logout, refreshUser])

  const explanation = session ? noSignalExplanation(session, signals) : null

  // Promotion eligibility — computed from session state
  const lifecycleAtActivation = session?.lifecycle_status_at_activation ?? null
  const hasEvidence = (session?.signal_eligible_bars_processed ?? 0) > 0
  // Show promotion panel when draft was backtested at session creation
  const showPromotionPanel = lifecycleAtActivation === 'backtested'
  // Show ineligible notice for drafts that were already forward_tested or beyond
  const alreadyForwardTested =
    lifecycleAtActivation != null &&
    !['draft', 'validated', 'backtested'].includes(lifecycleAtActivation)

  const ftGuidance = session ? computeGuidance({
    lifecycleStatus: session.lifecycle_status_at_activation,
    hasFtSession: true,
    hasFtEvidenceBars: session.signal_eligible_bars_processed > 0,
  }) : null

  async function handlePromote() {
    if (!session) return
    setPromotionState('promoting')
    setPromotionError(null)
    try {
      await promoteDraftToForwardTested(session.session_id, session.draft_id)
      setPromotionState('success')
    } catch (err) {
      setPromotionState('error')
      setPromotionError(err instanceof Error ? err.message : 'Promotion failed')
    }
  }

  return (
    <div style={s.panel}>
      {/* Header — always visible so existing navigation tests pass */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <button style={btnLink} onClick={onBack}>← Back</button>
        <span style={s.heading}>Signals for {sessionId.slice(0, 8)}…</span>
      </div>

      {loading && <div style={s.state}>Loading session…</div>}
      {error && <div style={s.error}>{error}</div>}

      {!loading && session && (
        <>
          {/* Session state messaging */}
          <div data-testid="session-state-banner" style={s.stateBanner}>
            <StatusBadge status={session.status} />
            <span data-testid="session-state-message" style={s.stateMessage}>
              {SESSION_STATE_MESSAGES[session.status] ?? session.status}
            </span>
          </div>

          {/* Lifecycle guidance */}
          {ftGuidance && (
            <LifecycleGuidanceCard
              currentStageLabel={ftGuidance.currentStageLabel}
              nextAction={ftGuidance.nextAction}
              whyItMatters={ftGuidance.whyItMatters}
              blockers={ftGuidance.blockers}
              navigateLocked={ftGuidance.navigateLocked}
            />
          )}

          {/* Configuration summary */}
          <section data-testid="config-panel" style={s.opsSection}>
            <div style={s.sectionHeading}>Configuration</div>
            <div>
              <ConfigRow label="Draft" value={session.strategy_snapshot.display_name} />
              <ConfigRow label="Symbol" value={session.symbol} />
              <ConfigRow label="Timeframe" value={session.timeframe} />
              <ConfigRow label="Market Data Source" value={session.provider_name ?? '—'} />
              <ConfigRow label="Exchange" value={session.exchange} />
              <ConfigRow label="Asset Class" value={session.asset_class} />
              <ConfigRow label="Strategy Stage at Start" value={STAGE_LABELS[session.lifecycle_status_at_activation] ?? session.lifecycle_status_at_activation} />
              <ConfigRow label="Strategy Version" value={session.strategy_snapshot.snapshot_hash.slice(0, 12) + '…'} />
            </div>
          </section>

          {/* Last cycle / metrics */}
          <section data-testid="cycle-panel" style={s.opsSection}>
            <div style={s.sectionHeading}>Cycle Metrics</div>
            <div>
              <ConfigRow
                label="Last Bar Processed"
                value={session.last_processed_bar_timestamp ? fmtTs(session.last_processed_bar_timestamp) : '—'}
              />
              <ConfigRow label="Total Bars Evaluated" value={String(session.bars_evaluated)} />
              <ConfigRow
                label="Warmup Progress"
                value={`${session.warmup_bars_processed} / ${session.warmup_bars_required} bars`}
              />
              <ConfigRow label="Live Bars Evaluated After Warmup" value={String(session.signal_eligible_bars_processed)} />
              <ConfigRow label="Signals Recorded" value={String(session.signals_recorded)} />
              {session.activation_timestamp && (
                <ConfigRow label="Activated At" value={fmtTs(session.activation_timestamp)} />
              )}
            </div>
          </section>

          {/* Lifecycle Promotion — forward_tested (Phase P1) */}
          {alreadyForwardTested ? (
            <div data-testid="ft-promotion-ineligible" style={s.ftPromotionIneligible}>
              This draft was already <strong>{lifecycleAtActivation}</strong> when this session
              was created. No further forward-test promotion is required.
            </div>
          ) : showPromotionPanel ? (
            <section data-testid="ft-promotion-panel" style={s.opsSection}>
              <div style={s.sectionHeading}>Advance Stage</div>
              <div data-testid="ft-evidence-panel">
                <EvidenceReadinessPanel
                  title="Promotion Evidence — Backtest Complete → Forward Test Complete"
                  items={[
                    {
                      label:       'Forward-Test Session Exists',
                      complete:    true,
                      explanation: 'A forward-test session is required to record live market behavior.',
                    },
                    {
                      label:       'Live Bars Evaluated After Warmup',
                      complete:    (session?.signal_eligible_bars_processed ?? 0) > 0,
                      explanation: 'At least one live market bar must be evaluated after the warmup period to establish behavior evidence.',
                    },
                  ]}
                />
              </div>
              {promotionState === 'success' ? (
                <div data-testid="ft-promotion-success" style={s.ftPromotionSuccess}>
                  ✓ Draft promoted to <strong>Forward Test Complete</strong>. Paper trading eligibility
                  can now be built on this strategy.
                </div>
              ) : !hasEvidence ? (
                <div data-testid="ft-promotion-no-evidence" style={s.ftPromotionNoEvidence}>
                  Run at least one complete forward-test cycle (warmup + signal-eligible bar)
                  before promotion.
                </div>
              ) : (
                <div>
                  <p style={{ fontSize: 11, color: '#a0aec0', marginBottom: 10 }}>
                    This session has evaluated {session!.signal_eligible_bars_processed} signal-eligible
                    bar{session!.signal_eligible_bars_processed === 1 ? '' : 's'}. You can now
                    promote the draft to <strong style={{ color: '#7eb8f7' }}>Forward Test Complete</strong>.
                  </p>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' as const }}>
                    <button
                      data-testid="promote-to-forward-tested-btn"
                      style={{
                        ...s.ftPromoteBtn,
                        opacity: promotionState === 'promoting' ? 0.5 : 1,
                        cursor:  promotionState === 'promoting' ? 'not-allowed' : 'pointer',
                      }}
                      disabled={promotionState === 'promoting'}
                      onClick={handlePromote}
                    >
                      {promotionState === 'promoting' ? 'Promoting…' : 'Promote to Forward-Tested'}
                    </button>
                    {promotionState === 'error' && promotionError && (
                      <span data-testid="ft-promotion-error" style={s.ftPromotionErrorText}>
                        {promotionError}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </section>
          ) : null}

          {/* Provenance */}
          <section data-testid="provenance-panel" style={s.opsSection}>
            <div style={s.sectionHeading}>Provenance</div>
            <div>
              <ConfigRow label="Session ID" value={session.session_id} mono />
              <ConfigRow label="Draft ID" value={session.draft_id} mono />
              <ConfigRow label="Created" value={fmtTs(session.created_at)} />
              <ConfigRow label="Snapshot Hash" value={session.strategy_snapshot.snapshot_hash} mono />
            </div>
          </section>

          {/* Failure information */}
          {session.failure_reason && (
            <div data-testid="failure-panel" style={s.failureBanner}>
              <strong>Failure: </strong>{session.failure_reason}
              {session.error_category && <span style={{ color: '#718096' }}> · {session.error_category}</span>}
            </div>
          )}

          {/* Signal trace */}
          <section data-testid="signals-panel" style={s.opsSection}>
            <div style={s.sectionHeading}>Signals</div>
            {signals.length === 0 ? (
              <div data-testid="no-signal-explanation" style={s.noSignalExplanation}>
                {explanation}
              </div>
            ) : (
              <div style={s.tableWrap}>
                <table style={s.table}>
                  <thead>
                    <tr>
                      {['Bar Time', 'Signal', 'Rule', 'Close', 'Warmup OK', 'Features', 'Recorded'].map(h => (
                        <th key={h} style={th}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {signals.map(sig => (
                      <tr key={sig.signal_id} style={{ borderBottom: '1px solid #2d3748' }}>
                        <td style={td}>{fmtTs(sig.bar_timestamp)}</td>
                        <td style={td}>
                          <span style={{ color: sig.signal_direction.startsWith('entry') ? '#66bb6a' : '#ef5350' }}>
                            {sig.signal_direction}
                          </span>
                        </td>
                        <td style={td}>{sig.rule_id}</td>
                        <td style={td}>{sig.bar_close.toFixed(2)}</td>
                        <td style={td}>{sig.warmup_satisfied ? '✓' : '✗'}</td>
                        <td style={td}>
                          {Object.keys(sig.feature_values_at_signal).length > 0
                            ? Object.entries(sig.feature_values_at_signal)
                                .map(([k, v]) => `${k}: ${v.toFixed(4)}`)
                                .join(', ')
                            : '—'}
                        </td>
                        <td style={td}>{fmtTs(sig.signal_timestamp)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Recent bars */}
          <section data-testid="bars-panel" style={s.opsSection}>
            <div style={s.sectionHeading}>Recent Bars</div>
            {bars.length === 0 ? (
              <div style={s.state}>No bars have been processed yet.</div>
            ) : (
              <div style={s.tableWrap}>
                <table style={s.table}>
                  <thead>
                    <tr>
                      {['#', 'Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume', 'Type'].map(h => (
                        <th key={h} style={th}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[...bars].reverse().slice(0, 50).map(bar => (
                      <tr key={bar.bar_index} style={{ borderBottom: '1px solid #2d3748' }}>
                        <td style={td}>{bar.bar_index}</td>
                        <td style={td}>{fmtTs(bar.bar_timestamp)}</td>
                        <td style={td}>{bar.open.toFixed(2)}</td>
                        <td style={td}>{bar.high.toFixed(2)}</td>
                        <td style={td}>{bar.low.toFixed(2)}</td>
                        <td style={td}>{bar.close.toFixed(2)}</td>
                        <td style={td}>{bar.volume.toLocaleString()}</td>
                        <td style={td}>
                          <span style={{ color: bar.is_warmup_bar ? '#ffa726' : '#66bb6a', fontSize: 10, fontWeight: 600 }}>
                            {bar.is_warmup_bar ? 'WARMUP' : 'SIGNAL'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export function ForwardTestPanel({
  prefill = null,
  onPrefillConsumed,
}: ForwardTestPanelProps = {}) {
  const { logout, refreshUser } = useAuth()
  const [sessions,     setSessions]     = useState<ForwardTestSessionSummary[]>([])
  const [loading,      setLoading]      = useState(true)
  const [error,        setError]        = useState<string | null>(null)
  const [showCreate,   setShowCreate]   = useState(prefill != null)
  const [busyId,       setBusyId]       = useState<string | null>(null)
  const [cycleResult,  setCycleResult]  = useState<ForwardTestCycleResult | null>(null)
  const [detailView,   setDetailView]   = useState<string | null>(null)

  // If the parent sets a prefill while the panel is already mounted (e.g., user was
  // already on the Forward Test tab), open the create form automatically.
  useEffect(() => {
    if (prefill != null) setShowCreate(true)
  }, [prefill])

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

  if (detailView) {
    return <SessionOperatorView sessionId={detailView} onBack={() => setDetailView(null)} />
  }

  if (showCreate) {
    return (
      <div style={s.panel}>
        <div style={s.heading}>
          New Forward Test Session
          {prefill?.draft_name && (
            <span style={{ fontSize: 12, color: '#718096', marginLeft: 8 }}>
              — {prefill.draft_name}
            </span>
          )}
        </div>
        <CreateForm
          initialValues={prefill}
          onCreated={(session) => {
            setSessions(prev => [session, ...prev])
            setShowCreate(false)
            onPrefillConsumed?.()
          }}
          onCancel={() => {
            setShowCreate(false)
            onPrefillConsumed?.()
          }}
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
                  onSelect={() => setDetailView(session.session_id)}
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
  prefillNotice: {
    background:   '#1a1e2a',
    border:       '1px solid #2a3a4a',
    borderRadius: 4,
    padding:      '6px 10px',
    fontSize:     11,
    color:        '#63b3ed',
    marginBottom: 10,
  } as React.CSSProperties,
  select: {
    background:  '#2d3748',
    border:      '1px solid #4a5568',
    borderRadius: 4,
    padding:     '6px 10px',
    color:       '#e2e8f0',
    fontFamily:  'monospace',
    fontSize:    13,
  } as React.CSSProperties,
  draftDisplay: {
    display:     'flex',
    alignItems:  'center',
    gap:         8,
    background:  '#2d3748',
    border:      '1px solid #4a5568',
    borderRadius: 4,
    padding:     '6px 10px',
  } as React.CSSProperties,
  draftName: {
    color:      '#e2e8f0',
    fontWeight: 600,
    fontSize:   13,
  } as React.CSSProperties,
  draftUuid: {
    color:    '#718096',
    fontSize: 11,
  } as React.CSSProperties,
  noCredNotice: {
    color:     '#a0aec0',
    fontSize:  11,
    marginTop: 4,
    fontStyle: 'italic',
  } as React.CSSProperties,
  metaLoading: {
    color:   '#718096',
    fontSize: 12,
    padding: '6px 0',
  } as React.CSSProperties,
  // R7 operator view styles
  opsSection: {
    background:   '#1e2533',
    border:       '1px solid #2d3748',
    borderRadius: 6,
    padding:      '14px 16px',
    marginBottom: 12,
  } as React.CSSProperties,
  sectionHeading: {
    fontSize:       11,
    fontWeight:     600,
    color:          '#718096',
    textTransform:  'uppercase' as const,
    letterSpacing:  '0.08em',
    marginBottom:   10,
  } as React.CSSProperties,
  stateBanner: {
    display:      'flex',
    alignItems:   'center',
    gap:          10,
    marginBottom: 12,
    padding:      '8px 0',
  } as React.CSSProperties,
  stateMessage: {
    color:    '#a0aec0',
    fontSize: 12,
  } as React.CSSProperties,
  noSignalExplanation: {
    color:      '#a0aec0',
    fontSize:   12,
    lineHeight: 1.6,
    padding:    '8px 0',
  } as React.CSSProperties,
  failureBanner: {
    color:        '#ef5350',
    background:   '#2d1515',
    border:       '1px solid #ef535033',
    borderRadius: 6,
    padding:      '10px 14px',
    marginBottom: 12,
    fontSize:     12,
  } as React.CSSProperties,
  ftPromotionIneligible: {
    fontSize:     11,
    color:        '#4a5568',
    background:   '#0a0a14',
    border:       '1px solid #1a1a28',
    borderRadius: 6,
    padding:      '8px 12px',
    marginBottom: 12,
  } as React.CSSProperties,
  ftPromotionNoEvidence: {
    fontSize:     12,
    color:        '#8a7040',
    background:   '#0e0a00',
    border:       '1px solid #3a2800',
    borderRadius: 6,
    padding:      '10px 14px',
  } as React.CSSProperties,
  ftPromotionSuccess: {
    fontSize:     12,
    color:        '#66bb6a',
    background:   '#0a1a0a',
    border:       '1px solid #1a4a1a',
    borderRadius: 6,
    padding:      '10px 14px',
  } as React.CSSProperties,
  ftPromoteBtn: {
    background:   '#1a3a2a',
    border:       '1px solid #2a6a4a',
    borderRadius: 5,
    color:        '#66bb6a',
    fontFamily:   'monospace',
    fontSize:     11,
    padding:      '6px 14px',
    cursor:       'pointer',
    whiteSpace:   'nowrap' as const,
  } as React.CSSProperties,
  ftPromotionErrorText: {
    fontSize: 11,
    color:    '#ef5350',
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
