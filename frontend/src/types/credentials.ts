/**
 * Provider credential types — Phase 3N.
 *
 * INVARIANTS:
 *   - CredentialMetadata never contains raw secret values or encrypted_secret
 *   - RegisterCredentialRequest.secret_value is write-only (sent to server, never stored)
 *   - These types mirror backend/api/schemas/vault.py exactly
 */

// Metadata returned by all vault API responses — no secrets ever present
export interface CredentialMetadata {
  credential_id: string
  provider_name: string
  credential_label: string
  active: boolean
  created_at: string   // UTC ISO-8601
  updated_at: string   // UTC ISO-8601
  // encrypted_secret intentionally absent — must never appear in frontend types
}

export interface CredentialListResponse {
  credentials: CredentialMetadata[]
  total: number
}

// Write-only request — secret_value must be cleared from state immediately after sending
export interface RegisterCredentialRequest {
  provider_name: string
  credential_label: string
  secret_value: string
}
