import { useState } from 'react'
import type { MarketDataParams } from '../api/marketData'

interface ControlsProps {
  onFetch: (params: MarketDataParams) => void
  loading: boolean
}

const TIMEFRAMES   = ['1d', '1w', '1M', '1h', '30m', '15m', '5m', '1m']
const ASSET_CLASSES = ['equity', 'etf', 'crypto', 'fx', 'future', 'index']
const PROVIDERS    = ['yahoo']

function todayStr(): string {
  return new Date().toISOString().split('T')[0]
}
function oneYearAgoStr(): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() - 1)
  return d.toISOString().split('T')[0]
}

export default function Controls({ onFetch, loading }: ControlsProps) {
  const [provider,    setProvider]    = useState('yahoo')
  const [symbol,      setSymbol]      = useState('AAPL')
  const [assetClass,  setAssetClass]  = useState('equity')
  const [exchange,    setExchange]    = useState('NASDAQ')
  const [timeframe,   setTimeframe]   = useState('1d')
  const [start,       setStart]       = useState(oneYearAgoStr())
  const [end,         setEnd]         = useState(todayStr())

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onFetch({ provider, symbol, asset_class: assetClass, exchange, timeframe, start, end })
  }

  return (
    <form onSubmit={handleSubmit} style={s.form}>
      <div style={s.sectionTitle}>Market Data</div>

      <div style={s.fields}>
        <Field label="Provider">
          <select value={provider} onChange={e => setProvider(e.target.value)} style={s.input}>
            {PROVIDERS.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </Field>

        <div style={s.row2}>
          <Field label="Symbol">
            <input
              value={symbol}
              onChange={e => setSymbol(e.target.value.toUpperCase())}
              style={s.input}
              placeholder="AAPL"
              required
            />
          </Field>
          <Field label="Timeframe">
            <select value={timeframe} onChange={e => setTimeframe(e.target.value)} style={s.input}>
              {TIMEFRAMES.map(tf => <option key={tf} value={tf}>{tf}</option>)}
            </select>
          </Field>
        </div>

        <div style={s.row2}>
          <Field label="Asset Class">
            <select value={assetClass} onChange={e => setAssetClass(e.target.value)} style={s.input}>
              {ASSET_CLASSES.map(ac => <option key={ac} value={ac}>{ac}</option>)}
            </select>
          </Field>
          <Field label="Exchange">
            <input
              value={exchange}
              onChange={e => setExchange(e.target.value.toUpperCase())}
              style={s.input}
              placeholder="NASDAQ"
            />
          </Field>
        </div>

        <div style={s.row2}>
          <Field label="Start">
            <input type="date" value={start} onChange={e => setStart(e.target.value)} style={s.input} required />
          </Field>
          <Field label="End">
            <input type="date" value={end} onChange={e => setEnd(e.target.value)} style={s.input} required />
          </Field>
        </div>
      </div>

      <button type="submit" disabled={loading} style={{ ...s.fetchBtn, opacity: loading ? 0.6 : 1 }}>
        {loading ? 'Loading…' : 'Fetch'}
      </button>
    </form>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={s.field}>
      <span style={s.label}>{label}</span>
      {children}
    </label>
  )
}

const s: Record<string, React.CSSProperties> = {
  form: {
    padding:       '14px 14px 10px',
    borderBottom:  '1px solid #1e1e30',
    display:       'flex',
    flexDirection: 'column',
    gap:           10,
  },
  sectionTitle: {
    fontSize:      10,
    fontWeight:    700,
    color:         '#4a5568',
    letterSpacing: '0.09em',
    fontFamily:    'monospace',
  },
  fields: {
    display:       'flex',
    flexDirection: 'column',
    gap:           7,
  },
  row2: {
    display: 'flex',
    gap:     6,
  },
  field: {
    display:       'flex',
    flexDirection: 'column',
    gap:           3,
    flex:          1,
    minWidth:      0,
  },
  label: {
    fontSize:      10,
    color:         '#4a5568',
    letterSpacing: '0.06em',
    fontFamily:    'monospace',
  },
  input: {
    background:  '#0a0a14',
    border:      '1px solid #2a2d3e',
    borderRadius: 3,
    color:       '#d1d4dc',
    fontFamily:  'monospace',
    fontSize:    12,
    padding:     '5px 7px',
    width:       '100%',
    boxSizing:   'border-box' as const,
  },
  fetchBtn: {
    background:    '#26a69a',
    border:        'none',
    borderRadius:  4,
    color:         '#fff',
    cursor:        'pointer',
    fontFamily:    'monospace',
    fontSize:      12,
    fontWeight:    700,
    letterSpacing: '0.04em',
    padding:       '8px',
    width:         '100%',
  },
}
