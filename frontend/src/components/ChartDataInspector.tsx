/**
 * ChartDataInspector — CHART-UX-4A.3.
 *
 * TradingView-style OHLC header displayed at the top of the price chart.
 * Shows symbol · timeframe · exchange · O H L C · change% for the hovered candle.
 *
 * Design decisions (CHART-UX-4A.3 — Simplify Chart Header):
 *  - Indicator rows removed: values already shown in chart overlays/legends.
 *    Showing them here was duplication and visual noise.
 *  - Volume removed from header: creates clutter; OHLC + change% is sufficient
 *    for candle-to-candle inspection. fmtVolume kept for future use.
 *  - Indicator props retained in interface for future re-enablement without
 *    breaking caller sites.
 *  - No date/time (already shown on the time-axis crosshair).
 *  - Compact, single dark-theme bar — does not obscure the chart.
 */

import type { IndicatorArtifactResponse } from '../types/chartIndicators'
import type { ChartTheme } from '../types/chartTheme'

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/** Candle data the inspector renders for the current crosshair position. */
export interface InspectorCandle {
  open:   number
  high:   number
  low:    number
  close:  number
  volume: number
  /** change = close - prevClose; undefined when no previous candle exists */
  change?:    number
  /** changePct = change / prevClose * 100; undefined when unavailable */
  changePct?: number
}

/**
 * Pre-indexed indicator values for the current crosshair timestamp.
 * Maps instance_id → series_id → value (null for warmup / no-data).
 * Retained for future re-enablement of indicator rows.
 */
export type InspectorIndicatorValues = Map<string, Map<string, number | null>>

interface ChartDataInspectorProps {
  symbol:    string
  timeframe: string
  exchange?: string
  /** Candle at current crosshair position (latest candle when no hover) */
  candle: InspectorCandle | null
  theme?: ChartTheme
  // Indicator props below are accepted but not currently rendered.
  // They are retained so caller sites do not need to change and the
  // plumbing is available for future re-enablement.
  indicatorArtifacts?: IndicatorArtifactResponse[]
  instanceLabels?:     Map<string, string>
  instanceColors?:     Map<string, string>
  instanceVisible?:    Map<string, boolean>
  indicatorValues?:    InspectorIndicatorValues
  /** 1-based candle index for the current crosshair position */
  candleNumber?: number
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function fmtPrice(v: number): string {
  return v.toFixed(2)
}

/** Format volume compactly: 1 234 567 → "1.23M", 12 345 → "12.35K" */
export function fmtVolume(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000)     return `${(v / 1_000).toFixed(2)}K`
  return String(Math.round(v))
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ChartDataInspector({
  symbol, timeframe, exchange, candle, theme, candleNumber,
}: ChartDataInspectorProps) {
  const tc = theme?.colors

  if (!candle) {
    return (
      <div data-testid="chart-data-inspector" style={{
        ...s.bar,
        background:   tc?.ohlcBarBg     ?? s.bar.background as string,
        borderBottom: `1px solid ${tc?.ohlcBarBorder ?? '#1a1a2e'}`,
      }}>
        <span style={{ ...s.meta, color: tc?.metaText ?? s.meta.color as string }}>
          {symbol}{timeframe ? ` · ${timeframe}` : ''}{exchange ? ` · ${exchange}` : ''}
        </span>
      </div>
    )
  }

  const { open, high, low, close, change, changePct } = candle

  // Single movement color applied to all OHLC tokens and the change string.
  const movementColor: string =
    change === undefined || change === null ? '#8892a4'
    : change >= 0 ? '#26a69a'
    : '#ef5350'

  const changeStr = (change !== undefined && change !== null && changePct !== undefined && changePct !== null)
    ? `${change >= 0 ? '+' : ''}${change.toFixed(2)} (${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%)`
    : undefined

  return (
    <div data-testid="chart-data-inspector" style={{
      ...s.bar,
      background:   tc?.ohlcBarBg     ?? s.bar.background as string,
      borderBottom: `1px solid ${tc?.ohlcBarBorder ?? '#1a1a2e'}`,
    }}>
      {/* ── OHLC header: symbol · timeframe · exchange · O H L C · change ── */}
      <div style={s.primaryRow}>
        <span data-testid="inspector-meta" style={{ ...s.meta, color: tc?.metaText ?? s.meta.color as string }}>
          {symbol}{timeframe ? ` · ${timeframe}` : ''}{exchange ? ` · ${exchange}` : ''}
        </span>
        <span style={s.gap} />
        <span data-testid="inspector-open"   style={{ ...s.ohlcToken, color: movementColor }}>O {fmtPrice(open)}</span>
        <span data-testid="inspector-high"   style={{ ...s.ohlcToken, color: movementColor }}>H {fmtPrice(high)}</span>
        <span data-testid="inspector-low"    style={{ ...s.ohlcToken, color: movementColor }}>L {fmtPrice(low)}</span>
        <span data-testid="inspector-close"  style={{ ...s.ohlcToken, color: movementColor }}>C {fmtPrice(close)}</span>
        {changeStr !== undefined && (
          <span data-testid="inspector-change" style={{ ...s.changeVal, color: movementColor }}>
            {changeStr}
          </span>
        )}
        {candleNumber !== undefined && (
          <span data-testid="inspector-candle-number" style={s.candleNumber}>
            #{candleNumber}
          </span>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const s: Record<string, React.CSSProperties> = {
  bar: {
    display:        'flex',
    flexDirection:  'column',
    padding:        '3px 10px',
    background:     'rgba(10, 10, 20, 0.85)',
    borderBottom:   '1px solid #1a1a2e',
    flex:           1,
    minWidth:       0,
    userSelect:     'none',
    pointerEvents:  'none',
  },
  primaryRow: {
    display:     'flex',
    alignItems:  'center',
    gap:         5,
    flexWrap:    'nowrap',
    overflow:    'hidden',
    fontFamily:  'monospace',
    fontSize:    11,
    lineHeight:  '16px',
    whiteSpace:  'nowrap',
  },
  meta: {
    color:         '#7a8499',
    fontSize:      11,
    fontFamily:    'monospace',
    letterSpacing: '0.03em',
    flexShrink:    0,
  },
  gap: { flexShrink: 0, width: 6 },
  ohlcToken: {
    fontSize:   11,
    fontFamily: 'monospace',
    flexShrink: 0,
    marginLeft: 3,
  },
  changeVal: {
    fontSize:   11,
    fontFamily: 'monospace',
    marginLeft: 6,
    flexShrink: 0,
  },
  candleNumber: {
    fontSize:   11,
    fontFamily: 'monospace',
    marginLeft: 8,
    flexShrink: 0,
    color:      '#4a5070',
  },
}
