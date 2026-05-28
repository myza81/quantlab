/**
 * Tests for the provider credential API client — Phase 3N.
 *
 * Verifies:
 *   - All vault endpoints use authedFetch (throw AuthError on 401)
 *   - fetchCredentials parses and returns CredentialListResponse
 *   - registerCredential sends POST with correct body and parses response
 *   - disableCredential sends PATCH and parses response
 *   - deleteCredential handles 204 No Content correctly
 *   - Authorization header is injected on all requests
 *   - CredentialMetadata type has no secret fields (type-level test via undefined check)
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthError } from '../client'
import * as session from '../../auth/session'

// ---------------------------------------------------------------------------
// Shared fixture
// ---------------------------------------------------------------------------

const MOCK_CREDENTIAL = {
  credential_id:    'cred-123',
  provider_name:    'polygon',
  credential_label: 'My Key',
  active:           true,
  created_at:       '2026-01-01T00:00:00+00:00',
  updated_at:       '2026-01-01T00:00:00+00:00',
}

// ---------------------------------------------------------------------------
// fetchCredentials
// ---------------------------------------------------------------------------

describe('fetchCredentials', () => {
  beforeEach(() => { localStorage.clear(); vi.restoreAllMocks() })
  afterEach(() => { localStorage.clear(); vi.restoreAllMocks() })

  it('throws AuthError on 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    ))
    const { fetchCredentials } = await import('../credentials')
    await expect(fetchCredentials()).rejects.toThrow(AuthError)
  })

  it('returns CredentialListResponse on 200', async () => {
    const payload = { credentials: [MOCK_CREDENTIAL], total: 1 }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 })
    ))
    const { fetchCredentials } = await import('../credentials')
    const result = await fetchCredentials()
    expect(result.total).toBe(1)
    expect(result.credentials).toHaveLength(1)
    expect(result.credentials[0].credential_id).toBe('cred-123')
    expect(result.credentials[0].provider_name).toBe('polygon')
  })

  it('injects Authorization header', async () => {
    session.storeToken('tok-xyz')
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ credentials: [], total: 0 }), { status: 200 })
    )
    vi.stubGlobal('fetch', mockFetch)
    const { fetchCredentials } = await import('../credentials')
    await fetchCredentials()
    const [url, init] = mockFetch.mock.calls[0]
    expect(url).toBe('/provider-credentials')
    const headers = new Headers(init.headers)
    expect(headers.get('Authorization')).toBe('Bearer tok-xyz')
  })

  it('returns empty list when no credentials exist', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ credentials: [], total: 0 }), { status: 200 })
    ))
    const { fetchCredentials } = await import('../credentials')
    const result = await fetchCredentials()
    expect(result.credentials).toHaveLength(0)
    expect(result.total).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// registerCredential
// ---------------------------------------------------------------------------

describe('registerCredential', () => {
  beforeEach(() => { localStorage.clear(); vi.restoreAllMocks() })
  afterEach(() => { localStorage.clear(); vi.restoreAllMocks() })

  it('throws AuthError on 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    ))
    const { registerCredential } = await import('../credentials')
    await expect(
      registerCredential({ provider_name: 'polygon', credential_label: 'Key', secret_value: 'sk_abc' })
    ).rejects.toThrow(AuthError)
  })

  it('sends POST with correct JSON body', async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(MOCK_CREDENTIAL), { status: 201 })
    )
    vi.stubGlobal('fetch', mockFetch)
    const { registerCredential } = await import('../credentials')
    await registerCredential({
      provider_name:    'polygon',
      credential_label: 'My Key',
      secret_value:     'sk_secret',
    })
    const [url, init] = mockFetch.mock.calls[0]
    expect(url).toBe('/provider-credentials')
    expect(init.method).toBe('POST')
    const body = JSON.parse(init.body as string)
    expect(body.provider_name).toBe('polygon')
    expect(body.credential_label).toBe('My Key')
    expect(body.secret_value).toBe('sk_secret')
  })

  it('returns CredentialMetadata on 201', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify(MOCK_CREDENTIAL), { status: 201 })
    ))
    const { registerCredential } = await import('../credentials')
    const result = await registerCredential({
      provider_name: 'polygon', credential_label: 'My Key', secret_value: 'sk_abc',
    })
    expect(result.credential_id).toBe('cred-123')
    expect(result.active).toBe(true)
    // Verify no secret fields appear in the returned object
    expect((result as unknown as Record<string, unknown>).secret_value).toBeUndefined()
    expect((result as unknown as Record<string, unknown>).encrypted_secret).toBeUndefined()
  })

  it('throws descriptive error on 422', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'provider_name must not be empty' }), { status: 422 })
    ))
    const { registerCredential } = await import('../credentials')
    await expect(
      registerCredential({ provider_name: '', credential_label: 'Key', secret_value: 'sk' })
    ).rejects.toThrow('provider_name must not be empty')
  })
})

// ---------------------------------------------------------------------------
// disableCredential
// ---------------------------------------------------------------------------

describe('disableCredential', () => {
  beforeEach(() => { localStorage.clear(); vi.restoreAllMocks() })
  afterEach(() => { localStorage.clear(); vi.restoreAllMocks() })

  it('throws AuthError on 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    ))
    const { disableCredential } = await import('../credentials')
    await expect(disableCredential('cred-123')).rejects.toThrow(AuthError)
  })

  it('sends PATCH to correct URL', async () => {
    const disabled = { ...MOCK_CREDENTIAL, active: false }
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(disabled), { status: 200 })
    )
    vi.stubGlobal('fetch', mockFetch)
    const { disableCredential } = await import('../credentials')
    const result = await disableCredential('cred-123')
    const [url, init] = mockFetch.mock.calls[0]
    expect(url).toBe('/provider-credentials/cred-123/disable')
    expect(init.method).toBe('PATCH')
    expect(result.active).toBe(false)
  })

  it('returns updated CredentialMetadata with active=false', async () => {
    const disabled = { ...MOCK_CREDENTIAL, active: false }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify(disabled), { status: 200 })
    ))
    const { disableCredential } = await import('../credentials')
    const result = await disableCredential('cred-123')
    expect(result.active).toBe(false)
    expect(result.credential_id).toBe('cred-123')
  })
})

// ---------------------------------------------------------------------------
// deleteCredential
// ---------------------------------------------------------------------------

describe('deleteCredential', () => {
  beforeEach(() => { localStorage.clear(); vi.restoreAllMocks() })
  afterEach(() => { localStorage.clear(); vi.restoreAllMocks() })

  it('throws AuthError on 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    ))
    const { deleteCredential } = await import('../credentials')
    await expect(deleteCredential('cred-123')).rejects.toThrow(AuthError)
  })

  it('sends DELETE to correct URL', async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(null, { status: 204 })
    )
    vi.stubGlobal('fetch', mockFetch)
    const { deleteCredential } = await import('../credentials')
    await deleteCredential('cred-123')
    const [url, init] = mockFetch.mock.calls[0]
    expect(url).toBe('/provider-credentials/cred-123')
    expect(init.method).toBe('DELETE')
  })

  it('resolves void on 204 No Content', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(null, { status: 204 })
    ))
    const { deleteCredential } = await import('../credentials')
    const result = await deleteCredential('cred-123')
    expect(result).toBeUndefined()
  })

  it('throws error on 404', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Credential not found' }), { status: 404 })
    ))
    const { deleteCredential } = await import('../credentials')
    await expect(deleteCredential('nonexistent')).rejects.toThrow('Credential not found')
  })
})

// ---------------------------------------------------------------------------
// Type-level: CredentialMetadata must not expose secrets
// ---------------------------------------------------------------------------

describe('CredentialMetadata type — no secret fields', () => {
  beforeEach(() => { localStorage.clear(); vi.restoreAllMocks() })
  afterEach(() => { localStorage.clear(); vi.restoreAllMocks() })

  it('does not include secret_value or encrypted_secret in the type shape', async () => {
    const payload = { credentials: [MOCK_CREDENTIAL], total: 1 }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 })
    ))
    const { fetchCredentials } = await import('../credentials')
    const result = await fetchCredentials()
    const cred = result.credentials[0]
    // These fields must be absent from the response object
    expect((cred as unknown as Record<string, unknown>).secret_value).toBeUndefined()
    expect((cred as unknown as Record<string, unknown>).encrypted_secret).toBeUndefined()
    expect((cred as unknown as Record<string, unknown>).raw_secret).toBeUndefined()
  })
})
