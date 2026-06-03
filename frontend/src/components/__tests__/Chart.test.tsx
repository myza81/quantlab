/**
 * Chart.test.tsx — Chart-UX-3C.2.
 *
 * Coverage:
 *  1.  Chart renders without crashing with minimal candle data
 *  2.  OscPane label appears when oscillator artifact provided
 *  3.  Pane splitter rendered for each oscillator group
 *  4.  Dragging splitter down increases pane height
 *  5.  Dragging splitter up enforces minimum pane height (80px)
 *  6.  No splitter when only price-overlay artifacts present
 *  7.  Empty artifact array produces no oscillator panes
 *  8.  subscribeVisibleTimeRangeChange called (time-based sync setup)
 *  9.  subscribeCrosshairMove called when oscillator pane mounted
 * 10.  Two distinct oscillator tool groups render two splitters
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import Chart from '../Chart'
import type { IndicatorArtifactResponse } from '../../types/chartIndicators'

// ResizeObserver is not available in jsdom — polyfill with a proper class so
// `new ResizeObserver(cb)` works as the Chart component expects.
class _MockResizeObserver {
  observe    = vi.fn()
  unobserve  = vi.fn()
  disconnect = vi.fn()
}
vi.stubGlobal('ResizeObserver', _MockResizeObserver)

// ---------------------------------------------------------------------------
// Shared mocks — vi.hoisted ensures these are available before vi.mock() runs
// ---------------------------------------------------------------------------

const mocks = vi.hoisted(() => {
  const subTimeRange   = vi.fn()
  const unsubTimeRange = vi.fn()
  const subCrosshair   = vi.fn()
  const unsubCrosshair = vi.fn()
  const fitContent     = vi.fn()
  const setVisibleRange = vi.fn()
  const getVisibleRange = vi.fn().mockReturnValue(null)
  const setData        = vi.fn()
  const addSeries      = vi.fn()
  const removeSeries   = vi.fn()
  const chartRemove    = vi.fn()
  const applyOptions   = vi.fn()

  function makeTimeScale() {
    return {
      setVisibleRange,
      setVisibleLogicalRange: vi.fn(),
      getVisibleRange,
      subscribeVisibleTimeRangeChange:      subTimeRange,
      unsubscribeVisibleTimeRangeChange:    unsubTimeRange,
      subscribeVisibleLogicalRangeChange:   vi.fn(),
      unsubscribeVisibleLogicalRangeChange: vi.fn(),
      fitContent,
    }
  }

  function makeSeries() {
    return {
      setData,
      applyOptions:    vi.fn(),
      createPriceLine: vi.fn().mockReturnValue({}),
      removePriceLine: vi.fn(),
    }
  }

  function makeChart() {
    return {
      addSeries:               addSeries.mockReturnValue(makeSeries()),
      removeSeries,
      remove:                  chartRemove,
      applyOptions,
      timeScale:               vi.fn().mockReturnValue(makeTimeScale()),
      subscribeCrosshairMove:  subCrosshair,
      unsubscribeCrosshairMove: unsubCrosshair,
      clearCrosshairPosition:  vi.fn(),
      setCrosshairPosition:    vi.fn(),
    }
  }

  return {
    subTimeRange, unsubTimeRange, subCrosshair, unsubCrosshair,
    fitContent, setVisibleRange, getVisibleRange, setData,
    addSeries, removeSeries, chartRemove, applyOptions,
    makeChart, makeTimeScale, makeSeries,
  }
})

vi.mock('lightweight-charts', () => ({
  createChart:         vi.fn().mockImplementation(() => mocks.makeChart()),
  createSeriesMarkers: vi.fn().mockReturnValue({ setMarkers: vi.fn(), detach: vi.fn() }),
  CandlestickSeries:   'CandlestickSeries',
  LineSeries:          'LineSeries',
  HistogramSeries:     'HistogramSeries',
  LineStyle:           { Dashed: 2 },
}))

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeCandles(n = 5) {
  return Array.from({ length: n }, (_, i) => ({
    timestamp: new Date(Date.UTC(2023, 0, 3 + i)).toISOString(),
    open: 100 + i, high: 105 + i, low: 99 + i, close: 102 + i, volume: 1000,
  }))
}

function makeOscArtifact(toolId: string, instanceId: string): IndicatorArtifactResponse {
  return {
    tool_id: toolId, instance_id: instanceId,
    display_name: toolId.toUpperCase(), pane: 'oscillator_pane',
    render_type: 'line', parameters: { period: 14 }, warmup_bars: 0, diagnostics: null,
    series: [{
      series_id: toolId, label: toolId.toUpperCase(),
      pane: 'oscillator_pane', render_type: 'line', default_color: '#a855f7',
      values: [
        { timestamp: '2023-01-03T00:00:00Z', value: 55 },
        { timestamp: '2023-01-04T00:00:00Z', value: 60 },
      ],
    }],
  }
}

function makeOverlayArtifact(toolId: string, instanceId: string): IndicatorArtifactResponse {
  return {
    tool_id: toolId, instance_id: instanceId,
    display_name: toolId.toUpperCase(), pane: 'price_overlay',
    render_type: 'line', parameters: { period: 20 }, warmup_bars: 0, diagnostics: null,
    series: [{
      series_id: toolId, label: toolId.toUpperCase(),
      pane: 'price_overlay', render_type: 'line', default_color: '#f59e0b',
      values: [
        { timestamp: '2023-01-03T00:00:00Z', value: null },
        { timestamp: '2023-01-04T00:00:00Z', value: 101.5 },
      ],
    }],
  }
}

function renderChart(props: Partial<React.ComponentProps<typeof Chart>> = {}) {
  return render(
    <Chart
      candles={makeCandles()}
      symbol="AAPL"
      timeframe="1d"
      {...props}
    />
  )
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Chart', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('1. renders without crashing with minimal candle data', () => {
    expect(() => renderChart()).not.toThrow()
  })

  it('2. OscPane label appears when oscillator artifact provided', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    expect(screen.getByText('RSI')).toBeInTheDocument()
  })

  it('3. pane splitter rendered for each oscillator group', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    expect(screen.getByTestId('pane-splitter')).toBeInTheDocument()
  })

  it('4. dragging splitter down increases pane height', async () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    fireEvent.mouseDown(splitter, { clientY: 100 })
    fireEvent.mouseMove(document, { clientY: 160 })
    fireEvent.mouseUp(document)

    await waitFor(() => {
      const paneEl = splitter.nextElementSibling as HTMLElement
      const h = parseInt(paneEl?.style.height ?? '0', 10)
      expect(h).toBeGreaterThan(130)
    })
  })

  it('5. dragging splitter far up clamps pane height to minimum (80px)', async () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    fireEvent.mouseDown(splitter, { clientY: 200 })
    fireEvent.mouseMove(document, { clientY: 0 })
    fireEvent.mouseUp(document)

    await waitFor(() => {
      const paneEl = splitter.nextElementSibling as HTMLElement
      const h = parseInt(paneEl?.style.height ?? '0', 10)
      expect(h).toBeGreaterThanOrEqual(80)
    })
  })

  it('6. no pane splitter when only price-overlay artifacts present', () => {
    renderChart({ indicatorArtifacts: [makeOverlayArtifact('sma', 'sma_1')] })
    expect(screen.queryByTestId('pane-splitter')).not.toBeInTheDocument()
  })

  it('7. empty artifact array produces no oscillator panes', () => {
    renderChart({ indicatorArtifacts: [] })
    expect(screen.queryByTestId('pane-splitter')).not.toBeInTheDocument()
  })

  it('8. subscribeVisibleTimeRangeChange called during chart setup', () => {
    renderChart()
    // Strategy osc chart sync registers time-range subscription on mount
    expect(mocks.subTimeRange).toHaveBeenCalled()
  })

  it('9. subscribeCrosshairMove called when oscillator pane mounts', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    // OscPane registers crosshair sync once priceChart state is available
    expect(mocks.subCrosshair).toHaveBeenCalled()
  })

  it('10. two distinct oscillator tool groups render two pane splitters', () => {
    const rsi  = makeOscArtifact('rsi', 'rsi_1')
    const macd = makeOscArtifact('macd', 'macd_1')
    renderChart({ indicatorArtifacts: [rsi, macd] })

    const splitters = screen.getAllByTestId('pane-splitter')
    expect(splitters.length).toBe(2)
    expect(screen.getByText('RSI')).toBeInTheDocument()
    expect(screen.getByText('MACD')).toBeInTheDocument()
  })
})
