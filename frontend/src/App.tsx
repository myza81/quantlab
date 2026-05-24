import { useState } from 'react'
import Controls from './components/Controls'
import Chart from './components/Chart'
import { DraftWorkspace } from './components/DraftWorkspace'
import { StrategyTestPanel } from './components/StrategyTestPanel'
import { BacktestReportPage } from './components/BacktestReportPage'
import { fetchOHLCV } from './api/marketData'
import type { OHLCVCandle, MarketDataParams } from './api/marketData'
import type { CompositionRunResponse } from './api/compositionRun'
import type { BacktestReport } from './types/backtestRuns'
import type { StrategyOverlay, SignalType } from './types/strategy'

type Status     = 'idle' | 'loading' | 'success' | 'error'
type ActiveView = 'chart' | 'composer' | 'report'

export default function App() {
  const [activeView, setActiveView] = useState<ActiveView>('chart')

  const [candles, setCandles] = useState<OHLCVCandle[]>([])
  const [status,  setStatus]  = useState<Status>('idle')
  const [error,   setError]   = useState<string | null>(null)
  const [params,  setParams]  = useState<MarketDataParams | null>(null)
  const [overlay, setOverlay] = useState<StrategyOverlay | null>(null)

  const [backtestReport, setBacktestReport] = useState<BacktestReport | null>(null)

  async function handleFetch(p: MarketDataParams) {
    setStatus('loading')
    setError(null)
    setParams(p)
    setOverlay(null)
    try {
      const resp = await fetchOHLCV(p)
      setCandles(resp.candles)
      setStatus('success')
    } catch (err) {
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

  function handleBacktestResult(report: BacktestReport) {
    setBacktestReport(report)
    setActiveView('report')
  }

  return (
    <div style={st.app}>

      {/* ── Global header ── */}
      <header style={st.header}>
        <span style={st.logo}>QuantLab</span>
        <span style={st.tagline}>Research-first strategy platform</span>
        <div style={st.nav}>
          <NavTab label="Chart"    active={activeView === 'chart'}    onClick={() => setActiveView('chart')} />
          <NavTab label="Composer" active={activeView === 'composer'} onClick={() => setActiveView('composer')} />
        </div>
      </header>

      {/* ── Composer ── */}
      {activeView === 'composer' && (
        <div style={st.fill}>
          <DraftWorkspace />
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
            <Chart
              candles={candles}
              symbol={params?.symbol ?? ''}
              timeframe={params?.timeframe ?? ''}
              overlay={overlay}
            />
          )}
        </div>
      </div>

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
    display:    'flex',
    gap:        6,
    marginLeft: 'auto',
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
}
