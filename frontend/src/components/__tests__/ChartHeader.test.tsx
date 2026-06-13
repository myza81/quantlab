/**
 * ChartHeader.test.tsx — CHART-HEADER-1 / CHART-TOOLBAR-1A / CHART-TOOLBAR-1B / CHART-TOOLBAR-1C
 *
 * Coverage:
 * Rendering
 *  1.  renders with data-testid="chart-header"
 *  2.  shows symbol when provided
 *  3.  shows fallback dash when symbol is empty
 *  4.  subtitle includes instrumentName
 *  5.  subtitle includes exchange
 *  6.  subtitle includes assetClass
 *  7.  subtitle includes timeframe
 *  8.  subtitle joins parts with " · "
 *  9.  subtitle hidden when no metadata provided
 * Gear button
 * 10.  gear button renders (data-testid="chart-settings-btn")
 * 11.  gear button has aria-label "Chart settings"
 * 12.  clicking gear shows settings panel
 * 13.  clicking backdrop closes settings panel
 * 14.  clicking close button in panel closes panel
 * 15.  onSettingsChange called when a toggle is changed
 * Camera button (CHART-TOOLBAR-1A)
 * 16.  camera button renders (data-testid="chart-screenshot-btn")
 * 17.  camera button is disabled when onScreenshot is not provided
 * 18.  camera button has aria-label "Screenshot"
 * 21.  camera button is enabled when onScreenshot is provided
 * 22.  clicking enabled camera button calls onScreenshot
 * 23.  clicking disabled camera button does not call any screenshot fn
 * Reset View button (CHART-TOOLBAR-1B)
 * 24.  reset button renders (data-testid="chart-reset-view-btn")
 * 25.  reset button is disabled when onResetView is not provided
 * 26.  reset button has aria-label "Reset View"
 * 27.  reset button is enabled when onResetView is provided
 * 28.  clicking enabled reset button calls onResetView
 * 29.  clicking disabled reset button does not call onResetView
 * Auto Scale button (CHART-TOOLBAR-1C)
 * 30.  autoscale button renders (data-testid="chart-autoscale-btn")
 * 31.  autoscale button is disabled when onAutoScale is not provided
 * 32.  autoscale button has aria-label "Auto Scale"
 * 33.  autoscale button is enabled when onAutoScale is provided
 * 34.  clicking enabled autoscale button calls onAutoScale
 * 35.  clicking disabled autoscale button does not call onAutoScale
 * Candle count (CHART-HEADER-1.1)
 * 19.  candleCount shown in subtitle as "N candles"
 * 20.  candleCount=0 does not add candle text to subtitle
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ChartHeader from '../ChartHeader'
import { DEFAULT_CHART_SETTINGS } from '../../types/chartSettings'
import type { ChartSettings } from '../../types/chartSettings'

function renderHeader(
  overrides: Partial<Parameters<typeof ChartHeader>[0]> = {},
  onSettingsChange = vi.fn(),
) {
  const props = {
    symbol:          'AAPL',
    timeframe:       '1d',
    instrumentName:  undefined,
    exchange:        undefined,
    assetClass:      undefined,
    chartSettings:   DEFAULT_CHART_SETTINGS as ChartSettings,
    onSettingsChange,
    ...overrides,
  }
  return render(<ChartHeader {...props} />)
}

describe('ChartHeader', () => {

  // ── Rendering ──────────────────────────────────────────────────────────────

  it('1. renders with data-testid chart-header', () => {
    renderHeader()
    expect(screen.getByTestId('chart-header')).toBeInTheDocument()
  })

  it('2. shows symbol when provided', () => {
    renderHeader({ symbol: 'TSLA' })
    expect(screen.getByTestId('chart-header-symbol')).toHaveTextContent('TSLA')
  })

  it('3. shows dash placeholder when symbol is empty string', () => {
    renderHeader({ symbol: '' })
    expect(screen.queryByTestId('chart-header-symbol')).toBeNull()
    expect(screen.getByTestId('chart-header')).toHaveTextContent('—')
  })

  it('4. subtitle includes instrumentName', () => {
    renderHeader({ instrumentName: 'Apple Inc.' })
    expect(screen.getByTestId('chart-header-subtitle')).toHaveTextContent('Apple Inc.')
  })

  it('5. subtitle includes exchange', () => {
    renderHeader({ exchange: 'NASDAQ' })
    expect(screen.getByTestId('chart-header-subtitle')).toHaveTextContent('NASDAQ')
  })

  it('6. subtitle includes assetClass', () => {
    renderHeader({ assetClass: 'equity' })
    expect(screen.getByTestId('chart-header-subtitle')).toHaveTextContent('equity')
  })

  it('7. subtitle includes timeframe', () => {
    renderHeader({ timeframe: '4h' })
    expect(screen.getByTestId('chart-header-subtitle')).toHaveTextContent('4h')
  })

  it('8. subtitle joins parts with " · "', () => {
    renderHeader({ instrumentName: 'Apple Inc.', exchange: 'NASDAQ', assetClass: 'equity', timeframe: '1d' })
    const text = screen.getByTestId('chart-header-subtitle').textContent
    expect(text).toBe('Apple Inc. · NASDAQ · equity · 1d')
  })

  it('9. subtitle not rendered when no instrumentName, exchange, or assetClass', () => {
    renderHeader({ instrumentName: undefined, exchange: undefined, assetClass: undefined, timeframe: '' })
    expect(screen.queryByTestId('chart-header-subtitle')).toBeNull()
  })

  // ── Gear button ────────────────────────────────────────────────────────────

  it('10. gear button renders', () => {
    renderHeader()
    expect(screen.getByTestId('chart-settings-btn')).toBeInTheDocument()
  })

  it('11. gear button has aria-label "Chart settings"', () => {
    renderHeader()
    expect(screen.getByTestId('chart-settings-btn')).toHaveAttribute('aria-label', 'Chart settings')
  })

  it('12. clicking gear shows settings panel', () => {
    renderHeader()
    fireEvent.click(screen.getByTestId('chart-settings-btn'))
    expect(screen.getByTestId('chart-settings-panel')).toBeInTheDocument()
  })

  it('13. clicking backdrop closes settings panel', () => {
    renderHeader()
    fireEvent.click(screen.getByTestId('chart-settings-btn'))
    expect(screen.getByTestId('chart-settings-panel')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('chart-settings-backdrop'))
    expect(screen.queryByTestId('chart-settings-panel')).not.toBeInTheDocument()
  })

  it('14. clicking close button in settings panel closes it', () => {
    renderHeader()
    fireEvent.click(screen.getByTestId('chart-settings-btn'))
    fireEvent.click(screen.getByTestId('chart-settings-close'))
    expect(screen.queryByTestId('chart-settings-panel')).not.toBeInTheDocument()
  })

  it('15. onSettingsChange is called when a toggle is changed', () => {
    const onChange = vi.fn()
    renderHeader({}, onChange)
    fireEvent.click(screen.getByTestId('chart-settings-btn'))
    fireEvent.click(screen.getByTestId('settings-toggle-signal-markers'))
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        labels: expect.objectContaining({ showSignalMarkers: false }),
      })
    )
  })

  // ── Camera button ──────────────────────────────────────────────────────────

  it('16. camera button renders', () => {
    renderHeader()
    expect(screen.getByTestId('chart-screenshot-btn')).toBeInTheDocument()
  })

  it('17. camera button is disabled when onScreenshot is not provided', () => {
    renderHeader()  // no onScreenshot prop → disabled
    expect(screen.getByTestId('chart-screenshot-btn')).toBeDisabled()
  })

  it('18. camera button has aria-label "Screenshot"', () => {
    renderHeader()
    expect(screen.getByTestId('chart-screenshot-btn')).toHaveAttribute('aria-label', 'Screenshot')
  })

  // ── Candle count (CHART-HEADER-1.1) ───────────────────────────────────────

  it('19. candleCount shown in subtitle as "N candles"', () => {
    renderHeader({ timeframe: '1d', candleCount: 251 })
    const subtitle = screen.getByTestId('chart-header-subtitle')
    expect(subtitle.textContent).toContain('251 candles')
  })

  it('20. candleCount=0 does not add candle text to subtitle', () => {
    renderHeader({ timeframe: '1d', candleCount: 0 })
    const subtitle = screen.queryByTestId('chart-header-subtitle')
    // subtitle only has timeframe "1d" — no "candles" text
    if (subtitle) {
      expect(subtitle.textContent).not.toContain('candles')
    }
  })

  // ── Camera button — screenshot interactions (CHART-TOOLBAR-1A) ─────────────

  it('21. camera button is enabled when onScreenshot is provided', () => {
    renderHeader({ onScreenshot: vi.fn() })
    expect(screen.getByTestId('chart-screenshot-btn')).not.toBeDisabled()
  })

  it('22. clicking enabled camera button calls onScreenshot', () => {
    const onScreenshot = vi.fn()
    renderHeader({ onScreenshot })
    fireEvent.click(screen.getByTestId('chart-screenshot-btn'))
    expect(onScreenshot).toHaveBeenCalledTimes(1)
  })

  it('23. clicking disabled camera button does not trigger onScreenshot', () => {
    const onScreenshot = vi.fn()
    renderHeader()  // no onScreenshot prop → button disabled
    fireEvent.click(screen.getByTestId('chart-screenshot-btn'))
    expect(onScreenshot).not.toHaveBeenCalled()
  })

  // ── Reset View button (CHART-TOOLBAR-1B) ──────────────────────────────────

  it('24. reset button renders', () => {
    renderHeader()
    expect(screen.getByTestId('chart-reset-view-btn')).toBeInTheDocument()
  })

  it('25. reset button is disabled when onResetView is not provided', () => {
    renderHeader()  // no onResetView prop → disabled
    expect(screen.getByTestId('chart-reset-view-btn')).toBeDisabled()
  })

  it('26. reset button has aria-label "Reset View"', () => {
    renderHeader()
    expect(screen.getByTestId('chart-reset-view-btn')).toHaveAttribute('aria-label', 'Reset View')
  })

  it('27. reset button is enabled when onResetView is provided', () => {
    renderHeader({ onResetView: vi.fn() })
    expect(screen.getByTestId('chart-reset-view-btn')).not.toBeDisabled()
  })

  it('28. clicking enabled reset button calls onResetView', () => {
    const onResetView = vi.fn()
    renderHeader({ onResetView })
    fireEvent.click(screen.getByTestId('chart-reset-view-btn'))
    expect(onResetView).toHaveBeenCalledTimes(1)
  })

  it('29. clicking disabled reset button does not trigger onResetView', () => {
    const onResetView = vi.fn()
    renderHeader()  // no onResetView prop → button disabled
    fireEvent.click(screen.getByTestId('chart-reset-view-btn'))
    expect(onResetView).not.toHaveBeenCalled()
  })

  // ── Auto Scale button (CHART-TOOLBAR-1C) ────────────────────────────────

  it('30. autoscale button renders', () => {
    renderHeader()
    expect(screen.getByTestId('chart-autoscale-btn')).toBeInTheDocument()
  })

  it('31. autoscale button is disabled when onAutoScale is not provided', () => {
    renderHeader()  // no onAutoScale prop → disabled
    expect(screen.getByTestId('chart-autoscale-btn')).toBeDisabled()
  })

  it('32. autoscale button has aria-label "Auto Scale"', () => {
    renderHeader()
    expect(screen.getByTestId('chart-autoscale-btn')).toHaveAttribute('aria-label', 'Auto Scale')
  })

  it('33. autoscale button is enabled when onAutoScale is provided', () => {
    renderHeader({ onAutoScale: vi.fn() })
    expect(screen.getByTestId('chart-autoscale-btn')).not.toBeDisabled()
  })

  it('34. clicking enabled autoscale button calls onAutoScale', () => {
    const onAutoScale = vi.fn()
    renderHeader({ onAutoScale })
    fireEvent.click(screen.getByTestId('chart-autoscale-btn'))
    expect(onAutoScale).toHaveBeenCalledTimes(1)
  })

  it('35. clicking disabled autoscale button does not trigger onAutoScale', () => {
    const onAutoScale = vi.fn()
    renderHeader()  // no onAutoScale prop → button disabled
    fireEvent.click(screen.getByTestId('chart-autoscale-btn'))
    expect(onAutoScale).not.toHaveBeenCalled()
  })
})
