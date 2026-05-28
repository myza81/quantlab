import { useEffect, useRef, useState } from 'react'
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
} from 'lightweight-charts'
import type { OHLCVCandle } from '../api/marketData'
import type { IndicatorSeries } from '../api/strategyRuns'
import type { StrategyOverlay } from '../types/strategy'

interface ChartProps {
  candles: OHLCVCandle[]
  symbol: string
  timeframe: string
  overlay?: StrategyOverlay | null
  onClearStrategyResults?: () => void
}

function toUTCTimestamp(isoString: string): UTCTimestamp {
  return Math.floor(new Date(isoString).getTime() / 1000) as UTCTimestamp
}

const _DEFAULT_COLORS = ['#2196f3', '#ff9800', '#9c27b0', '#00bcd4', '#4caf50']

// Shared chart theme options (reused for both price and oscillator charts)
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

// Series type alias for lifecycle tracking (price-pane line series + oscillator series)
type AnySeriesApi = ISeriesApi<'Line'> | ISeriesApi<'Histogram'>
type ReferenceGuideBinding = {
  series: ISeriesApi<'Line'>
  lines: IPriceLine[]
}

type OscillatorReferenceGuide = {
  id: string
  matches: (series: IndicatorSeries) => boolean
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

export default function Chart({ candles, symbol, timeframe, overlay, onClearStrategyResults }: ChartProps) {
  // Price chart
  const priceContainerRef   = useRef<HTMLDivElement>(null)
  const chartRef            = useRef<IChartApi | null>(null)
  const candleSeriesRef     = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const markerApiRef        = useRef<ISeriesMarkersPluginApi<Time> | null>(null)
  const forecastSeriesRef   = useRef<ISeriesApi<'Line'> | null>(null)
  const priceSeriesMapRef   = useRef<Map<string, ISeriesApi<'Line'>>>(new Map())

  // Oscillator chart
  const oscContainerRef     = useRef<HTMLDivElement>(null)
  const oscChartRef         = useRef<IChartApi | null>(null)
  const oscSeriesMapRef     = useRef<Map<string, AnySeriesApi>>(new Map())
  const oscGuideMapRef      = useRef<Map<string, ReferenceGuideBinding>>(new Map())

  // Show oscillator pane only when there are oscillator-pane series
  const [showOscillator, setShowOscillator] = useState(false)

  // ── Create price chart on mount ────────────────────────────────────────────
  useEffect(() => {
    if (!priceContainerRef.current) return

    const chart = createChart(priceContainerRef.current, {
      ..._CHART_THEME,
      width:  priceContainerRef.current.clientWidth,
      height: priceContainerRef.current.clientHeight || 400,
    })

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor:    '#26a69a',
      downColor:  '#ef5350',
      borderVisible: false,
      wickUpColor:   '#26a69a',
      wickDownColor: '#ef5350',
    })

    const forecastSeries = chart.addSeries(LineSeries, {
      color:                 '#ffa726',
      lineWidth:             1,
      lineStyle:             2,
      crosshairMarkerVisible: false,
      lastValueVisible:      false,
      priceLineVisible:      false,
    })

    const markerApi = createSeriesMarkers(candleSeries, [])

    chartRef.current        = chart
    candleSeriesRef.current = candleSeries
    markerApiRef.current    = markerApi
    forecastSeriesRef.current = forecastSeries

    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        chart.applyOptions({ width, height })
      }
    })
    ro.observe(priceContainerRef.current)

    return () => {
      ro.disconnect()
      priceSeriesMapRef.current.clear()
      markerApiRef.current?.detach()
      chart.remove()
      chartRef.current        = null
      candleSeriesRef.current = null
      markerApiRef.current    = null
      forecastSeriesRef.current = null
    }
  }, [])

  // ── Create oscillator chart on mount ───────────────────────────────────────
  useEffect(() => {
    if (!oscContainerRef.current) return

    const oscChart = createChart(oscContainerRef.current, {
      ..._CHART_THEME,
      width:  oscContainerRef.current.clientWidth,
      height: oscContainerRef.current.clientHeight || 160,
    })

    oscChartRef.current = oscChart

    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        oscChart.applyOptions({ width, height })
      }
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

  // ── Synchronize time scales between price and oscillator charts ────────────
  useEffect(() => {
    const priceChart = chartRef.current
    const oscChart   = oscChartRef.current
    if (!priceChart || !oscChart) return

    let syncing = false

    const syncFromPrice = (range: ReturnType<ReturnType<IChartApi['timeScale']>['getVisibleLogicalRange']>) => {
      if (syncing || !range) return
      syncing = true
      oscChart.timeScale().setVisibleLogicalRange(range)
      syncing = false
    }

    const syncFromOsc = (range: ReturnType<ReturnType<IChartApi['timeScale']>['getVisibleLogicalRange']>) => {
      if (syncing || !range) return
      syncing = true
      priceChart.timeScale().setVisibleLogicalRange(range)
      syncing = false
    }

    priceChart.timeScale().subscribeVisibleLogicalRangeChange(syncFromPrice)
    oscChart.timeScale().subscribeVisibleLogicalRangeChange(syncFromOsc)

    return () => {
      priceChart.timeScale().unsubscribeVisibleLogicalRangeChange(syncFromPrice)
      oscChart.timeScale().unsubscribeVisibleLogicalRangeChange(syncFromOsc)
    }
  }, [])  // runs once after both charts are created

  // ── Update candlestick data ────────────────────────────────────────────────
  useEffect(() => {
    const series = candleSeriesRef.current
    if (!series) return

    if (candles.length === 0) {
      series.setData([])
      return
    }

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

  // ── Render overlay: signals + forecast + indicators ────────────────────────
  // Runs whenever overlay changes. Removes all previous indicators first.
  useEffect(() => {
    const priceChart  = chartRef.current
    const oscChart    = oscChartRef.current
    const candleSeries  = candleSeriesRef.current
    const markerApi     = markerApiRef.current
    const forecastSeries = forecastSeriesRef.current
    if (!priceChart || !candleSeries || !markerApi || !forecastSeries) return

    // ── Remove all existing price-pane indicator series ──
    for (const s of priceSeriesMapRef.current.values()) {
      priceChart.removeSeries(s)
    }
    priceSeriesMapRef.current.clear()

    // ── Remove all existing oscillator series ──
    if (oscChart) {
      clearOscillatorReferenceGuides(oscGuideMapRef.current)
      for (const s of oscSeriesMapRef.current.values()) {
        oscChart.removeSeries(s)
      }
    }
    oscSeriesMapRef.current.clear()

    // ── Clear signal markers and forecast line ──
    markerApi.setMarkers([])
    forecastSeries.setData([])

    if (!overlay) {
      setShowOscillator(false)
      return
    }

    // ── Route indicators by pane ──
    const indicators: IndicatorSeries[] = overlay.indicators ?? []
    const priceIndicators = indicators.filter(ind => ind.pane !== 'oscillator')
    const oscIndicators   = indicators.filter(ind => ind.pane === 'oscillator')

    setShowOscillator(oscIndicators.length > 0)

    // Render price-pane indicators as line series
    priceIndicators.forEach((ind, idx) => {
      const color = ind.color ?? _DEFAULT_COLORS[idx % _DEFAULT_COLORS.length]
      const s = priceChart.addSeries(LineSeries, {
        color,
        lineWidth: 1,
        crosshairMarkerVisible: false,
        lastValueVisible:       false,
        priceLineVisible:       false,
        title: ind.name,
      })
      s.setData(ind.points.map(p => ({
        time:  toUTCTimestamp(p.timestamp),
        value: p.value,
      })))
      priceSeriesMapRef.current.set(ind.name, s)
    })

    // Render oscillator-pane indicators (line or histogram)
    if (oscChart && oscIndicators.length > 0) {
      const renderedGuideIds = new Set<string>()

      oscIndicators.forEach((ind, idx) => {
        const color = ind.color ?? _DEFAULT_COLORS[idx % _DEFAULT_COLORS.length]

        if (ind.kind === 'histogram') {
          const s = oscChart.addSeries(HistogramSeries, {
            priceLineVisible:  false,
            lastValueVisible:  false,
            title: ind.name,
          })
          // Color each histogram bar by sign: green = positive, red = negative
          s.setData(ind.points.map(p => ({
            time:  toUTCTimestamp(p.timestamp),
            value: p.value,
            color: p.value >= 0 ? '#26a69a' : '#ef5350',
          })))
          oscSeriesMapRef.current.set(ind.name, s)
        } else {
          const s = oscChart.addSeries(LineSeries, {
            color,
            lineWidth: 1,
            crosshairMarkerVisible: false,
            lastValueVisible:       false,
            priceLineVisible:       false,
            title: ind.name,
          })
          s.setData(ind.points.map(p => ({
            time:  toUTCTimestamp(p.timestamp),
            value: p.value,
          })))
          oscSeriesMapRef.current.set(ind.name, s)

          for (const guide of _OSCILLATOR_REFERENCE_GUIDES) {
            if (renderedGuideIds.has(guide.id) || !guide.matches(ind)) continue
            const lines = guide.levels.map(level => s.createPriceLine({
              price: level.value,
              color: level.color,
              lineWidth: 1,
              lineStyle: LineStyle.Dashed,
              axisLabelVisible: false,
              title: level.label,
            }))
            oscGuideMapRef.current.set(guide.id, { series: s, lines })
            renderedGuideIds.add(guide.id)
          }
        }
      })

      oscChart.timeScale().fitContent()
    }

    // ── Signal markers ──
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

    // ── Forecast projection line ──
    if (overlay.forecast && candles.length > 0) {
      const lastCandle = candles[candles.length - 1]
      forecastSeries.setData([
        { time: toUTCTimestamp(lastCandle.timestamp), value: lastCandle.close },
        { time: toUTCTimestamp(overlay.forecast.target_timestamp), value: overlay.forecast.target_price },
      ])
    }
  }, [overlay, candles])

  const signalCount    = overlay?.signals.length ?? 0
  const priceIndCount  = (overlay?.indicators ?? []).filter(i => i.pane !== 'oscillator').length
  const oscIndCount    = (overlay?.indicators ?? []).filter(i => i.pane === 'oscillator').length
  const hasStrategyResults = signalCount > 0 || priceIndCount > 0 || oscIndCount > 0 || !!overlay?.forecast

  return (
    <div style={styles.wrapper}>
      {candles.length > 0 && (
        <div style={styles.header}>
          <span>{symbol} · {timeframe} · {candles.length} candles</span>
          {priceIndCount > 0 && (
            <span style={styles.badge}>
              {priceIndCount} overlay{priceIndCount !== 1 ? 's' : ''}
            </span>
          )}
          {oscIndCount > 0 && (
            <span style={{ ...styles.badge, color: '#7e57c2' }}>
              {oscIndCount} oscillator{oscIndCount !== 1 ? 's' : ''}
            </span>
          )}
          {signalCount > 0 && (
            <span style={styles.badge}>
              {signalCount} signal{signalCount !== 1 ? 's' : ''}
            </span>
          )}
          {overlay?.forecast && (
            <span style={{
              ...styles.badge,
              color: overlay.forecast.direction === 'long' ? '#26a69a' : '#ef5350',
            }}>
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
              cursor: hasStrategyResults ? 'pointer' : 'default',
            }}
          >
            Clear Strategy Results
          </button>
        </div>
      )}

      {/* Price chart — always visible */}
      <div ref={priceContainerRef} style={styles.priceChart} />

      {/* Oscillator chart — shown only when oscillator series are present */}
      <div style={{
        ...styles.oscWrapper,
        height:   showOscillator ? 180 : 0,
        overflow: 'hidden',
      }}>
        {showOscillator && (
          <div style={styles.oscLabel}>oscillator</div>
        )}
        <div ref={oscContainerRef} style={styles.oscChart} />
      </div>
    </div>
  )
}

function clearOscillatorReferenceGuides(guides: Map<string, ReferenceGuideBinding>) {
  for (const binding of guides.values()) {
    for (const line of binding.lines) {
      binding.series.removePriceLine(line)
    }
  }
  guides.clear()
}

const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    flex:          1,
    display:       'flex',
    flexDirection: 'column',
    background:    '#0f0f1a',
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
    flex:     1,
    width:    '100%',
    minHeight: 0,
  },
  oscWrapper: {
    flexShrink:   0,
    borderTop:    '1px solid #1a1a2e',
    position:     'relative' as const,
    transition:   'height 0.15s ease',
  },
  oscLabel: {
    position:     'absolute' as const,
    top:          4,
    left:         8,
    fontSize:     9,
    color:        '#2a2a3e',
    fontFamily:   'monospace',
    letterSpacing: '0.07em',
    pointerEvents: 'none' as const,
    zIndex:       1,
  },
  oscChart: {
    width:  '100%',
    height: '100%',
  },
  badge: {
    fontSize:     '11px',
    color:        '#ffa726',
    background:   '#1a1a2e',
    padding:      '2px 8px',
    borderRadius: '4px',
  },
  clearBtn: {
    marginLeft:    'auto',
    background:    '#111827',
    border:        '1px solid #2a2d3e',
    borderRadius:  4,
    color:         '#9aa4b8',
    fontFamily:    'monospace',
    fontSize:      11,
    padding:       '3px 9px',
  },
}
