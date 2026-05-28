/**
 * Market data API client — updated Phase 3P-A.
 *
 * All OHLCV fetches now require active subscription (backend enforces).
 * authedFetch() is always used so the Authorization header is injected and
 * AuthError is thrown on 401/403 (token expiry or entitlement failure → logout/gate).
 */
import { authedFetch } from './client'

export interface OHLCVCandle {
  timestamp: string
  open:      number
  high:      number
  low:       number
  close:     number
  volume:    number
}

// Fetch provenance metadata — mirrors backend DatasetFetchMetadataResponse
export interface DatasetFetchMetadata {
  dataset_id:      string
  fingerprint:     string   // SHA-256 hex of normalized request parameters
  provider:        string
  symbol:          string
  asset_class:     string
  exchange:        string
  timeframe:       string
  start_utc:       string   // ISO-8601 UTC
  end_utc:         string   // ISO-8601 UTC
  adjustment_mode: string
  schema_version:  string
}

export interface MarketDataOHLCVResponse {
  provider:       string
  symbol:         string
  asset_class:    string
  exchange:       string
  timeframe:      string
  start:          string
  end:            string
  candle_count:   number
  candles:        OHLCVCandle[]
  fetch_metadata: DatasetFetchMetadata | null  // always present from Phase 3O backend
}

export interface MarketDataParams {
  provider:         string
  symbol:           string
  asset_class:      string
  exchange:         string
  timeframe:        string
  start:            string
  end:              string
  adjustment_mode?: string
  currency?:        string
  credential_id?:   string  // vault credential_id; when set, authedFetch is used
}

export async function fetchOHLCV(params: MarketDataParams): Promise<MarketDataOHLCVResponse> {
  const query = new URLSearchParams({
    provider:        params.provider,
    symbol:          params.symbol,
    asset_class:     params.asset_class,
    exchange:        params.exchange,
    timeframe:       params.timeframe,
    start:           params.start,
    end:             params.end,
    adjustment_mode: params.adjustment_mode ?? 'adjusted',
    currency:        params.currency ?? 'USD',
  })

  if (params.credential_id) {
    query.set('credential_id', params.credential_id)
  }

  const url = `/market-data/ohlcv?${query}`

  const resp = await authedFetch(url)

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error((err as { detail?: string }).detail ?? `HTTP ${resp.status}`)
  }

  return resp.json() as Promise<MarketDataOHLCVResponse>
}
