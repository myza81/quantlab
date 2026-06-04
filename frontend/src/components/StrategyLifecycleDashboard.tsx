/**
 * StrategyLifecycleDashboard — Phase UX-2.
 *
 * Central command view for strategy lifecycle progression.
 * Shows: lifecycle stage track, current stage, next recommended action,
 * evidence summary per stage, blockers, quick navigation, technical details.
 *
 * Data sources:
 *   GET /drafts                  — all owned drafts (for picker)
 *   GET /backtests/runs          — filter by draft_id client-side
 *   GET /forward-tests           — filter by strategy_snapshot.draft_id
 *   GET /paper-trading/sessions  — filter by strategy_snapshot.draft_id
 *
 * Frontend displays. Backend decides. No lifecycle logic duplicated here.
 * No strategy_json in any response. No broker integration.
 */
import { useEffect, useState } from 'react'
import { fetchDrafts } from '../api/drafts'
import { listBacktestRuns } from '../api/backtestRuns'
import { listForwardTestSessions } from '../api/forwardTests'
import { listPaperTradingSessions } from '../api/paperTrading'
import { computeGuidance, STAGE_LABELS } from '../lib/lifecycleGuidance'
import type { NavigateTarget } from '../lib/lifecycleGuidance'
import { EvidenceReadinessPanel } from './EvidenceReadinessPanel'
import type { EvidenceItem } from './EvidenceReadinessPanel'
import type { StrategyDraftData } from '../types/drafts'
import type { BacktestRunListItem } from '../types/backtestRuns'
import type { ForwardTestSessionSummary } from '../types/forwardTesting'
import type { PaperTradingSessionSummary } from '../types/paperTrading'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Props {
  onNavigateToComposer: () => void
  onNavigateToHistory:  () => void
  onNavigateToForwardTest: () => void
  onNavigateToPaperTrading: () => void
}

type StageState = 'complete' | 'current' | 'locked'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const LIFECYCLE_STAGES: { key: string; label: string }[] = [
  { key: 'draft',            label: STAGE_LABELS.draft },
  { key: 'validated',        label: STAGE_LABELS.validated },
  { key: 'backtested',       label: STAGE_LABELS.backtested },
  { key: 'forward_tested',   label: STAGE_LABELS.forward_tested },
  { key: 'paper_tested',     label: STAGE_LABELS.paper_tested },
  { key: 'approved_for_live',label: STAGE_LABELS.approved_for_live },
]

const STAGE_KEYS = LIFECYCLE_STAGES.map(s => s.key)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function stageIndex(status: string): number {
  return STAGE_KEYS.indexOf(status)
}

function getStageState(stageKey: string, currentStatus: string): StageState {
  const si = stageIndex(stageKey)
  const ci = stageIndex(currentStatus)
  if (si < ci) return 'complete'
  if (si === ci) return 'current'
  return 'locked'
}

function filterBtRuns(runs: BacktestRunListItem[], draftId: string): BacktestRunListItem[] {
  return runs.filter(r => r.draft_id === draftId)
}

function filterFtSessions(sessions: ForwardTestSessionSummary[], draftId: string): ForwardTestSessionSummary[] {
  return sessions.filter(s => s.strategy_snapshot.draft_id === draftId)
}

function filterPtSessions(sessions: PaperTradingSessionSummary[], draftId: string): PaperTradingSessionSummary[] {
  return sessions.filter(s => s.strategy_snapshot.draft_id === draftId)
}

function resolveNav(
  target: NavigateTarget | null,
  nav: Pick<Props, 'onNavigateToComposer' | 'onNavigateToHistory' | 'onNavigateToForwardTest' | 'onNavigateToPaperTrading'>,
): (() => void) | null {
  switch (target) {
    case 'composer':      return nav.onNavigateToComposer
    case 'history':       return nav.onNavigateToHistory
    case 'forward-test':  return nav.onNavigateToForwardTest
    case 'paper-trading': return nav.onNavigateToPaperTrading
    default:              return null
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StageNode({ stageKey, label, state }: { stageKey: string; label: string; state: StageState }) {
  const color  = state === 'complete' ? '#48bb78' : state === 'current' ? '#26a69a' : '#4a5568'
  const filled = state === 'complete' || state === 'current'
  return (
    <div
      data-testid={`lcd-stage-${stageKey}`}
      data-state={state}
      style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, minWidth: 80 }}
    >
      <div style={{
        width: 16, height: 16, borderRadius: '50%',
        background: filled ? color : 'transparent',
        border: `2px solid ${color}`,
      }} />
      <div style={{ fontSize: 10, color, textAlign: 'center', fontWeight: state === 'current' ? 600 : 400 }}>
        {label}
      </div>
    </div>
  )
}

function EvidenceSection({ title, testId, children }: { title: string; testId: string; children: React.ReactNode }) {
  return (
    <div data-testid={testId} style={{ flex: '1 1 200px', background: '#0d1117', border: '1px solid #21262d', borderRadius: 6, padding: '10px 12px' }}>
      <div style={{ fontSize: 10, color: '#718096', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
        {title}
      </div>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function StrategyLifecycleDashboard({ onNavigateToComposer, onNavigateToHistory, onNavigateToForwardTest, onNavigateToPaperTrading }: Props) {
  const [drafts,       setDrafts]       = useState<StrategyDraftData[]>([])
  const [selectedId,   setSelectedId]   = useState<string | null>(null)
  const [btRuns,       setBtRuns]       = useState<BacktestRunListItem[]>([])
  const [ftSessions,   setFtSessions]   = useState<ForwardTestSessionSummary[]>([])
  const [ptSessions,   setPtSessions]   = useState<PaperTradingSessionSummary[]>([])
  const [loading,      setLoading]      = useState(true)
  const [error,        setError]        = useState<string | null>(null)
  const [techExpanded, setTechExpanded] = useState(false)

  // Load drafts on mount
  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchDrafts()
      .then(res => {
        setDrafts(res.drafts)
        if (res.drafts.length > 0 && selectedId === null) {
          setSelectedId(res.drafts[0].draft_id)
        }
      })
      .catch(e => setError(e instanceof Error ? e.message : 'Failed to load drafts'))
      .finally(() => setLoading(false))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Load evidence data when a draft is selected
  useEffect(() => {
    if (!selectedId) return
    Promise.allSettled([
      listBacktestRuns(),
      listForwardTestSessions(),
      listPaperTradingSessions(),
    ]).then(([btResult, ftResult, ptResult]) => {
      if (btResult.status === 'fulfilled') setBtRuns(btResult.value)
      if (ftResult.status === 'fulfilled') setFtSessions(ftResult.value)
      if (ptResult.status === 'fulfilled') setPtSessions(ptResult.value)
    })
  }, [selectedId])

  // Derived
  const selectedDraft   = drafts.find(d => d.draft_id === selectedId) ?? null
  const draftBtRuns     = selectedDraft ? filterBtRuns(btRuns, selectedDraft.draft_id) : []
  const draftFtSessions = selectedDraft ? filterFtSessions(ftSessions, selectedDraft.draft_id) : []
  const draftPtSessions = selectedDraft ? filterPtSessions(ptSessions, selectedDraft.draft_id) : []

  const currentStatus = selectedDraft?.lifecycle_status ?? 'draft'

  const guidance = selectedDraft
    ? computeGuidance({
        lifecycleStatus:      currentStatus,
        hasCompletedBacktest: draftBtRuns.some(r => r.status === 'completed'),
        hasFtSession:         draftFtSessions.length > 0,
        hasFtEvidenceBars:    draftFtSessions.some(s => s.signal_eligible_bars_processed > 0),
        hasPtSession:         draftPtSessions.length > 0,
        ptIsFinalized:        draftPtSessions.some(s => s.status === 'terminated' || s.status === 'completed'),
        ptHasBarEvidence:     draftPtSessions.some(
          s => (s.status === 'terminated' || s.status === 'completed') && s.last_processed_bar_timestamp !== null,
        ),
      })
    : null

  const navCallback = guidance ? resolveNav(guidance.navigateTarget, { onNavigateToComposer, onNavigateToHistory, onNavigateToForwardTest, onNavigateToPaperTrading }) : null
  const blockers    = guidance?.blockers ?? []

  // Evidence helpers
  const latestCompletedBt = draftBtRuns
    .filter(r => r.status === 'completed')
    .sort((a, b) => b.run_timestamp.localeCompare(a.run_timestamp))[0] ?? null

  const eligibleFtSessions = draftFtSessions.filter(s => s.signal_eligible_bars_processed > 0)
  const latestEligibleFt   = eligibleFtSessions.sort((a, b) => b.created_at.localeCompare(a.created_at))[0] ?? null

  const readyPtSessions = draftPtSessions.filter(
    s => (s.status === 'terminated' || s.status === 'completed') && s.last_processed_bar_timestamp !== null,
  )

  // Evidence readiness items — stage-specific, used by EvidenceReadinessPanel below evidence summaries
  const evidenceReadinessItems: EvidenceItem[] = (() => {
    if (currentStatus === 'validated') {
      return [
        {
          label:       'Completed Backtest Run',
          complete:    draftBtRuns.some(r => r.status === 'completed'),
          explanation: 'A completed backtest provides historical performance evidence required for lifecycle promotion.',
        },
      ]
    }
    if (currentStatus === 'backtested') {
      return [
        {
          label:       'Forward-Test Session Exists',
          complete:    draftFtSessions.length > 0,
          explanation: 'A forward-test session is required to record live market behavior on sequential data.',
        },
        {
          label:       'Live Bars Evaluated After Warmup',
          complete:    draftFtSessions.some(s => s.signal_eligible_bars_processed > 0),
          explanation: 'At least one live market bar must be evaluated after the warmup period to establish behavior evidence.',
        },
      ]
    }
    if (currentStatus === 'forward_tested') {
      return [
        {
          label:       'Paper-Trading Session Exists',
          complete:    draftPtSessions.length > 0,
          explanation: 'A paper-trading session is required to simulate execution and record portfolio behavior.',
        },
        {
          label:       'Session Finalized',
          complete:    draftPtSessions.some(s => s.status === 'terminated' || s.status === 'completed'),
          explanation: 'The paper-trading session must be terminated or completed before promotion evidence can be reviewed.',
        },
        {
          label:       'Market Data Processed',
          complete:    draftPtSessions.some(s => s.last_processed_bar_timestamp !== null),
          explanation: 'At least one market bar must be processed to confirm live data integration.',
        },
      ]
    }
    return []
  })()

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div data-testid="lcd-panel" style={{ padding: '20px 24px', maxWidth: 900, color: '#e2e8f0', fontFamily: 'inherit' }}>
      <h2 style={{ fontSize: 16, fontWeight: 600, color: '#e2e8f0', marginBottom: 16, marginTop: 0 }}>
        Strategy Lifecycle Dashboard
      </h2>

      {/* Draft picker */}
      {loading ? (
        <div data-testid="lcd-loading" style={{ color: '#718096', fontSize: 13 }}>Loading…</div>
      ) : error ? (
        <div data-testid="lcd-error" style={{ color: '#fc8181', fontSize: 13 }}>Error: {error}</div>
      ) : drafts.length === 0 ? (
        <div data-testid="lcd-no-drafts" style={{ color: '#718096', fontSize: 13 }}>
          No strategies found. Open the Strategy Builder to create your first draft.
        </div>
      ) : (
        <>
          <div style={{ marginBottom: 20, display: 'flex', alignItems: 'center', gap: 10 }}>
            <label style={{ fontSize: 12, color: '#a0aec0' }}>Strategy:</label>
            <select
              data-testid="lcd-draft-select"
              value={selectedId ?? ''}
              onChange={e => setSelectedId(e.target.value || null)}
              style={{
                background: '#161b22', border: '1px solid #30363d', borderRadius: 4,
                color: '#e2e8f0', fontSize: 13, padding: '4px 8px', minWidth: 240,
              }}
            >
              {drafts.map(d => (
                <option key={d.draft_id} value={d.draft_id}>
                  {d.display_name} — {d.lifecycle_status ?? 'draft'}
                </option>
              ))}
            </select>
          </div>

          {!selectedDraft ? (
            <div data-testid="lcd-no-draft-selected" style={{ color: '#718096', fontSize: 13 }}>
              Select a strategy to view its lifecycle.
            </div>
          ) : (
            <>
              {/* Lifecycle Stage Track */}
              <div
                data-testid="lcd-stage-track"
                style={{ display: 'flex', alignItems: 'flex-start', gap: 0, marginBottom: 24, overflowX: 'auto' }}
              >
                {LIFECYCLE_STAGES.map((stage, i) => (
                  <div key={stage.key} style={{ display: 'flex', alignItems: 'flex-start' }}>
                    <StageNode
                      stageKey={stage.key}
                      label={stage.label}
                      state={getStageState(stage.key, currentStatus)}
                    />
                    {i < LIFECYCLE_STAGES.length - 1 && (
                      <div style={{
                        width: 28, height: 2, marginTop: 7, flexShrink: 0,
                        background: stageIndex(stage.key) < stageIndex(currentStatus) ? '#48bb78' : '#2d3748',
                      }} />
                    )}
                  </div>
                ))}
              </div>

              {/* Current stage + next action row */}
              <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
                {/* Current stage card */}
                <div
                  data-testid="lcd-current-stage"
                  style={{ background: '#0d1117', border: '1px solid #21262d', borderRadius: 6, padding: '10px 16px', flex: '1 1 160px' }}
                >
                  <div style={{ fontSize: 10, color: '#718096', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>
                    Current Stage
                  </div>
                  <div style={{ fontSize: 14, color: '#26a69a', fontWeight: 600 }}>
                    {LIFECYCLE_STAGES.find(s => s.key === currentStatus)?.label ?? currentStatus}
                  </div>
                </div>

                {/* Next action card */}
                <div
                  data-testid="lcd-next-action"
                  style={{ background: '#0d1117', border: '1px solid #21262d', borderRadius: 6, padding: '10px 16px', flex: '2 1 240px' }}
                >
                  <div style={{ fontSize: 10, color: '#718096', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
                    Next Recommended Action
                  </div>
                  {guidance === null ? (
                    <div style={{ fontSize: 12, color: '#718096' }}>
                      No further actions available for this lifecycle stage.
                    </div>
                  ) : guidance.navigateLocked ? (
                    <div data-testid="lcd-next-action-locked" style={{ fontSize: 12, color: '#718096' }}>
                      {guidance.nextAction} — requires external review process.
                    </div>
                  ) : (
                    <button
                      data-testid="lcd-next-action-btn"
                      onClick={navCallback ?? undefined}
                      style={{
                        background: '#276749', border: 'none', borderRadius: 4,
                        color: '#e2e8f0', cursor: 'pointer', fontSize: 12,
                        fontFamily: 'inherit', padding: '6px 14px',
                      }}
                    >
                      {guidance.nextAction}
                    </button>
                  )}
                </div>
              </div>

              {/* Blockers */}
              <div
                data-testid="lcd-blockers"
                style={{ background: '#0d1117', border: '1px solid #21262d', borderRadius: 6, padding: '10px 14px', marginBottom: 16 }}
              >
                <div style={{ fontSize: 10, color: '#718096', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
                  What Is Blocking Progress?
                </div>
                {blockers.length === 0 ? (
                  <div data-testid="lcd-no-blockers" style={{ fontSize: 12, color: '#48bb78' }}>
                    No blockers — strategy is ready for the next step.
                  </div>
                ) : (
                  <ul style={{ margin: 0, padding: '0 0 0 16px' }}>
                    {blockers.map((b, i) => (
                      <li key={i} data-testid="lcd-blocker-item" style={{ fontSize: 12, color: '#ffa726', lineHeight: 1.6 }}>
                        {b}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {/* Evidence summary */}
              <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
                {/* Backtest evidence */}
                <EvidenceSection title="Backtest Evidence" testId="lcd-evidence-backtest">
                  {draftBtRuns.length === 0 ? (
                    <div data-testid="lcd-evidence-backtest-empty" style={{ fontSize: 12, color: '#718096' }}>
                      No backtests exist yet.
                    </div>
                  ) : (
                    <div style={{ fontSize: 12, color: '#a0aec0' }}>
                      <div>Total runs: <strong style={{ color: '#e2e8f0' }}>{draftBtRuns.length}</strong></div>
                      {latestCompletedBt ? (
                        <div style={{ marginTop: 4 }}>
                          Latest completed:{' '}
                          <strong style={{ color: '#48bb78' }}>
                            {new Date(latestCompletedBt.run_timestamp).toLocaleDateString()}
                          </strong>
                        </div>
                      ) : (
                        <div style={{ marginTop: 4, color: '#718096' }}>No completed run yet.</div>
                      )}
                    </div>
                  )}
                </EvidenceSection>

                {/* Forward-test evidence */}
                <EvidenceSection title="Forward-Test Evidence" testId="lcd-evidence-ft">
                  {draftFtSessions.length === 0 ? (
                    <div data-testid="lcd-evidence-ft-empty" style={{ fontSize: 12, color: '#718096' }}>
                      No forward-test sessions exist yet.
                    </div>
                  ) : (
                    <div style={{ fontSize: 12, color: '#a0aec0' }}>
                      <div>Total sessions: <strong style={{ color: '#e2e8f0' }}>{draftFtSessions.length}</strong></div>
                      <div>Eligible sessions: <strong style={{ color: eligibleFtSessions.length > 0 ? '#48bb78' : '#718096' }}>{eligibleFtSessions.length}</strong></div>
                      {latestEligibleFt && (
                        <div style={{ marginTop: 4 }}>
                          Latest eligible: <strong style={{ color: '#26a69a' }}>{latestEligibleFt.status}</strong>
                        </div>
                      )}
                    </div>
                  )}
                </EvidenceSection>

                {/* Paper-trading evidence */}
                <EvidenceSection title="Paper-Trading Evidence" testId="lcd-evidence-pt">
                  {draftPtSessions.length === 0 ? (
                    <div data-testid="lcd-evidence-pt-empty" style={{ fontSize: 12, color: '#718096' }}>
                      No paper trading sessions exist yet.
                    </div>
                  ) : (
                    <div style={{ fontSize: 12, color: '#a0aec0' }}>
                      <div>Total sessions: <strong style={{ color: '#e2e8f0' }}>{draftPtSessions.length}</strong></div>
                      <div>
                        Evidence ready:{' '}
                        <strong style={{ color: readyPtSessions.length > 0 ? '#48bb78' : '#718096' }}>
                          {readyPtSessions.length > 0 ? 'Yes' : 'No'}
                        </strong>
                      </div>
                    </div>
                  )}
                </EvidenceSection>
              </div>

              {/* Evidence readiness panel */}
              {evidenceReadinessItems.length > 0 && (
                <EvidenceReadinessPanel
                  title="Promotion Evidence Readiness"
                  items={evidenceReadinessItems}
                />
              )}

              {/* Quick navigation */}
              <div
                data-testid="lcd-quick-nav"
                style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}
              >
                <button
                  data-testid="lcd-nav-composer"
                  onClick={onNavigateToComposer}
                  style={navBtnStyle}
                >
                  Open Strategy Builder
                </button>
                <button
                  data-testid="lcd-nav-history"
                  onClick={onNavigateToHistory}
                  style={navBtnStyle}
                >
                  Backtest History
                </button>
                <button
                  data-testid="lcd-nav-forward-test"
                  onClick={onNavigateToForwardTest}
                  style={navBtnStyle}
                >
                  Forward Test Panel
                </button>
                <button
                  data-testid="lcd-nav-paper-trading"
                  onClick={onNavigateToPaperTrading}
                  style={navBtnStyle}
                >
                  Paper Trading Panel
                </button>
              </div>

              {/* Technical details (collapsible) */}
              <div>
                <button
                  data-testid="lcd-tech-toggle"
                  onClick={() => setTechExpanded(x => !x)}
                  style={{
                    background: 'none', border: '1px solid #21262d', borderRadius: 4,
                    color: '#718096', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit',
                    padding: '4px 10px', marginBottom: 8,
                  }}
                >
                  {techExpanded ? '▾' : '▸'} Technical Details
                </button>
                {techExpanded && (
                  <div
                    data-testid="lcd-tech-details"
                    style={{ background: '#0d1117', border: '1px solid #21262d', borderRadius: 6, padding: '10px 14px', fontSize: 11, color: '#718096' }}
                  >
                    <div><span style={{ color: '#4a5568' }}>Draft ID:</span> {selectedDraft.draft_id}</div>
                    <div><span style={{ color: '#4a5568' }}>Lifecycle Enum:</span> {selectedDraft.lifecycle_status ?? 'draft'}</div>
                    <div><span style={{ color: '#4a5568' }}>Created:</span> {new Date(selectedDraft.created_at).toISOString()}</div>
                    <div><span style={{ color: '#4a5568' }}>Updated:</span> {new Date(selectedDraft.updated_at).toISOString()}</div>
                    <div><span style={{ color: '#4a5568' }}>Backtest runs:</span> {draftBtRuns.map(r => r.run_id).join(', ') || '—'}</div>
                    <div><span style={{ color: '#4a5568' }}>FT sessions:</span> {draftFtSessions.map(s => s.session_id).join(', ') || '—'}</div>
                    <div><span style={{ color: '#4a5568' }}>PT sessions:</span> {draftPtSessions.map(s => s.session_id).join(', ') || '—'}</div>
                  </div>
                )}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

const navBtnStyle: React.CSSProperties = {
  background: '#161b22',
  border: '1px solid #30363d',
  borderRadius: 4,
  color: '#a0aec0',
  cursor: 'pointer',
  fontSize: 11,
  fontFamily: 'inherit',
  padding: '5px 12px',
}
