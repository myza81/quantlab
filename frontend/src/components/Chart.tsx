import { useEffect, useRef } from 'react'
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  createSeriesMarkers,
} from 'lightweight-charts'
import type {
  IChartApi,
  ISeriesApi,
  CandlestickData,
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
}

function toUTCTimestamp(isoString: string): UTCTimestamp {
  return Math.floor(new Date(isoString).getTime() / 1000) as UTCTimestamp
}

// Palette for indicator series that don't specify a color
const _DEFAULT_COLORS = ['#2196f3', '#ff9800', '#9c27b0', '#00bcd4', '#4caf50']

export default function Chart({ candles, symbol, timeframe, overlay }: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const forecastSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  // Track active indicator series by name for lifecycle management
  const indicatorSeriesMapRef = useRef<Map<string, ISeriesApi<'Line'>>>(new Map())

  // Initialise chart once on mount
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      width:  containerRef.current.clientWidth,
      height: containerRef.current.clientHeight || 480,
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
    })

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    })

    const forecastSeries = chart.addSeries(LineSeries, {
      color: '#ffa726',
      lineWidth: 1,
      lineStyle: 2, // dashed
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    forecastSeriesRef.current = forecastSeries

    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        chart.applyOptions({ width, height })
      }
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      indicatorSeriesMapRef.current.clear()
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      forecastSeriesRef.current = null
    }
  }, [])

  // Update candlestick data — also clears overlay on new fetch
  useEffect(() => {
    const series = candleSeriesRef.current
    if (!series) return

    if (candles.length === 0) {
      series.setData([])
      return
    }

    const data: CandlestickData[] = candles.map(c => ({
      time: toUTCTimestamp(c.timestamp),
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }))
    series.setData(data)
    chartRef.current?.timeScale().fitContent()
  }, [candles])

  // Render strategy overlay: signal markers + forecast + indicator lines
  // Runs whenever overlay changes. Removes all previous indicators first.
  useEffect(() => {
    const chart = chartRef.current
    const candleSeries = candleSeriesRef.current
    const forecastSeries = forecastSeriesRef.current
    if (!chart || !candleSeries || !forecastSeries) return

    // --- Remove all existing indicator series ---
    for (const s of indicatorSeriesMapRef.current.values()) {
      chart.removeSeries(s)
    }
    indicatorSeriesMapRef.current.clear()

    // --- Clear signal markers and forecast line ---
    createSeriesMarkers(candleSeries, [])
    forecastSeries.setData([])

    if (!overlay) return

    // --- Render generic indicator series ---
    const indicators: IndicatorSeries[] = overlay.indicators ?? []
    indicators.forEach((ind, idx) => {
      const color = ind.color ?? _DEFAULT_COLORS[idx % _DEFAULT_COLORS.length]
      const lineSeries = chart.addSeries(LineSeries, {
        color,
        lineWidth: 1,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        priceLineVisible: false,
        title: ind.name,
      })
      const data = ind.points.map(p => ({
        time: toUTCTimestamp(p.timestamp),
        value: p.value,
      }))
      lineSeries.setData(data)
      indicatorSeriesMapRef.current.set(ind.name, lineSeries)
    })

    // --- Signal markers ---
    if (overlay.signals.length > 0) {
      const markers: SeriesMarker<UTCTimestamp>[] = overlay.signals.map(sig => ({
        time: toUTCTimestamp(sig.timestamp),
        position: sig.signal_type === 'long' ? 'belowBar' : 'aboveBar',
        color: sig.signal_type === 'long' ? '#26a69a' : '#ef5350',
        shape: sig.signal_type === 'long' ? 'arrowUp' : 'arrowDown',
        text: sig.signal_type.toUpperCase(),
        size: 1,
      }))
      createSeriesMarkers(candleSeries, markers)
    }

    // --- Forecast projection line: last candle → target ---
    if (overlay.forecast && candles.length > 0) {
      const lastCandle = candles[candles.length - 1]
      forecastSeries.setData([
        { time: toUTCTimestamp(lastCandle.timestamp), value: lastCandle.close },
        { time: toUTCTimestamp(overlay.forecast.target_timestamp), value: overlay.forecast.target_price },
      ])
    }
  }, [overlay, candles])

  const signalCount = overlay?.signals.length ?? 0
  const indicatorCount = (overlay?.indicators ?? []).length

  return (
    <div style={styles.wrapper}>
      {candles.length > 0 && (
        <div style={styles.header}>
          <span>{symbol} · {timeframe} · {candles.length} candles</span>
          {indicatorCount > 0 && (
            <span style={styles.badge}>{indicatorCount} indicator{indicatorCount !== 1 ? 's' : ''}</span>
          )}
          {signalCount > 0 && (
            <span style={styles.badge}>{signalCount} signal{signalCount !== 1 ? 's' : ''}</span>
          )}
          {overlay?.forecast && (
            <span style={{
              ...styles.badge,
              color: overlay.forecast.direction === 'long' ? '#26a69a' : '#ef5350',
            }}>
              forecast {overlay.forecast.direction}
            </span>
          )}
        </div>
      )}
      <div ref={containerRef} style={styles.chart} />
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    background: '#0f0f1a',
  },
  header: {
    padding: '8px 16px',
    fontSize: '12px',
    color: '#8892a4',
    fontFamily: 'monospace',
    letterSpacing: '0.04em',
    borderBottom: '1px solid #1a1a2e',
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  chart: {
    width:    '100%',
    flex:     1,
    minHeight: 0,
  },
  badge: {
    fontSize: '11px',
    color: '#ffa726',
    background: '#1a1a2e',
    padding: '2px 8px',
    borderRadius: '4px',
  },
}
