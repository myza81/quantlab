/**
 * BacktestPanel — runs the full backtest pipeline from a selected draft.
 *
 * User supplies: market params (symbol, timeframe, dates) + simulation config.
 * Panel orchestrates: fetch data → signal events → trade intents → simulate.
 * Displays: summary stats, trades table, rejections.
 */
import { useState } from 'react'
import type { StrategyDraftData } from '../types/drafts'
import type {
  BacktestConfig,
  BacktestMarketParams,
  BacktestResult,
  CommissionMode,
  PositionSizeMode,
  SlippageMode,
} from '../types/backtest'
import { runBacktest } from '../api/backtest'

interface Props {
  draft: StrategyDraftData
}

const DEFAULT_MARKET: BacktestMarketParams = {
  symbol:      'AAPL',
  provider:    'yahoo',
  asset_class: 'equity',
  exchange:    '',
  timeframe:   '1d',
  start:       '2023-01-01',
  end:         '2024-01-01',
}

const DEFAULT_CONFIG: BacktestConfig = {
  initial_cash:       10000,
  position_size_mode: 'equity_fraction',
  fixed_quantity:     1,
  equity_fraction:    0.95,
  commission_mode:    'none',
  commission_value:   0,
  slippage_mode:      'none',
  slippage_value:     0,
}

export function BacktestPanel({ draft }: Props) {
  const [open, setOpen]       = useState(false)
  const [market, setMarket]   = useState<BacktestMarketParams>(DEFAULT_MARKET)
  const [config, setConfig]   = useState<BacktestConfig>(DEFAULT_CONFIG)
  const [running, setRunning] = useState(false)
  const [error, setError]     = useState<string | null>(null)
  const [result, setResult]   = useState<BacktestResult | null>(null)
  const [activeTab, setActiveTab] = useState<'summary' | 'trades' | 'rejections'>('summary')

  const hasSemantic = draft.semantics &&
    (draft.semantics.entry_rules.length > 0 || draft.semantics.exit_rules.length > 0)
  const hasTools = draft.toolset.tools.length > 0

  async function handleRun() {
    if (!draft.semantics) {
      setError('Draft has no semantics. Add entry/exit rules first.')
      return
    }
    setRunning(true)
    setError(null)
    setResult(null)
    try {
      const res = await runBacktest(market, draft.semantics, draft.toolset, config)
      setResult(res)
      setActiveTab('summary')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Backtest failed')
    } finally {
      setRunning(false)
    }
  }

  function setM(k: keyof BacktestMarketParams, v: string) {
    setMarket(prev => ({ ...prev, [k]: v }))
  }

  function setC(k: keyof BacktestConfig, v: unknown) {
    setConfig(prev => ({ ...prev, [k]: v }))
  }

  const pnl     = result?.summary.total_realized_pnl ?? 0
  const pnlPct  = result ? ((result.summary.final_equity - result.summary.initial_cash) / result.summary.initial_cash * 100) : 0
  const winRate = result && result.summary.close_long_trades > 0
    ? (result.trades.filter(t => t.action === 'close_long' && (t.realized_pnl ?? 0) > 0).length / result.summary.close_long_trades * 100)
    : 0

  return (
    <div style={s.container}>
      {/* Header */}
      <button style={s.header} onClick={() => setOpen(o => !o)}>
        <span style={s.headerTitle}>Backtest</span>
        <span style={s.chevron}>{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div style={s.body}>
          {/* Readiness warnings */}
          {!hasSemantic && (
            <div style={s.warn}>No entry/exit rules defined — add semantics before running.</div>
          )}
          {!hasTools && (
            <div style={s.warn}>No tools configured — indicators won't be computed.</div>
          )}

          {/* Market params */}
          <div style={s.section}>
            <div style={s.sectionLabel}>Market</div>
            <div style={s.grid2}>
              <Field label="Symbol">
                <input style={s.input} value={market.symbol}
                  onChange={e => setM('symbol', e.target.value.toUpperCase())} />
              </Field>
              <Field label="Provider">
                <input style={s.input} value={market.provider}
                  onChange={e => setM('provider', e.target.value)} />
              </Field>
              <Field label="Asset Class">
                <input style={s.input} value={market.asset_class}
                  onChange={e => setM('asset_class', e.target.value)} />
              </Field>
              <Field label="Exchange (optional)">
                <input style={s.input} value={market.exchange}
                  onChange={e => setM('exchange', e.target.value)}
                  placeholder="e.g. NASDAQ, KLSE" />
              </Field>
              <Field label="Timeframe">
                <select style={s.input} value={market.timeframe}
                  onChange={e => setM('timeframe', e.target.value)}>
                  {['1d','1wk','1mo','1h','4h'].map(tf => (
                    <option key={tf} value={tf}>{tf}</option>
                  ))}
                </select>
              </Field>
              <Field label="Start">
                <input style={s.input} type="date" value={market.start}
                  onChange={e => setM('start', e.target.value)} />
              </Field>
              <Field label="End">
                <input style={s.input} type="date" value={market.end}
                  onChange={e => setM('end', e.target.value)} />
              </Field>
            </div>
          </div>

          {/* Simulation config */}
          <div style={s.section}>
            <div style={s.sectionLabel}>Simulation</div>
            <div style={s.grid2}>
              <Field label="Initial Cash">
                <input style={s.input} type="number" value={config.initial_cash}
                  onChange={e => setC('initial_cash', parseFloat(e.target.value) || 0)} />
              </Field>
              <Field label="Sizing Mode">
                <select style={s.input} value={config.position_size_mode}
                  onChange={e => setC('position_size_mode', e.target.value as PositionSizeMode)}>
                  <option value="equity_fraction">Equity Fraction</option>
                  <option value="fixed_quantity">Fixed Quantity</option>
                </select>
              </Field>
              {config.position_size_mode === 'equity_fraction' ? (
                <Field label="Equity Fraction">
                  <input style={s.input} type="number" step="0.01" min="0.01" max="1"
                    value={config.equity_fraction ?? 0.95}
                    onChange={e => setC('equity_fraction', parseFloat(e.target.value) || null)} />
                </Field>
              ) : (
                <Field label="Fixed Quantity">
                  <input style={s.input} type="number" step="1" min="1"
                    value={config.fixed_quantity}
                    onChange={e => setC('fixed_quantity', parseFloat(e.target.value) || 1)} />
                </Field>
              )}
              <Field label="Commission">
                <select style={s.input} value={config.commission_mode}
                  onChange={e => setC('commission_mode', e.target.value as CommissionMode)}>
                  <option value="none">None</option>
                  <option value="fixed">Fixed $</option>
                  <option value="percentage">% per trade</option>
                </select>
              </Field>
              {config.commission_mode !== 'none' && (
                <Field label="Commission Value">
                  <input style={s.input} type="number" step="0.001" min="0"
                    value={config.commission_value}
                    onChange={e => setC('commission_value', parseFloat(e.target.value) || 0)} />
                </Field>
              )}
              <Field label="Slippage">
                <select style={s.input} value={config.slippage_mode}
                  onChange={e => setC('slippage_mode', e.target.value as SlippageMode)}>
                  <option value="none">None</option>
                  <option value="fixed">Fixed $</option>
                  <option value="percentage">%</option>
                </select>
              </Field>
              {config.slippage_mode !== 'none' && (
                <Field label="Slippage Value">
                  <input style={s.input} type="number" step="0.001" min="0"
                    value={config.slippage_value}
                    onChange={e => setC('slippage_value', parseFloat(e.target.value) || 0)} />
                </Field>
              )}
            </div>
          </div>

          {/* Run button */}
          <button
            style={{ ...s.runBtn, opacity: running ? 0.5 : 1 }}
            onClick={handleRun}
            disabled={running}
          >
            {running ? 'Running…' : '▶  Run Backtest'}
          </button>

          {error && <div style={s.error}>{error}</div>}

          {/* Results */}
          {result && (
            <div style={s.results}>
              {/* Quick stats */}
              <div style={s.statRow}>
                <Stat label="Return" value={`${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%`} color={pnlPct >= 0 ? '#66bb6a' : '#ef5350'} />
                <Stat label="Net PnL" value={`$${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}`} color={pnl >= 0 ? '#66bb6a' : '#ef5350'} />
                <Stat label="Trades" value={String(result.summary.total_trades)} />
                <Stat label="Win Rate" value={result.summary.close_long_trades > 0 ? `${winRate.toFixed(1)}%` : '—'} />
                <Stat label="Final Equity" value={`$${result.summary.final_equity.toFixed(2)}`} />
                <Stat label="Rejections" value={String(result.summary.total_rejections)} color={result.summary.total_rejections > 0 ? '#ffa726' : undefined} />
              </div>

              {/* Tabs */}
              <div style={s.tabs}>
                {(['summary', 'trades', 'rejections'] as const).map(tab => (
                  <button key={tab} style={{ ...s.tab, ...(activeTab === tab ? s.tabActive : {}) }}
                    onClick={() => setActiveTab(tab)}>
                    {tab}{tab === 'trades' ? ` (${result.trades.length})` : tab === 'rejections' ? ` (${result.rejections.length})` : ''}
                  </button>
                ))}
              </div>

              {activeTab === 'summary' && (
                <div style={s.summaryGrid}>
                  <SummaryRow label="Bars evaluated"    value={String(result.summary.total_bars)} />
                  <SummaryRow label="Open long trades"  value={String(result.summary.open_long_trades)} />
                  <SummaryRow label="Close long trades" value={String(result.summary.close_long_trades)} />
                  <SummaryRow label="Initial cash"      value={`$${result.summary.initial_cash.toFixed(2)}`} />
                  <SummaryRow label="Final cash"        value={`$${result.summary.final_cash.toFixed(2)}`} />
                  <SummaryRow label="Final equity"      value={`$${result.summary.final_equity.toFixed(2)}`} />
                  <SummaryRow label="Peak equity"       value={`$${result.summary.peak_equity.toFixed(2)}`} />
                  <SummaryRow label="Trough equity"     value={`$${result.summary.trough_equity.toFixed(2)}`} />
                  <SummaryRow label="Realized PnL"      value={`$${result.summary.total_realized_pnl.toFixed(2)}`} />
                  <SummaryRow label="Unrealized PnL"    value={`$${result.summary.final_unrealized_pnl.toFixed(2)}`} />
                  <SummaryRow label="Commission paid"   value={`$${result.summary.total_commission_paid.toFixed(2)}`} />
                  <SummaryRow label="Slippage paid"     value={`$${result.summary.total_slippage_paid.toFixed(2)}`} />
                  <SummaryRow label="Total cost"        value={`$${result.summary.total_cost_paid.toFixed(2)}`} />
                </div>
              )}

              {activeTab === 'trades' && (
                result.trades.length === 0
                  ? <div style={s.empty}>No trades executed.</div>
                  : (
                    <div style={s.tableWrap}>
                      <table style={s.table}>
                        <thead>
                          <tr>
                            {['Bar','Action','Qty','Price','Cash After','PnL','Costs'].map(h => (
                              <th key={h} style={s.th}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {result.trades.map(t => (
                            <tr key={t.trade_id} style={s.tr}>
                              <td style={s.td}>{t.bar_index}</td>
                              <td style={{ ...s.td, color: t.action === 'open_long' ? '#66bb6a' : '#ef5350' }}>
                                {t.action === 'open_long' ? 'BUY' : 'SELL'}
                              </td>
                              <td style={s.td}>{t.quantity}</td>
                              <td style={s.td}>${t.price.toFixed(2)}</td>
                              <td style={s.td}>${t.cash_after.toFixed(2)}</td>
                              <td style={{ ...s.td, color: (t.realized_pnl ?? 0) >= 0 ? '#66bb6a' : '#ef5350' }}>
                                {t.realized_pnl !== null ? `$${t.realized_pnl.toFixed(2)}` : '—'}
                              </td>
                              <td style={s.td}>${t.cost_breakdown.total_cost.toFixed(2)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )
              )}

              {activeTab === 'rejections' && (
                result.rejections.length === 0
                  ? <div style={s.empty}>No rejections.</div>
                  : (
                    <div style={s.tableWrap}>
                      <table style={s.table}>
                        <thead>
                          <tr>
                            {['Bar','Reason','Detail'].map(h => (
                              <th key={h} style={s.th}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {result.rejections.map(r => (
                            <tr key={r.rejection_id} style={s.tr}>
                              <td style={s.td}>{r.bar_index}</td>
                              <td style={{ ...s.td, color: '#ffa726' }}>{r.reason}</td>
                              <td style={s.td}>{r.detail}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <span style={s.fieldLabel}>{label}</span>
      {children}
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={s.stat}>
      <span style={s.statLabel}>{label}</span>
      <span style={{ ...s.statValue, color: color ?? '#d1d4dc' }}>{value}</span>
    </div>
  )
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={s.summaryRow}>
      <span style={s.summaryLabel}>{label}</span>
      <span style={s.summaryValue}>{value}</span>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  container: {
    background:   '#0d0d1a',
    border:       '1px solid #2a2a3e',
    borderRadius: 6,
    fontFamily:   'monospace',
    fontSize:     12,
    color:        '#d1d4dc',
    overflow:     'hidden',
  },
  header: {
    width:          '100%',
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'space-between',
    padding:        '10px 14px',
    background:     'transparent',
    border:         'none',
    cursor:         'pointer',
    color:          '#d1d4dc',
    fontFamily:     'monospace',
    fontSize:       12,
  },
  headerTitle: {
    fontWeight:    700,
    letterSpacing: '0.06em',
    color:         '#7b8cde',
    fontSize:      13,
  },
  chevron: { color: '#4a5568', fontSize: 10 },
  body: {
    padding:       '0 14px 14px',
    display:       'flex',
    flexDirection: 'column',
    gap:           12,
  },
  warn: {
    background:   '#1a1400',
    border:       '1px solid #3a3000',
    borderRadius: 4,
    color:        '#ffa726',
    fontSize:     11,
    padding:      '6px 10px',
  },
  section: {
    display:       'flex',
    flexDirection: 'column',
    gap:           8,
  },
  sectionLabel: {
    color:         '#4a5568',
    fontSize:      10,
    letterSpacing: '0.08em',
    textTransform: 'uppercase' as const,
  },
  grid2: {
    display:             'grid',
    gridTemplateColumns: '1fr 1fr',
    gap:                 8,
  },
  fieldLabel: {
    color:    '#4a5568',
    fontSize: 10,
  },
  input: {
    background:   '#0a0a14',
    border:       '1px solid #2a2a3e',
    borderRadius: 3,
    color:        '#d1d4dc',
    fontFamily:   'monospace',
    fontSize:     12,
    padding:      '4px 7px',
    width:        '100%',
    boxSizing:    'border-box' as const,
  },
  runBtn: {
    background:    '#1a2a4a',
    border:        '1px solid #2a4a7a',
    borderRadius:  4,
    color:         '#7eb8f7',
    cursor:        'pointer',
    fontFamily:    'monospace',
    fontSize:      12,
    fontWeight:    700,
    letterSpacing: '0.05em',
    padding:       '8px 14px',
    width:         '100%',
  },
  error: {
    background:   '#1a0f0f',
    border:       '1px solid #3a2a2a',
    borderRadius: 4,
    color:        '#ef5350',
    fontSize:     11,
    padding:      '6px 10px',
    whiteSpace:   'pre-wrap' as const,
  },
  results: {
    display:       'flex',
    flexDirection: 'column',
    gap:           10,
  },
  statRow: {
    display:             'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap:                 6,
  },
  stat: {
    background:    '#0a0a14',
    border:        '1px solid #1e1e2e',
    borderRadius:  4,
    padding:       '6px 8px',
    display:       'flex',
    flexDirection: 'column',
    gap:           2,
  },
  statLabel: {
    color:    '#4a5568',
    fontSize: 10,
  },
  statValue: {
    fontWeight: 700,
    fontSize:   13,
  },
  tabs: {
    display: 'flex',
    gap:     4,
  },
  tab: {
    background:   '#0a0a14',
    border:       '1px solid #2a2a3e',
    borderRadius: 3,
    color:        '#4a5568',
    cursor:       'pointer',
    fontFamily:   'monospace',
    fontSize:     11,
    padding:      '3px 10px',
  },
  tabActive: {
    borderColor: '#7b8cde',
    color:       '#7b8cde',
  },
  summaryGrid: {
    display:       'flex',
    flexDirection: 'column',
    gap:           3,
  },
  summaryRow: {
    display: 'flex',
    gap:     12,
  },
  summaryLabel: {
    color:    '#4a5568',
    minWidth: 140,
    fontSize: 11,
  },
  summaryValue: {
    color:    '#7a8598',
    fontSize: 11,
  },
  tableWrap: {
    overflowX: 'auto' as const,
    maxHeight: 280,
    overflowY: 'auto' as const,
  },
  table: {
    width:           '100%',
    borderCollapse:  'collapse' as const,
    fontSize:        11,
  },
  th: {
    background:  '#0a0a14',
    borderBottom: '1px solid #2a2a3e',
    color:        '#4a5568',
    fontWeight:   600,
    padding:      '4px 8px',
    textAlign:    'left' as const,
    position:     'sticky' as const,
    top:          0,
  },
  tr: {},
  td: {
    borderBottom: '1px solid #1a1a2a',
    color:        '#7a8598',
    padding:      '4px 8px',
  },
  empty: {
    color:   '#4a5568',
    padding: '8px 0',
    fontSize: 11,
  },
}
