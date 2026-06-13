import type { ChartTheme } from '../types/chartTheme'

export const quantlabDark: ChartTheme = {
  preset:      'quantlab-dark',
  displayName: 'QuantLab Dark',
  lwChart: {
    background: '#0f0f1a',
    text:       '#d1d4dc',
    grid:       '#1a1a2e',
    border:     '#2a2d3e',
  },
  colors: {
    toolbarBg:     '#0d0d1e',
    toolbarBorder: '#1a1a2e',
    ohlcBarBg:     'rgba(10, 10, 20, 0.85)',
    ohlcBarBorder: '#1a1a2e',
    symbolText:    '#d1d4dc',
    subtitleText:  '#4a5568',
    metaText:      '#7a8499',
    mutedText:     '#2a3040',
    panelBg:       '#0d0d1e',
    panelBorder:   '#2a2d3e',
    panelText:     '#c4cde0',
    panelMuted:    '#7a8499',
    actionBtnBorder:       '#2a2d3e',
    actionBtnActiveBorder: '#3a5a7a',
    actionBtnActiveColor:  '#7eb8f7',
    actionBtnActiveBg:     'rgba(126,184,247,0.10)',
    candleUp:   '#26a69a',
    candleDown: '#ef5350',
  },
}
