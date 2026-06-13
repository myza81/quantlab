/**
 * ChartHeader — CHART-HEADER-1
 *
 * Chart-local toolbar rendered above the chart canvas.
 * Shows symbol identity (ticker, instrument name, market, timeframe) on the
 * left and action buttons (screenshot placeholder, chart settings) on the right.
 *
 * This component owns the chart settings popover state.  The global App header
 * contains only brand/account controls.
 */
import { useState } from 'react'
import ChartSettingsPanel from './ChartSettingsPanel'
import { getTheme } from '../themes'
import type { ChartSettings } from '../types/chartSettings'

export interface ChartHeaderProps {
  symbol:           string
  timeframe:        string
  /** Company / instrument display name (e.g. "Apple Inc.") */
  instrumentName?:  string
  /** Exchange identifier (e.g. "NASDAQ") */
  exchange?:        string
  /** Asset class (e.g. "equity") */
  assetClass?:      string
  /** Number of loaded candles — shown beside timeframe (e.g. "1d · 251 candles") */
  candleCount?:     number
  chartSettings:    ChartSettings
  onSettingsChange: (patch: Partial<ChartSettings>) => void
  /** When provided, enables the screenshot button and calls this on click. */
  onScreenshot?:    () => void
  /** When provided, enables the reset view button and calls this on click. */
  onResetView?:     () => void
  /** When provided, enables the auto scale button and calls this on click. */
  onAutoScale?:     () => void
}

export default function ChartHeader({
  symbol, timeframe, instrumentName, exchange, assetClass, candleCount,
  chartSettings, onSettingsChange, onScreenshot, onResetView, onAutoScale,
}: ChartHeaderProps) {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const tc = getTheme(chartSettings.themePreset).colors

  const subtitleParts: string[] = []
  if (instrumentName) subtitleParts.push(instrumentName)
  if (exchange)       subtitleParts.push(exchange)
  if (assetClass)     subtitleParts.push(assetClass)
  if (timeframe)      subtitleParts.push(timeframe)
  if (candleCount !== undefined && candleCount > 0) subtitleParts.push(`${candleCount.toLocaleString()} candles`)
  const subtitle = subtitleParts.join(' · ')

  return (
    <div data-testid="chart-header" style={{
      ...s.header,
      background:   tc.toolbarBg,
      borderBottom: `1px solid ${tc.toolbarBorder}`,
    }}>

      {/* Left: symbol + subtitle */}
      <div style={s.identity}>
        {symbol
          ? <span data-testid="chart-header-symbol" style={{ ...s.symbol, color: tc.symbolText }}>{symbol}</span>
          : <span style={{ ...s.symbolEmpty, color: tc.mutedText }}>—</span>
        }
        {subtitle && (
          <span data-testid="chart-header-subtitle" style={{ ...s.subtitle, color: tc.subtitleText }}>{subtitle}</span>
        )}
      </div>

      {/* Right: action buttons */}
      <div style={s.actions}>

        {/* Screenshot — downloads current chart view as PNG */}
        <button
          data-testid="chart-screenshot-btn"
          type="button"
          onClick={onScreenshot}
          disabled={!onScreenshot}
          style={onScreenshot
            ? { ...s.actionBtn, borderColor: tc.actionBtnBorder, color: tc.metaText }
            : { ...s.disabledBtn, borderColor: tc.toolbarBorder }
          }
          title={onScreenshot ? 'Download chart as PNG' : 'Screenshot (load chart data first)'}
          aria-label="Screenshot"
        >
          <CameraIcon />
        </button>

        {/* Reset View — returns chart to initial viewport */}
        <button
          data-testid="chart-reset-view-btn"
          type="button"
          onClick={onResetView}
          disabled={!onResetView}
          style={onResetView
            ? { ...s.actionBtn, borderColor: tc.actionBtnBorder, color: tc.metaText }
            : { ...s.disabledBtn, borderColor: tc.toolbarBorder }
          }
          title={onResetView ? 'Reset View' : 'Reset View (load chart data first)'}
          aria-label="Reset View"
        >
          <ResetIcon />
        </button>

        {/* Auto Scale — refits vertical scales to visible content */}
        <button
          data-testid="chart-autoscale-btn"
          type="button"
          onClick={onAutoScale}
          disabled={!onAutoScale}
          style={onAutoScale
            ? { ...s.actionBtn, borderColor: tc.actionBtnBorder, color: tc.metaText }
            : { ...s.disabledBtn, borderColor: tc.toolbarBorder }
          }
          title={onAutoScale ? 'Auto Scale' : 'Auto Scale (load chart data first)'}
          aria-label="Auto Scale"
        >
          <AutoScaleIcon />
        </button>

        {/* Chart settings popover */}
        <div style={{ position: 'relative' as const }}>
          <button
            data-testid="chart-settings-btn"
            type="button"
            onClick={() => setSettingsOpen(v => !v)}
            style={{
              ...s.actionBtn,
              background:  settingsOpen ? tc.actionBtnActiveBg  : 'transparent',
              borderColor: settingsOpen ? tc.actionBtnActiveBorder : tc.actionBtnBorder,
              color:       settingsOpen ? tc.actionBtnActiveColor  : tc.metaText,
            }}
            title="Chart settings"
            aria-label="Chart settings"
          >
            <GearIcon />
          </button>

          {settingsOpen && (
            <>
              <div
                data-testid="chart-settings-backdrop"
                style={s.backdrop}
                onClick={() => setSettingsOpen(false)}
              />
              <ChartSettingsPanel
                settings={chartSettings}
                onChange={onSettingsChange}
                onClose={() => setSettingsOpen(false)}
              />
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Inline icons — no external dependency ────────────────────────────────────

function CameraIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none"
      stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round"
    >
      <path d="M5 4.5 L6 2.5 L10 2.5 L11 4.5" />
      <rect x="1" y="4.5" width="14" height="9" rx="1.5" />
      <circle cx="8" cy="9" r="2.5" />
    </svg>
  )
}

function ResetIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none"
      stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round"
    >
      <path d="M2.5 6.5 Q2.5 2.5 6.5 2.5 Q10.5 2.5 10.5 6.5" />
      <path d="M13.5 9.5 Q13.5 13.5 9.5 13.5 Q5.5 13.5 5.5 9.5" />
      <path d="M10.5 4 L12 2.5 L10.5 1" />
      <path d="M5.5 12 L4 13.5 L5.5 15" />
    </svg>
  )
}

function AutoScaleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none"
      stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round"
    >
      <path d="M2 3 L2 13 M14 3 L14 13" />
      <path d="M2 8 L14 8" />
      <path d="M5 5 L5 11 M11 5 L11 11" />
      <path d="M3.5 10.5 L4.5 11.5 L5.5 10.5" />
      <path d="M12.5 5.5 L11.5 4.5 L10.5 5.5" />
    </svg>
  )
}

function GearIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none"
      stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round"
    >
      <circle cx="8" cy="8" r="2.5" />
      <path d="
        M8 1v2 M8 13v2
        M1 8h2 M13 8h2
        M3.22 3.22l1.41 1.41
        M11.37 11.37l1.41 1.41
        M3.22 12.78l1.41-1.41
        M11.37 4.63l1.41-1.41
      " />
    </svg>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  header: {
    display:      'flex',
    alignItems:   'center',
    padding:      '0 12px',
    background:   '#0d0d1e',
    borderBottom: '1px solid #1a1a2e',
    flexShrink:   0,
    minHeight:    56,
    gap:          12,
  },
  identity: {
    display:       'flex',
    flexDirection: 'column',
    gap:           3,
    flex:          1,
    minWidth:      0,
  },
  symbol: {
    fontSize:      15,
    fontWeight:    700,
    fontFamily:    'monospace',
    letterSpacing: '0.04em',
    color:         '#d1d4dc',
    lineHeight:    1.2,
  },
  symbolEmpty: {
    fontSize:   13,
    fontFamily: 'monospace',
    color:      '#2a3040',
    lineHeight: 1.2,
  },
  subtitle: {
    fontSize:     11,
    fontFamily:   'monospace',
    color:        '#4a5568',
    lineHeight:   1.2,
    whiteSpace:   'nowrap' as const,
    overflow:     'hidden',
    textOverflow: 'ellipsis',
  },
  actions: {
    display:    'flex',
    alignItems: 'center',
    gap:        6,
    flexShrink: 0,
  },
  actionBtn: {
    width:          40,
    height:         40,
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'center',
    background:     'transparent',
    border:         '1px solid',
    borderRadius:   6,
    cursor:         'pointer',
    padding:        0,
    lineHeight:     1,
    flexShrink:     0,
    transition:     'color 0.12s, background 0.12s, border-color 0.12s',
  } as React.CSSProperties,
  disabledBtn: {
    width:          40,
    height:         40,
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'center',
    background:     'transparent',
    border:         '1px solid #1a1a2e',
    borderRadius:   6,
    cursor:         'not-allowed',
    padding:        0,
    lineHeight:     1,
    flexShrink:     0,
    opacity:        0.3,
    color:          '#4a5568',
  },
  backdrop: { position: 'fixed' as const, inset: 0, zIndex: 99 },
}
