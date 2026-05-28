import { useState } from 'react'
import Controls from './components/Controls'
import Chart from './components/Chart'
import { DraftWorkspace } from './components/DraftWorkspace'
import { StrategyTestPanel } from './components/StrategyTestPanel'
import { BacktestReportPage } from './components/BacktestReportPage'
import { CredentialManager } from './components/CredentialManager'
import { LoginPage } from './components/LoginPage'
import { RegisterPage } from './components/RegisterPage'
import { AuthGuard } from './components/AuthGuard'
import { SubscriptionGate } from './components/SubscriptionGate'
import { useAuth } from './auth/AuthContext'
import { isAuthError } from './api/client'
import { fetchOHLCV } from './api/marketData'
import type { OHLCVCandle, MarketDataParams, DatasetFetchMetadata } from './api/marketData'
import type { CompositionRunResponse } from './api/compositionRun'
import type { BacktestReport } from './types/backtestRuns'
import type { StrategyOverlay, SignalType } from './types/strategy'

type Status     = 'idle' | 'loading' | 'success' | 'error'
type ActiveView = 'chart' | 'composer' | 'credentials' | 'report'
type AuthView   = 'login' | 'register'

export default function App() {
  const { user, logout } = useAuth()
  const [authView, setAuthView] = useState<AuthView>('login')
  const [activeView, setActiveView] = useState<ActiveView>('chart')

  const [candles,       setCandles]       = useState<OHLCVCandle[]>([])
  const [status,        setStatus]        = useState<Status>('idle')
  const [error,         setError]         = useState<string | null>(null)
  const [params,        setParams]        = useState<MarketDataParams | null>(null)
  const [overlay,       setOverlay]       = useState<StrategyOverlay | null>(null)
  const [fetchMetadata, setFetchMetadata] = useState<DatasetFetchMetadata | null>(null)

  const [backtestReport, setBacktestReport] = useState<BacktestReport | null>(null)

  async function handleFetch(p: MarketDataParams) {
    setStatus('loading')
    setError(null)
    setParams(p)
    setOverlay(null)
    setFetchMetadata(null)
    try {
      const resp = await fetchOHLCV(p)
      setCandles(resp.candles)
      setFetchMetadata(resp.fetch_metadata ?? null)
      setStatus('success')
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
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
        name:   ind.name,
        kind:   ind.kind,
        pane:   ind.pane,
        color:  ind.color,
        points: ind.points
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
    setActiveView('report')
  }

  const authFallback = authView === 'login'
    ? <LoginPage onNavigateRegister={() => setAuthView('register')} />
    : <RegisterPage onNavigateLogin={() => setAuthView('login')} />

  return (
    <AuthGuard fallback={authFallback}>
      <SubscriptionGate>
      <div style={st.app}>

        {/* ── Global header ── */}
        <header style={st.header}>
          <span style={st.logo}>QuantLab</span>
          <span style={st.tagline}>Research-first strategy platform</span>
          <div style={st.nav}>
            <NavTab label="Chart"       active={activeView === 'chart'}       onClick={() => setActiveView('chart')} />
            <NavTab label="Composer"    active={activeView === 'composer'}    onClick={() => setActiveView('composer')} />
            <NavTab label="Credentials" active={activeView === 'credentials'} onClick={() => setActiveView('credentials')} />
          </div>
          {user && (
            <div style={st.userArea}>
              <span style={st.username}>{user.username}</span>
              <button style={st.logoutBtn} onClick={logout}>Sign out</button>
            </div>
          )}
        </header>

        {/* ── Composer ── */}
        {activeView === 'composer' && (
          <div style={st.fill}>
            <DraftWorkspace />
          </div>
        )}

        {/* ── Credentials ── */}
        {activeView === 'credentials' && (
          <div style={{ ...st.fill, overflowY: 'auto' }}>
            <CredentialManager />
          </div>
        )}

        {/* ── Report ── */}
        {activeView === 'report' && backtestReport && (
          <div style={st.fill}>
            <BacktestReportPage
              report={backtestReport}
              onBack={() => setActiveView('chart')}
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
            <Controls onFetch={handleFetch} loading={status === 'loading'} />
            <StrategyTestPanel
              candles={candles}
              symbol={params?.symbol ?? ''}
              timeframe={params?.timeframe ?? ''}
              onResult={handleCompositionResult}
              onBacktestResult={handleBacktestResult}
            />
          </aside>

          {/* Chart area */}
          <div style={st.chartArea}>
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
              <>
                {fetchMetadata && (
                  <DatasetMetaBadge metadata={fetchMetadata} candleCount={candles.length} />
                )}
                <Chart
                  candles={candles}
                  symbol={params?.symbol ?? ''}
                  timeframe={params?.timeframe ?? ''}
                  overlay={overlay}
                  onClearStrategyResults={clearStrategyResults}
                />
              </>
            )}
          </div>
        </div>

      </div>
      </SubscriptionGate>
    </AuthGuard>
  )
}

// Compact dataset provenance strip shown above the chart after a successful fetch
function DatasetMetaBadge({
  metadata,
  candleCount,
}: {
  metadata:    DatasetFetchMetadata
  candleCount: number
}) {
  return (
    <div data-testid="dataset-meta-badge" style={st.metaBadge}>
      <span style={st.metaItem}>
        <span style={st.metaKey}>provider</span>
        <span style={st.metaVal}>{metadata.provider}</span>
      </span>
      <span style={st.metaSep}>·</span>
      <span style={st.metaItem}>
        <span style={st.metaKey}>candles</span>
        <span style={st.metaVal}>{candleCount.toLocaleString()}</span>
      </span>
      <span style={st.metaSep}>·</span>
      <span style={st.metaItem}>
        <span style={st.metaKey}>dataset</span>
        <span style={st.metaVal} title={metadata.dataset_id}>
          {metadata.dataset_id.slice(0, 40)}{metadata.dataset_id.length > 40 ? '…' : ''}
        </span>
      </span>
      <span style={st.metaSep}>·</span>
      <span style={st.metaItem}>
        <span style={st.metaKey}>fingerprint</span>
        <span style={st.metaVal} title={metadata.fingerprint}>
          {metadata.fingerprint.slice(0, 12)}
        </span>
      </span>
    </div>
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
  nav: {
    display: 'flex',
    gap:     6,
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
  sidebar: {
    width:         272,
    flexShrink:    0,
    background:    '#0a0a14',
    borderRight:   '1px solid #1a1a28',
    display:       'flex',
    flexDirection: 'column',
    overflow:      'hidden',
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
