/**
 * BacktestReportPage — full backtest simulation report.
 *
 * Sections:
 *   1. Run header (symbol, strategy, config assumptions)
 *   2. Lifecycle promotion panel (Phase R4 — shown when promotion is actionable)
 *   3. Metrics summary cards
 *   4. Equity curve + drawdown charts
 *   5. Trade ledger table
 *   6. Rejections / audit
 */
import { useState } from 'react'
import type { BacktestReport, BacktestRunSummary } from '../types/backtestRuns'
import type { ForwardTestPrefill } from '../types/forwardTesting'
import { downloadEquityCSV, downloadReportJSON, downloadTradesCSV } from '../api/backtestRuns'
import { EquityCurveChart } from './EquityCurveChart'
import { TradeLedgerTable } from './TradeLedgerTable'
import { LifecycleBadge } from './LifecycleBadge'
import { computeGuidance } from '../lib/lifecycleGuidance'
import { LifecycleGuidanceCard } from './LifecycleGuidanceCard'
import { EvidenceReadinessPanel } from './EvidenceReadinessPanel'
import type { EvidenceItem } from './EvidenceReadinessPanel'

interface Props {
  report:                BacktestReport
  onBack:                () => void
  sourceLabel?:          string | null
  onNavigateToComposer?: () => void
  /** Called when the user requests promotion of the draft to 'backtested'. */
  onPromoteDraft?: (runId: string, draftId: string) => Promise<void>
  /** Called when the user wants to start a forward test from this report context. */
  onStartForwardTest?: (prefill: ForwardTestPrefill) => void
}

function buildPrefillFromRun(run: BacktestRunSummary): ForwardTestPrefill {
  return {
    draft_id:      run.draft_id,
    draft_name:    run.draft_name,
    symbol:        run.symbol,
    timeframe:     run.timeframe,
    provider_name: run.dataset_provenance?.provider_name ?? undefined,
  }
}

const $ = (v: number | null | undefined, dp = 2) =>
  v == null ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp })

const pct = (v: number | null | undefined, signed = true) => {
  if (v == null) return '—'
  const prefix = signed && v > 0 ? '+' : ''
  return `${prefix}${v.toFixed(2)}%`
}

function pnlColor(v: number | null | undefined): string {
  if (v == null) return '#7a8598'
  return v > 0 ? '#66bb6a' : v < 0 ? '#ef5350' : '#7a8598'
}

function fmtDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}

interface MetricCardProps { label: string; value: string; color?: string; sub?: string }
function MetricCard({ label, value, color, sub }: MetricCardProps) {
  return (
    <div style={s.card}>
      <div style={s.cardLabel}>{label}</div>
      <div style={{ ...s.cardValue, color: color ?? '#d1d4dc' }}>{value}</div>
      {sub && <div style={s.cardSub}>{sub}</div>}
    </div>
  )
}

interface ProvenanceRowProps { label: string; value: string; mono?: boolean }
function ProvenanceRow({ label, value, mono }: ProvenanceRowProps) {
  return (
    <div style={s.provRow}>
      <span style={s.provKey}>{label}</span>
      <span style={mono ? s.provValMono : s.provVal}>{value}</span>
    </div>
  )
}

const BACKTESTED_OR_BEYOND = new Set(['backtested', 'forward_tested', 'paper_tested', 'approved_for_live'])

export function BacktestReportPage({ report, onBack, sourceLabel, onNavigateToComposer, onPromoteDraft, onStartForwardTest }: Props) {
  const { run, metrics } = report

  // Promotion state — scoped to this report view
  const [promotionState, setPromotionState] = useState<'idle' | 'promoting' | 'success' | 'error'>('idle')
  const [promotionError, setPromotionError] = useState<string | null>(null)

  const lifecycleAtRun = run.draft_provenance?.lifecycle_status_at_run ?? null

  // Show promotion panel only when draft was 'validated' at run time — the
  // minimum required lifecycle state for backtest evidence to count.
  const showPromotionPanel =
    run.status === 'completed' &&
    lifecycleAtRun === 'validated' &&
    promotionState !== 'success' &&
    onPromoteDraft != null

  // Show prerequisite notice when draft was still 'draft' at run time —
  // the user needs to validate the draft before a backtest can count as evidence.
  const showDraftPrerequisiteNotice =
    run.status === 'completed' &&
    lifecycleAtRun === 'draft'

  // Show "already eligible" info when draft was already backtested+ at run time.
  const alreadyEligible =
    run.status === 'completed' &&
    lifecycleAtRun != null &&
    BACKTESTED_OR_BEYOND.has(lifecycleAtRun)

  async function handlePromote() {
    if (!onPromoteDraft) return
    setPromotionState('promoting')
    setPromotionError(null)
    try {
      await onPromoteDraft(run.run_id, run.draft_id)
      setPromotionState('success')
    } catch (err) {
      setPromotionState('error')
      setPromotionError(err instanceof Error ? err.message : 'Promotion failed')
    }
  }

  const cfgLabel = (() => {
    const parts: string[] = []
    if (run.config.position_size_mode === 'equity_fraction' && run.config.equity_fraction != null)
      parts.push(`${(run.config.equity_fraction * 100).toFixed(0)}% equity/trade`)
    else
      parts.push(`${run.config.fixed_quantity} unit/trade`)
    if (run.config.commission_mode !== 'none')
      parts.push(`${run.config.commission_mode} commission ${run.config.commission_value}`)
    if (run.config.slippage_mode !== 'none')
      parts.push(`${run.config.slippage_mode} slippage ${run.config.slippage_value}`)
    if (parts.length === 0) parts.push('no commission · no slippage')
    return parts.join(' · ')
  })()

  // After a successful promotion the draft advances to 'backtested'. The report
  // page only has a historical snapshot (lifecycleAtRun), so we derive the
  // effective status here rather than re-fetching the draft.
  const effectiveLifecycleStatus: string =
    promotionState === 'success' ? 'backtested' : (lifecycleAtRun ?? 'draft')

  const btGuidance = run.status === 'completed' && lifecycleAtRun != null
    ? computeGuidance({
        lifecycleStatus:      effectiveLifecycleStatus,
        // This page IS the completed backtest evidence — pass it directly
        // instead of defaulting to false, which caused "Run Backtest" to appear
        // alongside "Promotion Ready" on the same page.
        hasCompletedBacktest: run.status === 'completed',
      })
    : null
  const btNavCallback = btGuidance?.navigateTarget === 'composer' ? onNavigateToComposer : undefined

  // Evidence readiness panel — shown for draft/validated → Backtest Complete pathway
  const showBtEvidencePanel = lifecycleAtRun === 'draft' || lifecycleAtRun === 'validated'
  const btEvidenceItems: EvidenceItem[] = showBtEvidencePanel ? [
    {
      label:       'Strategy Draft Exists',
      complete:    true,
      explanation: 'A strategy draft is required before any evidence can be recorded.',
    },
    {
      label:       'Draft Validated',
      complete:    lifecycleAtRun !== 'draft',
      explanation: 'Validated drafts confirm the strategy toolset and conditions are complete.',
    },
    {
      label:       'Backtest Completed',
      complete:    run.status === 'completed',
      explanation: 'A completed backtest run provides historical performance evidence required for lifecycle promotion.',
    },
  ] : []

  return (
    <div style={s.page}>

      {/* ── Header ── */}
      <div style={s.header}>
        <button style={s.backBtn} onClick={onBack}>← Back to Chart</button>
        {onNavigateToComposer && (
          <button
            data-testid="edit-strategy-btn"
            style={s.editStrategyBtn}
            onClick={onNavigateToComposer}
          >
            Edit Strategy
          </button>
        )}
        <div style={s.headerMeta}>
          <span style={s.headerSymbol}>{run.symbol} · {run.timeframe}</span>
          <span style={s.headerStrategy}>{run.draft_name}</span>
          {sourceLabel && (
            <span data-testid="report-source-label" style={s.headerSource}>{sourceLabel}</span>
          )}
          <span style={s.headerTs}>{fmtDateTime(run.run_timestamp)}</span>
          <span style={s.headerBars}>{run.bars_count} bars · {cfgLabel}</span>
        </div>
        <div style={s.exportGroup}>
          <button style={s.exportBtn} onClick={() => downloadTradesCSV(run.run_id)} title="Download trade ledger CSV">↓ Trades</button>
          <button style={s.exportBtn} onClick={() => downloadEquityCSV(run.run_id)}  title="Download equity curve CSV">↓ Equity</button>
          <button style={s.exportBtn} onClick={() => downloadReportJSON(run.run_id)} title="Download full report JSON">↓ JSON</button>
        </div>
        <div style={s.headerRunId}>run {run.run_id.slice(0, 8)}</div>
      </div>

      <div style={s.body}>
      <div style={s.bodyInner}>

        {/* ── Draft Prerequisite Notice ── */}
        {showDraftPrerequisiteNotice && (
          <div data-testid="draft-prerequisite-notice" style={s.draftPrerequisiteNotice}>
            <LifecycleBadge status="draft" />
            <span style={s.draftPrerequisiteText}>
              This backtest was run while the draft was still in <strong>draft</strong> status.
              Validate the draft first, then re-run the backtest to unlock lifecycle promotion.
            </span>
          </div>
        )}

        {/* ── Lifecycle Promotion Panel ── */}
        {showPromotionPanel && (
          <div data-testid="promotion-panel" style={s.promotionPanel}>
            <div style={s.promotionHeader}>
              <span style={s.promotionTitle}>Lifecycle Promotion</span>
              <LifecycleBadge status={lifecycleAtRun!} />
              <span style={s.promotionArrow}>→</span>
              <LifecycleBadge status="backtested" />
            </div>
            <p style={s.promotionBody}>
              This backtest completed on a <strong style={{ color: '#7eb8f7' }}>validated</strong> draft.
              Promote it to <strong style={{ color: '#66bb6a' }}>backtested</strong> to
              unlock forward testing.
            </p>
            <div style={s.promotionActions}>
              <button
                data-testid="promote-to-backtested-btn"
                style={{
                  ...s.promotionBtn,
                  opacity: promotionState === 'promoting' ? 0.5 : 1,
                  cursor:  promotionState === 'promoting' ? 'not-allowed' : 'pointer',
                }}
                disabled={promotionState === 'promoting'}
                onClick={handlePromote}
              >
                {promotionState === 'promoting' ? 'Promoting…' : 'Promote to Backtested'}
              </button>
              {promotionState === 'error' && promotionError && (
                <span data-testid="promotion-error" style={s.promotionError}>
                  {promotionError}
                </span>
              )}
            </div>
          </div>
        )}

        {promotionState === 'success' && (
          <div data-testid="promotion-success" style={s.promotionSuccess}>
            <span style={s.promotionSuccessIcon}>✓</span>
            Draft promoted to <strong style={{ color: '#66bb6a' }}>Backtested</strong>.
            Forward testing is now available.
            {onStartForwardTest && (
              <button
                data-testid="start-forward-test-btn"
                style={s.fwdTestBtn}
                onClick={() => onStartForwardTest(buildPrefillFromRun(run))}
              >
                Start Forward Test ↗
              </button>
            )}
          </div>
        )}

        {alreadyEligible && (
          <div data-testid="already-eligible-notice" style={s.alreadyEligible}>
            <LifecycleBadge status={lifecycleAtRun!} />
            <span style={s.alreadyEligibleText}>
              This draft was already <strong>{lifecycleAtRun}</strong> when this run was executed.
              Forward testing is available from the Forward Test tab.
            </span>
            <button
              data-testid="forward-test-hint-btn"
              style={{
                ...s.fwdTestHintBtn,
                ...(onStartForwardTest ? {
                  cursor:      'pointer',
                  color:       '#63b3ed',
                  borderColor: '#2a4a5e',
                } : {}),
              }}
              disabled={!onStartForwardTest}
              title={onStartForwardTest
                ? 'Open Forward Test with this strategy context pre-filled'
                : 'Go to the Forward Test tab to start a session'}
              onClick={onStartForwardTest
                ? () => onStartForwardTest(buildPrefillFromRun(run))
                : undefined}
            >
              Start Forward Test ↗
            </button>
          </div>
        )}

        {btGuidance && (
          <LifecycleGuidanceCard
            currentStageLabel={btGuidance.currentStageLabel}
            nextAction={btGuidance.nextAction}
            whyItMatters={btGuidance.whyItMatters}
            blockers={btGuidance.blockers}
            onNavigate={btNavCallback}
            navigateLocked={btGuidance.navigateLocked}
          />
        )}

        {btEvidenceItems.length > 0 && (
          <div data-testid="bt-evidence-panel">
            <EvidenceReadinessPanel
              title="Promotion Evidence — Validated → Backtest Complete"
              items={btEvidenceItems}
            />
          </div>
        )}

        {/* ── Metrics grid ── */}
        <div style={s.section}>
          <div style={s.sectionTitle}>Performance Summary</div>
          <div style={s.metricsGrid}>
            <MetricCard label="Initial Equity"  value={`$${$(metrics.initial_equity)}`} />
            <MetricCard label="Final Equity"    value={`$${$(metrics.final_equity)}`}
              color={pnlColor(metrics.final_equity - metrics.initial_equity)} />
            <MetricCard label="Net Profit"      value={`$${$(metrics.total_net_profit)}`}
              color={pnlColor(metrics.total_net_profit)} />
            <MetricCard label="Total Return"    value={pct(metrics.total_return_pct)}
              color={pnlColor(metrics.total_return_pct)} />
            <MetricCard label="Max Drawdown"
              value={pct(metrics.max_drawdown_pct, false)}
              color={metrics.max_drawdown_pct > 20 ? '#ef5350' : metrics.max_drawdown_pct > 10 ? '#ffa726' : '#66bb6a'} />
            <MetricCard label="Profit Factor"
              value={metrics.profit_factor == null ? 'N/A' : $(metrics.profit_factor)}
              color={metrics.profit_factor == null ? undefined : metrics.profit_factor >= 1 ? '#66bb6a' : '#ef5350'} />
            <MetricCard label="Win Rate"
              value={metrics.win_rate == null ? 'N/A' : pct(metrics.win_rate * 100, false)}
              sub={metrics.trade_count > 0 ? `${metrics.win_count}W / ${metrics.loss_count}L / ${metrics.breakeven_count}BE` : undefined} />
            <MetricCard label="Trades"         value={`${metrics.trade_count}`}
              sub={`${metrics.total_rejections} rejected`} />
            <MetricCard label="Avg Win"        value={metrics.avg_win == null ? 'N/A' : `$${$(metrics.avg_win)}`}
              color={metrics.avg_win != null ? '#66bb6a' : undefined} />
            <MetricCard label="Avg Loss"       value={metrics.avg_loss == null ? 'N/A' : `$${$(metrics.avg_loss)}`}
              color={metrics.avg_loss != null ? '#ef5350' : undefined} />
            <MetricCard label="Best Trade"     value={metrics.best_trade_pnl == null ? 'N/A' : `$${$(metrics.best_trade_pnl)}`}
              color='#66bb6a' />
            <MetricCard label="Worst Trade"    value={metrics.worst_trade_pnl == null ? 'N/A' : `$${$(metrics.worst_trade_pnl)}`}
              color='#ef5350' />
            <MetricCard label="Gross Profit"   value={`$${$(metrics.gross_profit)}`}  color='#66bb6a' />
            <MetricCard label="Gross Loss"     value={`$${$(metrics.gross_loss)}`}    color='#ef5350' />
            <MetricCard label="Commission"     value={`$${$(metrics.total_commission)}`} />
            <MetricCard label="Slippage Cost"  value={`$${$(metrics.total_slippage)}`} />
            <MetricCard label="Peak Equity"    value={`$${$(metrics.peak_equity)}`} />
            <MetricCard label="Trough Equity"  value={`$${$(metrics.trough_equity)}`} />
          </div>
        </div>

        {/* ── Equity curve ── */}
        {report.equity_curve.length > 0 && (
          <div style={s.section}>
            <div style={s.sectionTitle}>Equity & Drawdown</div>
            <EquityCurveChart
              equityCurve={report.equity_curve}
              drawdownCurve={report.drawdown_curve}
            />
          </div>
        )}

        {/* ── Trade ledger ── */}
        <div style={s.section}>
          <div style={s.sectionTitle}>
            Trade Ledger
            <span style={s.sectionCount}>{metrics.trade_count} closed trades</span>
            {report.open_position && (
              <span style={{ ...s.sectionCount, color: '#7eb8f7' }}>+ 1 open</span>
            )}
          </div>
          <TradeLedgerTable
            trades={report.trades}
            openPosition={report.open_position}
          />
        </div>

        {/* ── Run Provenance ── */}
        {(run.dataset_provenance || run.draft_provenance) && (
          <div style={s.section}>
            <div style={s.sectionTitle}>Run Provenance</div>
            <div style={s.provenanceGrid}>
              {run.dataset_provenance && (
                <div style={s.provenanceBlock}>
                  <div style={s.provenanceBlockTitle}>Dataset</div>
                  {run.dataset_provenance.source_mode && (
                    <ProvenanceRow label="source"      value={run.dataset_provenance.source_mode} />
                  )}
                  {run.dataset_provenance.provider_name && (
                    <ProvenanceRow label="provider"    value={run.dataset_provenance.provider_name} />
                  )}
                  {run.dataset_provenance.catalog_id && (
                    <ProvenanceRow label="catalog_id"  value={run.dataset_provenance.catalog_id.slice(0, 8)} mono />
                  )}
                  <ProvenanceRow label="bars"          value={`${run.dataset_provenance.bar_count.toLocaleString()}`} />
                  {run.dataset_provenance.bars_fingerprint && (
                    <ProvenanceRow label="fingerprint" value={run.dataset_provenance.bars_fingerprint.slice(0, 12)} mono />
                  )}
                </div>
              )}
              {run.draft_provenance && (
                <div style={s.provenanceBlock}>
                  <div style={s.provenanceBlockTitle}>Strategy</div>
                  <ProvenanceRow label="draft_id"   value={run.draft_provenance.draft_id.slice(0, 8)} mono />
                  <ProvenanceRow label="name"        value={run.draft_provenance.display_name} />
                  <div style={{ ...s.provRow, alignItems: 'center' }}>
                    <span style={s.provKey}>lifecycle</span>
                    <LifecycleBadge status={run.draft_provenance.lifecycle_status_at_run} />
                  </div>
                  {run.draft_provenance.semantics_hash && (
                    <ProvenanceRow label="logic_hash" value={run.draft_provenance.semantics_hash.slice(0, 12)} mono />
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Rejections / Rule Audit ── */}
        <div style={s.section}>
          <div style={s.sectionTitle}>
            Signal / Rule Audit
            {report.rejections.length > 0 && (
              <span style={{ ...s.sectionCount, color: '#ffa726' }}>
                {report.rejections.length} rejected
              </span>
            )}
          </div>

          {/* Rule IDs that triggered trades — populated when semantics are linked */}
          {report.trades.length > 0 && report.trades.some(t => t.entry_rule_id) && (
            <div style={s.ruleAuditList}>
              {report.trades.map(t => (
                <div key={t.trade_num} style={s.ruleAuditRow}>
                  <span style={s.ruleAuditNum}>#{t.trade_num}</span>
                  <span style={s.ruleAuditLabel}>entry:</span>
                  <span style={s.ruleAuditId}>{t.entry_rule_id ?? '—'}</span>
                  <span style={s.ruleAuditLabel}>exit:</span>
                  <span style={s.ruleAuditId}>{t.exit_rule_id ?? '—'}</span>
                </div>
              ))}
            </div>
          )}

          {report.rejections.length === 0 ? (
            <div style={s.auditNote}>No rejected intents — all signals were executed.</div>
          ) : (
            <div style={s.rejectionList}>
              {report.rejections.map(r => (
                <div key={r.rejection_id} style={s.rejectionRow}>
                  <span style={s.rejBadge}>{r.reason}</span>
                  <span style={s.rejDetail}>{r.detail}</span>
                  <span style={s.rejMeta}>bar {r.bar_index}</span>
                </div>
              ))}
            </div>
          )}
          <div style={{ ...s.auditNote, marginTop: 8 }}>
            Per-bar indicator values at signal time are not yet included in this report.
          </div>
        </div>

      </div>
      </div>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  page: {
    display:       'flex',
    flexDirection: 'column',
    flex:          1,
    overflow:      'hidden',
    background:    '#0f0f1a',
    fontFamily:    'monospace',
    color:         '#d1d4dc',
  },
  header: {
    display:      'flex',
    alignItems:   'center',
    gap:          12,
    padding:      '10px 16px',
    background:   '#0d0d20',
    borderBottom: '1px solid #1e1e30',
    flexShrink:   0,
  },
  backBtn: {
    background:   'transparent',
    border:       '1px solid #2a2d3e',
    borderRadius: 4,
    color:        '#7eb8f7',
    cursor:       'pointer',
    fontFamily:   'monospace',
    fontSize:     11,
    padding:      '4px 10px',
    flexShrink:   0,
  },
  editStrategyBtn: {
    background:   'transparent',
    border:       '1px solid #2a3a2a',
    borderRadius: 4,
    color:        '#66bb6a',
    cursor:       'pointer',
    fontFamily:   'monospace',
    fontSize:     11,
    padding:      '4px 10px',
    flexShrink:   0,
  },
  headerSource: {
    fontSize:      11,
    color:         '#3a5568',
    fontFamily:    'monospace',
    letterSpacing: '0.03em',
  },
  headerMeta: {
    display: 'flex',
    gap:     12,
    flex:    1,
    flexWrap: 'wrap' as const,
    alignItems: 'center',
  },
  headerSymbol: {
    fontWeight:    700,
    fontSize:      13,
    color:         '#26a69a',
    letterSpacing: '0.05em',
  },
  headerStrategy: {
    fontSize: 12,
    color:    '#d1d4dc',
  },
  headerTs: {
    fontSize: 11,
    color:    '#4a5568',
  },
  headerBars: {
    fontSize: 11,
    color:    '#4a5568',
  },
  headerRunId: {
    fontSize:  10,
    color:     '#2a2d3e',
    flexShrink: 0,
  },
  exportGroup: {
    display:    'flex',
    gap:        4,
    flexShrink: 0,
  },
  exportBtn: {
    background:   'transparent',
    border:       '1px solid #2a2d3e',
    borderRadius: 3,
    color:        '#4a6080',
    cursor:       'pointer',
    fontFamily:   'monospace',
    fontSize:     10,
    padding:      '3px 8px',
    letterSpacing: '0.03em',
  },
  body: {
    flex:      1,
    overflowY: 'auto',
    padding:   '24px 16px',
  },
  bodyInner: {
    maxWidth:      1100,
    margin:        '0 auto',
    display:       'flex',
    flexDirection: 'column',
    gap:           24,
  },
  section: {
    display:       'flex',
    flexDirection: 'column',
    gap:           10,
  },
  sectionTitle: {
    fontSize:      11,
    fontWeight:    700,
    color:         '#4a5568',
    letterSpacing: '0.08em',
    display:       'flex',
    alignItems:    'center',
    gap:           8,
  },
  sectionCount: {
    fontSize:   10,
    color:      '#7a8598',
    fontWeight: 400,
  },
  metricsGrid: {
    display:             'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
    gap:                 8,
  },
  card: {
    background:    '#0d0d20',
    border:        '1px solid #1e1e30',
    borderRadius:  6,
    padding:       '10px 12px',
    display:       'flex',
    flexDirection: 'column',
    gap:           3,
  },
  cardLabel: {
    fontSize:  10,
    color:     '#4a5568',
    letterSpacing: '0.05em',
  },
  cardValue: {
    fontSize:   15,
    fontWeight: 700,
    color:      '#d1d4dc',
  },
  cardSub: {
    fontSize: 10,
    color:    '#4a5568',
  },
  auditNote: {
    fontSize:  11,
    color:     '#4a5568',
    fontStyle: 'italic',
  },
  rejectionList: {
    display:       'flex',
    flexDirection: 'column',
    gap:           4,
    maxHeight:     180,
    overflowY:     'auto',
  },
  rejectionRow: {
    display:    'flex',
    gap:        10,
    alignItems: 'baseline',
    fontSize:   11,
  },
  rejBadge: {
    background:   '#2a1a0a',
    color:        '#ffa726',
    borderRadius: 3,
    padding:      '1px 6px',
    fontSize:     10,
    flexShrink:   0,
  },
  rejDetail: {
    color: '#7a8598',
    flex:  1,
  },
  rejMeta: {
    color:    '#4a5568',
    fontSize: 10,
    flexShrink: 0,
  },
  ruleAuditList: {
    display:       'flex',
    flexDirection: 'column',
    gap:           3,
    marginBottom:  6,
  },
  ruleAuditRow: {
    display:    'flex',
    gap:        8,
    alignItems: 'center',
    fontSize:   10,
    fontFamily: 'monospace',
  },
  ruleAuditNum: {
    color:     '#4a5568',
    width:     24,
    flexShrink: 0,
  },
  ruleAuditLabel: {
    color:     '#2a3040',
    flexShrink: 0,
  },
  ruleAuditId: {
    color:     '#7eb8f7',
    letterSpacing: '0.02em',
  },
  provenanceGrid: {
    display:   'flex',
    gap:       16,
    flexWrap:  'wrap' as const,
  },
  provenanceBlock: {
    background:    '#0a0a14',
    border:        '1px solid #1a1a28',
    borderRadius:  5,
    padding:       '8px 12px',
    display:       'flex',
    flexDirection: 'column' as const,
    gap:           4,
    minWidth:      200,
  },
  provenanceBlockTitle: {
    fontSize:      9,
    color:         '#2a3040',
    fontFamily:    'monospace',
    letterSpacing: '0.08em',
    textTransform: 'uppercase' as const,
    marginBottom:  4,
  },
  provRow: {
    display: 'flex',
    gap:     8,
    alignItems: 'baseline',
  },
  provKey: {
    fontSize:      10,
    color:         '#2a3040',
    fontFamily:    'monospace',
    letterSpacing: '0.04em',
    flexShrink:    0,
    width:         80,
  },
  provVal: {
    fontSize:   10,
    color:      '#4a5568',
    fontFamily: 'monospace',
  },
  provValMono: {
    fontSize:      10,
    color:         '#3a5068',
    fontFamily:    'monospace',
    letterSpacing: '0.06em',
  },

  // ── Lifecycle promotion panel ──
  promotionPanel: {
    background:    '#0a1a0a',
    border:        '1px solid #1a3a1a',
    borderRadius:  6,
    padding:       '12px 16px',
    display:       'flex',
    flexDirection: 'column' as const,
    gap:           8,
  },
  promotionHeader: {
    display:    'flex',
    alignItems: 'center',
    gap:        8,
  },
  promotionTitle: {
    fontSize:      10,
    fontWeight:    700,
    color:         '#4a5568',
    letterSpacing: '0.08em',
    textTransform: 'uppercase' as const,
    marginRight:   4,
  },
  promotionArrow: {
    fontSize: 12,
    color:    '#4a5568',
  },
  promotionBody: {
    fontSize:  11,
    color:     '#7a8598',
    margin:    0,
    lineHeight: 1.5,
  },
  promotionActions: {
    display:    'flex',
    alignItems: 'center',
    gap:        12,
    marginTop:  4,
  },
  promotionBtn: {
    background:   '#0a2a0a',
    border:       '1px solid #1a5a1a',
    borderRadius: 4,
    color:        '#66bb6a',
    fontFamily:   'monospace',
    fontSize:     11,
    padding:      '5px 14px',
    whiteSpace:   'nowrap' as const,
  },
  promotionError: {
    fontSize:  11,
    color:     '#ef5350',
    fontFamily: 'monospace',
  },
  promotionSuccess: {
    display:       'flex',
    alignItems:    'center',
    gap:           8,
    background:    '#0a1e0a',
    border:        '1px solid #1a4a1a',
    borderRadius:  6,
    padding:       '10px 14px',
    fontSize:      12,
    color:         '#7a8598',
  },
  promotionSuccessIcon: {
    fontSize: 14,
    color:    '#66bb6a',
  },
  draftPrerequisiteNotice: {
    display:       'flex',
    alignItems:    'center',
    gap:           10,
    background:    '#0e0a00',
    border:        '1px solid #3a2800',
    borderRadius:  6,
    padding:       '8px 12px',
    flexWrap:      'wrap' as const,
  },
  draftPrerequisiteText: {
    fontSize:  11,
    color:     '#8a7040',
    flex:      1,
  },
  alreadyEligible: {
    display:       'flex',
    alignItems:    'center',
    gap:           10,
    background:    '#0a0a14',
    border:        '1px solid #1a1a28',
    borderRadius:  6,
    padding:       '8px 12px',
    flexWrap:      'wrap' as const,
  },
  alreadyEligibleText: {
    fontSize:  11,
    color:     '#4a5568',
    flex:      1,
  },
  fwdTestHintBtn: {
    background:   'transparent',
    border:       '1px solid #2a2d3e',
    borderRadius: 4,
    color:        '#4a5568',
    fontFamily:   'monospace',
    fontSize:     10,
    padding:      '3px 10px',
    cursor:       'not-allowed',
    whiteSpace:   'nowrap' as const,
  },
  fwdTestBtn: {
    background:   'transparent',
    border:       '1px solid #2a4a5e',
    borderRadius: 4,
    color:        '#63b3ed',
    fontFamily:   'monospace',
    fontSize:     10,
    padding:      '3px 10px',
    cursor:       'pointer',
    whiteSpace:   'nowrap' as const,
    marginLeft:   8,
  },
}
