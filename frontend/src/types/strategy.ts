import type { ToolVisualizationSeries } from './toolVisualization'

export type SignalType = 'long' | 'short' | 'exit' | 'reduce'
export type ForecastDirection = 'long' | 'short' | 'neutral'

export interface StrategySignalOverlay {
  timestamp: string
  symbol: string
  timeframe: string
  signal_type: SignalType
  entry_reference: number
  invalidation_level: number
  confidence?: number
  reasoning?: string
}

export interface StrategyForecastOverlay {
  generated_at: string
  target_timestamp: string
  target_price: number
  direction: ForecastDirection
  confidence: number
  invalidation_price?: number
  reason?: string
}

export interface StrategyOverlay {
  signals: StrategySignalOverlay[]
  forecast: StrategyForecastOverlay | null
  indicators: ToolVisualizationSeries[]
}
