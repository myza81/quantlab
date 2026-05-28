/**
 * Typed API client for semantic endpoints.
 *
 * Draft-scoped endpoints (require auth — Phase 3L):
 *   GET  /drafts/{id}/semantics
 *   PUT  /drafts/{id}/semantics
 *   POST /drafts/{id}/semantics/validate
 *
 * Stateless payload endpoints (public — no draft ownership):
 *   POST /semantics/validate
 */
import { authedFetch } from './client'
import type {
  SemanticsResponse,
  SemanticsValidationResponse,
  StrategySemantics,
} from '../types/semantics'

// ---------------------------------------------------------------------------
// Authenticated helper — draft-scoped routes
// ---------------------------------------------------------------------------

async function _authedReq<T>(method: string, path: string, body?: unknown): Promise<T> {
  const resp = await authedFetch(path, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
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
// Public helper — stateless payload routes
// ---------------------------------------------------------------------------

async function _publicReq<T>(method: string, path: string, body?: unknown): Promise<T> {
  const resp = await fetch(path, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
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
// Draft-scoped (authenticated)
// ---------------------------------------------------------------------------

/** GET /drafts/{id}/semantics */
export function getSemantics(draftId: string): Promise<SemanticsResponse> {
  return _authedReq('GET', `/drafts/${draftId}/semantics`)
}

/** PUT /drafts/{id}/semantics — replace and persist */
export function setSemantics(
  draftId: string,
  semantics: StrategySemantics,
): Promise<SemanticsResponse> {
  return _authedReq('PUT', `/drafts/${draftId}/semantics`, { semantics })
}

/** POST /drafts/{id}/semantics/validate — validate stored semantics */
export function validateDraftSemantics(
  draftId: string,
): Promise<SemanticsValidationResponse> {
  return _authedReq('POST', `/drafts/${draftId}/semantics/validate`)
}

// ---------------------------------------------------------------------------
// Stateless payload (public)
// ---------------------------------------------------------------------------

/** POST /semantics/validate — validate payload without persisting */
export function validateSemanticsPayload(
  semantics: StrategySemantics,
): Promise<SemanticsValidationResponse> {
  return _publicReq('POST', '/semantics/validate', { semantics })
}
