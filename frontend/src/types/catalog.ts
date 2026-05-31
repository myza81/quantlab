/**
 * Catalog types — Phase 3P-E.
 *
 * IMPORTANT: file_path does NOT appear in any response type.
 * File path is a registration-time-only input; backend resolves it internally.
 * Frontend durable identity is catalog_id only.
 */

export type CatalogProviderType = 'csv' | 'parquet'
export type CatalogTimeframe    = '1d' | '1w' | '1M' | '1h' | '30m' | '15m' | '5m' | '1m'
export type CatalogAssetClass   = 'equity' | 'etf' | 'crypto' | 'fx' | 'future' | 'index'
export type CatalogAdjustment   = 'adjusted' | 'unadjusted'

// ---------------------------------------------------------------------------
// Request — file_path is accepted for registration only; never echoed back
// ---------------------------------------------------------------------------

export interface RegisterDatasetRequest {
  file_path:       string                // registration-time input; cleared after submit
  display_name:    string
  provider_type:   CatalogProviderType
  symbol:          string
  asset_class:     string
  timeframe:       string
  venue:           string
  dataset_type?:   string                // defaults to "ohlcv" on backend
  adjustment_mode?: CatalogAdjustment
}

// ---------------------------------------------------------------------------
// Responses — no file_path
// ---------------------------------------------------------------------------

export interface CatalogEntry {
  catalog_id:      string
  provider_type:   string
  display_name:    string
  dataset_type:    string
  asset_class:     string
  timeframe:       string
  symbol:          string
  venue:           string
  adjustment_mode: string
  registered_at:   string
  enabled:         boolean
  metadata?:       Record<string, unknown> | null
}

export interface CatalogListResponse {
  entries: CatalogEntry[]
  count:   number
}

export interface RegisterDatasetResponse {
  catalog_id:    string
  display_name:  string
  provider_type: string
  symbol:        string
  asset_class:   string
  venue:         string
  timeframe:     string
}

export interface CatalogOHLCVCandle {
  timestamp: string
  open:      number
  high:      number
  low:       number
  close:     number
  volume:    number
}

export interface CatalogOHLCVResponse {
  catalog_id:    string
  provider_type: string
  symbol:        string
  asset_class:   string
  venue:         string
  timeframe:     string
  candle_count:  number
  candles:       CatalogOHLCVCandle[]
}
