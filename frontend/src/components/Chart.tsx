/**
 * Chart.tsx — Chart-UX-3C.2.
 *
 * Changes from Chart-UX-3C.1:
 *  - Time-scale sync: replaced logical-range sync with time-range sync
 *    (subscribeVisibleTimeRangeChange / setVisibleRange) so price chart and
 *    oscillator panes stay aligned even when they have different bar counts.
 *  - Crosshair sync: price chart crosshair position mirrored to all oscillator
 *    panes (one-directional: price → oscillators).
 *  - Resizable panes: DragSplitter component between panes; oscPaneHeights state
 *    in Chart; OscPane accepts a height prop and ResizeObserver tracks height too.
 *  - indicatorArtifacts prop carries pre-patched colors from App.tsx so Chart
 *    has no dependency on seriesColorOverrides — colors arrive via series.default_color.
 *
 * Null warmup values (value: null) are filtered before rendering — never zero.
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
} from 'lightweight-charts'
import type { OHLCVCandle } from '../api/marketData'
import type { ToolVisualizationSeries } from '../types/toolVisualization'
import type { StrategyOverlay } from '../types/strategy'
import type { IndicatorArtifactResponse } from '../types/chartIndicators'

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
    borderColor: '#2a2d3e',
    timeVisible: true,
    secondsVisible: false,
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

const MIN_OSC_HEIGHT    = 80
const DEFAULT_OSC_HEIGHT = 130

// ---------------------------------------------------------------------------
// DragSplitter — thin draggable divider between panes
// ---------------------------------------------------------------------------

interface DragSplitterProps {
  onDrag: (delta: number) => void
}

function DragSplitter({ onDrag }: DragSplitterProps) {
  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    let lastY = e.clientY
    const onMove = (ev: MouseEvent) => {
      const delta = ev.clientY - lastY
      lastY = ev.clientY
      onDrag(delta)
    }
    const onUp = () => {
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
  position:   'relative' as const,
  zIndex:     10,
}

// ---------------------------------------------------------------------------
// OscPane — one dynamic oscillator pane per indicator tool group
// ---------------------------------------------------------------------------

interface OscPaneProps {
  label: string
  artifacts: IndicatorArtifactResponse[]
  instanceColors?: Map<string, string>
  priceChart: IChartApi | null
  height?: number
}

function OscPane({ label, artifacts, instanceColors, priceChart, height = DEFAULT_OSC_HEIGHT }: OscPaneProps) {
  const containerRef   = useRef<HTMLDivElement>(null)
  const chartRef       = useRef<IChartApi | null>(null)
  const seriesMapRef   = useRef<Map<string, AnySeriesApi>>(new Map())
  // time (UTCTimestamp) → first-series value — used for crosshair sync
  const timeValueMapRef = useRef<Map<number, number>>(new Map())

  // Create the oscillator chart once on mount
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      ..._CHART_THEME,
      height,
    })
    chartRef.current = chart

    const ro = new ResizeObserver(entries => {
      for (const e of entries) {
        chart.applyOptions({
          width:  e.contentRect.width,
          height: e.contentRect.height,
        })
      }
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      seriesMapRef.current.clear()
      chart.remove()
      chartRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Time-scale sync + crosshair sync when price chart becomes available
  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !priceChart) return

    let syncing = false

    const syncFromPrice = (range: IRange<Time> | null) => {
      // Skip if no data loaded yet — setVisibleRange throws "Value is null" on empty charts
      if (syncing || !range || seriesMapRef.current.size === 0) return
      syncing = true
      try { chart.timeScale().setVisibleRange(range) } catch { /* chart not ready */ }
      syncing = false
    }

    const syncFromOsc = (range: IRange<Time> | null) => {
      if (syncing || !range) return
      syncing = true
      try { priceChart.timeScale().setVisibleRange(range) } catch { /* chart not ready */ }
      syncing = false
    }

    priceChart.timeScale().subscribeVisibleTimeRangeChange(syncFromPrice)
    chart.timeScale().subscribeVisibleTimeRangeChange(syncFromOsc)

    // Crosshair sync: price chart → this oscillator pane (one-directional)
    const syncCrosshair = (param: MouseEventParams) => {
      if (!param.time) {
        chart.clearCrosshairPosition()
        return
      }
      const firstSeries = [...seriesMapRef.current.values()][0]
      if (!firstSeries) return
      const val = timeValueMapRef.current.get(param.time as number)
      if (val !== undefined) {
        chart.setCrosshairPosition(val, param.time, firstSeries)
      }
    }

    priceChart.subscribeCrosshairMove(syncCrosshair)

    return () => {
      priceChart.timeScale().unsubscribeVisibleTimeRangeChange(syncFromPrice)
      chart.timeScale().unsubscribeVisibleTimeRangeChange(syncFromOsc)
      priceChart.unsubscribeCrosshairMove(syncCrosshair)
    }
  }, [priceChart])

  // Update series when artifacts or colors change
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    for (const s of seriesMapRef.current.values()) {
      try { chart.removeSeries(s) } catch { /* ignore */ }
    }
    seriesMapRef.current.clear()
    timeValueMapRef.current.clear()

    for (const artifact of artifacts) {
      const oscSeries = artifact.series.filter(s => s.pane === 'oscillator_pane')
      const isSingleSeries = oscSeries.length === 1
      const instanceColor  = instanceColors?.get(artifact.instance_id)
      let firstSeriesPopulated = false

      for (const series of oscSeries) {
        const key = `${artifact.instance_id}.${series.series_id}`
        const points = series.values
          .filter(p => p.value !== null && p.timestamp)
          .map(p => ({ time: toUTCTimestamp(p.timestamp) as Time, value: p.value as number }))

        if (points.length === 0) continue

        if (series.render_type === 'histogram') {
          const s = chart.addSeries(HistogramSeries, {
            priceLineVisible: false,
            lastValueVisible: true,
            title: series.label,
          })
          s.setData(points.map(p => ({
            ...p,
            color: p.value >= 0 ? '#26a69a' : '#ef5350',
          })))
          seriesMapRef.current.set(key, s)
        } else {
          // Colors arrive pre-patched in series.default_color from App.tsx.
          // instanceColor (palette) still covers the single-series case where
          // the user hasn't yet picked a custom color.
          const color = (isSingleSeries && instanceColor) ? instanceColor : series.default_color
          const s = chart.addSeries(LineSeries, {
            color,
            lineWidth:              1,
            crosshairMarkerVisible: false,
            lastValueVisible:       true,
            priceLineVisible:       false,
            title: series.label,
          })
          s.setData(points)
          seriesMapRef.current.set(key, s)
        }

        // Populate the time→value map for crosshair sync from the first series
        if (!firstSeriesPopulated && series.render_type !== 'histogram') {
          for (const p of points) {
            timeValueMapRef.current.set(p.time as number, p.value)
          }
          firstSeriesPopulated = true
        }
      }
    }

    // Sync range from price chart after data update (avoids fitContent drift)
    if (seriesMapRef.current.size > 0) {
      const priceRange = priceChart?.timeScale().getVisibleRange()
      if (priceRange) {
        try { chart.timeScale().setVisibleRange(priceRange) } catch { chart.timeScale().fitContent() }
      } else {
        chart.timeScale().fitContent()
      }
    }
  }, [artifacts, instanceColors, priceChart])

  return (
    <div style={{ ...oscPaneWrapperStyle, height }}>
      <div style={oscPaneLabelStyle}>{label}</div>
      <div ref={containerRef} style={oscPaneChartStyle} />
    </div>
  )
}

const oscPaneWrapperStyle: React.CSSProperties = {
  flexShrink: 0,
  position:   'relative' as const,
  background: '#0f0f1a',
}
const oscPaneLabelStyle: React.CSSProperties = {
  position:      'absolute' as const,
  top:           4,
  left:          8,
  fontSize:      9,
  color:         '#2a2a3e',
  fontFamily:    'monospace',
  letterSpacing: '0.07em',
  pointerEvents: 'none' as const,
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
  // Price chart
  const priceContainerRef        = useRef<HTMLDivElement>(null)
  const chartRef                 = useRef<IChartApi | null>(null)
  const candleSeriesRef          = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const markerApiRef             = useRef<ISeriesMarkersPluginApi<Time> | null>(null)
  const forecastSeriesRef        = useRef<ISeriesApi<'Line'> | null>(null)
  const priceSeriesMapRef        = useRef<Map<string, ISeriesApi<'Line'>>>(new Map())
  const artifactPriceSeriesMapRef = useRef<Map<string, ISeriesApi<'Line'>>>(new Map())

  // State copy of price chart API — passed to OscPane for time-scale + crosshair sync
  const [priceChartApi, setPriceChartApi] = useState<IChartApi | null>(null)

  // Strategy oscillator chart
  const oscContainerRef = useRef<HTMLDivElement>(null)
  const oscChartRef     = useRef<IChartApi | null>(null)
  const oscSeriesMapRef = useRef<Map<string, AnySeriesApi>>(new Map())
  const oscGuideMapRef  = useRef<Map<string, ReferenceGuideBinding>>(new Map())

  const [showOscillator, setShowOscillator] = useState(false)

  // Indicator oscillator pane heights (tool_id → px height)
  const [oscPaneHeights, setOscPaneHeights] = useState<Record<string, number>>({})

  // One OscPane group per oscillator tool_id
  const oscArtifactGroups = useMemo(() => {
    if (!indicatorArtifacts || indicatorArtifacts.length === 0) return []
    const seen = new Set<string>()
    const groups: { key: string; label: string }[] = []
    for (const a of indicatorArtifacts) {
      if (!seen.has(a.tool_id) && a.series.some(s => s.pane === 'oscillator_pane')) {
        seen.add(a.tool_id)
        groups.push({ key: a.tool_id, label: a.display_name })
      }
    }
    return groups
  }, [indicatorArtifacts])

  // Initialise heights for newly-appearing groups; remove stale ones
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

  // ── Sync strategy oscillator with price chart (time-range based) ──────────
  useEffect(() => {
    const priceChart = chartRef.current
    const oscChart   = oscChartRef.current
    if (!priceChart || !oscChart) return

    let syncing = false

    const syncFromPrice = (range: IRange<Time> | null) => {
      if (syncing || !range) return
      syncing = true
      try { oscChart.timeScale().setVisibleRange(range) } catch { /* osc chart not ready */ }
      syncing = false
    }

    const syncFromOsc = (range: IRange<Time> | null) => {
      if (syncing || !range) return
      syncing = true
      try { priceChart.timeScale().setVisibleRange(range) } catch { /* price chart not ready */ }
      syncing = false
    }

    priceChart.timeScale().subscribeVisibleTimeRangeChange(syncFromPrice)
    oscChart.timeScale().subscribeVisibleTimeRangeChange(syncFromOsc)

    return () => {
      priceChart.timeScale().unsubscribeVisibleTimeRangeChange(syncFromPrice)
      oscChart.timeScale().unsubscribeVisibleTimeRangeChange(syncFromOsc)
    }
  }, [])

  // ── Update candlestick data ───────────────────────────────────────────────
  useEffect(() => {
    const series = candleSeriesRef.current
    if (!series) return
    if (candles.length === 0) { series.setData([]); return }
    const data: CandlestickData[] = candles.map(c => ({
      time:  toUTCTimestamp(c.timestamp),
      open:  c.open,
      high:  c.high,
      low:   c.low,
      close: c.close,
    }))
    series.setData(data)
    chartRef.current?.timeScale().fitContent()
  }, [candles])

  // ── Strategy oscillator pane visibility ───────────────────────────────────
  useEffect(() => {
    const hasOscFromOverlay = (overlay?.indicators ?? []).some(i => i.pane === 'oscillator')
    setShowOscillator(hasOscFromOverlay)
  }, [overlay])

  // ── Render strategy overlay (signals + forecast + indicators) ─────────────
  useEffect(() => {
    const priceChart    = chartRef.current
    const oscChart      = oscChartRef.current
    const candleSeries  = candleSeriesRef.current
    const markerApi     = markerApiRef.current
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

    const indicators: ToolVisualizationSeries[] = overlay.indicators ?? []
    const priceIndicators = indicators.filter(ind => ind.pane !== 'oscillator')
    const oscIndicators   = indicators.filter(ind => ind.pane === 'oscillator')

    priceIndicators.forEach((ind, idx) => {
      const color = ind.color ?? _DEFAULT_COLORS[idx % _DEFAULT_COLORS.length]
      const s = priceChart.addSeries(LineSeries, {
        color, lineWidth: 1,
        crosshairMarkerVisible: false,
        lastValueVisible:       true,
        priceLineVisible:       false,
        title: ind.name,
      })
      s.setData(ind.points.map(p => ({ time: toUTCTimestamp(p.timestamp), value: p.value })))
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
          s.setData(ind.points.map(p => ({
            time: toUTCTimestamp(p.timestamp), value: p.value,
            color: p.value >= 0 ? '#26a69a' : '#ef5350',
          })))
          oscSeriesMapRef.current.set(ind.name, s)
        } else {
          const s = oscChart.addSeries(LineSeries, {
            color, lineWidth: 1,
            crosshairMarkerVisible: false,
            lastValueVisible:       false,
            priceLineVisible:       false,
            title: ind.name,
          })
          s.setData(ind.points.map(p => ({ time: toUTCTimestamp(p.timestamp), value: p.value })))
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
      oscChart.timeScale().fitContent()
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
      const lastCandle = candles[candles.length - 1]
      forecastSeries.setData([
        { time: toUTCTimestamp(lastCandle.timestamp), value: lastCandle.close },
        { time: toUTCTimestamp(overlay.forecast.target_timestamp), value: overlay.forecast.target_price },
      ])
    }
  }, [overlay, candles])

  // ── Render artifact price overlay series ──────────────────────────────────
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
        const key = `${artifact.instance_id}.${series.series_id}`
        // series.default_color already carries any user color override (patched in App.tsx).
        // instanceColor (palette) used as fallback for single-series before user picks a color.
        const color = (isSingleSeries && instanceColor) ? instanceColor : series.default_color

        const points = series.values
          .filter(p => p.value !== null && p.timestamp)
          .map(p => ({ time: toUTCTimestamp(p.timestamp) as Time, value: p.value as number }))

        if (points.length === 0) continue

        const s = priceChart.addSeries(LineSeries, {
          color,
          lineWidth:              1,
          crosshairMarkerVisible: false,
          lastValueVisible:       true,
          priceLineVisible:       false,
          title: series.label,
        })
        s.setData(points)
        artifactPriceSeriesMapRef.current.set(key, s)
      }
    }
  }, [indicatorArtifacts, instanceColors])

  // ── Derive counts for header badges ──────────────────────────────────────
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

      {/* Strategy overlay oscillator pane */}
      <div style={{
        ...styles.oscWrapper,
        height:   showOscillator ? 160 : 0,
        overflow: 'hidden',
      }}>
        {showOscillator && <div style={styles.oscLabel}>oscillator</div>}
        <div ref={oscContainerRef} style={styles.oscChart} />
      </div>

      {/* Dynamic indicator artifact oscillator panes — one per tool group with drag splitters */}
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
    overflowY:     'auto' as const,
  },
  header: {
    padding:      '8px 16px',
    fontSize:     '12px',
    color:        '#8892a4',
    fontFamily:   'monospace',
    letterSpacing: '0.04em',
    borderBottom: '1px solid #1a1a2e',
    display:      'flex',
    alignItems:   'center',
    gap:          '12px',
    flexShrink:   0,
  },
  priceChart: {
    flex:      1,
    width:     '100%',
    minHeight: 200,
  },
  oscWrapper: {
    flexShrink:  0,
    borderTop:   '1px solid #1a1a2e',
    position:    'relative' as const,
    transition:  'height 0.15s ease',
  },
  oscLabel: {
    position:      'absolute' as const,
    top:           4,
    left:          8,
    fontSize:      9,
    color:         '#2a2a3e',
    fontFamily:    'monospace',
    letterSpacing: '0.07em',
    pointerEvents: 'none' as const,
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
