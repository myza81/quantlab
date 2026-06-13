import type { ChartTheme } from '../types/chartTheme'

export const tradingviewDark: ChartTheme = {
  preset:      'tradingview-dark',
  displayName: 'TradingView Dark',
  lwChart: {
    background: '#131722',
    text:       '#b2b5be',
    grid:       '#2a2e39',
    border:     '#363c4e',
  },
  colors: {
    toolbarBg:     '#1e222d',
    toolbarBorder: '#2a2e39',
    ohlcBarBg:     'rgba(30, 34, 45, 0.92)',
    ohlcBarBorder: '#2a2e39',
    symbolText:    '#d9d9d9',
    subtitleText:  '#787b86',
    metaText:      '#787b86',
    mutedText:     '#363c4e',
    panelBg:       '#1e222d',
    panelBorder:   '#363c4e',
    panelText:     '#d1d4dc',
    panelMuted:    '#787b86',
    actionBtnBorder:       '#363c4e',
    actionBtnActiveBorder: '#4c7aae',
    actionBtnActiveColor:  '#5b9bd5',
    actionBtnActiveBg:     'rgba(91,155,213,0.12)',
    candleUp:   '#26a69a',
    candleDown: '#ef5350',
  },
}
