/**
 * ChartLegendOverlay — Chart-UX-3C.5.
 *
 * Lightweight React-DOM overlay positioned absolutely over the price chart canvas.
 * Renders one compact row per active indicator instance that has price-overlay series.
 * Values update live on crosshair move (values prop changes on every crosshair event).
 *
 * Architecture:
 *  - pointer-events: none on the wrapper so chart interactions pass through
 *  - individual action buttons have pointer-events: auto
 *  - hover on a legend row propagates instanceId to onHover (ownership feedback)
 *  - color chip matches rendered series color
 */
import type { IndicatorArtifactResponse } from '../types/chartIndicators'

interface LegendEntry {
  instanceId:   string
  instanceLabel: string
  series: Array<{
    seriesId:   string
    label:      string
    color:      string
    value:      number | null | undefined
  }>
  visible:      boolean
}

interface ChartLegendOverlayProps {
  /** Visible price-overlay artifacts (already filtered) */
  artifacts:           IndicatorArtifactResponse[]
  /** instance_id → hex color (palette or user-set) */
  instanceColors?:     Map<string, string>
  /** instance_id → compact label, e.g. "SMA (20)" */
  instanceLabels?:     Map<string, string>
  /** instance_id → visible */
  instanceVisible?:    Map<string, boolean>
  /** Crosshair values: instance_id → series_id → number | null */
  crosshairValues?:    Map<string, Map<string, number | null>>
  /** Which instance is highlighted (from sidebar hover) */
  highlightedId?:      string | null
  onHover?:            (instanceId: string | null) => void
  onToggle?:           (instanceId: string) => void
  onRemove?:           (instanceId: string) => void
}

function formatValue(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return v.toFixed(2)
}

export function ChartLegendOverlay({
  artifacts,
  instanceColors,
  instanceLabels,
  instanceVisible,
  crosshairValues,
  highlightedId,
  onHover,
  onToggle,
  onRemove,
}: ChartLegendOverlayProps) {
  const entries: LegendEntry[] = []

  for (const artifact of artifacts) {
    const priceSeries = artifact.series.filter(s => s.pane === 'price_overlay')
    if (priceSeries.length === 0) continue
    const iColor  = instanceColors?.get(artifact.instance_id)
    const visible = instanceVisible?.get(artifact.instance_id) ?? true
    const label   = instanceLabels?.get(artifact.instance_id) ?? artifact.display_name
    const cvMap   = crosshairValues?.get(artifact.instance_id)

    entries.push({
      instanceId:    artifact.instance_id,
      instanceLabel: label,
      visible,
      series: priceSeries.map(s => ({
        seriesId: s.series_id,
        label:    s.label,
        color:    iColor ?? s.default_color,
        value:    cvMap?.get(s.series_id),
      })),
    })
  }

  if (entries.length === 0) return null

  return (
    <div
      data-testid="chart-legend-overlay"
      style={overlayStyle}
    >
      {entries.map(entry => (
        <div
          key={entry.instanceId}
          data-testid={`legend-row-${entry.instanceId}`}
          style={{
            ...rowStyle,
            opacity: entry.visible ? 1 : 0.4,
            outline: highlightedId === entry.instanceId ? '1px solid #3a4570' : 'none',
            borderRadius: 2,
          }}
          onMouseEnter={() => onHover?.(entry.instanceId)}
          onMouseLeave={() => onHover?.(null)}
        >
          {entry.series.length === 1 ? (
            // Single-series: compact inline display
            <span style={singleRowStyle}>
              <span style={{ ...colorChipStyle, background: entry.series[0].color }} />
              <span style={labelStyle}>{entry.instanceLabel}</span>
              <span
                data-testid={`legend-value-${entry.instanceId}-${entry.series[0].seriesId}`}
                style={{ ...valueStyle, color: entry.series[0].color }}
              >
                {formatValue(entry.series[0].value)}
              </span>
              <span style={actionsStyle}>
                <button
                  type="button"
                  data-testid={`legend-toggle-${entry.instanceId}`}
                  style={actionBtnStyle}
                  onClick={() => onToggle?.(entry.instanceId)}
                  title={entry.visible ? 'Hide' : 'Show'}
                >
                  {entry.visible ? '◉' : '○'}
                </button>
                <button
                  type="button"
                  data-testid={`legend-remove-${entry.instanceId}`}
                  style={actionBtnStyle}
                  onClick={() => onRemove?.(entry.instanceId)}
                  title="Remove"
                >
                  ×
                </button>
              </span>
            </span>
          ) : (
            // Multi-series: one sub-row per series
            <div>
              <div style={multiHeaderStyle}>
                <span style={labelStyle}>{entry.instanceLabel}</span>
                <span style={actionsStyle}>
                  <button
                    type="button"
                    data-testid={`legend-toggle-${entry.instanceId}`}
                    style={actionBtnStyle}
                    onClick={() => onToggle?.(entry.instanceId)}
                    title={entry.visible ? 'Hide' : 'Show'}
                  >
                    {entry.visible ? '◉' : '○'}
                  </button>
                  <button
                    type="button"
                    data-testid={`legend-remove-${entry.instanceId}`}
                    style={actionBtnStyle}
                    onClick={() => onRemove?.(entry.instanceId)}
                    title="Remove"
                  >
                    ×
                  </button>
                </span>
              </div>
              {entry.series.map(s => (
                <div key={s.seriesId} style={singleRowStyle}>
                  <span style={{ ...colorChipStyle, background: s.color }} />
                  <span style={{ ...labelStyle, color: '#8892a4' }}>{s.label}</span>
                  <span
                    data-testid={`legend-value-${entry.instanceId}-${s.seriesId}`}
                    style={{ ...valueStyle, color: s.color }}
                  >
                    {formatValue(s.value)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

const overlayStyle: React.CSSProperties = {
  position:      'absolute',
  top:           6,
  left:          6,
  zIndex:        5,
  pointerEvents: 'none',   // pass-through to chart; action buttons override below
  display:       'flex',
  flexDirection: 'column',
  gap:           2,
}

const rowStyle: React.CSSProperties = {
  background:    'rgba(15, 15, 26, 0.72)',
  padding:       '2px 5px',
  borderRadius:  2,
  pointerEvents: 'auto',  // rows are interactive
}

const singleRowStyle: React.CSSProperties = {
  display:    'flex',
  alignItems: 'center',
  gap:        5,
}

const multiHeaderStyle: React.CSSProperties = {
  display:    'flex',
  alignItems: 'center',
  gap:        5,
}

const colorChipStyle: React.CSSProperties = {
  width:        8,
  height:       2,
  borderRadius: 1,
  flexShrink:   0,
  display:      'inline-block',
}

const labelStyle: React.CSSProperties = {
  fontSize:   10,
  fontFamily: 'monospace',
  color:      '#c4cde0',
  flex:       1,
}

const valueStyle: React.CSSProperties = {
  fontSize:    10,
  fontFamily:  'monospace',
  minWidth:    42,
  textAlign:   'right',
}

const actionsStyle: React.CSSProperties = {
  display:    'flex',
  alignItems: 'center',
  gap:        1,
  marginLeft: 3,
}

const actionBtnStyle: React.CSSProperties = {
  background:    'transparent',
  border:        'none',
  color:         '#4a5070',
  cursor:        'pointer',
  fontSize:      10,
  padding:       '0 1px',
  lineHeight:    1,
  pointerEvents: 'auto',
}
