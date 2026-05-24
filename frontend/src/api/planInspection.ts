/**
 * Typed API client for plan inspection endpoints.
 *
 * No business logic. No local inspection. Backend is source-of-truth.
 */
import type { EvaluationReadinessResponse, PlanInspectionResponse } from '../types/planInspection'

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

/** GET /drafts/{id}/semantics/plan */
export function fetchDraftPlanInspection(draftId: string): Promise<PlanInspectionResponse> {
  return _req('GET', `/drafts/${draftId}/semantics/plan`)
}

/** GET /drafts/{id}/semantics/readiness */
export function fetchDraftReadiness(draftId: string): Promise<EvaluationReadinessResponse> {
  return _req('GET', `/drafts/${draftId}/semantics/readiness`)
}
