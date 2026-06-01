/**
 * Paper Trading API client tests — Phase P8A.
 *
 * Covers the active paper-trading API client surface and auth/header behavior.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as session from '../../auth/session'

const SESSION_ID = 'aaaaaaaa-0001-4001-8001-000000000001'
const DRAFT_ID   = 'dddddddd-0001-4001-8001-000000000001'

const SESSION_SUMMARY = {
  session_id: SESSION_ID,
  status: 'running',
  symbol: 'AAPL',
  timeframe: '1d',
  source_mode: 'provider',
  provider_name: 'yahoo',
  catalog_id: null,
  exchange: 'NASDAQ',
  asset_class: 'equity',
  created_at: '2026-05-30T12:00:00+00:00',
  updated_at: '2026-05-30T12:00:00+00:00',
  last_processed_bar_timestamp: null,
  strategy_snapshot: {
    draft_id: DRAFT_ID,
    display_name: 'Paper Strategy',
    lifecycle_status: 'forward_tested',
    snapshot_hash: 'abc123',
  },
}

const SESSION_DETAIL = {
  ...SESSION_SUMMARY,
  draft_id: DRAFT_ID,
  account_id: 'bbbbbbbb-0001-4001-8001-000000000002',
  forward_test_session_id: null,
  lifecycle_status_at_activation: 'forward_tested',
  activation_timestamp: null,
  failure_reason: null,
  simulation_assumptions: {
    starting_cash: 10_000,
    currency: 'USD',
    fill_timing_model: 'next_bar_open',
    fee_mode: 'none',
    fee_value: 0,
    slippage_mode: 'none',
    slippage_value: 0,
    position_size_mode: 'fixed_quantity',
    position_size_value: 1,
    max_concurrent_positions: 1,
    max_drawdown_stop_pct: null,
    allow_short_selling: false,
  },
}

const ACCOUNT = {
  account_id: SESSION_DETAIL.account_id,
  session_id: SESSION_ID,
  currency: 'USD',
  starting_cash: 10_000,
  cash_balance: 9_900,
  equity: 10_100,
  available_cash: 9_900,
  peak_equity: 10_100,
  current_drawdown_pct: 0,
  total_realized_pnl: 100,
  total_fees_paid: 0,
  total_slippage_applied: 0,
  status: 'active',
  created_at: '2026-05-30T12:00:00+00:00',
  updated_at: '2026-05-30T12:05:00+00:00',
  closed_at: null,
}

const CYCLE_RESULT = {
  session_id: SESSION_ID,
  status: 'running',
  bars_fetched: 1,
  bars_processed: 1,
  warmup_bars_processed: 0,
  signal_eligible_bars_processed: 1,
  signals_generated: 0,
  signals_suppressed: 0,
  pending_orders_resolved: 0,
  orders_created: 0,
  orders_rejected: 0,
  fills_created: 0,
  positions_opened: 0,
  positions_closed: 0,
  account_snapshot_created: true,
  last_processed_bar_timestamp: '2026-05-30T12:00:00+00:00',
  gap_detected: false,
  provider_failure: false,
  activated: false,
  drawdown_stop_triggered: false,
  message: null,
}

const DRAFT_RESPONSE = {
  draft_id: DRAFT_ID,
  display_name: 'Paper Strategy',
  description: null,
  toolset: { toolset_id: DRAFT_ID, tools: [] },
  created_at: '2026-05-01T00:00:00+00:00',
  updated_at: '2026-05-30T12:10:00+00:00',
  enabled: true,
  tags: [],
  notes: null,
  lifecycle_status: 'paper_tested',
}

function mockOk(data: unknown, status = 200) {
  return vi.fn().mockResolvedValue(new Response(JSON.stringify(data), { status }))
}

function mockError(detail: string, status: number) {
  return vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail }), { status }))
}

beforeEach(() => { localStorage.clear(); vi.resetModules(); vi.restoreAllMocks() })
afterEach(() => { localStorage.clear(); vi.restoreAllMocks() })

describe('paperTrading API client', () => {
  it('creates a paper trading session with the expected payload', async () => {
    const fetchMock = mockOk(SESSION_DETAIL, 201)
    vi.stubGlobal('fetch', fetchMock)
    const { createPaperTradingSession } = await import('../paperTrading')

    const result = await createPaperTradingSession({
      draft_id: DRAFT_ID,
      symbol: 'AAPL',
      timeframe: '1d',
      source_mode: 'provider',
      provider_name: 'yahoo',
      forward_test_session_id: null,
      simulation_assumptions: { starting_cash: 10_000 },
    })

    expect(result.session_id).toBe(SESSION_ID)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/paper-trading/sessions')
    expect((init as RequestInit).method).toBe('POST')
    expect(JSON.parse((init as RequestInit).body as string).draft_id).toBe(DRAFT_ID)
  })

  it('lists sessions and injects Authorization header', async () => {
    session.storeToken('tok-pt')
    const fetchMock = mockOk([SESSION_SUMMARY])
    vi.stubGlobal('fetch', fetchMock)
    const { listPaperTradingSessions } = await import('../paperTrading')

    const result = await listPaperTradingSessions()

    expect(result).toHaveLength(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/paper-trading/sessions')
    expect(new Headers((init as RequestInit | undefined)?.headers).get('Authorization')).toBe('Bearer tok-pt')
  })

  it('loads session detail and account detail', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(SESSION_DETAIL), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(ACCOUNT), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const { getPaperTradingSession, getPaperTradingAccount } = await import('../paperTrading')

    await expect(getPaperTradingSession(SESSION_ID)).resolves.toMatchObject({ draft_id: DRAFT_ID })
    await expect(getPaperTradingAccount(SESSION_ID)).resolves.toMatchObject({ equity: 10_100 })
    expect(fetchMock.mock.calls[0][0]).toBe(`/paper-trading/sessions/${SESSION_ID}`)
    expect(fetchMock.mock.calls[1][0]).toBe(`/paper-trading/sessions/${SESSION_ID}/account`)
  })

  it('runs lifecycle and inspection endpoint calls against the expected URLs', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(CYCLE_RESULT), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...SESSION_DETAIL, status: 'paused' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...SESSION_DETAIL, status: 'running' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...SESSION_DETAIL, status: 'terminated' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const api = await import('../paperTrading')

    await api.runPaperTradingCycle(SESSION_ID)
    await api.pausePaperTradingSession(SESSION_ID)
    await api.resumePaperTradingSession(SESSION_ID)
    await api.terminatePaperTradingSession(SESSION_ID)
    await api.listPaperTradingOrders(SESSION_ID)
    await api.listPaperTradingFills(SESSION_ID)
    await api.listPaperTradingPositions(SESSION_ID)
    await api.getEquityCurve(SESSION_ID)

    expect(fetchMock.mock.calls.map(c => c[0])).toEqual([
      `/paper-trading/sessions/${SESSION_ID}/run-cycle`,
      `/paper-trading/sessions/${SESSION_ID}/pause`,
      `/paper-trading/sessions/${SESSION_ID}/resume`,
      `/paper-trading/sessions/${SESSION_ID}/terminate`,
      `/paper-trading/sessions/${SESSION_ID}/orders`,
      `/paper-trading/sessions/${SESSION_ID}/fills`,
      `/paper-trading/sessions/${SESSION_ID}/positions`,
      `/paper-trading/sessions/${SESSION_ID}/equity-curve`,
    ])
  })

  it('promotes a draft to paper_tested and sends notes as nullable', async () => {
    const fetchMock = mockOk(DRAFT_RESPONSE)
    vi.stubGlobal('fetch', fetchMock)
    const { promoteDraftToPaperTested } = await import('../paperTrading')

    const result = await promoteDraftToPaperTested(SESSION_ID, DRAFT_ID, 'reviewed')

    expect(result.lifecycle_status).toBe('paper_tested')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(`/paper-trading/sessions/${SESSION_ID}/promote-draft`)
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      draft_id: DRAFT_ID,
      notes: 'reviewed',
    })
  })

  it('throws backend detail on API errors', async () => {
    vi.stubGlobal('fetch', mockError('Run at least one complete paper-trading cycle', 422))
    const { promoteDraftToPaperTested } = await import('../paperTrading')

    await expect(promoteDraftToPaperTested(SESSION_ID, DRAFT_ID))
      .rejects.toThrow('Run at least one complete paper-trading cycle')
  })
})
