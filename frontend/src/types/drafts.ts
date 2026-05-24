import type { StrategyToolSetData } from './tools'
import type { StrategySemantics } from './semantics'

/**
 * Passive frontend representation of a StrategyDraft.
 *
 * Mirrors the backend StrategyDraft model. Frontend never mutates or validates
 * this structure — that authority belongs entirely to the backend.
 *
 * Validation is always performed server-side via POST /drafts/{id}/validate.
 */
export interface StrategyDraftData {
  draft_id: string
  display_name: string
  description: string | null
  toolset: StrategyToolSetData
  created_at: string   // ISO 8601 UTC datetime string
  updated_at: string   // ISO 8601 UTC datetime string
  enabled: boolean
  tags: string[]
  notes: string | null
  semantics?: StrategySemantics | null
}

/** Response from GET /drafts */
export interface DraftListResponse {
  drafts: StrategyDraftData[]
  count: number
}

/** Response from POST /drafts/{id}/validate */
export interface CompositionValidationResponse {
  valid: boolean
  errors: string[]
}
