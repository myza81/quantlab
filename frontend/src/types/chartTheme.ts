export type ThemePreset = 'quantlab-dark' | 'tradingview-dark' | 'light'

export interface ChartTheme {
  preset:      ThemePreset
  displayName: string

  /** Color tokens fed directly into Lightweight Charts createChart / applyOptions */
  lwChart: {
    background: string
    text:       string
    grid:       string
    border:     string
  }

  /** Component-level color tokens for chart-area UI */
  colors: {
    toolbarBg:     string
    toolbarBorder: string
    ohlcBarBg:     string
    ohlcBarBorder: string
    symbolText:    string
    subtitleText:  string
    metaText:      string
    mutedText:     string
    panelBg:       string
    panelBorder:   string
    panelText:     string
    panelMuted:    string
    actionBtnBorder:       string
    actionBtnActiveBorder: string
    actionBtnActiveColor:  string
    actionBtnActiveBg:     string
    candleUp:   string
    candleDown: string
  }
}
