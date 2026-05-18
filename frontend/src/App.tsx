import { useState } from 'react'
import Controls from './components/Controls'
import Chart from './components/Chart'
import ToolPanel from './components/ToolPanel'
import { DraftWorkspace } from './components/DraftWorkspace'
import { fetchOHLCV } from './api/marketData'
import { runStrategy } from './api/strategyRuns'
import type { OHLCVCandle, MarketDataParams } from './api/marketData'
import type { StrategyRunResponse } from './api/strategyRuns'
import type { StrategyOverlay } from './types/strategy'

type Status = 'idle' | 'loading' | 'success' | 'error'
type StrategyStatus = 'idle' | 'running' | 'done' | 'error'
type ActiveView = 'chart' | 'drafts'

export default function App() {
  const [activeView, setActiveView] = useState<ActiveView>('chart')

  const [candles, setCandles] = useState<OHLCVCandle[]>([])
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<string | null>(null)
  const [params, setParams] = useState<MarketDataParams | null>(null)

  const [toolsOpen, setToolsOpen] = useState(false)

  const [overlay, setOverlay] = useState<StrategyOverlay | null>(null)
  const [strategyStatus, setStrategyStatus] = useState<StrategyStatus>('idle')
  const [strategyError, setStrategyError] = useState<string | null>(null)
  const [strategyResult, setStrategyResult] = useState<StrategyRunResponse | null>(null)

  async function handleFetch(p: MarketDataParams) {
    setStatus('loading')
    setError(null)
    setParams(p)
    // Clear strategy overlay when fetching new data
    setOverlay(null)
    setStrategyStatus('idle')
    setStrategyError(null)
    setStrategyResult(null)

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

  async function handleRunStrategy() {
    if (!params || candles.length === 0) return

    setStrategyStatus('running')
    setStrategyError(null)
    setOverlay(null)
    setStrategyResult(null)

    try {
      const result = await runStrategy({
        strategy_id: 'example_strategy',
        provider: params.provider,
        symbol: params.symbol,
        timeframe: params.timeframe,
        start: params.start,
        end: params.end,
        asset_class: params.asset_class,
        exchange: params.exchange,
      })

      setStrategyResult(result)
      setOverlay({
        signals: result.signals.map(s => ({
          timestamp: s.timestamp,
          symbol: s.symbol,
          timeframe: s.timeframe,
          signal_type: s.signal_type,
          entry_reference: s.entry_reference,
          invalidation_level: s.invalidation_level,
          confidence: s.confidence ?? undefined,
          reasoning: s.reasoning ?? undefined,
        })),
        forecast: result.forecasts.length > 0
          ? {
              generated_at: result.forecasts[0].generated_at,
              target_timestamp: result.forecasts[0].target_timestamp,
              target_price: result.forecasts[0].target_price,
              direction: result.forecasts[0].direction,
              confidence: result.forecasts[0].confidence,
              invalidation_price: result.forecasts[0].invalidation_price ?? undefined,
              reason: result.forecasts[0].reason ?? undefined,
            }
          : null,
        indicators: result.indicators,
      })
      setStrategyStatus('done')
    } catch (err) {
      setStrategyError(err instanceof Error ? err.message : 'Unknown error')
      setStrategyStatus('error')
    }
  }

  return (
    <div style={styles.app}>
      <header style={styles.header}>
        <span style={styles.title}>QuantLab</span>
        <span style={styles.subtitle}>Research-first strategy platform</span>

        <NavTab
          label="Chart"
          active={activeView === 'chart'}
          onClick={() => setActiveView('chart')}
        />
        <NavTab
          label="Drafts"
          active={activeView === 'drafts'}
          onClick={() => setActiveView('drafts')}
        />

        {activeView === 'chart' && (
          <button
            style={{
              ...styles.toolsBtn,
              background: toolsOpen ? '#1a3a3a' : 'transparent',
              borderColor: toolsOpen ? '#26a69a' : '#2a2d3e',
              color: toolsOpen ? '#26a69a' : '#4a5568',
            }}
            onClick={() => setToolsOpen(o => !o)}
          >
            Tools
          </button>
        )}
      </header>

      {activeView === 'drafts' && (
        <main style={{ ...styles.main, overflow: 'hidden' }}>
          <DraftWorkspace />
        </main>
      )}

      {activeView === 'chart' && (
        <>
          {toolsOpen && <ToolPanel />}

          <Controls onFetch={handleFetch} loading={status === 'loading'} />

          {status === 'success' && candles.length > 0 && (
            <div style={styles.strategyBar}>
              <button
                style={{
                  ...styles.runBtn,
                  opacity: strategyStatus === 'running' ? 0.5 : 1,
                  cursor: strategyStatus === 'running' ? 'not-allowed' : 'pointer',
                }}
                onClick={handleRunStrategy}
                disabled={strategyStatus === 'running'}
              >
                {strategyStatus === 'running' ? 'Running…' : 'Run Strategy'}
              </button>

              {strategyStatus === 'done' && strategyResult && (
                <ResultInspector result={strategyResult} />
              )}
              {strategyStatus === 'error' && (
                <span style={styles.strategyErr}>Error: {strategyError}</span>
              )}
            </div>
          )}

          <main style={styles.main}>
            {status === 'idle' && (
              <div style={styles.placeholder}>
                Select a symbol and click Fetch to load chart data.
              </div>
            )}
            {status === 'loading' && (
              <div style={styles.placeholder}>Loading…</div>
            )}
            {status === 'error' && (
              <div style={{ ...styles.placeholder, color: '#ef5350' }}>
                Error: {error}
              </div>
            )}
            {status === 'success' && candles.length === 0 && (
              <div style={styles.placeholder}>
                No candles returned. The provider may have no data for this symbol, timeframe, or date range.
              </div>
            )}
            {status === 'success' && candles.length > 0 && (
              <Chart
                candles={candles}
                symbol={params?.symbol ?? ''}
                timeframe={params?.timeframe ?? ''}
                overlay={overlay}
              />
            )}
          </main>
        </>
      )}
    </div>
  )
}

function NavTab({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      style={{
        background: active ? '#1a2a3a' : 'transparent',
        border: '1px solid',
        borderColor: active ? '#2a4a6a' : '#2a2d3e',
        borderRadius: '4px',
        color: active ? '#7eb8f7' : '#4a5568',
        fontSize: '11px',
        fontFamily: 'monospace',
        letterSpacing: '0.05em',
        padding: '4px 12px',
        cursor: 'pointer',
      }}
      onClick={onClick}
    >
      {label}
    </button>
  )
}

function ResultInspector({ result }: { result: StrategyRunResponse }) {
  const items: Array<{ label: string; value: string | number }> = [
    { label: 'strategy', value: result.strategy_id },
    { label: 'status', value: result.status },
    { label: 'candles', value: result.candles_received },
    { label: 'signals', value: result.signals.length },
    { label: 'indicators', value: result.indicators.length },
    { label: 'forecasts', value: result.forecasts.length },
  ]
  if (result.warnings.length > 0) {
    items.push({ label: 'warnings', value: result.warnings.length })
  }
  if (result.error) {
    items.push({ label: 'error', value: result.error })
  }

  return (
    <div style={inspectorStyles.row}>
      {items.map(item => (
        <span key={item.label} style={inspectorStyles.item}>
          <span style={inspectorStyles.label}>{item.label}</span>
          <span style={inspectorStyles.value}>{item.value}</span>
        </span>
      ))}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  app: {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    background: '#0f0f1a',
    color: '#d1d4dc',
    fontFamily: 'system-ui, monospace, sans-serif',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    padding: '10px 16px',
    background: '#1a1a2e',
    borderBottom: '1px solid #2a2d3e',
  },
  title: {
    fontWeight: 700,
    fontSize: '15px',
    letterSpacing: '0.06em',
    color: '#26a69a',
  },
  subtitle: {
    fontSize: '12px',
    color: '#4a5568',
    flex: 1,
  },
  toolsBtn: {
    border: '1px solid #2a2d3e',
    borderRadius: '4px',
    padding: '4px 12px',
    fontSize: '11px',
    fontFamily: 'monospace',
    letterSpacing: '0.05em',
    cursor: 'pointer',
    marginLeft: 'auto',
  },
  strategyBar: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
    padding: '8px 16px',
    background: '#12121f',
    borderBottom: '1px solid #2a2d3e',
    flexWrap: 'wrap' as const,
  },
  runBtn: {
    background: '#1e3a5f',
    color: '#7eb8f7',
    border: '1px solid #2a4a7f',
    borderRadius: '4px',
    padding: '5px 14px',
    fontSize: '12px',
    fontFamily: 'monospace',
    letterSpacing: '0.04em',
    flexShrink: 0,
  },
  strategyErr: {
    fontSize: '12px',
    color: '#ef5350',
    fontFamily: 'monospace',
  },
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  placeholder: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#4a5568',
    fontSize: '14px',
    textAlign: 'center',
    padding: '40px',
  },
}

const inspectorStyles: Record<string, React.CSSProperties> = {
  row: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    flexWrap: 'wrap' as const,
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    fontSize: '11px',
    fontFamily: 'monospace',
  },
  label: {
    color: '#4a5568',
  },
  value: {
    color: '#8892a4',
    background: '#1a1a2e',
    padding: '1px 6px',
    borderRadius: '3px',
  },
}
