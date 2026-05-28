/**
 * Typed API client for /provider-credentials vault endpoints — Phase 3N.
 *
 * All requests use authedFetch — no plain fetch calls.
 * No raw secret values are ever returned from these endpoints (backend invariant).
 * Backend is always the source-of-truth; this layer is pure HTTP transport.
 */
import { authedFetch } from './client'
import type {
  CredentialListResponse,
  CredentialMetadata,
  RegisterCredentialRequest,
} from '../types/credentials'

export type { CredentialListResponse, CredentialMetadata, RegisterCredentialRequest }

// ---------------------------------------------------------------------------
// HTTP helper — all vault endpoints require authentication
// ---------------------------------------------------------------------------

async function _req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const resp = await authedFetch(path, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (resp.status === 204) return undefined as unknown as T

  const data = await resp.json().catch(() => ({ detail: resp.statusText }))

  if (!resp.ok) {
    const detail = (data as { detail?: unknown }).detail
    const msg =
      typeof detail === 'string'
        ? detail
        : JSON.stringify(detail ?? `HTTP ${resp.status}`)
    throw new Error(msg)
  }

  return data as T
}

// ---------------------------------------------------------------------------
// Vault API calls
// ---------------------------------------------------------------------------

export function fetchCredentials(): Promise<CredentialListResponse> {
  return _req('GET', '/provider-credentials')
}

export function registerCredential(
  req: RegisterCredentialRequest,
): Promise<CredentialMetadata> {
  return _req('POST', '/provider-credentials', req)
}

export function disableCredential(credentialId: string): Promise<CredentialMetadata> {
  return _req('PATCH', `/provider-credentials/${credentialId}/disable`)
}

export function deleteCredential(credentialId: string): Promise<void> {
  return _req('DELETE', `/provider-credentials/${credentialId}`)
}
