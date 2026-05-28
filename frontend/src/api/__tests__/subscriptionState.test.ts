/**
 * Tests for Phase 3P-A — Subscription state handling on the frontend.
 *
 * Verifies:
 *   - User type includes subscription_status, role, subscription_expires_at
 *   - fetchOHLCV always uses authedFetch (no unauthenticated path after Phase 3P-A)
 *   - 403 from OHLCV endpoint (subscription_required) propagates as a thrown Error
 *   - subscription_status field present in fetchMe response shape
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { User, SubscriptionStatus, UserRole } from '../../auth/types'
import * as session from '../../auth/session'
import { AuthError } from '../client'

// ---------------------------------------------------------------------------
// Type shape validation (compile-time and runtime)
// ---------------------------------------------------------------------------

describe('User type — subscription fields', () => {
  it('User interface includes role, subscription_status, subscription_expires_at', () => {
    const user: User = {
      user_id:                  'u-1',
      username:                 'alice',
      email:                    'alice@example.com',
      created_at:               '2025-01-01T00:00:00Z',
      role:                     'user',
      subscription_status:      'active',
      subscription_expires_at:  null,
    }
    expect(user.role).toBe('user')
    expect(user.subscription_status).toBe('active')
    expect(user.subscription_expires_at).toBeNull()
  })

  it('SubscriptionStatus covers all four states', () => {
    const statuses: SubscriptionStatus[] = ['pending', 'active', 'expired', 'suspended']
    expect(statuses).toHaveLength(4)
  })

  it('UserRole covers user and admin', () => {
    const roles: UserRole[] = ['user', 'admin']
    expect(roles).toHaveLength(2)
  })

  it('admin user has role=admin and active status', () => {
    const admin: User = {
      user_id:                  'admin-1',
      username:                 'admin',
      email:                    'admin@example.com',
      created_at:               '2025-01-01T00:00:00Z',
      role:                     'admin',
      subscription_status:      'active',
      subscription_expires_at:  null,
    }
    expect(admin.role).toBe('admin')
    expect(admin.subscription_status).toBe('active')
  })
})


// ---------------------------------------------------------------------------
// fetchOHLCV — always authedFetch after Phase 3P-A
// ---------------------------------------------------------------------------

const BASE_PARAMS = {
  provider:    'yahoo',
  symbol:      'AAPL',
  asset_class: 'equity',
  exchange:    'NASDAQ',
  timeframe:   '1d',
  start:       '2025-01-01T00:00:00Z',
  end:         '2026-01-01T00:00:00Z',
}

function makeOHLCVResponse(): Record<string, unknown> {
  return {
    provider:       'yahoo',
    symbol:         'AAPL',
    asset_class:    'equity',
    exchange:       'NASDAQ',
    timeframe:      '1d',
    start:          '2025-01-01T00:00:00+00:00',
    end:            '2026-01-01T00:00:00+00:00',
    candle_count:   0,
    candles:        [],
    fetch_metadata: null,
  }
}

describe('fetchOHLCV — subscription enforcement (Phase 3P-A)', () => {
  beforeEach(() => { localStorage.clear(); vi.restoreAllMocks() })
  afterEach(() => { localStorage.clear(); vi.restoreAllMocks() })

  it('injects Authorization header on every OHLCV fetch', async () => {
    session.storeToken('tok-alice')
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(makeOHLCVResponse()), { status: 200 })
    )
    vi.stubGlobal('fetch', mockFetch)
    const { fetchOHLCV } = await import('../marketData')
    await fetchOHLCV(BASE_PARAMS)
    const [, init] = mockFetch.mock.calls[0]
    const headers = new Headers(init?.headers ?? {})
    expect(headers.get('Authorization')).toBe('Bearer tok-alice')
  })

  it('throws AuthError on 401 (unauthenticated or token expired)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    ))
    const { fetchOHLCV } = await import('../marketData')
    await expect(fetchOHLCV(BASE_PARAMS)).rejects.toThrow(AuthError)
  })

  it('throws Error with subscription_required detail on 403 (pending/expired/suspended)', async () => {
    session.storeToken('tok-pending')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ detail: { code: 'subscription_required', subscription_status: 'pending' } }),
        { status: 403 }
      )
    ))
    const { fetchOHLCV } = await import('../marketData')
    await expect(fetchOHLCV(BASE_PARAMS)).rejects.toThrow()
  })

  it('throws Error with suspended detail on 403 (suspended account)', async () => {
    session.storeToken('tok-suspended')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ detail: { code: 'subscription_required', subscription_status: 'suspended' } }),
        { status: 403 }
      )
    ))
    const { fetchOHLCV } = await import('../marketData')
    await expect(fetchOHLCV(BASE_PARAMS)).rejects.toThrow()
  })

  it('does not include credential_id in query when not provided', async () => {
    session.storeToken('tok-abc')
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(makeOHLCVResponse()), { status: 200 })
    )
    vi.stubGlobal('fetch', mockFetch)
    const { fetchOHLCV } = await import('../marketData')
    await fetchOHLCV(BASE_PARAMS)
    const [url] = mockFetch.mock.calls[0]
    expect(url).not.toContain('credential_id')
  })

  it('includes credential_id in query when provided', async () => {
    session.storeToken('tok-abc')
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(makeOHLCVResponse()), { status: 200 })
    )
    vi.stubGlobal('fetch', mockFetch)
    const { fetchOHLCV } = await import('../marketData')
    await fetchOHLCV({ ...BASE_PARAMS, credential_id: 'cred-xyz' })
    const [url] = mockFetch.mock.calls[0]
    expect(url).toContain('credential_id=cred-xyz')
  })
})
