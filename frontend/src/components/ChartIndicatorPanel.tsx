/**
 * ChartIndicatorPanel — Chart-UX-3C.1 (refinement of Chart-UX-3C).
 *
 * Compact sidebar indicator widget:
 *   - "Indicators (N)"  + Add Indicator  button
 *   - One compact row per active instance: swatch · label · eye · pencil · ×
 *   - Parameter editor collapsed by default; opens inline on pencil click
 *   - Color palette assigns distinct colors per instance
 *   - Visibility toggle hides chart series without removing the instance
 *   - "Clear All" footer button
 *   - Indicator picker as a top-mounted dropdown
 *
 * Architecture invariants:
 *   - No indicator computation in this module.
 *   - onInstancesChange callback exposes full instance state (including colors,
 *     visibility, artifacts) so App.tsx can derive what Chart.tsx renders.
 *   - Instance colors are frontend-only state; they never touch the backend.
 */
import { useEffect, useState, useRef } from 'react'
import { getChartIndicators, computeIndicatorArtifact } from '../api/chartIndicators'
import type { MarketDataParams } from '../api/marketData'
import type {
  ChartIndicatorMetadata,
  ChartIndicatorParameterSpec,
  IndicatorArtifactResponse,
  IndicatorInstance,
} from '../types/chartIndicators'

// ---------------------------------------------------------------------------
// Color palette — 10 distinct colors assigned sequentially per instance
// ---------------------------------------------------------------------------

const INSTANCE_PALETTE = [
  '#f59e0b', // amber
  '#22c55e', // green
  '#ef4444', // red
  '#3b82f6', // blue
  '#a855f7', // purple
  '#06b6d4', // cyan
  '#f97316', // orange
  '#84cc16', // lime
  '#ec4899', // pink
  '#14b8a6', // teal
]

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ChartIndicatorPanelProps {
  hasData: boolean
  params: MarketDataParams | null
  onInstancesChange: (instances: IndicatorInstance[]) => void
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let _instanceCounter = 0

/** Assign the next palette color sequentially. */
function nextPaletteColor(): string {
  _instanceCounter += 1
  return INSTANCE_PALETTE[(_instanceCounter - 1) % INSTANCE_PALETTE.length]
}

/** Reset counter (for tests) — exported only for testing. */
export function _resetInstanceCounter() { _instanceCounter = 0 }

/**
 * Compact label derived from display_name abbreviation + editable param values.
 * Metadata-driven, no tool-specific branching.
 * "Simple Moving Average" + {period:20} → "SMA (20)"
 * "Moving Average Convergence Divergence" + {fast:12,slow:26,signal:9} → "MACD (12, 26, 9)"
 */
function makeInstanceLabel(
  displayName: string,
  editableParameters: string[],
  parameters: Record<string, number | string>,
): string {
  const abbrev = displayName
    .split(/\s+/)
    .map(w => w[0]?.toUpperCase() ?? '')
    .join('')
  const values = editableParameters
    .filter(p => parameters[p] !== undefined)
    .map(p => parameters[p])
  return values.length === 0 ? abbrev : `${abbrev} (${values.join(', ')})`
}

function getDefaultParameters(
  metadata: ChartIndicatorMetadata,
): Record<string, number | string> {
  const result: Record<string, number | string> = {}
  for (const spec of metadata.parameters) {
    if (!metadata.editable_parameters.includes(spec.name)) continue
    if (spec.default !== null && spec.default !== undefined) {
      result[spec.name] = spec.default as number | string
    }
  }
  return result
}

function matchesSearch(meta: ChartIndicatorMetadata, query: string): boolean {
  if (!query.trim()) return true
  const q = query.toLowerCase()
  if (meta.tool_id.includes(q)) return true
  if (meta.display_name.toLowerCase().includes(q)) return true
  if (meta.description.toLowerCase().includes(q)) return true
  return false
}

function parseEditedParams(
  edits: Record<string, string>,
  instance: IndicatorInstance,
  specs: ChartIndicatorParameterSpec[],
): Record<string, number | string> {
  const result = { ...instance.parameters }
  for (const [name, raw] of Object.entries(edits)) {
    const spec = specs.find(p => p.name === name)
    if (!spec) { result[name] = raw; continue }
    if (spec.type_label === 'int') {
      const n = parseInt(raw, 10)
      if (!isNaN(n)) result[name] = n
    } else if (spec.type_label === 'float') {
      const n = parseFloat(raw)
      if (!isNaN(n)) result[name] = n
    } else {
      result[name] = raw
    }
  }
  return result
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ChartIndicatorPanel({ hasData, params, onInstancesChange }: ChartIndicatorPanelProps) {
  const [indicators,   setIndicators]   = useState<ChartIndicatorMetadata[]>([])
  const [metaLoading,  setMetaLoading]  = useState(false)
  const [metaError,    setMetaError]    = useState<string | null>(null)
  const [instances,    setInstances]    = useState<IndicatorInstance[]>([])
  const [showPicker,   setShowPicker]   = useState(false)
  const [searchQuery,  setSearchQuery]  = useState('')
  const [editingId,    setEditingId]    = useState<string | null>(null)
  const [editedParams, setEditedParams] = useState<Record<string, Record<string, string>>>({})

  // Stable ref to callback so effects don't depend on it
  const onChangeRef = useRef(onInstancesChange)
  onChangeRef.current = onInstancesChange

  // Notify parent whenever instances change
  useEffect(() => {
    onChangeRef.current(instances)
  }, [instances])

  // Load indicator metadata once on mount
  useEffect(() => {
    setMetaLoading(true)
    setMetaError(null)
    getChartIndicators()
      .then(resp => { setIndicators(resp.indicators); setMetaLoading(false) })
      .catch((err: unknown) => {
        setMetaError(err instanceof Error ? err.message : 'Failed to load indicators')
        setMetaLoading(false)
      })
  }, [])

  // Compute and store artifact for one instance
  async function computeArtifact(
    instance: IndicatorInstance,
    currentParams: Record<string, number | string>,
  ): Promise<void> {
    if (!params) return

    setInstances(prev =>
      prev.map(i => i.instanceId === instance.instanceId ? { ...i, loading: true, error: null } : i)
    )

    try {
      const artifact: IndicatorArtifactResponse = await computeIndicatorArtifact({
        tool_id:          instance.toolId,
        instance_id:      instance.instanceId,
        symbol:           params.symbol,
        provider:         params.provider,
        timeframe:        params.timeframe,
        date_range_start: params.start,
        date_range_end:   params.end,
        parameters:       currentParams,
        asset_class:      params.asset_class,
        exchange:         params.exchange ?? '',
        credential_id:    params.credential_id,
      })
      setInstances(prev =>
        prev.map(i =>
          i.instanceId === instance.instanceId
            ? { ...i, artifact, loading: false, error: null, parameters: currentParams }
            : i
        )
      )
    } catch (err: unknown) {
      setInstances(prev =>
        prev.map(i =>
          i.instanceId === instance.instanceId
            ? { ...i, loading: false, error: err instanceof Error ? err.message : 'Computation failed' }
            : i
        )
      )
    }
  }

  async function handleAddIndicator(metadata: ChartIndicatorMetadata) {
    if (!params) return
    const color = nextPaletteColor()
    const instanceId = `${metadata.tool_id}_${_instanceCounter}`
    const defaultParams = getDefaultParameters(metadata)
    const label = makeInstanceLabel(metadata.display_name, metadata.editable_parameters, defaultParams)

    const newInstance: IndicatorInstance = {
      instanceId,
      toolId:        metadata.tool_id,
      displayName:   metadata.display_name,
      instanceLabel: label,
      instanceColor: color,
      seriesColors:  {},
      parameters:    defaultParams,
      artifact:      null,
      visible:       true,
      loading:       true,
      error:         null,
    }

    const next = [...instances, newInstance]
    setInstances(next)
    setEditedParams(prev => ({ ...prev, [instanceId]: _toStrings(defaultParams) }))
    setShowPicker(false)

    await computeArtifact(newInstance, defaultParams)
  }

  function handleToggleVisible(instanceId: string) {
    setInstances(prev =>
      prev.map(i => i.instanceId === instanceId ? { ...i, visible: !i.visible } : i)
    )
  }

  function handleRemove(instanceId: string) {
    if (editingId === instanceId) setEditingId(null)
    setInstances(prev => prev.filter(i => i.instanceId !== instanceId))
    setEditedParams(prev => { const n = { ...prev }; delete n[instanceId]; return n })
  }

  function handleClearAll() {
    setInstances([])
    setEditedParams({})
    setEditingId(null)
  }

  async function handleApply(instance: IndicatorInstance) {
    if (!params) return
    const specs = indicators.find(m => m.tool_id === instance.toolId)?.parameters ?? []
    const parsed = parseEditedParams(editedParams[instance.instanceId] ?? {}, instance, specs)
    const label = makeInstanceLabel(
      instance.displayName,
      indicators.find(m => m.tool_id === instance.toolId)?.editable_parameters ?? [],
      parsed,
    )
    // Update label when params change
    setInstances(prev => prev.map(i =>
      i.instanceId === instance.instanceId ? { ...i, instanceLabel: label } : i
    ))
    setEditingId(null)
    await computeArtifact({ ...instance, parameters: parsed }, parsed)
  }

  function handleCancel() {
    setEditingId(null)
  }

  function handleSeriesColorChange(instanceId: string, seriesId: string, color: string) {
    setInstances(prev => prev.map(i => {
      if (i.instanceId !== instanceId) return i
      const newSeriesColors = { ...i.seriesColors, [seriesId]: color }
      // For single-series indicators also update instanceColor so the palette swatch reflects the choice
      const isSingleSeries = (i.artifact?.series.length ?? 0) === 1
      return { ...i, seriesColors: newSeriesColors, instanceColor: isSingleSeries ? color : i.instanceColor }
    }))
  }

  // Category map for picker
  const categoryMap = new Map<string, ChartIndicatorMetadata[]>()
  for (const m of indicators) {
    if (searchQuery.trim() && !matchesSearch(m, searchQuery)) continue
    const list = categoryMap.get(m.category) ?? []
    categoryMap.set(m.category, [...list, m])
  }

  const canAdd = hasData && !!params

  return (
    <div data-testid="chart-indicator-panel" style={s.panel}>
      {/* ── Header ── */}
      <div style={s.header}>
        <span style={s.title}>
          Indicators{instances.length > 0 ? ` (${instances.length})` : ''}
        </span>
        <button
          type="button"
          data-testid="indicators-btn"
          style={s.addBtn}
          onClick={() => setShowPicker(p => !p)}
          disabled={!hasData}
          title={!hasData ? 'Load chart data first' : 'Add indicator'}
        >
          + Add Indicator
        </button>
      </div>

      {/* ── Picker dropdown ── */}
      {showPicker && (
        <div data-testid="indicator-picker" style={s.picker}>
          <input
            data-testid="indicator-search"
            type="text"
            placeholder="Search indicators…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            style={s.searchInput}
            autoFocus
          />

          {!canAdd && hasData && (
            <div data-testid="indicator-catalog-notice" style={s.notice}>
              Requires provider-sourced data.
            </div>
          )}
          {metaLoading && (
            <div data-testid="indicator-meta-loading" style={s.status}>Loading…</div>
          )}
          {metaError && (
            <div data-testid="indicator-meta-error" style={{ ...s.status, color: '#ef5350' }}>
              {metaError}
            </div>
          )}
          {!metaLoading && !metaError && (
            <div data-testid="indicator-categories">
              {categoryMap.size === 0 && (
                <div data-testid="indicator-no-results" style={s.status}>
                  No results for "{searchQuery}"
                </div>
              )}
              {[...categoryMap.entries()].map(([cat, tools]) => (
                <div key={cat} data-testid={`indicator-category-${cat.toLowerCase()}`}>
                  <div style={s.catLabel}>{cat}</div>
                  {tools.map(meta => (
                    <div key={meta.tool_id} data-testid={`indicator-tool-${meta.tool_id}`} style={s.toolRow}>
                      <span style={s.toolName}>{meta.display_name}</span>
                      <button
                        type="button"
                        data-testid={`add-indicator-${meta.tool_id}`}
                        style={s.toolAddBtn}
                        disabled={!canAdd}
                        onClick={() => handleAddIndicator(meta)}
                      >
                        + Add
                      </button>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Active indicator list ── */}
      {instances.length > 0 && (
        <div data-testid="active-indicators" style={s.activeList}>
          {instances.map(inst => {
            const specs = indicators.find(m => m.tool_id === inst.toolId)?.parameters ?? []
            const editableSpecs = specs.filter(p =>
              indicators.find(m => m.tool_id === inst.toolId)?.editable_parameters.includes(p.name) ?? false
            )
            const currEdits = editedParams[inst.instanceId] ?? _toStrings(inst.parameters)
            const isEditing = editingId === inst.instanceId

            return (
              <div key={inst.instanceId} data-testid={`indicator-instance-${inst.instanceId}`} style={s.instOuter}>
                {/* Compact row */}
                <div style={{ ...s.instRow, opacity: inst.visible ? 1 : 0.4 }}>
                  {/* Color swatch */}
                  <span
                    data-testid={`swatch-${inst.instanceId}`}
                    style={{ ...s.swatch, background: inst.instanceColor }}
                  />

                  {/* Label */}
                  <span
                    data-testid={`label-${inst.instanceId}`}
                    style={s.instLabel}
                  >
                    {inst.instanceLabel}
                    {inst.loading && <span style={s.loadingDot}> ···</span>}
                    {inst.error && (
                      <span
                        data-testid={`indicator-error-${inst.instanceId}`}
                        style={s.errorDot}
                        title={inst.error}
                      > !</span>
                    )}
                  </span>

                  {/* Actions */}
                  <div style={s.actions}>
                    <button
                      type="button"
                      data-testid={`toggle-visible-${inst.instanceId}`}
                      style={s.iconBtn}
                      onClick={() => handleToggleVisible(inst.instanceId)}
                      title={inst.visible ? 'Hide' : 'Show'}
                    >
                      {inst.visible ? '◉' : '○'}
                    </button>
                    <button
                      type="button"
                      data-testid={`settings-${inst.instanceId}`}
                      style={{ ...s.iconBtn, color: isEditing ? '#7986cb' : '#4a5070' }}
                      onClick={() => setEditingId(isEditing ? null : inst.instanceId)}
                      title="Edit parameters"
                    >
                      ⚙
                    </button>
                    <button
                      type="button"
                      data-testid={`remove-${inst.instanceId}`}
                      style={s.iconBtn}
                      onClick={() => handleRemove(inst.instanceId)}
                      title="Remove"
                    >
                      ×
                    </button>
                  </div>
                </div>

                {/* Inline parameter editor — collapsed by default */}
                {isEditing && (
                  <div data-testid={`editor-${inst.instanceId}`} style={s.editor}>
                    {editableSpecs.map(spec => {
                      const val = currEdits[spec.name] ?? String(inst.parameters[spec.name] ?? '')
                      return (
                        <label key={spec.name} style={s.paramRow}>
                          <span style={s.paramName}>{spec.name}</span>
                          <input
                            data-testid={`param-${inst.instanceId}-${spec.name}`}
                            type="number"
                            value={val}
                            min={spec.min_value ?? undefined}
                            max={spec.max_value ?? undefined}
                            step={spec.type_label === 'float' ? 0.1 : 1}
                            onChange={e => setEditedParams(prev => ({
                              ...prev,
                              [inst.instanceId]: { ...(prev[inst.instanceId] ?? {}), [spec.name]: e.target.value },
                            }))}
                            style={s.paramInput}
                          />
                        </label>
                      )
                    })}

                    {/* Per-series color editor — applies immediately without backend recompute */}
                    {inst.artifact && inst.artifact.series.length > 0 && (
                      <div data-testid={`color-section-${inst.instanceId}`} style={s.colorSection}>
                        <div style={s.colorSectionTitle}>Colors</div>
                        {inst.artifact.series.map(series => {
                          const effectiveColor = inst.seriesColors[series.series_id]
                            ?? (inst.artifact!.series.length === 1 ? inst.instanceColor : series.default_color)
                          return (
                            <label key={series.series_id} style={s.colorRow}>
                              <span style={s.paramName}>{series.label}</span>
                              <input
                                data-testid={`color-${inst.instanceId}-${series.series_id}`}
                                type="color"
                                value={effectiveColor}
                                onChange={e => handleSeriesColorChange(inst.instanceId, series.series_id, e.target.value)}
                                style={s.colorInput}
                              />
                            </label>
                          )
                        })}
                      </div>
                    )}

                    <div style={s.editorFooter}>
                      <button
                        type="button"
                        data-testid={`apply-${inst.instanceId}`}
                        style={s.applyBtn}
                        onClick={() => handleApply(inst)}
                        disabled={inst.loading || !params}
                      >
                        Apply
                      </button>
                      <button
                        type="button"
                        data-testid={`cancel-${inst.instanceId}`}
                        style={s.cancelBtn}
                        onClick={handleCancel}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )
          })}

          {/* Clear All */}
          <div style={s.footer}>
            <button
              type="button"
              data-testid="clear-all-btn"
              style={s.clearBtn}
              onClick={handleClearAll}
            >
              🗑 Clear All
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------

function _toStrings(params: Record<string, number | string>): Record<string, string> {
  const r: Record<string, string> = {}
  for (const [k, v] of Object.entries(params)) r[k] = String(v)
  return r
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const s: Record<string, React.CSSProperties> = {
  panel: {
    borderTop:  '1px solid #1a1a2e',
    background: '#0a0a14',
    flexShrink: 0,
  },
  header: {
    display:      'flex',
    alignItems:   'center',
    padding:      '7px 10px 6px',
    gap:          6,
    borderBottom: '1px solid #12121e',
  },
  title: {
    flex:        1,
    fontSize:    11,
    fontFamily:  'monospace',
    color:       '#7986a8',
    fontWeight:  600,
    letterSpacing: '0.03em',
  },
  addBtn: {
    background:   '#141426',
    border:       '1px solid #2a2d3e',
    borderRadius: 3,
    color:        '#7986cb',
    fontFamily:   'monospace',
    fontSize:     10,
    padding:      '2px 7px',
    cursor:       'pointer',
  },
  picker: {
    background:   '#0d0d1e',
    borderBottom: '1px solid #1a1a2e',
    maxHeight:    340,
    overflowY:    'auto' as const,
  },
  searchInput: {
    display:      'block',
    width:        'calc(100% - 20px)',
    margin:       '8px 10px',
    padding:      '5px 8px',
    background:   '#0a0a14',
    border:       '1px solid #2a2d3e',
    borderRadius: 3,
    color:        '#c4cde0',
    fontFamily:   'monospace',
    fontSize:     11,
    outline:      'none',
    boxSizing:    'border-box' as const,
  },
  notice: { padding: '5px 10px 8px', fontSize: 10, color: '#5a6070', fontStyle: 'italic' as const },
  status: { padding: '5px 10px 8px', fontSize: 10, color: '#5a6070' },
  catLabel: {
    padding:       '5px 10px 2px',
    fontSize:      9,
    color:         '#3a4055',
    fontFamily:    'monospace',
    letterSpacing: '0.07em',
    textTransform: 'uppercase' as const,
  },
  toolRow: {
    display:    'flex',
    alignItems: 'center',
    padding:    '3px 10px',
    gap:        6,
  },
  toolName: {
    flex:       1,
    fontSize:   11,
    color:      '#c4cde0',
    fontFamily: 'monospace',
  },
  toolAddBtn: {
    background:   '#141426',
    border:       '1px solid #2a2d3e',
    borderRadius: 3,
    color:        '#7986cb',
    fontFamily:   'monospace',
    fontSize:     10,
    padding:      '1px 6px',
    cursor:       'pointer',
    whiteSpace:   'nowrap' as const,
  },
  activeList: {
    overflowY:  'auto' as const,
    maxHeight:  260,
  },
  instOuter: {
    borderBottom: '1px solid #0d0d1a',
  },
  instRow: {
    display:    'flex',
    alignItems: 'center',
    padding:    '4px 8px 4px 10px',
    gap:        6,
    transition: 'opacity 0.1s',
  },
  swatch: {
    width:        8,
    height:       8,
    borderRadius: '50%',
    flexShrink:   0,
  },
  instLabel: {
    flex:       1,
    fontSize:   11,
    fontFamily: 'monospace',
    color:      '#c4cde0',
    overflow:   'hidden',
    textOverflow: 'ellipsis' as const,
    whiteSpace: 'nowrap' as const,
  },
  loadingDot: { color: '#4a5070', fontSize: 9 },
  errorDot:   { color: '#ef5350', fontSize: 10, cursor: 'help' },
  actions: {
    display:    'flex',
    alignItems: 'center',
    gap:        1,
    flexShrink: 0,
  },
  iconBtn: {
    background: 'transparent',
    border:     'none',
    color:      '#4a5070',
    cursor:     'pointer',
    fontSize:   12,
    padding:    '0 3px',
    lineHeight: 1,
  },
  editor: {
    padding:    '6px 10px 8px',
    background: '#0d0d1a',
  },
  paramRow: {
    display:      'flex',
    alignItems:   'center',
    gap:          6,
    marginBottom: 4,
  },
  paramName: {
    fontSize:  10,
    color:     '#4a5070',
    fontFamily: 'monospace',
    minWidth:  60,
  },
  paramInput: {
    width:        56,
    padding:      '2px 4px',
    background:   '#0a0a14',
    border:       '1px solid #2a2d3e',
    borderRadius: 3,
    color:        '#c4cde0',
    fontFamily:   'monospace',
    fontSize:     11,
  },
  editorFooter: {
    display: 'flex',
    gap:     6,
    marginTop: 5,
  },
  applyBtn: {
    background:   '#141426',
    border:       '1px solid #3a4570',
    borderRadius: 3,
    color:        '#7986cb',
    fontFamily:   'monospace',
    fontSize:     10,
    padding:      '2px 8px',
    cursor:       'pointer',
  },
  cancelBtn: {
    background:   'transparent',
    border:       '1px solid #2a2d3e',
    borderRadius: 3,
    color:        '#4a5070',
    fontFamily:   'monospace',
    fontSize:     10,
    padding:      '2px 8px',
    cursor:       'pointer',
  },
  footer: {
    padding:   '5px 10px',
    borderTop: '1px solid #12121e',
  },
  clearBtn: {
    background:   'transparent',
    border:       'none',
    color:        '#4a5070',
    fontFamily:   'monospace',
    fontSize:     10,
    cursor:       'pointer',
    padding:      0,
  },
  colorSection: {
    marginTop:  6,
    paddingTop: 5,
    borderTop:  '1px solid #1a1a2e',
  },
  colorSectionTitle: {
    fontSize:      9,
    color:         '#3a4055',
    fontFamily:    'monospace',
    letterSpacing: '0.07em',
    textTransform: 'uppercase' as const,
    marginBottom:  4,
  },
  colorRow: {
    display:      'flex',
    alignItems:   'center',
    gap:          6,
    marginBottom: 3,
  },
  colorInput: {
    width:        32,
    height:       20,
    padding:      1,
    border:       '1px solid #2a2d3e',
    borderRadius: 3,
    background:   '#0a0a14',
    cursor:       'pointer',
  },
}
