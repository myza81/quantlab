/**
 * Dataset Catalog API client — Phase 3P-E.
 *
 * All requests use authedFetch — Authorization header always injected.
 * file_path appears only in RegisterDatasetRequest (registration-time input);
 * it is never returned in responses and never stored after submission.
 * Backend is the authority for catalog_id-based resource identity.
 */
import { authedFetch } from './client'
import type {
  CatalogEntry,
  CatalogListResponse,
  CatalogOHLCVResponse,
  RegisterDatasetRequest,
  RegisterDatasetResponse,
} from '../types/catalog'

export type {
  CatalogEntry,
  CatalogListResponse,
  CatalogOHLCVResponse,
  RegisterDatasetRequest,
  RegisterDatasetResponse,
}

async function _req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const resp = await authedFetch(path, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body:    body !== undefined ? JSON.stringify(body) : undefined,
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

export function listDatasets(includeDisabled = false): Promise<CatalogListResponse> {
  const q = includeDisabled ? '?include_disabled=true' : ''
  return _req('GET', `/catalog/datasets${q}`)
}

export function registerDataset(req: RegisterDatasetRequest): Promise<RegisterDatasetResponse> {
  return _req('POST', '/catalog/datasets', req)
}

export function removeDataset(catalogId: string): Promise<void> {
  return _req('DELETE', `/catalog/datasets/${catalogId}`)
}

export function fetchCatalogOHLCV(
  catalogId: string,
  start: string,
  end: string,
): Promise<CatalogOHLCVResponse> {
  const q = new URLSearchParams({ start, end })
  return _req('GET', `/catalog/datasets/${catalogId}/ohlcv?${q}`)
}
