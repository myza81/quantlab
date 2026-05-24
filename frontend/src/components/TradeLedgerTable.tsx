/**
 * TradeLedgerTable — scrollable trade-by-trade ledger for a backtest report.
 */
import type { TradeRecord } from '../types/backtestRuns'

interface Props {
  trades:        TradeRecord[]
  openPosition?: TradeRecord | null
}

const $ = (v: number | null | undefined, dp = 2) =>
  v == null ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp })

const pct = (v: number | null | undefined) =>
  v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`

function fmtTs(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      year: '2-digit', month: 'short', day: 'numeric',
    })
  } catch { return iso }
}

function pnlColor(v: number | null | undefined): string {
  if (v == null) return '#7a8598'
  return v > 0 ? '#66bb6a' : v < 0 ? '#ef5350' : '#7a8598'
}

export function TradeLedgerTable({ trades, openPosition }: Props) {
  const allRows = openPosition ? [...trades, openPosition] : trades

  if (allRows.length === 0) {
    return <div style={s.empty}>No closed trades in this backtest.</div>
  }

  return (
    <div style={s.container}>
      <table style={s.table}>
        <thead>
          <tr>
            {[
              '#', 'Entry Date', 'Exit Date', 'Side', 'Qty',
              'Entry $', 'Exit $', 'Gross P/L', 'Net P/L', 'Ret %',
              'Commission', 'Slippage', 'Holding', 'Equity After',
            ].map(h => (
              <th key={h} style={s.th}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {allRows.map(t => {
            const isOpen = t.exit_bar_index === null
            return (
              <tr key={t.trade_num} style={isOpen ? s.openRow : undefined}>
                <td style={s.td}>{t.trade_num}</td>
                <td style={s.td}>{fmtTs(t.entry_timestamp)}</td>
                <td style={s.td}>{isOpen ? <span style={s.openBadge}>OPEN</span> : fmtTs(t.exit_timestamp)}</td>
                <td style={{ ...s.td, color: '#26a69a' }}>{t.side.toUpperCase()}</td>
                <td style={s.td}>{$(t.quantity, 4)}</td>
                <td style={s.td}>{$(t.entry_price)}</td>
                <td style={s.td}>{$(t.exit_price)}</td>
                <td style={{ ...s.td, color: pnlColor(t.gross_pnl) }}>{$(t.gross_pnl)}</td>
                <td style={{ ...s.td, color: pnlColor(t.net_pnl),  fontWeight: 600 }}>{$(t.net_pnl)}</td>
                <td style={{ ...s.td, color: pnlColor(t.return_pct) }}>{pct(t.return_pct)}</td>
                <td style={s.td}>{$(t.entry_commission + (t.exit_commission ?? 0))}</td>
                <td style={s.td}>{$(t.entry_slippage  + (t.exit_slippage  ?? 0))}</td>
                <td style={s.td}>{t.holding_bars == null ? '—' : `${t.holding_bars}d`}</td>
                <td style={s.td}>{$(t.equity_after)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  container: {
    overflowX:    'auto',
    overflowY:    'auto',
    maxHeight:    380,
    border:       '1px solid #1e1e30',
    borderRadius: 4,
    fontSize:     11,
    fontFamily:   'monospace',
  },
  table: {
    width:           '100%',
    borderCollapse:  'collapse',
    whiteSpace:      'nowrap',
  },
  th: {
    background:    '#0d0d20',
    color:         '#4a5568',
    padding:       '6px 10px',
    textAlign:     'left',
    fontWeight:    600,
    letterSpacing: '0.04em',
    position:      'sticky',
    top:           0,
    borderBottom:  '1px solid #1e1e30',
  },
  td: {
    padding:      '5px 10px',
    color:        '#7a8598',
    borderBottom: '1px solid #12121e',
  },
  openRow: {
    background: '#0f0f22',
  },
  openBadge: {
    background:   '#1a2a4a',
    color:        '#7eb8f7',
    borderRadius: 3,
    padding:      '1px 5px',
    fontSize:     10,
  },
  empty: {
    color:    '#4a5568',
    fontSize: 12,
    padding:  '12px 0',
  },
}
