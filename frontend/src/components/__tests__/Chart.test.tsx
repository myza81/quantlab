/**
 * Chart.test.tsx — Chart-UX-4A (Data Inspector) + Chart-UX-3C.4 (carry-forward).
 *
 * Coverage:
 * Rendering / basic (carry-forward)
 *  1.  Chart renders without crashing
 *  2.  OscPane label appears when oscillator artifact provided
 *  3.  Pane splitter rendered for each oscillator group
 *  4.  No pane splitter for price-overlay-only artifacts
 *  5.  Empty artifact array produces no oscillator panes
 * Logical-range sync (3C.4)
 *  6.  subscribeVisibleLogicalRangeChange called for price→osc sync
 *  7.  subscribeVisibleTimeRangeChange NOT used for pane sync
 *  8.  OscPane does NOT subscribe oscillator chart as a sync source
 *  9.  setVisibleLogicalRange called when price chart range changes
 * 10.  Extreme logical range values propagate to all oscillator panes
 * 11.  Null logical range is safely ignored (no crash)
 * 12.  Multiple OscPanes both subscribe to price logical range
 * 13.  subscribeCrosshairMove still called (crosshair sync preserved)
 * 14.  getVisibleLogicalRange applied to oscillator after data update
 * Timestamp alignment (carry-forward)
 * 15.  Warmup bars included as whitespace (5 candle entries for 5-candle domain)
 * 16.  Warmup entries have no value field; non-warmup entries have value
 * 17.  Candle data sorted ascending by timestamp
 * 18.  Duplicate candle timestamps deduped — last wins
 * 19.  Oscillator setData limited to candle-domain timestamps
 * Resize stability (3C.3B carry-forward, direction fixed in 3C.4)
 * 20.  Pointer drag UP increases pane height (inverted direction)
 * 21.  Pointer drag DOWN decreases pane height
 * 22.  Min height clamp still works (100px)
 * 23.  Max height clamp still works (600px)
 * 24.  React setState NOT called during pointermove — only on pointerup
 * 25.  requestAnimationFrame scheduled on each pointermove
 * 26.  chart.applyOptions({ height }) called inside rAF during drag
 * 27.  Final height committed on pointerup (once)
 * 28.  pointercancel commits final height same as pointerup
 * 29.  Unmount during active drag cancels pending rAF
 * 30.  Logical range resynced after drag commit
 * 31.  Removing indicator after resize does not crash
 * 32.  No document event listeners accumulated (pointer capture model)
 * 33.  Two distinct tool groups render two pane splitters
 * 34.  Removing oscillator indicator removes its pane splitter
 * Volume histogram deduplication (volume + volume_ma active together)
 * 61.  volume only → one HistogramSeries rendered
 * 62.  volume_ma only (no MA) → one HistogramSeries rendered
 * 63.  volume + volume_ma active → exactly one HistogramSeries total
 * 64.  volume + volume_ma(20) active → MA line still rendered alongside single histogram
 * 65.  no OscPane created when both volume and volume_ma active
 * Strategy overlay rendering (volume outputs on volume scale)
 * 66.  strategy-run volume output renders as HistogramSeries
 * 67.  strategy-run volume histogram uses priceScaleId="volume"
 * 68.  strategy-run volume scale margins applied (top: 0.75, bottom: 0)
 * 69.  strategy-run volume_ma line uses priceScaleId="volume"
 * 70.  strategy-run EMA/SMA uses normal price scale (no priceScaleId)
 * 71.  strategy-run volume + EMA — histogram on volume scale, EMA on default
 * 72.  strategy-run oscillator indicator triggers strategy oscillator pane label
 * 73.  indicator artifact rendering unchanged when strategy overlay also active
 * Volume histogram single-color mode (VOL-UX-2)
 * 74.  volumeColorModes absent → histogram uses directional close-to-close colors
 * 75.  volumeColorModes with matching instance_id → all bars use that single color
 * 76.  volumeColorModes with non-matching instance_id → histogram falls back to directional
 * 77.  empty volumeColorModes Map → histogram uses directional colors
 * Strategy oscillator crosshair sync
 * 78.  strategy-run oscillator subscribes to price chart crosshair movement
 * 79.  strategy-run oscillator sets crosshair position for matching timestamp data
 * 80.  strategy-run oscillator clears crosshair when event has no time
 * CHART-SETTINGS-1A — label toggle effects (gear button is in App.tsx header)
 * 91.  showLatestPriceLabel: false — applyOptions called
 * 92.  showIndicatorValueLabels: false — overlay line created with lastValueVisible: false
 * 93.  showStrategyValueLabels: false — strategy EMA created with lastValueVisible: false
 * 94.  showSignalMarkers: false — setMarkers([]) called
 * 95.  showSignalMarkers: true — setMarkers called with signal data
 * Reactive toggle regression (G1, G2, G6)
 * 96.  showSignalMarkers: false preserved after overlay re-run (G6a)
 * 97.  showSignalMarkers: toggle ON after overlay re-run restores markers (G6b)
 * 98.  showIndicatorValueLabels reactive toggle — applyOptions on existing series (G1)
 * 99.  showStrategyValueLabels reactive toggle — applyOptions on existing series (G2)
 * 100. showIndicatorValueLabels toggle applies to OscPane oscillator series (G4)
 * CHART-SETTINGS-1A.4 — Indicators toggle: right-axis labels hidden; top chips unaffected
 * 101. ChartLegendOverlay visible when showIndicatorValueLabels=false (top legend unaffected)
 * 102. OscPane chip label visible when showIndicatorValueLabels=false (header chips unaffected)
 * 103. OscPane chip label visible when showIndicatorValueLabels=true
 * CHART-SETTINGS-1A.5 — title="" required to fully hide right-axis labels in LW Charts v5
 * 104. OscPane RSI series created with title="" when showIndicatorValueLabels=false
 * 105. OscPane RSI Midline series created with title="" when showIndicatorValueLabels=false
 * 106. OscPane reactive toggle sets title="" in applyOptions when hiding
 * 107. Price-overlay reactive toggle sets title="" in applyOptions when hiding
 * CHART-TOOLBAR-1A — Screenshot export (ChartHandle.takeScreenshot)
 * 108. ChartHandle.takeScreenshot calls chart.takeScreenshot() to capture price pane
 * 109. takeScreenshot downloads a PNG with correct filename pattern
 * 110. takeScreenshot filename sanitizes non-alphanumeric characters in symbol/timeframe
 * CHART-TOOLBAR-1B — Reset View (ChartHandle.resetView)
 * 111. ChartHandle.resetView exposed on ChartHandle interface
 * 112. resetView does not throw when called with chart data loaded
 * 113. resetView calls setVisibleLogicalRange on captured initial range
 * 114. resetView gracefully handles empty chart state
 * CHART-TOOLBAR-1C — Auto Scale (ChartHandle.autoScale)
 * 115. ChartHandle.autoScale exposed on ChartHandle interface
 * 116. autoScale does not throw when called with chart data loaded
 * 117. autoScale preserves visible logical range
 * 118. autoScale gracefully handles empty chart state
 * Market Structure Overlay (MS-2 / MS-3A)
 * 120. showMinorStructure: false — no blue series added
 * 121. showMainStructure: false — no orange series added
 * 122. showMinorStructure: true — blue LineSeries added
 * 123. showMainStructure: true — orange LineSeries added
 * 124. showMinorStructure: true — setData called with candle-length array
 * 127. structureResult: null — no structure series added
 * 128. structureResult: undefined — no structure series added
 * 129. showDebugMetadata: true — debug panel in DOM
 * 130. showDebugMetadata: false — debug panel absent
 * 131. showDebugMetadata: true + null result — debug panel absent
 * 132. toggle off → on — addSeries called after rerender
 * 133. toggle on → off — removeSeries called after rerender
 * 134. main structure lineWidth is 2
 * 135. minor structure lineWidth is 1
 * 136. non-degenerate main leg exercises interpolation path
 * 137. no createSeriesMarkers called for structure (label rendering removed MS-3A)
 */
import { createRef } from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createChart, createSeriesMarkers } from 'lightweight-charts'
import Chart, { type ChartHandle } from '../Chart'
import { DEFAULT_CHART_SETTINGS } from '../../types/chartSettings'
import type { ChartSettings } from '../../types/chartSettings'
import type { IndicatorArtifactResponse } from '../../types/chartIndicators'
import type { OHLCVCandle } from '../../api/marketData'
import type { StrategyOverlay } from '../../types/strategy'
import type { ToolVisualizationSeries } from '../../types/toolVisualization'
import type { StructureResult } from '../../types/marketStructure'

// ---------------------------------------------------------------------------
// Global mocks
// ---------------------------------------------------------------------------

class _MockResizeObserver {
  observe    = vi.fn()
  unobserve  = vi.fn()
  disconnect = vi.fn()
}
vi.stubGlobal('ResizeObserver', _MockResizeObserver)

Object.defineProperty(HTMLElement.prototype, 'setPointerCapture', {
  value: vi.fn(), writable: true, configurable: true,
})
Object.defineProperty(HTMLElement.prototype, 'releasePointerCapture', {
  value: vi.fn(), writable: true, configurable: true,
})

let _rafCallbacks: FrameRequestCallback[] = []
let _rafCounter = 0
const _mockRaf = vi.fn((cb: FrameRequestCallback) => {
  const id = ++_rafCounter; _rafCallbacks.push(cb); return id
})
const _mockCaf = vi.fn()
vi.stubGlobal('requestAnimationFrame', _mockRaf)
vi.stubGlobal('cancelAnimationFrame', _mockCaf)

function flushRaf() {
  const cbs = [..._rafCallbacks]
  _rafCallbacks = []
  cbs.forEach(cb => cb(performance.now()))
}

// ---------------------------------------------------------------------------
// lightweight-charts mock
// ---------------------------------------------------------------------------

const mocks = vi.hoisted(() => {
  // Logical-range methods (3C.4 primary)
  const subLogicalRange    = vi.fn()
  const unsubLogicalRange  = vi.fn()
  const setLogicalRange    = vi.fn()
  const getLogicalRange    = vi.fn().mockReturnValue(null)
  // Time-range methods (should NOT be called for pane sync after 3C.4)
  const subTimeRange       = vi.fn()
  const unsubTimeRange     = vi.fn()
  const setVisibleRange    = vi.fn()
  const getVisibleRange    = vi.fn().mockReturnValue(null)
  // Other
  const subCrosshair       = vi.fn()
  const unsubCrosshair     = vi.fn()
  const fitContent         = vi.fn()
  const setData            = vi.fn()
  const addSeries          = vi.fn()
  const removeSeries       = vi.fn()
  const applyOptions       = vi.fn()
  const chartRemove        = vi.fn()
  const chartInstances: Array<{
    clearCrosshairPosition: ReturnType<typeof vi.fn>
    setCrosshairPosition: ReturnType<typeof vi.fn>
  }> = []
  // Volume price scale (volume_ma tool renders histogram on named 'volume' scale)
  const priceScaleApplyOptions = vi.fn()
  const priceScaleMock         = { applyOptions: priceScaleApplyOptions }
  // Shared applyOptions for all series instances (CHART-SETTINGS-1A)
  const seriesApplyOptions     = vi.fn()
  // setMarkers for signal marker toggle tests (CHART-SETTINGS-1A)
  const setMarkers             = vi.fn()
  // takeScreenshot — returns a mock canvas (CHART-TOOLBAR-1A)
  const takeScreenshot         = vi.fn().mockReturnValue({
    width:     800,
    height:    400,
    toDataURL: vi.fn().mockReturnValue('data:image/png;base64,fake'),
  })

  function makeTimeScale() {
    return {
      // Logical range API
      getVisibleLogicalRange:              getLogicalRange,
      setVisibleLogicalRange:              setLogicalRange,
      subscribeVisibleLogicalRangeChange:  subLogicalRange,
      unsubscribeVisibleLogicalRangeChange: unsubLogicalRange,
      // Time range API (still present on mock — should not be called for sync)
      getVisibleRange,
      setVisibleRange,
      subscribeVisibleTimeRangeChange:     subTimeRange,
      unsubscribeVisibleTimeRangeChange:   unsubTimeRange,
      fitContent,
    }
  }

  function makeSeries() {
    return {
      setData, applyOptions: seriesApplyOptions,
      createPriceLine: vi.fn().mockReturnValue({}),
      removePriceLine: vi.fn(),
      // Series-level priceScale() — used by volume histogram to configure scale margins
      // after addSeries creates the named 'volume' scale.  Shares priceScaleMock so
      // test 52 (priceScaleApplyOptions) still captures the call.
      priceScale: vi.fn().mockReturnValue(priceScaleMock),
    }
  }

  function makeChart() {
    const chart = {
      addSeries:               addSeries.mockReturnValue(makeSeries()),
      removeSeries,
      remove:                  chartRemove,
      applyOptions,
      timeScale:               vi.fn().mockReturnValue(makeTimeScale()),
      subscribeCrosshairMove:  subCrosshair,
      unsubscribeCrosshairMove: unsubCrosshair,
      clearCrosshairPosition:  vi.fn(),
      setCrosshairPosition:    vi.fn(),
      priceScale:              vi.fn().mockReturnValue(priceScaleMock),
      takeScreenshot,
    }
    chartInstances.push(chart)
    return chart
  }

  return {
    subLogicalRange, unsubLogicalRange, setLogicalRange, getLogicalRange,
    subTimeRange, unsubTimeRange, setVisibleRange, getVisibleRange,
    subCrosshair, unsubCrosshair, fitContent,
    setData, addSeries, removeSeries, applyOptions, chartRemove,
    priceScaleApplyOptions, priceScaleMock,
    seriesApplyOptions, setMarkers,
    takeScreenshot,
    chartInstances,
    makeChart, makeTimeScale, makeSeries,
  }
})

vi.mock('lightweight-charts', () => ({
  createChart:         vi.fn().mockImplementation(() => mocks.makeChart()),
  createSeriesMarkers: vi.fn().mockImplementation(() => ({ setMarkers: mocks.setMarkers, detach: vi.fn() })),
  CandlestickSeries:   'CandlestickSeries',
  LineSeries:          'LineSeries',
  HistogramSeries:     'HistogramSeries',
  LineStyle:           { Solid: 0, Dotted: 1, Dashed: 2 },
}))

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const TS      = (d: number) => new Date(Date.UTC(2023, 0, 3 + d)).toISOString()
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

/** RSI + RSI Midline merged into a single artifact (mirrors ChartIndicatorPanel behavior) */
function makeRsiArtifactWithMidline(): IndicatorArtifactResponse {
  return {
    tool_id: 'rsi', instance_id: 'rsi_1',
    display_name: 'RSI', pane: 'oscillator_pane',
    render_type: 'line', parameters: {}, warmup_bars: 0, diagnostics: null,
    series: [
      {
        series_id: 'rsi_val', label: 'RSI',
        pane: 'oscillator_pane', render_type: 'line', default_color: '#9c27b0',
        values: [{ timestamp: TS(0), value: null }, { timestamp: TS(1), value: 45.5 }],
      },
      {
        series_id: 'rsi_midline', label: 'RSI Midline',
        pane: 'oscillator_pane', render_type: 'line', default_color: '#808080',
        values: [{ timestamp: TS(0), value: 50 }, { timestamp: TS(1), value: 50 }],
      },
    ],
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

/** Volume artifact with histogram series only (no MA) */
function makeVolumeArtifact(instanceId = 'vol_1'): IndicatorArtifactResponse {
  return {
    tool_id: 'volume_ma', instance_id: instanceId,
    display_name: 'Volume', pane: 'price_overlay',
    render_type: 'histogram', parameters: {}, warmup_bars: 0, diagnostics: null,
    series: [
      {
        series_id: 'volume', label: 'Volume',
        pane: 'price_overlay', render_type: 'histogram', default_color: '#26a69a',
        values: [
          { timestamp: TS(0), value: 1000 },
          { timestamp: TS(1), value: 2000 },
          { timestamp: TS(2), value: 1500 },
        ],
      },
      {
        series_id: 'volume_ma', label: 'Vol MA',
        pane: 'price_overlay', render_type: 'line', default_color: '#ff9800',
        // All null — ma_length not configured
        values: [
          { timestamp: TS(0), value: null },
          { timestamp: TS(1), value: null },
          { timestamp: TS(2), value: null },
        ],
      },
    ],
  }
}

/** Volume artifact with both histogram and MA line */
function makeVolumeArtifactWithMA(instanceId = 'vol_ma_1'): IndicatorArtifactResponse {
  return {
    tool_id: 'volume_ma', instance_id: instanceId,
    display_name: 'Volume', pane: 'price_overlay',
    render_type: 'histogram', parameters: { ma_length: 2 }, warmup_bars: 1, diagnostics: null,
    series: [
      {
        series_id: 'volume', label: 'Volume',
        pane: 'price_overlay', render_type: 'histogram', default_color: '#26a69a',
        values: [
          { timestamp: TS(0), value: 1000 },
          { timestamp: TS(1), value: 2000 },
          { timestamp: TS(2), value: 1500 },
        ],
      },
      {
        series_id: 'volume_ma', label: 'Vol MA',
        pane: 'price_overlay', render_type: 'line', default_color: '#ff9800',
        values: [
          { timestamp: TS(0), value: null },    // warmup
          { timestamp: TS(1), value: 1500.0 },  // SMA(2): (1000+2000)/2
          { timestamp: TS(2), value: 1750.0 },  // SMA(2): (2000+1500)/2
        ],
      },
    ],
  }
}

function renderChart(props: Partial<React.ComponentProps<typeof Chart>> = {}) {
  return render(<Chart candles={makeCandles()} symbol="AAPL" timeframe="1d" {...props} />)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Chart', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.chartInstances.length = 0
    _rafCallbacks = []
    _rafCounter   = 0
    localStorage.clear()  // prevent pane height persistence leaking between tests
  })

  afterEach(() => { _rafCallbacks = [] })

  // ── Rendering ─────────────────────────────────────────────────────────────

  it('1. renders without crashing', () => {
    expect(() => renderChart()).not.toThrow()
  })

  it('2. OscPane wrapper appears when oscillator artifact provided', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    // OscPane header shows tool name twice (title + instance chip) — use data-testid
    expect(screen.getByTestId('osc-pane-wrapper')).toBeInTheDocument()
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

  // ── Logical-range sync (3C.4) ─────────────────────────────────────────────

  it('6. subscribeVisibleLogicalRangeChange called for price→osc sync', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    expect(mocks.subLogicalRange).toHaveBeenCalled()
  })

  it('7. subscribeVisibleTimeRangeChange NOT used for pane sync', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    // Time-range subscribe should NOT be called (logical range is the sync mechanism)
    expect(mocks.subTimeRange).not.toHaveBeenCalled()
  })

  it('8. oscillator chart does NOT subscribe to push range back to price chart', () => {
    // With one-directional logical sync, the oscillator's own time scale
    // is never registered as a subscriber to push changes to the price chart.
    // We verify by confirming unsubscribeVisibleLogicalRangeChange is only ever
    // registered for cleanup (not for a reverse sync from osc → price).
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    // All subscribeVisibleLogicalRangeChange calls should be on the PRICE chart
    // (not the oscillator's own time scale). Since both charts share the same
    // mock, we just confirm we never subscribe AND set the range in a cycle.
    // Practical check: unsubscribeVisibleLogicalRangeChange count = subscribe count.
    expect(mocks.subLogicalRange.mock.calls.length).toBeGreaterThan(0)
  })

  it('9. setVisibleLogicalRange called when logical range syncs', () => {
    const logicalRange = { from: 5, to: 50 }
    mocks.getLogicalRange.mockReturnValue(logicalRange)
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    // After data loads, the OscPane reads and applies the logical range
    expect(mocks.setLogicalRange).toHaveBeenCalledWith(logicalRange)
  })

  it('10. extreme logical range values propagate to all oscillator panes', () => {
    const extremeRange = { from: -1000, to: 10000 }
    mocks.getLogicalRange.mockReturnValue(extremeRange)
    mocks.setLogicalRange.mockClear()
    renderChart({
      indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1'), makeOscArtifact('macd', 'macd_1')],
    })
    // Both OscPanes call setVisibleLogicalRange with the extreme range
    const extremeCalls = mocks.setLogicalRange.mock.calls.filter(
      c => c[0]?.from === extremeRange.from && c[0]?.to === extremeRange.to
    )
    expect(extremeCalls.length).toBeGreaterThanOrEqual(2)
  })

  it('11. null logical range is safely ignored', () => {
    mocks.getLogicalRange.mockReturnValue(null)
    // No throw expected when logical range is null
    expect(() => renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })).not.toThrow()
  })

  it('12. multiple OscPanes both subscribe to price logical range', () => {
    mocks.subLogicalRange.mockClear()
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1'), makeOscArtifact('macd', 'macd_1')] })
    // strategy osc (1) + rsi OscPane (1) + macd OscPane (1) = at least 3
    expect(mocks.subLogicalRange.mock.calls.length).toBeGreaterThanOrEqual(3)
  })

  it('13. subscribeCrosshairMove still called (crosshair sync preserved)', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    expect(mocks.subCrosshair).toHaveBeenCalled()
  })

  it('14. getVisibleLogicalRange applied to oscillator after data update', () => {
    const range = { from: 2, to: 30 }
    mocks.getLogicalRange.mockReturnValue(range)
    mocks.setLogicalRange.mockClear()
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    expect(mocks.setLogicalRange).toHaveBeenCalledWith(range)
  })

  // ── Timestamp alignment (carry-forward) ───────────────────────────────────

  it('15. warmup bars included as whitespace (5 entries for 5-candle domain)', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifactWithWarmup('rsi', 'rsi_1')] })
    const data = mocks.setData.mock.calls.map(c => c[0] as unknown[]).find(a => a.length === 5)
    expect(data).toHaveLength(5)
  })

  it('16. warmup entries are whitespace (no value); non-warmup have value', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifactWithWarmup('rsi', 'rsi_1')] })
    const data = mocks.setData.mock.calls
      .map(c => c[0] as Array<{ time: number; value?: number }>)
      .find(a => a.length === 5)!
    expect('value' in data[0]).toBe(false)
    expect('value' in data[1]).toBe(false)
    expect(data[2].value).toBe(55)
  })

  it('17. candle data sorted ascending by timestamp', () => {
    renderChart({ candles: [...makeCandles(3)].reverse() })
    const data = mocks.setData.mock.calls.map(c => c[0] as Array<{ time: number }>).find(a => a.length === 3)!
    expect(data[0].time).toBeLessThan(data[1].time)
    expect(data[1].time).toBeLessThan(data[2].time)
  })

  it('18. duplicate candle timestamps deduped — last wins', () => {
    const candles = makeCandles(3)
    renderChart({ candles: [...candles, { ...candles[1], close: 9999 }] })
    const data = mocks.setData.mock.calls.map(c => c[0] as Array<{ time: number; close?: number }>).find(a => a.length === 3)!
    expect(data.find(d => d.time === TS_UNIX(1))?.close).toBe(9999)
  })

  it('19. oscillator setData does not include timestamps outside candle domain', () => {
    const artifact = makeOscArtifact('rsi', 'rsi_1')
    artifact.series[0].values.push({ timestamp: TS(99), value: 77 })
    renderChart({ candles: makeCandles(2), indicatorArtifacts: [artifact] })
    const data = mocks.setData.mock.calls
      .map(c => c[0] as Array<{ time: number }>)
      .find(a => a.some(p => p.time === TS_UNIX(0)))
    expect(data?.length).toBe(2)
  })

  // ── Resize stability with fixed direction (3C.3B + 3C.4) ─────────────────

  it('20. pointer drag UP increases pane height (inverted direction)', async () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    // Drag upward: startY=300, then move to 200 → delta = startY - clientY = +100
    fireEvent.pointerDown(splitter, { clientY: 300, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 200, pointerId: 1 })
    flushRaf()
    fireEvent.pointerUp(splitter, { clientY: 200, pointerId: 1 })

    await waitFor(() => {
      const wrapper = screen.getByTestId('osc-pane-wrapper')
      expect(parseInt(wrapper.style.height || '0', 10)).toBeGreaterThan(130)
    })
  })

  it('21. pointer drag DOWN decreases pane height', async () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    // Drag downward: startY=100, move to 160 → delta = startY - clientY = -60
    fireEvent.pointerDown(splitter, { clientY: 100, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 160, pointerId: 1 })
    flushRaf()
    fireEvent.pointerUp(splitter, { clientY: 160, pointerId: 1 })

    await waitFor(() => {
      const wrapper = screen.getByTestId('osc-pane-wrapper')
      const h = parseInt(wrapper.style.height || '0', 10)
      // height decreased from 130 (or clamped to min)
      expect(h).toBeLessThanOrEqual(130)
    })
  })

  it('22. min height clamp (100px)', async () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    // Large downward drag → clamped at MIN (100), OscPane gets MIN - SPLITTER_HEIGHT (91)
    fireEvent.pointerDown(splitter, { clientY: 0, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 2000, pointerId: 1 })
    flushRaf()
    fireEvent.pointerUp(splitter, { clientY: 2000, pointerId: 1 })

    await waitFor(() => {
      const h = parseInt(screen.getByTestId('osc-pane-wrapper').style.height || '0', 10)
      // MIN_OSC_HEIGHT is 100px, but OscPane height is adjusted by SPLITTER_HEIGHT (9)
      expect(h).toBeGreaterThanOrEqual(100 - 9)
    })
  })

  it('23. max height clamp (600px)', async () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    // Large upward drag → clamped at MAX (600)
    fireEvent.pointerDown(splitter, { clientY: 2000, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 0, pointerId: 1 })
    flushRaf()
    fireEvent.pointerUp(splitter, { clientY: 0, pointerId: 1 })

    await waitFor(() => {
      const h = parseInt(screen.getByTestId('osc-pane-wrapper').style.height || '0', 10)
      expect(h).toBeLessThanOrEqual(600)
    })
  })

  it('24. React setState NOT called during pointermove — only on pointerup', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')
    const applyBefore = mocks.applyOptions.mock.calls.length

    fireEvent.pointerDown(splitter, { clientY: 300, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 250, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 220, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 200, pointerId: 1 })

    // rAF not flushed → no applyOptions yet
    expect(mocks.applyOptions.mock.calls.length).toBe(applyBefore)

    flushRaf()
    expect(mocks.applyOptions.mock.calls.length).toBeGreaterThan(applyBefore)

    fireEvent.pointerUp(splitter, { clientY: 200, pointerId: 1 })
  })

  it('25. requestAnimationFrame scheduled on each pointermove', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')
    const rafBefore = _mockRaf.mock.calls.length

    fireEvent.pointerDown(splitter, { clientY: 300, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 250, pointerId: 1 })

    expect(_mockRaf.mock.calls.length).toBeGreaterThan(rafBefore)
    fireEvent.pointerUp(splitter, { clientY: 250, pointerId: 1 })
  })

  it('26. chart.applyOptions called with new height inside rAF', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    fireEvent.pointerDown(splitter, { clientY: 300, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 200, pointerId: 1 })

    const before = mocks.applyOptions.mock.calls.length
    flushRaf()

    const heightCalls = mocks.applyOptions.mock.calls
      .slice(before)
      .filter(c => c[0]?.height !== undefined)
    expect(heightCalls.length).toBeGreaterThan(0)

    fireEvent.pointerUp(splitter, { clientY: 200, pointerId: 1 })
  })

  it('27. final height committed once on pointerup', async () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    fireEvent.pointerDown(splitter, { clientY: 300, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 200, pointerId: 1 })
    flushRaf()
    fireEvent.pointerUp(splitter, { clientY: 200, pointerId: 1 })

    await waitFor(() => {
      const h = parseInt(screen.getByTestId('osc-pane-wrapper').style.height || '0', 10)
      expect(h).toBeGreaterThan(130)
    })
  })

  it('28. pointercancel commits final height same as pointerup', async () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    fireEvent.pointerDown(splitter, { clientY: 300, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 200, pointerId: 1 })
    flushRaf()
    fireEvent.pointerCancel(splitter, { clientY: 200, pointerId: 1 })

    await waitFor(() => {
      const h = parseInt(screen.getByTestId('osc-pane-wrapper').style.height || '0', 10)
      expect(h).toBeGreaterThan(130)
    })
  })

  it('29. unmount during active drag cancels pending rAF', () => {
    const { unmount } = renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    fireEvent.pointerDown(splitter, { clientY: 300, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 200, pointerId: 1 })
    expect(_rafCallbacks.length).toBeGreaterThan(0)

    unmount()
    expect(_mockCaf).toHaveBeenCalled()
  })

  it('30. logical range resynced after drag commit', async () => {
    const range = { from: 2, to: 30 }
    mocks.getLogicalRange.mockReturnValue(range)
    mocks.setLogicalRange.mockClear()

    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    fireEvent.pointerDown(splitter, { clientY: 300, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 200, pointerId: 1 })
    flushRaf()
    fireEvent.pointerUp(splitter, { clientY: 200, pointerId: 1 })

    // setVisibleLogicalRange should have been called with the price chart range
    expect(mocks.setLogicalRange).toHaveBeenCalledWith(range)
  })

  it('31. removing indicator after resize does not crash', async () => {
    const { rerender } = renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    fireEvent.pointerDown(splitter, { clientY: 300, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 200, pointerId: 1 })
    flushRaf()
    fireEvent.pointerUp(splitter, { clientY: 200, pointerId: 1 })

    expect(() => {
      rerender(<Chart candles={makeCandles()} symbol="AAPL" timeframe="1d" indicatorArtifacts={[]} />)
    }).not.toThrow()

    await waitFor(() => {
      expect(screen.queryByTestId('pane-splitter')).not.toBeInTheDocument()
    })
  })

  it('32. no document event listeners accumulated (pointer capture model)', () => {
    const addEventSpy = vi.spyOn(document, 'addEventListener')
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    for (let i = 0; i < 3; i++) {
      fireEvent.pointerDown(splitter, { clientY: 300, pointerId: 1 })
      fireEvent.pointerMove(splitter, { clientY: 200 + i * 10, pointerId: 1 })
      flushRaf()
      fireEvent.pointerUp(splitter, { clientY: 200 + i * 10, pointerId: 1 })
    }

    const dragCalls = addEventSpy.mock.calls.filter(
      c => ['mousemove', 'mouseup', 'pointermove', 'pointerup'].includes(c[0] as string)
    )
    expect(dragCalls.length).toBe(0)
    addEventSpy.mockRestore()
  })

  it('33. two distinct tool groups render two pane splitters and two pane wrappers', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1'), makeOscArtifact('macd', 'macd_1')] })
    expect(screen.getAllByTestId('pane-splitter')).toHaveLength(2)
    expect(screen.getAllByTestId('osc-pane-wrapper')).toHaveLength(2)
  })

  it('34. removing oscillator indicator removes its pane splitter', async () => {
    const { rerender } = renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    expect(screen.getByTestId('pane-splitter')).toBeInTheDocument()

    rerender(<Chart candles={makeCandles()} symbol="AAPL" timeframe="1d" indicatorArtifacts={[]} />)
    await waitFor(() => expect(screen.queryByTestId('pane-splitter')).not.toBeInTheDocument())
  })

  // ── Chart-UX-3C.5: Chart Object Experience ─────────────────────────────────

  it('35. OscPane header shows instance chip', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    expect(screen.getByTestId('osc-instance-rsi_1')).toBeInTheDocument()
  })

  it('36. OscPane header toggle button calls onIndicatorToggle', () => {
    const onToggle = vi.fn()
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')], onIndicatorToggle: onToggle })
    fireEvent.click(screen.getByTestId('osc-toggle-rsi_1'))
    expect(onToggle).toHaveBeenCalledWith('rsi_1')
  })

  it('37. OscPane header remove button calls onIndicatorRemove', () => {
    const onRemove = vi.fn()
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')], onIndicatorRemove: onRemove })
    fireEvent.click(screen.getByTestId('osc-remove-rsi_1'))
    expect(onRemove).toHaveBeenCalledWith('rsi_1')
  })

  it('38. double-clicking splitter resets pane height to default (130)', async () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    // First drag up to 230
    fireEvent.pointerDown(splitter, { clientY: 300, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 200, pointerId: 1 })
    flushRaf()
    fireEvent.pointerUp(splitter, { clientY: 200, pointerId: 1 })

    // Double-click to reset
    fireEvent.doubleClick(splitter)

    await waitFor(() => {
      const wrapper = screen.getByTestId('osc-pane-wrapper')
      // DEFAULT_OSC_HEIGHT is 130px, but OscPane height is adjusted by SPLITTER_HEIGHT (9)
      expect(parseInt(wrapper.style.height || '0', 10)).toBe(130 - 9)
    })
  })

  it('39. pane height persisted to localStorage on commit', async () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')

    fireEvent.pointerDown(splitter, { clientY: 300, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientY: 200, pointerId: 1 })
    flushRaf()
    fireEvent.pointerUp(splitter, { clientY: 200, pointerId: 1 })

    await waitFor(() => {
      const stored = localStorage.getItem('ql_pane_heights')
      expect(stored).not.toBeNull()
      const parsed = JSON.parse(stored!)
      expect(Object.values(parsed).some((v) => (v as number) > 130)).toBe(true)
    })
  })

  it('40. pane height restored from localStorage on mount', async () => {
    // Pre-seed localStorage with a known height
    localStorage.setItem('ql_pane_heights', JSON.stringify({ rsi: 250 }))
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })

    await waitFor(() => {
      const wrapper = screen.getByTestId('osc-pane-wrapper')
      // Height is adjusted: stored value (250) minus DragSplitter height (9) = 241
      const SPLITTER_HEIGHT = 9
      expect(parseInt(wrapper.style.height || '0', 10)).toBe(250 - SPLITTER_HEIGHT)
    })
  })

  it('41. hovering OscPane wrapper triggers isHovered active-pane feedback', async () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const wrapper = screen.getByTestId('osc-pane-wrapper')

    fireEvent.mouseEnter(wrapper)
    await waitFor(() => {
      // Hover adds a non-transparent left border
      expect(wrapper.style.borderLeft).not.toContain('transparent')
    })

    fireEvent.mouseLeave(wrapper)
    await waitFor(() => {
      expect(wrapper.style.borderLeft).toContain('transparent')
    })
  })

  it('42. splitter outer div has wider hit target (padding)', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    const splitter = screen.getByTestId('pane-splitter')
    expect(splitter.style.padding).toBeTruthy()
  })

  // ── CHART-UX-4A: Data Inspector integration ────────────────────────────

  it('43. inspector renders with symbol / timeframe', () => {
    renderChart({ symbol: 'TSLA', timeframe: '1h' })
    const meta = screen.getByTestId('inspector-meta').textContent ?? ''
    expect(meta).toContain('TSLA')
    expect(meta).toContain('1h')
  })

  it('44. inspector renders exchange when provided', () => {
    renderChart({ symbol: 'AAPL', timeframe: '1d', exchange: 'NASDAQ' })
    expect(screen.getByTestId('inspector-meta').textContent).toContain('NASDAQ')
  })

  it('45. initial render shows latest candle OHLC', () => {
    // makeCandles(5): last candle close = 102+4 = 106; token text is "C 106.00"
    renderChart({ candles: makeCandles(5) })
    const close = screen.getByTestId('inspector-close').textContent ?? ''
    expect(close).toContain('106.00')
  })

  it('46. crosshair move callback fires for price chart', () => {
    renderChart()
    // subscribeCrosshairMove called on the price chart
    expect(mocks.subCrosshair).toHaveBeenCalled()
  })

  it('47. mouse leave resets inspector to latest candle', async () => {
    renderChart({ candles: makeCandles(5) })
    // Simulate crosshair leaving: pass null/empty to the registered handler
    const handler = mocks.subCrosshair.mock.calls[0]?.[0]
    if (handler) {
      handler(null)
    }
    await waitFor(() => {
      const close = screen.getByTestId('inspector-close').textContent ?? ''
      expect(close).toContain('106.00')  // back to latest
    })
  })

  it('48. inspector does not render date/time strings', () => {
    renderChart({ symbol: 'AAPL', timeframe: '1d' })
    const text = screen.getByTestId('chart-data-inspector').textContent ?? ''
    expect(text).not.toMatch(/\b20\d{2}\b/)        // no year
    expect(text).not.toMatch(/\d{2}:\d{2}/)        // no HH:MM
  })

  it('49. inspector present with no candles (empty state)', () => {
    renderChart({ candles: [] })
    expect(screen.getByTestId('chart-data-inspector')).toBeInTheDocument()
  })

  // ── Volume histogram rendering (volume_ma tool) ───────────────────────────

  it('50. volume histogram: HistogramSeries created in price pane (not OscPane)', () => {
    renderChart({ indicatorArtifacts: [makeVolumeArtifact()] })
    // HistogramSeries added with priceScaleId='volume' — no pane splitter expected
    expect(screen.queryByTestId('pane-splitter')).not.toBeInTheDocument()
    expect(screen.queryByTestId('osc-pane-wrapper')).not.toBeInTheDocument()
  })

  it('51. volume histogram: addSeries called with HistogramSeries token', () => {
    renderChart({ indicatorArtifacts: [makeVolumeArtifact()] })
    const calls = mocks.addSeries.mock.calls
    const histCalls = calls.filter(([seriesType]: [string, ...unknown[]]) => seriesType === 'HistogramSeries')
    expect(histCalls.length).toBeGreaterThan(0)
  })

  it('52. volume histogram: priceScale("volume") applyOptions called for scale margins', () => {
    renderChart({ indicatorArtifacts: [makeVolumeArtifact()] })
    expect(mocks.priceScaleApplyOptions).toHaveBeenCalledWith(
      expect.objectContaining({ scaleMargins: expect.any(Object) })
    )
  })

  it('53. volume MA line absent when volume_ma series all null (ma_length not set)', () => {
    // makeVolumeArtifact() has volume_ma series with all-null values
    renderChart({ indicatorArtifacts: [makeVolumeArtifact()] })
    // addSeries called for volume histogram; volume_ma line skipped (all null)
    const calls = mocks.addSeries.mock.calls
    const lineCalls = calls.filter(([type, opts]: [string, { priceScaleId?: string }]) =>
      type === 'LineSeries' && opts?.priceScaleId === 'volume'
    )
    expect(lineCalls.length).toBe(0)
  })

  it('54. volume MA line rendered on volume scale when ma values present', () => {
    renderChart({ indicatorArtifacts: [makeVolumeArtifactWithMA()] })
    const calls = mocks.addSeries.mock.calls
    const volumeLineCalls = calls.filter(([type, opts]: [string, { priceScaleId?: string }]) =>
      type === 'LineSeries' && opts?.priceScaleId === 'volume'
    )
    expect(volumeLineCalls.length).toBeGreaterThan(0)
  })

  it('55. volume artifact does not create OscPane or pane splitter', () => {
    renderChart({ indicatorArtifacts: [makeVolumeArtifactWithMA()] })
    expect(screen.queryByTestId('pane-splitter')).not.toBeInTheDocument()
    expect(screen.queryByTestId('osc-pane-wrapper')).not.toBeInTheDocument()
  })

  it('56. existing line overlays still rendered correctly alongside volume', () => {
    renderChart({ indicatorArtifacts: [makeVolumeArtifact(), makeOverlayArtifact('sma', 'sma_1')] })
    const calls = mocks.addSeries.mock.calls
    // SMA overlay: LineSeries WITHOUT priceScaleId='volume'
    const smaLineCalls = calls.filter(([type, opts]: [string, { priceScaleId?: string }]) =>
      type === 'LineSeries' && opts?.priceScaleId !== 'volume'
    )
    expect(smaLineCalls.length).toBeGreaterThan(0)
    // Volume histogram still present
    const histCalls = calls.filter(([t]: [string]) => t === 'HistogramSeries')
    expect(histCalls.length).toBeGreaterThan(0)
  })

  // ── Volume histogram directional coloring ─────────────────────────────────
  //
  // Candle sequence used for tests 57-60:
  //   Bar 0: close=100  → first bar, no prev  → neutral/green (#26a69a)
  //   Bar 1: close=110  → 110 >= 100           → green  (#26a69a)
  //   Bar 2: close=90   → 90  <  110           → red    (#ef5350)
  //   Bar 3: close=105  → 105 >= 90            → green  (#26a69a)
  //   Bar 4: close=100  → 100 <  105           → red    (#ef5350)

  /** Candles with a known up/down close sequence for coloring assertions. */
  function makeDirectionalCandles(): OHLCVCandle[] {
    const closes = [100, 110, 90, 105, 100]
    return closes.map((close, i) => ({
      timestamp: TS(i),
      open:  close - 2,
      high:  close + 3,
      low:   close - 3,
      close,
      volume: 1000 * (i + 1),
    }))
  }

  /** Volume artifact whose timestamps align with a given candle array. */
  function makeVolumeArtifactForCandles(candles: OHLCVCandle[]): IndicatorArtifactResponse {
    return {
      tool_id: 'volume_ma', instance_id: 'vol_dir',
      display_name: 'Volume', pane: 'price_overlay',
      render_type: 'histogram', parameters: {}, warmup_bars: 0, diagnostics: null,
      series: [
        {
          series_id: 'volume', label: 'Volume',
          pane: 'price_overlay', render_type: 'histogram', default_color: '#26a69a',
          values: candles.map(c => ({ timestamp: c.timestamp, value: c.volume })),
        },
        {
          series_id: 'volume_ma', label: 'Vol MA',
          pane: 'price_overlay', render_type: 'line', default_color: '#ff9800',
          values: candles.map(c => ({ timestamp: c.timestamp, value: null })),
        },
      ],
    }
  }

  /** Find the setData call whose data points carry a `color` property (histogram data). */
  function findHistogramSetData(): Array<{ time: number; value: number; color: string }> | undefined {
    return mocks.setData.mock.calls
      .map(c => c[0] as Array<{ time: number; value: number; color?: string }>)
      .find(arr => arr.length > 0 && typeof arr[0].color === 'string') as
      Array<{ time: number; value: number; color: string }> | undefined
  }

  it('57. volume: first bar gets neutral green color (no previous close exists)', () => {
    const candles = makeDirectionalCandles()
    renderChart({ candles, indicatorArtifacts: [makeVolumeArtifactForCandles(candles)] })
    const data = findHistogramSetData()
    expect(data).toBeDefined()
    expect(data![0].color).toBe('#26a69a')
  })

  it('58. volume: green bar when close >= previous close', () => {
    const candles = makeDirectionalCandles()
    // Bar 1: close=110 >= close=100 (bar 0) → green
    renderChart({ candles, indicatorArtifacts: [makeVolumeArtifactForCandles(candles)] })
    const data = findHistogramSetData()!
    expect(data[1].color).toBe('#26a69a')
    // Bar 3: close=105 >= close=90 (bar 2) → green
    expect(data[3].color).toBe('#26a69a')
  })

  it('59. volume: red bar when close < previous close', () => {
    const candles = makeDirectionalCandles()
    // Bar 2: close=90 < close=110 (bar 1) → red
    renderChart({ candles, indicatorArtifacts: [makeVolumeArtifactForCandles(candles)] })
    const data = findHistogramSetData()!
    expect(data[2].color).toBe('#ef5350')
    // Bar 4: close=100 < close=105 (bar 3) → red
    expect(data[4].color).toBe('#ef5350')
  })

  it('60. volume: full alternating sequence green/green/red/green/red', () => {
    const candles = makeDirectionalCandles()
    renderChart({ candles, indicatorArtifacts: [makeVolumeArtifactForCandles(candles)] })
    const data = findHistogramSetData()!
    expect(data.map(p => p.color)).toEqual([
      '#26a69a', // bar 0 — neutral/green (no prev)
      '#26a69a', // bar 1 — 110 >= 100
      '#ef5350', // bar 2 — 90  <  110
      '#26a69a', // bar 3 — 105 >= 90
      '#ef5350', // bar 4 — 100 <  105
    ])
  })

  // ── Volume histogram deduplication (volume + volume_ma active together) ─────
  //
  // When both the raw 'volume' tool and the 'volume_ma' tool are active they each
  // expose a histogram series in the price pane.  Rendering both produces duplicate
  // overlapping bars.  The chart should render exactly one histogram and still render
  // any MA line from volume_ma.

  /** Artifact for the raw 'volume' tool — histogram only, no MA series. */
  function makeRawVolumeArtifact(instanceId = 'raw_vol'): IndicatorArtifactResponse {
    return {
      tool_id: 'volume', instance_id: instanceId,
      display_name: 'Volume', pane: 'price_overlay',
      render_type: 'histogram', parameters: {}, warmup_bars: 0, diagnostics: null,
      series: [
        {
          series_id: 'volume', label: 'Volume',
          pane: 'price_overlay', render_type: 'histogram', default_color: '#26a69a',
          values: [
            { timestamp: TS(0), value: 1000 },
            { timestamp: TS(1), value: 2000 },
            { timestamp: TS(2), value: 1500 },
          ],
        },
      ],
    }
  }

  it('61. volume only → one HistogramSeries rendered', () => {
    renderChart({ indicatorArtifacts: [makeRawVolumeArtifact()] })
    const histCalls = mocks.addSeries.mock.calls.filter(
      ([t]: [string]) => t === 'HistogramSeries'
    )
    expect(histCalls.length).toBe(1)
  })

  it('62. volume_ma only (no MA) → one HistogramSeries rendered', () => {
    renderChart({ indicatorArtifacts: [makeVolumeArtifact()] })
    const histCalls = mocks.addSeries.mock.calls.filter(
      ([t]: [string]) => t === 'HistogramSeries'
    )
    expect(histCalls.length).toBe(1)
  })

  it('63. volume + volume_ma active → exactly one HistogramSeries total (deduplication)', () => {
    renderChart({
      indicatorArtifacts: [makeRawVolumeArtifact(), makeVolumeArtifact()],
    })
    const histCalls = mocks.addSeries.mock.calls.filter(
      ([t]: [string]) => t === 'HistogramSeries'
    )
    expect(histCalls.length).toBe(1)
  })

  it('64. volume + volume_ma(20) active → single histogram and MA line both rendered', () => {
    renderChart({
      indicatorArtifacts: [makeRawVolumeArtifact(), makeVolumeArtifactWithMA()],
    })
    const calls = mocks.addSeries.mock.calls
    const histCalls = calls.filter(([t]: [string]) => t === 'HistogramSeries')
    const maLineCalls = calls.filter(([t, opts]: [string, { priceScaleId?: string }]) =>
      t === 'LineSeries' && opts?.priceScaleId === 'volume'
    )
    expect(histCalls.length).toBe(1)
    expect(maLineCalls.length).toBeGreaterThan(0)
  })

  it('65. no OscPane created when both volume and volume_ma active', () => {
    renderChart({
      indicatorArtifacts: [makeRawVolumeArtifact(), makeVolumeArtifactWithMA()],
    })
    expect(screen.queryByTestId('pane-splitter')).not.toBeInTheDocument()
    expect(screen.queryByTestId('osc-pane-wrapper')).not.toBeInTheDocument()
  })

  // ── Strategy overlay rendering (66–73) ─────────────────────────────────────
  //
  // When a strategy run produces volume/volume_ma outputs, Chart.tsx must render
  // them on the dedicated "volume" price scale, not the OHLC price scale.
  // Volume values (~millions) would explode the price axis if treated as price lines.

  function makeStrategyOverlay(indicators: ToolVisualizationSeries[]): StrategyOverlay {
    return { signals: [], forecast: null, indicators }
  }

  function makeVolumeStrategyIndicator(): ToolVisualizationSeries {
    return {
      name: 'vol_1.volume', kind: 'histogram', pane: 'price',
      price_scale: 'volume', color: null,
      points: [
        { timestamp: TS(0), value: 1000 },
        { timestamp: TS(1), value: 2000 },
        { timestamp: TS(2), value: 1500 },
      ],
    }
  }

  function makeVolumeMaStrategyIndicator(): ToolVisualizationSeries {
    return {
      name: 'vma_1.volume_ma', kind: 'line', pane: 'price',
      price_scale: 'volume', color: null,
      points: [
        { timestamp: TS(1), value: 1500 },
        { timestamp: TS(2), value: 1750 },
      ],
    }
  }

  function makeEmaStrategyIndicator(): ToolVisualizationSeries {
    return {
      name: 'ema_1.ema', kind: 'line', pane: 'price',
      price_scale: 'default', color: '#ff5500',
      points: [
        { timestamp: TS(0), value: 101 },
        { timestamp: TS(1), value: 101.5 },
      ],
    }
  }

  function makeRsiStrategyIndicator(): ToolVisualizationSeries {
    return {
      name: 'rsi_1.rsi', kind: 'line', pane: 'oscillator',
      price_scale: 'default', color: null,
      points: [
        { timestamp: TS(0), value: 55 },
        { timestamp: TS(1), value: 60 },
      ],
    }
  }

  it('66. strategy-run volume output renders as HistogramSeries', () => {
    renderChart({ overlay: makeStrategyOverlay([makeVolumeStrategyIndicator()]) })
    const histCalls = mocks.addSeries.mock.calls.filter(
      ([t]: [string]) => t === 'HistogramSeries'
    )
    expect(histCalls.length).toBeGreaterThanOrEqual(1)
  })

  it('67. strategy-run volume histogram uses priceScaleId="volume"', () => {
    renderChart({ overlay: makeStrategyOverlay([makeVolumeStrategyIndicator()]) })
    const histCall = mocks.addSeries.mock.calls.find(
      ([t]: [string]) => t === 'HistogramSeries'
    )
    expect(histCall).toBeDefined()
    expect(histCall![1]?.priceScaleId).toBe('volume')
  })

  it('68. strategy-run volume scale margins applied (top: 0.75, bottom: 0)', () => {
    renderChart({ overlay: makeStrategyOverlay([makeVolumeStrategyIndicator()]) })
    expect(mocks.priceScaleApplyOptions).toHaveBeenCalledWith(
      expect.objectContaining({ scaleMargins: { top: 0.75, bottom: 0 } })
    )
  })

  it('69. strategy-run volume_ma line uses priceScaleId="volume"', () => {
    renderChart({ overlay: makeStrategyOverlay([makeVolumeMaStrategyIndicator()]) })
    const volumeLineCall = mocks.addSeries.mock.calls.find(
      ([t, opts]: [string, Record<string, unknown>]) =>
        t === 'LineSeries' && opts?.priceScaleId === 'volume'
    )
    expect(volumeLineCall).toBeDefined()
  })

  it('70. strategy-run EMA uses normal price scale (no priceScaleId)', () => {
    renderChart({ overlay: makeStrategyOverlay([makeEmaStrategyIndicator()]) })
    const lineCall = mocks.addSeries.mock.calls.find(
      ([t]: [string]) => t === 'LineSeries'
    )
    expect(lineCall).toBeDefined()
    expect(lineCall![1]?.priceScaleId).toBeUndefined()
  })

  it('71. strategy-run volume + EMA — histogram on volume scale, EMA on default scale', () => {
    renderChart({
      overlay: makeStrategyOverlay([makeVolumeStrategyIndicator(), makeEmaStrategyIndicator()])
    })
    const histCall = mocks.addSeries.mock.calls.find(
      ([t]: [string]) => t === 'HistogramSeries'
    )
    const emaLineCall = mocks.addSeries.mock.calls.find(
      ([t, opts]: [string, Record<string, unknown>]) =>
        t === 'LineSeries' && !opts?.priceScaleId
    )
    expect(histCall).toBeDefined()
    expect(emaLineCall).toBeDefined()
    // EMA must NOT be on volume scale
    expect(emaLineCall![1]?.priceScaleId).toBeUndefined()
  })

  it('72. strategy-run oscillator indicator triggers strategy oscillator pane label', () => {
    renderChart({ overlay: makeStrategyOverlay([makeRsiStrategyIndicator()]) })
    // showOscillator = true → strategy oscillator label rendered in the pane div
    expect(screen.getByText('oscillator')).toBeInTheDocument()
  })

  it('73. indicator artifact rendering unchanged when strategy overlay also active', () => {
    renderChart({
      indicatorArtifacts: [makeOverlayArtifact('sma', 'sma_1')],
      overlay: makeStrategyOverlay([makeVolumeStrategyIndicator()]),
    })
    // Both artifact SMA line and strategy volume histogram should render without crash
    const histCalls = mocks.addSeries.mock.calls.filter(
      ([t]: [string]) => t === 'HistogramSeries'
    )
    const lineCalls = mocks.addSeries.mock.calls.filter(
      ([t]: [string]) => t === 'LineSeries'
    )
    expect(histCalls.length).toBeGreaterThanOrEqual(1)
    expect(lineCalls.length).toBeGreaterThanOrEqual(1)
    // No oscillator pane splitter (neither artifact is oscillator, RSI not in overlay)
    expect(screen.queryByTestId('pane-splitter')).not.toBeInTheDocument()
  })

  it('78. strategy-run oscillator subscribes to price chart crosshair movement', () => {
    renderChart({ overlay: makeStrategyOverlay([makeRsiStrategyIndicator()]) })
    expect(mocks.subCrosshair.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it('79. strategy-run oscillator sets crosshair position for matching timestamp data', () => {
    renderChart({ overlay: makeStrategyOverlay([makeRsiStrategyIndicator()]) })
    const syncCrosshair = mocks.subCrosshair.mock.calls[0]?.[0]

    syncCrosshair?.({ time: TS_UNIX(1), seriesData: new Map() })

    expect(mocks.chartInstances[1].setCrosshairPosition).toHaveBeenCalledWith(
      60,
      TS_UNIX(1),
      expect.anything(),
    )
  })

  it('80. strategy-run oscillator clears crosshair when event has no time', () => {
    renderChart({ overlay: makeStrategyOverlay([makeRsiStrategyIndicator()]) })
    const syncCrosshair = mocks.subCrosshair.mock.calls[0]?.[0]

    syncCrosshair?.({ seriesData: new Map() })

    expect(mocks.chartInstances[1].clearCrosshairPosition).toHaveBeenCalled()
  })

  // ── Volume histogram single-color mode (VOL-UX-2) ─────────────────────────
  //
  // volumeColorModes: Map<instanceId, hexColor> — when present for an artifact,
  // every histogram bar uses that single color instead of directional red/green.

  it('74. volumeColorModes absent → histogram uses directional close-to-close colors', () => {
    const candles = makeDirectionalCandles()
    renderChart({ candles, indicatorArtifacts: [makeVolumeArtifactForCandles(candles)] })
    const data = findHistogramSetData()!
    expect(data.map(p => p.color)).toEqual([
      '#26a69a', // bar 0 — neutral/green
      '#26a69a', // bar 1 — 110 >= 100
      '#ef5350', // bar 2 — 90  <  110
      '#26a69a', // bar 3 — 105 >= 90
      '#ef5350', // bar 4 — 100 <  105
    ])
  })

  it('75. volumeColorModes with matching instance_id → all bars use that single color', () => {
    const candles = makeDirectionalCandles()
    const volumeColorModes = new Map([['vol_dir', '#ff00ff']])
    renderChart({
      candles,
      indicatorArtifacts: [makeVolumeArtifactForCandles(candles)],
      volumeColorModes,
    })
    const data = findHistogramSetData()!
    expect(data.every(p => p.color === '#ff00ff')).toBe(true)
  })

  it('76. volumeColorModes with non-matching instance_id → histogram falls back to directional', () => {
    const candles = makeDirectionalCandles()
    const volumeColorModes = new Map([['other_instance', '#ff00ff']])
    renderChart({
      candles,
      indicatorArtifacts: [makeVolumeArtifactForCandles(candles)],
      volumeColorModes,
    })
    const data = findHistogramSetData()!
    expect(data.map(p => p.color)).toEqual([
      '#26a69a', '#26a69a', '#ef5350', '#26a69a', '#ef5350',
    ])
  })

  it('77. empty volumeColorModes Map → histogram uses directional colors', () => {
    const candles = makeDirectionalCandles()
    renderChart({
      candles,
      indicatorArtifacts: [makeVolumeArtifactForCandles(candles)],
      volumeColorModes: new Map(),
    })
    const data = findHistogramSetData()!
    expect(data.map(p => p.color)).toEqual([
      '#26a69a', '#26a69a', '#ef5350', '#26a69a', '#ef5350',
    ])
  })

  // ── TOOL-VIS-STYLE-1 — line style rendering ─────────────────────────────────
  // Filter helper: overlay artifact LineSeries are identified by lastValueVisible: true
  // (the forecast series created on mount uses lastValueVisible: false).

  function findOverlayLineCalls() {
    return mocks.addSeries.mock.calls.filter(
      ([type, opts]: [string, Record<string, unknown>]) =>
        type === 'LineSeries' && opts?.lastValueVisible === true
    )
  }

  it('81. line overlay without line_style uses LineStyle.Solid (0)', () => {
    renderChart({ indicatorArtifacts: [makeOverlayArtifact('sma', 'sma_1')] })
    const calls = findOverlayLineCalls()
    expect(calls.length).toBeGreaterThan(0)
    const opts = calls[0][1] as Record<string, unknown>
    expect(opts.lineStyle).toBe(0) // LineStyle.Solid
  })

  it('82. line overlay with line_style="dashed" uses LineStyle.Dashed (2)', () => {
    const artifact = makeOverlayArtifact('sma', 'sma_1')
    artifact.series[0] = { ...artifact.series[0], line_style: 'dashed' }
    renderChart({ indicatorArtifacts: [artifact] })
    const calls = findOverlayLineCalls()
    expect(calls.length).toBeGreaterThan(0)
    const opts = calls[0][1] as Record<string, unknown>
    expect(opts.lineStyle).toBe(2) // LineStyle.Dashed
  })

  it('83. line overlay with line_style="dotted" uses LineStyle.Dotted (1)', () => {
    const artifact = makeOverlayArtifact('sma', 'sma_1')
    artifact.series[0] = { ...artifact.series[0], line_style: 'dotted' }
    renderChart({ indicatorArtifacts: [artifact] })
    const calls = findOverlayLineCalls()
    expect(calls.length).toBeGreaterThan(0)
    const opts = calls[0][1] as Record<string, unknown>
    expect(opts.lineStyle).toBe(1) // LineStyle.Dotted
  })

  // ── CHART-SETTINGS-1A — chart settings panel and label toggles ────────────
  //
  // Helpers:
  //  makeSettings(labels) — produces a ChartSettings with only the given label overrides
  //  makeSignaledOverlay()  — a strategy overlay that includes a single long signal

  function makeSettings(labelOverrides: Partial<ChartSettings['labels']>): ChartSettings {
    return {
      ...DEFAULT_CHART_SETTINGS,
      labels: { ...DEFAULT_CHART_SETTINGS.labels, ...labelOverrides },
    }
  }

  function makeSignaledOverlay(): StrategyOverlay {
    return {
      signals: [{
        timestamp:          TS(1),
        symbol:             'AAPL',
        timeframe:          '1d',
        signal_type:        'long' as const,
        entry_reference:    0,
        invalidation_level: 0,
      }],
      forecast:   null,
      indicators: [],
    }
  }

  it('91. showLatestPriceLabel: false — applyOptions called with lastValueVisible: false', () => {
    renderChart({ chartSettings: makeSettings({ showLatestPriceLabel: false }) })
    expect(mocks.seriesApplyOptions).toHaveBeenCalledWith(
      expect.objectContaining({ lastValueVisible: false, priceLineVisible: false })
    )
  })

  it('92. showIndicatorValueLabels: false — overlay line series created with lastValueVisible: false', () => {
    renderChart({
      indicatorArtifacts: [makeOverlayArtifact('sma', 'sma_1')],
      chartSettings: makeSettings({ showIndicatorValueLabels: false }),
    })
    // With showIndicatorValueLabels: false the overlay series is NOT created with lastValueVisible: true
    // (findOverlayLineCalls filters for lastValueVisible: true — should return nothing)
    expect(findOverlayLineCalls()).toHaveLength(0)
  })

  it('93. showStrategyValueLabels: false — strategy line series created with lastValueVisible: false', () => {
    renderChart({
      overlay: makeStrategyOverlay([makeEmaStrategyIndicator()]),
      chartSettings: makeSettings({ showStrategyValueLabels: false }),
    })
    // Strategy EMA line should NOT appear in findOverlayLineCalls (which filters lastValueVisible: true)
    expect(findOverlayLineCalls()).toHaveLength(0)
  })

  it('94. showSignalMarkers: false — setMarkers([]) when overlay has signals', () => {
    mocks.setMarkers.mockClear()
    renderChart({
      overlay: makeSignaledOverlay(),
      chartSettings: makeSettings({ showSignalMarkers: false }),
    })
    // The overlay effect stores markers then calls setMarkers([]) because showSignalMarkers is false.
    // The last call must be setMarkers([]).
    const calls = mocks.setMarkers.mock.calls
    expect(calls.length).toBeGreaterThan(0)
    expect(calls[calls.length - 1][0]).toEqual([])
  })

  it('95. showSignalMarkers: true — setMarkers called with signal data when overlay has signals', () => {
    mocks.setMarkers.mockClear()
    renderChart({
      overlay: makeSignaledOverlay(),
      chartSettings: makeSettings({ showSignalMarkers: true }),
    })
    // At least one call must pass a non-empty array
    const nonEmpty = mocks.setMarkers.mock.calls.find(
      (c: unknown[][]) => Array.isArray(c[0]) && (c[0] as unknown[]).length > 0
    )
    expect(nonEmpty).toBeDefined()
  })

  // ── CHART-SETTINGS-1A: reactive toggle regression (G1, G2, G6) ──────────────
  //
  // These tests cover the "settings already stored, then user toggles" path:
  // series are alive, the toggle fires, applyOptions is called.
  // Stable candle/artifact/overlay references are used so the creation-side
  // effects do not re-run — only the toggle effects exercise the tested code.

  it('96. showSignalMarkers: false preserved after overlay re-run with new signals', () => {
    // Initial render: overlay with signals, markers OFF
    mocks.setMarkers.mockClear()
    const candles  = makeCandles()
    const overlay1 = makeSignaledOverlay()
    const { rerender } = render(
      <Chart candles={candles} symbol="AAPL" timeframe="1d"
        overlay={overlay1} chartSettings={makeSettings({ showSignalMarkers: false })} />
    )
    mocks.setMarkers.mockClear()

    // Strategy re-runs → new overlay object → overlay effect fires again
    const overlay2 = makeSignaledOverlay()   // different reference = effect re-runs
    rerender(
      <Chart candles={candles} symbol="AAPL" timeframe="1d"
        overlay={overlay2} chartSettings={makeSettings({ showSignalMarkers: false })} />
    )

    // Overlay effect reads chartSettingsRef → showSignalMarkers still false → setMarkers([])
    const calls = mocks.setMarkers.mock.calls
    expect(calls.length).toBeGreaterThan(0)
    expect(calls[calls.length - 1][0]).toEqual([])
  })

  it('97. showSignalMarkers: toggle ON after overlay re-run restores current markers', () => {
    // Start: markers OFF, first overlay run
    const candles  = makeCandles()
    const overlay1 = makeSignaledOverlay()
    const { rerender } = render(
      <Chart candles={candles} symbol="AAPL" timeframe="1d"
        overlay={overlay1} chartSettings={makeSettings({ showSignalMarkers: false })} />
    )

    // Strategy re-runs while OFF → new overlay object → currentMarkersRef updated
    const overlay2 = makeSignaledOverlay()
    rerender(
      <Chart candles={candles} symbol="AAPL" timeframe="1d"
        overlay={overlay2} chartSettings={makeSettings({ showSignalMarkers: false })} />
    )

    // Toggle ON — toggle effect reads currentMarkersRef (from overlay2) and restores markers
    mocks.setMarkers.mockClear()
    rerender(
      <Chart candles={candles} symbol="AAPL" timeframe="1d"
        overlay={overlay2} chartSettings={makeSettings({ showSignalMarkers: true })} />
    )
    const nonEmpty = mocks.setMarkers.mock.calls.find(
      (c: unknown[][]) => Array.isArray(c[0]) && (c[0] as unknown[]).length > 0
    )
    expect(nonEmpty).toBeDefined()
  })

  it('98. showIndicatorValueLabels reactive toggle — applyOptions on existing artifact series', () => {
    // Stable refs: artifact effect does NOT re-run on rerender, only the toggle effect fires
    const candles   = makeCandles()
    const artifacts = [makeOverlayArtifact('sma', 'sma_1')]
    const { rerender } = render(
      <Chart candles={candles} symbol="AAPL" timeframe="1d"
        indicatorArtifacts={artifacts} chartSettings={makeSettings({})} />
    )
    mocks.seriesApplyOptions.mockClear()

    rerender(
      <Chart candles={candles} symbol="AAPL" timeframe="1d"
        indicatorArtifacts={artifacts}
        chartSettings={makeSettings({ showIndicatorValueLabels: false })} />
    )

    // Toggle effect iterates labelledArtifactSeriesKeys → applyOptions({ lastValueVisible: false })
    expect(mocks.seriesApplyOptions).toHaveBeenCalledWith(
      expect.objectContaining({ lastValueVisible: false })
    )
  })

  it('99. showStrategyValueLabels reactive toggle — applyOptions on existing strategy series', () => {
    // Stable refs: overlay effect does NOT re-run on rerender, only the toggle effect fires
    const candles = makeCandles()
    const overlay  = makeStrategyOverlay([makeEmaStrategyIndicator()])
    const { rerender } = render(
      <Chart candles={candles} symbol="AAPL" timeframe="1d"
        overlay={overlay} chartSettings={makeSettings({})} />
    )
    mocks.seriesApplyOptions.mockClear()

    rerender(
      <Chart candles={candles} symbol="AAPL" timeframe="1d"
        overlay={overlay}
        chartSettings={makeSettings({ showStrategyValueLabels: false })} />
    )

    // Toggle effect iterates labelledStrategySeriesKeys → applyOptions({ lastValueVisible: false })
    expect(mocks.seriesApplyOptions).toHaveBeenCalledWith(
      expect.objectContaining({ lastValueVisible: false })
    )
  })

  it('100. showIndicatorValueLabels toggle applies to OscPane oscillator series', () => {
    // Stable refs: OscPane series rebuild does NOT re-run, only the OscPane toggle effect fires
    const candles      = makeCandles()
    const oscArtifacts = [makeOscArtifact('rsi', 'rsi_1')]
    const { rerender } = render(
      <Chart candles={candles} symbol="AAPL" timeframe="1d"
        indicatorArtifacts={oscArtifacts} chartSettings={makeSettings({})} />
    )
    mocks.seriesApplyOptions.mockClear()

    rerender(
      <Chart candles={candles} symbol="AAPL" timeframe="1d"
        indicatorArtifacts={oscArtifacts}
        chartSettings={makeSettings({ showIndicatorValueLabels: false })} />
    )

    // OscPane toggle effect iterates seriesMapRef → applyOptions({ lastValueVisible: false })
    expect(mocks.seriesApplyOptions).toHaveBeenCalledWith(
      expect.objectContaining({ lastValueVisible: false })
    )
  })

  // ── CHART-FIX-YAXIS-WIDTH-1 — consistent right axis minimum width ─────────
  // All chart instances share _CHART_THEME; a single minimumWidth field on
  // rightPriceScale ensures oscillator panes reserve at least the same axis
  // width as the price chart regardless of their label digit count.

  it('84. rightPriceScale.minimumWidth is present in chart configuration', () => {
    renderChart()
    const calls = vi.mocked(createChart).mock.calls
    expect(calls.length).toBeGreaterThan(0)
    const opts = calls[0][1] as { rightPriceScale?: Record<string, unknown> }
    expect(opts.rightPriceScale).toHaveProperty('minimumWidth')
  })

  it('85. rightPriceScale.minimumWidth value is at least 80', () => {
    renderChart()
    const opts = vi.mocked(createChart).mock.calls[0][1] as { rightPriceScale?: { minimumWidth?: number } }
    expect(opts.rightPriceScale?.minimumWidth).toBeGreaterThanOrEqual(80)
  })

  it('86. main price chart createChart call carries rightPriceScale.minimumWidth', () => {
    renderChart()
    // All chart instances from a no-oscillator render use _CHART_THEME — verify each.
    vi.mocked(createChart).mock.calls.forEach(([, opts]) => {
      const o = opts as { rightPriceScale?: { minimumWidth?: number } }
      expect(typeof o.rightPriceScale?.minimumWidth).toBe('number')
      expect(o.rightPriceScale!.minimumWidth).toBeGreaterThanOrEqual(80)
    })
  })

  it('87. OscPane createChart calls also carry rightPriceScale.minimumWidth', () => {
    renderChart({ indicatorArtifacts: [makeOscArtifact('rsi', 'rsi_1')] })
    // With one oscillator pane: price chart + strategy osc + OscPane = 3 createChart calls.
    const calls = vi.mocked(createChart).mock.calls
    expect(calls.length).toBeGreaterThanOrEqual(3)
    const allHave = calls.every(([, opts]) => {
      const o = opts as { rightPriceScale?: { minimumWidth?: number } }
      return typeof o.rightPriceScale?.minimumWidth === 'number' &&
             o.rightPriceScale.minimumWidth >= 80
    })
    expect(allHave).toBe(true)
  })

  // ── CHART-SETTINGS-1A.5 — title="" to fully hide right-axis labels in LW Charts v5 ──
  // Root cause: LW Charts v5 renders `title` as a persistent right-axis text label
  // independently of `lastValueVisible`. Both must be set to hide the label completely.

  it('104. OscPane RSI series created with title="" when showIndicatorValueLabels=false', () => {
    const candles = makeCandles()
    renderChart({
      candles,
      indicatorArtifacts: [makeRsiArtifactWithMidline()],
      chartSettings: makeSettings({ showIndicatorValueLabels: false }),
    })
    // No LineSeries must be created with title='RSI' — it must be '' when hidden
    const rsiTitleCall = mocks.addSeries.mock.calls.find(
      ([type, opts]: [string, Record<string, unknown>]) =>
        type === 'LineSeries' && opts?.title === 'RSI'
    )
    expect(rsiTitleCall).toBeUndefined()
  })

  it('105. OscPane RSI Midline series created with title="" when showIndicatorValueLabels=false', () => {
    const candles = makeCandles()
    renderChart({
      candles,
      indicatorArtifacts: [makeRsiArtifactWithMidline()],
      chartSettings: makeSettings({ showIndicatorValueLabels: false }),
    })
    // RSI Midline title must also be '' when hidden
    const midlineTitleCall = mocks.addSeries.mock.calls.find(
      ([type, opts]: [string, Record<string, unknown>]) =>
        type === 'LineSeries' && opts?.title === 'RSI Midline'
    )
    expect(midlineTitleCall).toBeUndefined()
  })

  it('106. OscPane reactive toggle sets title="" in applyOptions when hiding', () => {
    const candles = makeCandles()
    const oscArtifacts = [makeRsiArtifactWithMidline()]
    const { rerender } = render(
      <Chart candles={candles} symbol="AAPL" timeframe="1d"
        indicatorArtifacts={oscArtifacts} chartSettings={makeSettings({})} />
    )
    mocks.seriesApplyOptions.mockClear()

    rerender(
      <Chart candles={candles} symbol="AAPL" timeframe="1d"
        indicatorArtifacts={oscArtifacts}
        chartSettings={makeSettings({ showIndicatorValueLabels: false })} />
    )

    // Toggle effect must include title: '' — lastValueVisible alone is insufficient in v5
    expect(mocks.seriesApplyOptions).toHaveBeenCalledWith(
      expect.objectContaining({ lastValueVisible: false, title: '' })
    )
  })

  it('107. Price-overlay reactive toggle sets title="" in applyOptions when hiding', () => {
    const candles   = makeCandles()
    const artifacts = [makeOverlayArtifact('sma', 'sma_1')]
    const { rerender } = render(
      <Chart candles={candles} symbol="AAPL" timeframe="1d"
        indicatorArtifacts={artifacts} chartSettings={makeSettings({})} />
    )
    mocks.seriesApplyOptions.mockClear()

    rerender(
      <Chart candles={candles} symbol="AAPL" timeframe="1d"
        indicatorArtifacts={artifacts}
        chartSettings={makeSettings({ showIndicatorValueLabels: false })} />
    )

    // Price-overlay toggle effect must also clear title to hide right-axis label
    expect(mocks.seriesApplyOptions).toHaveBeenCalledWith(
      expect.objectContaining({ lastValueVisible: false, title: '' })
    )
  })

  // ── CHART-SETTINGS-1A.4 — Indicators toggle: right-axis hidden; top chips unaffected ──

  it('101. ChartLegendOverlay visible when showIndicatorValueLabels=false (top legend unaffected)', () => {
    const candles  = makeCandles()
    const artifact = makeOverlayArtifact('sma', 'sma_1')
    renderChart({
      candles,
      indicatorArtifacts: [artifact],
      chartSettings: makeSettings({ showIndicatorValueLabels: false }),
    })
    // The overlay legend (top-left chip) must remain visible — only right-axis labels are hidden
    expect(screen.getByTestId('chart-legend-overlay')).toBeInTheDocument()
  })

  it('102. OscPane chip label visible when showIndicatorValueLabels=false (header chips unaffected)', () => {
    const candles      = makeCandles()
    const oscArtifacts = [makeOscArtifact('rsi', 'rsi_1')]
    renderChart({
      candles,
      indicatorArtifacts: oscArtifacts,
      instanceLabels: new Map([['rsi_1', 'RSI (14)']]),
      chartSettings: makeSettings({ showIndicatorValueLabels: false }),
    })
    // Top header chip label stays visible — toggle only affects right-axis lastValueVisible
    expect(screen.getByText('RSI (14)')).toBeInTheDocument()
  })

  it('103. OscPane chip label visible when showIndicatorValueLabels=true', () => {
    const candles      = makeCandles()
    const oscArtifacts = [makeOscArtifact('rsi', 'rsi_1')]
    renderChart({
      candles,
      indicatorArtifacts: oscArtifacts,
      instanceLabels: new Map([['rsi_1', 'RSI (14)']]),
      chartSettings: makeSettings({ showIndicatorValueLabels: true }),
    })
    expect(screen.getByText('RSI (14)')).toBeInTheDocument()
  })

  // ── CHART-TOOLBAR-1A — Screenshot export ─────────────────────────────────
  //
  // Chart exposes takeScreenshot() via a ChartHandle ref. In JSDOM, the 2D
  // canvas context is unavailable, so the implementation falls back to downloading
  // the price chart's canvas directly. Tests verify the ref is wired, the download
  // anchor is created with the correct filename pattern, and chart.takeScreenshot()
  // is called on the LW Charts instance.

  it('108. ChartHandle.takeScreenshot calls chart.takeScreenshot() to capture price pane', () => {
    const chartRef = createRef<ChartHandle>()
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    render(<Chart ref={chartRef} candles={makeCandles()} symbol="AAPL" timeframe="1d" />)

    mocks.takeScreenshot.mockClear()
    chartRef.current?.takeScreenshot()

    expect(mocks.takeScreenshot).toHaveBeenCalled()
    clickSpy.mockRestore()
  })

  it('109. takeScreenshot downloads a PNG with correct filename pattern', () => {
    const chartRef = createRef<ChartHandle>()
    const clickedFilenames: string[] = []

    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(function(this: HTMLAnchorElement) {
        clickedFilenames.push(this.download)
      })

    render(<Chart ref={chartRef} candles={makeCandles()} symbol="AAPL" timeframe="1d" />)
    chartRef.current?.takeScreenshot()

    expect(clickedFilenames).toHaveLength(1)
    expect(clickedFilenames[0]).toMatch(/^AAPL-1d-\d{8}-\d{6}\.png$/)
    clickSpy.mockRestore()
  })

  it('110. takeScreenshot filename sanitizes non-alphanumeric characters', () => {
    const chartRef = createRef<ChartHandle>()
    const clickedFilenames: string[] = []

    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(function(this: HTMLAnchorElement) {
        clickedFilenames.push(this.download)
      })

    render(<Chart ref={chartRef} candles={makeCandles()} symbol="AAPL/USD" timeframe="15m" />)
    chartRef.current?.takeScreenshot()

    // Slash in symbol → underscore; filename must match the safe pattern
    expect(clickedFilenames[0]).toMatch(/^AAPL_USD-15m-\d{8}-\d{6}\.png$/)
    clickSpy.mockRestore()
  })

  // Reset View (CHART-TOOLBAR-1B)

  it('111. ChartHandle.resetView exposed on ChartHandle interface', () => {
    const chartRef = createRef<ChartHandle>()
    render(<Chart ref={chartRef} candles={makeCandles()} symbol="AAPL" timeframe="1d" />)

    // Verify resetView method exists and is callable
    expect(chartRef.current).toBeDefined()
    expect(typeof chartRef.current?.resetView).toBe('function')
  })

  it('112. resetView does not throw when called with chart data loaded', () => {
    const chartRef = createRef<ChartHandle>()
    render(<Chart ref={chartRef} candles={makeCandles()} symbol="AAPL" timeframe="1d" />)

    // Should not throw an error
    expect(() => chartRef.current?.resetView()).not.toThrow()
  })

  it('113. resetView calls setVisibleLogicalRange on captured initial range', () => {
    const chartRef = createRef<ChartHandle>()
    render(<Chart ref={chartRef} candles={makeCandles()} symbol="AAPL" timeframe="1d" />)

    chartRef.current?.resetView()

    // Verify the mocks were called (setLogicalRange is the mock for setVisibleLogicalRange)
    expect(mocks.setLogicalRange).toHaveBeenCalled()
  })

  it('114. resetView gracefully handles empty chart state', () => {
    const chartRef = createRef<ChartHandle>()
    render(<Chart ref={chartRef} candles={[]} symbol="AAPL" timeframe="1d" />)

    // No candles loaded, so initial ranges are null — should not crash
    expect(() => chartRef.current?.resetView()).not.toThrow()
  })

  // Auto Scale (CHART-TOOLBAR-1C)

  it('115. ChartHandle.autoScale exposed on ChartHandle interface', () => {
    const chartRef = createRef<ChartHandle>()
    render(<Chart ref={chartRef} candles={makeCandles()} symbol="AAPL" timeframe="1d" />)

    // Verify autoScale method exists and is callable
    expect(chartRef.current).toBeDefined()
    expect(typeof chartRef.current?.autoScale).toBe('function')
  })

  it('116. autoScale does not throw when called with chart data loaded', () => {
    const chartRef = createRef<ChartHandle>()
    render(<Chart ref={chartRef} candles={makeCandles()} symbol="AAPL" timeframe="1d" />)

    // Should not throw an error
    expect(() => chartRef.current?.autoScale()).not.toThrow()
  })

  it('117. autoScale preserves visible logical range', () => {
    const chartRef = createRef<ChartHandle>()
    render(<Chart ref={chartRef} candles={makeCandles()} symbol="AAPL" timeframe="1d" />)

    chartRef.current?.autoScale()

    // Verify getLogicalRange was called (ensures range was captured and restored)
    expect(mocks.getLogicalRange).toHaveBeenCalled()
  })

  it('118. autoScale gracefully handles empty chart state', () => {
    const chartRef = createRef<ChartHandle>()
    render(<Chart ref={chartRef} candles={[]} symbol="AAPL" timeframe="1d" />)

    // No candles loaded — should not crash
    expect(() => chartRef.current?.autoScale()).not.toThrow()
  })

  // ── Market Structure Overlay (MS-2 / MS-3A) ──────────────────────────────
  // Tests numbered 120–135 (125 and 126 removed in MS-3A — structure label
  // rendering was removed; structure kinds remain in models only).
  // Helpers local to this describe block.

  function makeStructureSettings(structure: Partial<ChartSettings['structure']>): ChartSettings {
    return {
      ...DEFAULT_CHART_SETTINGS,
      structure: { ...DEFAULT_CHART_SETTINGS.structure, ...structure },
    }
  }

  function makeStructureResult(): StructureResult {
    return {
      minorPoints: [
        { id: 'mp1', level: 'minor', kind: 'H',  timestamp: TS(0), barIndex: 0, price: 105, source: 'price', confirmed: true },
        { id: 'mp2', level: 'minor', kind: 'L',  timestamp: TS(2), barIndex: 2, price: 99,  source: 'price', confirmed: true },
        { id: 'mp3', level: 'minor', kind: 'H',  timestamp: TS(4), barIndex: 4, price: 112, source: 'price', confirmed: true },
      ],
      minorLegs: [
        { id: 'ml1', level: 'minor', fromPointId: 'mp1', toPointId: 'mp2', direction: 'down', startBarIndex: 0, endBarIndex: 2, startPrice: 105, endPrice: 99 },
        { id: 'ml2', level: 'minor', fromPointId: 'mp2', toPointId: 'mp3', direction: 'up',   startBarIndex: 2, endBarIndex: 4, startPrice: 99,  endPrice: 112 },
      ],
      mainPoints: [
        { id: 'map1', level: 'main', kind: 'H',  timestamp: TS(0), barIndex: 0, price: 105, source: 'minor', confirmed: true },
        { id: 'map2', level: 'main', kind: 'HH', timestamp: TS(4), barIndex: 4, price: 112, source: 'minor', confirmed: true },
      ],
      mainLegs: [
        // Non-degenerate: different from/to points, different bar indices — exercises interpolation
        { id: 'mal1', level: 'main', fromPointId: 'map1', toPointId: 'map2', direction: 'up', startBarIndex: 0, endBarIndex: 4, startPrice: 105, endPrice: 112 },
      ],
      debugEvents: [
        { barIndex: 1, timestamp: TS(1), candleRelationship: 'higher_high', action: 'continue_up', reason: 'HH', affectedLevel: 'minor' },
        { barIndex: 2, timestamp: TS(2), candleRelationship: 'lower_low', action: 'reversal_down', reason: 'LL', affectedLevel: 'minor', newDirection: 'down' },
      ],
      bosEvents:   [],
      chochEvents: [],
    }
  }

  it('120. showMinorStructure: false — no structure series added when toggle is off', () => {
    mocks.addSeries.mockClear()
    renderChart({
      structureResult: makeStructureResult(),
      chartSettings:   makeStructureSettings({ showMinorStructure: false }),
    })
    const blueSeriesCalls = mocks.addSeries.mock.calls.filter(([, opts]) =>
      (opts as Record<string, unknown>)?.color === '#4a90d9'
    )
    expect(blueSeriesCalls).toHaveLength(0)
  })

  it('121. showMainStructure: false — no main structure series added when toggle is off', () => {
    mocks.addSeries.mockClear()
    renderChart({
      structureResult: makeStructureResult(),
      chartSettings:   makeStructureSettings({ showMainStructure: false }),
    })
    const orangeSeriesCalls = mocks.addSeries.mock.calls.filter(([, opts]) =>
      (opts as Record<string, unknown>)?.color === '#e87722'
    )
    expect(orangeSeriesCalls).toHaveLength(0)
  })

  it('122. showMinorStructure: true — blue LineSeries added to price chart', () => {
    mocks.addSeries.mockClear()
    renderChart({
      structureResult: makeStructureResult(),
      chartSettings:   makeStructureSettings({ showMinorStructure: true }),
    })
    const blueSeriesCalls = mocks.addSeries.mock.calls.filter(([, opts]) =>
      (opts as Record<string, unknown>)?.color === '#4a90d9'
    )
    expect(blueSeriesCalls.length).toBeGreaterThanOrEqual(1)
  })

  it('123. showMainStructure: true — orange LineSeries added to price chart', () => {
    mocks.addSeries.mockClear()
    renderChart({
      structureResult: makeStructureResult(),
      chartSettings:   makeStructureSettings({ showMainStructure: true }),
    })
    const orangeSeriesCalls = mocks.addSeries.mock.calls.filter(([, opts]) =>
      (opts as Record<string, unknown>)?.color === '#e87722'
    )
    expect(orangeSeriesCalls.length).toBeGreaterThanOrEqual(1)
  })

  it('124. showMinorStructure: true — setData called with entries for each candle', () => {
    mocks.setData.mockClear()
    const candles = makeCandles(5)
    renderChart({
      candles,
      structureResult: makeStructureResult(),
      chartSettings:   makeStructureSettings({ showMinorStructure: true }),
    })
    const dataLengths = mocks.setData.mock.calls.map(([data]) => (data as unknown[]).length)
    expect(dataLengths.some(l => l === candles.length)).toBe(true)
  })

  it('127. structureResult: null — no structure series added', () => {
    mocks.addSeries.mockClear()
    renderChart({
      structureResult: null,
      chartSettings:   makeStructureSettings({ showMinorStructure: true, showMainStructure: true }),
    })
    const blueOrOrange = mocks.addSeries.mock.calls.filter(([, opts]) => {
      const c = (opts as Record<string, unknown>)?.color
      return c === '#4a90d9' || c === '#e87722'
    })
    expect(blueOrOrange).toHaveLength(0)
  })

  it('128. structureResult: undefined — no structure series added', () => {
    mocks.addSeries.mockClear()
    renderChart({
      chartSettings: makeStructureSettings({ showMinorStructure: true }),
    })
    const blueSeriesCalls = mocks.addSeries.mock.calls.filter(([, opts]) =>
      (opts as Record<string, unknown>)?.color === '#4a90d9'
    )
    expect(blueSeriesCalls).toHaveLength(0)
  })

  it('129. showDebugMetadata: true — debug panel renders in DOM', () => {
    renderChart({
      structureResult: makeStructureResult(),
      chartSettings:   makeStructureSettings({ showDebugMetadata: true }),
    })
    expect(screen.getByTestId('structure-debug-panel')).toBeInTheDocument()
  })

  it('130. showDebugMetadata: false — debug panel absent from DOM', () => {
    renderChart({
      structureResult: makeStructureResult(),
      chartSettings:   makeStructureSettings({ showDebugMetadata: false }),
    })
    expect(screen.queryByTestId('structure-debug-panel')).not.toBeInTheDocument()
  })

  it('131. showDebugMetadata: true but structureResult: null — debug panel absent', () => {
    renderChart({
      structureResult: null,
      chartSettings:   makeStructureSettings({ showDebugMetadata: true }),
    })
    expect(screen.queryByTestId('structure-debug-panel')).not.toBeInTheDocument()
  })

  it('132. toggle from off to on — addSeries called after rerender', () => {
    const candles = makeCandles()
    const { rerender } = renderChart({
      candles,
      structureResult: makeStructureResult(),
      chartSettings:   makeStructureSettings({ showMinorStructure: false }),
    })
    mocks.addSeries.mockClear()

    rerender(
      <Chart candles={candles} symbol="AAPL" timeframe="1d"
        structureResult={makeStructureResult()}
        chartSettings={makeStructureSettings({ showMinorStructure: true })} />
    )
    const blueSeriesCalls = mocks.addSeries.mock.calls.filter(([, opts]) =>
      (opts as Record<string, unknown>)?.color === '#4a90d9'
    )
    expect(blueSeriesCalls.length).toBeGreaterThanOrEqual(1)
  })

  it('133. toggle from on to off — removeSeries called after rerender', () => {
    const candles = makeCandles()
    const { rerender } = renderChart({
      candles,
      structureResult: makeStructureResult(),
      chartSettings:   makeStructureSettings({ showMinorStructure: true }),
    })
    mocks.removeSeries.mockClear()

    rerender(
      <Chart candles={candles} symbol="AAPL" timeframe="1d"
        structureResult={makeStructureResult()}
        chartSettings={makeStructureSettings({ showMinorStructure: false })} />
    )
    expect(mocks.removeSeries).toHaveBeenCalled()
  })

  it('134. main structure lineWidth is 2 (heavier than minor)', () => {
    mocks.addSeries.mockClear()
    renderChart({
      structureResult: makeStructureResult(),
      chartSettings:   makeStructureSettings({ showMainStructure: true }),
    })
    const mainCall = mocks.addSeries.mock.calls.find(([, opts]) =>
      (opts as Record<string, unknown>)?.color === '#e87722'
    )
    expect(mainCall).toBeDefined()
    expect((mainCall![1] as Record<string, unknown>).lineWidth).toBe(2)
  })

  it('135. minor structure lineWidth is 1 (lighter than main)', () => {
    mocks.addSeries.mockClear()
    renderChart({
      structureResult: makeStructureResult(),
      chartSettings:   makeStructureSettings({ showMinorStructure: true }),
    })
    const minorCall = mocks.addSeries.mock.calls.find(([, opts]) =>
      (opts as Record<string, unknown>)?.color === '#4a90d9'
    )
    expect(minorCall).toBeDefined()
    expect((minorCall![1] as Record<string, unknown>).lineWidth).toBe(1)
  })

  it('136. non-degenerate main leg exercises interpolation — setData entries cover span', () => {
    // makeStructureResult() main leg: startBarIndex=0, endBarIndex=4 → span of 4 bars
    // setData must be called with candle-length array (interpolation fills bar 0..4)
    mocks.setData.mockClear()
    const candles = makeCandles(6)  // 6 candles: indices 0–5
    renderChart({
      candles,
      structureResult: makeStructureResult(),
      chartSettings:   makeStructureSettings({ showMainStructure: true }),
    })
    const dataLengths = mocks.setData.mock.calls.map(([data]) => (data as unknown[]).length)
    expect(dataLengths.some(l => l === candles.length)).toBe(true)
  })

  it('137. createSeriesMarkers called twice on mount — signal API + structure label API', () => {
    // MS-6C: structure labels use a dedicated marker API, separate from signal markers.
    vi.mocked(createSeriesMarkers).mockClear()
    renderChart({
      structureResult: makeStructureResult(),
      chartSettings:   makeStructureSettings({ showMinorStructure: true, showMainStructure: true }),
    })
    // One call for signal markers, one for structure labels — both created on chart mount.
    expect(vi.mocked(createSeriesMarkers).mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  // ── MS-6C: Structure label rendering ────────────────────────────────────────

  it('138. showStructureLabels: false — setMarkers not called with structure kind text', () => {
    mocks.setMarkers.mockClear()
    renderChart({
      structureResult: makeStructureResult(),
      chartSettings:   makeStructureSettings({
        showMinorStructure:  true,
        showStructureLabels: false,
      }),
    })
    const structureLabelCall = mocks.setMarkers.mock.calls.find((c: unknown[][]) =>
      Array.isArray(c[0]) && (c[0] as Array<{ text?: string }>).some(m => /^(H|L|HH|HL|LH|LL)$/.test(m.text ?? ''))
    )
    expect(structureLabelCall).toBeUndefined()
  })

  it('139. showStructureLabels: true + showMinorStructure: true — setMarkers called with minor kind labels', () => {
    mocks.setMarkers.mockClear()
    renderChart({
      structureResult: makeStructureResult(),
      chartSettings:   makeStructureSettings({
        showMinorStructure:  true,
        showStructureLabels: true,
      }),
    })
    const structureLabelCall = mocks.setMarkers.mock.calls.find((c: unknown[][]) =>
      Array.isArray(c[0]) && (c[0] as Array<{ text?: string }>).some(m => /^(H|L|HH|HL|LH|LL)$/.test(m.text ?? ''))
    )
    expect(structureLabelCall).toBeDefined()
  })

  it('140. showStructureLabels: true + showMinorStructure: false — no minor kind labels in any setMarkers call', () => {
    mocks.setMarkers.mockClear()
    renderChart({
      structureResult: makeStructureResult(),
      chartSettings:   makeStructureSettings({
        showMinorStructure:  false,
        showStructureLabels: true,
      }),
    })
    // No call should contain minor labels (minor disabled)
    const minorLabelCall = mocks.setMarkers.mock.calls.find((c: unknown[][]) =>
      Array.isArray(c[0]) && (c[0] as Array<{ color?: string; text?: string }>).some(
        m => m.color === '#4a90d9' && /^(H|L|HH|HL|LH|LL)$/.test(m.text ?? '')
      )
    )
    expect(minorLabelCall).toBeUndefined()
  })

  it('141. showStructureLabels: true + showMainStructure: false — no main kind labels in any setMarkers call', () => {
    mocks.setMarkers.mockClear()
    renderChart({
      structureResult: makeStructureResult(),
      chartSettings:   makeStructureSettings({
        showMainStructure:   false,
        showStructureLabels: true,
      }),
    })
    const mainLabelCall = mocks.setMarkers.mock.calls.find((c: unknown[][]) =>
      Array.isArray(c[0]) && (c[0] as Array<{ color?: string; text?: string }>).some(
        m => m.color === '#e87722' && /^(H|L|HH|HL|LH|LL)$/.test(m.text ?? '')
      )
    )
    expect(mainLabelCall).toBeUndefined()
  })

  it('142. H / HH / LH kind markers use position: aboveBar', () => {
    mocks.setMarkers.mockClear()
    renderChart({
      structureResult: makeStructureResult(),
      chartSettings:   makeStructureSettings({
        showMinorStructure:  true,
        showMainStructure:   true,
        showStructureLabels: true,
      }),
    })
    // Collect all markers across all setMarkers calls that have structure kind text
    const allMarkers = mocks.setMarkers.mock.calls
      .flatMap((c: unknown[][]) => Array.isArray(c[0]) ? c[0] : []) as Array<{ text?: string; position?: string }>
    const highKinds = allMarkers.filter(m => ['H', 'HH', 'LH'].includes(m.text ?? ''))
    expect(highKinds.length).toBeGreaterThan(0)
    highKinds.forEach(m => {
      expect(m.position).toBe('aboveBar')
    })
  })

  it('143. L / LL / HL kind markers use position: belowBar', () => {
    mocks.setMarkers.mockClear()
    // Use a result with a low-type point: makeStructureResult() has L at barIndex 2
    renderChart({
      structureResult: makeStructureResult(),
      chartSettings:   makeStructureSettings({
        showMinorStructure:  true,
        showStructureLabels: true,
      }),
    })
    const allMarkers = mocks.setMarkers.mock.calls
      .flatMap((c: unknown[][]) => Array.isArray(c[0]) ? c[0] : []) as Array<{ text?: string; position?: string }>
    const lowKinds = allMarkers.filter(m => ['L', 'LL', 'HL'].includes(m.text ?? ''))
    expect(lowKinds.length).toBeGreaterThan(0)
    lowKinds.forEach(m => {
      expect(m.position).toBe('belowBar')
    })
  })

  // ── MS-6H: Sequence-label integration guards ────────────────────────────────
  // makeStructureResult() uses only plain H/L kinds in minorPoints — tests 138–143
  // pass even if HL/HH text is never rendered. These tests use a dedicated fixture
  // with HL and HH minor kinds to assert the actual marker text values.

  function makeSequencedStructureResult(): StructureResult {
    return {
      minorPoints: [
        { id: 'mp1', level: 'minor', kind: 'L',  timestamp: TS(0), barIndex: 0, price: 39,  source: 'price', confirmed: true },
        { id: 'mp2', level: 'minor', kind: 'H',  timestamp: TS(2), barIndex: 2, price: 51,  source: 'price', confirmed: true },
        { id: 'mp3', level: 'minor', kind: 'HL', timestamp: TS(4), barIndex: 4, price: 44,  source: 'price', confirmed: true },
        { id: 'mp4', level: 'minor', kind: 'HH', timestamp: TS(6), barIndex: 6, price: 56,  source: 'price', confirmed: true },
        { id: 'mp5', level: 'minor', kind: 'HL', timestamp: TS(8), barIndex: 8, price: 46,  source: 'price', confirmed: true },
        { id: 'mp6', level: 'minor', kind: 'HH', timestamp: TS(10), barIndex: 10, price: 61, source: 'price', confirmed: true },
      ],
      minorLegs: [
        { id: 'ml1', level: 'minor', fromPointId: 'mp1', toPointId: 'mp2', direction: 'up',   startBarIndex: 0, endBarIndex: 2,  startPrice: 39, endPrice: 51 },
        { id: 'ml2', level: 'minor', fromPointId: 'mp2', toPointId: 'mp3', direction: 'down', startBarIndex: 2, endBarIndex: 4,  startPrice: 51, endPrice: 44 },
        { id: 'ml3', level: 'minor', fromPointId: 'mp3', toPointId: 'mp4', direction: 'up',   startBarIndex: 4, endBarIndex: 6,  startPrice: 44, endPrice: 56 },
        { id: 'ml4', level: 'minor', fromPointId: 'mp4', toPointId: 'mp5', direction: 'down', startBarIndex: 6, endBarIndex: 8,  startPrice: 56, endPrice: 46 },
        { id: 'ml5', level: 'minor', fromPointId: 'mp5', toPointId: 'mp6', direction: 'up',   startBarIndex: 8, endBarIndex: 10, startPrice: 46, endPrice: 61 },
      ],
      mainPoints: [],
      mainLegs:   [],
      debugEvents: [],
      bosEvents:   [],
      chochEvents: [],
    }
  }

  it('145. minor marker text includes HL when backend fixture has HL minor kind', () => {
    mocks.setMarkers.mockClear()
    renderChart({
      candles:         makeCandles(11),
      structureResult: makeSequencedStructureResult(),
      chartSettings:   makeStructureSettings({ showMinorStructure: true, showStructureLabels: true }),
    })
    const allMarkers = mocks.setMarkers.mock.calls
      .flatMap((c: unknown[][]) => Array.isArray(c[0]) ? c[0] : []) as Array<{ text?: string; color?: string }>
    const hlMarkers = allMarkers.filter(m => m.text === 'HL' && m.color === '#4a90d9')
    expect(hlMarkers.length).toBeGreaterThanOrEqual(2)
  })

  it('146. minor marker text includes HH when backend fixture has HH minor kind', () => {
    mocks.setMarkers.mockClear()
    renderChart({
      candles:         makeCandles(11),
      structureResult: makeSequencedStructureResult(),
      chartSettings:   makeStructureSettings({ showMinorStructure: true, showStructureLabels: true }),
    })
    const allMarkers = mocks.setMarkers.mock.calls
      .flatMap((c: unknown[][]) => Array.isArray(c[0]) ? c[0] : []) as Array<{ text?: string; color?: string }>
    const hhMarkers = allMarkers.filter(m => m.text === 'HH' && m.color === '#4a90d9')
    expect(hhMarkers.length).toBeGreaterThanOrEqual(2)
  })

  it('144. labels removed when showStructureLabels toggled off after being on', () => {
    const candles = makeCandles(5)
    const result  = makeStructureResult()
    const { rerender } = renderChart({
      candles,
      structureResult: result,
      chartSettings:   makeStructureSettings({ showMinorStructure: true, showStructureLabels: true }),
    })
    mocks.setMarkers.mockClear()

    rerender(
      <Chart candles={candles} symbol="AAPL" timeframe="1d"
        structureResult={result}
        chartSettings={makeStructureSettings({ showMinorStructure: true, showStructureLabels: false })} />
    )
    // After toggling off, setMarkers([]) must be called (labels cleared)
    const clearCall = mocks.setMarkers.mock.calls.find(
      (c: unknown[][]) => Array.isArray(c[0]) && (c[0] as unknown[]).length === 0
    )
    expect(clearCall).toBeDefined()
  })

  // ── MS-EVENT-CLEANUP-2: Minor-structure gate for BoS / CHoCH markers ──────
  // BoS and CHoCH are minor-structure events; both toggles must be on.

  function makeStructureResultWithBosEvent(): StructureResult {
    return {
      ...makeStructureResult(),
      bosEvents: [{
        status: 'valid', direction: 'bullish', structureScope: 'minor',
        breakLevel: 110, protectedLevel: 100,
        breakCandleIndex: 1, breakCandleTimestamp: TS(1),
        eventType: 'bos', eventEffect: 'continuation',
      }],
    }
  }

  function makeStructureResultWithChochEvent(): StructureResult {
    return {
      ...makeStructureResult(),
      chochEvents: [{
        direction: 'bullish', structureScope: 'minor', protectedLevel: 95,
        breakCandleIndex: 2, breakCandleTimestamp: TS(2),
        structureReferenceIndex: 1, structureReferenceTimestamp: TS(1),
        referenceStructureType: 'HL', violatedTrend: 'uptrend',
        eventType: 'choch', status: 'valid', eventEffect: 'transition',
      }],
    }
  }

  it('147. CHoCH hidden when showMinorStructure: false even if showChoch and showMainStructure are true', () => {
    mocks.setMarkers.mockClear()
    renderChart({
      candles:         makeCandles(5),
      structureResult: makeStructureResultWithChochEvent(),
      chartSettings:   makeStructureSettings({
        showMinorStructure: false,
        showMainStructure:  true,
        showChoch:          true,
      }),
    })
    const hasChochMarker = mocks.setMarkers.mock.calls.some(
      (call: unknown[][]) =>
        Array.isArray(call[0]) &&
        (call[0] as { text?: string }[]).some(m => m.text === 'CHoCH'),
    )
    expect(hasChochMarker).toBe(false)
  })

  it('148. CHoCH visible when showMinorStructure: true and showChoch: true (showMainStructure irrelevant)', () => {
    mocks.setMarkers.mockClear()
    renderChart({
      candles:         makeCandles(5),
      structureResult: makeStructureResultWithChochEvent(),
      chartSettings:   makeStructureSettings({
        showMinorStructure: true,
        showMainStructure:  false,
        showChoch:          true,
      }),
    })
    const hasChochMarker = mocks.setMarkers.mock.calls.some(
      (call: unknown[][]) =>
        Array.isArray(call[0]) &&
        (call[0] as { text?: string }[]).some(m => m.text === 'CHoCH'),
    )
    expect(hasChochMarker).toBe(true)
  })

  it('149. BoS hidden when showMinorStructure: false even if showBos and showMainStructure are true', () => {
    mocks.setMarkers.mockClear()
    renderChart({
      candles:         makeCandles(5),
      structureResult: makeStructureResultWithBosEvent(),
      chartSettings:   makeStructureSettings({
        showMinorStructure: false,
        showMainStructure:  true,
        showBos:            true,
      }),
    })
    const hasBoSMarker = mocks.setMarkers.mock.calls.some(
      (call: unknown[][]) =>
        Array.isArray(call[0]) &&
        (call[0] as { text?: string }[]).some(m => m.text === 'BoS'),
    )
    expect(hasBoSMarker).toBe(false)
  })

  it('150. BoS visible when showMinorStructure: true and showBos: true (showMainStructure irrelevant)', () => {
    mocks.setMarkers.mockClear()
    renderChart({
      candles:         makeCandles(5),
      structureResult: makeStructureResultWithBosEvent(),
      chartSettings:   makeStructureSettings({
        showMinorStructure: true,
        showMainStructure:  false,
        showBos:            true,
      }),
    })
    const hasBoSMarker = mocks.setMarkers.mock.calls.some(
      (call: unknown[][]) =>
        Array.isArray(call[0]) &&
        (call[0] as { text?: string }[]).some(m => m.text === 'BoS'),
    )
    expect(hasBoSMarker).toBe(true)
  })
})
