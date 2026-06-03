/**
 * Chart.tsx — Chart-UX-3C.3A (Time Synchronization Hardening).
 *
 * Root-cause fix for horizontal drift between price chart and oscillator panes:
 *
 *   Problem: warmup-null values were filtered before setData, so oscillator panes
 *   had fewer bars than the price chart.  When setVisibleRange was called with a
 *   timestamp in the warmup gap, lightweight-charts clamped to the first available
 *   bar and the pane appeared shifted.  With bidirectional sync, this clamped range
 *   could echo back to the price chart, fighting the intended position.
 *
 *   Fix 1 — Full timestamp domain: warmup bars are now included as WhitespaceData
 *   ({ time: T } with no value).  Every oscillator pane shares the exact same bar
 *   sequence as the price chart, so setVisibleRange positions correctly at any zoom.
 *
 *   Fix 2 — One-directional sync (price → oscillators): oscillator time-scale changes
 *   no longer propagate back to the price chart.  This eliminates echo-back drift and
 *   all feedback-loop risk.  Tradeoff: scrolling inside an oscillator pane no longer
 *   drives the price chart.  Oscillators resync on the next price-chart scroll event.
 *
 *   Fix 3 — normalizeChartData: sort + dedupe all data before setData to prevent
 *   out-of-order or duplicate timestamp errors from the chart library.
 *
 *   Fix 4 — No fitContent after indicator updates: setVisibleRange(priceRange) is
 *   applied instead, preserving user zoom/scroll.  fitContent only runs on initial
 *   candle load.
 *
 * All other behavior (crosshair sync, color overrides, resizable panes) is preserved.
 */
import { useEffect, useRef, useState, useMemo } from 'react'
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
  IRange,
  MouseEventParams,
  LineData,
  HistogramData,
  WhitespaceData,
} from 'lightweight-charts'
import type { OHLCVCandle } from '../api/marketData'
import type { ToolVisualizationSeries } from '../types/toolVisualization'
import type { StrategyOverlay } from '../types/strategy'
import type { IndicatorArtifactResponse, IndicatorSeriesPoint } from '../types/chartIndicators'

interface ChartProps {
  candles: OHLCVCandle[]
  symbol: string
  timeframe: string
  overlay?: StrategyOverlay | null
  indicatorArtifacts?: IndicatorArtifactResponse[]
  /** palette colors keyed by instance_id, for single-series overlay tools. */
  instanceColors?: Map<string, string>
  onClearStrategyResults?: () => void
}

function toUTCTimestamp(isoString: string): UTCTimestamp {
  return Math.floor(new Date(isoString).getTime() / 1000) as UTCTimestamp
}

const _DEFAULT_COLORS = ['#2196f3', '#ff9800', '#9c27b0', '#00bcd4', '#4caf50']

const _CHART_THEME = {
  layout: {
    background: { color: '#0f0f1a' },
    textColor: '#d1d4dc',
  },
  grid: {
    vertLines: { color: '#1a1a2e' },
    horzLines: { color: '#1a1a2e' },
  },
  crosshair: { mode: 1 },
  rightPriceScale: { borderColor: '#2a2d3e' },
  timeScale: {
    borderColor:     '#2a2d3e',
    timeVisible:     true,
    secondsVisible:  false,
  },
}

type AnySeriesApi = ISeriesApi<'Line'> | ISeriesApi<'Histogram'>
type ReferenceGuideBinding = {
  series: ISeriesApi<'Line'>
  lines: IPriceLine[]
}

type OscillatorReferenceGuide = {
  id: string
  matches: (series: ToolVisualizationSeries) => boolean
  levels: { value: number; label: string; color: string }[]
}

const _OSCILLATOR_REFERENCE_GUIDES: OscillatorReferenceGuide[] = [
  {
    id: 'rsi',
    matches: ind => {
      const name = ind.name.toLowerCase()
      return ind.pane === 'oscillator' && ind.kind !== 'histogram' && /\brsi\b|\.rsi\b|rsi_/i.test(name)
    },
    levels: [
      { value: 70, label: 'RSI 70', color: 'rgba(239, 83, 80, 0.45)' },
      { value: 50, label: 'RSI 50', color: 'rgba(136, 146, 164, 0.28)' },
      { value: 30, label: 'RSI 30', color: 'rgba(38, 166, 154, 0.45)' },
    ],
  },
]

const MIN_OSC_HEIGHT     = 80
const DEFAULT_OSC_HEIGHT = 130

// ---------------------------------------------------------------------------
// Data-normalization helpers
// ---------------------------------------------------------------------------

/**
 * Sort by time ascending + deduplicate (last occurrence wins for duplicate
 * timestamps).  Does NOT mutate the input array.
 */
function normalizeChartData<T extends { time: UTCTimestamp }>(data: readonly T[]): T[] {
  const map = new Map<number, T>()
  for (const d of data) map.set(d.time as number, d)
  return [...map.values()].sort((a, b) => (a.time as number) - (b.time as number))
}

/**
 * Build a line-series data array aligned to the full candle timestamp domain.
 * Candle timestamps that have no indicator value (warmup bars) become
 * WhitespaceData items ({ time: T }), anchoring the oscillator's time axis to
 * the same bar sequence as the price chart.
 */
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

/**
 * Build a histogram-series data array aligned to the full candle timestamp domain.
 */
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

// ---------------------------------------------------------------------------
// DragSplitter — thin draggable divider between panes
// ---------------------------------------------------------------------------

function DragSplitter({ onDrag }: { onDrag: (delta: number) => void }) {
  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    let lastY = e.clientY
    const onMove = (ev: MouseEvent) => { onDrag(ev.clientY - lastY); lastY = ev.clientY }
    const onUp   = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }
  return (
    <div
      data-testid="pane-splitter"
      onMouseDown={handleMouseDown}
      style={splitterStyle}
    />
  )
}

const splitterStyle: React.CSSProperties = {
  height:     5,
  cursor:     'row-resize',
  background: '#0f0f1a',
  borderTop:  '1px solid #1e1e30',
  flexShrink: 0,
  position:   'relative',
  zIndex:     10,
}

// ---------------------------------------------------------------------------
// OscPane — one oscillator pane per indicator tool group
// ---------------------------------------------------------------------------

interface OscPaneProps {
  label:             string
  artifacts:         IndicatorArtifactResponse[]
  instanceColors?:   Map<string, string>
  /** Full price-chart timestamp sequence — used for whitespace alignment */
  candleTimestamps:  UTCTimestamp[]
  /** Price chart API reference — sync source (one-directional: price → osc) */
  priceChart:        IChartApi | null
  height?:           number
}

function OscPane({
  label, artifacts, instanceColors, candleTimestamps, priceChart, height = DEFAULT_OSC_HEIGHT,
}: OscPaneProps) {
  const containerRef    = useRef<HTMLDivElement>(null)
  const chartRef        = useRef<IChartApi | null>(null)
  const seriesMapRef    = useRef<Map<string, AnySeriesApi>>(new Map())
  // UTCTimestamp → first-series value — for crosshair position lookup
  const timeValueMapRef = useRef<Map<number, number>>(new Map())
  // Guards re-entrant price→osc sync calls
  const isSyncingRef    = useRef(false)

  // Create oscillator chart once on mount
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

  // One-directional time-scale sync: price chart → this pane.
  // Oscillator range changes do NOT propagate back to the price chart.
  // Rationale: bidirectional sync caused clamped oscillator ranges to echo back
  // when the oscillator lacked warmup-period timestamps.  With full timestamp
  // alignment (whitespace bars) the oscillator can handle any price-chart range,
  // making one-directional sync sufficient and echo-free.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !priceChart) return

    const syncFromPrice = (range: IRange<Time> | null) => {
      if (isSyncingRef.current || !range || seriesMapRef.current.size === 0) return
      isSyncingRef.current = true
      try { chart.timeScale().setVisibleRange(range) } catch { /* chart not ready */ }
      isSyncingRef.current = false
    }

    // Crosshair sync: price chart → this pane (one-directional)
    const syncCrosshair = (param: MouseEventParams | null) => {
      if (!param || !param.time || seriesMapRef.current.size === 0) {
        try { chart.clearCrosshairPosition() } catch { /* ignore */ }
        return
      }
      const firstSeries = [...seriesMapRef.current.values()][0]
      if (!firstSeries) return
      const val = timeValueMapRef.current.get(param.time as number)
      if (val !== undefined) {
        try { chart.setCrosshairPosition(val, param.time, firstSeries) } catch { /* time out of range */ }
      }
    }

    priceChart.timeScale().subscribeVisibleTimeRangeChange(syncFromPrice)
    priceChart.subscribeCrosshairMove(syncCrosshair)

    return () => {
      priceChart.timeScale().unsubscribeVisibleTimeRangeChange(syncFromPrice)
      priceChart.unsubscribeCrosshairMove(syncCrosshair)
    }
  }, [priceChart])

  // Rebuild series when artifacts, colors, or candle timestamps change.
  // Uses buildAlignedLineData/buildAlignedHistData so every candle timestamp
  // is represented (warmup bars as whitespace).
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    for (const s of seriesMapRef.current.values()) {
      try { chart.removeSeries(s) } catch { /* already gone */ }
    }
    seriesMapRef.current.clear()
    timeValueMapRef.current.clear()

    for (const artifact of artifacts) {
      const oscSeries      = artifact.series.filter(s => s.pane === 'oscillator_pane')
      const isSingleSeries = oscSeries.length === 1
      const instanceColor  = instanceColors?.get(artifact.instance_id)
      let firstPopulated   = false

      for (const series of oscSeries) {
        const key = `${artifact.instance_id}.${series.series_id}`

        if (series.render_type === 'histogram') {
          const data = buildAlignedHistData(series.values, candleTimestamps)
          if (data.every(d => !('value' in d))) continue  // all whitespace → skip
          const s = chart.addSeries(HistogramSeries, {
            priceLineVisible: false,
            lastValueVisible: true,
            title:            series.label,
          })
          s.setData(data)
          seriesMapRef.current.set(key, s)
        } else {
          const color = (isSingleSeries && instanceColor) ? instanceColor : series.default_color
          const data  = buildAlignedLineData(series.values, candleTimestamps)
          if (data.every(d => !('value' in d))) continue  // all whitespace → skip
          const s = chart.addSeries(LineSeries, {
            color,
            lineWidth:              1,
            crosshairMarkerVisible: false,
            lastValueVisible:       true,
            priceLineVisible:       false,
            title:                  series.label,
          })
          s.setData(data)
          seriesMapRef.current.set(key, s)

          // Populate time→value lookup for crosshair sync
          if (!firstPopulated) {
            for (const p of data) {
              if ('value' in p && p.value !== undefined) {
                timeValueMapRef.current.set(p.time as number, p.value)
              }
            }
            firstPopulated = true
          }
        }
      }
    }

    // Apply current price-chart range instead of fitContent to preserve user zoom
    if (seriesMapRef.current.size > 0) {
      const priceRange = priceChart?.timeScale().getVisibleRange()
      if (priceRange) {
        try { chart.timeScale().setVisibleRange(priceRange) } catch { chart.timeScale().fitContent() }
      } else {
        chart.timeScale().fitContent()
      }
    }
  }, [artifacts, instanceColors, candleTimestamps, priceChart])

  return (
    <div data-testid="osc-pane-wrapper" style={{ ...oscPaneWrapperStyle, height }}>
      <div style={oscPaneLabelStyle}>{label}</div>
      <div ref={containerRef} style={oscPaneChartStyle} />
    </div>
  )
}

const oscPaneWrapperStyle: React.CSSProperties = {
  flexShrink: 0,
  position:   'relative',
  background: '#0f0f1a',
}
const oscPaneLabelStyle: React.CSSProperties = {
  position:      'absolute',
  top:           4,
  left:          8,
  fontSize:      9,
  color:         '#2a2a3e',
  fontFamily:    'monospace',
  letterSpacing: '0.07em',
  pointerEvents: 'none',
  zIndex:        1,
}
const oscPaneChartStyle: React.CSSProperties = {
  width:  '100%',
  height: '100%',
}

// ---------------------------------------------------------------------------
// Main Chart component
// ---------------------------------------------------------------------------

export default function Chart({
  candles, symbol, timeframe, overlay,
  indicatorArtifacts, instanceColors,
  onClearStrategyResults,
}: ChartProps) {
  // Price chart refs
  const priceContainerRef         = useRef<HTMLDivElement>(null)
  const chartRef                  = useRef<IChartApi | null>(null)
  const candleSeriesRef           = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const markerApiRef              = useRef<ISeriesMarkersPluginApi<Time> | null>(null)
  const forecastSeriesRef         = useRef<ISeriesApi<'Line'> | null>(null)
  const priceSeriesMapRef         = useRef<Map<string, ISeriesApi<'Line'>>>(new Map())
  const artifactPriceSeriesMapRef = useRef<Map<string, ISeriesApi<'Line'>>>(new Map())

  // State copy of price chart API — passed to OscPane for sync
  const [priceChartApi, setPriceChartApi] = useState<IChartApi | null>(null)

  // Strategy oscillator chart
  const oscContainerRef = useRef<HTMLDivElement>(null)
  const oscChartRef     = useRef<IChartApi | null>(null)
  const oscSeriesMapRef = useRef<Map<string, AnySeriesApi>>(new Map())
  const oscGuideMapRef  = useRef<Map<string, ReferenceGuideBinding>>(new Map())
  const oscSyncingRef   = useRef(false)

  const [showOscillator, setShowOscillator] = useState(false)

  // Indicator oscillator pane heights (tool_id → px)
  const [oscPaneHeights, setOscPaneHeights] = useState<Record<string, number>>({})

  // Candle timestamps (stable array of UTCTimestamp — shared timestamp domain)
  const candleTimestamps = useMemo(
    () => normalizeChartData(
      candles.map(c => ({ time: toUTCTimestamp(c.timestamp) }))
    ).map(d => d.time),
    [candles]
  )

  // One OscPane per distinct oscillator tool_id
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

  // Initialise heights for new groups; prune stale ones
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
      upColor:       '#26a69a',
      downColor:     '#ef5350',
      borderVisible: false,
      wickUpColor:   '#26a69a',
      wickDownColor: '#ef5350',
    })

    const forecastSeries = chart.addSeries(LineSeries, {
      color:                  '#ffa726',
      lineWidth:              1,
      lineStyle:              2,
      crosshairMarkerVisible: false,
      lastValueVisible:       false,
      priceLineVisible:       false,
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
      chartRef.current          = null
      candleSeriesRef.current   = null
      markerApiRef.current      = null
      forecastSeriesRef.current = null
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

  // ── One-directional sync: price chart → strategy oscillator ──────────────
  useEffect(() => {
    const priceChart = chartRef.current
    const oscChart   = oscChartRef.current
    if (!priceChart || !oscChart) return

    const syncFromPrice = (range: IRange<Time> | null) => {
      if (oscSyncingRef.current || !range) return
      oscSyncingRef.current = true
      try { oscChart.timeScale().setVisibleRange(range) } catch { /* not ready */ }
      oscSyncingRef.current = false
    }

    priceChart.timeScale().subscribeVisibleTimeRangeChange(syncFromPrice)
    return () => {
      priceChart.timeScale().unsubscribeVisibleTimeRangeChange(syncFromPrice)
    }
  }, [])

  // ── Update candlestick data — fitContent only on initial candle load ───────
  useEffect(() => {
    const series = candleSeriesRef.current
    if (!series) return
    if (candles.length === 0) { series.setData([]); return }

    const data: CandlestickData[] = normalizeChartData(
      candles.map(c => ({
        time:  toUTCTimestamp(c.timestamp),
        open:  c.open,
        high:  c.high,
        low:   c.low,
        close: c.close,
      }))
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
    markerApi.setMarkers([])
    forecastSeries.setData([])

    if (!overlay) return

    const indicators      = overlay.indicators ?? []
    const priceIndicators = indicators.filter(ind => ind.pane !== 'oscillator')
    const oscIndicators   = indicators.filter(ind => ind.pane === 'oscillator')

    priceIndicators.forEach((ind, idx) => {
      const color = ind.color ?? _DEFAULT_COLORS[idx % _DEFAULT_COLORS.length]
      const s = priceChart.addSeries(LineSeries, {
        color, lineWidth: 1,
        crosshairMarkerVisible: false,
        lastValueVisible:       true,
        priceLineVisible:       false,
        title:                  ind.name,
      })
      s.setData(normalizeChartData(
        ind.points.map(p => ({ time: toUTCTimestamp(p.timestamp), value: p.value }))
      ))
      priceSeriesMapRef.current.set(ind.name, s)
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
            ind.points.map(p => ({
              time: toUTCTimestamp(p.timestamp), value: p.value,
              color: p.value >= 0 ? '#26a69a' : '#ef5350',
            }))
          ))
          oscSeriesMapRef.current.set(ind.name, s)
        } else {
          const s = oscChart.addSeries(LineSeries, {
            color, lineWidth: 1,
            crosshairMarkerVisible: false,
            lastValueVisible:       false,
            priceLineVisible:       false,
            title:                  ind.name,
          })
          s.setData(normalizeChartData(
            ind.points.map(p => ({ time: toUTCTimestamp(p.timestamp), value: p.value }))
          ))
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
      // Apply price-chart range instead of fitContent to avoid clobbering user zoom
      const priceRange = chartRef.current?.timeScale().getVisibleRange()
      if (priceRange) {
        try { oscChart.timeScale().setVisibleRange(priceRange) } catch { oscChart.timeScale().fitContent() }
      } else {
        oscChart.timeScale().fitContent()
      }
    }

    if (overlay.signals.length > 0) {
      const markers: SeriesMarker<Time>[] = overlay.signals.map(sig => ({
        time:     toUTCTimestamp(sig.timestamp),
        position: sig.signal_type === 'long' ? 'belowBar' : 'aboveBar',
        color:    sig.signal_type === 'long' ? '#26a69a' : '#ef5350',
        shape:    sig.signal_type === 'long' ? 'arrowUp' : 'arrowDown',
        text:     sig.signal_type.toUpperCase(),
        size:     1,
      }))
      markerApi.setMarkers(markers)
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

    for (const artifact of indicatorArtifacts) {
      const priceSeries    = artifact.series.filter(s => s.pane === 'price_overlay')
      const isSingleSeries = priceSeries.length === 1
      const instanceColor  = instanceColors?.get(artifact.instance_id)

      for (const series of priceSeries) {
        const key   = `${artifact.instance_id}.${series.series_id}`
        const color = (isSingleSeries && instanceColor) ? instanceColor : series.default_color

        // Price-overlay series: only non-null points (warmup gap is fine since
        // the price chart defines the timestamp domain, not the overlay series)
        const points = normalizeChartData(
          series.values
            .filter(p => p.value !== null && p.timestamp)
            .map(p => ({ time: toUTCTimestamp(p.timestamp), value: p.value as number }))
        )
        if (points.length === 0) continue

        const s = priceChart.addSeries(LineSeries, {
          color,
          lineWidth:              1,
          crosshairMarkerVisible: false,
          lastValueVisible:       true,
          priceLineVisible:       false,
          title:                  series.label,
        })
        s.setData(points)
        artifactPriceSeriesMapRef.current.set(key, s)
      }
    }
  }, [indicatorArtifacts, instanceColors])

  // ── Header badge counts ──────────────────────────────────────────────────
  const signalCount   = overlay?.signals.length ?? 0
  const priceIndCount = (overlay?.indicators ?? []).filter(i => i.pane !== 'oscillator').length
  const oscIndCount   = (overlay?.indicators ?? []).filter(i => i.pane === 'oscillator').length
  const hasStrategyResults = signalCount > 0 || priceIndCount > 0 || oscIndCount > 0 || !!overlay?.forecast

  return (
    <div style={styles.wrapper}>
      {candles.length > 0 && (
        <div style={styles.header}>
          <span>{symbol} · {timeframe} · {candles.length} candles</span>
          {priceIndCount > 0 && (
            <span style={styles.badge}>{priceIndCount} overlay{priceIndCount !== 1 ? 's' : ''}</span>
          )}
          {oscIndCount > 0 && (
            <span style={{ ...styles.badge, color: '#7e57c2' }}>
              {oscIndCount} oscillator{oscIndCount !== 1 ? 's' : ''}
            </span>
          )}
          {signalCount > 0 && (
            <span style={styles.badge}>{signalCount} signal{signalCount !== 1 ? 's' : ''}</span>
          )}
          {overlay?.forecast && (
            <span style={{ ...styles.badge, color: overlay.forecast.direction === 'long' ? '#26a69a' : '#ef5350' }}>
              forecast {overlay.forecast.direction}
            </span>
          )}
          <button
            type="button"
            onClick={onClearStrategyResults}
            disabled={!hasStrategyResults}
            style={{
              ...styles.clearBtn,
              opacity: hasStrategyResults ? 1 : 0.45,
              cursor:  hasStrategyResults ? 'pointer' : 'default',
            }}
          >
            Clear Strategy Results
          </button>
        </div>
      )}

      {/* Price chart */}
      <div ref={priceContainerRef} style={styles.priceChart} />

      {/* Strategy oscillator pane */}
      <div style={{
        ...styles.oscWrapper,
        height:   showOscillator ? 160 : 0,
        overflow: 'hidden',
      }}>
        {showOscillator && <div style={styles.oscLabel}>oscillator</div>}
        <div ref={oscContainerRef} style={styles.oscChart} />
      </div>

      {/* Indicator artifact oscillator panes — one per tool group */}
      {oscArtifactGroups.map(group => {
        const paneHeight = oscPaneHeights[group.key] ?? DEFAULT_OSC_HEIGHT
        return (
          <div key={group.key}>
            <DragSplitter onDrag={delta => {
              setOscPaneHeights(prev => ({
                ...prev,
                [group.key]: Math.max(MIN_OSC_HEIGHT, (prev[group.key] ?? DEFAULT_OSC_HEIGHT) + delta),
              }))
            }} />
            <OscPane
              label={group.label}
              artifacts={(indicatorArtifacts ?? []).filter(a => a.tool_id === group.key)}
              instanceColors={instanceColors}
              candleTimestamps={candleTimestamps}
              priceChart={priceChartApi}
              height={paneHeight}
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
  wrapper: {
    flex:          1,
    display:       'flex',
    flexDirection: 'column',
    background:    '#0f0f1a',
    minHeight:     0,
    overflowY:     'auto',
  },
  header: {
    padding:       '8px 16px',
    fontSize:      '12px',
    color:         '#8892a4',
    fontFamily:    'monospace',
    letterSpacing: '0.04em',
    borderBottom:  '1px solid #1a1a2e',
    display:       'flex',
    alignItems:    'center',
    gap:           '12px',
    flexShrink:    0,
  },
  priceChart: {
    flex:      1,
    width:     '100%',
    minHeight: 200,
  },
  oscWrapper: {
    flexShrink: 0,
    borderTop:  '1px solid #1a1a2e',
    position:   'relative',
    transition: 'height 0.15s ease',
  },
  oscLabel: {
    position:      'absolute',
    top:           4,
    left:          8,
    fontSize:      9,
    color:         '#2a2a3e',
    fontFamily:    'monospace',
    letterSpacing: '0.07em',
    pointerEvents: 'none',
    zIndex:        1,
  },
  oscChart: { width: '100%', height: '100%' },
  badge: {
    fontSize:     '11px',
    color:        '#ffa726',
    background:   '#1a1a2e',
    padding:      '2px 8px',
    borderRadius: '4px',
  },
  clearBtn: {
    marginLeft:   'auto',
    background:   '#111827',
    border:       '1px solid #2a2d3e',
    borderRadius: 4,
    color:        '#9aa4b8',
    fontFamily:   'monospace',
    fontSize:     11,
    padding:      '3px 9px',
  },
}
