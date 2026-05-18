/**
 * Typed API client for all /drafts backend endpoints.
 *
 * No business logic. No validation duplication.
 * Backend is always the source-of-truth — this layer is pure HTTP transport.
 */
import type {
  CompositionValidationResponse,
  DraftListResponse,
  StrategyDraftData,
} from '../types/drafts'

export type { CompositionValidationResponse, DraftListResponse, StrategyDraftData }

// ---------------------------------------------------------------------------
// Request shapes (mirror backend schemas)
// ---------------------------------------------------------------------------

export interface DraftCreateRequest {
  draft_id: string
  display_name: string
  description?: string | null
  toolset: {
    toolset_id: string
    tools: ToolConfigPayload[]
    display_name?: string | null
    enabled?: boolean
  }
  enabled?: boolean
  tags?: string[]
  notes?: string | null
}

export interface DraftUpdateRequest {
  display_name?: string
  description?: string | null
  enabled?: boolean
  tags?: string[]
  notes?: string | null
}

export interface ToolConfigPayload {
  instance_id: string
  tool_id: string
  parameters: Record<string, unknown>
  enabled?: boolean
  display_name?: string | null
  color?: string | null
}

export interface AddToolRequest {
  tool: ToolConfigPayload
  index?: number | null
}

export interface PatchToolRequest {
  parameters?: Record<string, unknown>
  enabled?: boolean
  display_name?: string | null
  color?: string | null
}

export interface ReorderToolsRequest {
  ordered_instance_ids: string[]
}

// ---------------------------------------------------------------------------
// HTTP helper
// ---------------------------------------------------------------------------

async function _req<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const resp = await fetch(path, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  // 204 No Content — void operations (delete, archive)
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
// Draft CRUD
// ---------------------------------------------------------------------------

export function fetchDrafts(): Promise<DraftListResponse> {
  return _req('GET', '/drafts')
}

export function fetchDraft(id: string): Promise<StrategyDraftData> {
  return _req('GET', `/drafts/${id}`)
}

export function createDraft(
  payload: DraftCreateRequest,
): Promise<StrategyDraftData> {
  return _req('POST', '/drafts', payload)
}

export function updateDraft(
  id: string,
  patch: DraftUpdateRequest,
): Promise<StrategyDraftData> {
  return _req('PUT', `/drafts/${id}`, patch)
}

export function deleteDraft(id: string): Promise<void> {
  return _req('DELETE', `/drafts/${id}`)
}

export function archiveDraft(id: string): Promise<void> {
  return _req('POST', `/drafts/${id}/archive`)
}

// ---------------------------------------------------------------------------
// Draft composition
// ---------------------------------------------------------------------------

export function addToolToDraft(
  id: string,
  req: AddToolRequest,
): Promise<StrategyDraftData> {
  return _req('POST', `/drafts/${id}/tools`, req)
}

export function removeToolFromDraft(
  id: string,
  instanceId: string,
): Promise<StrategyDraftData> {
  return _req('DELETE', `/drafts/${id}/tools/${instanceId}`)
}

export function reorderDraftTools(
  id: string,
  req: ReorderToolsRequest,
): Promise<StrategyDraftData> {
  return _req('POST', `/drafts/${id}/tools/reorder`, req)
}

export function patchDraftTool(
  id: string,
  instanceId: string,
  req: PatchToolRequest,
): Promise<StrategyDraftData> {
  return _req('PATCH', `/drafts/${id}/tools/${instanceId}`, req)
}

export function validateDraft(
  id: string,
): Promise<CompositionValidationResponse> {
  return _req('POST', `/drafts/${id}/validate`)
}
