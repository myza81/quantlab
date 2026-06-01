/**
 * Asset search API client.
 *
 * Calls GET /market-data/search to resolve user queries (ticker symbol or
 * company name) to structured asset metadata. Used by AssetResolverInput
 * to populate exchange, asset_class, and symbol without manual user entry.
 *
 * All calls use authedFetch — active subscription required (backend enforces).
 *
 * Error handling (Chart-UX-2):
 *   Throws AssetSearchError with a discriminated `kind` field so callers can
 *   show provider-specific UX messages without checking status codes.
 */
import { authedFetch } from './client'
import { AssetSearchError } from '../types/assetSearch'
import type { AssetSearchResponse, SearchErrorKind } from '../types/assetSearch'

export type { AssetSearchResult, AssetSearchResponse, SearchErrorKind } from '../types/assetSearch'
export { AssetSearchError } from '../types/assetSearch'

/**
 * Classify a backend error message into a SearchErrorKind.
 * The backend guarantees specific message patterns (see market_data.py docstring).
 */
function classifyError(detail: string): SearchErrorKind {
  if (detail.includes('does not support')) return 'unsupported'
  if (detail.includes('is not registered'))  return 'unknown_provider'
  return 'error'
}

/**
 * Search for assets matching *query* via the backend asset resolver.
 *
 * @param query        Ticker symbol or company name (min 2 chars).
 * @param provider     Data provider to search through (default: "yahoo").
 * @param limit        Maximum results (1–20, default: 10).
 * @param credentialId Optional vault credential_id for credentialed providers
 *                     (e.g. Polygon).  Forwarded as credential_id query param.
 *
 * @throws AssetSearchError with kind='unsupported' when the provider has no
 *         search capability.
 * @throws AssetSearchError with kind='unknown_provider' when the provider is
 *         not registered.
 * @throws AssetSearchError with kind='error' on network or searcher failures.
 */
export async function searchAssets(
  query:         string,
  provider:      string = 'yahoo',
  limit:         number = 10,
  credentialId?: string,
): Promise<AssetSearchResponse> {
  const params = new URLSearchParams({
    q:        query,
    provider,
    limit:    String(limit),
  })
  if (credentialId) {
    params.set('credential_id', credentialId)
  }

  const resp = await authedFetch(`/market-data/search?${params}`)

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }))
    const detail = (body as { detail?: string }).detail ?? `HTTP ${resp.status}`
    throw new AssetSearchError(classifyError(detail), detail)
  }

  return resp.json() as Promise<AssetSearchResponse>
}
