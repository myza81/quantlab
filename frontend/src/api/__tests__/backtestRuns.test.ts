/**
 * Backtest Runs API client tests — Phase R4.
 *
 * Covers:
 *  1. promoteDraftToBacktested — 200 returns updated draft
 *  2. promoteDraftToBacktested — 422 lifecycle error throws Error with detail
 *  3. promoteDraftToBacktested — 404 not-found throws Error
 *  4. promoteDraftToBacktested — 400 bad run_id throws Error
 *  5. promoteDraftToBacktested — optional notes sent in request body
 *  6. promoteDraftToBacktested — notes omitted when not provided
 *  7. promoteDraftToBacktested — Authorization header injected
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as session from '../../auth/session'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const RUN_ID   = 'aaaaaaaa-0001-4001-8001-000000000001'
const DRAFT_ID = 'bbbbbbbb-0002-4002-8002-000000000002'

const DRAFT_RESPONSE = {
  draft_id:         DRAFT_ID,
  display_name:     'Test Strategy',
  description:      null,
  toolset:          { toolset_id: DRAFT_ID, tools: [] },
  created_at:       '2026-01-01T00:00:00Z',
  updated_at:       '2026-05-31T00:00:00Z',
  enabled:          true,
  tags:             [],
  notes:            null,
  lifecycle_status: 'backtested',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockOk(data: unknown, status = 200) {
  return vi.fn().mockResolvedValue(new Response(JSON.stringify(data), { status }))
}

function mockError(detail: string, status: number) {
  return vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail }), { status }))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

beforeEach(() => { localStorage.clear(); vi.resetModules(); vi.restoreAllMocks() })
afterEach(() => { localStorage.clear(); vi.restoreAllMocks() })

describe('promoteDraftToBacktested', () => {

  it('returns updated DraftResponse on 200', async () => {
    vi.stubGlobal('fetch', mockOk(DRAFT_RESPONSE))
    const { promoteDraftToBacktested } = await import('../backtestRuns')
    const result = await promoteDraftToBacktested(RUN_ID, DRAFT_ID)
    expect(result.lifecycle_status).toBe('backtested')
    expect(result.draft_id).toBe(DRAFT_ID)
  })

  it('throws Error with backend detail on 422 lifecycle error', async () => {
    vi.stubGlobal('fetch', mockError('Only completed runs qualify as promotion evidence.', 422))
    const { promoteDraftToBacktested } = await import('../backtestRuns')
    await expect(promoteDraftToBacktested(RUN_ID, DRAFT_ID))
      .rejects.toThrow('Only completed runs qualify as promotion evidence.')
  })

  it('throws Error on 404 not-found', async () => {
    vi.stubGlobal('fetch', mockError("Backtest run not found.", 404))
    const { promoteDraftToBacktested } = await import('../backtestRuns')
    await expect(promoteDraftToBacktested(RUN_ID, DRAFT_ID)).rejects.toThrow()
  })

  it('throws Error on 400 bad run_id format', async () => {
    vi.stubGlobal('fetch', mockError('run_id must be a valid UUID.', 400))
    const { promoteDraftToBacktested } = await import('../backtestRuns')
    await expect(promoteDraftToBacktested('not-a-uuid', DRAFT_ID))
      .rejects.toThrow('run_id must be a valid UUID.')
  })

  it('includes notes in request body when provided', async () => {
    const fetchMock = mockOk(DRAFT_RESPONSE)
    vi.stubGlobal('fetch', fetchMock)
    const { promoteDraftToBacktested } = await import('../backtestRuns')
    await promoteDraftToBacktested(RUN_ID, DRAFT_ID, 'Reviewed equity curve')
    const [, init] = fetchMock.mock.calls[0]
    const body = JSON.parse((init as RequestInit).body as string)
    expect(body.notes).toBe('Reviewed equity curve')
    expect(body.draft_id).toBe(DRAFT_ID)
  })

  it('omits notes from request body when not provided', async () => {
    const fetchMock = mockOk(DRAFT_RESPONSE)
    vi.stubGlobal('fetch', fetchMock)
    const { promoteDraftToBacktested } = await import('../backtestRuns')
    await promoteDraftToBacktested(RUN_ID, DRAFT_ID)
    const [, init] = fetchMock.mock.calls[0]
    const body = JSON.parse((init as RequestInit).body as string)
    expect(body.notes).toBeUndefined()
    expect(body.draft_id).toBe(DRAFT_ID)
  })

  it('injects Authorization header', async () => {
    session.storeToken('tok-r4')
    const fetchMock = mockOk(DRAFT_RESPONSE)
    vi.stubGlobal('fetch', fetchMock)
    const { promoteDraftToBacktested } = await import('../backtestRuns')
    await promoteDraftToBacktested(RUN_ID, DRAFT_ID)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(`/backtests/runs/${RUN_ID}/promote-draft`)
    expect(new Headers((init as RequestInit).headers).get('Authorization')).toBe('Bearer tok-r4')
  })
})
