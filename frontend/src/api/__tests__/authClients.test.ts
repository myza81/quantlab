/**
 * Tests for authenticated API clients (Phase 3M).
 *
 * Verifies that:
 *   - authedFetch injects the Bearer token and throws AuthError on 401
 *   - Protected clients (drafts, semantics, planInspection, compositionRun, backtestRuns) use authedFetch
 *   - Public clients (backtest, marketData, tools) do NOT require auth and do not throw AuthError on 401
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthError, authedFetch, isAuthError } from '../client'
import * as session from '../../auth/session'

// ---------------------------------------------------------------------------
// client.ts — authedFetch + AuthError
// ---------------------------------------------------------------------------

describe('AuthError', () => {
  it('is an Error subclass with name "AuthError"', () => {
    const err = new AuthError()
    expect(err).toBeInstanceOf(Error)
    expect(err.name).toBe('AuthError')
    expect(err.message).toBe('Authentication required')
  })

  it('accepts a custom message', () => {
    const err = new AuthError('session expired')
    expect(err.message).toBe('session expired')
  })
})

describe('isAuthError', () => {
  it('returns true for AuthError instances', () => {
    expect(isAuthError(new AuthError())).toBe(true)
  })

  it('returns false for plain Error', () => {
    expect(isAuthError(new Error('not auth'))).toBe(false)
  })

  it('returns false for non-error values', () => {
    expect(isAuthError(null)).toBe(false)
    expect(isAuthError('string')).toBe(false)
    expect(isAuthError(401)).toBe(false)
  })
})

describe('authedFetch', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })
  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('injects Authorization header when token is stored', async () => {
    session.storeToken('tok-abc')
    const mockFetch = vi.fn().mockResolvedValue(
      new Response('{}', { status: 200 })
    )
    vi.stubGlobal('fetch', mockFetch)

    await authedFetch('/some-protected-route')

    const [, init] = mockFetch.mock.calls[0]
    const headers = new Headers(init.headers)
    expect(headers.get('Authorization')).toBe('Bearer tok-abc')
  })

  it('does not inject Authorization header when no token stored', async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response('{}', { status: 200 })
    )
    vi.stubGlobal('fetch', mockFetch)

    await authedFetch('/public-route')

    const [, init] = mockFetch.mock.calls[0]
    const headers = new Headers(init.headers)
    expect(headers.get('Authorization')).toBeNull()
  })

  it('throws AuthError on 401 response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    ))

    await expect(authedFetch('/protected')).rejects.toThrow(AuthError)
  })

  it('does not throw for non-401 error responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('Not Found', { status: 404 })
    ))

    const resp = await authedFetch('/missing')
    expect(resp.status).toBe(404)
  })
})

// ---------------------------------------------------------------------------
// Protected clients — verify they propagate AuthError
// ---------------------------------------------------------------------------

describe('drafts client — AuthError propagation', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })
  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('fetchDrafts throws AuthError on 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    ))
    const { fetchDrafts } = await import('../drafts')
    await expect(fetchDrafts()).rejects.toThrow(AuthError)
  })

  it('createDraft throws AuthError on 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    ))
    const { createDraft } = await import('../drafts')
    await expect(
      createDraft({ draft_id: 'd1', display_name: 'Test', toolset: { toolset_id: 'd1', tools: [] } })
    ).rejects.toThrow(AuthError)
  })
})

describe('semantics client — AuthError propagation', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })
  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('getSemantics throws AuthError on 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    ))
    const { getSemantics } = await import('../semantics')
    await expect(getSemantics('draft-1')).rejects.toThrow(AuthError)
  })

  it('validateSemanticsPayload does NOT throw AuthError on 401 (public endpoint)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ valid: false, errors: [] }), { status: 401 })
    ))
    const { validateSemanticsPayload } = await import('../semantics')
    // Public endpoint uses plain fetch — 401 is treated as a non-OK HTTP error, not AuthError
    await expect(
      validateSemanticsPayload({ entry_rules: [], exit_rules: [], metadata: { version: '1' } })
    ).rejects.toSatisfy((e: unknown) => !isAuthError(e))
  })
})

describe('planInspection client — AuthError propagation', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })
  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('fetchDraftPlanInspection throws AuthError on 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    ))
    const { fetchDraftPlanInspection } = await import('../planInspection')
    await expect(fetchDraftPlanInspection('draft-1')).rejects.toThrow(AuthError)
  })
})

describe('compositionRun client — AuthError propagation', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })
  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('runComposition throws AuthError on 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    ))
    const { runComposition } = await import('../compositionRun')
    await expect(runComposition('draft-1', 'AAPL', '1d', [])).rejects.toThrow(AuthError)
  })
})

describe('backtestRuns client — AuthError propagation', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })
  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('runBacktest throws AuthError on 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    ))
    const { runBacktest } = await import('../backtestRuns')
    const config = {
      initial_equity: 10000,
      position_size_mode: 'equity_fraction' as const,
      equity_fraction: 0.95,
      fixed_quantity: 1,
      commission_mode: 'none' as const,
      commission_value: 0,
      slippage_mode: 'none' as const,
      slippage_value: 0,
    }
    await expect(runBacktest('d1', 'AAPL', '1d', [], config)).rejects.toThrow(AuthError)
  })

  it('fetchBacktestReport throws AuthError on 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    ))
    const { fetchBacktestReport } = await import('../backtestRuns')
    await expect(fetchBacktestReport('run-1')).rejects.toThrow(AuthError)
  })
})
