import { useState, useEffect, useMemo, useRef } from 'react'
import Controls from './components/Controls'
import Chart, { type ChartHandle } from './components/Chart'
import { DraftWorkspace } from './components/DraftWorkspace'
import { StrategyTestPanel } from './components/StrategyTestPanel'
import { BacktestReportPage } from './components/BacktestReportPage'
import { BacktestHistoryPanel } from './components/BacktestHistoryPanel'
import { AdminConsole } from './components/AdminConsole'
import { CredentialManager } from './components/CredentialManager'
import { CatalogManager } from './components/CatalogManager'
import { ForwardTestPanel } from './components/ForwardTestPanel'
import { PaperTradingPanel } from './components/PaperTradingPanel'
import { StrategyLifecycleDashboard } from './components/StrategyLifecycleDashboard'
import { EngineRegistryPanel } from './components/EngineRegistryPanel'
import { SessionProvenanceStrip } from './components/SessionProvenanceStrip'
import { StrategyContextProvider } from './context/StrategyContext'
import { StrategyContextBar } from './components/StrategyContextBar'
import { Sidebar } from './components/navigation/Sidebar'
import { LoginPage } from './components/LoginPage'
import { RegisterPage } from './components/RegisterPage'
import { AuthGuard } from './components/AuthGuard'
import { SubscriptionGate } from './components/SubscriptionGate'
import { useAuth } from './auth/AuthContext'
import { useSessionPersistence } from './hooks/useSessionPersistence'
import { isAuthError, isSubscriptionExpiredError } from './api/client'
import { fetchOHLCV } from './api/marketData'
import { fetchBacktestReport, promoteDraftToBacktested } from './api/backtestRuns'
import type { OHLCVCandle, MarketDataParams, DatasetFetchMetadata } from './api/marketData'
import type { CompositionRunResponse } from './api/compositionRun'
import type { BacktestReport } from './types/backtestRuns'
import type { StrategyOverlay, SignalType } from './types/strategy'
import type { CatalogOHLCVResponse, CatalogEntry } from './types/catalog'
import type { ResearchSession } from './types/researchSession'
import type { ForwardTestPrefill } from './types/forwardTesting'
import { ChartIndicatorPanel } from './components/ChartIndicatorPanel'
import type { ChartIndicatorPanelHandle } from './components/ChartIndicatorPanel'
import type { IndicatorInstance } from './types/chartIndicators'
import { useChartSettings } from './hooks/useChartSettings'
import ChartHeader from './components/ChartHeader'
import type { SelectedAsset } from './components/AssetResolverInput'
import { fetchMarketStructure } from './api/marketStructure'
import type { StructureResult } from './types/marketStructure'

type Status     = 'idle' | 'loading' | 'success' | 'error'
type ActiveView = 'chart' | 'composer' | 'credentials' | 'report' | 'admin' | 'datasets' | 'history' | 'forward-test' | 'paper-trading' | 'lifecycle' | 'research-engines'
type AuthView   = 'login' | 'register'

// Workflow pages where the persistent Strategy Context Bar is shown (NAV-UX-3A/3B).
// Hidden on Research (chart/symbol-centric), Settings (credentials/datasets),
// and Admin (not strategy-scoped). Internal view keys are stable across nav label changes.
const CONTEXT_BAR_VIEWS = new Set<ActiveView>([
  'composer',       // → Strategy
  'history',        // → Backtest
  'forward-test',   // → Forward Test
  'paper-trading',  // → Paper Trading
  'lifecycle',      // → Lifecycle
  'report',         // Backtest Report (transient, not in nav)
])

export default function App() {
  const { user, logout, refreshUser } = useAuth()
  const { save: saveSession, load: loadSession } = useSessionPersistence()
  const [authView, setAuthView] = useState<AuthView>('login')
  const [activeView, setActiveView] = useState<ActiveView>('chart')

  const [candles,       setCandles]       = useState<OHLCVCandle[]>([])
  const [status,        setStatus]        = useState<Status>('idle')
  const [error,         setError]         = useState<string | null>(null)
  const [params,        setParams]        = useState<MarketDataParams | null>(null)
  const [overlay,       setOverlay]       = useState<StrategyOverlay | null>(null)
  const [fetchMetadata, setFetchMetadata] = useState<DatasetFetchMetadata | null>(null)

  const [backtestReport,     setBacktestReport]     = useState<BacktestReport | null>(null)
  const [catalogMeta,        setCatalogMeta]        = useState<{ response: CatalogOHLCVResponse; entry: CatalogEntry } | null>(null)
  const [resumableRunId,     setResumableRunId]     = useState<string | null>(null)
  const [resuming,           setResuming]           = useState(false)
  const [forwardTestPrefill, setForwardTestPrefill] = useState<ForwardTestPrefill | null>(null)

  // Chart-wide visualization preferences (CHART-SETTINGS-1A)
  const { settings: chartSettings, updateSettings: updateChartSettings } = useChartSettings()
  // Chart header identity — lifted from Controls when user selects an asset
  const [selectedAsset, setSelectedAsset] = useState<SelectedAsset | null>(null)

  // Chart-UX-3C.1: full indicator instances (visibility, colors, artifacts)
  const [indicatorInstances, setIndicatorInstances] = useState<IndicatorInstance[]>([])
  // Chart-UX-3C.5: indicator panel ref (for Chart legend/header action callbacks)
  const indicatorPanelRef = useRef<ChartIndicatorPanelHandle>(null)
  // CHART-TOOLBAR-1A: screenshot handle — enables the screenshot button when chart is loaded
  const chartHandleRef = useRef<ChartHandle | null>(null)
  // Chart-UX-3C.5: hovered instance for ownership feedback (sidebar ↔ chart legend)
  const [hoveredInstanceId, setHoveredInstanceId] = useState<string | null>(null)

  // MS-2: Market structure overlay state
  const [structureResult, setStructureResult] = useState<StructureResult | null>(null)
  // Fingerprint of the candle set we last fetched structure for (avoids re-fetch on toggle)
  const structureFingerprintRef = useRef<string>('')

  // Derived chart props — memoized to avoid spurious Chart effect re-runs
  const visibleArtifacts = useMemo(() =>
    indicatorInstances
      .filter(i => i.visible && i.artifact !== null)
      .map(i => {
        const artifact = i.artifact!
        // Patch series.default_color and line_style with user overrides so Chart
        // doesn't need separate override props.
        const hasColorOverrides = Object.keys(i.seriesColors).length > 0
        const hasStyleOverrides = Object.keys(i.seriesLineStyles).length > 0
        if (!hasColorOverrides && !hasStyleOverrides) return artifact
        return {
          ...artifact,
          series: artifact.series.map(s => ({
            ...s,
            default_color: i.seriesColors[s.series_id] ?? s.default_color,
            line_style:    i.seriesLineStyles[s.series_id],
          })),
        }
      }),
    [indicatorInstances]
  )

  const instanceColorMap = useMemo(
    () => new Map(indicatorInstances.map(i => [i.instanceId, i.instanceColor])),
    [indicatorInstances]
  )

  const instanceLabelMap = useMemo(
    () => new Map(indicatorInstances.map(i => [i.instanceId, i.instanceLabel])),
    [indicatorInstances]
  )

  const instanceVisibleMap = useMemo(
    () => new Map(indicatorInstances.map(i => [i.instanceId, i.visible])),
    [indicatorInstances]
  )

  const volumeColorModes = useMemo(
    () => {
      const m = new Map<string, string>()
      for (const i of indicatorInstances) {
        if (i.parameters.volume_color_mode === 'single') {
          m.set(i.instanceId, String(i.parameters.volume_color ?? '#26a69a'))
        }
      }
      return m
    },
    [indicatorInstances]
  )

  // Restore lightweight session context on mount
  useEffect(() => {
    const s = loadSession()
    if (!s) return
    // Restore tab — but not 'report' without a loaded report
    if (s.activeView && s.activeView !== 'report') {
      setActiveView(s.activeView as ActiveView)
    }
    // Offer to resume the last report if one exists from a prior run
    if (s.latestRunId) {
      setResumableRunId(s.latestRunId)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // MS-2: Fetch market structure when candles load and any structure toggle is on.
  // Fingerprint prevents re-fetching when only toggles change (data doesn't change).
  // All structure toggle states are in deps so the first toggle-on triggers the fetch.
  useEffect(() => {
    const s = chartSettings.structure
    const needsStructure = s.showMinorStructure || s.showMainStructure ||
                           s.showStructureLabels || s.showDebugMetadata ||
                           s.showBos || s.showChoch

    if (!needsStructure || candles.length === 0) return

    const fp = `${candles.length}::${candles[0].timestamp}::${candles[candles.length - 1].timestamp}`
    if (fp === structureFingerprintRef.current) return  // same candles, already fetched

    structureFingerprintRef.current = fp
    setStructureResult(null)

    fetchMarketStructure(candles)
      .then(result => {
        // Guard against stale fetch completing after candles changed
        if (structureFingerprintRef.current === fp) setStructureResult(result)
      })
      .catch(() => {
        if (structureFingerprintRef.current === fp) structureFingerprintRef.current = ''
      })
  }, [ // eslint-disable-line react-hooks/exhaustive-deps
    candles,
    chartSettings.structure.showMinorStructure,
    chartSettings.structure.showMainStructure,
    chartSettings.structure.showStructureLabels,
    chartSettings.structure.showDebugMetadata,
    chartSettings.structure.showBos,
    chartSettings.structure.showChoch,
  ])

  // Clear structure result when candles change (new dataset invalidates cached result)
  useEffect(() => {
    structureFingerprintRef.current = ''
    setStructureResult(null)
  }, [candles]) // eslint-disable-line react-hooks/exhaustive-deps

  // Persist session context whenever key state changes
  useEffect(() => {
    saveSession({
      sourceMode:         catalogMeta ? 'catalog' : (status === 'success' ? 'provider' : null),
      symbol:             catalogMeta?.entry.symbol ?? params?.symbol ?? '',
      timeframe:          catalogMeta?.entry.timeframe ?? params?.timeframe ?? '',
      providerName:       fetchMetadata?.provider ?? null,
      catalogId:          catalogMeta?.entry.catalog_id ?? null,
      catalogDisplayName: catalogMeta?.entry.display_name ?? null,
      latestRunId:        backtestReport?.run.run_id ?? resumableRunId,
      activeView,
    })
  }, [catalogMeta, status, params, fetchMetadata, backtestReport, activeView]) // eslint-disable-line react-hooks/exhaustive-deps

  const session: ResearchSession = {
    sourceMode:          catalogMeta ? 'catalog' : (status === 'success' ? 'provider' : null),
    symbol:              catalogMeta?.entry.symbol ?? params?.symbol ?? '',
    timeframe:           catalogMeta?.entry.timeframe ?? params?.timeframe ?? '',
    candleCount:         candles.length,
    providerName:        fetchMetadata?.provider ?? null,
    catalogId:           catalogMeta?.entry.catalog_id ?? null,
    catalogDisplayName:  catalogMeta?.entry.display_name ?? null,
    latestBacktestRunId: backtestReport?.run.run_id ?? null,
    latestDraftId:       backtestReport?.run.draft_id ?? null,
    latestDraftName:     backtestReport?.run.draft_name ?? null,
  }

  const sourceLabel = session.sourceMode === 'catalog'
    ? `catalog · ${session.catalogDisplayName ?? session.catalogId?.slice(0, 8)} · ${session.symbol} · ${session.timeframe}`
    : session.sourceMode === 'provider'
      ? `${session.providerName ?? 'provider'} · ${session.symbol} · ${session.timeframe}`
      : null

  async function handleFetch(p: MarketDataParams) {
    setStatus('loading')
    setError(null)
    setParams(p)
    setOverlay(null)
    setFetchMetadata(null)
    setCatalogMeta(null)
    setIndicatorInstances([])
    try {
      const resp = await fetchOHLCV(p)
      setCandles(resp.candles)
      setFetchMetadata(resp.fetch_metadata ?? null)
      setStatus('success')
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      if (isSubscriptionExpiredError(err)) { await refreshUser(); return }
      setError(err instanceof Error ? err.message : 'Unknown error')
      setStatus('error')
      setCandles([])
    }
  }

  function handleCompositionResult(result: CompositionRunResponse) {
    setOverlay({
      signals: result.signals
        .filter(s => s.timestamp !== null)
        .map(s => ({
          timestamp:          s.timestamp as string,
          symbol:             s.symbol,
          timeframe:          s.timeframe,
          signal_type:        s.signal_type as SignalType,
          entry_reference:    0,
          invalidation_level: 0,
        })),
      forecast: null,
      indicators: result.indicators.map(ind => ({
        name:        ind.name,
        kind:        ind.kind,
        pane:        ind.pane,
        price_scale: ind.price_scale,
        color:       ind.color,
        points:      ind.points
          .filter(p => p.timestamp !== null)
          .map(p => ({ timestamp: p.timestamp as string, value: p.value })),
      })),
    })
  }

  function clearStrategyResults() {
    setOverlay(null)
  }

  function handleBacktestResult(report: BacktestReport) {
    setBacktestReport(report)
    setResumableRunId(null)  // current report supersedes the stored resumable run
    setActiveView('report')
  }

  async function handlePromoteDraft(runId: string, draftId: string) {
    // Returns the updated draft so BacktestReportPage can call ctx.updateDraft()
    // to advance the context bar immediately (NAV-UX-3E).
    return promoteDraftToBacktested(runId, draftId)
  }

  function handleStartForwardTest(prefill: ForwardTestPrefill): void {
    setForwardTestPrefill(prefill)
    setActiveView('forward-test')
  }

  function handlePrefillConsumed(): void {
    setForwardTestPrefill(null)
  }

  async function handleResumeReport() {
    if (!resumableRunId) return
    setResuming(true)
    try {
      const report = await fetchBacktestReport(resumableRunId)
      setBacktestReport(report)
      setResumableRunId(null)
      setActiveView('report')
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      // Run no longer exists or access denied — clear the stale id silently
      setResumableRunId(null)
    } finally {
      setResuming(false)
    }
  }

  function handleCatalogLoad(response: CatalogOHLCVResponse, entry: CatalogEntry) {
    setCandles(response.candles as unknown as OHLCVCandle[])
    setFetchMetadata(null)
    setCatalogMeta({ response, entry })
    setOverlay(null)
    setIndicatorInstances([])
    setStatus('success')
    setError(null)
    setActiveView('chart')
  }

  const authFallback = authView === 'login'
    ? <LoginPage onNavigateRegister={() => setAuthView('register')} />
    : <RegisterPage onNavigateLogin={() => setAuthView('login')} />

  return (
    <AuthGuard fallback={authFallback}>
      <SubscriptionGate>
      <StrategyContextProvider>
      <div style={st.app}>

        {/* ── Global header — app identity and account only ── */}
        <header style={st.header}>
          <span style={st.logo}>QuantLab</span>
          <span style={st.tagline}>Research-first strategy platform</span>
          {user && (
            <div style={st.userArea}>
              <span style={st.username}>{user.username}</span>
              <button style={st.logoutBtn} onClick={logout}>Sign out</button>
            </div>
          )}
        </header>

        {/* ── Sidebar + Content Layout ── */}
        <div style={st.mainLayout}>
          <Sidebar
            activeView={activeView}
            onNavigate={(view) => setActiveView(view as ActiveView)}
            isAdmin={user?.role === 'admin' || user?.role === 'superadmin' || false}
          />

          {/* ── Main content area ── */}
          <div style={st.content}>
            {/* ── Session provenance strip — metadata hidden on chart view (shown in ChartHeader) ── */}
            <SessionProvenanceStrip
              session={session}
              onNavigateToReport={backtestReport ? () => setActiveView('report') : undefined}
              onResumeReport={resumableRunId && !backtestReport ? handleResumeReport : undefined}
              resuming={resuming}
              hideMetadata={activeView === 'chart'}
            />

            {/* ── Persistent strategy context bar (workflow pages only) ── */}
            {CONTEXT_BAR_VIEWS.has(activeView) && (
              <StrategyContextBar
                onStrategyChange={() => {
                  // Changing strategy invalidates a report belonging to the previous
                  // strategy. Navigate back to Backtest History to avoid showing a
                  // report that no longer matches the selected strategy.
                  if (activeView === 'report') {
                    setBacktestReport(null)
                    setActiveView('history')
                  }
                }}
              />
            )}

            {/* ── History ── */}
            {activeView === 'history' && (
              <div style={st.fill}>
                <BacktestHistoryPanel
                  onReportLoaded={(report) => { setBacktestReport(report); setActiveView('report') }}
                />
              </div>
            )}

            {/* ── Forward Testing ── */}
            {activeView === 'forward-test' && (
              <div style={{ ...st.fill, overflowY: 'auto' }}>
                <ForwardTestPanel
                  prefill={forwardTestPrefill}
                  onPrefillConsumed={handlePrefillConsumed}
                />
              </div>
            )}

            {/* ── Paper Trading ── */}
            {activeView === 'paper-trading' && (
              <div style={{ ...st.fill, overflowY: 'auto' }}>
                <PaperTradingPanel />
              </div>
            )}

            {/* ── Strategy Lifecycle Dashboard ── */}
            {activeView === 'lifecycle' && (
              <div style={{ ...st.fill, overflowY: 'auto' }}>
                <StrategyLifecycleDashboard
                  onNavigateToComposer={() => setActiveView('composer')}
                  onNavigateToHistory={() => setActiveView('history')}
                  onNavigateToForwardTest={() => setActiveView('forward-test')}
                  onNavigateToPaperTrading={() => setActiveView('paper-trading')}
                  onNavigateToForwardTestWithPrefill={handleStartForwardTest}
                />
              </div>
            )}

            {/* ── Composer ── */}
            {activeView === 'composer' && (
              <div style={st.fill}>
                <DraftWorkspace />
              </div>
            )}

            {/* ── Settings (Data Providers + Dataset Catalog + Research Engines) ── */}
            {(activeView === 'credentials' || activeView === 'datasets' || activeView === 'research-engines') && (
              <div style={{ ...st.fill, flexDirection: 'column' }}>
                <div style={st.settingsSubBar}>
                  <NavTab
                    label="Data Providers"
                    active={activeView === 'credentials'}
                    onClick={() => setActiveView('credentials')}
                  />
                  <NavTab
                    label="Dataset Catalog"
                    active={activeView === 'datasets'}
                    onClick={() => setActiveView('datasets')}
                  />
                  <NavTab
                    label="Research Engines"
                    active={activeView === 'research-engines'}
                    onClick={() => setActiveView('research-engines')}
                  />
                </div>
                {activeView === 'credentials' && (
                  <div style={{ flex: 1, overflowY: 'auto' }}>
                    <CredentialManager />
                  </div>
                )}
                {activeView === 'datasets' && (
                  <div style={{ flex: 1, overflowY: 'auto' }}>
                    <CatalogManager onLoadIntoChart={handleCatalogLoad} />
                  </div>
                )}
                {activeView === 'research-engines' && (
                  <div style={{ flex: 1, overflow: 'hidden' }}>
                    <EngineRegistryPanel />
                  </div>
                )}
              </div>
            )}

            {/* ── Admin Console — visible only when role === 'admin' or 'superadmin' ── */}
            {activeView === 'admin' && (
              <div style={st.fill}>
                <AdminConsole />
              </div>
            )}

            {/* ── Report (transient — not in nav, accessed via Backtest history or provenance strip) ── */}
            {activeView === 'report' && backtestReport && (
              <div style={st.fill}>
                <BacktestReportPage
                  report={backtestReport}
                  onBack={() => setActiveView('history')}
                  sourceLabel={sourceLabel}
                  onNavigateToComposer={() => setActiveView('composer')}
                  onPromoteDraft={handlePromoteDraft}
                  onStartForwardTest={handleStartForwardTest}
                />
              </div>
            )}

            {/*
              ── Chart view ──
              Kept in the DOM at all times (display:none when inactive) so the
              lightweight-charts instance, candle data, and overlay survive view switches.
            */}
            <div style={{ ...st.fill, display: activeView === 'chart' ? 'flex' : 'none' }}>

              {/* Left sidebar */}
              <aside style={st.sidebar}>
                <Controls
                  onFetch={handleFetch}
                  loading={status === 'loading'}
                  onAssetSelect={setSelectedAsset}
                />
                <StrategyTestPanel
                  candles={candles}
                  symbol={catalogMeta?.entry.symbol ?? params?.symbol ?? ''}
                  timeframe={catalogMeta?.entry.timeframe ?? params?.timeframe ?? ''}
                  sessionContext={session}
                  onResult={handleCompositionResult}
                  onBacktestResult={handleBacktestResult}
                  onNavigateToComposer={() => setActiveView('composer')}
                />
                {/* Chart-UX-3C.1: Indicator panel lives in sidebar */}
                <ChartIndicatorPanel
                  ref={indicatorPanelRef}
                  key={params ? `${params.symbol}|${params.timeframe}|${params.start}` : 'catalog'}
                  hasData={status === 'success' && candles.length > 0}
                  params={params}
                  onInstancesChange={setIndicatorInstances}
                  highlightedInstanceId={hoveredInstanceId}
                  onHoverInstance={setHoveredInstanceId}
                />
              </aside>

              {/* Chart area */}
              <div style={st.chartArea}>
                {/* Chart-local toolbar — symbol identity and action buttons */}
                <ChartHeader
                  symbol={catalogMeta?.entry.symbol ?? params?.symbol ?? ''}
                  timeframe={catalogMeta?.entry.timeframe ?? params?.timeframe ?? ''}
                  instrumentName={catalogMeta ? catalogMeta.entry.display_name : (selectedAsset?.name ?? undefined)}
                  exchange={params?.exchange ?? undefined}
                  assetClass={params?.asset_class ?? undefined}
                  candleCount={candles.length > 0 ? candles.length : undefined}
                  chartSettings={chartSettings}
                  onSettingsChange={updateChartSettings}
                  onScreenshot={candles.length > 0 ? () => chartHandleRef.current?.takeScreenshot() : undefined}
                  onResetView={candles.length > 0 ? () => chartHandleRef.current?.resetView() : undefined}
                  onAutoScale={candles.length > 0 ? () => chartHandleRef.current?.autoScale() : undefined}
                />
                {status === 'idle' && (
                  <div style={st.placeholder}>Select a symbol and click Fetch to load chart data.</div>
                )}
                {status === 'loading' && (
                  <div style={st.placeholder}>Loading…</div>
                )}
                {status === 'error' && (
                  <div style={{ ...st.placeholder, color: '#ef5350' }}>Error: {error}</div>
                )}
                {status === 'success' && candles.length === 0 && (
                  <div style={st.placeholder}>No candles returned for this symbol / timeframe / date range.</div>
                )}
                {status === 'success' && candles.length > 0 && (
                  <Chart
                    ref={chartHandleRef}
                    candles={candles}
                    symbol={catalogMeta?.entry.symbol ?? params?.symbol ?? ''}
                    timeframe={catalogMeta?.entry.timeframe ?? params?.timeframe ?? ''}
                    overlay={overlay}
                    indicatorArtifacts={visibleArtifacts}
                    instanceColors={instanceColorMap}
                    instanceLabels={instanceLabelMap}
                    instanceVisible={instanceVisibleMap}
                    highlightedInstanceId={hoveredInstanceId}
                    onClearStrategyResults={clearStrategyResults}
                    onHoverInstance={setHoveredInstanceId}
                    onIndicatorToggle={id => indicatorPanelRef.current?.toggleVisible(id)}
                    onIndicatorRemove={id => indicatorPanelRef.current?.removeInstance(id)}
                    volumeColorModes={volumeColorModes}
                    chartSettings={chartSettings}
                    structureResult={structureResult}
                  />
                )}
              </div>
            </div>
          </div>
        </div>

      </div>
      </StrategyContextProvider>
      </SubscriptionGate>
    </AuthGuard>
  )
}

function NavTab({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        background:    active ? '#0d1e2e' : 'transparent',
        border:        '1px solid',
        borderColor:   active ? '#1e3a5a' : '#2a2d3e',
        borderRadius:  4,
        color:         active ? '#7eb8f7' : '#4a5568',
        cursor:        'pointer',
        fontFamily:    'monospace',
        fontSize:      11,
        letterSpacing: '0.05em',
        padding:       '4px 14px',
      }}
    >
      {label}
    </button>
  )
}

const st: Record<string, React.CSSProperties> = {
  app: {
    display:       'flex',
    flexDirection: 'column',
    height:        '100vh',
    background:    '#0f0f1a',
    color:         '#d1d4dc',
    fontFamily:    'system-ui, monospace, sans-serif',
    overflow:      'hidden',
  },
  header: {
    display:      'flex',
    alignItems:   'center',
    gap:          12,
    padding:      '9px 16px',
    background:   '#0d0d1e',
    borderBottom: '1px solid #1a1a2e',
    flexShrink:   0,
  },
  logo: {
    fontWeight:    700,
    fontSize:      14,
    letterSpacing: '0.08em',
    color:         '#26a69a',
  },
  tagline: {
    fontSize: 11,
    color:    '#2a3040',
    flex:     1,
  },
  mainLayout: {
    flex:      1,
    display:   'flex',
    overflow:  'hidden',
    minHeight: 0,
  },
  content: {
    flex:           1,
    display:        'flex',
    flexDirection:  'column',
    overflow:       'hidden',
    minHeight:      0,
  },
  userArea: {
    display:    'flex',
    alignItems: 'center',
    gap:        8,
    marginLeft: 'auto',
  },
  username: {
    fontSize:   11,
    color:      '#8892a4',
    fontFamily: 'monospace',
  },
  logoutBtn: {
    background:    'transparent',
    border:        '1px solid #2a2d3e',
    borderRadius:  4,
    color:         '#4a5568',
    cursor:        'pointer',
    fontFamily:    'monospace',
    fontSize:      11,
    letterSpacing: '0.04em',
    padding:       '3px 10px',
  },
  fill: {
    flex:     1,
    display:  'flex',
    overflow: 'hidden',
    minHeight: 0,
  },
  settingsSubBar: {
    display:      'flex',
    gap:          6,
    padding:      '8px 16px',
    background:   '#0a0a14',
    borderBottom: '1px solid #1a1a28',
    flexShrink:   0,
  },
  sidebar: {
    width:         272,
    flexShrink:    0,
    background:    '#0a0a14',
    borderRight:   '1px solid #1a1a28',
    display:       'flex',
    flexDirection: 'column',
    overflowY:     'auto' as const,
  },
  chartArea: {
    flex:          1,
    display:       'flex',
    flexDirection: 'column',
    minWidth:      0,
    overflow:      'hidden',
  },
  placeholder: {
    flex:           1,
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'center',
    color:          '#2a3040',
    fontSize:       13,
    textAlign:      'center' as const,
    padding:        40,
  },
  metaBadge: {
    display:      'flex',
    alignItems:   'center',
    gap:          8,
    padding:      '5px 12px',
    background:   '#0a0a14',
    borderBottom: '1px solid #1a1a28',
    flexShrink:   0,
    flexWrap:     'wrap' as const,
  },
  metaItem: {
    display:    'flex',
    alignItems: 'center',
    gap:        4,
  },
  metaKey: {
    fontSize:      10,
    color:         '#2a3040',
    fontFamily:    'monospace',
    letterSpacing: '0.04em',
  },
  metaVal: {
    fontSize:   10,
    color:      '#4a5568',
    fontFamily: 'monospace',
  },
  metaSep: {
    fontSize: 10,
    color:    '#1a1a28',
  },
}
