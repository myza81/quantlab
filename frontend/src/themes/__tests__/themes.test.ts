/**
 * themes.test.ts — CHART-SETTINGS-1B
 *
 * Coverage:
 *  1. THEMES map contains all three presets
 *  2. getTheme('quantlab-dark') returns quantlabDark
 *  3. getTheme('tradingview-dark') returns tradingviewDark
 *  4. getTheme('light') returns light
 *  5. getTheme(undefined) falls back to quantlabDark
 *  6. Each theme has all required fields
 *  7. buildLwChartColorOptions returns expected shape for each theme
 *  8. QuantLab Dark preserves existing default background color
 */
import { describe, it, expect } from 'vitest'
import { THEMES, getTheme, buildLwChartColorOptions, quantlabDark, tradingviewDark, light } from '../index'

describe('theme registry', () => {
  it('1. THEMES map contains all three presets', () => {
    expect('quantlab-dark'    in THEMES).toBe(true)
    expect('tradingview-dark' in THEMES).toBe(true)
    expect('light'            in THEMES).toBe(true)
  })

  it('2. getTheme quantlab-dark returns quantlabDark', () => {
    expect(getTheme('quantlab-dark')).toBe(quantlabDark)
  })

  it('3. getTheme tradingview-dark returns tradingviewDark', () => {
    expect(getTheme('tradingview-dark')).toBe(tradingviewDark)
  })

  it('4. getTheme light returns light', () => {
    expect(getTheme('light')).toBe(light)
  })

  it('5. getTheme(undefined) falls back to quantlabDark', () => {
    expect(getTheme(undefined)).toBe(quantlabDark)
  })

  it('6. each theme has all required fields', () => {
    for (const theme of [quantlabDark, tradingviewDark, light]) {
      expect(theme.preset).toBeDefined()
      expect(theme.displayName).toBeDefined()
      expect(theme.lwChart.background).toBeDefined()
      expect(theme.lwChart.text).toBeDefined()
      expect(theme.lwChart.grid).toBeDefined()
      expect(theme.lwChart.border).toBeDefined()
      expect(theme.colors.toolbarBg).toBeDefined()
      expect(theme.colors.toolbarBorder).toBeDefined()
      expect(theme.colors.panelBg).toBeDefined()
      expect(theme.colors.panelText).toBeDefined()
      expect(theme.colors.candleUp).toBeDefined()
      expect(theme.colors.candleDown).toBeDefined()
    }
  })

  it('7. buildLwChartColorOptions returns layout/grid/scale shape', () => {
    const opts = buildLwChartColorOptions(quantlabDark)
    expect(opts.layout.background).toBeDefined()
    expect(opts.layout.textColor).toBeDefined()
    expect(opts.grid.vertLines.color).toBeDefined()
    expect(opts.grid.horzLines.color).toBeDefined()
    expect(opts.rightPriceScale.borderColor).toBeDefined()
    expect(opts.timeScale.borderColor).toBeDefined()
    // Must NOT include width, height, rightOffset, barSpacing
    expect((opts as Record<string, unknown>).width).toBeUndefined()
    expect((opts as Record<string, unknown>).height).toBeUndefined()
    expect((opts.timeScale as Record<string, unknown>).rightOffset).toBeUndefined()
    expect((opts.timeScale as Record<string, unknown>).barSpacing).toBeUndefined()
  })

  it('8. QuantLab Dark preserves existing default background color', () => {
    expect(quantlabDark.lwChart.background).toBe('#0f0f1a')
    expect(quantlabDark.colors.toolbarBg).toBe('#0d0d1e')
  })
})
