import { quantlabDark }    from './quantlabDark'
import { tradingviewDark } from './tradingviewDark'
import { light }           from './light'
import type { ThemePreset, ChartTheme } from '../types/chartTheme'

export const THEMES: Record<ThemePreset, ChartTheme> = {
  'quantlab-dark':    quantlabDark,
  'tradingview-dark': tradingviewDark,
  'light':            light,
}

export function getTheme(preset: ThemePreset | undefined): ChartTheme {
  if (preset && preset in THEMES) return THEMES[preset]
  return quantlabDark
}

/**
 * Builds Lightweight Charts color options from a theme.
 * Safe to pass to chart.applyOptions() — does not include width, height,
 * or pan/zoom state (barSpacing, rightOffset) that would disrupt user interaction.
 */
export function buildLwChartColorOptions(theme: ChartTheme) {
  return {
    layout: {
      background: { color: theme.lwChart.background },
      textColor:  theme.lwChart.text,
    },
    grid: {
      vertLines: { color: theme.lwChart.grid },
      horzLines: { color: theme.lwChart.grid },
    },
    rightPriceScale: { borderColor: theme.lwChart.border },
    timeScale:       { borderColor: theme.lwChart.border },
  }
}

export type { ThemePreset, ChartTheme }
export { quantlabDark, tradingviewDark, light }
