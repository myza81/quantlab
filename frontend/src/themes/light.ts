import type { ChartTheme } from '../types/chartTheme'

export const light: ChartTheme = {
  preset:      'light',
  displayName: 'Light',
  lwChart: {
    background: '#ffffff',
    text:       '#1a1a2e',
    grid:       '#e8eaed',
    border:     '#c8cdd6',
  },
  colors: {
    toolbarBg:     '#f8f9fc',
    toolbarBorder: '#e2e5ec',
    ohlcBarBg:     'rgba(248, 249, 252, 0.97)',
    ohlcBarBorder: '#e2e5ec',
    symbolText:    '#1a1a2e',
    subtitleText:  '#6b7280',
    metaText:      '#9ca3af',
    mutedText:     '#c8cdd6',
    panelBg:       '#ffffff',
    panelBorder:   '#d1d4dc',
    panelText:     '#1a1a2e',
    panelMuted:    '#6b7280',
    actionBtnBorder:       '#c8cdd6',
    actionBtnActiveBorder: '#3b82f6',
    actionBtnActiveColor:  '#2563eb',
    actionBtnActiveBg:     'rgba(59,130,246,0.08)',
    candleUp:   '#22a37e',
    candleDown: '#e53e3e',
  },
}
