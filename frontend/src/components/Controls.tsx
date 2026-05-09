import { useState } from 'react'
import type { MarketDataParams } from '../api/marketData'

interface ControlsProps {
  onFetch: (params: MarketDataParams) => void
  loading: boolean
}

const TIMEFRAMES = ['1d', '1w', '1M', '1h', '30m', '15m', '5m', '1m']
const ASSET_CLASSES = ['equity', 'etf', 'crypto', 'fx', 'future', 'index']
const PROVIDERS = ['yahoo']

function todayStr(): string {
  return new Date().toISOString().split('T')[0]
}

function oneYearAgoStr(): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() - 1)
  return d.toISOString().split('T')[0]
}

export default function Controls({ onFetch, loading }: ControlsProps) {
  const [provider, setProvider] = useState('yahoo')
  const [symbol, setSymbol] = useState('AAPL')
  const [assetClass, setAssetClass] = useState('equity')
  const [exchange, setExchange] = useState('NASDAQ')
  const [timeframe, setTimeframe] = useState('1d')
  const [start, setStart] = useState(oneYearAgoStr())
  const [end, setEnd] = useState(todayStr())

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onFetch({ provider, symbol, asset_class: assetClass, exchange, timeframe, start, end })
  }

  return (
    <form onSubmit={handleSubmit} style={styles.form}>
      <div style={styles.row}>
        <label style={styles.label}>
          Provider
          <select value={provider} onChange={e => setProvider(e.target.value)} style={styles.select}>
            {PROVIDERS.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>

        <label style={styles.label}>
          Symbol
          <input
            value={symbol}
            onChange={e => setSymbol(e.target.value.toUpperCase())}
            style={styles.input}
            placeholder="AAPL"
            required
          />
        </label>

        <label style={styles.label}>
          Asset Class
          <select value={assetClass} onChange={e => setAssetClass(e.target.value)} style={styles.select}>
            {ASSET_CLASSES.map(ac => <option key={ac} value={ac}>{ac}</option>)}
          </select>
        </label>

        <label style={styles.label}>
          Exchange
          <input
            value={exchange}
            onChange={e => setExchange(e.target.value.toUpperCase())}
            style={styles.input}
            placeholder="NASDAQ"
          />
        </label>

        <label style={styles.label}>
          Timeframe
          <select value={timeframe} onChange={e => setTimeframe(e.target.value)} style={styles.select}>
            {TIMEFRAMES.map(tf => <option key={tf} value={tf}>{tf}</option>)}
          </select>
        </label>

        <label style={styles.label}>
          Start
          <input
            type="date"
            value={start}
            onChange={e => setStart(e.target.value)}
            style={styles.input}
            required
          />
        </label>

        <label style={styles.label}>
          End
          <input
            type="date"
            value={end}
            onChange={e => setEnd(e.target.value)}
            style={styles.input}
            required
          />
        </label>

        <button type="submit" disabled={loading} style={styles.button}>
          {loading ? 'Loading…' : 'Fetch'}
        </button>
      </div>
    </form>
  )
}

const styles: Record<string, React.CSSProperties> = {
  form: {
    background: '#1a1a2e',
    padding: '12px 16px',
    borderBottom: '1px solid #2a2d3e',
  },
  row: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '12px',
    alignItems: 'flex-end',
  },
  label: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    fontSize: '11px',
    color: '#8892a4',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  },
  input: {
    background: '#0f0f1a',
    border: '1px solid #2a2d3e',
    color: '#d1d4dc',
    padding: '6px 8px',
    borderRadius: '4px',
    fontFamily: 'monospace',
    fontSize: '13px',
    width: '100px',
  },
  select: {
    background: '#0f0f1a',
    border: '1px solid #2a2d3e',
    color: '#d1d4dc',
    padding: '6px 8px',
    borderRadius: '4px',
    fontSize: '13px',
  },
  button: {
    background: '#26a69a',
    color: '#fff',
    border: 'none',
    borderRadius: '4px',
    padding: '8px 20px',
    fontSize: '13px',
    fontWeight: 600,
    cursor: 'pointer',
    alignSelf: 'flex-end',
  },
}
