export interface OHLCVCandle {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface MarketDataOHLCVResponse {
  provider: string
  symbol: string
  asset_class: string
  exchange: string
  timeframe: string
  start: string
  end: string
  candle_count: number
  candles: OHLCVCandle[]
}

export interface MarketDataParams {
  provider: string
  symbol: string
  asset_class: string
  exchange: string
  timeframe: string
  start: string
  end: string
  adjustment_mode?: string
  currency?: string
}

export async function fetchOHLCV(params: MarketDataParams): Promise<MarketDataOHLCVResponse> {
  const query = new URLSearchParams({
    provider: params.provider,
    symbol: params.symbol,
    asset_class: params.asset_class,
    exchange: params.exchange,
    timeframe: params.timeframe,
    start: params.start,
    end: params.end,
    adjustment_mode: params.adjustment_mode ?? 'adjusted',
    currency: params.currency ?? 'USD',
  })

  const resp = await fetch(`/market-data/ohlcv?${query}`)

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail ?? `HTTP ${resp.status}`)
  }

  return resp.json() as Promise<MarketDataOHLCVResponse>
}
