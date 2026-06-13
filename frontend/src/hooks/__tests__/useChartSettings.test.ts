/**
 * useChartSettings.test.ts — CHART-SETTINGS-1A / 1B
 *
 * Coverage:
 *  1. Returns DEFAULT_CHART_SETTINGS when localStorage is empty
 *  2. Returns DEFAULT_CHART_SETTINGS when localStorage contains malformed JSON
 *  3. Loads stored labels from localStorage on mount
 *  4. Merges partial stored settings with defaults (missing keys fall back)
 *  5. updateSettings writes merged settings to localStorage
 *  6. updateSettings merges a labels patch without touching appearance/scales/layout
 *  7. Calling updateSettings twice accumulates changes
 *  8. localStorage write failure is silently swallowed
 *  9. Loads stored themePreset from localStorage (1B)
 * 10. updateSettings themePreset persists to localStorage (1B)
 * 11. Missing themePreset in stored data falls back to default (1B)
 */
import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, beforeEach } from 'vitest'
import { useChartSettings } from '../useChartSettings'
import { DEFAULT_CHART_SETTINGS } from '../../types/chartSettings'

const STORAGE_KEY = 'ql_chart_settings'

describe('useChartSettings', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('1. returns DEFAULT_CHART_SETTINGS when localStorage is empty', () => {
    const { result } = renderHook(() => useChartSettings())
    expect(result.current.settings).toEqual(DEFAULT_CHART_SETTINGS)
  })

  it('2. returns DEFAULT_CHART_SETTINGS when localStorage has malformed JSON', () => {
    localStorage.setItem(STORAGE_KEY, '{{not valid json')
    const { result } = renderHook(() => useChartSettings())
    expect(result.current.settings).toEqual(DEFAULT_CHART_SETTINGS)
  })

  it('3. loads stored label settings from localStorage on mount', () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      ...DEFAULT_CHART_SETTINGS,
      labels: { ...DEFAULT_CHART_SETTINGS.labels, showSignalMarkers: false },
    }))
    const { result } = renderHook(() => useChartSettings())
    expect(result.current.settings.labels.showSignalMarkers).toBe(false)
    // Other labels should still be true
    expect(result.current.settings.labels.showLatestPriceLabel).toBe(true)
  })

  it('4. merges partial stored settings — missing keys fall back to defaults', () => {
    // Only store labels section, omit appearance/scales/layout
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      labels: { showLatestPriceLabel: false },
    }))
    const { result } = renderHook(() => useChartSettings())
    // Missing labels keys fall back to defaults
    expect(result.current.settings.labels.showLatestPriceLabel).toBe(false)
    expect(result.current.settings.labels.showIndicatorValueLabels).toBe(true)
    // Missing sections fall back entirely to defaults
    expect(result.current.settings.appearance).toEqual(DEFAULT_CHART_SETTINGS.appearance)
    expect(result.current.settings.scales).toEqual(DEFAULT_CHART_SETTINGS.scales)
    expect(result.current.settings.layout).toEqual(DEFAULT_CHART_SETTINGS.layout)
  })

  it('5. updateSettings writes merged settings to localStorage', () => {
    const { result } = renderHook(() => useChartSettings())
    act(() => {
      result.current.updateSettings({
        labels: { ...DEFAULT_CHART_SETTINGS.labels, showSignalMarkers: false },
      })
    })
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY)!)
    expect(stored.labels.showSignalMarkers).toBe(false)
  })

  it('6. updateSettings merges a labels patch without touching appearance/scales/layout', () => {
    const { result } = renderHook(() => useChartSettings())
    act(() => {
      result.current.updateSettings({
        labels: { ...DEFAULT_CHART_SETTINGS.labels, showLatestPriceLabel: false },
      })
    })
    const { settings } = result.current
    expect(settings.labels.showLatestPriceLabel).toBe(false)
    expect(settings.labels.showIndicatorValueLabels).toBe(true)
    expect(settings.appearance).toEqual(DEFAULT_CHART_SETTINGS.appearance)
    expect(settings.scales).toEqual(DEFAULT_CHART_SETTINGS.scales)
    expect(settings.layout).toEqual(DEFAULT_CHART_SETTINGS.layout)
  })

  it('7. calling updateSettings twice accumulates changes', () => {
    const { result } = renderHook(() => useChartSettings())
    act(() => {
      result.current.updateSettings({
        labels: { ...DEFAULT_CHART_SETTINGS.labels, showSignalMarkers: false },
      })
    })
    act(() => {
      result.current.updateSettings({
        labels: { ...result.current.settings.labels, showLatestPriceLabel: false },
      })
    })
    expect(result.current.settings.labels.showSignalMarkers).toBe(false)
    expect(result.current.settings.labels.showLatestPriceLabel).toBe(false)
  })

  it('8. localStorage write failure is silently swallowed', () => {
    const originalSetItem = localStorage.setItem.bind(localStorage)
    localStorage.setItem = () => { throw new Error('storage full') }
    const { result } = renderHook(() => useChartSettings())
    expect(() => {
      act(() => {
        result.current.updateSettings({
          labels: { ...DEFAULT_CHART_SETTINGS.labels, showSignalMarkers: false },
        })
      })
    }).not.toThrow()
    // State still updated in memory even if storage fails
    expect(result.current.settings.labels.showSignalMarkers).toBe(false)
    localStorage.setItem = originalSetItem
  })

  it('9. loads stored themePreset from localStorage', () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      ...DEFAULT_CHART_SETTINGS,
      themePreset: 'tradingview-dark',
    }))
    const { result } = renderHook(() => useChartSettings())
    expect(result.current.settings.themePreset).toBe('tradingview-dark')
  })

  it('10. updateSettings themePreset persists to localStorage', () => {
    const { result } = renderHook(() => useChartSettings())
    act(() => {
      result.current.updateSettings({ themePreset: 'light' })
    })
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY)!)
    expect(stored.themePreset).toBe('light')
    expect(result.current.settings.themePreset).toBe('light')
  })

  it('11. missing themePreset in stored data falls back to default', () => {
    // Stored settings from before 1B — no themePreset field
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      labels: DEFAULT_CHART_SETTINGS.labels,
    }))
    const { result } = renderHook(() => useChartSettings())
    expect(result.current.settings.themePreset).toBe(DEFAULT_CHART_SETTINGS.themePreset)
  })
})
