/**
 * Chart indicator types — Chart-UX-3C.
 *
 * These types mirror the backend chart indicator schemas defined in
 * backend/api/schemas/chart.py.  The frontend renders values exactly as
 * delivered by the backend.  No indicator computation occurs here.
 */

// ---------------------------------------------------------------------------
// GET /chart/indicators — metadata response
// ---------------------------------------------------------------------------

export interface ChartSeriesSpec {
  series_id: string                             // matches output_feature_names entry
  label: string                                 // chart legend label
  pane: 'price_overlay' | 'oscillator_pane'
  render_type: 'line' | 'histogram' | 'area' | 'band_fill'
  default_color: string                         // hex color
}

export interface ChartIndicatorParameterSpec {
  name: string
  description: string
  type_label: 'int' | 'float' | 'str' | string
  required: boolean
  default: number | string | null
  min_value: number | null
  max_value: number | null
}

export interface ChartIndicatorMetadata {
  tool_id: string
  display_name: string
  short_name?: string                           // compact UI label, e.g. "EMA"; falls back to display_name
  description: string
  category: string                              // "Trend", "Momentum", "Volatility", etc.
  chart_pane: 'price_overlay' | 'oscillator_pane'
  render_type: string
  series_kind: 'continuous' | 'event'
  output_series: ChartSeriesSpec[]
  editable_parameters: string[]                 // names of user-editable parameters
  parameters: ChartIndicatorParameterSpec[]
  visible_on_chart: boolean
}

export interface ChartIndicatorsListResponse {
  indicators: ChartIndicatorMetadata[]
}

// ---------------------------------------------------------------------------
// POST /chart/indicator-artifact — request and response
// ---------------------------------------------------------------------------

export interface IndicatorArtifactRequest {
  tool_id: string
  instance_id: string
  symbol: string
  provider: string
  timeframe: string
  date_range_start: string   // ISO 8601 UTC
  date_range_end: string     // ISO 8601 UTC
  parameters: Record<string, number | string>
  asset_class?: string
  exchange?: string
  credential_id?: string
}

/** A single bar's value for one indicator series. null = warmup bar (no output). */
export interface IndicatorSeriesPoint {
  timestamp: string          // ISO 8601 UTC
  value: number | null       // null for warmup bars — NEVER render as zero
}

export interface IndicatorArtifactSeries {
  series_id: string
  label: string
  pane: 'price_overlay' | 'oscillator_pane'
  render_type: 'line' | 'histogram' | 'area' | 'band_fill' | string
  default_color: string
  values: IndicatorSeriesPoint[]
}

export interface IndicatorArtifactResponse {
  tool_id: string
  instance_id: string        // echoed from request — route response to the correct instance
  display_name: string
  pane: 'price_overlay' | 'oscillator_pane'
  render_type: string
  parameters: Record<string, number | string>
  series: IndicatorArtifactSeries[]
  warmup_bars: number        // number of leading null values to expect
  diagnostics: string | null
}

// ---------------------------------------------------------------------------
// Frontend-only indicator instance model
// ---------------------------------------------------------------------------

/**
 * Represents one active indicator instance on the chart.
 * Managed by ChartIndicatorPanel; each instance has a stable instanceId.
 *
 * Chart-UX-3C.1 additions:
 *   instanceLabel  — compact display label, e.g. "SMA (20)", "MACD (12, 26, 9)"
 *   instanceColor  — palette-assigned color for single-series overlays
 *   visible        — when false the instance is hidden without being removed
 *
 * Chart-UX-3C.2 additions:
 *   seriesColors   — user-set per-series color overrides (frontend only, never sent to backend)
 */
export interface IndicatorInstance {
  instanceId: string
  toolId: string
  displayName: string
  instanceLabel: string                         // compact label derived from params
  instanceColor: string                         // palette color (or user-set for single-series)
  seriesColors: Record<string, string>          // series_id → hex, user override per series
  parameters: Record<string, number | string>
  artifact: IndicatorArtifactResponse | null
  visible: boolean
  loading: boolean
  error: string | null
}
