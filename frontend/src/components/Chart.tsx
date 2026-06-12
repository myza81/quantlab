/**
 * Chart.tsx — Chart-UX-3C.5 (Chart Object Experience).
 *
 * New features:
 *  - On-chart indicator legends: ChartLegendOverlay positioned over price pane,
 *    shows label + live crosshair value per instance + toggle/remove actions.
 *  - Live crosshair values: subscribeCrosshairMove on price chart; param.seriesData
 *    used to read current values without any extra lookup map.
 *  - OscPane headers: compact header bar per artifact instance (color chip · label ·
 *    live value · toggle · remove). Replaces the tiny corner label.
 *  - OscPane crosshair values: propagated via onCrosshairValues callback so the
 *    pane header can show live values when user hovers the price chart.
 *  - Active pane feedback: isHovered state on OscPane → left border highlight.
 *  - Splitter improvements: hover state, active-drag visual, wider hit target,
 *    double-click resets pane to DEFAULT_OSC_HEIGHT.
 *  - Pane height persistence: localStorage key "ql_pane_heights"; loaded on first
 *    render, saved on every committed height change.
 *  - Indicator ownership feedback: highlightedInstanceId prop → outline on matching
 *    legend rows; onHoverInstance callback lets parent highlight sidebar items.
 *  - Chart interaction defaults: rightOffset=5, barSpacing=8, kinetic scroll.
 *
 * All Chart-UX-3C.3A–3C.4 correctness preserved (logical range sync, whitespace
 * timestamp alignment, one-directional sync, pointer-capture drag).
 */
import { useEffect, useRef, useState, useMemo, forwardRef, useImperativeHandle } from 'react'
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  LineStyle,
  createSeriesMarkers,
} from 'lightweight-charts'
import type {
  IChartApi,
  IPriceLine,
  ISeriesApi,
  ISeriesMarkersPluginApi,
  CandlestickData,
  Time,
  UTCTimestamp,
  SeriesMarker,
  LogicalRange,
  MouseEventParams,
  LineData,
  HistogramData,
  WhitespaceData,
} from 'lightweight-charts'
import type { OHLCVCandle } from '../api/marketData'
import type { ToolVisualizationSeries } from '../types/toolVisualization'
import type { StrategyOverlay } from '../types/strategy'
import type { IndicatorArtifactResponse, IndicatorSeriesPoint } from '../types/chartIndicators'
import { ChartLegendOverlay } from './ChartLegendOverlay'
import ChartDataInspector, { type InspectorCandle, type InspectorIndicatorValues } from './ChartDataInspector'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ChartProps {
  candles:               OHLCVCandle[]
  symbol:                string
  timeframe:             string
  exchange?:             string
  overlay?:              StrategyOverlay | null
  indicatorArtifacts?:   IndicatorArtifactResponse[]
  instanceColors?:       Map<string, string>
  /** Compact per-instance labels, e.g. "SMA (20)" */
  instanceLabels?:       Map<string, string>
  /** Per-instance visibility state */
  instanceVisible?:      Map<string, boolean>
  /** Which instance is highlighted (from sidebar hover) */
  highlightedInstanceId?: string | null
  onClearStrategyResults?: () => void
  onHoverInstance?:      (instanceId: string | null) => void
  onIndicatorToggle?:    (instanceId: string) => void
  onIndicatorRemove?:    (instanceId: string) => void
  /** Per-instance volume color mode: present with a hex color → single-color mode for that instance */
  volumeColorModes?:     Map<string, string>
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const _DEFAULT_COLORS    = ['#2196f3', '#ff9800', '#9c27b0', '#00bcd4', '#4caf50']

function toLineStyle(style?: string): LineStyle {
  if (style === 'dashed') return LineStyle.Dashed
  if (style === 'dotted') return LineStyle.Dotted
  return LineStyle.Solid
}
const MIN_OSC_HEIGHT     = 100
const MAX_OSC_HEIGHT     = 600
const DEFAULT_OSC_HEIGHT = 130
const STORAGE_KEY        = 'ql_pane_heights'

// Volume histogram directional colors — close-to-close comparison (TradingView convention)
const VOLUME_UP_COLOR   = '#26a69a'
const VOLUME_DOWN_COLOR = '#ef5350'

// ---------------------------------------------------------------------------
// Pane height persistence
// ---------------------------------------------------------------------------

function loadPersistedHeights(): Record<string, number> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Record<string, number>) : {}
  } catch { return {} }
}

function savePersistedHeights(heights: Record<string, number>) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(heights)) } catch { /* ignore */ }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function toUTCTimestamp(isoString: string): UTCTimestamp {
  return Math.floor(new Date(isoString).getTime() / 1000) as UTCTimestamp
}

function normalizeChartData<T extends { time: UTCTimestamp }>(data: readonly T[]): T[] {
  const map = new Map<number, T>()
  for (const d of data) map.set(d.time as number, d)
  return [...map.values()].sort((a, b) => (a.time as number) - (b.time as number))
}

function buildAlignedLineData(
  values: IndicatorSeriesPoint[],
  candleTimestamps: UTCTimestamp[],
): Array<LineData<Time> | WhitespaceData<Time>> {
  const byTs = new Map<number, number | null>()
  for (const v of values) {
    if (v.timestamp) byTs.set(toUTCTimestamp(v.timestamp), v.value)
  }
  return candleTimestamps.map(ts => {
    const val = byTs.get(ts)
    return (val !== null && val !== undefined)
      ? ({ time: ts as Time, value: val } as LineData<Time>)
      : ({ time: ts as Time } as WhitespaceData<Time>)
  })
}

function buildAlignedHistData(
  values: IndicatorSeriesPoint[],
  candleTimestamps: UTCTimestamp[],
): Array<HistogramData<Time> | WhitespaceData<Time>> {
  const byTs = new Map<number, number | null>()
  for (const v of values) {
    if (v.timestamp) byTs.set(toUTCTimestamp(v.timestamp), v.value)
  }
  return candleTimestamps.map(ts => {
    const val = byTs.get(ts)
    return (val !== null && val !== undefined)
      ? ({ time: ts as Time, value: val, color: val >= 0 ? '#26a69a' : '#ef5350' } as HistogramData<Time>)
      : ({ time: ts as Time } as WhitespaceData<Time>)
  })
}

/**
 * Build a timestamp → hex-color map for volume histogram bars using
 * close-to-close directional coloring (TradingView convention):
 *   close[i] >= close[i-1]  →  VOLUME_UP_COLOR   (green)
 *   close[i] <  close[i-1]  →  VOLUME_DOWN_COLOR  (red)
 *   first bar (no previous)  →  VOLUME_UP_COLOR   (neutral/green)
 */
function buildVolumeColorMap(candles: OHLCVCandle[]): Map<UTCTimestamp, string> {
  const sorted = [...candles].sort((a, b) => toUTCTimestamp(a.timestamp) - toUTCTimestamp(b.timestamp))
  const map    = new Map<UTCTimestamp, string>()
  for (let i = 0; i < sorted.length; i++) {
    const ts    = toUTCTimestamp(sorted[i].timestamp)
    const color = i === 0 || sorted[i].close >= sorted[i - 1].close
      ? VOLUME_UP_COLOR
      : VOLUME_DOWN_COLOR
    map.set(ts, color)
  }
  return map
}

function resyncRange(oscChart: IChartApi, priceChart: IChartApi | null) {
  if (!priceChart) return
  const range = priceChart.timeScale().getVisibleLogicalRange()
  if (range) try { oscChart.timeScale().setVisibleLogicalRange(range) } catch { /* not ready */ }
}

// ---------------------------------------------------------------------------
// Chart theme
// ---------------------------------------------------------------------------

const _CHART_THEME = {
  layout: {
    background: { color: '#0f0f1a' },
    textColor:  '#d1d4dc',
  },
  grid: {
    vertLines: { color: '#1a1a2e' },
    horzLines: { color: '#1a1a2e' },
  },
  crosshair: { mode: 0 },
  rightPriceScale: { borderColor: '#2a2d3e' },
  timeScale: {
    borderColor:     '#2a2d3e',
    timeVisible:     true,
    secondsVisible:  false,
    rightOffset:     5,
    barSpacing:      8,
  },
}

type AnySeriesApi = ISeriesApi<'Line'> | ISeriesApi<'Histogram'>
type ReferenceGuideBinding = { series: ISeriesApi<'Line'>; lines: IPriceLine[] }
type OscillatorReferenceGuide = {
  id: string
  matches: (s: ToolVisualizationSeries) => boolean
  levels: { value: number; label: string; color: string }[]
}

const _OSCILLATOR_REFERENCE_GUIDES: OscillatorReferenceGuide[] = [
  {
    id: 'rsi',
    matches: ind => {
      const n = ind.name.toLowerCase()
      return ind.pane === 'oscillator' && ind.kind !== 'histogram' && /\brsi\b|\.rsi\b|rsi_/i.test(n)
    },
    levels: [
      { value: 70, label: 'RSI 70', color: 'rgba(239, 83, 80, 0.45)' },
      { value: 50, label: 'RSI 50', color: 'rgba(136, 146, 164, 0.28)' },
      { value: 30, label: 'RSI 30', color: 'rgba(38, 166, 154, 0.45)' },
    ],
  },
]

// ---------------------------------------------------------------------------
// OscPaneHandle
// ---------------------------------------------------------------------------

export interface OscPaneHandle {
  readonly el:    HTMLDivElement | null
  readonly chart: IChartApi | null
}

// ---------------------------------------------------------------------------
// DragSplitter (pointer events + rAF + hover/active/double-click)
// ---------------------------------------------------------------------------

interface DragSplitterProps {
  onCommitHeight:     (height: number) => void
  getCommittedHeight: () => number
  oscHandle:          OscPaneHandle | null
  priceChartRef:      React.RefObject<IChartApi | null>
  onReset:            () => void
  minHeight?:         number
  maxHeight?:         number
}

function DragSplitter({
  onCommitHeight, getCommittedHeight, oscHandle, priceChartRef, onReset,
  minHeight = MIN_OSC_HEIGHT, maxHeight = MAX_OSC_HEIGHT,
}: DragSplitterProps) {
  const rafRef    = useRef<number | null>(null)
  const dragRef   = useRef<{ startY: number; startH: number; liveH: number } | null>(null)
  const [isHovered,  setIsHovered]  = useState(false)
  const [isDragging, setIsDragging] = useState(false)

  useEffect(() => () => {
    if (rafRef.current !== null) { cancelAnimationFrame(rafRef.current); rafRef.current = null }
  }, [])

  const scheduleApply = (h: number) => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null
      const { el, chart } = oscHandle ?? {}
      if (el)    el.style.height = `${h}px`
      if (chart) { chart.applyOptions({ height: h }); resyncRange(chart, priceChartRef.current) }
    })
  }

  const applyFinal = (h: number) => {
    if (rafRef.current !== null) { cancelAnimationFrame(rafRef.current); rafRef.current = null }
    const { el, chart } = oscHandle ?? {}
    if (el)    el.style.height = `${h}px`
    if (chart) { chart.applyOptions({ height: h }); resyncRange(chart, priceChartRef.current) }
  }

  const handlePointerDown = (e: React.PointerEvent) => {
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    const startH = getCommittedHeight()
    dragRef.current = { startY: e.clientY, startH, liveH: startH }
    setIsDragging(true)
  }

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!dragRef.current) return
    const delta = dragRef.current.startY - e.clientY
    const newH  = Math.min(maxHeight, Math.max(minHeight, dragRef.current.startH + delta))
    dragRef.current.liveH = newH
    scheduleApply(newH)
  }

  const handlePointerEnd = () => {
    if (!dragRef.current) return
    const finalH = dragRef.current.liveH
    dragRef.current = null
    setIsDragging(false)
    applyFinal(finalH)
    onCommitHeight(finalH)
  }

  const handleDoubleClick = () => {
    applyFinal(DEFAULT_OSC_HEIGHT)
    onReset()
  }

  const lineColor = isDragging ? '#5a7ec0'
    : isHovered ? '#3a4a7e'
    : '#1e1e30'

  return (
    // Wider hit target via vertical padding; actual visible line is 1px inside
    <div
      data-testid="pane-splitter"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerEnd}
      onPointerCancel={handlePointerEnd}
      onDoubleClick={handleDoubleClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={splitterOuterStyle}
    >
      <div data-testid="pane-splitter-line" style={{ ...splitterLineStyle, background: lineColor }} />
    </div>
  )
}

const splitterOuterStyle: React.CSSProperties = {
  cursor:      'row-resize',
  background:  '#0f0f1a',
  flexShrink:  0,
  padding:     '4px 0',      // wider invisible hit target
  touchAction: 'none',
  userSelect:  'none',
}
const splitterLineStyle: React.CSSProperties = {
  height:     1,
  transition: 'background 0.1s',
}

// ---------------------------------------------------------------------------
// OscPane (forwardRef, with compact header)
// ---------------------------------------------------------------------------

interface OscPaneProps {
  label:             string
  artifacts:         IndicatorArtifactResponse[]
  instanceColors?:   Map<string, string>
  instanceLabels?:   Map<string, string>
  instanceVisible?:  Map<string, boolean>
  candleTimestamps:  UTCTimestamp[]
  priceChart:        IChartApi | null
  height?:           number
  highlightedId?:    string | null
  /** Crosshair values from this pane: instance_id → series_id → value */
  onCrosshairValues?: (vals: Map<string, Map<string, number | null>>) => void
  onToggle?:         (instanceId: string) => void
  onRemove?:         (instanceId: string) => void
}

const OscPane = forwardRef<OscPaneHandle, OscPaneProps>(function OscPane(
  {
    label, artifacts, instanceColors, instanceLabels, instanceVisible,
    candleTimestamps, priceChart, height = DEFAULT_OSC_HEIGHT,
    highlightedId, onCrosshairValues, onToggle, onRemove,
  },
  ref,
) {
  const wrapperRef      = useRef<HTMLDivElement>(null)
  const containerRef    = useRef<HTMLDivElement>(null)
  const chartRef        = useRef<IChartApi | null>(null)
  const seriesMapRef    = useRef<Map<string, AnySeriesApi>>(new Map())
  const timeValueMapRef = useRef<Map<number, number>>(new Map())  // first-series values
  const isSyncingRef    = useRef(false)
  // Full value lookup for all series — instance_id → series_id → ts → value
  const allValuesRef    = useRef<Map<string, Map<string, Map<number, number>>>>(new Map())
  const [isHovered, setIsHovered] = useState(false)
  const [oscCrosshairVals, setOscCrosshairVals] =
    useState<Map<string, Map<string, number | null>>>(new Map())

  useImperativeHandle(ref, () => ({
    get el()    { return wrapperRef.current },
    get chart() { return chartRef.current },
  }), [])

  // Create chart on mount
  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, { ..._CHART_THEME, height })
    chartRef.current = chart

    const ro = new ResizeObserver(entries => {
      for (const e of entries) chart.applyOptions({ width: e.contentRect.width, height: e.contentRect.height })
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      seriesMapRef.current.clear()
      chart.remove()
      chartRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // One-directional logical range sync + crosshair sync + live value reporting
  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !priceChart) return

    const syncFromPrice = (range: LogicalRange | null) => {
      if (isSyncingRef.current || !range || seriesMapRef.current.size === 0) return
      isSyncingRef.current = true
      try { chart.timeScale().setVisibleLogicalRange(range) } catch { /* not ready */ }
      isSyncingRef.current = false
    }

    const syncCrosshair = (param: MouseEventParams | null) => {
      if (!param || !param.time || seriesMapRef.current.size === 0) {
        try { chart.clearCrosshairPosition() } catch { /* ignore */ }
        // Clear displayed values
        setOscCrosshairVals(new Map())
        onCrosshairValues?.(new Map())
        return
      }
      const ts = param.time as number

      // Position crosshair on oscillator chart
      const firstSeries = [...seriesMapRef.current.values()][0]
      if (firstSeries) {
        const val = timeValueMapRef.current.get(ts)
        if (val !== undefined) {
          try { chart.setCrosshairPosition(val, param.time, firstSeries) } catch { /* out of range */ }
        }
      }

      // Build live values for all instances in this pane
      const vals = new Map<string, Map<string, number | null>>()
      for (const [instId, seriesValMap] of allValuesRef.current) {
        const svMap = new Map<string, number | null>()
        for (const [seriesId, tsMap] of seriesValMap) {
          svMap.set(seriesId, tsMap.get(ts) ?? null)
        }
        vals.set(instId, svMap)
      }
      setOscCrosshairVals(vals)
      onCrosshairValues?.(vals)
    }

    priceChart.timeScale().subscribeVisibleLogicalRangeChange(syncFromPrice)
    priceChart.subscribeCrosshairMove(syncCrosshair)

    return () => {
      priceChart.timeScale().unsubscribeVisibleLogicalRangeChange(syncFromPrice)
      priceChart.unsubscribeCrosshairMove(syncCrosshair)
    }
  }, [priceChart]) // eslint-disable-line react-hooks/exhaustive-deps

  // Rebuild series data on artifacts/colors/timestamps change
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    for (const s of seriesMapRef.current.values()) {
      try { chart.removeSeries(s) } catch { /* gone */ }
    }
    seriesMapRef.current.clear()
    timeValueMapRef.current.clear()
    allValuesRef.current.clear()

    for (const artifact of artifacts) {
      const oscSeries      = artifact.series.filter(s => s.pane === 'oscillator_pane')
      const isSingleSeries = oscSeries.length === 1
      const instanceColor  = instanceColors?.get(artifact.instance_id)
      let firstPopulated   = false

      const instSeriesVals = new Map<string, Map<number, number>>()

      for (const series of oscSeries) {
        const key = `${artifact.instance_id}.${series.series_id}`

        if (series.render_type === 'histogram') {
          const data = buildAlignedHistData(series.values, candleTimestamps)
          if (data.every(d => !('value' in d))) continue
          const s = chart.addSeries(HistogramSeries, {
            priceLineVisible: false, lastValueVisible: true, title: series.label,
          })
          s.setData(data)
          seriesMapRef.current.set(key, s)
        } else {
          const color = (isSingleSeries && instanceColor) ? instanceColor : series.default_color
          const data  = buildAlignedLineData(series.values, candleTimestamps)
          if (data.every(d => !('value' in d))) continue
          const s = chart.addSeries(LineSeries, {
            color, lineWidth: 1, crosshairMarkerVisible: false,
            lastValueVisible: true, priceLineVisible: false, title: series.label,
            lineStyle: toLineStyle(series.line_style),
          })
          s.setData(data)
          seriesMapRef.current.set(key, s)

          // Build crosshair value lookup
          const tsValMap = new Map<number, number>()
          for (const p of data) {
            if ('value' in p && p.value !== undefined) tsValMap.set(p.time as number, p.value)
          }
          instSeriesVals.set(series.series_id, tsValMap)

          if (!firstPopulated) {
            timeValueMapRef.current = tsValMap
            firstPopulated = true
          }
        }
      }
      if (instSeriesVals.size > 0) {
        allValuesRef.current.set(artifact.instance_id, instSeriesVals)
      }
    }

    if (seriesMapRef.current.size > 0) {
      const priceRange = priceChart?.timeScale().getVisibleLogicalRange()
      if (priceRange) {
        try { chart.timeScale().setVisibleLogicalRange(priceRange) } catch { chart.timeScale().fitContent() }
      } else {
        chart.timeScale().fitContent()
      }
    }
  }, [artifacts, instanceColors, candleTimestamps, priceChart])

  const borderColor = isHovered ? '#2a3a6e' : 'transparent'

  return (
    <div
      ref={wrapperRef}
      data-testid="osc-pane-wrapper"
      style={{ ...oscPaneWrapperStyle, height, borderLeft: `2px solid ${borderColor}` }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Compact header replacing the old corner label */}
      <div style={oscPaneHeaderStyle}>
        <span style={oscPaneTitleStyle}>{label}</span>
        {artifacts.map(artifact => {
          const iColor   = instanceColors?.get(artifact.instance_id)
          const iLabel   = instanceLabels?.get(artifact.instance_id) ?? artifact.display_name
          const visible  = instanceVisible?.get(artifact.instance_id) ?? true
          const cvMap    = oscCrosshairVals.get(artifact.instance_id)
          const firstSeries = artifact.series.find(s => s.pane === 'oscillator_pane')
          const firstVal    = firstSeries ? (cvMap?.get(firstSeries.series_id) ?? null) : null
          const displayColor = iColor ?? firstSeries?.default_color ?? '#888'
          const isHigh   = highlightedId === artifact.instance_id

          return (
            <span
              key={artifact.instance_id}
              data-testid={`osc-instance-${artifact.instance_id}`}
              style={{
                ...oscInstanceChipStyle,
                outline: isHigh ? '1px solid #3a4570' : 'none',
                opacity: visible ? 1 : 0.4,
              }}
            >
              <span style={{ ...chipDotStyle, background: displayColor }} />
              <span style={chipLabelStyle}>{iLabel}</span>
              {firstVal !== null && (
                <span
                  data-testid={`osc-value-${artifact.instance_id}`}
                  style={{ ...chipValueStyle, color: displayColor }}
                >
                  {firstVal.toFixed(2)}
                </span>
              )}
              <button
                type="button"
                data-testid={`osc-toggle-${artifact.instance_id}`}
                style={oscActionBtnStyle}
                onClick={() => onToggle?.(artifact.instance_id)}
                title={visible ? 'Hide' : 'Show'}
              >
                {visible ? '◉' : '○'}
              </button>
              <button
                type="button"
                data-testid={`osc-remove-${artifact.instance_id}`}
                style={oscActionBtnStyle}
                onClick={() => onRemove?.(artifact.instance_id)}
                title="Remove"
              >
                ×
              </button>
            </span>
          )
        })}
      </div>
      <div ref={containerRef} style={oscPaneChartStyle} />
    </div>
  )
})

const oscPaneWrapperStyle: React.CSSProperties = {
  flexShrink:  0,
  position:    'relative',
  background:  '#0f0f1a',
  transition:  'border-color 0.1s',
}
const oscPaneHeaderStyle: React.CSSProperties = {
  display:     'flex',
  alignItems:  'center',
  gap:         4,
  padding:     '2px 6px',
  background:  'rgba(10,10,20,0.6)',
  flexWrap:    'wrap',
}
const oscPaneTitleStyle: React.CSSProperties = {
  fontSize:      9,
  color:         '#3a4055',
  fontFamily:    'monospace',
  letterSpacing: '0.07em',
  textTransform: 'uppercase',
  marginRight:   4,
}
const oscInstanceChipStyle: React.CSSProperties = {
  display:      'flex',
  alignItems:   'center',
  gap:          3,
  borderRadius: 2,
  padding:      '0 2px',
}
const chipDotStyle: React.CSSProperties = {
  width:        6,
  height:       6,
  borderRadius: '50%',
  flexShrink:   0,
}
const chipLabelStyle: React.CSSProperties = {
  fontSize:   9,
  fontFamily: 'monospace',
  color:      '#c4cde0',
}
const chipValueStyle: React.CSSProperties = {
  fontSize:   9,
  fontFamily: 'monospace',
  minWidth:   32,
}
const oscActionBtnStyle: React.CSSProperties = {
  background: 'transparent',
  border:     'none',
  color:      '#4a5070',
  cursor:     'pointer',
  fontSize:   9,
  padding:    '0 1px',
  lineHeight: 1,
}
const oscPaneChartStyle: React.CSSProperties = {
  width:  '100%',
  height: `calc(100% - 22px)`,  // subtract header height
}

// ---------------------------------------------------------------------------
// Main Chart component
// ---------------------------------------------------------------------------

export default function Chart({
  candles, symbol, timeframe, exchange, overlay,
  indicatorArtifacts, instanceColors, instanceLabels, instanceVisible,
  highlightedInstanceId, onClearStrategyResults,
  onHoverInstance, onIndicatorToggle, onIndicatorRemove,
  volumeColorModes,
}: ChartProps) {
  const priceContainerRef         = useRef<HTMLDivElement>(null)
  const chartRef                  = useRef<IChartApi | null>(null)
  const candleSeriesRef           = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const markerApiRef              = useRef<ISeriesMarkersPluginApi<Time> | null>(null)
  const forecastSeriesRef         = useRef<ISeriesApi<'Line'> | null>(null)
  const priceSeriesMapRef         = useRef<Map<string, AnySeriesApi>>(new Map())
  const artifactPriceSeriesMapRef = useRef<Map<string, AnySeriesApi>>(new Map())

  const [priceChartApi, setPriceChartApi] = useState<IChartApi | null>(null)

  const oscContainerRef = useRef<HTMLDivElement>(null)
  const oscChartRef     = useRef<IChartApi | null>(null)
  const oscSeriesMapRef = useRef<Map<string, AnySeriesApi>>(new Map())
  const oscTimeValueMapRef = useRef<Map<number, number>>(new Map())
  const oscGuideMapRef  = useRef<Map<string, ReferenceGuideBinding>>(new Map())
  const oscSyncingRef   = useRef(false)

  const [showOscillator, setShowOscillator] = useState(false)

  // Committed pane heights (loaded from localStorage on first render)
  const [oscPaneHeights, setOscPaneHeights] = useState<Record<string, number>>(() => loadPersistedHeights())

  const oscHandlesRef = useRef<Map<string, OscPaneHandle | null>>(new Map())

  // Crosshair values — updated on every price-chart crosshair move
  const [crosshairValues, setCrosshairValues] =
    useState<Map<string, Map<string, number | null>>>(new Map())

  // ── Inspector state ───────────────────────────────────────────────────────
  // null = show latest candle (mouse left chart or no hover yet)
  const [inspectorCandle, setInspectorCandle] = useState<InspectorCandle | null>(null)
  // Pre-indexed all indicator series values by timestamp (built when artifacts change)
  const allIndicatorValsByTsRef = useRef<Map<string, Map<string, Map<number, number | null>>>>(new Map())
  // Combined inspector values for current crosshair position
  const [inspectorIndVals, setInspectorIndVals] = useState<InspectorIndicatorValues>(new Map())

  const candleTimestamps = useMemo(
    () => normalizeChartData(candles.map(c => ({ time: toUTCTimestamp(c.timestamp) }))).map(d => d.time),
    [candles]
  )

  // Pre-index candles by UTC timestamp (seconds) for O(1) inspector lookup
  const candleByTs = useMemo(() => {
    const m = new Map<number, { candle: OHLCVCandle; prevClose: number | undefined }>()
    const sorted = [...candles].sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
    for (let i = 0; i < sorted.length; i++) {
      const ts = toUTCTimestamp(sorted[i].timestamp) as number
      m.set(ts, { candle: sorted[i], prevClose: i > 0 ? sorted[i - 1].close : undefined })
    }
    return m
  }, [candles])

  // Derive the "latest" candle for the inspector's fallback state
  const latestInspectorCandle = useMemo((): InspectorCandle | null => {
    if (candles.length === 0) return null
    const sorted = [...candles].sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
    const last = sorted[sorted.length - 1]
    const prev = sorted.length > 1 ? sorted[sorted.length - 2] : undefined
    const change    = prev ? last.close - prev.close : undefined
    const changePct = (change !== undefined && prev) ? (change / prev.close) * 100 : undefined
    return { open: last.open, high: last.high, low: last.low, close: last.close, volume: last.volume, change, changePct }
  }, [candles])

  // Pre-index ALL artifact series values (both price_overlay and oscillator_pane)
  // by instance_id → series_id → UTCTimestamp(s) → value|null
  // Built once per artifact change; used in O(1) inspector lookups during crosshair.
  useEffect(() => {
    const byTs = new Map<string, Map<string, Map<number, number | null>>>()
    for (const artifact of indicatorArtifacts ?? []) {
      const seriesMap = new Map<string, Map<number, number | null>>()
      for (const series of artifact.series) {
        const tsMap = new Map<number, number | null>()
        for (const pt of series.values) {
          if (pt.timestamp) tsMap.set(toUTCTimestamp(pt.timestamp) as number, pt.value)
        }
        seriesMap.set(series.series_id, tsMap)
      }
      byTs.set(artifact.instance_id, seriesMap)
    }
    allIndicatorValsByTsRef.current = byTs
  }, [indicatorArtifacts])

  const oscArtifactGroups = useMemo(() => {
    if (!indicatorArtifacts || indicatorArtifacts.length === 0) return []
    const seen   = new Set<string>()
    const groups: { key: string; label: string }[] = []
    for (const a of indicatorArtifacts) {
      if (!seen.has(a.tool_id) && a.series.some(s => s.pane === 'oscillator_pane')) {
        seen.add(a.tool_id)
        groups.push({ key: a.tool_id, label: a.display_name })
      }
    }
    return groups
  }, [indicatorArtifacts])

  useEffect(() => {
    setOscPaneHeights(prev => {
      const next = { ...prev }
      for (const g of oscArtifactGroups) {
        if (!(g.key in next)) next[g.key] = DEFAULT_OSC_HEIGHT
      }
      for (const k of Object.keys(next)) {
        if (!oscArtifactGroups.some(g => g.key === k)) delete next[k]
      }
      return next
    })
  }, [oscArtifactGroups])

  // ── Create price chart on mount ────────────────────────────────────────────
  useEffect(() => {
    if (!priceContainerRef.current) return
    const chart = createChart(priceContainerRef.current, {
      ..._CHART_THEME,
      width:  priceContainerRef.current.clientWidth,
      height: priceContainerRef.current.clientHeight || 400,
    })

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a', downColor: '#ef5350', borderVisible: false,
      wickUpColor: '#26a69a', wickDownColor: '#ef5350',
    })
    const forecastSeries = chart.addSeries(LineSeries, {
      color: '#ffa726', lineWidth: 1, lineStyle: 2,
      crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false,
    })
    const markerApi = createSeriesMarkers(candleSeries, [])

    chartRef.current          = chart
    candleSeriesRef.current   = candleSeries
    markerApiRef.current      = markerApi
    forecastSeriesRef.current = forecastSeries
    setPriceChartApi(chart)

    const ro = new ResizeObserver(entries => {
      for (const e of entries) chart.applyOptions({ width: e.contentRect.width, height: e.contentRect.height })
    })
    ro.observe(priceContainerRef.current)

    return () => {
      ro.disconnect()
      priceSeriesMapRef.current.clear()
      artifactPriceSeriesMapRef.current.clear()
      markerApiRef.current?.detach()
      chart.remove()
      chartRef.current = null; candleSeriesRef.current = null
      markerApiRef.current = null; forecastSeriesRef.current = null
      setPriceChartApi(null)
    }
  }, [])

  // ── Create strategy oscillator chart on mount ─────────────────────────────
  useEffect(() => {
    if (!oscContainerRef.current) return
    const oscChart = createChart(oscContainerRef.current, {
      ..._CHART_THEME,
      width:  oscContainerRef.current.clientWidth,
      height: oscContainerRef.current.clientHeight || 160,
    })
    oscChartRef.current = oscChart
    const ro = new ResizeObserver(entries => {
      for (const e of entries) oscChart.applyOptions({ width: e.contentRect.width, height: e.contentRect.height })
    })
    ro.observe(oscContainerRef.current)
    return () => {
      ro.disconnect()
      clearOscillatorReferenceGuides(oscGuideMapRef.current)
      oscSeriesMapRef.current.clear()
      oscChart.remove()
      oscChartRef.current = null
    }
  }, [])

  // ── One-directional logical range sync: price → strategy osc ─────────────
  useEffect(() => {
    const priceChart = chartRef.current
    const oscChart   = oscChartRef.current
    if (!priceChart || !oscChart) return

    const syncFromPrice = (range: LogicalRange | null) => {
      if (oscSyncingRef.current || !range) return
      oscSyncingRef.current = true
      try { oscChart.timeScale().setVisibleLogicalRange(range) } catch { /* not ready */ }
      oscSyncingRef.current = false
    }

    priceChart.timeScale().subscribeVisibleLogicalRangeChange(syncFromPrice)
    return () => { priceChart.timeScale().unsubscribeVisibleLogicalRangeChange(syncFromPrice) }
  }, [])

  // ── Crosshair sync: price → strategy osc ─────────────────────────────────
  useEffect(() => {
    const priceChart = chartRef.current
    const oscChart   = oscChartRef.current
    if (!priceChart || !oscChart) return

    const syncCrosshair = (param: MouseEventParams | null) => {
      if (!param || !param.time || oscSeriesMapRef.current.size === 0) {
        try { oscChart.clearCrosshairPosition() } catch { /* ignore */ }
        return
      }

      const firstSeries = [...oscSeriesMapRef.current.values()][0]
      if (!firstSeries) {
        try { oscChart.clearCrosshairPosition() } catch { /* ignore */ }
        return
      }

      const val = oscTimeValueMapRef.current.get(param.time as number)
      if (val === undefined) return

      try { oscChart.setCrosshairPosition(val, param.time, firstSeries) } catch { /* out of range */ }
    }

    priceChart.subscribeCrosshairMove(syncCrosshair)
    return () => { priceChart.unsubscribeCrosshairMove(syncCrosshair) }
  }, [])

  // ── Crosshair → legend value update ──────────────────────────────────────
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    const onCrosshair = (param: MouseEventParams | null) => {
      if (!param || !param.time) {
        // Mouse left chart — revert inspector to latest candle, clear indicator vals
        setCrosshairValues(new Map())
        setInspectorCandle(null)
        setInspectorIndVals(new Map())
        return
      }

      // ── Legend overlay values (price pane series) ───────────────────
      const newVals = new Map<string, Map<string, number | null>>()
      for (const artifact of indicatorArtifacts ?? []) {
        const svMap = new Map<string, number | null>()
        for (const series of artifact.series.filter(s => s.pane === 'price_overlay')) {
          const key = `${artifact.instance_id}.${series.series_id}`
          const seriesApi = artifactPriceSeriesMapRef.current.get(key)
          if (seriesApi) {
            const d = param.seriesData.get(seriesApi) as { value?: number } | undefined
            svMap.set(series.series_id, d?.value ?? null)
          }
        }
        if (svMap.size > 0) newVals.set(artifact.instance_id, svMap)
      }
      setCrosshairValues(newVals)

      // ── Inspector candle update ─────────────────────────────────────
      const ts = param.time as number
      const entry = candleByTs.get(ts)
      if (entry) {
        const { candle, prevClose } = entry
        const change    = prevClose !== undefined ? candle.close - prevClose : undefined
        const changePct = (change !== undefined && prevClose !== undefined)
          ? (change / prevClose) * 100
          : undefined
        setInspectorCandle({
          open: candle.open, high: candle.high, low: candle.low,
          close: candle.close, volume: candle.volume,
          change, changePct,
        })
      }

      // ── Inspector indicator values (all series, by pre-indexed ts) ──
      const indVals = new Map<string, Map<string, number | null>>()
      for (const [instId, seriesMap] of allIndicatorValsByTsRef.current) {
        const svMap = new Map<string, number | null>()
        for (const [seriesId, tsMap] of seriesMap) {
          svMap.set(seriesId, tsMap.get(ts) ?? null)
        }
        indVals.set(instId, svMap)
      }
      setInspectorIndVals(indVals)
    }

    chart.subscribeCrosshairMove(onCrosshair)
    return () => { chart.unsubscribeCrosshairMove(onCrosshair) }
  }, [indicatorArtifacts, candleByTs])

  // ── Update candlestick data ───────────────────────────────────────────────
  useEffect(() => {
    const series = candleSeriesRef.current
    if (!series) return
    if (candles.length === 0) { series.setData([]); return }
    const data: CandlestickData[] = normalizeChartData(
      candles.map(c => ({ time: toUTCTimestamp(c.timestamp), open: c.open, high: c.high, low: c.low, close: c.close }))
    )
    series.setData(data)
    chartRef.current?.timeScale().fitContent()
  }, [candles])

  // ── Strategy oscillator pane visibility ───────────────────────────────────
  useEffect(() => {
    setShowOscillator((overlay?.indicators ?? []).some(i => i.pane === 'oscillator'))
  }, [overlay])

  // ── Render strategy overlay ───────────────────────────────────────────────
  useEffect(() => {
    const priceChart     = chartRef.current
    const oscChart       = oscChartRef.current
    const candleSeries   = candleSeriesRef.current
    const markerApi      = markerApiRef.current
    const forecastSeries = forecastSeriesRef.current
    if (!priceChart || !candleSeries || !markerApi || !forecastSeries) return

    for (const s of priceSeriesMapRef.current.values()) priceChart.removeSeries(s)
    priceSeriesMapRef.current.clear()
    if (oscChart) {
      clearOscillatorReferenceGuides(oscGuideMapRef.current)
      for (const s of oscSeriesMapRef.current.values()) oscChart.removeSeries(s)
    }
    oscSeriesMapRef.current.clear()
    oscTimeValueMapRef.current.clear()
    markerApi.setMarkers([])
    forecastSeries.setData([])

    if (!overlay) {
      oscTimeValueMapRef.current.clear()
      return
    }

    const indicators      = overlay.indicators ?? []
    const priceIndicators = indicators.filter(ind => ind.pane !== 'oscillator')
    const oscIndicators   = indicators.filter(ind => ind.pane === 'oscillator')

    const strategyVolumeColorMap = buildVolumeColorMap(candles)

    priceIndicators.forEach((ind, idx) => {
      const color = ind.color ?? _DEFAULT_COLORS[idx % _DEFAULT_COLORS.length]

      if (ind.kind === 'histogram') {
        // Volume-style histogram: dedicated scale so it floats at the bottom of the
        // price pane without distorting OHLC price scaling (same as indicator path).
        const pts = normalizeChartData(
          ind.points.map(p => ({
            time:  toUTCTimestamp(p.timestamp),
            value: p.value,
            color: strategyVolumeColorMap.get(toUTCTimestamp(p.timestamp)) ?? VOLUME_UP_COLOR,
          }))
        )
        if (pts.length === 0) return
        const s = priceChart.addSeries(HistogramSeries, {
          color,
          priceFormat:      { type: 'volume' },
          priceScaleId:     'volume',
          lastValueVisible: false,
          priceLineVisible: false,
          title:            ind.name,
        })
        s.priceScale().applyOptions({ scaleMargins: { top: 0.75, bottom: 0 } })
        s.setData(pts as HistogramData[])
        priceSeriesMapRef.current.set(ind.name, s)
      } else if (ind.price_scale === 'volume') {
        // Volume MA line: on the volume scale so it aligns with the histogram.
        const pts = normalizeChartData(
          ind.points.map(p => ({ time: toUTCTimestamp(p.timestamp), value: p.value }))
        )
        if (pts.length === 0) return
        const s = priceChart.addSeries(LineSeries, {
          color,
          lineWidth:              1,
          priceScaleId:           'volume',
          crosshairMarkerVisible: false,
          lastValueVisible:       false,
          priceLineVisible:       false,
          title:                  ind.name,
        })
        s.setData(pts as LineData[])
        priceSeriesMapRef.current.set(ind.name, s)
      } else {
        // Normal price overlay (EMA, SMA, Bollinger, etc.) — default price scale.
        const pts = normalizeChartData(
          ind.points.map(p => ({ time: toUTCTimestamp(p.timestamp), value: p.value }))
        )
        if (pts.length === 0) return
        const s = priceChart.addSeries(LineSeries, {
          color, lineWidth: 1, crosshairMarkerVisible: false,
          lastValueVisible: true, priceLineVisible: false, title: ind.name,
        })
        s.setData(pts as LineData[])
        priceSeriesMapRef.current.set(ind.name, s)
      }
    })

    if (oscChart && oscIndicators.length > 0) {
      const renderedGuideIds = new Set<string>()
      oscIndicators.forEach((ind, idx) => {
        const color = ind.color ?? _DEFAULT_COLORS[idx % _DEFAULT_COLORS.length]
        if (ind.kind === 'histogram') {
          const s = oscChart.addSeries(HistogramSeries, {
            priceLineVisible: false, lastValueVisible: false, title: ind.name,
          })
          s.setData(normalizeChartData(
            ind.points.map(p => ({ time: toUTCTimestamp(p.timestamp), value: p.value, color: p.value >= 0 ? '#26a69a' : '#ef5350' }))
          ))
          oscSeriesMapRef.current.set(ind.name, s)
        } else {
          const s = oscChart.addSeries(LineSeries, {
            color, lineWidth: 1, crosshairMarkerVisible: false,
            lastValueVisible: false, priceLineVisible: false, title: ind.name,
          })
          s.setData(normalizeChartData(ind.points.map(p => ({ time: toUTCTimestamp(p.timestamp), value: p.value }))))
          oscSeriesMapRef.current.set(ind.name, s)
          for (const guide of _OSCILLATOR_REFERENCE_GUIDES) {
            if (renderedGuideIds.has(guide.id) || !guide.matches(ind)) continue
            const lines = guide.levels.map(level => s.createPriceLine({
              price: level.value, color: level.color, lineWidth: 1,
              lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: level.label,
            }))
            oscGuideMapRef.current.set(guide.id, { series: s, lines })
            renderedGuideIds.add(guide.id)
          }
        }
      })

      const firstLine = oscIndicators.find(ind => ind.kind !== 'histogram')
      if (firstLine) {
        const tsVal = new Map<number, number>()
        for (const p of firstLine.points) {
          if (p.timestamp) tsVal.set(toUTCTimestamp(p.timestamp) as number, p.value)
        }
        oscTimeValueMapRef.current = tsVal
      } else {
        oscTimeValueMapRef.current.clear()
      }

      const pr = chartRef.current?.timeScale().getVisibleLogicalRange()
      if (pr) {
        try { oscChart.timeScale().setVisibleLogicalRange(pr) } catch { oscChart.timeScale().fitContent() }
      } else {
        oscChart.timeScale().fitContent()
      }
    } else {
      oscTimeValueMapRef.current.clear()
    }

    if (overlay.signals.length > 0) {
      markerApi.setMarkers(overlay.signals.map(sig => ({
        time:     toUTCTimestamp(sig.timestamp),
        position: sig.signal_type === 'long' ? 'belowBar' : 'aboveBar',
        color:    sig.signal_type === 'long' ? '#26a69a' : '#ef5350',
        shape:    sig.signal_type === 'long' ? 'arrowUp' : 'arrowDown',
        text:     sig.signal_type.toUpperCase(),
        size:     1,
      } as SeriesMarker<Time>)))
    }

    if (overlay.forecast && candles.length > 0) {
      const last = candles[candles.length - 1]
      forecastSeries.setData([
        { time: toUTCTimestamp(last.timestamp), value: last.close },
        { time: toUTCTimestamp(overlay.forecast.target_timestamp), value: overlay.forecast.target_price },
      ])
    }
  }, [overlay, candles])

  // ── Render artifact price-overlay series ─────────────────────────────────
  useEffect(() => {
    const priceChart = chartRef.current
    if (!priceChart) return
    for (const s of artifactPriceSeriesMapRef.current.values()) {
      try { priceChart.removeSeries(s) } catch { /* ignore */ }
    }
    artifactPriceSeriesMapRef.current.clear()
    if (!indicatorArtifacts || indicatorArtifacts.length === 0) return

    // Lazy color map: built once on first histogram encountered per render.
    // Uses close-to-close comparison from current candle data.
    let colorMap: Map<UTCTimestamp, string> | null = null
    const getVolumeColorMap = () => {
      if (!colorMap) colorMap = buildVolumeColorMap(candles)
      return colorMap
    }

    // Deduplication flag: tracks whether any artifact has already rendered a volume
    // histogram in this pass. When both 'volume' and 'volume_ma' are active, they each
    // expose a histogram series — rendering both would produce identical overlapping bars.
    // Only the first histogram encountered is rendered; MA lines always render.
    let hasRenderedVolumeHistogram = false

    for (const artifact of indicatorArtifacts) {
      const priceSeries    = artifact.series.filter(s => s.pane === 'price_overlay')
      const isSingleSeries = priceSeries.length === 1
      const instanceColor  = instanceColors?.get(artifact.instance_id)

      // Volume-style artifacts: any artifact that has a histogram series in the price
      // pane uses a named 'volume' price scale so the histogram floats at the bottom
      // of the price chart (TradingView-style) without interfering with candle scaling.
      const hasVolumeHistogram = priceSeries.some(s => s.render_type === 'histogram')

      for (const series of priceSeries) {
        const key   = `${artifact.instance_id}.${series.series_id}`
        const color = (isSingleSeries && instanceColor) ? instanceColor : series.default_color

        if (series.render_type === 'histogram') {
          // Skip duplicate volume histograms. When 'volume' and 'volume_ma' are both
          // active, the second histogram is visually identical to the first; skip it so
          // only one histogram layer floats on the price chart (TradingView behaviour).
          if (hasRenderedVolumeHistogram) continue
          hasRenderedVolumeHistogram = true
          // Single-color mode: use the provided hex for all bars; otherwise directional.
          const singleColor = volumeColorModes?.get(artifact.instance_id)
          const pts = normalizeChartData(
            series.values
              .filter(p => p.value !== null && p.timestamp)
              .map(p => {
                const ts = toUTCTimestamp(p.timestamp)
                return {
                  time:  ts,
                  value: p.value as number,
                  color: singleColor ?? (getVolumeColorMap().get(ts) ?? VOLUME_UP_COLOR),
                }
              })
          )
          if (pts.length === 0) continue
          const s = priceChart.addSeries(HistogramSeries, {
            color,
            priceFormat: { type: 'volume' },
            priceScaleId: 'volume',
            lastValueVisible: false,
            priceLineVisible: false,
            title: series.label,
          })
          // The 'volume' price scale is created by addSeries — configure it here,
          // after the scale exists.  s.priceScale() is the canonical way to reach
          // the named scale without relying on chart.priceScale('volume') which
          // throws if called before the first series with that ID is added.
          s.priceScale().applyOptions({ scaleMargins: { top: 0.75, bottom: 0 } })
          s.setData(pts as HistogramData[])
          artifactPriceSeriesMapRef.current.set(key, s)
        } else {
          const pts = normalizeChartData(
            series.values.filter(p => p.value !== null && p.timestamp)
              .map(p => ({ time: toUTCTimestamp(p.timestamp), value: p.value as number }))
          )
          if (pts.length === 0) continue
          if (hasVolumeHistogram) {
            // Volume MA line: also on the 'volume' scale so it aligns with the histogram.
            const s = priceChart.addSeries(LineSeries, {
              color,
              lineWidth: 1,
              priceScaleId: 'volume',
              crosshairMarkerVisible: false,
              lastValueVisible: false,
              priceLineVisible: false,
              title: series.label,
              lineStyle: toLineStyle(series.line_style),
            })
            s.setData(pts as LineData[])
            artifactPriceSeriesMapRef.current.set(key, s)
          } else {
            // Regular line overlay (SMA, EMA, Bollinger, etc.)
            const s = priceChart.addSeries(LineSeries, {
              color, lineWidth: 1, crosshairMarkerVisible: false,
              lastValueVisible: true, priceLineVisible: false, title: series.label,
              lineStyle: toLineStyle(series.line_style),
            })
            s.setData(pts as LineData[])
            artifactPriceSeriesMapRef.current.set(key, s)
          }
        }
      }
    }
  }, [indicatorArtifacts, instanceColors, candles, volumeColorModes])

  // ── Commit handler: save to localStorage ─────────────────────────────────
  const commitHeight = (key: string, h: number) => {
    setOscPaneHeights(prev => {
      const next = { ...prev, [key]: h }
      savePersistedHeights(next)
      return next
    })
  }

  const signalCount       = overlay?.signals.length ?? 0
  const priceIndCount     = (overlay?.indicators ?? []).filter(i => i.pane !== 'oscillator').length
  const oscIndCount       = (overlay?.indicators ?? []).filter(i => i.pane === 'oscillator').length
  const hasStrategyResults = signalCount > 0 || priceIndCount > 0 || oscIndCount > 0 || !!overlay?.forecast

  return (
    <div style={styles.wrapper}>
      {/* ── Data Inspector (replaces old header row) ─────────────────── */}
      <ChartDataInspector
        symbol={symbol}
        timeframe={timeframe}
        exchange={exchange}
        candle={inspectorCandle ?? latestInspectorCandle}
        indicatorArtifacts={indicatorArtifacts}
        instanceLabels={instanceLabels}
        instanceColors={instanceColors}
        instanceVisible={instanceVisible}
        indicatorValues={inspectorCandle !== null ? inspectorIndVals : undefined}
      />

      {/* ── Strategy results toolbar (hidden when no results) ────────── */}
      {hasStrategyResults && (
        <div style={styles.toolbar}>
          {priceIndCount > 0 && <span style={styles.badge}>{priceIndCount} overlay{priceIndCount !== 1 ? 's' : ''}</span>}
          {oscIndCount   > 0 && <span style={{ ...styles.badge, color: '#7e57c2' }}>{oscIndCount} oscillator{oscIndCount !== 1 ? 's' : ''}</span>}
          {signalCount   > 0 && <span style={styles.badge}>{signalCount} signal{signalCount !== 1 ? 's' : ''}</span>}
          {overlay?.forecast && (
            <span style={{ ...styles.badge, color: overlay.forecast.direction === 'long' ? '#26a69a' : '#ef5350' }}>
              forecast {overlay.forecast.direction}
            </span>
          )}
          <button
            type="button"
            onClick={onClearStrategyResults}
            style={{ ...styles.clearBtn, marginLeft: 'auto' }}
          >
            Clear Strategy Results
          </button>
        </div>
      )}

      {/* Price chart + legend overlay */}
      <div style={styles.priceWrapper}>
        <div ref={priceContainerRef} style={styles.priceChart} />
        <ChartLegendOverlay
          artifacts={(indicatorArtifacts ?? []).filter(a => a.series.some(s => s.pane === 'price_overlay'))}
          instanceColors={instanceColors}
          instanceLabels={instanceLabels}
          instanceVisible={instanceVisible}
          crosshairValues={crosshairValues}
          highlightedId={highlightedInstanceId}
          onHover={onHoverInstance}
          onToggle={onIndicatorToggle}
          onRemove={onIndicatorRemove}
        />
      </div>

      {/* Strategy oscillator pane */}
      <div style={{ ...styles.oscWrapper, height: showOscillator ? 160 : 0, overflow: 'hidden' }}>
        {showOscillator && <div style={styles.oscLabel}>oscillator</div>}
        <div ref={oscContainerRef} style={styles.oscChart} />
      </div>

      {/* Indicator artifact oscillator panes */}
      {oscArtifactGroups.map(group => {
        const committedH = oscPaneHeights[group.key] ?? DEFAULT_OSC_HEIGHT
        return (
          <div key={group.key}>
            <DragSplitter
              getCommittedHeight={() => oscPaneHeights[group.key] ?? DEFAULT_OSC_HEIGHT}
              onCommitHeight={h => commitHeight(group.key, h)}
              oscHandle={oscHandlesRef.current.get(group.key) ?? null}
              priceChartRef={chartRef}
              onReset={() => commitHeight(group.key, DEFAULT_OSC_HEIGHT)}
            />
            <OscPane
              ref={(handle: OscPaneHandle | null) => { oscHandlesRef.current.set(group.key, handle) }}
              label={group.label}
              artifacts={(indicatorArtifacts ?? []).filter(a => a.tool_id === group.key)}
              instanceColors={instanceColors}
              instanceLabels={instanceLabels}
              instanceVisible={instanceVisible}
              candleTimestamps={candleTimestamps}
              priceChart={priceChartApi}
              height={committedH}
              highlightedId={highlightedInstanceId}
              onCrosshairValues={_vals => { /* values consumed inside OscPane header */ }}
              onToggle={onIndicatorToggle}
              onRemove={onIndicatorRemove}
            />
          </div>
        )
      })}
    </div>
  )
}

function clearOscillatorReferenceGuides(guides: Map<string, ReferenceGuideBinding>) {
  for (const binding of guides.values()) {
    for (const line of binding.lines) binding.series.removePriceLine(line)
  }
  guides.clear()
}

const styles: Record<string, React.CSSProperties> = {
  wrapper: { flex: 1, display: 'flex', flexDirection: 'column', background: '#0f0f1a', minHeight: 0, overflowY: 'auto' },
  toolbar: {
    padding: '4px 10px', fontSize: '11px', color: '#8892a4', fontFamily: 'monospace',
    borderBottom: '1px solid #1a1a2e', display: 'flex',
    alignItems: 'center', gap: '8px', flexShrink: 0,
  },
  priceWrapper: { flex: 1, position: 'relative', minHeight: 200 },
  priceChart: { width: '100%', height: '100%' },
  oscWrapper: { flexShrink: 0, borderTop: '1px solid #1a1a2e', position: 'relative', transition: 'height 0.15s ease' },
  oscLabel: { position: 'absolute', top: 4, left: 8, fontSize: 9, color: '#2a2a3e', fontFamily: 'monospace', letterSpacing: '0.07em', pointerEvents: 'none', zIndex: 1 },
  oscChart: { width: '100%', height: '100%' },
  badge: { fontSize: '11px', color: '#ffa726', background: '#1a1a2e', padding: '2px 8px', borderRadius: '4px' },
  clearBtn: { background: '#111827', border: '1px solid #2a2d3e', borderRadius: 4, color: '#9aa4b8', fontFamily: 'monospace', fontSize: 11, padding: '3px 9px', cursor: 'pointer' },
}
