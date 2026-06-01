/**
 * Asset search types — mirrors backend AssetSearchResult / AssetSearchResponse schemas.
 *
 * Designed as a platform-wide reusable contract for Chart, Backtesting,
 * Strategy Composer, Forward Testing, and Paper Trading asset pickers.
 */

export interface AssetSearchResult {
  /** Canonical ticker symbol, e.g. "AAPL", "5347.KL", "BTC-USD" */
  symbol:      string
  /** Full company or asset name, e.g. "Apple Inc.", "Tenaga Nasional Berhad" */
  name:        string
  /** Display exchange name, e.g. "NASDAQ", "NYSE", "Kuala Lumpur Stock Exchange" */
  exchange:    string
  /** QuantLab asset class: "equity" | "etf" | "crypto" | "fx" | "future" | "index" | "fund" */
  asset_class: string
  /** ISO 4217 currency code, e.g. "USD", "MYR" */
  currency:    string
  /** Human-readable type label, e.g. "Equity", "ETF", "Cryptocurrency" */
  type_label:  string
}

export interface AssetSearchResponse {
  query:    string
  provider: string
  results:  AssetSearchResult[]
}

/**
 * Discriminated error kind from the asset search API.
 *
 * - unsupported:      provider registered but has no search capability
 * - error:            searcher raised (network, auth, timeout)
 * - unknown_provider: provider name not registered at all
 */
export type SearchErrorKind = 'unsupported' | 'error' | 'unknown_provider'

/** Typed error thrown by searchAssets() on non-200 responses. */
export class AssetSearchError extends Error {
  constructor(
    public readonly kind: SearchErrorKind,
    message: string,
  ) {
    super(message)
    this.name = 'AssetSearchError'
  }
}
