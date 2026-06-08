/**
 * Stable frontend visualization contracts for backend-computed tool outputs.
 *
 * These types mirror the backend CompositionIndicatorSeries contract.
 * The frontend renders these values exactly as delivered by the backend.
 * No indicator computation occurs here.
 *
 * Designed to remain extensible for future multi-output indicators:
 *   Bollinger Bands, ATR, VWAP, Ichimoku, volume profile, multi-band indicators.
 */

/** Rendering style for a single tool output series. */
export type ToolOutputKind = 'line' | 'histogram'

/** Chart pane the series belongs to. */
export type ToolOutputPane = 'price' | 'oscillator'

/** A single (timestamp, value) data point. */
export interface ToolOutputPoint {
  timestamp: string   // ISO 8601 string
  value: number
}

/**
 * A named, typed sequence of data points for chart rendering.
 *
 * Backend assigns pane, kind, and price_scale — the frontend routes and renders
 * accordingly.  Multiple series with the same pane are rendered in the same chart
 * pane.  price_scale = "volume" means the series belongs on the dedicated volume
 * axis (bottom of the price pane) and must not distort OHLC price scaling.
 */
export interface ToolVisualizationSeries {
  name:        string
  kind:        ToolOutputKind
  pane:        ToolOutputPane
  price_scale: string          // "default" | "volume"
  color:       string | null
  points:      ToolOutputPoint[]
}
