/**
 * ChartDataInspector.test.tsx — CHART-UX-4A.3.
 *
 * Coverage:
 *  1.  Inspector renders with symbol / timeframe / exchange in meta
 *  2.  Inspector renders without exchange gracefully
 *  3.  No candle → only meta row rendered (no OHLC)
 *  4.  Latest candle OHLC values rendered correctly
 *  5.  Positive change renders green color
 *  6.  Negative change renders red color
 *  7.  Zero change renders green (change >= 0 boundary)
 *  8.  First candle (no change) — inspector shows OHLC without change string
 *  9.  Volume NOT shown in OHLC header (volume removed per CHART-UX-4A.3)
 * 10.  Volume NOT shown regardless of candle volume size
 * 11.  Volume NOT shown for sub-1000 volume
 * 12.  Volume NOT shown when volume === 0
 * 13.  Indicator rows NOT rendered (values shown in chart overlays)
 * 14.  Indicator rows absent even when indicatorArtifacts provided
 * 15.  Multi-series indicator rows NOT rendered
 * 16.  Hidden indicator instance not rendered (inspector-indicators absent)
 * 17.  No date/time in inspector output
 * 18.  Inspector renders when indicatorArtifacts is undefined
 * 19.  Inspector renders when indicatorValues is undefined — no indicator row
 * 20.  fmtVolume helper: 0 → "0", 999 → "999", 1000 → "1.00K", 1_500_000 → "1.50M"
 */

import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import ChartDataInspector, { fmtVolume, type InspectorCandle, type InspectorIndicatorValues } from '../ChartDataInspector'
import type { IndicatorArtifactResponse } from '../../types/chartIndicators'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeCandle(overrides: Partial<InspectorCandle> = {}): InspectorCandle {
  return {
    open:   47.00,
    high:   48.50,
    low:    45.00,
    close:  47.00,
    volume: 2_345,
    change:    -1.00,
    changePct: -2.08,
    ...overrides,
  }
}

function makeArtifact(
  instanceId: string,
  seriesId: string = 'close',
  pane: 'price_overlay' | 'oscillator_pane' = 'price_overlay',
): IndicatorArtifactResponse {
  return {
    tool_id:      'ema',
    instance_id:  instanceId,
    display_name: 'EMA',
    pane:         'price',
    render_type:  'line',
    parameters:   { period: 21 },
    series: [{
      series_id:     seriesId,
      label:         'EMA 21',
      pane,
      render_type:   'line',
      default_color: '#2196f3',
      values:        [],
    }],
    warmup_bars: 20,
    diagnostics: {},
  }
}

// ---------------------------------------------------------------------------
// 1–3. Basic render
// ---------------------------------------------------------------------------

describe('ChartDataInspector', () => {
  it('1. renders symbol / timeframe / exchange in meta', () => {
    render(
      <ChartDataInspector
        symbol="AAPL" timeframe="1D" exchange="NASDAQ"
        candle={makeCandle()}
      />
    )
    expect(screen.getByTestId('inspector-meta').textContent).toContain('AAPL')
    expect(screen.getByTestId('inspector-meta').textContent).toContain('1D')
    expect(screen.getByTestId('inspector-meta').textContent).toContain('NASDAQ')
  })

  it('2. renders without exchange gracefully', () => {
    render(<ChartDataInspector symbol="BTCUSD" timeframe="4H" candle={makeCandle()} />)
    const meta = screen.getByTestId('inspector-meta').textContent ?? ''
    expect(meta).toContain('BTCUSD')
    expect(meta).not.toContain('NASDAQ')
  })

  it('3. no candle → only meta rendered (no OHLC spans)', () => {
    render(<ChartDataInspector symbol="AAPL" timeframe="1D" candle={null} />)
    expect(screen.getByTestId('chart-data-inspector')).toBeTruthy()
    expect(screen.queryByTestId('inspector-open')).toBeNull()
    expect(screen.queryByTestId('inspector-close')).toBeNull()
  })

  // ── 4. OHLC token text and unified movementColor ──────────────────────────

  it('4. all OHLC tokens rendered as label+value pairs', () => {
    render(<ChartDataInspector symbol="AAPL" timeframe="1D" candle={makeCandle()} />)
    expect(screen.getByTestId('inspector-open').textContent).toBe('O 47.00')
    expect(screen.getByTestId('inspector-high').textContent).toBe('H 48.50')
    expect(screen.getByTestId('inspector-low').textContent).toBe('L 45.00')
    expect(screen.getByTestId('inspector-close').textContent).toBe('C 47.00')
  })

  it('4b. bullish candle — all OHLC tokens are green', () => {
    render(<ChartDataInspector symbol="A" timeframe="1D"
      candle={makeCandle({ change: 1.0, changePct: 2.0 })} />)
    const green = 'rgb(38, 166, 154)'  // #26a69a
    expect((screen.getByTestId('inspector-open')  as HTMLElement).style.color).toBe(green)
    expect((screen.getByTestId('inspector-high')  as HTMLElement).style.color).toBe(green)
    expect((screen.getByTestId('inspector-low')   as HTMLElement).style.color).toBe(green)
    expect((screen.getByTestId('inspector-close') as HTMLElement).style.color).toBe(green)
  })

  it('4c. bearish candle — all OHLC tokens are red', () => {
    render(<ChartDataInspector symbol="A" timeframe="1D"
      candle={makeCandle({ change: -1.0, changePct: -2.08 })} />)
    const red = 'rgb(239, 83, 80)'    // #ef5350
    expect((screen.getByTestId('inspector-open')  as HTMLElement).style.color).toBe(red)
    expect((screen.getByTestId('inspector-high')  as HTMLElement).style.color).toBe(red)
    expect((screen.getByTestId('inspector-low')   as HTMLElement).style.color).toBe(red)
    expect((screen.getByTestId('inspector-close') as HTMLElement).style.color).toBe(red)
  })

  it('4d. zero-change candle — all OHLC tokens are green (change >= 0 boundary)', () => {
    render(<ChartDataInspector symbol="A" timeframe="1D"
      candle={makeCandle({ change: 0, changePct: 0 })} />)
    const green = 'rgb(38, 166, 154)'
    expect((screen.getByTestId('inspector-open')  as HTMLElement).style.color).toBe(green)
    expect((screen.getByTestId('inspector-close') as HTMLElement).style.color).toBe(green)
  })

  it('4e. first candle (no prevClose) — all OHLC tokens are neutral', () => {
    render(<ChartDataInspector symbol="A" timeframe="1D"
      candle={makeCandle({ change: undefined, changePct: undefined })} />)
    const neutral = 'rgb(136, 146, 164)'  // #8892a4
    expect((screen.getByTestId('inspector-open')  as HTMLElement).style.color).toBe(neutral)
    expect((screen.getByTestId('inspector-high')  as HTMLElement).style.color).toBe(neutral)
    expect((screen.getByTestId('inspector-low')   as HTMLElement).style.color).toBe(neutral)
    expect((screen.getByTestId('inspector-close') as HTMLElement).style.color).toBe(neutral)
  })

  // ── 5–7. Change token follows movementColor ───────────────────────────────

  it('5. positive change — change token is green, all OHLC green', () => {
    render(<ChartDataInspector symbol="A" timeframe="1D"
      candle={makeCandle({ change: 1.5, changePct: 3.2 })} />)
    const el = screen.getByTestId('inspector-change')
    expect(el.textContent).toContain('+1.50')
    expect((el as HTMLElement).style.color).toBe('rgb(38, 166, 154)')
  })

  it('6. negative change — change token is red, all OHLC red', () => {
    render(<ChartDataInspector symbol="A" timeframe="1D"
      candle={makeCandle({ change: -1.0, changePct: -2.08 })} />)
    const el = screen.getByTestId('inspector-change')
    expect(el.textContent).toContain('-1.00')
    expect((el as HTMLElement).style.color).toBe('rgb(239, 83, 80)')
  })

  it('7. zero change — change token is green (change >= 0)', () => {
    render(<ChartDataInspector symbol="A" timeframe="1D"
      candle={makeCandle({ change: 0, changePct: 0 })} />)
    const el = screen.getByTestId('inspector-change')
    expect((el as HTMLElement).style.color).toBe('rgb(38, 166, 154)')
  })

  // ── 8. First candle (no previous close) ──────────────────────────────────

  it('8. first candle — no change string, OHLC still rendered', () => {
    render(<ChartDataInspector symbol="A" timeframe="1D"
      candle={makeCandle({ change: undefined, changePct: undefined })} />)
    expect(screen.queryByTestId('inspector-change')).toBeNull()
    expect(screen.getByTestId('inspector-open')).toBeTruthy()
  })

  // ── 9–12. Volume not shown (CHART-UX-4A.3: removed to reduce header clutter) ──

  it('9. volume not shown in OHLC header (K-range volume)', () => {
    render(<ChartDataInspector symbol="A" timeframe="1D" candle={makeCandle({ volume: 3_130 })} />)
    expect(screen.queryByTestId('inspector-volume')).toBeNull()
  })

  it('10. volume not shown in OHLC header (M-range volume)', () => {
    render(<ChartDataInspector symbol="A" timeframe="1D" candle={makeCandle({ volume: 1_500_000 })} />)
    expect(screen.queryByTestId('inspector-volume')).toBeNull()
  })

  it('11. volume not shown in OHLC header (sub-1000 volume)', () => {
    render(<ChartDataInspector symbol="A" timeframe="1D" candle={makeCandle({ volume: 750 })} />)
    expect(screen.queryByTestId('inspector-volume')).toBeNull()
  })

  it('12. volume not shown when volume === 0', () => {
    render(<ChartDataInspector symbol="A" timeframe="1D" candle={makeCandle({ volume: 0 })} />)
    expect(screen.queryByTestId('inspector-volume')).toBeNull()
  })

  // ── 13–16. Indicator rows absent (CHART-UX-4A.3) ─────────────────────────
  // Indicator values are shown in chart overlays/legends — not duplicated here.

  it('13. indicator rows not rendered when indicatorArtifacts provided', () => {
    const artifact = makeArtifact('inst-001', 'close')
    const indVals: InspectorIndicatorValues = new Map([
      ['inst-001', new Map([['close', 58.56]])],
    ])
    render(
      <ChartDataInspector
        symbol="A" timeframe="1D"
        candle={makeCandle()}
        indicatorArtifacts={[artifact]}
        instanceLabels={new Map([['inst-001', 'EMA 21 close']])}
        instanceColors={new Map([['inst-001', '#2196f3']])}
        indicatorValues={indVals}
      />
    )
    expect(screen.queryByTestId('inspector-indicators')).toBeNull()
    expect(screen.queryByTestId('inspector-ind-inst-001')).toBeNull()
    expect(screen.queryByTestId('inspector-ind-val-inst-001')).toBeNull()
  })

  it('14. indicator rows absent even for null / warmup values', () => {
    const artifact = makeArtifact('inst-002', 'close')
    const indVals: InspectorIndicatorValues = new Map([
      ['inst-002', new Map([['close', null]])],
    ])
    render(
      <ChartDataInspector
        symbol="A" timeframe="1D"
        candle={makeCandle()}
        indicatorArtifacts={[artifact]}
        indicatorValues={indVals}
      />
    )
    expect(screen.queryByTestId('inspector-indicators')).toBeNull()
    expect(screen.queryByTestId('inspector-ind-val-inst-002')).toBeNull()
  })

  it('15. multi-series indicator rows not rendered', () => {
    const artifact: IndicatorArtifactResponse = {
      tool_id:      'macd',
      instance_id:  'inst-macd',
      display_name: 'MACD',
      pane:         'oscillator',
      render_type:  'line',
      parameters:   {},
      series: [
        { series_id: 'macd',   label: 'MACD',   pane: 'oscillator_pane', render_type: 'line',      default_color: '#2196f3', values: [] },
        { series_id: 'signal', label: 'Signal', pane: 'oscillator_pane', render_type: 'line',      default_color: '#ff9800', values: [] },
        { series_id: 'hist',   label: 'Hist',   pane: 'oscillator_pane', render_type: 'histogram', default_color: '#4caf50', values: [] },
      ],
      warmup_bars: 26,
      diagnostics: {},
    }
    const indVals: InspectorIndicatorValues = new Map([
      ['inst-macd', new Map([
        ['macd',   -0.31],
        ['signal', -0.20],
        ['hist',   -0.11],
      ])],
    ])
    render(
      <ChartDataInspector
        symbol="A" timeframe="1D"
        candle={makeCandle()}
        indicatorArtifacts={[artifact]}
        instanceLabels={new Map([['inst-macd', 'MACD']])}
        indicatorValues={indVals}
      />
    )
    expect(screen.queryByTestId('inspector-indicators')).toBeNull()
    expect(screen.queryByTestId('inspector-ind-val-inst-macd')).toBeNull()
  })

  it('16. hidden indicator instance — inspector-indicators area absent', () => {
    const artifact = makeArtifact('inst-hidden', 'close')
    render(
      <ChartDataInspector
        symbol="A" timeframe="1D"
        candle={makeCandle()}
        indicatorArtifacts={[artifact]}
        instanceVisible={new Map([['inst-hidden', false]])}
      />
    )
    expect(screen.queryByTestId('inspector-indicators')).toBeNull()
    expect(screen.queryByTestId('inspector-ind-inst-hidden')).toBeNull()
  })

  // ── 17. No date/time ──────────────────────────────────────────────────────

  it('17. no date/time rendered in inspector output', () => {
    render(
      <ChartDataInspector
        symbol="AAPL" timeframe="1D" exchange="NASDAQ"
        candle={makeCandle()}
      />
    )
    const text = screen.getByTestId('chart-data-inspector').textContent ?? ''
    expect(text).not.toMatch(/\b20\d{2}\b/)
    expect(text).not.toMatch(/\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b/)
    expect(text).not.toMatch(/\d{2}:\d{2}/)
  })

  // ── 18–19. Edge cases ────────────────────────────────────────────────────

  it('18. renders when indicatorArtifacts is undefined', () => {
    render(<ChartDataInspector symbol="A" timeframe="1D" candle={makeCandle()} />)
    expect(screen.getByTestId('inspector-open')).toBeTruthy()
    expect(screen.queryByTestId('inspector-indicators')).toBeNull()
  })

  it('19. renders when indicatorValues is undefined — no indicator row shown', () => {
    const artifact = makeArtifact('inst-noval', 'close')
    render(
      <ChartDataInspector
        symbol="A" timeframe="1D"
        candle={makeCandle()}
        indicatorArtifacts={[artifact]}
        indicatorValues={undefined}
      />
    )
    expect(screen.queryByTestId('inspector-indicators')).toBeNull()
    expect(screen.queryByTestId('inspector-ind-val-inst-noval')).toBeNull()
    // OHLC header still renders correctly
    expect(screen.getByTestId('inspector-open')).toBeTruthy()
  })

  // ── 20. fmtVolume unit tests (helper retained for future use) ─────────────

  describe('fmtVolume', () => {
    it('20a. 0 → "0"',           () => expect(fmtVolume(0)).toBe('0'))
    it('20b. 999 → "999"',       () => expect(fmtVolume(999)).toBe('999'))
    it('20c. 1000 → "1.00K"',    () => expect(fmtVolume(1000)).toBe('1.00K'))
    it('20d. 1500 → "1.50K"',    () => expect(fmtVolume(1500)).toBe('1.50K'))
    it('20e. 999999 → "1000.00K"', () => expect(fmtVolume(999_999)).toBe('1000.00K'))
    it('20f. 1_000_000 → "1.00M"', () => expect(fmtVolume(1_000_000)).toBe('1.00M'))
    it('20g. 1_500_000 → "1.50M"', () => expect(fmtVolume(1_500_000)).toBe('1.50M'))
  })
})
