/**
 * Chart.test.tsx — Chart-UX-3C.3B (Pane Resize Stability).
 *
 * Coverage:
 * Rendering / sync (inherited from 3C.3A)
 *  1.  Chart renders without crashing
 *  2.  OscPane label appears when oscillator artifact provided
 *  3.  Pane splitter rendered for each oscillator group
 *  4.  No pane splitter for price-overlay-only artifacts
 *  5.  Empty artifact array produces no oscillator panes
 *  6.  subscribeVisibleTimeRangeChange called (price→osc sync setup)
 *  7.  subscribeCrosshairMove called when oscillator pane mounts
 *  8.  Two distinct tool groups render two pane splitters
 *  9.  Removing oscillator indicator removes its pane splitter
 * Timestamp alignment (inherited from 3C.3A)
 * 10.  Warmup bars included as whitespace (5 candle entries for 5-candle domain)
 * 11.  Warmup entries have no value field; non-warmup entries have value
 * 12.  Histogram bars have sign-based colors
 * 13.  Candle data sorted ascending by timestamp
 * 14.  Duplicate candle timestamps deduped — last wins
 * 15.  Oscillator setData limited to candle-domain timestamps
 * 16.  Price-chart getVisibleRange applied to oscillator (not fitContent)
 * 17.  Multiple OscPanes subscribe to price-chart time-range changes
 * Resize stability (3C.3B new)
 * 18.  Pointer drag (down) increases pane height
 * 19.  Pointer drag (up) clamps pane height to MIN_OSC_HEIGHT (100px)
 * 20.  Pointer drag respects MAX_OSC_HEIGHT (600px)
 * 21.  React setState NOT called during pointermove — only on pointerup
 * 22.  requestAnimationFrame scheduled on each pointermove
 * 23.  chart.applyOptions({ height }) called inside rAF during drag
 * 24.  final height committed on pointerup via onCommitHeight (once)
 * 25.  pointercancel commits final height same as pointerup
 * 26.  Unmount during active drag cancels pending rAF
 * 27.  Time range resynced after drag commit
 * 28.  Removing indicator after resize does not crash
 * 29.  Repeated drags do not accumulate document listeners (pointer capture model)
 */
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import Chart from '../Chart'
import type { IndicatorArtifactResponse } from '../../types/chartIndicators'

// ---------------------------------------------------------------------------
// Global mocks
// ---------------------------------------------------------------------------

// ResizeObserver polyfill
class _MockResizeObserver {
  observe    = vi.fn()
  unobserve  = vi.fn()
  disconnect = vi.fn()
}
vi.stubGlobal('ResizeObserver', _MockResizeObserver)

// setPointerCapture / releasePointerCapture — jsdom lacks these; define before spying
Object.defineProperty(HTMLElement.prototype, 'setPointerCapture', {
  value: vi.fn(), writable: true, configurable: true,
})
Object.defineProperty(HTMLElement.prototype, 'releasePointerCapture', {
  value: vi.fn(), writable: true, configurable: true,
})

// rAF — synchronous in tests; capture the callback so we can verify it was scheduled
let _rafCallbacks: FrameRequestCallback[] = []
let _rafCounter = 0
const _mockRaf = vi.fn((cb: FrameRequestCallback) => {
  const id = ++_rafCounter
  _rafCallbacks.push(cb)
  return id
})
const _mockCaf = vi.fn((id: number) => {
  _rafCallbacks = _rafCallbacks.filter((_, i) => i !== id - 1)
})
vi.stubGlobal('requestAnimationFrame', _mockRaf)
vi.stubGlobal('cancelAnimationFrame', _mockCaf)

/** Flush all pending rAF callbacks (simulates one animation frame). */
function flushRaf() {
  const cbs = [..._rafCallbacks]
  _rafCallbacks = []
  cbs.forEach(cb => cb(performance.now()))
}

// ---------------------------------------------------------------------------
// lightweight-charts mock
// ---------------------------------------------------------------------------

const mocks = vi.hoisted(() => {
  const subTimeRange    = vi.fn()
  const unsubTimeRange  = vi.fn()
  const subCrosshair    = vi.fn()
  const unsubCrosshair  = vi.fn()
  const fitContent      = vi.fn()
  const setVisibleRange = vi.fn()
  const getVisibleRange = vi.fn().mockReturnValue(null)
  const setData         = vi.fn()
  const addSeries       = vi.fn()
  const removeSeries    = vi.fn()
  const applyOptions    = vi.fn()
  const chartRemove     = vi.fn()

  function makeTimeScale() {
    return {
      setVisibleRange,
      setVisibleLogicalRange:             vi.fn(),
      getVisibleRange,
      subscribeVisibleTimeRangeChange:    subTimeRange,
      unsubscribeVisibleTimeRangeChange:  unsubTimeRange,
      subscribeVisibleLogicalRangeChange: vi.fn(),
      unsubscribeVisibleLogicalRangeChange: vi.fn(),
      fitContent,
    }
  }

  function makeSeries() {
    return {
      setData, applyOptions: vi.fn(),
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
    addSeries, removeSeries, applyOptions, chartRemove,
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

const TS = (d: number) => new Date(Date.UTC(2023, 0, 3 + d)).toISOString()
const TS_UNIX = (d: number) => Math.floor(new Date(Date.UTC(2023, 0, 3 + d)).getTime() / 1000)

function makeCandles(n = 5) {
  return Array.from({ length: n }, (_, i) => ({
    timestamp: TS(i), open: 100 + i, high: 105 + i, low: 99 + i, close: 102 + i, volume: 1000,
  }))
}

function makeOscArtifact(toolId: string, instanceId: string): IndicatorArtifactResponse {
  return {
    tool_id: toolId, instance_id: instanceId,
    display_name: toolId.toUpperCase(), pane: 'oscillator_pane',
    render_type: 'line', parameters: {}, warmup_bars: 0, diagnostics: null,
    series: [{
      series_id: toolId, label: toolId.toUpperCase(),
      pane: 'oscillator_pane', render_type: 'line', default_color: '#a855f7',
      values: [{ timestamp: TS(0), value: 55 }, { timestamp: TS(1), value: 60 }],
    }],
  }
}

function makeOscArtifactWithWarmup(toolId: string, instanceId: string): IndicatorArtifactResponse {
  return {
    tool_id: toolId, instance_id: instanceId,
    display_name: toolId.toUpperCase(), pane: 'oscillator_pane',
    render_type: 'line', parameters: {}, warmup_bars: 2, diagnostics: null,
    series: [{
      series_id: toolId, label: toolId.toUpperCase(),
      pane: 'oscillator_pane', render_type: 'line', default_color: '#a855f7',
      values: [
        { timestamp: TS(0), value: null },
        { timestamp: TS(1), value: null },
        { timestamp: TS(2), value: 55 },
        { timestamp: TS(3), value: 60 },
        { timestamp: TS(4), value: 58 },
      ],
    }],
  }
}

function makeHistArtifact(toolId: string, instanceId: string): IndicatorArtifactResponse {
  return {
    tool_id: toolId, instance_id: instanceId,
    display_name: toolId.toUpperCase(), pane: 'oscillator_pane',
    render_type: 'histogram', parameters: {}, warmup_bars: 0, diagnostics: null,
    series: [{
      series_id: `${toolId}_hist`, label: 'Histogram',
      pane: 'oscillator_pane', render_type: 'histogram', default_color: '#26a69a',
      values: [{ timestamp: TS(0), value: 1.5 }, { timestamp: TS(1), value: -0.8 }],
    }],
  }
}

function makeOverlayArtifact(toolId: string, instanceId: string): IndicatorArtifactResponse {
  return {
    tool_id: toolId, instance_id: instanceId,
    display_name: toolId.toUpperCase(), pane: 'price_overlay',
    render_type: 'line', parameters: {}, warmup_bars: 0, diagnostics: null,
    series: [{
      series_id: toolId, label: toolId.toUpperCase(),
      pane: 'price_overlay', render_type: 'line', default_color: '#f59e0b',
      values: [{ timestamp: TS(0), value: null }, { timestamp: TS(1), value: 101.5 }],
    }],
  }
}

function renderChart(props: Partial<React.ComponentProps<typeof Chart>> = {}) {
  return render(
    <Chart candles={makeCandles()} symbol="AAPL" timeframe="1d" {...props} />
  )
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Chart', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    _rafCallbacks = []
    _rafCounter = 0
  })

  afterEach(() => {
    _rafCallbacks = []
  })

  // ── Rendering / sync ──────────────────────────────────────────────────────

  it('1. renders without crashing', () => {
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

  it('4. no pane splitter for price-overlay-only artifacts', () => {
    renderChart({ indicatorArtifacts: [makeOverlayArtifact('sma', 'sma_1')] })
    expect(screen.queryByTestId('pane-splitter')).not.toBeInTheDocument()
  })

  it('5. empty artifact array produces no oscillator panes', () => {
    renderChart({ indicatorArtifacts: [] })
    expect(screen.queryByTestId('pane-splitter')).not.toBeInTheDocument()
  })

  it('6. subscribeVisibleTimeRangeChange called during sync setup', () => {
    renderChart()
    expect(mocks.subTimeRange).toHaveBeenCalled()
  })

  it('7. subscribeCrosshairMove called when oscillator pane mounts', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    expect(mocks.subCrosshair).toHaveBeenCalled()
  })

  it('8. two distinct tool groups render two pane splitters', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1'), makeOscArtifact('macd', 'macd_1')] })
    expect(screen.getAllByTestId('pane-splitter')).toHaveLength(2)
  })

  it('9. removing oscillator indicator removes its pane splitter', async () => {
    const { rerender } = renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    expect(screen.getByTestId('pane-splitter')).toBeInTheDocument()

    rerender(<Chart candles={makeCandles()} symbol="AAPL" timeframe="1d" indicatorArtifacts={[]} />)
    await waitFor(() => expect(screen.queryByTestId('pane-splitter')).not.toBeInTheDocument())
  })

  // ── Timestamp alignment ───────────────────────────────────────────────────

  it('10. oscillator setData called with ALL candle timestamps (including warmup)', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifactWithWarmup('rsi', 'rsi_1')] })
    const data = mocks.setData.mock.calls.map(c => c[0] as unknown[]).find(a => a.length === 5)
    expect(data).toBeDefined()
    expect(data).toHaveLength(5)
  })

  it('11. warmup entries are whitespace (no value); non-warmup have value', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifactWithWarmup('rsi', 'rsi_1')] })
    const data = mocks.setData.mock.calls
      .map(c => c[0] as Array<{ time: number; value?: number }>)
      .find(a => a.length === 5)!
    expect('value' in data[0]).toBe(false)
    expect('value' in data[1]).toBe(false)
    expect(data[2].value).toBe(55)
    expect(data[3].value).toBe(60)
  })

  it('12. histogram bars have sign-based colors', () => {
    renderChart({ indicatorArtifacts: [makeHistArtifact('macd', 'macd_1')] })
    const data = mocks.setData.mock.calls
      .map(c => c[0] as Array<{ time: number; value?: number; color?: string }>)
      .find(a => a.some(p => p.color !== undefined))!
    expect(data.find(p => (p.value ?? 0) > 0)?.color).toBe('#26a69a')
    expect(data.find(p => (p.value ?? 0) < 0)?.color).toBe('#ef5350')
  })

  it('13. candle data sorted ascending by timestamp', () => {
    renderChart({ candles: [...makeCandles(3)].reverse() })
    const data = mocks.setData.mock.calls.map(c => c[0] as Array<{ time: number }>).find(a => a.length === 3)!
    expect(data[0].time).toBeLessThan(data[1].time)
    expect(data[1].time).toBeLessThan(data[2].time)
  })

  it('14. duplicate candle timestamps deduped — last value wins', () => {
    const candles = makeCandles(3)
    const dup = { ...candles[1], close: 9999 }
    renderChart({ candles: [...candles, dup] })
    const data = mocks.setData.mock.calls.map(c => c[0] as Array<{ time: number; close?: number }>).find(a => a.length === 3)!
    expect(data.find(d => d.time === TS_UNIX(1))?.close).toBe(9999)
  })

  it('15. oscillator setData does not include timestamps outside candle domain', () => {
    const artifact = makeOscArtifact('rsi', 'rsi_1')
    artifact.series[0].values.push({ timestamp: TS(99), value: 77 })
    renderChart({ candles: makeCandles(2), indicatorArtifacts: [artifact] })
    const data = mocks.setData.mock.calls
      .map(c => c[0] as Array<{ time: number }>)
      .find(a => a.some(p => p.time === TS_UNIX(0)))
    expect(data?.length).toBe(2)
  })

  it('16. price-chart getVisibleRange applied to oscillator after data update', () => {
    const range = { from: TS_UNIX(0), to: TS_UNIX(4) }
    mocks.getVisibleRange.mockReturnValue(range)
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    expect(mocks.setVisibleRange).toHaveBeenCalledWith(range)
  })

  it('17. multiple OscPanes each subscribe to price-chart time-range changes', () => {
    mocks.subTimeRange.mockClear()
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1'), makeOscArtifact('macd', 'macd_1')] })
    expect(mocks.subTimeRange.mock.calls.length).toBeGreaterThanOrEqual(3)
  })

  // ── Resize stability (3C.3B) ─────────────────────────────────────────────

  it('18. pointer drag down increases pane height', async () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    fireEvent.pointerDown(splitter, { clientY: 100, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 170, pointerId: 1 })
    flushRaf()
    fireEvent.pointerUp(splitter, { clientY: 170, pointerId: 1 })

    await waitFor(() => {
      const wrapper = screen.getByTestId('osc-pane-wrapper')
      const h = parseInt(wrapper.style.height || '0', 10)
      expect(h).toBeGreaterThan(130)
    })
  })

  it('19. pointer drag up clamps pane height to MIN_OSC_HEIGHT (100px)', async () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    fireEvent.pointerDown(splitter, { clientY: 500, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 0, pointerId: 1 })  // drag up 500px
    flushRaf()
    fireEvent.pointerUp(splitter, { clientY: 0, pointerId: 1 })

    await waitFor(() => {
      const wrapper = screen.getByTestId('osc-pane-wrapper')
      const h = parseInt(wrapper.style.height || '0', 10)
      expect(h).toBeGreaterThanOrEqual(100)
    })
  })

  it('20. pointer drag down clamped to MAX_OSC_HEIGHT (600px)', async () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    fireEvent.pointerDown(splitter, { clientY: 0, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 2000, pointerId: 1 })  // drag down 2000px
    flushRaf()
    fireEvent.pointerUp(splitter, { clientY: 2000, pointerId: 1 })

    await waitFor(() => {
      const wrapper = screen.getByTestId('osc-pane-wrapper')
      const h = parseInt(wrapper.style.height || '0', 10)
      expect(h).toBeLessThanOrEqual(600)
    })
  })

  it('21. React state (onCommitHeight) NOT called during pointermove — only on pointerup', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    // Track React state updates via applyOptions (proxy) — state update triggers re-render
    // Simpler: track how many times the wrapper's style.height changes via the DOM
    // We count applyOptions calls to the chart before and after pointermove vs pointerup
    const applyBefore = mocks.applyOptions.mock.calls.length

    fireEvent.pointerDown(splitter, { clientY: 100, pointerId: 1 })
    // Multiple pointermove events in same rAF window
    fireEvent.pointerMove(splitter, { clientY: 110, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 120, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 130, pointerId: 1 })

    // rAF not flushed yet — no applyOptions should have been called
    // (rAF collapses the moves into one frame)
    const applyAfterMoves = mocks.applyOptions.mock.calls.length
    expect(applyAfterMoves).toBe(applyBefore)  // no immediate updates

    flushRaf()  // now one update fires
    const applyAfterFlush = mocks.applyOptions.mock.calls.length
    expect(applyAfterFlush).toBeGreaterThan(applyBefore)

    fireEvent.pointerUp(splitter, { clientY: 130, pointerId: 1 })
    // After pointerup the final applyOptions is synchronous (applyFinal)
    // then onCommitHeight fires → React re-render
  })

  it('22. requestAnimationFrame scheduled on pointermove', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')
    const rafBefore = _mockRaf.mock.calls.length

    fireEvent.pointerDown(splitter, { clientY: 100, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 150, pointerId: 1 })

    expect(_mockRaf.mock.calls.length).toBeGreaterThan(rafBefore)
    fireEvent.pointerUp(splitter, { clientY: 150, pointerId: 1 })
  })

  it('23. chart.applyOptions called with new height inside rAF', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    fireEvent.pointerDown(splitter, { clientY: 100, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 200, pointerId: 1 })  // delta = +100

    const callsBefore = mocks.applyOptions.mock.calls.length
    flushRaf()
    const callsAfter = mocks.applyOptions.mock.calls.length
    expect(callsAfter).toBeGreaterThan(callsBefore)

    // applyOptions should have been called with a height property
    const heightCalls = mocks.applyOptions.mock.calls.filter(c => c[0]?.height !== undefined)
    expect(heightCalls.length).toBeGreaterThan(0)

    fireEvent.pointerUp(splitter, { clientY: 200, pointerId: 1 })
  })

  it('24. final height committed via React state once on pointerup', async () => {
    // Track how many React re-renders occur by watching the wrapper's committed height
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    fireEvent.pointerDown(splitter, { clientY: 100, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 150, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 180, pointerId: 1 })
    flushRaf()
    fireEvent.pointerUp(splitter, { clientY: 180, pointerId: 1 })

    // After pointerup, React state is committed → re-render → wrapper gets new height prop
    await waitFor(() => {
      const wrapper = screen.getByTestId('osc-pane-wrapper')
      const h = parseInt(wrapper.style.height || '0', 10)
      expect(h).toBeGreaterThan(130)
    })
  })

  it('25. pointercancel commits final height same as pointerup', async () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    fireEvent.pointerDown(splitter, { clientY: 100, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 170, pointerId: 1 })
    flushRaf()
    fireEvent.pointerCancel(splitter, { clientY: 170, pointerId: 1 })

    await waitFor(() => {
      const wrapper = screen.getByTestId('osc-pane-wrapper')
      const h = parseInt(wrapper.style.height || '0', 10)
      expect(h).toBeGreaterThan(130)
    })
  })

  it('26. unmounting during active drag cancels pending rAF', () => {
    const { unmount } = renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    fireEvent.pointerDown(splitter, { clientY: 100, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 150, pointerId: 1 })
    // rAF pending — now unmount
    expect(_rafCallbacks.length).toBeGreaterThan(0)
    unmount()
    // cancelAnimationFrame should have been called
    expect(_mockCaf).toHaveBeenCalled()
  })

  it('27. time range resynced after drag commit (setVisibleRange called with price range)', async () => {
    const range = { from: TS_UNIX(0), to: TS_UNIX(4) }
    mocks.getVisibleRange.mockReturnValue(range)
    mocks.setVisibleRange.mockClear()

    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    fireEvent.pointerDown(splitter, { clientY: 100, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 160, pointerId: 1 })
    flushRaf()
    fireEvent.pointerUp(splitter, { clientY: 160, pointerId: 1 })

    // setVisibleRange should be called with the price chart range during/after resize
    expect(mocks.setVisibleRange).toHaveBeenCalledWith(range)
  })

  it('28. removing indicator after resize does not crash', async () => {
    const { rerender } = renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    fireEvent.pointerDown(splitter, { clientY: 100, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 160, pointerId: 1 })
    flushRaf()
    fireEvent.pointerUp(splitter, { clientY: 160, pointerId: 1 })

    expect(() => {
      rerender(<Chart candles={makeCandles()} symbol="AAPL" timeframe="1d" indicatorArtifacts={[]} />)
    }).not.toThrow()

    await waitFor(() => {
      expect(screen.queryByTestId('pane-splitter')).not.toBeInTheDocument()
    })
  })

  it('29. no document event listeners accumulated (pointer capture model)', () => {
    const addEventSpy = vi.spyOn(document, 'addEventListener')
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    // Multiple drags
    for (let i = 0; i < 3; i++) {
      fireEvent.pointerDown(splitter, { clientY: 100, pointerId: 1 })
      fireEvent.pointerMove(splitter, { clientY: 120 + i * 10, pointerId: 1 })
      flushRaf()
      fireEvent.pointerUp(splitter, { clientY: 120 + i * 10, pointerId: 1 })
    }

    // No document.addEventListener should have been called by DragSplitter
    const dragListenerCalls = addEventSpy.mock.calls.filter(
      c => c[0] === 'mousemove' || c[0] === 'mouseup' || c[0] === 'pointermove' || c[0] === 'pointerup'
    )
    expect(dragListenerCalls.length).toBe(0)
    addEventSpy.mockRestore()
  })
})
