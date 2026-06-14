import { useState, useCallback } from 'react'
import { DEFAULT_CHART_SETTINGS } from '../types/chartSettings'
import type { ChartSettings } from '../types/chartSettings'

const STORAGE_KEY = 'ql_chart_settings'

function loadSettings(): ChartSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_CHART_SETTINGS
    const parsed = JSON.parse(raw) as Partial<ChartSettings>
    // Shallow merge per-section so missing keys from older stored versions fall back to defaults
    return {
      labels:      { ...DEFAULT_CHART_SETTINGS.labels,     ...(parsed.labels     ?? {}) },
      appearance:  { ...DEFAULT_CHART_SETTINGS.appearance, ...(parsed.appearance ?? {}) },
      scales:      { ...DEFAULT_CHART_SETTINGS.scales,     ...(parsed.scales     ?? {}) },
      layout:      { ...DEFAULT_CHART_SETTINGS.layout,     ...(parsed.layout     ?? {}) },
      structure:   { ...DEFAULT_CHART_SETTINGS.structure,  ...(parsed.structure  ?? {}) },
      themePreset: parsed.themePreset ?? DEFAULT_CHART_SETTINGS.themePreset,
    }
  } catch {
    return DEFAULT_CHART_SETTINGS
  }
}

function saveSettings(s: ChartSettings): void {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(s)) } catch { /* storage unavailable */ }
}

export function useChartSettings() {
  const [settings, setSettings] = useState<ChartSettings>(loadSettings)

  const updateSettings = useCallback((patch: Partial<ChartSettings>) => {
    setSettings(prev => {
      const next: ChartSettings = {
        labels:      { ...prev.labels,     ...(patch.labels     ?? {}) },
        appearance:  { ...prev.appearance, ...(patch.appearance ?? {}) },
        scales:      { ...prev.scales,     ...(patch.scales     ?? {}) },
        layout:      { ...prev.layout,     ...(patch.layout     ?? {}) },
        structure:   { ...prev.structure,  ...(patch.structure  ?? {}) },
        themePreset: patch.themePreset ?? prev.themePreset,
      }
      saveSettings(next)
      return next
    })
  }, [])

  return { settings, updateSettings }
}
