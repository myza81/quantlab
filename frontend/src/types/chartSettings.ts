export interface ChartSettingsLabels {
  showLatestPriceLabel:     boolean
  showIndicatorValueLabels: boolean
  showStrategyValueLabels:  boolean
  showSignalMarkers:        boolean
}

export interface ChartSettingsAppearance {
  backgroundColor: string
  gridColor:       string
  textColor:       string
}

export interface ChartSettingsScales {
  showGrid:                 boolean
  showCrosshair:            boolean
  syncCrosshairAcrossPanes: boolean
}

export interface ChartSettingsLayout {
  rightAxisMinimumWidth: number
}

export interface ChartSettingsStructure {
  showMinorStructure: boolean
  showMainStructure: boolean
  showStructureLabels: boolean
  showDebugMetadata: boolean
  showBos: boolean
  showChoch: boolean
  minorStructureEngine: 'minor_structure_v1' | 'minor_structure_v2' | 'minor_structure_v3'
}

import type { ThemePreset } from './chartTheme'

export interface ChartSettings {
  labels:      ChartSettingsLabels
  appearance:  ChartSettingsAppearance
  scales:      ChartSettingsScales
  layout:      ChartSettingsLayout
  structure:   ChartSettingsStructure
  themePreset: ThemePreset
}

export const DEFAULT_CHART_SETTINGS: ChartSettings = {
  labels: {
    showLatestPriceLabel:     true,
    showIndicatorValueLabels: true,
    showStrategyValueLabels:  true,
    showSignalMarkers:        true,
  },
  appearance: {
    backgroundColor: '#0f0f1a',
    gridColor:       '#1a1a2e',
    textColor:       '#d1d4dc',
  },
  scales: {
    showGrid:                 true,
    showCrosshair:            true,
    syncCrosshairAcrossPanes: true,
  },
  layout: {
    rightAxisMinimumWidth: 80,
  },
  structure: {
    showMinorStructure:   false,
    showMainStructure:    false,
    showStructureLabels:  false,
    showDebugMetadata:    false,
    showBos:              false,
    showChoch:            false,
    minorStructureEngine: 'minor_structure_v1',
  },
  themePreset: 'quantlab-dark',
}
