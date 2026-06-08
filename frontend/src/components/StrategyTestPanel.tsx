/**
 * StrategyTestPanel — sidebar panel for selecting, validating, and running a
 * saved Composer draft against the loaded chart.
 *
 * Sections:
 *   1. Draft selector + summary
 *   2. Validate / Run buttons + result
 *   3. Backtest config (collapsible) + Run Backtest button
 */
import { useEffect, useState } from 'react'
import { fetchDrafts, validateDraft } from '../api/drafts'
import { runComposition } from '../api/compositionRun'
import { runBacktest } from '../api/backtestRuns'
import { isAuthError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { CompositionRunResponse } from '../api/compositionRun'
import type { BacktestReport, BacktestRunConfig } from '../types/backtestRuns'
import { DEFAULT_BACKTEST_CONFIG } from '../types/backtestRuns'
import type { StrategyDraftData } from '../types/drafts'
import type { OHLCVCandle } from '../api/marketData'
import type { ResearchSession } from '../types/researchSession'

interface Props {
  candles:               OHLCVCandle[]
  symbol:                string
  timeframe:             string
  sessionContext?:       ResearchSession
  onResult:              (result: CompositionRunResponse) => void
  onBacktestResult:      (report: BacktestReport) => void
  onNavigateToComposer?: () => void
}

export function StrategyTestPanel({ candles, symbol, timeframe, sessionContext, onResult, onBacktestResult, onNavigateToComposer }: Props) {
  const { logout } = useAuth()
  const [drafts,       setDrafts]       = useState<StrategyDraftData[]>([])
  const [listLoading,  setListLoading]  = useState(true)
  const [listError,    setListError]    = useState<string | null>(null)
  const [selectedId,   setSelectedId]   = useState<string>('')
  const [selected,     setSelected]     = useState<StrategyDraftData | null>(null)
  const [validating,   setValidating]   = useState(false)
  const [validation,   setValidation]   = useState<{ valid: boolean; errors: string[] } | null>(null)
  const [running,      setRunning]      = useState(false)
  const [runError,     setRunError]     = useState<string | null>(null)
  const [lastResult,   setLastResult]   = useState<CompositionRunResponse | null>(null)

  // Backtest
  const [btOpen,    setBtOpen]    = useState(false)
  const [btConfig,  setBtConfig]  = useState<BacktestRunConfig>(DEFAULT_BACKTEST_CONFIG)
  const [btRunning, setBtRunning] = useState(false)
  const [btError,   setBtError]   = useState<string | null>(null)

  useEffect(() => {
    setListLoading(true)
    fetchDrafts()
      .then(r => setDrafts(r.drafts.filter(d => d.enabled)))
      .catch(e => {
        if (isAuthError(e)) { logout(); return }
        setListError(e instanceof Error ? e.message : 'Failed to load strategies')
      })
      .finally(() => setListLoading(false))
  }, [logout])

  useEffect(() => {
    setSelected(drafts.find(d => d.draft_id === selectedId) ?? null)
    setValidation(null)
    setRunError(null)
    setLastResult(null)
    setBtError(null)
    setBtOpen(false)
  }, [selectedId, drafts])

  async function handleValidate() {
    if (!selectedId) return
    setValidating(true)
    setValidation(null)
    try {
      setValidation(await validateDraft(selectedId))
    } catch (e) {
      if (isAuthError(e)) { logout(); return }
      setValidation({ valid: false, errors: [e instanceof Error ? e.message : 'Validation failed'] })
    } finally {
      setValidating(false)
    }
  }

  async function handleRun() {
    if (!selectedId || !candles.length) return
    setRunning(true)
    setRunError(null)
    setLastResult(null)
    setBtError(null)
    try {
      const result = await runComposition(selectedId, symbol, timeframe, candles)
      setLastResult(result)
      onResult(result)
    } catch (e) {
      if (isAuthError(e)) { logout(); return }
      setRunError(e instanceof Error ? e.message : 'Run failed')
    } finally {
      setRunning(false)
    }
  }

  async function handleRunBacktest() {
    if (!selectedId || !candles.length) return
    setBtRunning(true)
    setBtError(null)
    try {
      const response = await runBacktest(selectedId, symbol, timeframe, candles, btConfig, {
        source_mode:   sessionContext?.sourceMode ?? undefined,
        provider_name: sessionContext?.providerName ?? undefined,
        catalog_id:    sessionContext?.catalogId ?? undefined,
      })
      onBacktestResult(response.report)
    } catch (e) {
      if (isAuthError(e)) { logout(); return }
      setBtError(e instanceof Error ? e.message : 'Backtest failed')
    } finally {
      setBtRunning(false)
    }
  }

  const hasData  = candles.length > 0
  const hasDraft = !!selectedId
  const isValid  = validation?.valid === true
  const canRun   = hasData && hasDraft && !running && !validating && (validation === null || isValid)
  const canBt    = hasData && hasDraft && !btRunning && !running

  const entryCount = selected?.semantics?.entry_rules.length ?? 0
  const exitCount  = selected?.semantics?.exit_rules.length ?? 0
  const toolCount  = selected?.toolset.tools.length ?? 0

  return (
    <div style={s.panel}>
      {/* ── Section title ── */}
      <div style={s.sectionTitle}>
        <span>Strategy Test</span>
        {onNavigateToComposer && (
          <button
            data-testid="goto-composer-btn"
            style={s.composerShortcut}
            onClick={onNavigateToComposer}
            title="Open Strategy Builder"
          >
            Strategy Builder
          </button>
        )}
      </div>

      {/* ── Data source context ── */}
      {sessionContext?.sourceMode && (
        <div data-testid="data-source-context" style={s.sourceCtx}>
          <span style={s.sourceKey}>data</span>
          <span style={s.sourceVal}>
            {sessionContext.sourceMode === 'catalog'
              ? `catalog · ${sessionContext.catalogDisplayName ?? sessionContext.catalogId?.slice(0, 8) ?? '?'}`
              : sessionContext.providerName ?? 'provider'}
          </span>
          <span style={s.sourceSep}>·</span>
          <span style={s.sourceVal}>{sessionContext.symbol}</span>
          <span style={s.sourceSep}>·</span>
          <span style={s.sourceVal}>{sessionContext.timeframe}</span>
          <span style={s.sourceSep}>·</span>
          <span style={s.sourceVal}>{sessionContext.candleCount.toLocaleString()} bars</span>
        </div>
      )}

      {/* ── Draft selector ── */}
      <div style={s.group}>
        {listLoading && <div style={s.hint}>Loading…</div>}
        {listError   && <div style={s.error}>{listError}</div>}
        {!listLoading && !listError && (
          drafts.length === 0
            ? <div style={s.hint}>No saved strategies. Create one in the Strategy Builder.</div>
            : <select style={s.select} value={selectedId} onChange={e => setSelectedId(e.target.value)}>
                <option value="">— select strategy —</option>
                {drafts.map(d => (
                  <option key={d.draft_id} value={d.draft_id}>{d.display_name}</option>
                ))}
              </select>
        )}

        {/* Draft summary */}
        {selected && (
          <div style={s.summary}>
            <div style={s.summaryName}>{selected.display_name}</div>
            <div style={s.summaryMeta}>
              <span>{toolCount} tool{toolCount !== 1 ? 's' : ''}</span>
              <span style={s.dot}>·</span>
              <span>{entryCount} entry</span>
              <span style={s.dot}>·</span>
              <span>{exitCount} exit</span>
            </div>
            {selected.toolset.tools.length > 0 && (
              <div style={s.tags}>
                {selected.toolset.tools.map(t => (
                  <span key={t.instance_id} style={s.tag}>{t.instance_id}</span>
                ))}
              </div>
            )}
          </div>
        )}

        {hasDraft && !hasData && (
          <div style={s.hint}>Fetch data from Chart or load a dataset from Datasets to continue.</div>
        )}
        {!hasDraft && !listLoading && drafts.length > 0 && (
          <div style={s.hint}>Select a strategy to begin.</div>
        )}
      </div>

      {/* ── Validate + Run ── */}
      {hasDraft && (
        <div style={s.group}>
          {validation && (
            <div style={{ ...s.validBox, borderColor: validation.valid ? '#1e3a1e' : '#3a1e1e' }}>
              <span style={{ color: validation.valid ? '#66bb6a' : '#ef5350', fontWeight: 700 }}>
                {validation.valid ? '✓ valid' : '✗ invalid'}
              </span>
              {validation.errors.map((e, i) => (
                <div key={i} style={s.validErr}>{e}</div>
              ))}
            </div>
          )}
          {runError && <div style={s.error}>{runError}</div>}

          <div style={s.btnRow}>
            <button
              style={{ ...s.btn, ...s.validateBtn, opacity: validating || running ? 0.5 : 1 }}
              onClick={handleValidate}
              disabled={validating || running}
            >
              {validating ? '…' : 'Validate'}
            </button>
            <button
              style={{ ...s.btn, ...s.runBtn, flex: 1, opacity: canRun ? 1 : 0.4 }}
              onClick={handleRun}
              disabled={!canRun}
            >
              {running ? 'Running…' : '▶ Run'}
            </button>
          </div>

          {/* Run result */}
          {lastResult && (
            <div style={s.result}>
              <ResultRow label="status" value={lastResult.status}
                color={lastResult.status === 'success' ? '#66bb6a' : '#ffa726'} />
              <ResultRow label="signals"    value={String(lastResult.signals.length)} />
              <ResultRow label="entry"
                value={String(lastResult.signals.filter(s => s.signal_type === 'long').length)}
                color="#66bb6a" />
              <ResultRow label="exit"
                value={String(lastResult.signals.filter(s => s.signal_type === 'exit').length)}
                color="#ef5350" />
              <ResultRow label="indicators" value={String(lastResult.indicators.length)} />
              {lastResult.warnings.map((w, i) => (
                <div key={i} style={s.warn}>{w}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Backtest config (collapsible) ── */}
      {hasDraft && hasData && (
        <div style={s.group}>
          <button style={s.btToggle} onClick={() => setBtOpen(o => !o)}>
            <span>Backtest</span>
            <span style={s.btChevron}>{btOpen ? '▲' : '▼'}</span>
          </button>

          {btOpen && (
            <div style={s.btBody}>
              <ConfigField label="Initial Equity ($)">
                <input
                  data-testid="stp-equity-input"
                  type="number" style={s.cfgInput}
                  value={btConfig.initial_equity} min={100} step={100}
                  onChange={e => setBtConfig(c => ({ ...c, initial_equity: parseFloat(e.target.value) || 10000 }))}
                />
              </ConfigField>

              <ConfigField label="Position Size">
                <div style={{ display: 'flex', gap: 4 }}>
                  <select
                    style={{ ...s.cfgInput, flex: 1 }}
                    value={btConfig.position_size_mode}
                    onChange={e => setBtConfig(c => ({
                      ...c, position_size_mode: e.target.value as BacktestRunConfig['position_size_mode'],
                    }))}
                  >
                    <option value="equity_fraction">% of Equity</option>
                    <option value="fixed_quantity">Fixed Units</option>
                  </select>
                  {btConfig.position_size_mode === 'equity_fraction' ? (
                    <input
                      data-testid="stp-fraction-input"
                      type="number" style={{ ...s.cfgInput, width: 52 }}
                      value={Math.round((btConfig.equity_fraction ?? 0.95) * 100)}
                      min={1} max={100} step={1}
                      onChange={e => setBtConfig(c => ({ ...c, equity_fraction: parseFloat(e.target.value) / 100 || 0.95 }))}
                    />
                  ) : (
                    <input
                      type="number" style={{ ...s.cfgInput, width: 52 }}
                      value={btConfig.fixed_quantity} min={1} step={1}
                      onChange={e => setBtConfig(c => ({ ...c, fixed_quantity: parseFloat(e.target.value) || 1 }))}
                    />
                  )}
                  <span style={s.cfgUnit}>
                    {btConfig.position_size_mode === 'equity_fraction' ? '%' : 'u'}
                  </span>
                </div>
              </ConfigField>

              <ConfigField label="Commission">
                <div style={{ display: 'flex', gap: 4 }}>
                  <select
                    style={{ ...s.cfgInput, flex: 1 }}
                    value={btConfig.commission_mode}
                    onChange={e => setBtConfig(c => ({
                      ...c, commission_mode: e.target.value as BacktestRunConfig['commission_mode'],
                    }))}
                  >
                    <option value="none">None</option>
                    <option value="percentage">% per trade</option>
                    <option value="fixed">Fixed $</option>
                  </select>
                  {btConfig.commission_mode !== 'none' && (
                    <input
                      type="number" style={{ ...s.cfgInput, width: 60 }}
                      value={btConfig.commission_value} min={0} step={0.001}
                      onChange={e => setBtConfig(c => ({ ...c, commission_value: parseFloat(e.target.value) || 0 }))}
                    />
                  )}
                </div>
              </ConfigField>

              {btError && <div style={s.error}>{btError}</div>}

              <button
                style={{ ...s.btn, ...s.btRunBtn, opacity: canBt ? 1 : 0.4 }}
                onClick={handleRunBacktest}
                disabled={!canBt}
              >
                {btRunning ? 'Running…' : '▶ Run Backtest'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ResultRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
      <span style={{ color: '#4a5568' }}>{label}</span>
      <span style={{ color: color ?? '#7a8598', fontWeight: color ? 600 : 400 }}>{value}</span>
    </div>
  )
}

function ConfigField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <span style={{ fontSize: 10, color: '#4a5568', letterSpacing: '0.04em' }}>{label}</span>
      {children}
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  panel: {
    display:       'flex',
    flexDirection: 'column',
    fontFamily:    'monospace',
    fontSize:      12,
    color:         '#d1d4dc',
  },
  sectionTitle: {
    fontSize:      10,
    fontWeight:    700,
    color:         '#4a5568',
    letterSpacing: '0.09em',
    padding:       '14px 14px 8px',
    borderBottom:  '1px solid #1e1e30',
    display:       'flex',
    alignItems:    'center',
    justifyContent: 'space-between',
  },
  composerShortcut: {
    background:    'transparent',
    border:        '1px solid #1e2a3a',
    borderRadius:  3,
    color:         '#3a6080',
    cursor:        'pointer',
    fontFamily:    'monospace',
    fontSize:      9,
    letterSpacing: '0.04em',
    padding:       '2px 7px',
  },
  sourceCtx: {
    display:      'flex',
    alignItems:   'center',
    gap:          5,
    padding:      '5px 14px',
    borderBottom: '1px solid #0f0f20',
    flexWrap:     'wrap' as const,
  },
  sourceKey: {
    fontSize:      9,
    color:         '#2a3040',
    fontFamily:    'monospace',
    letterSpacing: '0.04em',
  },
  sourceVal: {
    fontSize:   9,
    color:      '#3a4a5a',
    fontFamily: 'monospace',
  },
  sourceSep: {
    fontSize: 9,
    color:    '#1a1a28',
  },
  group: {
    display:       'flex',
    flexDirection: 'column',
    gap:           8,
    padding:       '12px 14px',
    borderBottom:  '1px solid #1a1a28',
  },
  select: {
    background:   '#0a0a14',
    border:       '1px solid #2a2d3e',
    borderRadius: 3,
    color:        '#d1d4dc',
    fontFamily:   'monospace',
    fontSize:     12,
    padding:      '5px 7px',
    width:        '100%',
  },
  summary: {
    background:    '#0a0a14',
    border:        '1px solid #1a1a28',
    borderRadius:  4,
    padding:       '8px 10px',
    display:       'flex',
    flexDirection: 'column',
    gap:           5,
  },
  summaryName: { color: '#c0c8dc', fontWeight: 600, fontSize: 12 },
  summaryMeta: { display: 'flex', gap: 5, fontSize: 11, color: '#4a5568' },
  dot:         { color: '#2a2a3e' },
  tags:        { display: 'flex', flexWrap: 'wrap' as const, gap: 4 },
  tag: {
    background:   '#12122a',
    color:        '#6a7abe',
    fontSize:     10,
    padding:      '1px 6px',
    borderRadius: 3,
  },
  hint:  { color: '#3a4255', fontSize: 11 },
  error: {
    background:   '#1a0f0f',
    border:       '1px solid #3a1e1e',
    borderRadius: 3,
    color:        '#ef5350',
    fontSize:     11,
    padding:      '6px 8px',
    whiteSpace:   'pre-wrap' as const,
  },
  validBox: {
    border:        '1px solid',
    borderRadius:  3,
    padding:       '6px 8px',
    display:       'flex',
    flexDirection: 'column',
    gap:           3,
    fontSize:      11,
  },
  validErr: { color: '#ef9090', fontSize: 11 },
  btnRow: { display: 'flex', gap: 6 },
  btn: {
    border:        '1px solid',
    borderRadius:  3,
    cursor:        'pointer',
    fontFamily:    'monospace',
    fontSize:      11,
    fontWeight:    600,
    letterSpacing: '0.04em',
    padding:       '6px 10px',
  },
  validateBtn: { background: '#0a0a1a', borderColor: '#1e2a3a', color: '#5a7898' },
  runBtn:      { background: '#0d1e2e', borderColor: '#1e3a5a', color: '#7eb8f7' },
  result: {
    background:    '#0a0a14',
    border:        '1px solid #1a1a28',
    borderRadius:  3,
    padding:       '8px 10px',
    display:       'flex',
    flexDirection: 'column',
    gap:           4,
  },
  warn: { color: '#ffa726', fontSize: 10 },

  // Backtest
  btToggle: {
    display:       'flex',
    justifyContent: 'space-between',
    alignItems:    'center',
    background:    'transparent',
    border:        '1px solid #1e1e30',
    borderRadius:  3,
    color:         '#4a5a7a',
    cursor:        'pointer',
    fontFamily:    'monospace',
    fontSize:      11,
    fontWeight:    600,
    letterSpacing: '0.06em',
    padding:       '6px 10px',
    width:         '100%',
  },
  btChevron: { fontSize: 9, color: '#3a4a5a' },
  btBody: {
    display:       'flex',
    flexDirection: 'column',
    gap:           8,
    paddingTop:    4,
  },
  cfgInput: {
    background:   '#0a0a14',
    border:       '1px solid #1e1e30',
    borderRadius: 3,
    color:        '#d1d4dc',
    fontFamily:   'monospace',
    fontSize:     11,
    padding:      '4px 6px',
    width:        '100%',
    boxSizing:    'border-box' as const,
  },
  cfgUnit: { color: '#3a4255', fontSize: 10, alignSelf: 'center', flexShrink: 0 },
  btRunBtn: {
    background:  '#0d0d20',
    borderColor: '#2a2a50',
    color:       '#7a7abe',
    width:       '100%',
    textAlign:   'center' as const,
  },
}
