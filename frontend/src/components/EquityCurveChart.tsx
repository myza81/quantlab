/**
 * EquityCurveChart — renders equity and drawdown curves using lightweight-charts.
 *
 * Two stacked chart instances:
 *   Top:    equity line (absolute value)
 *   Bottom: drawdown % line (0 = no drawdown; higher = worse)
 */
import { useEffect, useRef } from 'react'
import { createChart, LineSeries } from 'lightweight-charts'
import type { IChartApi, ISeriesApi, LineData, UTCTimestamp } from 'lightweight-charts'
import type { BacktestEquityRecord, BacktestDrawdownRecord } from '../types/backtestRuns'

interface Props {
  equityCurve:   BacktestEquityRecord[]
  drawdownCurve: BacktestDrawdownRecord[]
}

function toTS(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp
}

const BASE_OPTS = {
  layout:          { background: { color: '#0f0f1a' }, textColor: '#d1d4dc' },
  grid:            { vertLines: { color: '#1a1a2e' }, horzLines: { color: '#1a1a2e' } },
  crosshair:       { mode: 1 as const },
  rightPriceScale: { borderColor: '#2a2d3e' },
  timeScale:       { borderColor: '#2a2d3e', timeVisible: true, secondsVisible: false },
}

export function EquityCurveChart({ equityCurve, drawdownCurve }: Props) {
  const equityRef   = useRef<HTMLDivElement>(null)
  const drawdownRef = useRef<HTMLDivElement>(null)
  const chartEq     = useRef<IChartApi | null>(null)
  const chartDd     = useRef<IChartApi | null>(null)
  const seriesEq    = useRef<ISeriesApi<'Line'> | null>(null)
  const seriesDd    = useRef<ISeriesApi<'Line'> | null>(null)

  const eqPoints = equityCurve.filter(p => p.timestamp !== null)
  const ddPoints = drawdownCurve.filter(p => p.timestamp !== null)

  // Mount: create charts and series once
  useEffect(() => {
    if (!equityRef.current || !drawdownRef.current) return

    const eq = createChart(equityRef.current, {
      ...BASE_OPTS,
      width:  equityRef.current.clientWidth,
      height: equityRef.current.clientHeight || 220,
    })
    const eqS = eq.addSeries(LineSeries, {
      color: '#26a69a', lineWidth: 2,
      crosshairMarkerVisible: true, lastValueVisible: true,
      priceLineVisible: true, title: 'Equity',
    })
    chartEq.current = eq
    seriesEq.current = eqS

    const dd = createChart(drawdownRef.current, {
      ...BASE_OPTS,
      width:  drawdownRef.current.clientWidth,
      height: drawdownRef.current.clientHeight || 110,
    })
    const ddS = dd.addSeries(LineSeries, {
      color: '#ef5350', lineWidth: 1,
      crosshairMarkerVisible: true, lastValueVisible: true,
      priceLineVisible: false, title: 'Drawdown %',
    })
    chartDd.current = dd
    seriesDd.current = ddS

    // Sync time scales — guard against empty drawdown chart
    eq.timeScale().subscribeVisibleTimeRangeChange(range => {
      if (range) try { dd.timeScale().setVisibleRange(range) } catch { /* no data yet */ }
    })

    // Resize observers
    const roEq = new ResizeObserver(entries => {
      for (const e of entries)
        eq.applyOptions({ width: e.contentRect.width, height: e.contentRect.height })
    })
    const roDd = new ResizeObserver(entries => {
      for (const e of entries)
        dd.applyOptions({ width: e.contentRect.width, height: e.contentRect.height })
    })
    roEq.observe(equityRef.current)
    roDd.observe(drawdownRef.current)

    return () => {
      roEq.disconnect()
      roDd.disconnect()
      eq.remove()
      dd.remove()
      chartEq.current  = null
      chartDd.current  = null
      seriesEq.current = null
      seriesDd.current = null
    }
  }, [])

  // Update data whenever curves change
  useEffect(() => {
    if (seriesEq.current && eqPoints.length > 0) {
      const data: LineData[] = eqPoints.map(p => ({
        time:  toTS(p.timestamp!),
        value: p.equity,
      }))
      seriesEq.current.setData(data)
      chartEq.current?.timeScale().fitContent()
    }

    if (seriesDd.current && ddPoints.length > 0) {
      const data: LineData[] = ddPoints.map(p => ({
        time:  toTS(p.timestamp!),
        value: p.drawdown_pct,
      }))
      seriesDd.current.setData(data)
    }
  }, [equityCurve, drawdownCurve])

  const hasData = eqPoints.length > 0

  return (
    <div style={s.wrapper}>
      <div style={s.chartSection}>
        <div style={s.label}>Equity Curve</div>
        {hasData
          ? <div ref={equityRef} style={s.equityChart} />
          : <div style={s.noData}>No timestamped equity data available.</div>}
      </div>
      <div style={s.chartSection}>
        <div style={s.label}>Drawdown %</div>
        {hasData && <div ref={drawdownRef} style={s.drawdownChart} />}
      </div>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  wrapper:       { display: 'flex', flexDirection: 'column', gap: 8 },
  chartSection:  { display: 'flex', flexDirection: 'column', gap: 4 },
  label:         { fontSize: 11, color: '#4a5568', fontFamily: 'monospace', letterSpacing: '0.05em' },
  equityChart:   { width: '100%', height: 220 },
  drawdownChart: { width: '100%', height: 110 },
  noData:        { color: '#4a5568', fontSize: 12, padding: '16px 0' },
}
