import { getTheme } from '../themes'
import type { ChartSettings } from '../types/chartSettings'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ChartSettingsPanelProps {
  settings: ChartSettings
  onChange: (patch: Partial<ChartSettings>) => void
  onClose:  () => void
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ChartSettingsPanel({ settings, onChange, onClose }: ChartSettingsPanelProps) {
  const theme = getTheme(settings.themePreset)
  const tc    = theme.colors

  function patchLabel(key: keyof ChartSettings['labels'], value: boolean) {
    onChange({ labels: { ...settings.labels, [key]: value } })
  }

  function patchStructure(key: keyof ChartSettings['structure'], value: boolean) {
    onChange({ structure: { ...settings.structure, [key]: value } })
  }

  return (
    <div data-testid="chart-settings-panel" style={{
      ...s.panel,
      background: tc.panelBg,
      border:     `1px solid ${tc.panelBorder}`,
    }}>

      {/* ── Header ── */}
      <div style={{ ...s.header, borderBottom: `1px solid ${tc.toolbarBorder}` }}>
        <span style={{ ...s.title, color: tc.panelMuted }}>Chart Settings</span>
        <button
          data-testid="chart-settings-close"
          type="button"
          onClick={onClose}
          style={{ ...s.closeBtn, color: tc.panelMuted }}
          aria-label="Close chart settings"
        >
          ×
        </button>
      </div>

      {/* ── Labels ── */}
      <div style={s.section}>
        <div data-testid="settings-section-labels" style={{ ...s.sectionHeader, color: tc.panelMuted }}>Labels</div>
        <ToggleRow
          label="Latest Price"
          testId="settings-toggle-latest-price"
          checked={settings.labels.showLatestPriceLabel}
          onChange={v => patchLabel('showLatestPriceLabel', v)}
          labelColor={tc.panelText}
        />
        <ToggleRow
          label="Indicators"
          testId="settings-toggle-indicator-values"
          checked={settings.labels.showIndicatorValueLabels}
          onChange={v => patchLabel('showIndicatorValueLabels', v)}
          labelColor={tc.panelText}
        />
        <ToggleRow
          label="Strategy Values"
          testId="settings-toggle-strategy-values"
          checked={settings.labels.showStrategyValueLabels}
          onChange={v => patchLabel('showStrategyValueLabels', v)}
          labelColor={tc.panelText}
        />
        <ToggleRow
          label="Signal Markers"
          testId="settings-toggle-signal-markers"
          checked={settings.labels.showSignalMarkers}
          onChange={v => patchLabel('showSignalMarkers', v)}
          labelColor={tc.panelText}
        />
      </div>

      {/* ── Market Structure ── */}
      <div style={{ ...s.section, borderTop: `1px solid ${tc.toolbarBorder}` }}>
        <div data-testid="settings-section-structure" style={{ ...s.sectionHeader, color: tc.panelMuted }}>Market Structure</div>
        <ToggleRow
          label="Minor Structure"
          testId="settings-toggle-minor-structure"
          checked={settings.structure.showMinorStructure}
          onChange={v => patchStructure('showMinorStructure', v)}
          labelColor={tc.panelText}
        />
        <ToggleRow
          label="Main Structure"
          testId="settings-toggle-main-structure"
          checked={settings.structure.showMainStructure}
          onChange={v => patchStructure('showMainStructure', v)}
          labelColor={tc.panelText}
        />
        <ToggleRow
          label="Structure Labels"
          testId="settings-toggle-structure-labels"
          checked={settings.structure.showStructureLabels}
          onChange={v => patchStructure('showStructureLabels', v)}
          labelColor={tc.panelText}
        />
        <ToggleRow
          label="Debug Metadata"
          testId="settings-toggle-debug-metadata"
          checked={settings.structure.showDebugMetadata}
          onChange={v => patchStructure('showDebugMetadata', v)}
          labelColor={tc.panelText}
        />
        <ToggleRow
          label="BoS Events"
          testId="settings-toggle-bos"
          checked={settings.structure.showBos}
          onChange={v => patchStructure('showBos', v)}
          labelColor={tc.panelText}
        />
        <ToggleRow
          label="CHoCH Events"
          testId="settings-toggle-choch"
          checked={settings.structure.showChoch}
          onChange={v => patchStructure('showChoch', v)}
          labelColor={tc.panelText}
        />
      </div>

      {/* ── Theme ── */}
      <div style={{ ...s.section, borderTop: `1px solid ${tc.toolbarBorder}` }}>
        <div data-testid="settings-section-theme" style={{ ...s.sectionHeader, color: tc.panelMuted }}>Theme</div>
        <RadioRow
          label="QuantLab Dark"
          testId="settings-radio-quantlab-dark"
          selected={settings.themePreset === 'quantlab-dark'}
          onSelect={() => onChange({ themePreset: 'quantlab-dark' })}
          labelColor={tc.panelText}
        />
        <RadioRow
          label="TradingView Dark"
          testId="settings-radio-tradingview-dark"
          selected={settings.themePreset === 'tradingview-dark'}
          onSelect={() => onChange({ themePreset: 'tradingview-dark' })}
          labelColor={tc.panelText}
        />
        <RadioRow
          label="Light"
          testId="settings-radio-light"
          selected={settings.themePreset === 'light'}
          onSelect={() => onChange({ themePreset: 'light' })}
          labelColor={tc.panelText}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ToggleRow
// ---------------------------------------------------------------------------

interface ToggleRowProps {
  label:      string
  testId:     string
  checked:    boolean
  onChange:   (v: boolean) => void
  labelColor: string
}

function ToggleRow({ label, testId, checked, onChange, labelColor }: ToggleRowProps) {
  return (
    <label style={s.toggleRow}>
      <input
        data-testid={testId}
        type="checkbox"
        checked={checked}
        onChange={e => onChange(e.target.checked)}
        style={s.checkbox}
      />
      <span style={{ ...s.toggleLabel, color: labelColor }}>{label}</span>
    </label>
  )
}

// ---------------------------------------------------------------------------
// RadioRow
// ---------------------------------------------------------------------------

interface RadioRowProps {
  label:      string
  testId:     string
  selected:   boolean
  onSelect:   () => void
  labelColor: string
}

function RadioRow({ label, testId, selected, onSelect, labelColor }: RadioRowProps) {
  return (
    <label style={s.toggleRow}>
      <input
        data-testid={testId}
        type="radio"
        checked={selected}
        onChange={onSelect}
        style={s.checkbox}
      />
      <span style={{ ...s.toggleLabel, color: labelColor }}>{label}</span>
    </label>
  )
}

// ---------------------------------------------------------------------------
// Styles (layout / structural only — colors applied dynamically above)
// ---------------------------------------------------------------------------

const s: Record<string, React.CSSProperties> = {
  panel: {
    position:     'absolute',
    top:          '100%',
    right:        0,
    zIndex:       100,
    width:        200,
    marginTop:    2,
    borderRadius: 4,
    boxShadow:    '0 4px 16px rgba(0,0,0,0.55)',
    userSelect:   'none',
  },
  header: {
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'space-between',
    padding:        '6px 10px 5px',
  },
  title: {
    fontSize:      10,
    fontFamily:    'monospace',
    letterSpacing: '0.06em',
    textTransform: 'uppercase' as const,
  },
  closeBtn: {
    background: 'transparent',
    border:     'none',
    cursor:     'pointer',
    fontSize:   14,
    lineHeight: 1,
    padding:    '0 2px',
  },
  section: {
    padding: '6px 0',
  },
  sectionHeader: {
    fontSize:      9,
    fontFamily:    'monospace',
    letterSpacing: '0.08em',
    textTransform: 'uppercase' as const,
    padding:       '0 10px 4px',
  },
  toggleRow: {
    display:    'flex',
    alignItems: 'center',
    gap:        8,
    padding:    '3px 10px',
    cursor:     'pointer',
  },
  checkbox: {
    accentColor: '#2196f3',
    cursor:      'pointer',
    flexShrink:  0,
  },
  toggleLabel: {
    fontSize:   11,
    fontFamily: 'monospace',
  },
}
