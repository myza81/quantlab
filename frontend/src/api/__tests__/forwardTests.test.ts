/**
 * Forward Testing API client tests — Phase 4C.5.
 *
 * Verifies:
 *  1.  createForwardTestSession — 201 parses and returns session detail
 *  2.  createForwardTestSession — error response throws Error with detail
 *  3.  createForwardTestSession — 401 throws AuthError
 *  4.  listForwardTestSessions  — 200 returns array
 *  5.  getForwardTestSession    — 200 returns session detail
 *  6.  runForwardTestCycle      — 200 returns cycle result
 *  7.  runForwardTestCycle      — 422 throws Error with detail
 *  8.  pauseForwardTestSession  — 200 returns updated session
 *  9.  resumeForwardTestSession — 200 returns updated session
 * 10.  terminateForwardTestSession — 200 returns updated session
 * 11.  listForwardTestSignals   — 200 returns array
 * 12.  listForwardTestBars      — 200 returns array
 * 13.  Authorization header is injected on all requests
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as session from '../../auth/session'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SESSION_SUMMARY = {
  session_id: 'aaaaaaaa-0001-0001-0001-000000000001',
  status: 'pending',
  symbol: 'AAPL',
  timeframe: '1d',
  source_mode: 'provider',
  provider_name: 'yahoo',
  catalog_id: null,
  created_at: '2026-05-30T12:00:00+00:00',
  updated_at: '2026-05-30T12:00:00+00:00',
  last_processed_bar_timestamp: null,
  bars_evaluated: 0,
  signal_eligible_bars_processed: 0,
  signals_recorded: 0,
  strategy_snapshot: {
    draft_id: 'draft-001',
    display_name: 'Test',
    lifecycle_status: 'backtested',
    snapshot_hash: 'abc123',
  },
}

const SESSION_DETAIL = {
  ...SESSION_SUMMARY,
  draft_id: 'draft-001',
  lifecycle_status_at_activation: 'backtested',
  warmup_bars_required: 0,
  warmup_bars_processed: 0,
  activation_timestamp: null,
  failure_reason: null,
  error_category: null,
  exchange: 'NASDAQ',
  asset_class: 'equity',
}

const CYCLE_RESULT = {
  session_id: SESSION_SUMMARY.session_id,
  status: 'running',
  bars_fetched: 0,
  bars_processed: 0,
  warmup_bars_processed: 0,
  signal_eligible_bars_processed: 0,
  signals_generated: 0,
  signals_suppressed: 0,
  last_processed_bar_timestamp: null,
  gap_detected: false,
  provider_failure: false,
  activated: true,
  message: null,
}

const SIGNAL = {
  signal_id: 'sig-001',
  session_id: SESSION_SUMMARY.session_id,
  bar_timestamp: '2026-05-29T16:00:00+00:00',
  signal_timestamp: '2026-05-29T17:00:00+00:00',
  signal_direction: 'entry_long',
  rule_id: 'entry',
  bar_open: 100, bar_high: 105, bar_low: 98, bar_close: 103, bar_volume: 1000,
  feature_values_at_signal: {},
  warmup_satisfied: true,
  strategy_snapshot_hash: 'abc123',
  symbol: 'AAPL',
  timeframe: '1d',
  provider_name: 'yahoo',
  catalog_id: null,
  created_at: '2026-05-29T17:00:00+00:00',
}

const BAR = {
  bar_index: 0,
  bar_timestamp: '2026-05-29T16:00:00+00:00',
  open: 100, high: 105, low: 98, close: 103, volume: 1000,
  is_warmup_bar: false,
  processed_at: '2026-05-29T17:00:00+00:00',
}

function mockOk(data: unknown, status = 200) {
  return vi.fn().mockResolvedValue(
    new Response(JSON.stringify(data), { status })
  )
}

function mockError(detail: string, status: number) {
  return vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ detail }), { status })
  )
}

beforeEach(() => { localStorage.clear(); vi.resetModules(); vi.restoreAllMocks() })
afterEach(() => { localStorage.clear(); vi.restoreAllMocks() })

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('createForwardTestSession', () => {
  it('parses and returns session detail on 201', async () => {
    vi.stubGlobal('fetch', mockOk(SESSION_DETAIL, 201))
    const { createForwardTestSession } = await import('../forwardTests')
    const result = await createForwardTestSession({
      draft_id: 'draft-001',
      symbol: 'AAPL',
      timeframe: '1d',
      source_mode: 'provider',
      provider_name: 'yahoo',
    })
    expect(result.session_id).toBe(SESSION_DETAIL.session_id)
    expect(result.warmup_bars_required).toBe(0)
    expect(result.exchange).toBe('NASDAQ')
  })

  it('throws Error with detail message on 422', async () => {
    vi.stubGlobal('fetch', mockError("strategy lifecycle 'draft' is not eligible", 422))
    const { createForwardTestSession } = await import('../forwardTests')
    await expect(
      createForwardTestSession({ draft_id: 'x', symbol: 'AAPL', timeframe: '1d', source_mode: 'provider' })
    ).rejects.toThrow("strategy lifecycle 'draft' is not eligible")
  })

  it('throws AuthError on 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('Unauthorized', { status: 401 })))
    const { createForwardTestSession } = await import('../forwardTests')
    await expect(
      createForwardTestSession({ draft_id: 'x', symbol: 'AAPL', timeframe: '1d', source_mode: 'provider' })
    ).rejects.toThrow('Authentication required')
  })
})

describe('listForwardTestSessions', () => {
  it('returns array of summaries on 200', async () => {
    vi.stubGlobal('fetch', mockOk([SESSION_SUMMARY]))
    const { listForwardTestSessions } = await import('../forwardTests')
    const result = await listForwardTestSessions()
    expect(result).toHaveLength(1)
    expect(result[0].session_id).toBe(SESSION_SUMMARY.session_id)
  })

  it('injects Authorization header', async () => {
    session.storeToken('tok-ft')
    const mockFetch = vi.fn().mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }))
    vi.stubGlobal('fetch', mockFetch)
    const { listForwardTestSessions } = await import('../forwardTests')
    await listForwardTestSessions()
    const [url, init] = mockFetch.mock.calls[0]
    expect(url).toBe('/forward-tests')
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer tok-ft')
  })
})

describe('getForwardTestSession', () => {
  it('returns session detail on 200', async () => {
    vi.stubGlobal('fetch', mockOk(SESSION_DETAIL))
    const { getForwardTestSession } = await import('../forwardTests')
    const result = await getForwardTestSession(SESSION_SUMMARY.session_id)
    expect(result.draft_id).toBe('draft-001')
    expect(result.exchange).toBe('NASDAQ')
  })
})

describe('runForwardTestCycle', () => {
  it('returns cycle result on 200', async () => {
    vi.stubGlobal('fetch', mockOk(CYCLE_RESULT))
    const { runForwardTestCycle } = await import('../forwardTests')
    const result = await runForwardTestCycle(SESSION_SUMMARY.session_id)
    expect(result.activated).toBe(true)
    expect(result.bars_fetched).toBe(0)
  })

  it('throws Error on 422 catalog rejection', async () => {
    vi.stubGlobal('fetch', mockError('catalog source mode does not support live polling cycles', 422))
    const { runForwardTestCycle } = await import('../forwardTests')
    await expect(runForwardTestCycle('some-id')).rejects.toThrow('catalog source mode')
  })
})

describe('pauseForwardTestSession', () => {
  it('returns updated session on 200', async () => {
    const paused = { ...SESSION_DETAIL, status: 'paused' }
    vi.stubGlobal('fetch', mockOk(paused))
    const { pauseForwardTestSession } = await import('../forwardTests')
    const result = await pauseForwardTestSession(SESSION_SUMMARY.session_id)
    expect(result.status).toBe('paused')
  })
})

describe('resumeForwardTestSession', () => {
  it('returns updated session on 200', async () => {
    const running = { ...SESSION_DETAIL, status: 'running' }
    vi.stubGlobal('fetch', mockOk(running))
    const { resumeForwardTestSession } = await import('../forwardTests')
    const result = await resumeForwardTestSession(SESSION_SUMMARY.session_id)
    expect(result.status).toBe('running')
  })
})

describe('terminateForwardTestSession', () => {
  it('returns terminated session on 200', async () => {
    const terminated = { ...SESSION_DETAIL, status: 'terminated' }
    vi.stubGlobal('fetch', mockOk(terminated))
    const { terminateForwardTestSession } = await import('../forwardTests')
    const result = await terminateForwardTestSession(SESSION_SUMMARY.session_id)
    expect(result.status).toBe('terminated')
  })
})

describe('listForwardTestSignals', () => {
  it('returns array of signals on 200', async () => {
    vi.stubGlobal('fetch', mockOk([SIGNAL]))
    const { listForwardTestSignals } = await import('../forwardTests')
    const result = await listForwardTestSignals(SESSION_SUMMARY.session_id)
    expect(result).toHaveLength(1)
    expect(result[0].signal_direction).toBe('entry_long')
  })
})

describe('listForwardTestBars', () => {
  it('returns array of bars on 200', async () => {
    vi.stubGlobal('fetch', mockOk([BAR]))
    const { listForwardTestBars } = await import('../forwardTests')
    const result = await listForwardTestBars(SESSION_SUMMARY.session_id)
    expect(result).toHaveLength(1)
    expect(result[0].bar_index).toBe(0)
  })
})
