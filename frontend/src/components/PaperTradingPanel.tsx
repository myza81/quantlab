/**
 * PaperTradingPanel — Phase P3/P4/P5.
 *
 * P3: Create session, list sessions, account summary.
 * P4: Operator inspection — account detail, orders, fills, positions, action buttons.
 * P5: Trade Ledger (orders+fills combined), Session Metrics summary, Equity History table,
 *     symbol/status filters, newest/oldest sort.
 * P7: Evidence-gated lifecycle promotion: forward_tested → paper_tested.
 *
 * Scope constraints:
 *   - No approved-for-live promotion, no live trading, no broker integration
 *   - No setInterval, no automatic polling — every reload is user-triggered
 *   - Backend lifecycle validation is authoritative; frontend enforces only display logic
 *   - Metrics and unrealized P&L are display-only; backend is the authoritative calculation source
 */
import { useEffect, useState } from 'react'
import { isAuthError, isSubscriptionExpiredError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import {
  createPaperTradingSession,
  listPaperTradingSessions,
  getPaperTradingSession,
  getPaperTradingAccount,
  listPaperTradingOrders,
  listPaperTradingFills,
  listPaperTradingPositions,
  runPaperTradingCycle,
  pausePaperTradingSession,
  resumePaperTradingSession,
  terminatePaperTradingSession,
  getEquityCurve,
  promoteDraftToPaperTested,
} from '../api/paperTrading'
import { fetchDrafts } from '../api/drafts'
import { listForwardTestSessions } from '../api/forwardTests'
import type {
  PaperTradingSessionSummary,
  PaperTradingSessionDetail,
  PaperAccount,
  PaperOrder,
  PaperFill,
  PaperPosition,
  PaperCycleResult,
  PaperEquitySnapshot,
  CreatePaperTradingSessionRequest,
} from '../types/paperTrading'
import type { StrategyDraftData } from '../types/drafts'
import type { ForwardTestSessionSummary } from '../types/forwardTesting'
import { computeGuidance, STAGE_LABELS } from '../lib/lifecycleGuidance'
import { EvidenceReadinessPanel } from './EvidenceReadinessPanel'
import { LifecycleGuidanceCard } from './LifecycleGuidanceCard'

// Only drafts at these statuses may enter paper trading (mirrors backend P2)
const ELIGIBLE_PT_STATUSES = new Set(['forward_tested', 'paper_tested', 'approved_for_live'])

const STATUS_COLORS: Record<string, string> = {
  pending:    'rgba(255,167,38,0.13)',
  running:    'rgba(72,187,120,0.13)',
  paused:     'rgba(99,179,237,0.13)',
  completed:  'rgba(154,230,180,0.13)',
  failed:     'rgba(252,129,74,0.13)',
  terminated: 'rgba(160,174,192,0.13)',
}
const STATUS_TEXT_COLORS: Record<string, string> = {
  pending:    '#ffa726',
  running:    '#48bb78',
  paused:     '#63b3ed',
  completed:  '#9ae6b4',
  failed:     '#fc814a',
  terminated: '#a0aec0',
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span style={{
      display: 'inline-block',
      padding: '1px 7px',
      borderRadius: 10,
      fontSize: 11,
      fontWeight: 600,
      background: STATUS_COLORS[status] ?? 'rgba(255,255,255,0.08)',
      color: STATUS_TEXT_COLORS[status] ?? '#e2e8f0',
      border: `1px solid ${STATUS_TEXT_COLORS[status] ?? '#e2e8f0'}40`,
      textTransform: 'uppercase',
    }}>
      {status}
    </span>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
      <span style={{ color: '#718096', fontSize: 11, minWidth: 190, flexShrink: 0 }}>{label}</span>
      <span style={{ color: '#e2e8f0', fontSize: 11, fontFamily: 'inherit', wordBreak: 'break-all' }}>{value}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Session Metrics Summary (P5)
// ---------------------------------------------------------------------------

function MetricsSummary({
  orders, fills, positions, account,
}: {
  orders: PaperOrder[]
  fills: PaperFill[]
  positions: PaperPosition[]
  account: PaperAccount | null
}) {
  const filledOrders    = orders.filter(o => o.status === 'filled').length
  const rejectedOrders  = orders.filter(o => o.status === 'rejected').length
  const cancelledOrders = orders.filter(o => o.status === 'cancelled').length
  const openPositions   = positions.filter(p => p.is_open).length
  const unrealizedPnl   = positions.filter(p => p.is_open).reduce((sum, p) => sum + (p.unrealized_pnl ?? 0), 0)

  const fmt = (n: number) => n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const pnlClr = (n: number) => n >= 0 ? '#48bb78' : '#fc814a'

  const cell = (label: string, val: string, color?: string) => (
    <div>
      <div style={{ fontSize: 10, color: '#718096', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 13, fontWeight: 600, color: color ?? '#e2e8f0' }}>{val}</div>
    </div>
  )

  return (
    <div data-testid="pt-metrics" style={{
      background: '#1a2733',
      border: '1px solid #2d3a4a',
      borderRadius: 6,
      padding: '12px 16px',
      marginBottom: 12,
    }}>
      <div style={{ fontSize: 11, color: '#718096', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>
        Session Metrics
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '10px 16px' }}>
        {cell('Total Orders',   String(orders.length))}
        {cell('Filled',         String(filledOrders),   '#48bb78')}
        {cell('Rejected',       String(rejectedOrders), rejectedOrders > 0 ? '#fc814a' : '#e2e8f0')}
        {cell('Cancelled',      String(cancelledOrders))}
        {cell('Total Fills',    String(fills.length))}
        {cell('Open Positions', String(openPositions))}
        {account
          ? cell('Equity',       `${account.currency} ${fmt(account.equity)}`)
          : cell('Equity',       '—')}
        {account
          ? cell('Cash',         `${account.currency} ${fmt(account.cash_balance)}`)
          : cell('Cash',         '—')}
        {account
          ? cell('Realized P&L', `${account.currency} ${fmt(account.total_realized_pnl)}`, pnlClr(account.total_realized_pnl))
          : cell('Realized P&L', '—')}
        {cell('Unrealized P&L', `USD ${fmt(unrealizedPnl)}`, pnlClr(unrealizedPnl))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Account Detail Card (P4)
// ---------------------------------------------------------------------------

function AccountDetailCard({ account }: { account: PaperAccount }) {
  const fmt = (n: number) => n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const pnlColor = account.total_realized_pnl >= 0 ? '#48bb78' : '#fc814a'
  const ddColor  = account.current_drawdown_pct > 10 ? '#fc814a' : '#a0aec0'

  const cell = (label: string, content: React.ReactNode) => (
    <div>
      <div style={{ fontSize: 10, color: '#718096', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 12, color: '#e2e8f0' }}>{content}</div>
    </div>
  )

  return (
    <div data-testid="pt-account-detail" style={{
      background: '#232c3b',
      border: '1px solid #2d3a4a',
      borderRadius: 6,
      padding: '14px 16px',
      marginBottom: 12,
    }}>
      <div style={{ fontSize: 11, color: '#718096', marginBottom: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        Account
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px 20px' }}>
        {cell('Cash Balance',   <strong style={{ fontSize: 14 }}>{account.currency} {fmt(account.cash_balance)}</strong>)}
        {cell('Equity',         <strong style={{ fontSize: 14 }}>{account.currency} {fmt(account.equity)}</strong>)}
        {cell('Available Cash', `${account.currency} ${fmt(account.available_cash)}`)}
        {cell('Peak Equity',    `${account.currency} ${fmt(account.peak_equity)}`)}
        {cell('Starting Cash',  `${account.currency} ${fmt(account.starting_cash)}`)}
        {cell('Realized P&L',   <span style={{ color: pnlColor }}>{account.currency} {fmt(account.total_realized_pnl)}</span>)}
        {cell('Drawdown',       <span style={{ color: ddColor }}>{account.current_drawdown_pct.toFixed(2)}%</span>)}
        {cell('Fees Paid',      `${account.currency} ${fmt(account.total_fees_paid)}`)}
        {cell('Slippage',       `${account.currency} ${fmt(account.total_slippage_applied)}`)}
        {cell('Status',         <span style={{ textTransform: 'uppercase', fontSize: 11 }}>{account.status}</span>)}
        {cell('Account ID',     <span style={{ fontFamily: 'monospace', fontSize: 10 }}>{account.account_id.slice(0, 8)}…</span>)}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Section wrapper
// ---------------------------------------------------------------------------

function SectionBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{
        fontSize: 11, color: '#718096', fontWeight: 600, textTransform: 'uppercase',
        letterSpacing: '0.05em', marginBottom: 8, paddingTop: 12,
        borderTop: '1px solid #2d3a4a',
      }}>
        {title}
      </div>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Shared table styles
// ---------------------------------------------------------------------------

const thStyle: React.CSSProperties = {
  textAlign: 'left', padding: '4px 8px', color: '#718096', fontWeight: 600, whiteSpace: 'nowrap',
}
const tdStyle: React.CSSProperties = {
  padding: '4px 8px', color: '#e2e8f0', whiteSpace: 'nowrap',
}
const btnStyle = (primary?: boolean): React.CSSProperties => ({
  background: primary ? '#2b6cb0' : '#2d3a4a',
  border: 'none',
  borderRadius: 4,
  color: '#e2e8f0',
  cursor: 'pointer',
  fontSize: 11,
  fontFamily: 'inherit',
  padding: '4px 10px',
})
const errStyle: React.CSSProperties = {
  background: '#3a1a1a', border: '1px solid #5a2a2a', borderRadius: 4,
  padding: '6px 10px', fontSize: 11, color: '#fc814a',
}
const emptyStyle: React.CSSProperties = {
  fontSize: 11, color: '#4a5568', fontStyle: 'italic', padding: '8px 0',
}
const filterInputStyle: React.CSSProperties = {
  background: '#1a2233', border: '1px solid #2d3a4a', borderRadius: 4,
  color: '#e2e8f0', fontSize: 11, fontFamily: 'inherit', padding: '3px 8px',
}

// ---------------------------------------------------------------------------
// Equity Curve Chart (P6) — SVG, no external charting dependency
// ---------------------------------------------------------------------------

function EquityCurveChart({
  snapshots,
  error,
}: {
  snapshots: PaperEquitySnapshot[]
  error: string | null
}) {
  if (error) {
    return (
      <div data-testid="pt-equity-curve-error" style={{ ...errStyle, marginBottom: 10 }}>
        Unable to load equity curve: {error}
      </div>
    )
  }
  if (snapshots.length < 2) {
    return (
      <div data-testid="pt-equity-curve-insufficient" style={{ ...emptyStyle, padding: '12px 0' }}>
        Not enough equity history yet. Run more paper cycles to build the curve.
      </div>
    )
  }

  const W = 760, H = 130
  const PAD_L = 52, PAD_R = 8, PAD_T = 8, PAD_B = 18
  const plotW = W - PAD_L - PAD_R
  const plotH = H - PAD_T - PAD_B

  // Scale both equity and cash together so both lines stay in-frame
  const equities  = snapshots.map(s => s.equity)
  const cashes    = snapshots.map(s => s.cash_balance)
  const allVals   = [...equities, ...cashes]
  const minVal    = Math.min(...allVals)
  const maxVal    = Math.max(...allVals)
  const valRange  = maxVal - minVal || 1

  const tsList    = snapshots.map(s => new Date(s.bar_timestamp).getTime())
  const minTs     = tsList[0]
  const maxTs     = tsList[tsList.length - 1]
  const tsRange   = maxTs - minTs || 1

  const toX = (ts: number) => PAD_L + ((ts - minTs) / tsRange) * plotW
  const toY = (v: number)  => PAD_T + ((maxVal - v) / valRange) * plotH

  const eqPts   = snapshots.map(s => `${toX(new Date(s.bar_timestamp).getTime()).toFixed(1)},${toY(s.equity).toFixed(1)}`)
  const cashPts = snapshots.map(s => `${toX(new Date(s.bar_timestamp).getTime()).toFixed(1)},${toY(s.cash_balance).toFixed(1)}`)

  const first = snapshots[0]
  const last  = snapshots[snapshots.length - 1]
  const yBot  = (PAD_T + plotH).toFixed(1)
  const areaPath = [
    `M ${eqPts[0]}`,
    ...eqPts.slice(1).map(p => `L ${p}`),
    `L ${toX(new Date(last.bar_timestamp).getTime()).toFixed(1)},${yBot}`,
    `L ${toX(new Date(first.bar_timestamp).getTime()).toFixed(1)},${yBot}`,
    'Z',
  ].join(' ')

  const yTicks = [maxVal, (maxVal + minVal) / 2, minVal]
  const fmtLbl = (v: number) =>
    v >= 10000 ? `${(v / 1000).toFixed(1)}k` : v >= 1000 ? `${(v / 1000).toFixed(2)}k` : v.toFixed(0)

  return (
    <div data-testid="pt-equity-curve">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <div style={{ fontSize: 10, color: '#718096' }}>
          <span style={{ color: '#48bb78' }}>━ Equity</span>
          {'  '}
          <span style={{ color: '#63b3ed' }}>╌ Cash</span>
        </div>
        <div style={{ fontSize: 10, color: '#4a5568' }}>
          {new Date(first.bar_timestamp).toLocaleDateString()} → {new Date(last.bar_timestamp).toLocaleDateString()}
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 130, display: 'block' }}>
        {yTicks.map((v, i) => {
          const y = toY(v)
          return (
            <g key={i}>
              <line x1={PAD_L} y1={y} x2={W - PAD_R} y2={y} stroke="#2d3a4a" strokeWidth={0.5} />
              <text x={PAD_L - 3} y={y + 3} textAnchor="end" fontSize={8} fill="#4a5568">{fmtLbl(v)}</text>
            </g>
          )
        })}
        <line x1={PAD_L} y1={PAD_T + plotH} x2={W - PAD_R} y2={PAD_T + plotH} stroke="#2d3a4a" strokeWidth={0.5} />
        <path d={areaPath} fill="#48bb78" opacity={0.07} />
        <polyline points={cashPts.join(' ')} fill="none" stroke="#63b3ed" strokeWidth={1} strokeDasharray="3,2" opacity={0.5} />
        <polyline points={eqPts.join(' ')} fill="none" stroke="#48bb78" strokeWidth={1.5} />
      </svg>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Drawdown Summary (P6)
// ---------------------------------------------------------------------------

function DrawdownSummary({
  account,
  snapshots,
}: {
  account: PaperAccount | null
  snapshots: PaperEquitySnapshot[]
}) {
  if (!account) return null

  const maxDrawdown = snapshots.length > 0
    ? Math.max(...snapshots.map(s => s.current_drawdown_pct))
    : account.current_drawdown_pct
  const ddColor = (pct: number) => pct > 15 ? '#fc814a' : pct > 5 ? '#ffa726' : '#a0aec0'
  const fmt = (n: number) => n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const cell = (label: string, content: React.ReactNode) => (
    <div>
      <div style={{ fontSize: 10, color: '#718096', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 12, color: '#e2e8f0' }}>{content}</div>
    </div>
  )

  return (
    <div data-testid="pt-drawdown-summary" style={{
      background: '#1a2733', border: '1px solid #2d3a4a', borderRadius: 6,
      padding: '12px 14px', flex: 1, minWidth: 180,
    }}>
      <div style={{ fontSize: 10, color: '#718096', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>
        Drawdown
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 12px' }}>
        {cell('Current',      <span style={{ color: ddColor(account.current_drawdown_pct) }}>{account.current_drawdown_pct.toFixed(2)}%</span>)}
        {cell('Max (Session)',<span style={{ color: ddColor(maxDrawdown) }}>{maxDrawdown.toFixed(2)}%</span>)}
        {cell('Peak Equity',  `${account.currency} ${fmt(account.peak_equity)}`)}
        {cell('Latest Equity',`${account.currency} ${fmt(account.equity)}`)}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Return Summary (P6)
// ---------------------------------------------------------------------------

function ReturnSummary({ account }: { account: PaperAccount | null }) {
  if (!account) return null

  const absReturn = account.equity - account.starting_cash
  const pctReturn = account.starting_cash > 0 ? (absReturn / account.starting_cash) * 100 : 0
  const retColor  = absReturn >= 0 ? '#48bb78' : '#fc814a'
  const fmt = (n: number) => n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const cell = (label: string, content: React.ReactNode) => (
    <div>
      <div style={{ fontSize: 10, color: '#718096', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 12, color: '#e2e8f0' }}>{content}</div>
    </div>
  )

  return (
    <div data-testid="pt-return-summary" style={{
      background: '#1a2733', border: '1px solid #2d3a4a', borderRadius: 6,
      padding: '12px 14px', flex: 1, minWidth: 180,
    }}>
      <div style={{ fontSize: 10, color: '#718096', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>
        Return
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 12px' }}>
        {cell('Initial', `${account.currency} ${fmt(account.starting_cash)}`)}
        {cell('Latest',  `${account.currency} ${fmt(account.equity)}`)}
        {cell('Absolute', <span style={{ color: retColor }}>{account.currency} {fmt(absReturn)}</span>)}
        {cell('Return %', <span style={{ color: retColor }}>{pctReturn >= 0 ? '+' : ''}{pctReturn.toFixed(2)}%</span>)}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Trade Outcome Summary (P6)
// ---------------------------------------------------------------------------

function TradeOutcomeSummary({
  orders,
  fills,
  positions,
}: {
  orders: PaperOrder[]
  fills: PaperFill[]
  positions: PaperPosition[]
}) {
  const filled    = orders.filter(o => o.status === 'filled').length
  const rejected  = orders.filter(o => o.status === 'rejected').length
  const openPos   = positions.filter(p => p.is_open).length
  const closedPos = positions.filter(p => !p.is_open).length

  const cell = (label: string, val: string, color?: string) => (
    <div>
      <div style={{ fontSize: 10, color: '#718096', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 12, color: color ?? '#e2e8f0' }}>{val}</div>
    </div>
  )

  return (
    <div data-testid="pt-trade-outcome" style={{
      background: '#1a2733', border: '1px solid #2d3a4a', borderRadius: 6,
      padding: '12px 14px', flex: 1, minWidth: 180,
    }}>
      <div style={{ fontSize: 10, color: '#718096', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>
        Activity
      </div>
      {fills.length === 0 && (
        <div data-testid="pt-no-completed-trades" style={{ ...emptyStyle, marginBottom: 8 }}>
          No completed trades yet.
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 12px' }}>
        {cell('Total Orders',     String(orders.length))}
        {cell('Filled',           String(filled),    filled > 0 ? '#48bb78' : '#e2e8f0')}
        {cell('Rejected',         String(rejected),  rejected > 0 ? '#fc814a' : '#e2e8f0')}
        {cell('Total Fills',      String(fills.length))}
        {cell('Open Positions',   String(openPos))}
        {cell('Closed Positions', String(closedPos))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Session Detail View (P4/P5)
// ---------------------------------------------------------------------------

function SessionDetailView({
  sessionId,
  onBack,
}: {
  sessionId: string
  onBack: () => void
}) {
  const [detail, setDetail]       = useState<PaperTradingSessionDetail | null>(null)
  const [account, setAccount]     = useState<PaperAccount | null>(null)
  const [orders, setOrders]       = useState<PaperOrder[]>([])
  const [fills, setFills]         = useState<PaperFill[]>([])
  const [positions, setPositions] = useState<PaperPosition[]>([])
  const [equityCurve, setEquityCurve] = useState<PaperEquitySnapshot[]>([])
  const [currentDraftLifecycle, setCurrentDraftLifecycle] = useState<string | null>(null)

  const [loadingInitial, setLoadingInitial] = useState(true)
  const [refreshing, setRefreshing]         = useState(false)
  const [accountError, setAccountError]     = useState<string | null>(null)
  const [ordersError, setOrdersError]       = useState<string | null>(null)
  const [fillsError, setFillsError]         = useState<string | null>(null)
  const [positionsError, setPositionsError] = useState<string | null>(null)
  const [equityCurveError, setEquityCurveError] = useState<string | null>(null)

  const [actionError, setActionError] = useState<string | null>(null)
  const [cycleResult, setCycleResult] = useState<PaperCycleResult | null>(null)
  const [actioning, setActioning]     = useState(false)

  // P7 — paper-tested promotion state
  const [promoteStatus, setPromoteStatus] = useState<'idle' | 'promoting' | 'promoted' | 'error'>('idle')
  const [promoteError, setPromoteError]   = useState<string | null>(null)

  // P5 — trade ledger filter/sort state
  const [symbolFilter, setSymbolFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [sortOrder, setSortOrder]       = useState<'newest' | 'oldest'>('newest')

  const errMsg = (e: unknown) => (e instanceof Error ? e.message : 'Failed')

  async function load(initial: boolean) {
    if (initial) setLoadingInitial(true); else setRefreshing(true)
    setAccountError(null); setOrdersError(null); setFillsError(null)
    setPositionsError(null); setEquityCurveError(null)

    const [detailRes, accountRes, ordersRes, fillsRes, positionsRes, equityRes, draftsRes] = await Promise.allSettled([
      getPaperTradingSession(sessionId),
      getPaperTradingAccount(sessionId),
      listPaperTradingOrders(sessionId),
      listPaperTradingFills(sessionId),
      listPaperTradingPositions(sessionId),
      getEquityCurve(sessionId),
      fetchDrafts(),
    ])

    if (detailRes.status === 'fulfilled') {
      setDetail(detailRes.value)
      if (draftsRes.status === 'fulfilled') {
        const currentDraft = draftsRes.value.drafts.find(d => d.draft_id === detailRes.value.draft_id)
        setCurrentDraftLifecycle(currentDraft?.lifecycle_status ?? null)
      } else {
        setCurrentDraftLifecycle(null)
      }
    }
    if (accountRes.status === 'fulfilled')   setAccount(accountRes.value)
    else                                     setAccountError(errMsg(accountRes.reason))
    if (ordersRes.status === 'fulfilled')    setOrders(ordersRes.value)
    else                                     setOrdersError(errMsg(ordersRes.reason))
    if (fillsRes.status === 'fulfilled')     setFills(fillsRes.value)
    else                                     setFillsError(errMsg(fillsRes.reason))
    if (positionsRes.status === 'fulfilled') setPositions(positionsRes.value)
    else                                     setPositionsError(errMsg(positionsRes.reason))
    if (equityRes.status === 'fulfilled')    setEquityCurve(equityRes.value)
    else                                     setEquityCurveError(errMsg(equityRes.reason))

    if (initial) setLoadingInitial(false); else setRefreshing(false)
  }

  useEffect(() => { load(true) }, [sessionId]) // eslint-disable-line react-hooks/exhaustive-deps

  async function handleAction(fn: () => Promise<unknown>, isCycle = false) {
    setActionError(null)
    setCycleResult(null)
    setActioning(true)
    try {
      const result = await fn()
      if (isCycle && result != null) setCycleResult(result as PaperCycleResult)
      await load(false)
    } catch (err: unknown) {
      setActionError(errMsg(err))
    } finally {
      setActioning(false)
    }
  }

  if (loadingInitial && !detail) {
    return (
      <div>
        <button style={{ background: 'none', border: 'none', color: '#63b3ed', cursor: 'pointer', fontSize: 13, padding: 0, fontFamily: 'inherit' }} onClick={onBack}>
          ← Back
        </button>
        <div style={{ color: '#718096', marginTop: 16 }}>Loading session…</div>
      </div>
    )
  }

  const status       = detail?.status ?? ''
  const canRunCycle  = status === 'running' || status === 'pending'
  const canPause     = status === 'running'
  const canResume    = status === 'paused'
  const canTerminate = status === 'running' || status === 'paused' || status === 'pending'
  const busy         = actioning || refreshing
  const showPromotionPanel =
    detail?.lifecycle_status_at_activation === 'forward_tested' &&
    (currentDraftLifecycle === 'forward_tested' || promoteStatus === 'promoted')

  // P5 — build trade ledger rows
  const fillByOrderId = new Map(fills.map(f => [f.order_id, f]))
  let ledgerRows = orders.map(o => ({ order: o, fill: fillByOrderId.get(o.order_id) ?? null }))
  if (symbolFilter) {
    ledgerRows = ledgerRows.filter(r => r.order.symbol.toUpperCase().includes(symbolFilter.toUpperCase()))
  }
  if (statusFilter !== 'all') {
    ledgerRows = ledgerRows.filter(r => r.order.status === statusFilter)
  }
  if (sortOrder === 'newest') {
    ledgerRows = ledgerRows.slice().reverse()
  }

  const ptGuidance = detail ? computeGuidance({
    lifecycleStatus: detail.lifecycle_status_at_activation,
    hasPtSession: true,
    ptIsFinalized: status === 'terminated' || status === 'completed',
    ptHasBarEvidence:
      (status === 'terminated' || status === 'completed') &&
      detail.last_processed_bar_timestamp !== null,
  }) : null

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
        <button
          style={{ background: 'none', border: 'none', color: '#63b3ed', cursor: 'pointer', fontSize: 13, padding: 0, fontFamily: 'inherit' }}
          onClick={onBack}
        >
          ← Back
        </button>
        <span style={{ fontSize: 16, fontWeight: 600, color: '#e2e8f0' }}>
          {detail?.strategy_snapshot.display_name ?? sessionId.slice(0, 8)}
        </span>
        {detail && <StatusBadge status={detail.status} />}
        {refreshing && <span style={{ fontSize: 11, color: '#718096' }}>Refreshing…</span>}
      </div>

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        {canRunCycle && (
          <button
            data-testid="pt-run-cycle-btn"
            disabled={busy}
            onClick={() => handleAction(() => runPaperTradingCycle(sessionId), true)}
            style={{ ...btnStyle(true), opacity: busy ? 0.5 : 1, cursor: busy ? 'not-allowed' : 'pointer' }}
          >
            Process Next Bar
          </button>
        )}
        {canPause && (
          <button
            data-testid="pt-pause-btn"
            disabled={busy}
            onClick={() => handleAction(() => pausePaperTradingSession(sessionId))}
            style={{ ...btnStyle(), opacity: busy ? 0.5 : 1, cursor: busy ? 'not-allowed' : 'pointer' }}
          >
            Pause
          </button>
        )}
        {canResume && (
          <button
            data-testid="pt-resume-btn"
            disabled={busy}
            onClick={() => handleAction(() => resumePaperTradingSession(sessionId))}
            style={{ ...btnStyle(), opacity: busy ? 0.5 : 1, cursor: busy ? 'not-allowed' : 'pointer' }}
          >
            Resume
          </button>
        )}
        {canTerminate && (
          <button
            data-testid="pt-terminate-btn"
            disabled={busy}
            onClick={() => handleAction(() => terminatePaperTradingSession(sessionId))}
            style={{ ...btnStyle(), color: '#fc814a', opacity: busy ? 0.5 : 1, cursor: busy ? 'not-allowed' : 'pointer' }}
          >
            Terminate
          </button>
        )}
        <button
          data-testid="pt-refresh-btn"
          disabled={busy}
          onClick={() => load(false)}
          style={{ ...btnStyle(), opacity: busy ? 0.5 : 1, cursor: busy ? 'not-allowed' : 'pointer', marginLeft: 'auto' }}
        >
          ↻ Refresh
        </button>
      </div>

      {/* Action feedback */}
      {actionError && (
        <div data-testid="pt-action-error" style={{ ...errStyle, marginBottom: 10 }}>
          {actionError}
        </div>
      )}
      {cycleResult && (
        <div data-testid="pt-cycle-result" style={{
          background: '#0e2a1a', border: '1px solid #1a4a2a', borderRadius: 4,
          padding: '6px 10px', fontSize: 11, color: '#48bb78', marginBottom: 10,
        }}>
          Cycle: {cycleResult.message ?? `${cycleResult.bars_processed} bars processed`}
          {' · '}{cycleResult.fills_created} fill(s) · {cycleResult.signals_generated} signal(s)
        </div>
      )}

      {/* Lifecycle guidance */}
      {ptGuidance && (
        <LifecycleGuidanceCard
          currentStageLabel={ptGuidance.currentStageLabel}
          nextAction={ptGuidance.nextAction}
          whyItMatters={ptGuidance.whyItMatters}
          blockers={ptGuidance.blockers}
          navigateLocked={ptGuidance.navigateLocked}
        />
      )}

      {/* P7 — Paper-Tested Lifecycle Promotion */}
      {showPromotionPanel && (
        <div data-testid="pt-promote-panel" style={{
          background: '#0e1f1a',
          border: '1px solid #1a3a2a',
          borderRadius: 6,
          padding: '12px 14px',
          marginBottom: 12,
        }}>
          <div style={{ fontSize: 11, color: '#718096', marginBottom: 8, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Advance Stage
          </div>
          <div data-testid="pt-evidence-panel">
            <EvidenceReadinessPanel
              title="Promotion Evidence — Forward Test Complete → Paper Trading Evidence Complete"
              items={[
                {
                  label:       'Market Data Processed',
                  complete:    detail.last_processed_bar_timestamp !== null,
                  explanation: 'At least one market bar must be processed to confirm live data integration.',
                },
                {
                  label:       'Session Finalized',
                  complete:    detail.status === 'terminated' || detail.status === 'completed',
                  explanation: 'The session must be terminated or completed before promotion evidence can be reviewed.',
                },
                {
                  label:       'Equity Snapshot Recorded',
                  complete:    equityCurve.length > 0,
                  explanation: 'An equity snapshot confirms paper-trading activity was recorded during the session.',
                },
              ]}
            />
          </div>
          {promoteStatus === 'promoted' ? (
            <div data-testid="pt-promotion-success" style={{ color: '#48bb78', fontSize: 12 }}>
              Draft promoted to <strong>Paper Trading Evidence Complete</strong>. This session's evidence has been recorded.
            </div>
          ) : detail.last_processed_bar_timestamp === null ? (
            <div data-testid="pt-promotion-no-evidence" style={{ color: '#718096', fontSize: 12 }}>
              No paper-trading evidence yet. Run at least one cycle to generate promotion evidence.
            </div>
          ) : (detail.status !== 'terminated' && detail.status !== 'completed') ? (
            <div data-testid="pt-promotion-not-finalized" style={{ color: '#718096', fontSize: 12 }}>
              Session must be terminated or completed before promotion.
              Current status: <strong>{detail.status}</strong>. Terminate the session when ready.
            </div>
          ) : (
            <>
              <div style={{ fontSize: 11, color: '#a0aec0', marginBottom: 8 }}>
                Evidence confirmed: last bar processed at{' '}
                {new Date(detail.last_processed_bar_timestamp).toLocaleString()}.
                Session finalized ({detail.status}).
              </div>
              <button
                data-testid="promote-to-paper-tested-btn"
                disabled={promoteStatus === 'promoting'}
                onClick={async () => {
                  setPromoteStatus('promoting')
                  setPromoteError(null)
                  try {
                    await promoteDraftToPaperTested(sessionId, detail.draft_id)
                    setCurrentDraftLifecycle('paper_tested')
                    setPromoteStatus('promoted')
                  } catch (err: unknown) {
                    setPromoteError(err instanceof Error ? err.message : 'Promotion failed')
                    setPromoteStatus('error')
                  }
                }}
                style={{
                  background: promoteStatus === 'promoting' ? '#2d3a4a' : '#276749',
                  border: 'none',
                  borderRadius: 4,
                  color: '#e2e8f0',
                  cursor: promoteStatus === 'promoting' ? 'not-allowed' : 'pointer',
                  fontSize: 12,
                  fontFamily: 'inherit',
                  padding: '6px 14px',
                }}
              >
                {promoteStatus === 'promoting' ? 'Promoting…' : 'Advance to Paper Trading Evidence Complete'}
              </button>
            </>
          )}
          {promoteStatus === 'error' && promoteError && (
            <div data-testid="pt-promotion-error" style={{ color: '#fc814a', fontSize: 11, marginTop: 8 }}>
              {promoteError}
            </div>
          )}
        </div>
      )}

      {/* P6 — Performance Analytics */}
      <SectionBlock title="Performance Analytics">
        <EquityCurveChart snapshots={equityCurve} error={equityCurveError} />
        <div style={{ display: 'flex', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
          <DrawdownSummary account={account} snapshots={equityCurve} />
          <ReturnSummary account={account} />
          <TradeOutcomeSummary orders={orders} fills={fills} positions={positions} />
        </div>
      </SectionBlock>

      {/* P5 — Metrics Summary */}
      <MetricsSummary
        orders={orders}
        fills={fills}
        positions={positions}
        account={account}
      />

      {/* P4 — Account detail */}
      {account && <AccountDetailCard account={account} />}
      {accountError && (
        <div data-testid="pt-account-error" style={{ ...errStyle, marginBottom: 10 }}>
          Account: {accountError}
        </div>
      )}

      {/* P5 — Trade Ledger */}
      <SectionBlock title="Trade Ledger">
        <div style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            data-testid="pt-ledger-symbol-filter"
            placeholder="Filter by symbol…"
            value={symbolFilter}
            onChange={e => setSymbolFilter(e.target.value)}
            style={{ ...filterInputStyle, width: 140 }}
          />
          <select
            data-testid="pt-ledger-status-filter"
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            style={filterInputStyle}
          >
            <option value="all">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="filled">Filled</option>
            <option value="cancelled">Cancelled</option>
            <option value="rejected">Rejected</option>
          </select>
          <select
            data-testid="pt-ledger-sort"
            value={sortOrder}
            onChange={e => setSortOrder(e.target.value as 'newest' | 'oldest')}
            style={filterInputStyle}
          >
            <option value="newest">Newest First</option>
            <option value="oldest">Oldest First</option>
          </select>
        </div>

        {ledgerRows.length === 0 ? (
          <div data-testid="pt-ledger-empty" style={emptyStyle}>
            {orders.length === 0
              ? 'No trade activity yet. Run a paper cycle to generate simulated orders.'
              : 'No orders match the current filter.'}
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table data-testid="pt-trade-ledger" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead>
                <tr style={{ background: '#1a2233' }}>
                  <th style={thStyle}>Dir</th>
                  <th style={thStyle}>Symbol</th>
                  <th style={thStyle}>Qty</th>
                  <th style={thStyle}>Status</th>
                  <th style={thStyle}>Fill Price</th>
                  <th style={thStyle}>Fee</th>
                  <th style={thStyle}>Created</th>
                  <th style={thStyle}>Order ID</th>
                  <th style={thStyle}>Fill ID</th>
                </tr>
              </thead>
              <tbody>
                {ledgerRows.map(({ order: o, fill: f }, i) => (
                  <tr
                    key={o.order_id}
                    data-testid={`pt-ledger-row-${o.order_id}`}
                    style={{ background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)' }}
                  >
                    <td style={{ ...tdStyle, color: o.direction === 'buy' ? '#48bb78' : '#fc814a', fontWeight: 600 }}>
                      {o.direction.toUpperCase()}
                    </td>
                    <td style={tdStyle}>{o.symbol}</td>
                    <td style={tdStyle}>{o.quantity}</td>
                    <td style={tdStyle}><StatusBadge status={o.status} /></td>
                    <td style={tdStyle}>{f ? f.fill_price.toFixed(4) : '—'}</td>
                    <td style={tdStyle}>{f ? f.fee.toFixed(4) : '—'}</td>
                    <td style={{ ...tdStyle, color: '#718096' }}>
                      {new Date(o.created_at).toLocaleString()}
                    </td>
                    <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 10 }}>
                      {o.order_id.slice(0, 8)}…
                    </td>
                    <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 10 }}>
                      {f ? `${f.fill_id.slice(0, 8)}…` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionBlock>

      {/* P5 — Equity History */}
      <SectionBlock title="Equity History">
        {equityCurveError ? (
          <div data-testid="pt-equity-history-error" style={errStyle}>{equityCurveError}</div>
        ) : equityCurve.length === 0 ? (
          <div data-testid="pt-equity-history-empty" style={emptyStyle}>
            No equity snapshots yet. Run cycles to build equity history.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table data-testid="pt-equity-history-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead>
                <tr style={{ background: '#1a2233' }}>
                  <th style={thStyle}>Bar Timestamp</th>
                  <th style={thStyle}>Equity</th>
                  <th style={thStyle}>Cash</th>
                  <th style={thStyle}>Realized P&L</th>
                  <th style={thStyle}>Unrealized P&L</th>
                  <th style={thStyle}>Drawdown %</th>
                  <th style={thStyle}>Open Pos.</th>
                </tr>
              </thead>
              <tbody>
                {equityCurve.slice().reverse().map((s, i) => (
                  <tr key={s.snapshot_id} style={{ background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)' }}>
                    <td style={{ ...tdStyle, color: '#718096' }}>
                      {new Date(s.bar_timestamp).toLocaleString()}
                    </td>
                    <td style={tdStyle}>{s.equity.toFixed(2)}</td>
                    <td style={tdStyle}>{s.cash_balance.toFixed(2)}</td>
                    <td style={{ ...tdStyle, color: s.realized_pnl >= 0 ? '#48bb78' : '#fc814a' }}>
                      {s.realized_pnl.toFixed(2)}
                    </td>
                    <td style={{ ...tdStyle, color: s.unrealized_pnl >= 0 ? '#48bb78' : '#fc814a' }}>
                      {s.unrealized_pnl.toFixed(2)}
                    </td>
                    <td style={{ ...tdStyle, color: s.current_drawdown_pct > 10 ? '#fc814a' : '#a0aec0' }}>
                      {s.current_drawdown_pct.toFixed(2)}%
                    </td>
                    <td style={tdStyle}>{s.open_position_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionBlock>

      {/* P4 — Positions */}
      <SectionBlock title="Positions">
        {positionsError ? (
          <div data-testid="pt-positions-error" style={errStyle}>{positionsError}</div>
        ) : positions.length === 0 ? (
          <div data-testid="pt-positions-empty" style={emptyStyle}>No positions.</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table data-testid="pt-positions-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead>
                <tr style={{ background: '#1a2233' }}>
                  <th style={thStyle}>Symbol</th>
                  <th style={thStyle}>Qty</th>
                  <th style={thStyle}>Avg Entry</th>
                  <th style={thStyle}>Unrealized P&L</th>
                  <th style={thStyle}>Status</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p, i) => {
                  const upnl = p.unrealized_pnl
                  const upnlColor = upnl == null ? '#718096' : upnl >= 0 ? '#48bb78' : '#fc814a'
                  return (
                    <tr key={p.position_id} style={{ background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)' }}>
                      <td style={{ ...tdStyle, fontWeight: 600 }}>{p.symbol}</td>
                      <td style={tdStyle}>{p.quantity}</td>
                      <td style={tdStyle}>{p.average_entry_price.toFixed(4)}</td>
                      <td style={{ ...tdStyle, color: upnlColor }}>
                        {upnl != null ? upnl.toFixed(2) : '—'}
                      </td>
                      <td style={tdStyle}>{p.is_open ? 'Open' : 'Closed'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </SectionBlock>

      {/* P4 — Orders (raw) */}
      <SectionBlock title="Orders">
        {ordersError ? (
          <div data-testid="pt-orders-error" style={errStyle}>{ordersError}</div>
        ) : orders.length === 0 ? (
          <div data-testid="pt-orders-empty" style={emptyStyle}>No orders yet.</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table data-testid="pt-orders-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead>
                <tr style={{ background: '#1a2233' }}>
                  <th style={thStyle}>Dir</th>
                  <th style={thStyle}>Symbol</th>
                  <th style={thStyle}>Qty</th>
                  <th style={thStyle}>Status</th>
                  <th style={thStyle}>Created</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o, i) => (
                  <tr key={o.order_id} style={{ background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)' }}>
                    <td style={{ ...tdStyle, color: o.direction === 'buy' ? '#48bb78' : '#fc814a', fontWeight: 600 }}>
                      {o.direction.toUpperCase()}
                    </td>
                    <td style={tdStyle}>{o.symbol}</td>
                    <td style={tdStyle}>{o.quantity}</td>
                    <td style={tdStyle}><StatusBadge status={o.status} /></td>
                    <td style={{ ...tdStyle, color: '#718096' }}>{new Date(o.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionBlock>

      {/* P4 — Fills (raw) */}
      <SectionBlock title="Fills">
        {fillsError ? (
          <div data-testid="pt-fills-error" style={errStyle}>{fillsError}</div>
        ) : fills.length === 0 ? (
          <div data-testid="pt-fills-empty" style={emptyStyle}>No fills yet.</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table data-testid="pt-fills-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead>
                <tr style={{ background: '#1a2233' }}>
                  <th style={thStyle}>Dir</th>
                  <th style={thStyle}>Symbol</th>
                  <th style={thStyle}>Qty</th>
                  <th style={thStyle}>Fill Price</th>
                  <th style={thStyle}>Fee</th>
                  <th style={thStyle}>Date</th>
                </tr>
              </thead>
              <tbody>
                {fills.map((f, i) => (
                  <tr key={f.fill_id} style={{ background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)' }}>
                    <td style={{ ...tdStyle, color: f.direction === 'buy' ? '#48bb78' : '#fc814a', fontWeight: 600 }}>
                      {f.direction.toUpperCase()}
                    </td>
                    <td style={tdStyle}>{f.symbol}</td>
                    <td style={tdStyle}>{f.quantity}</td>
                    <td style={tdStyle}>{f.fill_price.toFixed(4)}</td>
                    <td style={{ ...tdStyle, color: '#718096' }}>{f.fee.toFixed(4)}</td>
                    <td style={{ ...tdStyle, color: '#718096' }}>{new Date(f.fill_bar_timestamp).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionBlock>

      {/* P4 — Session config */}
      {detail && (
        <div data-testid="pt-session-config" style={{
          background: '#1e2733',
          border: '1px solid #2d3a4a',
          borderRadius: 6,
          padding: '12px 14px',
          marginBottom: 12,
        }}>
          <div style={{ fontSize: 11, color: '#718096', marginBottom: 8, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Session Configuration
          </div>
          <Row label="Session ID"              value={detail.session_id} />
          <Row label="Draft"                   value={`${detail.strategy_snapshot.display_name} (${detail.strategy_snapshot.draft_id.slice(0, 8)}…)`} />
          <Row label="Symbol"                  value={detail.symbol} />
          <Row label="Timeframe"               value={detail.timeframe} />
          <Row label="Market Data Source"      value={detail.provider_name ?? '—'} />
          <Row label="Exchange"                value={detail.exchange} />
          <Row label="Asset Class"             value={detail.asset_class} />
          <Row label="Strategy Stage at Start" value={STAGE_LABELS[detail.lifecycle_status_at_activation] ?? detail.lifecycle_status_at_activation} />
          <Row label="Created"                 value={new Date(detail.created_at).toLocaleString()} />
          {detail.failure_reason && (
            <Row label="Failure Reason" value={detail.failure_reason} />
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Create Form (P3)
// ---------------------------------------------------------------------------

function CreateForm({
  onCreated,
  onCancel,
}: {
  onCreated: (session: PaperTradingSessionDetail) => void
  onCancel: () => void
}) {
  const [eligibleDrafts, setEligibleDrafts] = useState<StrategyDraftData[]>([])
  const [ftSessions, setFtSessions] = useState<ForwardTestSessionSummary[]>([])
  const [loadingMeta, setLoadingMeta] = useState(true)

  const [draftId, setDraftId]     = useState('')
  const [symbol, setSymbol]       = useState('AAPL')
  const [timeframe, setTimeframe] = useState('1d')
  const [provider, setProvider]   = useState('yahoo')
  const [exchange]   = useState('NASDAQ')
  const [assetClass] = useState('equity')
  const [ftSessionId, setFtSessionId] = useState<string>('')
  const [startingCash, setStartingCash] = useState('10000')

  const [submitting, setSubmitting] = useState(false)
  const [error, setError]           = useState<string | null>(null)

  // Load eligible drafts + FT sessions on mount
  useEffect(() => {
    Promise.all([
      fetchDrafts().catch(() => ({ drafts: [], count: 0 })),
      listForwardTestSessions().catch(() => []),
    ]).then(([draftResp, ftList]) => {
      const eligible = draftResp.drafts.filter(d => ELIGIBLE_PT_STATUSES.has(d.lifecycle_status ?? ''))
      setEligibleDrafts(eligible)
      setFtSessions(ftList)
      if (eligible.length > 0) setDraftId(eligible[0].draft_id)
    }).finally(() => setLoadingMeta(false))
  }, [])

  // Filter FT sessions by selected draft and evidence
  const matchingFtSessions = ftSessions.filter(s =>
    s.strategy_snapshot.draft_id === draftId &&
    s.signal_eligible_bars_processed > 0
  )

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const req: CreatePaperTradingSessionRequest = {
        draft_id:    draftId,
        symbol:      symbol.toUpperCase().trim(),
        timeframe,
        source_mode: 'provider',
        provider_name: provider || null,
        exchange,
        asset_class: assetClass,
        forward_test_session_id: ftSessionId || null,
        simulation_assumptions: {
          starting_cash: parseFloat(startingCash) || 10_000,
        },
      }
      const session = await createPaperTradingSession(req)
      onCreated(session)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Session creation failed')
    } finally {
      setSubmitting(false)
    }
  }

  const inputStyle: React.CSSProperties = {
    background: '#1a2233',
    border: '1px solid #2d3a4a',
    borderRadius: 4,
    color: '#e2e8f0',
    fontSize: 12,
    fontFamily: 'monospace',
    padding: '5px 8px',
    width: '100%',
    boxSizing: 'border-box',
  }
  const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: 11,
    color: '#718096',
    marginBottom: 4,
    marginTop: 10,
  }

  return (
    <form data-testid="pt-create-form" onSubmit={handleSubmit} style={{ maxWidth: 520 }}>
      <div style={{ fontSize: 15, fontWeight: 600, color: '#e2e8f0', marginBottom: 16 }}>
        New Paper Trading Session
      </div>

      {/* Lifecycle notice */}
      <div data-testid="pt-lifecycle-notice" style={{
        background: '#0e1a2e',
        border: '1px solid #1e3a5f',
        borderRadius: 4,
        padding: '8px 10px',
        marginBottom: 14,
        fontSize: 11,
        color: '#63b3ed',
      }}>
        Only forward-tested drafts may enter paper trading. Complete forward testing and promote your draft before creating a session.
      </div>

      {/* Draft picker */}
      <label style={labelStyle}>Strategy Draft</label>
      {loadingMeta ? (
        <div style={{ fontSize: 11, color: '#718096' }}>Loading eligible drafts…</div>
      ) : eligibleDrafts.length > 0 ? (
        <select
          data-testid="pt-draft-select"
          value={draftId}
          onChange={e => { setDraftId(e.target.value); setFtSessionId('') }}
          style={inputStyle}
          required
        >
          {eligibleDrafts.map(d => (
            <option key={d.draft_id} value={d.draft_id}>
              {d.display_name} [{d.lifecycle_status}]
            </option>
          ))}
        </select>
      ) : (
        <div data-testid="pt-no-eligible-drafts" style={{
          background: '#1a1000',
          border: '1px solid #3a2800',
          borderRadius: 4,
          padding: '8px 10px',
          fontSize: 11,
          color: '#8a7040',
        }}>
          No eligible drafts available. Complete forward testing and advance a draft to Forward Test Complete before paper trading.
        </div>
      )}

      {/* Optional FT session linkage */}
      {draftId && (
        <>
          <label style={labelStyle}>Link Forward-Test Session (optional)</label>
          {matchingFtSessions.length > 0 ? (
            <select
              data-testid="pt-ft-session-select"
              value={ftSessionId}
              onChange={e => setFtSessionId(e.target.value)}
              style={inputStyle}
            >
              <option value="">— None —</option>
              {matchingFtSessions.map(s => (
                <option key={s.session_id} value={s.session_id}>
                  {s.session_id.slice(0, 8)}… · {s.symbol}/{s.timeframe} · {s.status}
                </option>
              ))}
            </select>
          ) : (
            <div style={{ fontSize: 11, color: '#4a5568', fontStyle: 'italic' }}>
              No eligible forward-test sessions found for this draft. You may still create a session without linking one.
            </div>
          )}
        </>
      )}

      {/* Market config */}
      <label style={labelStyle}>Symbol</label>
      <input
        data-testid="pt-symbol-input"
        value={symbol}
        onChange={e => setSymbol(e.target.value)}
        placeholder="e.g. AAPL"
        style={inputStyle}
        required
      />

      <label style={labelStyle}>Timeframe</label>
      <select
        data-testid="pt-timeframe-select"
        value={timeframe}
        onChange={e => setTimeframe(e.target.value)}
        style={inputStyle}
      >
        {['1m','5m','15m','30m','1h','4h','1d','1w'].map(tf => (
          <option key={tf} value={tf}>{tf}</option>
        ))}
      </select>

      <label style={labelStyle}>Provider</label>
      <input
        data-testid="pt-provider-input"
        value={provider}
        onChange={e => setProvider(e.target.value)}
        placeholder="yahoo"
        style={inputStyle}
      />

      {/* Account settings */}
      <label style={labelStyle}>Starting Cash (USD)</label>
      <input
        data-testid="pt-starting-cash-input"
        type="number"
        min="1"
        step="100"
        value={startingCash}
        onChange={e => setStartingCash(e.target.value)}
        style={inputStyle}
        required
      />

      {error && (
        <div data-testid="pt-create-error" style={{ color: '#fc814a', fontSize: 11, marginTop: 10 }}>
          {error}
        </div>
      )}

      <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
        <button
          data-testid="pt-create-btn"
          type="submit"
          disabled={submitting || !draftId}
          style={{
            background: draftId && !submitting ? '#2b6cb0' : '#2d3a4a',
            border: 'none',
            borderRadius: 4,
            color: '#e2e8f0',
            cursor: draftId && !submitting ? 'pointer' : 'not-allowed',
            fontSize: 12,
            fontFamily: 'inherit',
            padding: '6px 16px',
          }}
        >
          {submitting ? 'Creating…' : 'Create Session'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          style={{
            background: 'none',
            border: '1px solid #2d3a4a',
            borderRadius: 4,
            color: '#718096',
            cursor: 'pointer',
            fontSize: 12,
            fontFamily: 'inherit',
            padding: '6px 14px',
          }}
        >
          Cancel
        </button>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Session List (P3)
// ---------------------------------------------------------------------------

function SessionList({
  sessions,
  onSelect,
  onNew,
}: {
  sessions: PaperTradingSessionSummary[]
  onSelect: (session: PaperTradingSessionSummary) => void
  onNew: () => void
}) {
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0' }}>Paper Trading Sessions</span>
        <button
          data-testid="pt-new-session-btn"
          onClick={onNew}
          style={{
            background: '#2b6cb0',
            border: 'none',
            borderRadius: 4,
            color: '#e2e8f0',
            cursor: 'pointer',
            fontSize: 12,
            fontFamily: 'inherit',
            padding: '5px 12px',
          }}
        >
          + New Session
        </button>
      </div>

      {sessions.length === 0 ? (
        <div data-testid="pt-empty-state" style={{
          background: '#1e2733',
          border: '1px solid #2d3a4a',
          borderRadius: 6,
          padding: '24px 20px',
          textAlign: 'center',
        }}>
          <div style={{ color: '#718096', fontSize: 13, marginBottom: 6 }}>
            No paper trading sessions yet.
          </div>
          <div style={{ color: '#4a5568', fontSize: 11 }}>
            Create a session from a forward-tested draft to start paper trading.
          </div>
        </div>
      ) : (
        <div data-testid="pt-session-list">
          {sessions.map(session => (
            <div
              key={session.session_id}
              style={{
                background: '#1e2733',
                border: '1px solid #2d3a4a',
                borderRadius: 6,
                padding: '12px 14px',
                marginBottom: 8,
                cursor: 'pointer',
              }}
              onClick={() => onSelect(session)}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                <button
                  data-testid={`pt-session-link-${session.session_id}`}
                  onClick={e => { e.stopPropagation(); onSelect(session) }}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: '#63b3ed',
                    cursor: 'pointer',
                    fontSize: 12,
                    fontFamily: 'monospace',
                    padding: 0,
                  }}
                >
                  {session.session_id.slice(0, 8)}…
                </button>
                <StatusBadge status={session.status} />
                <span style={{ fontSize: 11, color: '#718096', marginLeft: 'auto' }}>
                  {new Date(session.created_at).toLocaleDateString()}
                </span>
              </div>
              <div style={{ fontSize: 11, color: '#a0aec0' }}>
                {session.strategy_snapshot.display_name} · {session.symbol} / {session.timeframe} · {session.provider_name ?? 'provider'}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// PaperTradingPanel — root (P3)
// ---------------------------------------------------------------------------

type PanelView = 'list' | 'create' | 'detail'

export function PaperTradingPanel() {
  const { logout } = useAuth()
  const [view, setView]                           = useState<PanelView>('list')
  const [sessions, setSessions]                   = useState<PaperTradingSessionSummary[]>([])
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [loading, setLoading]                     = useState(true)
  const [listError, setListError]                 = useState<string | null>(null)

  function loadSessions() {
    setLoading(true)
    setListError(null)
    listPaperTradingSessions()
      .then(setSessions)
      .catch((err: unknown) => {
        if (isAuthError(err)) { logout(); return }
        if (isSubscriptionExpiredError(err)) return
        setListError(err instanceof Error ? err.message : 'Failed to load sessions')
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadSessions() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  function handleSessionCreated(session: PaperTradingSessionDetail) {
    setSessions(prev => [session, ...prev])
    setSelectedSessionId(session.session_id)
    setView('detail')
  }

  function handleSelectSession(session: PaperTradingSessionSummary) {
    setSelectedSessionId(session.session_id)
    setView('detail')
  }

  return (
    <div data-testid="pt-panel" style={{
      padding: '24px 28px',
      color: '#e2e8f0',
      fontFamily: 'monospace',
      fontSize: 13,
      background: '#1a202c',
      minHeight: '100%',
    }}>
      {loading && view === 'list' && (
        <div style={{ color: '#718096' }}>Loading paper trading sessions…</div>
      )}

      {listError && (
        <div data-testid="pt-list-error" style={{ color: '#fc814a', marginBottom: 12 }}>
          {listError}
        </div>
      )}

      {!loading && view === 'list' && (
        <SessionList
          sessions={sessions}
          onSelect={handleSelectSession}
          onNew={() => setView('create')}
        />
      )}

      {view === 'create' && (
        <CreateForm
          onCreated={handleSessionCreated}
          onCancel={() => setView('list')}
        />
      )}

      {view === 'detail' && selectedSessionId && (
        <SessionDetailView
          sessionId={selectedSessionId}
          onBack={() => { setView('list'); setSelectedSessionId(null) }}
        />
      )}
    </div>
  )
}
