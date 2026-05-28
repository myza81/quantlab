/**
 * BacktestReportPage — full backtest simulation report.
 *
 * Sections:
 *   1. Run header (symbol, strategy, config assumptions)
 *   2. Metrics summary cards
 *   3. Equity curve + drawdown charts
 *   4. Trade ledger table
 *   5. Rejections / audit
 */
import type { BacktestReport } from '../types/backtestRuns'
import { downloadEquityCSV, downloadReportJSON, downloadTradesCSV } from '../api/backtestRuns'
import { EquityCurveChart } from './EquityCurveChart'
import { TradeLedgerTable } from './TradeLedgerTable'

interface Props {
  report:  BacktestReport
  onBack:  () => void
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

export function BacktestReportPage({ report, onBack }: Props) {
  const { run, metrics } = report

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

  return (
    <div style={s.page}>

      {/* ── Header ── */}
      <div style={s.header}>
        <button style={s.backBtn} onClick={onBack}>← Back to Chart</button>
        <div style={s.headerMeta}>
          <span style={s.headerSymbol}>{run.symbol} · {run.timeframe}</span>
          <span style={s.headerStrategy}>{run.draft_name}</span>
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
}
