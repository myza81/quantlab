/**
 * ChartIndicatorPanel — Chart-UX-3C.1 / VOL-UX-1.
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
 * Volume UX consolidation (VOL-UX-1/2):
 *   - The picker exposes a single "Volume" entry; "Volume MA" is hidden.
 *   - The Volume settings panel shows a "Show Volume MA" checkbox + MA Length.
 *   - MA disabled  → toolId='volume', {} sent to backend.
 *   - MA enabled   → toolId='volume_ma', { ma_length } sent to backend.
 *   - Histogram bar color mode: directional (red/green) or single (one color).
 *   - Synthetic params (never sent to backend): show_volume_ma, volume_color_mode,
 *     volume_color.
 *
 * Architecture invariants:
 *   - No indicator computation in this module.
 *   - onInstancesChange callback exposes full instance state (including colors,
 *     visibility, artifacts) so App.tsx can derive what Chart.tsx renders.
 *   - Instance colors are frontend-only state; they never touch the backend.
 */
import { useEffect, useState, useRef, forwardRef, useImperativeHandle } from 'react'
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
  /** Instance to visually highlight (from chart legend hover) */
  highlightedInstanceId?: string | null
  /** Report which instance is hovered (for chart legend highlight) */
  onHoverInstance?: (instanceId: string | null) => void
}

/** Imperative handle exposed via forwardRef — lets Chart trigger actions. */
export interface ChartIndicatorPanelHandle {
  toggleVisible:  (instanceId: string) => void
  removeInstance: (instanceId: string) => void
  openSettings:   (instanceId: string) => void
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
  shortName?: string,
): string {
  // Use short_name from metadata when available; otherwise abbreviate display name
  // (first letter of each word) for backward compat with future custom tools.
  const prefix = shortName ?? displayName
    .split(/\s+/)
    .map(w => w[0]?.toUpperCase() ?? '')
    .join('')
  const values = editableParameters
    .filter(p => parameters[p] !== undefined)
    .map(p => parameters[p])
  return values.length === 0 ? prefix : `${prefix}(${values.join(', ')})`
}

/**
 * Controlled dropdown options for well-known string parameters.
 * Prevents free-text entry for values that must come from a fixed set.
 * Keyed by parameter name; value is the ordered list of accepted options.
 */
const CHART_PARAM_DROPDOWNS: Readonly<Record<string, readonly string[]>> = {
  source: ['close', 'open', 'high', 'low', 'hl2', 'hlc3', 'ohlc4'],
}

// ---------------------------------------------------------------------------
// Volume indicator consolidation (VOL-UX-1)
// ---------------------------------------------------------------------------

const VOLUME_TOOL_ID    = 'volume'
const VOLUME_MA_TOOL_ID = 'volume_ma'
const VOLUME_MA_DEFAULT = 20
const VOLUME_COLOR_DEFAULT    = '#26a69a'  // green — matches Chart.tsx VOLUME_UP_COLOR

/** True for both 'volume' and 'volume_ma' — these share one user-facing instance. */
function isVolumeFamily(toolId: string): boolean {
  return toolId === VOLUME_TOOL_ID || toolId === VOLUME_MA_TOOL_ID
}

// ---------------------------------------------------------------------------
// RSI indicator consolidation (RSI-UX-1C.1)
// ---------------------------------------------------------------------------

const RSI_TOOL_ID           = 'rsi'
const RSI_MIDLINE_TOOL_ID   = 'rsi_midline'
const RSI_SMOOTHING_TOOL_ID = 'rsi_smoothing'
const RSI_MIDLINE_DEFAULT   = 50

function parseRsiMidlineValue(raw: unknown): number {
  const n = typeof raw === 'number' ? raw : parseFloat(String(raw ?? RSI_MIDLINE_DEFAULT))
  return Number.isNaN(n) ? RSI_MIDLINE_DEFAULT : n
}

/**
 * Frontend UX defaults — override backend metadata defaults per tool_id.
 * Only applied at instance creation time; never overwrites existing or
 * restored instances.  Add new tool_ids here as needed.
 */
const _UX_DEFAULTS: Record<string, Record<string, number | string>> = {
  sma:  { period: 21 },
  ema:  { period: 9  },
  rsi:  { period: 14 },
  atr:  { period: 14 },
  macd: { fast_period: 12, slow_period: 26, signal_period: 9 },
}

function getDefaultParameters(
  metadata: ChartIndicatorMetadata,
): Record<string, number | string> {
  const result: Record<string, number | string> = {}
  // First pass: use backend defaults for all editable parameters
  for (const spec of metadata.parameters) {
    if (!metadata.editable_parameters.includes(spec.name)) continue
    if (spec.default !== null && spec.default !== undefined) {
      result[spec.name] = spec.default as number | string
    }
  }
  // Second pass: apply UX defaults (Chart-UX-3C.6A) to override backend defaults
  const overrides = _UX_DEFAULTS[metadata.tool_id] ?? {}
  for (const [key, val] of Object.entries(overrides)) {
    // Only apply override if the parameter is actually editable (in metadata.editable_parameters)
    if (metadata.editable_parameters.includes(key)) {
      result[key] = val
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

export const ChartIndicatorPanel = forwardRef<ChartIndicatorPanelHandle, ChartIndicatorPanelProps>(
function ChartIndicatorPanel({ hasData, params, onInstancesChange, highlightedInstanceId, onHoverInstance }: ChartIndicatorPanelProps, ref) {
  const [indicators,   setIndicators]   = useState<ChartIndicatorMetadata[]>([])
  const [metaLoading,  setMetaLoading]  = useState(false)
  const [metaError,    setMetaError]    = useState<string | null>(null)
  const [instances,    setInstances]    = useState<IndicatorInstance[]>([])
  const [showPicker,   setShowPicker]   = useState(false)
  const [searchQuery,  setSearchQuery]  = useState('')
  const [editingId,    setEditingId]    = useState<string | null>(null)
  const [editedParams, setEditedParams] = useState<Record<string, Record<string, string>>>({})

  // Expose actions to parent (App.tsx wires these to Chart legend/header buttons)
  useImperativeHandle(ref, () => ({
    toggleVisible:  handleToggleVisible,
    removeInstance: handleRemove,
    openSettings:   (id: string) => setEditingId(id),
  }), []) // eslint-disable-line react-hooks/exhaustive-deps

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
      // RSI-1C.1/1C.3: Request rsi, rsi_midline, and optionally rsi_smoothing artifacts
      if (instance.toolId === RSI_TOOL_ID) {
        const rsiPeriod = typeof currentParams.period === 'number'
          ? currentParams.period
          : parseInt(String(currentParams.period ?? 14), 10) || 14
        const midlineValue = parseRsiMidlineValue(currentParams.midline_value)
        const showSmoothing = currentParams.show_smoothing === 1 || currentParams.show_smoothing === '1'
        const smoothingType = String(currentParams.smoothing_type ?? 'SMA')
        const smoothingLength = typeof currentParams.smoothing_length === 'number'
          ? currentParams.smoothing_length
          : parseInt(String(currentParams.smoothing_length ?? 14), 10) || 14

        try {
          // Request RSI artifact
          const rsiArtifact: IndicatorArtifactResponse = await computeIndicatorArtifact({
            tool_id:          RSI_TOOL_ID,
            instance_id:      `${instance.instanceId}_rsi`,
            symbol:           params.symbol,
            provider:         params.provider,
            timeframe:        params.timeframe,
            date_range_start: params.start,
            date_range_end:   params.end,
            parameters:       { period: rsiPeriod },
            asset_class:      params.asset_class,
            exchange:         params.exchange ?? '',
            credential_id:    params.credential_id,
          })

          // Request RSI Midline artifact
          const midlineArtifact: IndicatorArtifactResponse = await computeIndicatorArtifact({
            tool_id:          RSI_MIDLINE_TOOL_ID,
            instance_id:      `${instance.instanceId}_midline`,
            symbol:           params.symbol,
            provider:         params.provider,
            timeframe:        params.timeframe,
            date_range_start: params.start,
            date_range_end:   params.end,
            parameters:       { value: midlineValue },
            asset_class:      params.asset_class,
            exchange:         params.exchange ?? '',
            credential_id:    params.credential_id,
          })

          // Merge artifacts: start with rsi + midline
          const seriesArray = [...rsiArtifact.series, ...midlineArtifact.series]

          // RSI-1C.3: Optionally request and merge RSI Smoothing artifact
          if (showSmoothing) {
            const smoothingArtifact: IndicatorArtifactResponse = await computeIndicatorArtifact({
              tool_id:          RSI_SMOOTHING_TOOL_ID,
              instance_id:      `${instance.instanceId}_smoothing`,
              symbol:           params.symbol,
              provider:         params.provider,
              timeframe:        params.timeframe,
              date_range_start: params.start,
              date_range_end:   params.end,
              parameters:       {
                period: rsiPeriod,
                smoothing_type: smoothingType,
                smoothing_length: smoothingLength,
              },
              asset_class:      params.asset_class,
              exchange:         params.exchange ?? '',
              credential_id:    params.credential_id,
            })
            seriesArray.push(...smoothingArtifact.series)
          }

          // Merge all artifacts
          const mergedArtifact: IndicatorArtifactResponse = {
            ...rsiArtifact,
            series: seriesArray,
          }

          setInstances(prev =>
            prev.map(i =>
              i.instanceId === instance.instanceId
                ? {
                    ...i,
                    artifact: mergedArtifact,
                    loading: false,
                    error: null,
                    parameters: {
                      period: rsiPeriod,
                      midline_value: midlineValue,
                      show_smoothing: showSmoothing ? 1 : 0,
                      smoothing_type: smoothingType,
                      smoothing_length: smoothingLength,
                    },
                  }
                : i
            )
          )
        } catch (err: unknown) {
          setInstances(prev =>
            prev.map(i =>
              i.instanceId === instance.instanceId
                ? {
                    ...i,
                    loading: false,
                    error: err instanceof Error ? err.message : 'Computation failed',
                  }
                : i
            )
          )
        }
        return
      }

      // Build backend-safe params: volume family strips all frontend-only keys.
      // volume → {}; volume_ma → just ma_length; other tools → all params.
      let apiParams: Record<string, number | string>
      if (isVolumeFamily(instance.toolId)) {
        if (instance.toolId === VOLUME_MA_TOOL_ID) {
          const ml = typeof currentParams.ma_length === 'number'
            ? currentParams.ma_length
            : parseInt(String(currentParams.ma_length ?? VOLUME_MA_DEFAULT), 10) || VOLUME_MA_DEFAULT
          apiParams = { ma_length: ml }
        } else {
          apiParams = {}
        }
      } else {
        apiParams = currentParams
      }

      const artifact: IndicatorArtifactResponse = await computeIndicatorArtifact({
        tool_id:          instance.toolId,
        instance_id:      instance.instanceId,
        symbol:           params.symbol,
        provider:         params.provider,
        timeframe:        params.timeframe,
        date_range_start: params.start,
        date_range_end:   params.end,
        parameters:       apiParams,
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
    const color      = nextPaletteColor()
    const instanceId = `${metadata.tool_id}_${_instanceCounter}`

    // Volume consolidation: inject synthetic settings with MA disabled by default.
    // Backend receives only {}, not the synthetic show_volume_ma / ma_length params.
    // RSI consolidation (RSI-1C.1): inject synthetic settings with midline and smoothing disabled.
    let finalParams: Record<string, number | string>
    let label: string
    if (metadata.tool_id === VOLUME_TOOL_ID) {
      finalParams = {
        show_volume_ma: 0,
        ma_length: VOLUME_MA_DEFAULT,
        volume_color_mode: 'directional',
        volume_color: VOLUME_COLOR_DEFAULT,
      }
      label       = 'Volume'
    } else if (metadata.tool_id === RSI_TOOL_ID) {
      // RSI-1C.1: Create composite RSI instance with midline.
      // Smoothing will be added in RSI-1C.2.
      finalParams = {
        period: 14,
        midline_value: RSI_MIDLINE_DEFAULT,
        show_smoothing: 0,
        smoothing_type: 'SMA',
        smoothing_length: 14,
      }
      label       = 'RSI'
    } else {
      finalParams = getDefaultParameters(metadata)
      label       = makeInstanceLabel(metadata.display_name, metadata.editable_parameters, finalParams, metadata.short_name)
    }

    const newInstance: IndicatorInstance = {
      instanceId,
      toolId:           metadata.tool_id,
      displayName:      metadata.display_name,
      instanceLabel:    label,
      instanceColor:    color,
      seriesColors:     {},
      seriesLineStyles: {},
      parameters:       finalParams,
      artifact:         null,
      visible:          true,
      loading:          true,
      error:            null,
    }

    const next = [...instances, newInstance]
    setInstances(next)
    setEditedParams(prev => ({ ...prev, [instanceId]: _toStrings(finalParams) }))
    setShowPicker(false)

    await computeArtifact(newInstance, finalParams)
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

    // Volume family: custom apply — switches toolId based on show_volume_ma checkbox.
    if (isVolumeFamily(instance.toolId)) {
      const edits     = editedParams[instance.instanceId] ?? {}
      const showMA     = edits.show_volume_ma === '1'
      const maLength   = parseInt(edits.ma_length ?? String(VOLUME_MA_DEFAULT), 10) || VOLUME_MA_DEFAULT
      const colorMode  = edits.volume_color_mode ?? 'directional'
      const volumeColor = edits.volume_color ?? VOLUME_COLOR_DEFAULT
      const newToolId  = showMA ? VOLUME_MA_TOOL_ID : VOLUME_TOOL_ID
      const newParams: Record<string, number | string> = {
        show_volume_ma: showMA ? 1 : 0,
        ma_length: maLength,
        volume_color_mode: colorMode,
        volume_color: volumeColor,
      }
      const newLabel   = showMA ? `Volume MA (${maLength})` : 'Volume'
      setInstances(prev => prev.map(i =>
        i.instanceId === instance.instanceId
          ? { ...i, toolId: newToolId, parameters: newParams, instanceLabel: newLabel }
          : i
      ))
      setEditingId(null)
      await computeArtifact({ ...instance, toolId: newToolId, parameters: newParams }, newParams)
      return
    }

    // RSI custom apply (RSI-1C.2)
    if (instance.toolId === RSI_TOOL_ID) {
      const edits = editedParams[instance.instanceId] ?? {}
      const period = parseInt(edits.period ?? String(instance.parameters.period ?? 14), 10) || 14
      const midlineValue = parseRsiMidlineValue(edits.midline_value ?? instance.parameters.midline_value)
      const showSmoothing = edits.show_smoothing === '1'
      const smoothingType = edits.smoothing_type ?? String(instance.parameters.smoothing_type ?? 'SMA')
      const smoothingLength = parseInt(edits.smoothing_length ?? String(instance.parameters.smoothing_length ?? 14), 10) || 14

      const newParams: Record<string, number | string> = {
        period,
        midline_value: midlineValue,
        show_smoothing: showSmoothing ? 1 : 0,
        smoothing_type: smoothingType,
        smoothing_length: smoothingLength,
      }

      // Label: "RSI (period)" — shown on compact row
      const newLabel = `RSI (${period})`

      setInstances(prev => prev.map(i =>
        i.instanceId === instance.instanceId
          ? { ...i, parameters: newParams, instanceLabel: newLabel }
          : i
      ))
      setEditingId(null)
      await computeArtifact({ ...instance, parameters: newParams }, newParams)
      return
    }

    // Generic apply for all other indicators.
    const specs  = indicators.find(m => m.tool_id === instance.toolId)?.parameters ?? []
    const parsed = parseEditedParams(editedParams[instance.instanceId] ?? {}, instance, specs)
    const label  = makeInstanceLabel(
      instance.displayName,
      indicators.find(m => m.tool_id === instance.toolId)?.editable_parameters ?? [],
      parsed,
      indicators.find(m => m.tool_id === instance.toolId)?.short_name,
    )
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

  function handleSeriesLineStyleChange(instanceId: string, seriesId: string, style: string) {
    setInstances(prev => prev.map(i => {
      if (i.instanceId !== instanceId) return i
      return { ...i, seriesLineStyles: { ...i.seriesLineStyles, [seriesId]: style } }
    }))
  }

  // Category map for picker.
  // volume_ma is intentionally excluded: it is surfaced through the single
  // "Volume" indicator's settings panel (Show Volume MA checkbox).
  // rsi_midline and rsi_smoothing are intentionally excluded: they are managed
  // through the single "RSI" indicator's settings panel (RSI-1C.1).
  const categoryMap = new Map<string, ChartIndicatorMetadata[]>()
  for (const m of indicators) {
    if (m.tool_id === VOLUME_MA_TOOL_ID) continue
    if (m.tool_id === RSI_MIDLINE_TOOL_ID || m.tool_id === RSI_SMOOTHING_TOOL_ID) continue
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
              <div
                key={inst.instanceId}
                data-testid={`indicator-instance-${inst.instanceId}`}
                style={{
                  ...s.instOuter,
                  outline: highlightedInstanceId === inst.instanceId ? '1px solid #3a4570' : 'none',
                  borderRadius: 2,
                }}
                onMouseEnter={() => onHoverInstance?.(inst.instanceId)}
                onMouseLeave={() => onHoverInstance?.(null)}
              >
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

                {/* ── Volume settings (VOL-UX-2) ── */}
                {isEditing && isVolumeFamily(inst.toolId) && (
                  <div data-testid={`editor-${inst.instanceId}`} style={s.editor}>

                    {/* Show Volume MA toggle */}
                    <label style={s.paramRow}>
                      <span style={s.paramName}>Show Volume MA</span>
                      <input
                        data-testid={`param-${inst.instanceId}-show_volume_ma`}
                        type="checkbox"
                        checked={currEdits.show_volume_ma === '1'}
                        onChange={e => setEditedParams(prev => ({
                          ...prev,
                          [inst.instanceId]: {
                            ...(prev[inst.instanceId] ?? {}),
                            show_volume_ma: e.target.checked ? '1' : '0',
                          },
                        }))}
                        style={{ cursor: 'pointer' }}
                      />
                    </label>

                    {/* MA Length — only shown when MA is enabled */}
                    {currEdits.show_volume_ma === '1' && (
                      <label style={s.paramRow}>
                        <span style={s.paramName}>MA Length</span>
                        <input
                          data-testid={`param-${inst.instanceId}-ma_length`}
                          type="number"
                          value={currEdits.ma_length ?? String(VOLUME_MA_DEFAULT)}
                          min={1}
                          step={1}
                          onChange={e => setEditedParams(prev => ({
                            ...prev,
                            [inst.instanceId]: {
                              ...(prev[inst.instanceId] ?? {}),
                              ma_length: e.target.value,
                            },
                          }))}
                          style={s.paramInput}
                        />
                      </label>
                    )}

                    {/* Histogram bar color mode — always visible, no artifact gate */}
                    <div style={s.paramRow}>
                      <span style={s.paramName}>Bar Color</span>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                          <input
                            data-testid={`param-${inst.instanceId}-volume_color_mode-directional`}
                            type="radio"
                            name={`volume_color_mode_${inst.instanceId}`}
                            value="directional"
                            checked={currEdits.volume_color_mode !== 'single'}
                            onChange={() => setEditedParams(prev => ({
                              ...prev,
                              [inst.instanceId]: {
                                ...(prev[inst.instanceId] ?? {}),
                                volume_color_mode: 'directional',
                              },
                            }))}
                          />
                          <span style={s.paramName}>Directional</span>
                        </label>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                          <input
                            data-testid={`param-${inst.instanceId}-volume_color_mode-single`}
                            type="radio"
                            name={`volume_color_mode_${inst.instanceId}`}
                            value="single"
                            checked={currEdits.volume_color_mode === 'single'}
                            onChange={() => setEditedParams(prev => ({
                              ...prev,
                              [inst.instanceId]: {
                                ...(prev[inst.instanceId] ?? {}),
                                volume_color_mode: 'single',
                              },
                            }))}
                          />
                          <span style={s.paramName}>Single</span>
                        </label>
                      </div>
                    </div>

                    {/* Volume bar color picker — always visible; only effective in single mode */}
                    <label style={{ ...s.colorRow, opacity: currEdits.volume_color_mode === 'single' ? 1 : 0.4 }}>
                      <span style={s.paramName}>Color</span>
                      <input
                        data-testid={`param-${inst.instanceId}-volume_color`}
                        type="color"
                        value={currEdits.volume_color ?? VOLUME_COLOR_DEFAULT}
                        disabled={currEdits.volume_color_mode !== 'single'}
                        onChange={e => setEditedParams(prev => ({
                          ...prev,
                          [inst.instanceId]: {
                            ...(prev[inst.instanceId] ?? {}),
                            volume_color: e.target.value,
                          },
                        }))}
                        style={s.colorInput}
                      />
                    </label>

                    {/* MA line color — only when MA enabled and artifact has volume_ma series */}
                    {(() => {
                      if (currEdits.show_volume_ma !== '1' || !inst.artifact) return null
                      const maSer = inst.artifact.series.find(ser => ser.series_id === 'volume_ma')
                      if (!maSer) return null
                      const maColor = inst.seriesColors[maSer.series_id] ?? maSer.default_color
                      return (
                        <label style={s.colorRow}>
                          <span style={s.paramName}>MA Color</span>
                          <input
                            data-testid={`color-${inst.instanceId}-volume_ma`}
                            type="color"
                            value={maColor}
                            onChange={e => handleSeriesColorChange(inst.instanceId, maSer.series_id, e.target.value)}
                            style={s.colorInput}
                          />
                        </label>
                      )
                    })()}

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

                {/* ── RSI settings (RSI-1C.2) ── */}
                {isEditing && inst.toolId === RSI_TOOL_ID && (
                  <div data-testid={`editor-${inst.instanceId}`} style={s.editor}>

                    {/* RSI Period */}
                    <label style={s.paramRow}>
                      <span style={s.paramName}>RSI Period</span>
                      <input
                        data-testid={`param-${inst.instanceId}-period`}
                        type="number"
                        value={currEdits.period ?? String(inst.parameters.period ?? 14)}
                        min={2}
                        step={1}
                        onChange={e => setEditedParams(prev => ({
                          ...prev,
                          [inst.instanceId]: {
                            ...(prev[inst.instanceId] ?? {}),
                            period: e.target.value,
                          },
                        }))}
                        style={s.paramInput}
                      />
                    </label>

                    {/* Middle Band (Midline Value) */}
                    <label style={s.paramRow}>
                      <span style={s.paramName}>Middle Band</span>
                      <input
                        data-testid={`param-${inst.instanceId}-midline_value`}
                        type="number"
                        value={currEdits.midline_value ?? String(inst.parameters.midline_value ?? RSI_MIDLINE_DEFAULT)}
                        min={0}
                        max={100}
                        step={0.1}
                        onChange={e => setEditedParams(prev => ({
                          ...prev,
                          [inst.instanceId]: {
                            ...(prev[inst.instanceId] ?? {}),
                            midline_value: e.target.value,
                          },
                        }))}
                        style={s.paramInput}
                      />
                    </label>

                    {/* Show RSI Smoothing */}
                    <label style={s.paramRow}>
                      <span style={s.paramName}>Show RSI Smoothing</span>
                      <input
                        data-testid={`param-${inst.instanceId}-show_smoothing`}
                        type="checkbox"
                        checked={currEdits.show_smoothing === '1'}
                        onChange={e => setEditedParams(prev => ({
                          ...prev,
                          [inst.instanceId]: {
                            ...(prev[inst.instanceId] ?? {}),
                            show_smoothing: e.target.checked ? '1' : '0',
                          },
                        }))}
                        style={{ cursor: 'pointer' }}
                      />
                    </label>

                    {/* Smoothing Type — only shown when smoothing enabled */}
                    {currEdits.show_smoothing === '1' && (
                      <label style={s.paramRow}>
                        <span style={s.paramName}>Smoothing Type</span>
                        <select
                          data-testid={`param-${inst.instanceId}-smoothing_type`}
                          value={currEdits.smoothing_type ?? String(inst.parameters.smoothing_type ?? 'SMA')}
                          onChange={e => setEditedParams(prev => ({
                            ...prev,
                            [inst.instanceId]: {
                              ...(prev[inst.instanceId] ?? {}),
                              smoothing_type: e.target.value,
                            },
                          }))}
                          style={s.paramInput}
                        >
                          <option value="SMA">SMA</option>
                          <option value="EMA">EMA</option>
                        </select>
                      </label>
                    )}

                    {/* Smoothing Length — only shown when smoothing enabled */}
                    {currEdits.show_smoothing === '1' && (
                      <label style={s.paramRow}>
                        <span style={s.paramName}>Smoothing Length</span>
                        <input
                          data-testid={`param-${inst.instanceId}-smoothing_length`}
                          type="number"
                          value={currEdits.smoothing_length ?? String(inst.parameters.smoothing_length ?? 14)}
                          min={1}
                          step={1}
                          onChange={e => setEditedParams(prev => ({
                            ...prev,
                            [inst.instanceId]: {
                              ...(prev[inst.instanceId] ?? {}),
                              smoothing_length: e.target.value,
                            },
                          }))}
                          style={s.paramInput}
                        />
                      </label>
                    )}

                    {/* Per-series style editor (color + line style) — applies immediately */}
                    {inst.artifact && inst.artifact.series.length > 0 && (
                      <div data-testid={`color-section-${inst.instanceId}`} style={s.colorSection}>
                        <div style={s.colorSectionTitle}>Style</div>
                        {inst.artifact.series.map(series => {
                          const effectiveColor = inst.seriesColors[series.series_id]
                            ?? (inst.artifact!.series.length === 1 ? inst.instanceColor : series.default_color)
                          const isLine = series.render_type !== 'histogram'
                          return (
                            <div key={series.series_id} style={s.colorRow}>
                              <span style={s.paramName}>{series.label}</span>
                              <input
                                data-testid={`color-${inst.instanceId}-${series.series_id}`}
                                type="color"
                                value={effectiveColor}
                                onChange={e => handleSeriesColorChange(inst.instanceId, series.series_id, e.target.value)}
                                style={s.colorInput}
                              />
                              {isLine && (
                                <select
                                  data-testid={`linestyle-${inst.instanceId}-${series.series_id}`}
                                  value={inst.seriesLineStyles[series.series_id] ?? 'solid'}
                                  onChange={e => handleSeriesLineStyleChange(inst.instanceId, series.series_id, e.target.value)}
                                  style={s.paramInput}
                                >
                                  <option value="solid">Solid</option>
                                  <option value="dashed">Dashed</option>
                                  <option value="dotted">Dotted</option>
                                </select>
                              )}
                            </div>
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

                {/* ── Generic parameter editor (all non-volume, non-RSI indicators) ── */}
                {isEditing && !isVolumeFamily(inst.toolId) && inst.toolId !== RSI_TOOL_ID && (
                  <div data-testid={`editor-${inst.instanceId}`} style={s.editor}>
                    {editableSpecs.map(spec => {
                      const val = currEdits[spec.name] ?? String(inst.parameters[spec.name] ?? '')
                      // Metadata-driven options take priority; fall back to the
                      // hardcoded table for parameters not yet updated on the backend.
                      const dropdownOptions =
                        (spec.options && spec.options.length > 0 ? spec.options : null)
                        ?? CHART_PARAM_DROPDOWNS[spec.name]
                      return (
                        <label key={spec.name} style={s.paramRow}>
                          <span style={s.paramName}>{spec.name}</span>
                          {dropdownOptions ? (
                            /* Controlled dropdown — prevents arbitrary string entry */
                            <select
                              data-testid={`param-${inst.instanceId}-${spec.name}`}
                              value={val}
                              onChange={e => setEditedParams(prev => ({
                                ...prev,
                                [inst.instanceId]: { ...(prev[inst.instanceId] ?? {}), [spec.name]: e.target.value },
                              }))}
                              style={s.paramInput}
                            >
                              {dropdownOptions.map(opt => (
                                <option key={opt} value={opt}>{opt}</option>
                              ))}
                            </select>
                          ) : (
                            /* Numeric input for int/float parameters */
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
                          )}
                        </label>
                      )
                    })}

                    {/* Per-series style editor (color + line style) — applies immediately */}
                    {inst.artifact && inst.artifact.series.length > 0 && (
                      <div data-testid={`color-section-${inst.instanceId}`} style={s.colorSection}>
                        <div style={s.colorSectionTitle}>Style</div>
                        {inst.artifact.series.map(series => {
                          const effectiveColor = inst.seriesColors[series.series_id]
                            ?? (inst.artifact!.series.length === 1 ? inst.instanceColor : series.default_color)
                          const isLine = series.render_type !== 'histogram'
                          return (
                            <div key={series.series_id} style={s.colorRow}>
                              <span style={s.paramName}>{series.label}</span>
                              <input
                                data-testid={`color-${inst.instanceId}-${series.series_id}`}
                                type="color"
                                value={effectiveColor}
                                onChange={e => handleSeriesColorChange(inst.instanceId, series.series_id, e.target.value)}
                                style={s.colorInput}
                              />
                              {isLine && (
                                <select
                                  data-testid={`linestyle-${inst.instanceId}-${series.series_id}`}
                                  value={inst.seriesLineStyles[series.series_id] ?? 'solid'}
                                  onChange={e => handleSeriesLineStyleChange(inst.instanceId, series.series_id, e.target.value)}
                                  style={s.paramInput}
                                >
                                  <option value="solid">Solid</option>
                                  <option value="dashed">Dashed</option>
                                  <option value="dotted">Dotted</option>
                                </select>
                              )}
                            </div>
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
}) // end forwardRef

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
