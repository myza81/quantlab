/**
 * Tests for market data fetch — updated Phase 3P-A.
 *
 * Verifies:
 *   - fetchOHLCV always uses authedFetch (Authorization header injected, Phase 3P-A)
 *   - fetchOHLCV throws AuthError on 401 (token expiry)
 *   - credential_id is included as query param when provided
 *   - credential_id is NOT included in query when absent
 *   - fetch_metadata parsed and returned in response
 *   - fetch_metadata null/absent handled gracefully
 *   - 400 error detail propagated correctly
 *   - provider field present in response
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthError } from '../client'
import * as session from '../../auth/session'

// ---------------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------------

const MOCK_FETCH_METADATA = {
  dataset_id:      'equity__NASDAQ__AAPL__polygon__1d__adjusted',
  fingerprint:     'abc123def456789012345678901234567890abcdef',
  provider:        'polygon',
  symbol:          'AAPL',
  asset_class:     'equity',
  exchange:        'NASDAQ',
  timeframe:       '1d',
  start_utc:       '2025-01-01T00:00:00+00:00',
  end_utc:         '2026-01-01T00:00:00+00:00',
  adjustment_mode: 'adjusted',
  schema_version:  '1',
}

function makeOHLCVResponse(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    provider:      'polygon',
    symbol:        'AAPL',
    asset_class:   'equity',
    exchange:      'NASDAQ',
    timeframe:     '1d',
    start:         '2025-01-01T00:00:00+00:00',
    end:           '2026-01-01T00:00:00+00:00',
    candle_count:  5,
    candles:       [],
    fetch_metadata: MOCK_FETCH_METADATA,
    ...overrides,
  }
}

const BASE_PARAMS = {
  provider:    'yahoo',
  symbol:      'AAPL',
  asset_class: 'equity',
  exchange:    'NASDAQ',
  timeframe:   '1d',
  start:       '2025-01-01T00:00:00Z',
  end:         '2026-01-01T00:00:00Z',
}

// ---------------------------------------------------------------------------
// All fetches now use authedFetch (Phase 3P-A — subscription required for all OHLCV)
// ---------------------------------------------------------------------------

describe('fetchOHLCV — no credential_id (always authedFetch, Phase 3P-A)', () => {
  beforeEach(() => { localStorage.clear(); vi.restoreAllMocks() })
  afterEach(() => { localStorage.clear(); vi.restoreAllMocks() })

  it('ALWAYS injects Authorization header (authedFetch used for all OHLCV)', async () => {
    session.storeToken('tok-abc')
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(makeOHLCVResponse({ provider: 'yahoo' })), { status: 200 })
    )
    vi.stubGlobal('fetch', mockFetch)
    const { fetchOHLCV } = await import('../marketData')
    await fetchOHLCV(BASE_PARAMS)
    const [, init] = mockFetch.mock.calls[0]
    const headers = new Headers(init?.headers ?? {})
    expect(headers.get('Authorization')).toBe('Bearer tok-abc')
  })

  it('throws AuthError on 401 (token missing or expired)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    ))
    const { fetchOHLCV } = await import('../marketData')
    await expect(fetchOHLCV(BASE_PARAMS)).rejects.toThrow(AuthError)
  })

  it('does NOT include credential_id in query string when absent', async () => {
    session.storeToken('tok-abc')
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(makeOHLCVResponse({ provider: 'yahoo' })), { status: 200 })
    )
    vi.stubGlobal('fetch', mockFetch)
    const { fetchOHLCV } = await import('../marketData')
    await fetchOHLCV(BASE_PARAMS)
    const [url] = mockFetch.mock.calls[0]
    expect(url).not.toContain('credential_id')
  })

  it('returns response with fetch_metadata', async () => {
    session.storeToken('tok-abc')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify(makeOHLCVResponse()), { status: 200 })
    ))
    const { fetchOHLCV } = await import('../marketData')
    const result = await fetchOHLCV(BASE_PARAMS)
    expect(result.fetch_metadata).not.toBeNull()
    expect(result.fetch_metadata?.fingerprint).toBe(MOCK_FETCH_METADATA.fingerprint)
  })

  it('handles null fetch_metadata gracefully', async () => {
    session.storeToken('tok-abc')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify(makeOHLCVResponse({ fetch_metadata: null })), { status: 200 })
    ))
    const { fetchOHLCV } = await import('../marketData')
    const result = await fetchOHLCV(BASE_PARAMS)
    expect(result.fetch_metadata).toBeNull()
  })

  it('throws Error with detail on 400', async () => {
    session.storeToken('tok-abc')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Unsupported provider: badprovider' }), { status: 400 })
    ))
    const { fetchOHLCV } = await import('../marketData')
    await expect(fetchOHLCV({ ...BASE_PARAMS, provider: 'badprovider' }))
      .rejects.toThrow('Unsupported provider: badprovider')
  })
})

// ---------------------------------------------------------------------------
// Authenticated path — with credential_id
// ---------------------------------------------------------------------------

describe('fetchOHLCV — with credential_id (authedFetch)', () => {
  beforeEach(() => { localStorage.clear(); vi.restoreAllMocks() })
  afterEach(() => { localStorage.clear(); vi.restoreAllMocks() })

  it('injects Authorization header when token is stored', async () => {
    session.storeToken('tok-user-secret')
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(makeOHLCVResponse()), { status: 200 })
    )
    vi.stubGlobal('fetch', mockFetch)
    const { fetchOHLCV } = await import('../marketData')
    await fetchOHLCV({ ...BASE_PARAMS, provider: 'polygon', credential_id: 'cred-123' })
    const [, init] = mockFetch.mock.calls[0]
    const headers = new Headers(init.headers)
    expect(headers.get('Authorization')).toBe('Bearer tok-user-secret')
  })

  it('includes credential_id in query string', async () => {
    session.storeToken('tok-abc')
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(makeOHLCVResponse()), { status: 200 })
    )
    vi.stubGlobal('fetch', mockFetch)
    const { fetchOHLCV } = await import('../marketData')
    await fetchOHLCV({ ...BASE_PARAMS, provider: 'polygon', credential_id: 'cred-abc' })
    const [url] = mockFetch.mock.calls[0]
    expect(url).toContain('credential_id=cred-abc')
  })

  it('throws AuthError on 401 (token expired / missing)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    ))
    const { fetchOHLCV } = await import('../marketData')
    await expect(
      fetchOHLCV({ ...BASE_PARAMS, provider: 'polygon', credential_id: 'cred-123' })
    ).rejects.toThrow(AuthError)
  })

  it('throws Error with detail on 400 credential error', async () => {
    session.storeToken('tok-abc')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Provider credential is disabled' }), { status: 400 })
    ))
    const { fetchOHLCV } = await import('../marketData')
    await expect(
      fetchOHLCV({ ...BASE_PARAMS, provider: 'polygon', credential_id: 'cred-disabled' })
    ).rejects.toThrow('Provider credential is disabled')
  })

  it('parses fetch_metadata from response', async () => {
    session.storeToken('tok-abc')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify(makeOHLCVResponse()), { status: 200 })
    ))
    const { fetchOHLCV } = await import('../marketData')
    const result = await fetchOHLCV({ ...BASE_PARAMS, provider: 'polygon', credential_id: 'cred-123' })
    expect(result.fetch_metadata?.dataset_id).toBe(MOCK_FETCH_METADATA.dataset_id)
    expect(result.fetch_metadata?.fingerprint).toBe(MOCK_FETCH_METADATA.fingerprint)
    expect(result.fetch_metadata?.provider).toBe('polygon')
  })
})

// ---------------------------------------------------------------------------
// Credential filtering — verifies the API client correctly passes credential_id
// ---------------------------------------------------------------------------

describe('fetchOHLCV — credential_id query param behaviour', () => {
  beforeEach(() => { localStorage.clear(); vi.restoreAllMocks() })
  afterEach(() => { localStorage.clear(); vi.restoreAllMocks() })

  it('omits credential_id when explicitly undefined', async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(makeOHLCVResponse()), { status: 200 })
    )
    vi.stubGlobal('fetch', mockFetch)
    const { fetchOHLCV } = await import('../marketData')
    await fetchOHLCV({ ...BASE_PARAMS, credential_id: undefined })
    const [url] = mockFetch.mock.calls[0]
    expect(url).not.toContain('credential_id')
  })

  it('sends correct provider in query string', async () => {
    session.storeToken('tok-abc')
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(makeOHLCVResponse()), { status: 200 })
    )
    vi.stubGlobal('fetch', mockFetch)
    const { fetchOHLCV } = await import('../marketData')
    await fetchOHLCV({ ...BASE_PARAMS, provider: 'polygon', credential_id: 'cred-xyz' })
    const [url] = mockFetch.mock.calls[0]
    expect(url).toContain('provider=polygon')
    expect(url).toContain('credential_id=cred-xyz')
  })
})
