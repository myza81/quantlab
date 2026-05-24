/**
 * Typed API client for semantic endpoints.
 *
 * No business logic. No validation duplication.
 * Backend is always the source-of-truth for semantic structure and validation.
 */
import type {
  SemanticsResponse,
  SemanticsValidationResponse,
  StrategySemantics,
} from '../types/semantics'

async function _req<T>(method: string, path: string, body?: unknown): Promise<T> {
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

/** GET /drafts/{id}/semantics */
export function getSemantics(draftId: string): Promise<SemanticsResponse> {
  return _req('GET', `/drafts/${draftId}/semantics`)
}

/** PUT /drafts/{id}/semantics — replace and persist */
export function setSemantics(
  draftId: string,
  semantics: StrategySemantics,
): Promise<SemanticsResponse> {
  return _req('PUT', `/drafts/${draftId}/semantics`, { semantics })
}

/** POST /drafts/{id}/semantics/validate — validate stored semantics */
export function validateDraftSemantics(
  draftId: string,
): Promise<SemanticsValidationResponse> {
  return _req('POST', `/drafts/${draftId}/semantics/validate`)
}

/** POST /semantics/validate — validate payload without persisting */
export function validateSemanticsPayload(
  semantics: StrategySemantics,
): Promise<SemanticsValidationResponse> {
  return _req('POST', '/semantics/validate', { semantics })
}
