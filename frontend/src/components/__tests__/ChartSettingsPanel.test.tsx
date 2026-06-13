/**
 * ChartSettingsPanel.test.tsx — CHART-SETTINGS-1A / 1B
 *
 * Coverage:
 * Rendering
 *  1. renders with data-testid="chart-settings-panel"
 *  2. shows "Labels" section header
 *  3. renders all four label toggles
 *  4. all toggles checked by default when DEFAULT_CHART_SETTINGS passed
 * Interactions
 *  5. toggling Latest Price calls onChange with showLatestPriceLabel: false
 *  6. toggling Indicators calls onChange with showIndicatorValueLabels: false
 *  7. toggling Strategy Values calls onChange with showStrategyValueLabels: false
 *  8. toggling Signal Markers calls onChange with showSignalMarkers: false
 *  9. re-checking unchecked toggle calls onChange with value: true
 * 10. close button calls onClose
 * 11. onChange patch preserves other labels unchanged
 * 12. data-testids present for all toggles
 * Theme section (1B)
 * 13. shows "Theme" section header
 * 14. renders all three theme radio options
 * 15. QuantLab Dark radio is selected by default
 * 16. selecting TradingView Dark calls onChange with themePreset: tradingview-dark
 * 17. selecting Light calls onChange with themePreset: light
 * 18. theme radio options are radio inputs
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ChartSettingsPanel from '../ChartSettingsPanel'
import { DEFAULT_CHART_SETTINGS } from '../../types/chartSettings'
import type { ChartSettings } from '../../types/chartSettings'

function renderPanel(
  overrides: Partial<ChartSettings> = {},
  onChange = vi.fn(),
  onClose  = vi.fn(),
) {
  const settings: ChartSettings = {
    ...DEFAULT_CHART_SETTINGS,
    ...overrides,
    labels:     { ...DEFAULT_CHART_SETTINGS.labels,     ...(overrides.labels     ?? {}) },
    appearance: { ...DEFAULT_CHART_SETTINGS.appearance, ...(overrides.appearance ?? {}) },
    scales:     { ...DEFAULT_CHART_SETTINGS.scales,     ...(overrides.scales     ?? {}) },
    layout:     { ...DEFAULT_CHART_SETTINGS.layout,     ...(overrides.layout     ?? {}) },
  }
  return render(
    <ChartSettingsPanel settings={settings} onChange={onChange} onClose={onClose} />
  )
}

describe('ChartSettingsPanel', () => {

  // ── Rendering ──────────────────────────────────────────────────────────────

  it('1. renders with data-testid chart-settings-panel', () => {
    renderPanel()
    expect(screen.getByTestId('chart-settings-panel')).toBeInTheDocument()
  })

  it('2. shows Labels section header', () => {
    renderPanel()
    expect(screen.getByTestId('settings-section-labels')).toBeInTheDocument()
  })

  it('3. renders all four label toggle rows', () => {
    renderPanel()
    expect(screen.getByTestId('settings-toggle-latest-price')).toBeInTheDocument()
    expect(screen.getByTestId('settings-toggle-indicator-values')).toBeInTheDocument()
    expect(screen.getByTestId('settings-toggle-strategy-values')).toBeInTheDocument()
    expect(screen.getByTestId('settings-toggle-signal-markers')).toBeInTheDocument()
  })

  it('4. all toggles checked when DEFAULT_CHART_SETTINGS passed', () => {
    renderPanel()
    expect(screen.getByTestId('settings-toggle-latest-price')).toBeChecked()
    expect(screen.getByTestId('settings-toggle-indicator-values')).toBeChecked()
    expect(screen.getByTestId('settings-toggle-strategy-values')).toBeChecked()
    expect(screen.getByTestId('settings-toggle-signal-markers')).toBeChecked()
  })

  // ── Interactions ───────────────────────────────────────────────────────────

  it('5. unchecking Latest Price calls onChange with showLatestPriceLabel: false', () => {
    const onChange = vi.fn()
    renderPanel({}, onChange)
    fireEvent.click(screen.getByTestId('settings-toggle-latest-price'))
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        labels: expect.objectContaining({ showLatestPriceLabel: false }),
      })
    )
  })

  it('6. unchecking Indicators calls onChange with showIndicatorValueLabels: false', () => {
    const onChange = vi.fn()
    renderPanel({}, onChange)
    fireEvent.click(screen.getByTestId('settings-toggle-indicator-values'))
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        labels: expect.objectContaining({ showIndicatorValueLabels: false }),
      })
    )
  })

  it('7. unchecking Strategy Values calls onChange with showStrategyValueLabels: false', () => {
    const onChange = vi.fn()
    renderPanel({}, onChange)
    fireEvent.click(screen.getByTestId('settings-toggle-strategy-values'))
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        labels: expect.objectContaining({ showStrategyValueLabels: false }),
      })
    )
  })

  it('8. unchecking Signal Markers calls onChange with showSignalMarkers: false', () => {
    const onChange = vi.fn()
    renderPanel({}, onChange)
    fireEvent.click(screen.getByTestId('settings-toggle-signal-markers'))
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        labels: expect.objectContaining({ showSignalMarkers: false }),
      })
    )
  })

  it('9. checking an unchecked toggle calls onChange with value: true', () => {
    const onChange = vi.fn()
    renderPanel({ labels: { ...DEFAULT_CHART_SETTINGS.labels, showSignalMarkers: false } }, onChange)
    expect(screen.getByTestId('settings-toggle-signal-markers')).not.toBeChecked()
    fireEvent.click(screen.getByTestId('settings-toggle-signal-markers'))
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        labels: expect.objectContaining({ showSignalMarkers: true }),
      })
    )
  })

  it('10. close button calls onClose', () => {
    const onClose = vi.fn()
    renderPanel({}, vi.fn(), onClose)
    fireEvent.click(screen.getByTestId('chart-settings-close'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('11. onChange patch preserves other label values unchanged', () => {
    const onChange = vi.fn()
    renderPanel({}, onChange)
    fireEvent.click(screen.getByTestId('settings-toggle-latest-price'))
    const patch = onChange.mock.calls[0][0] as Partial<typeof DEFAULT_CHART_SETTINGS>
    // Patch preserves all other labels at their original (true) values
    expect(patch.labels?.showIndicatorValueLabels).toBe(true)
    expect(patch.labels?.showStrategyValueLabels).toBe(true)
    expect(patch.labels?.showSignalMarkers).toBe(true)
  })

  it('12. all toggle data-testids exist and are checkbox inputs', () => {
    renderPanel()
    const ids = [
      'settings-toggle-latest-price',
      'settings-toggle-indicator-values',
      'settings-toggle-strategy-values',
      'settings-toggle-signal-markers',
    ]
    for (const id of ids) {
      const el = screen.getByTestId(id)
      expect(el.tagName).toBe('INPUT')
      expect((el as HTMLInputElement).type).toBe('checkbox')
    }
  })

  // ── Theme section (1B) ─────────────────────────────────────────────────────

  it('13. shows Theme section header', () => {
    renderPanel()
    expect(screen.getByTestId('settings-section-theme')).toBeInTheDocument()
  })

  it('14. renders all three theme radio options', () => {
    renderPanel()
    expect(screen.getByTestId('settings-radio-quantlab-dark')).toBeInTheDocument()
    expect(screen.getByTestId('settings-radio-tradingview-dark')).toBeInTheDocument()
    expect(screen.getByTestId('settings-radio-light')).toBeInTheDocument()
  })

  it('15. QuantLab Dark radio is selected by default', () => {
    renderPanel()
    expect(screen.getByTestId('settings-radio-quantlab-dark')).toBeChecked()
    expect(screen.getByTestId('settings-radio-tradingview-dark')).not.toBeChecked()
    expect(screen.getByTestId('settings-radio-light')).not.toBeChecked()
  })

  it('16. selecting TradingView Dark calls onChange with themePreset: tradingview-dark', () => {
    const onChange = vi.fn()
    renderPanel({}, onChange)
    fireEvent.click(screen.getByTestId('settings-radio-tradingview-dark'))
    expect(onChange).toHaveBeenCalledWith({ themePreset: 'tradingview-dark' })
  })

  it('17. selecting Light calls onChange with themePreset: light', () => {
    const onChange = vi.fn()
    renderPanel({}, onChange)
    fireEvent.click(screen.getByTestId('settings-radio-light'))
    expect(onChange).toHaveBeenCalledWith({ themePreset: 'light' })
  })

  it('18. theme radio options are radio inputs', () => {
    renderPanel()
    for (const testId of ['settings-radio-quantlab-dark', 'settings-radio-tradingview-dark', 'settings-radio-light']) {
      const el = screen.getByTestId(testId)
      expect(el.tagName).toBe('INPUT')
      expect((el as HTMLInputElement).type).toBe('radio')
    }
  })
})
